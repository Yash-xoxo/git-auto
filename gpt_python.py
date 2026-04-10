#!/usr/bin/env python3
"""
Scrape GitHub Trending and generate a clean static index.html page.

Features:
- Pulls trending repositories from GitHub Trending
- Visits each repository page via the GitHub API
- Fetches repo topics
- Fetches and renders README.md
- Overwrites index.html every run
- Produces a polished, responsive HTML dashboard

Install:
    pip install requests beautifulsoup4 markdown

Run:
    python github_trending_scraper.py
    python github_trending_scraper.py --since weekly --limit 12
"""

from __future__ import annotations

import argparse
import base64
import html
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import requests
from bs4 import BeautifulSoup


TRENDING_URL = "https://github.com/trending"
API_ROOT = "https://api.github.com"
DEFAULT_LIMIT = 12

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": "Mozilla/5.0 (compatible; GitHubTrendingScraper/1.0)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
)

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
if GITHUB_TOKEN:
    SESSION.headers.update({"Authorization": f"Bearer {GITHUB_TOKEN}"})


@dataclass
class TrendingRepo:
    owner: str
    name: str
    url: str
    description: str
    language: str
    stars_today: str
    total_stars: Optional[int]
    forks: Optional[int]
    topics: List[str]
    readme_html: str


def fetch_url(url: str, *, headers: Optional[dict] = None, timeout: int = 30) -> requests.Response:
    resp = SESSION.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def extract_slug_and_owner_repo(href: str) -> Optional[tuple[str, str]]:
    """
    Returns (owner, repo) for links like /owner/repo.
    Rejects deeper paths such as /owner/repo/issues.
    """
    m = re.fullmatch(r"/([^/]+)/([^/]+)", href or "")
    if not m:
        return None
    return m.group(1), m.group(2)


def scrape_trending_repos(since: str, limit: int) -> List[dict]:
    url = f"{TRENDING_URL}?since={since}"
    resp = fetch_url(url)
    soup = BeautifulSoup(resp.text, "html.parser")

    candidates = []
    seen = set()

    # GitHub Trending currently renders repository titles as h2 links.
    for heading in soup.find_all("h2"):
        link = heading.find("a", href=re.compile(r"^/[^/]+/[^/]+$"))
        if not link:
            continue

        slug = link.get("href", "").strip("/")
        if slug in seen:
            continue

        owner_repo = extract_slug_and_owner_repo(link.get("href", ""))
        if not owner_repo:
            continue

        seen.add(slug)
        owner, repo = owner_repo
        container = heading.find_parent(["article", "div"]) or heading.parent

        description = ""
        language = ""
        stars_today = ""

        if container:
            desc_tag = container.find("p")
            if desc_tag:
                description = clean_text(desc_tag.get_text(" ", strip=True))

            lang_tag = container.find(attrs={"itemprop": "programmingLanguage"})
            if lang_tag:
                language = clean_text(lang_tag.get_text(" ", strip=True))

            container_text = clean_text(container.get_text(" ", strip=True))
            m = re.search(r"([\d,]+)\s+stars\s+today", container_text, re.I)
            if m:
                stars_today = m.group(1)

        candidates.append(
            {
                "owner": owner,
                "repo": repo,
                "url": f"https://github.com/{owner}/{repo}",
                "description": description or "No description provided.",
                "language": language or "Unknown",
                "stars_today": stars_today or "0",
            }
        )

        if len(candidates) >= limit:
            break

    return candidates


def github_api_get_json(path: str) -> dict:
    url = f"{API_ROOT}{path}"
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    resp = fetch_url(url, headers=headers)
    return resp.json()


def fetch_repo_details(owner: str, repo: str) -> tuple[Optional[int], Optional[int], List[str]]:
    try:
        data = github_api_get_json(f"/repos/{owner}/{repo}")
        total_stars = data.get("stargazers_count")
        forks = data.get("forks_count")
        topics = data.get("topics") or []
        return total_stars, forks, topics
    except Exception:
        return None, None, []


def fetch_readme_markdown(owner: str, repo: str) -> Optional[str]:
    """
    Tries GitHub's README API endpoint first.
    Falls back cleanly if a README does not exist.
    """
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    url = f"{API_ROOT}/repos/{owner}/{repo}/readme"
    resp = SESSION.get(url, headers=headers, timeout=30)

    if resp.status_code == 404:
        return None
    resp.raise_for_status()

    ctype = resp.headers.get("content-type", "").lower()

    # Most common response is JSON with base64 content.
    if "application/json" in ctype:
        data = resp.json()
        content = data.get("content")
        encoding = data.get("encoding", "")
        if content and encoding == "base64":
            return base64.b64decode(content).decode("utf-8", errors="replace")
        download_url = data.get("download_url")
        if download_url:
            raw = fetch_url(download_url)
            return raw.text
        return None

    # Sometimes direct/raw content can be returned.
    return resp.text or None


def markdown_to_html(markdown_text: Optional[str]) -> str:
    if not markdown_text:
        return '<div class="empty">README not available for this repository.</div>'

    try:
        import markdown as md  # type: ignore

        rendered = md.markdown(
            markdown_text,
            extensions=["fenced_code", "tables", "extra", "sane_lists"],
            output_format="html5",
        )
        return rendered
    except Exception:
        return f"<pre>{html.escape(markdown_text)}</pre>"


def build_repo_card(repo: TrendingRepo) -> str:
    topics_html = ""
    if repo.topics:
        topic_bits = "".join(
            f'<span class="chip topic">{html.escape(topic)}</span>'
            for topic in repo.topics[:8]
        )
        topics_html = f"""
        <div class="chips">
            <span class="chip">{html.escape(repo.language)}</span>
            {topic_bits}
        </div>
        """
    else:
        topics_html = f"""
        <div class="chips">
            <span class="chip">{html.escape(repo.language)}</span>
        </div>
        """

    stars_total_html = (
        f'<span class="stat">★ {repo.total_stars:,}</span>' if repo.total_stars is not None else ""
    )
    forks_html = f'<span class="stat">⑂ {repo.forks:,}</span>' if repo.forks is not None else ""

    return f"""
    <article class="card">
        <div class="card-head">
            <div>
                <a class="repo-link" href="{html.escape(repo.url)}" target="_blank" rel="noreferrer">
                    {html.escape(repo.owner)} <span class="slash">/</span> {html.escape(repo.name)}
                </a>
                <p class="repo-desc">{html.escape(repo.description)}</p>
            </div>
            <div class="stars-today">
                <div class="stars-number">{html.escape(repo.stars_today)}</div>
                <div class="stars-label">stars today</div>
            </div>
        </div>

        <div class="meta-row">
            {stars_total_html}
            {forks_html}
        </div>

        {topics_html}

        <section class="readme-block">
            <div class="section-title">README preview</div>
            <div class="markdown-body">
                {repo.readme_html}
            </div>
        </section>
    </article>
    """


def build_html_page(repos: List[TrendingRepo], since: str) -> str:
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cards_html = "\n".join(build_repo_card(repo) for repo in repos)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>GitHub Trending Snapshot</title>
  <style>
    :root {{
      --bg: #0b0f17;
      --panel: #111827;
      --panel-2: #0f172a;
      --text: #e5e7eb;
      --muted: #94a3b8;
      --accent: #38bdf8;
      --accent-2: #22c55e;
      --border: rgba(148, 163, 184, 0.18);
      --shadow: 0 20px 60px rgba(0, 0, 0, 0.35);
      --radius: 22px;
    }}

    * {{
      box-sizing: border-box;
    }}

    body {{
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at top, rgba(56, 189, 248, 0.12), transparent 32%),
        linear-gradient(180deg, #050816 0%, #0b0f17 100%);
      color: var(--text);
    }}

    a {{
      color: inherit;
      text-decoration: none;
    }}

    .wrap {{
      width: min(1400px, calc(100% - 32px));
      margin: 0 auto;
      padding: 28px 0 50px;
    }}

    .hero {{
      background: linear-gradient(135deg, rgba(17, 24, 39, 0.92), rgba(15, 23, 42, 0.82));
      border: 1px solid var(--border);
      border-radius: calc(var(--radius) + 8px);
      box-shadow: var(--shadow);
      padding: 28px;
      margin-bottom: 22px;
      backdrop-filter: blur(14px);
    }}

    .eyebrow {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      border-radius: 999px;
      background: rgba(56, 189, 248, 0.12);
      color: #7dd3fc;
      font-size: 0.86rem;
      font-weight: 600;
      letter-spacing: 0.02em;
      margin-bottom: 14px;
    }}

    h1 {{
      margin: 0;
      font-size: clamp(2rem, 4vw, 3.8rem);
      line-height: 1.02;
      letter-spacing: -0.04em;
    }}

    .sub {{
      margin: 12px 0 0;
      max-width: 78ch;
      color: var(--muted);
      font-size: 1rem;
      line-height: 1.65;
    }}

    .hero-grid {{
      margin-top: 20px;
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 14px;
    }}

    .hero-stat {{
      border: 1px solid var(--border);
      background: rgba(15, 23, 42, 0.65);
      border-radius: 18px;
      padding: 16px;
    }}

    .hero-stat .label {{
      color: var(--muted);
      font-size: 0.85rem;
      margin-bottom: 6px;
    }}

    .hero-stat .value {{
      font-size: 1.2rem;
      font-weight: 700;
      letter-spacing: -0.02em;
    }}

    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
      gap: 18px;
    }}

    .card {{
      border: 1px solid var(--border);
      background: linear-gradient(180deg, rgba(17, 24, 39, 0.95), rgba(15, 23, 42, 0.9));
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      overflow: hidden;
    }}

    .card-head {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      padding: 22px 22px 14px;
      border-bottom: 1px solid rgba(148, 163, 184, 0.14);
    }}

    .repo-link {{
      display: inline-block;
      font-size: 1.25rem;
      font-weight: 800;
      letter-spacing: -0.03em;
      line-height: 1.25;
    }}

    .slash {{
      color: var(--muted);
      font-weight: 700;
    }}

    .repo-desc {{
      margin: 10px 0 0;
      color: #cbd5e1;
      line-height: 1.6;
      font-size: 0.96rem;
    }}

    .stars-today {{
      min-width: 110px;
      text-align: right;
      align-self: flex-start;
    }}

    .stars-number {{
      font-size: 1.75rem;
      font-weight: 900;
      letter-spacing: -0.05em;
      color: #fff;
    }}

    .stars-label {{
      color: var(--muted);
      font-size: 0.85rem;
      text-transform: uppercase;
      letter-spacing: 0.14em;
      margin-top: 4px;
    }}

    .meta-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      padding: 14px 22px 0;
    }}

    .stat {{
      font-size: 0.9rem;
      color: #dbeafe;
      background: rgba(56, 189, 248, 0.1);
      border: 1px solid rgba(56, 189, 248, 0.18);
      padding: 7px 10px;
      border-radius: 999px;
    }}

    .chips {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      padding: 14px 22px 0;
    }}

    .chip {{
      display: inline-flex;
      align-items: center;
      padding: 7px 10px;
      border-radius: 999px;
      background: rgba(148, 163, 184, 0.11);
      border: 1px solid rgba(148, 163, 184, 0.16);
      color: #e2e8f0;
      font-size: 0.86rem;
      line-height: 1;
    }}

    .chip.topic {{
      background: rgba(34, 197, 94, 0.1);
      border-color: rgba(34, 197, 94, 0.18);
    }}

    .readme-block {{
      margin-top: 18px;
      padding: 0 22px 22px;
    }}

    .section-title {{
      font-size: 0.82rem;
      text-transform: uppercase;
      letter-spacing: 0.16em;
      color: var(--muted);
      margin-bottom: 10px;
    }}

    .markdown-body {{
      max-height: 540px;
      overflow: auto;
      border-radius: 18px;
      border: 1px solid rgba(148, 163, 184, 0.14);
      background: rgba(2, 6, 23, 0.5);
      padding: 18px;
      line-height: 1.72;
      color: #e2e8f0;
    }}

    .markdown-body h1, .markdown-body h2, .markdown-body h3 {{
      margin-top: 1.2em;
      margin-bottom: 0.5em;
      line-height: 1.25;
    }}

    .markdown-body h1:first-child,
    .markdown-body h2:first-child,
    .markdown-body h3:first-child {{
      margin-top: 0;
    }}

    .markdown-body p {{
      margin: 0 0 1em;
    }}

    .markdown-body a {{
      color: #7dd3fc;
      text-decoration: underline;
      text-underline-offset: 2px;
    }}

    .markdown-body code {{
      background: rgba(148, 163, 184, 0.14);
      padding: 0.15rem 0.35rem;
      border-radius: 8px;
      font-size: 0.92em;
    }}

    .markdown-body pre {{
      overflow: auto;
      padding: 14px;
      border-radius: 14px;
      background: rgba(15, 23, 42, 0.9);
      border: 1px solid rgba(148, 163, 184, 0.16);
    }}

    .markdown-body img {{
      max-width: 100%;
      height: auto;
    }}

    .empty {{
      color: var(--muted);
      font-style: italic;
    }}

    .footer {{
      margin-top: 18px;
      color: var(--muted);
      font-size: 0.9rem;
      text-align: center;
      padding: 18px 0 6px;
    }}

    @media (max-width: 900px) {{
      .hero-grid {{
        grid-template-columns: 1fr;
      }}
      .card-head {{
        flex-direction: column;
      }}
      .stars-today {{
        text-align: left;
      }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <div class="eyebrow">GitHub Trending Snapshot</div>
      <h1>Trending repositories</h1>
      <p class="sub">
        Live snapshot generated from GitHub Trending, enriched with repository topics and README content.
        This page is regenerated from scratch on every run.
      </p>
      <div class="hero-grid">
        <div class="hero-stat">
          <div class="label">Date range</div>
          <div class="value">{html.escape(since.title())}</div>
        </div>
        <div class="hero-stat">
          <div class="label">Repositories rendered</div>
          <div class="value">{len(repos)}</div>
        </div>
        <div class="hero-stat">
          <div class="label">Generated at</div>
          <div class="value">{html.escape(generated_at)}</div>
        </div>
      </div>
    </section>

    <main class="grid">
      {cards_html}
    </main>

    <div class="footer">
      Overwrites index.html on each execution.
    </div>
  </div>
</body>
</html>
"""


def build_trending_dashboard(since: str, limit: int, output: str) -> Path:
    raw_items = scrape_trending_repos(since=since, limit=limit)

    repos: List[TrendingRepo] = []

    for item in raw_items:
        owner = item["owner"]
        repo_name = item["repo"]

        total_stars, forks, topics = fetch_repo_details(owner, repo_name)

        readme_md = fetch_readme_markdown(owner, repo_name)
        readme_html = markdown_to_html(readme_md)

        repos.append(
            TrendingRepo(
                owner=owner,
                name=repo_name,
                url=item["url"],
                description=item["description"],
                language=item["language"],
                stars_today=item["stars_today"],
                total_stars=total_stars,
                forks=forks,
                topics=topics,
                readme_html=readme_html,
            )
        )

    html_page = build_html_page(repos=repos, since=since)

    output_path = Path(output)
    output_path.write_text(html_page, encoding="utf-8")
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape GitHub Trending and generate index.html")
    parser.add_argument(
        "--since",
        choices=["daily", "weekly", "monthly"],
        default="daily",
        help="Trending time window",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help="Number of repositories to include",
    )
    parser.add_argument(
        "--output",
        default="index.html",
        help="Output HTML file name",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    path = build_trending_dashboard(args.since, args.limit, args.output)
    print(f"Generated {path.resolve()}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
GitHub Trending Scraper
Scrapes https://github.com/trending, fetches each repo's README,
and generates a polished index.html — overwritten on every run.
"""

import re
import sys
import time
import html as html_lib
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("Installing beautifulsoup4...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "beautifulsoup4",
                           "--quiet", "--break-system-packages"])
    from bs4 import BeautifulSoup

try:
    import markdown
except ImportError:
    print("Installing markdown...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "markdown",
                           "--quiet", "--break-system-packages"])
    import markdown

# ── helpers ──────────────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

LANG_COLORS = {
    "python":     "#3572A5", "typescript": "#2b7489", "javascript": "#f1e05a",
    "go":         "#00ADD8", "rust":       "#dea584", "java":       "#b07219",
    "c++":        "#f34b7d", "c#":         "#178600", "c":          "#555555",
    "ruby":       "#701516", "php":        "#4F5D95", "swift":      "#F05138",
    "kotlin":     "#A97BFF", "scala":      "#c22d40", "shell":      "#89e051",
    "html":       "#e34c26", "css":        "#563d7c", "vue":        "#41b883",
    "jupyter notebook": "#DA5B0B", "dockerfile": "#384d54",
    "r":          "#198CE7", "dart":       "#00B4AB",
    "elixir":     "#6e4a7e", "haskell":    "#5e5086",
    "lua":        "#000080", "matlab":     "#e16737",
}

def lang_color(lang: str) -> str:
    return LANG_COLORS.get((lang or "").lower(), "#8b949e")


def fetch(url: str, retries: int = 3, delay: float = 1.5) -> str | None:
    for attempt in range(retries):
        try:
            req = Request(url, headers=HEADERS)
            with urlopen(req, timeout=12) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except HTTPError as e:
            if e.code == 404:
                return None          # repo has no README or doesn't exist
            if e.code in (429, 503) and attempt < retries - 1:
                time.sleep(delay * (attempt + 1))
        except URLError:
            if attempt < retries - 1:
                time.sleep(delay)
    return None


# ── scraping ─────────────────────────────────────────────────────────────────

def scrape_trending():
    print("⏳  Fetching GitHub trending page…")
    raw = fetch("https://github.com/trending")
    if not raw:
        sys.exit("❌  Could not fetch github.com/trending")

    soup = BeautifulSoup(raw, "html.parser")
    articles = soup.select("article.Box-row")
    repos = []

    for article in articles:
        # ── repo path ──
        h2 = article.select_one("h2 a")
        if not h2:
            continue
        path = h2.get("href", "").strip("/")   # e.g. "owner/repo"
        if not path or "/" not in path:
            continue
        owner, name = path.split("/", 1)

        # ── description ──
        desc_tag = article.select_one("p")
        description = desc_tag.get_text(strip=True) if desc_tag else ""

        # ── language ──
        lang_tag = article.select_one("[itemprop='programmingLanguage']")
        language = lang_tag.get_text(strip=True) if lang_tag else ""

        # ── stars / forks ──
        nums = article.select("a.Link--muted")
        stars = nums[0].get_text(strip=True) if len(nums) > 0 else "0"
        forks = nums[1].get_text(strip=True) if len(nums) > 1 else "0"

        # ── stars today ──
        today_tag = article.select_one("span.d-inline-block.float-sm-right")
        stars_today = today_tag.get_text(strip=True) if today_tag else ""

        repos.append({
            "owner":       owner,
            "name":        name,
            "path":        path,
            "url":         f"https://github.com/{path}",
            "description": description,
            "language":    language,
            "stars":       stars,
            "forks":       forks,
            "stars_today": stars_today,
            "readme":      None,
        })

    print(f"✅  Found {len(repos)} trending repos.")
    return repos


def fetch_readmes(repos):
    for i, repo in enumerate(repos, 1):
        owner, name = repo["owner"], repo["name"]
        print(f"   [{i:2d}/{len(repos)}] Fetching README for {owner}/{name}…", end=" ", flush=True)

        readme_html = None
        for branch in ("main", "master"):
            for fname in ("README.md", "readme.md", "Readme.md", "README.MD"):
                raw_url = f"https://raw.githubusercontent.com/{owner}/{name}/{branch}/{fname}"
                content = fetch(raw_url)
                if content:
                    # Convert markdown → HTML, then truncate long READMEs
                    try:
                        readme_html = markdown.markdown(
                            content[:8000],   # cap at 8 000 chars to keep page lean
                            extensions=["fenced_code", "tables", "nl2br"]
                        )
                    except Exception:
                        readme_html = f"<pre>{html_lib.escape(content[:4000])}</pre>"
                    break
            if readme_html:
                break

        if readme_html:
            print("✓")
        else:
            print("– (not found)")

        repo["readme"] = readme_html
        time.sleep(0.4)   # be polite to GitHub


# ── HTML generation ───────────────────────────────────────────────────────────

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>GitHub Trending — {date}</title>
  <style>
    /* ── reset & tokens ───────────────────────────── */
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    :root {{
      --bg:        #0d1117;
      --surface:   #161b22;
      --surface2:  #21262d;
      --border:    #30363d;
      --accent:    #238636;
      --accent2:   #1f6feb;
      --text:      #e6edf3;
      --muted:     #8b949e;
      --red:       #f85149;
      --yellow:    #d29922;
      --radius:    10px;
      --shadow:    0 1px 3px rgba(0,0,0,.4), 0 4px 16px rgba(0,0,0,.3);
    }}

    body {{
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                   Helvetica, Arial, sans-serif;
      font-size: 15px;
      line-height: 1.6;
    }}

    /* ── header ───────────────────────────────────── */
    header {{
      background: linear-gradient(135deg, #161b22 0%, #0d1117 100%);
      border-bottom: 1px solid var(--border);
      padding: 28px 24px 22px;
      text-align: center;
      position: sticky; top: 0; z-index: 100;
      backdrop-filter: blur(8px);
    }}
    header .logo {{
      display: inline-flex; align-items: center; gap: 10px;
      font-size: 22px; font-weight: 700; color: var(--text);
      text-decoration: none;
    }}
    header .logo svg {{ width: 32px; height: 32px; fill: var(--text); }}
    header .subtitle {{
      color: var(--muted); font-size: 13px; margin-top: 6px;
    }}
    header .badge {{
      display: inline-block; background: var(--accent2); color: #fff;
      font-size: 11px; font-weight: 600; border-radius: 12px;
      padding: 2px 9px; margin-left: 8px; vertical-align: middle;
    }}

    /* ── layout ───────────────────────────────────── */
    main {{
      max-width: 1060px; margin: 36px auto; padding: 0 20px;
      display: flex; flex-direction: column; gap: 28px;
    }}

    /* ── rank ─────────────────────────────────────── */
    .rank-label {{
      font-size: 11px; font-weight: 700; text-transform: uppercase;
      letter-spacing: .08em; color: var(--muted);
      margin-bottom: 6px;
    }}

    /* ── card ─────────────────────────────────────── */
    .card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      overflow: hidden;
      box-shadow: var(--shadow);
      transition: border-color .2s, transform .15s;
    }}
    .card:hover {{ border-color: var(--accent2); transform: translateY(-2px); }}

    .card-header {{
      padding: 20px 24px 16px;
      display: flex; flex-wrap: wrap;
      align-items: flex-start; gap: 12px;
      border-bottom: 1px solid var(--border);
    }}
    .card-header-left {{ flex: 1; min-width: 0; }}

    .repo-name {{
      font-size: 18px; font-weight: 700;
      display: flex; align-items: center; flex-wrap: wrap; gap: 6px;
    }}
    .repo-name a {{
      color: var(--accent2); text-decoration: none;
      word-break: break-word;
    }}
    .repo-name a:hover {{ text-decoration: underline; }}
    .repo-owner {{
      color: var(--muted); font-weight: 400; font-size: 16px;
    }}

    .repo-desc {{
      color: var(--muted); font-size: 13.5px; margin-top: 6px;
      max-width: 720px;
    }}

    /* ── meta chips ───────────────────────────────── */
    .meta {{
      display: flex; flex-wrap: wrap; align-items: center; gap: 14px;
      padding: 10px 24px;
      background: var(--surface2);
      font-size: 13px; color: var(--muted);
    }}
    .meta-item {{ display: flex; align-items: center; gap: 5px; }}
    .lang-dot {{
      display: inline-block; width: 12px; height: 12px;
      border-radius: 50%;
    }}
    .stars-today {{
      margin-left: auto;
      background: var(--accent);
      color: #fff; font-size: 11px; font-weight: 700;
      border-radius: 12px; padding: 3px 10px;
      white-space: nowrap;
    }}

    /* ── readme section ───────────────────────────── */
    details {{ border-top: 1px solid var(--border); }}
    summary {{
      padding: 12px 24px;
      cursor: pointer;
      font-size: 13px; font-weight: 600; color: var(--muted);
      user-select: none;
      list-style: none;
      display: flex; align-items: center; gap: 8px;
      background: var(--surface);
    }}
    summary::-webkit-details-marker {{ display: none; }}
    summary::before {{
      content: "▶"; font-size: 9px;
      transition: transform .2s;
      display: inline-block;
    }}
    details[open] summary::before {{ transform: rotate(90deg); }}
    summary:hover {{ color: var(--text); }}

    .readme-body {{
      padding: 24px 28px 28px;
      background: var(--bg);
      overflow-x: auto;
    }}

    /* ── markdown styles ─────────────────────────── */
    .readme-body h1,
    .readme-body h2,
    .readme-body h3,
    .readme-body h4 {{
      color: var(--text); margin: 20px 0 10px;
      border-bottom: 1px solid var(--border); padding-bottom: 6px;
    }}
    .readme-body h1 {{ font-size: 1.6em; }}
    .readme-body h2 {{ font-size: 1.3em; }}
    .readme-body h3 {{ font-size: 1.1em; border: none; }}
    .readme-body p  {{ color: #cdd9e5; margin: 10px 0; }}
    .readme-body a  {{ color: var(--accent2); }}
    .readme-body a:hover {{ text-decoration: underline; }}
    .readme-body ul,
    .readme-body ol {{ padding-left: 20px; margin: 10px 0; color: #cdd9e5; }}
    .readme-body li {{ margin: 4px 0; }}
    .readme-body code {{
      background: var(--surface2); color: #e3b341;
      border-radius: 4px; padding: 2px 6px;
      font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
      font-size: 13px;
    }}
    .readme-body pre {{
      background: var(--surface2); border: 1px solid var(--border);
      border-radius: 6px; padding: 16px; overflow-x: auto; margin: 14px 0;
    }}
    .readme-body pre code {{
      background: none; padding: 0; color: #e6edf3; font-size: 13px;
    }}
    .readme-body table {{
      border-collapse: collapse; width: 100%; margin: 14px 0;
      font-size: 13px;
    }}
    .readme-body th,
    .readme-body td {{
      border: 1px solid var(--border);
      padding: 8px 12px; text-align: left;
    }}
    .readme-body th {{ background: var(--surface2); color: var(--text); }}
    .readme-body td {{ color: #cdd9e5; }}
    .readme-body blockquote {{
      border-left: 4px solid var(--accent2); padding: 6px 14px;
      margin: 12px 0; color: var(--muted);
      background: var(--surface2); border-radius: 0 6px 6px 0;
    }}
    .readme-body img {{
      max-width: 100%; border-radius: 6px; margin: 8px 0;
    }}
    .readme-truncated {{
      color: var(--muted); font-size: 12px; margin-top: 14px;
      text-align: center;
    }}

    /* ── footer ───────────────────────────────────── */
    footer {{
      text-align: center; color: var(--muted); font-size: 12.5px;
      padding: 36px 20px; border-top: 1px solid var(--border);
      margin-top: 20px;
    }}
    footer a {{ color: var(--accent2); text-decoration: none; }}
    footer a:hover {{ text-decoration: underline; }}

    /* ── no-readme placeholder ────────────────────── */
    .no-readme {{
      padding: 20px 24px; color: var(--muted); font-style: italic;
      font-size: 13px; text-align: center;
    }}

    /* ── responsive ───────────────────────────────── */
    @media (max-width: 600px) {{
      .card-header {{ flex-direction: column; }}
      .stars-today {{ margin-left: 0; }}
    }}
  </style>
</head>
<body>

<header>
  <a class="logo" href="https://github.com/trending" target="_blank" rel="noopener">
    <svg viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38
               0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13
               -.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66
               .07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15
               -.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0
               1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82
               1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01
               1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/>
    </svg>
    GitHub Trending
    <span class="badge">Today</span>
  </a>
  <div class="subtitle">
    Auto-generated on {date} &nbsp;·&nbsp; {count} trending repositories
  </div>
</header>

<main>
{cards}
</main>

<footer>
  Generated by <strong>scrape_github_trending.py</strong> on {date} &nbsp;·&nbsp;
  Data sourced from <a href="https://github.com/trending" target="_blank">github.com/trending</a>
</footer>

</body>
</html>
"""


def card_html(rank: int, repo: dict) -> str:
    owner    = html_lib.escape(repo["owner"])
    name     = html_lib.escape(repo["name"])
    url      = html_lib.escape(repo["url"])
    desc     = html_lib.escape(repo["description"]) if repo["description"] else \
               '<em style="color:var(--muted)">No description provided.</em>'
    lang     = html_lib.escape(repo["language"] or "")
    stars    = html_lib.escape(repo["stars"])
    forks    = html_lib.escape(repo["forks"])
    today    = html_lib.escape(repo["stars_today"])
    color    = lang_color(repo["language"])

    lang_chip = (
        f'<span class="meta-item">'
        f'<span class="lang-dot" style="background:{color}"></span>'
        f'{lang}'
        f'</span>'
    ) if lang else ""

    today_chip = (
        f'<span class="stars-today">⭐ {today}</span>'
    ) if today else ""

    readme_section = ""
    if repo["readme"]:
        readme_section = f"""\
<details>
  <summary>📖 README</summary>
  <div class="readme-body">
    {repo["readme"]}
    <p class="readme-truncated">(Preview — first 8 000 chars.
     <a href="{url}#readme" target="_blank" rel="noopener">View full README ↗</a>)</p>
  </div>
</details>"""
    else:
        readme_section = (
            '<div class="no-readme">README not available or could not be fetched.</div>'
        )

    return f"""\
<div>
  <div class="rank-label">#{rank}</div>
  <div class="card">
    <div class="card-header">
      <div class="card-header-left">
        <div class="repo-name">
          <span class="repo-owner">{owner} /</span>
          <a href="{url}" target="_blank" rel="noopener">{name}</a>
        </div>
        <div class="repo-desc">{desc}</div>
      </div>
    </div>
    <div class="meta">
      {lang_chip}
      <span class="meta-item">⭐ {stars}</span>
      <span class="meta-item">🍴 {forks}</span>
      {today_chip}
    </div>
    {readme_section}
  </div>
</div>"""


def build_html(repos: list) -> str:
    date  = datetime.now().strftime("%B %d, %Y  %H:%M")
    cards = "\n".join(card_html(i + 1, r) for i, r in enumerate(repos))
    return HTML_TEMPLATE.format(date=date, count=len(repos), cards=cards)


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    repos = scrape_trending()
    if not repos:
        sys.exit("❌  No repos found — GitHub may have changed their markup.")

    fetch_readmes(repos)

    print("\n🖊️  Building index.html…")
    html = build_html(repos)

    output_file = "index.html"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅  Done!  →  {output_file}  ({len(html):,} bytes)")
    print(f"   Open it in your browser:  file://{__import__('os').path.abspath(output_file)}")


if __name__ == "__main__":
    main()

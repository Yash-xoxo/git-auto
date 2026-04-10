#!/usr/bin/env python3
"""
GitHub Trending Scraper & README Renderer
Generates a clean, modern HTML page with trending repositories and their README files.
"""

import requests
from bs4 import BeautifulSoup
import markdown
import time
import sys
from urllib.parse import urljoin
from tqdm import tqdm  # Optional: progress bar

# ---------- Configuration ----------
TRENDING_URL = "https://github.com/trending"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
REQUEST_DELAY = 1  # seconds between requests to be polite
OUTPUT_FILE = "index.html"
# -----------------------------------

def fetch_page(url):
    """Fetch a URL and return BeautifulSoup object."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except requests.exceptions.RequestException as e:
        print(f"Error fetching {url}: {e}", file=sys.stderr)
        return None

def parse_trending_repos(soup):
    """Extract repository information from the trending page."""
    repos = []
    # Each repo is an <article class="Box-row"> inside a container
    articles = soup.select("article.Box-row")
    if not articles:
        print("Warning: No repository articles found. The HTML structure might have changed.", file=sys.stderr)
        return repos

    for article in articles:
        # Repository name and link
        h2 = article.find("h2", class_="h3 lh-condensed")
        if not h2:
            continue
        a_tag = h2.find("a")
        if not a_tag:
            continue
        # a_tag href is like "/owner/repo"
        repo_path = a_tag.get("href", "").strip()
        full_name = repo_path.lstrip("/")
        repo_url = urljoin("https://github.com", repo_path)

        # Description
        desc_tag = article.find("p", class_="col-9 color-fg-muted my-1 pr-4")
        description = desc_tag.get_text(strip=True) if desc_tag else ""

        # Language
        lang_tag = article.find("span", itemprop="programmingLanguage")
        language = lang_tag.get_text(strip=True) if lang_tag else "Unknown"

        # Stars and forks
        star_tag = article.find("a", href=lambda x: x and x.endswith("/stargazers"))
        stars = star_tag.get_text(strip=True).replace(",", "") if star_tag else "0"

        fork_tag = article.find("a", href=lambda x: x and x.endswith("/forks"))
        forks = fork_tag.get_text(strip=True).replace(",", "") if fork_tag else "0"

        # Stars today
        today_star_span = article.find("span", class_="d-inline-block float-sm-right")
        stars_today = "0"
        if today_star_span:
            # Find the last span containing star count
            star_spans = today_star_span.find_all("span")
            if star_spans:
                stars_today = star_spans[-1].get_text(strip=True).replace(",", "").split()[0]

        repos.append({
            "full_name": full_name,
            "owner": full_name.split("/")[0],
            "repo": full_name.split("/")[1],
            "url": repo_url,
            "description": description,
            "language": language,
            "stars": stars,
            "forks": forks,
            "stars_today": stars_today,
        })
    return repos

def get_readme_html(owner, repo):
    """
    Fetch README.md from raw.githubusercontent.com (trying main then master),
    convert Markdown to HTML, and return the HTML string.
    Returns empty string if not found or error.
    """
    branches = ["main", "master"]
    for branch in branches:
        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/README.md"
        try:
            resp = requests.get(raw_url, headers=HEADERS, timeout=8)
            if resp.status_code == 200:
                md_content = resp.text
                # Convert Markdown to HTML
                html_content = markdown.markdown(
                    md_content,
                    extensions=["fenced_code", "tables", "nl2br"]
                )
                return html_content
            elif resp.status_code != 404:
                # Non-404 error (e.g., 403 rate limit) - wait a bit and continue
                time.sleep(REQUEST_DELAY)
        except Exception:
            continue
    # If both fail, return empty
    return ""

def generate_html(repos_data):
    """Generate the final HTML page as a string."""
    # Prepare repository cards HTML
    cards_html = ""
    for repo in repos_data:
        # Format numbers with commas
        stars_fmt = f"{int(repo['stars']):,}" if repo['stars'].isdigit() else repo['stars']
        forks_fmt = f"{int(repo['forks']):,}" if repo['forks'].isdigit() else repo['forks']
        stars_today_fmt = f"{int(repo['stars_today']):,}" if repo['stars_today'].isdigit() else repo['stars_today']

        # README content (already HTML)
        readme_html = repo.get("readme_html", "")

        # Build card
        card = f"""
        <div class="repo-card">
            <div class="repo-header">
                <h2 class="repo-name">
                    <a href="{repo['url']}" target="_blank">{repo['full_name']}</a>
                </h2>
                <div class="repo-stats">
                    <span class="stat">⭐ {stars_fmt}</span>
                    <span class="stat">🍴 {forks_fmt}</span>
                    <span class="stat today">📈 {stars_today_fmt} today</span>
                </div>
            </div>
            <p class="repo-description">{repo['description']}</p>
            <div class="repo-language">Language: {repo['language']}</div>
            <div class="readme-container">
                <details>
                    <summary>📄 README.md</summary>
                    <div class="readme-content">
                        {readme_html if readme_html else "<p><i>No README found or unable to fetch.</i></p>"}
                    </div>
                </details>
            </div>
        </div>
        """
        cards_html += card

    # Full HTML template
    html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GitHub Trending with READMEs</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background: #f6f8fa;
            color: #24292f;
            line-height: 1.5;
            padding: 2rem 1rem;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        h1 {{
            font-size: 2.5rem;
            font-weight: 600;
            margin-bottom: 0.5rem;
            color: #1f2328;
            border-bottom: 1px solid #d0d7de;
            padding-bottom: 0.5rem;
        }}
        .subtitle {{
            color: #57606a;
            margin-bottom: 2rem;
            font-size: 1.1rem;
        }}
        .repo-card {{
            background: white;
            border: 1px solid #d0d7de;
            border-radius: 12px;
            padding: 1.5rem;
            margin-bottom: 2rem;
            box-shadow: 0 2px 5px rgba(0,0,0,0.03);
            transition: box-shadow 0.2s;
        }}
        .repo-card:hover {{
            box-shadow: 0 8px 24px rgba(140,149,159,0.2);
        }}
        .repo-header {{
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 0.75rem;
        }}
        .repo-name a {{
            font-size: 1.5rem;
            font-weight: 600;
            color: #0969da;
            text-decoration: none;
        }}
        .repo-name a:hover {{
            text-decoration: underline;
        }}
        .repo-stats {{
            display: flex;
            gap: 1.2rem;
            color: #57606a;
            font-size: 0.95rem;
        }}
        .stat {{
            display: flex;
            align-items: center;
            gap: 4px;
        }}
        .stat.today {{
            color: #1a7f37;
            font-weight: 500;
        }}
        .repo-description {{
            margin-bottom: 0.75rem;
            color: #24292f;
        }}
        .repo-language {{
            display: inline-block;
            background: #f3f4f6;
            padding: 0.2rem 0.8rem;
            border-radius: 20px;
            font-size: 0.85rem;
            color: #57606a;
            margin-bottom: 1rem;
        }}
        .readme-container {{
            margin-top: 1rem;
        }}
        details {{
            border-top: 1px solid #eaeef2;
            padding-top: 1rem;
        }}
        summary {{
            cursor: pointer;
            font-weight: 600;
            color: #0969da;
            user-select: none;
        }}
        summary:hover {{
            color: #0550ae;
        }}
        .readme-content {{
            margin-top: 1rem;
            padding: 1rem;
            background: #f6f8fa;
            border-radius: 8px;
            border: 1px solid #d0d7de;
            overflow-x: auto;
        }}
        /* Markdown rendered styles */
        .readme-content h1, .readme-content h2, .readme-content h3 {{
            margin-top: 1.5rem;
            margin-bottom: 0.5rem;
            font-weight: 600;
        }}
        .readme-content h1 {{ font-size: 1.8rem; border-bottom: 1px solid #d0d7de; padding-bottom: 0.3rem; }}
        .readme-content h2 {{ font-size: 1.5rem; border-bottom: 1px solid #d0d7de; padding-bottom: 0.3rem; }}
        .readme-content h3 {{ font-size: 1.25rem; }}
        .readme-content p {{ margin-bottom: 1rem; }}
        .readme-content pre {{
            background: #1f2328;
            color: #e6edf3;
            padding: 1rem;
            border-radius: 6px;
            overflow-x: auto;
            margin: 1rem 0;
        }}
        .readme-content code {{
            background: #eaeef2;
            padding: 0.2rem 0.4rem;
            border-radius: 4px;
            font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
            font-size: 0.9em;
        }}
        .readme-content pre code {{
            background: none;
            padding: 0;
        }}
        .readme-content table {{
            border-collapse: collapse;
            width: 100%;
            margin: 1rem 0;
        }}
        .readme-content th, .readme-content td {{
            border: 1px solid #d0d7de;
            padding: 0.5rem 1rem;
        }}
        .readme-content th {{
            background: #f6f8fa;
            font-weight: 600;
        }}
        .readme-content a {{
            color: #0969da;
            text-decoration: none;
        }}
        .readme-content a:hover {{
            text-decoration: underline;
        }}
        .readme-content ul, .readme-content ol {{
            padding-left: 2rem;
            margin-bottom: 1rem;
        }}
        .footer {{
            margin-top: 2rem;
            text-align: center;
            color: #57606a;
            font-size: 0.9rem;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🔥 GitHub Trending</h1>
        <div class="subtitle">Today's most popular repositories — with full README content</div>
        <div class="repo-list">
            {cards_html}
        </div>
        <div class="footer">
            Generated on {time.strftime("%Y-%m-%d %H:%M:%S")} • Data from GitHub Trending
        </div>
    </div>
</body>
</html>"""
    return html_template

def main():
    print("🚀 Fetching GitHub Trending page...")
    soup = fetch_page(TRENDING_URL)
    if not soup:
        print("Failed to fetch trending page. Exiting.")
        sys.exit(1)

    repos = parse_trending_repos(soup)
    if not repos:
        print("No repositories found. Exiting.")
        sys.exit(1)

    print(f"✅ Found {len(repos)} trending repositories.")
    print("📥 Fetching README files (this may take a moment)...")

    # Optional: progress bar if tqdm is installed
    try:
        iterator = tqdm(repos, desc="Fetching READMEs", unit="repo")
    except NameError:
        iterator = repos

    for repo in iterator:
        readme_html = get_readme_html(repo["owner"], repo["repo"])
        repo["readme_html"] = readme_html
        time.sleep(REQUEST_DELAY)  # Be polite to GitHub

    print("🎨 Generating HTML page...")
    html_content = generate_html(repos)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"✨ Done! Open '{OUTPUT_FILE}' in your browser to view the result.")

if __name__ == "__main__":
    main()

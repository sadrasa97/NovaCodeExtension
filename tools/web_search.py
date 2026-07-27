"""DuckDuckGo web search tool for the agent."""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from typing import Optional


def duckduckgo_search(query: str, max_results: int = 8) -> str:
    """
    Search DuckDuckGo for a query and return formatted results with references.
    Uses DuckDuckGo's HTML lite endpoint (no API key needed).
    """
    if not query.strip():
        return "[search error] Empty query"

    try:
        results = _ddg_search(query, max_results=max_results)
        if not results:
            return f"No results found for: {query}"

        lines = [f"## Web Search Results for: {query}\n"]
        for i, r in enumerate(results, 1):
            lines.append(f"### [{i}] {r['title']}")
            lines.append(f"**URL:** {r['url']}")
            if r.get("snippet"):
                lines.append(f"**Summary:** {r['snippet']}")
            lines.append("")

        lines.append("---")
        lines.append(f"*{len(results)} results found*")
        return "\n".join(lines)
    except Exception as exc:
        return f"[search error] {exc}"


def _ddg_search(query: str, max_results: int = 8) -> list[dict]:
    """Fetch search results from DuckDuckGo HTML lite."""
    encoded_query = urllib.parse.quote_plus(query)
    url = f"https://html.duckduckgo.com/html/?q={encoded_query}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    }

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        raise RuntimeError(f"DuckDuckGo request failed: {exc}") from exc

    return _parse_ddg_html(html, max_results)


def _parse_ddg_html(html: str, max_results: int) -> list[dict]:
    """Parse DuckDuckGo HTML lite results."""
    results = []

    # Pattern to find result links and snippets
    # DuckDuckGo HTML lite uses class="result__a" for titles and class="result__snippet" for descriptions
    link_pattern = re.compile(
        r'<a[^>]+class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
        re.DOTALL | re.IGNORECASE,
    )
    snippet_pattern = re.compile(
        r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
        re.DOTALL | re.IGNORECASE,
    )

    links = link_pattern.findall(html)
    snippets = snippet_pattern.findall(html)

    for i, (raw_url, raw_title) in enumerate(links):
        if i >= max_results:
            break

        # Clean HTML tags from title
        title = re.sub(r"<[^>]+>", "", raw_title).strip()
        if not title:
            continue

        # Decode the URL (DuckDuckGo wraps URLs)
        actual_url = _extract_ddg_url(raw_url)
        if not actual_url:
            continue

        snippet = ""
        if i < len(snippets):
            snippet = re.sub(r"<[^>]+>", "", snippets[i]).strip()

        results.append({
            "title": title,
            "url": actual_url,
            "snippet": snippet,
        })

    return results


def _extract_ddg_url(raw_url: str) -> Optional[str]:
    """Extract actual URL from DuckDuckGo redirect URL."""
    if "duckduckgo.com" in raw_url and "uddg=" in raw_url:
        parsed = urllib.parse.urlparse(raw_url)
        params = urllib.parse.parse_qs(parsed.query)
        if "uddg" in params:
            return urllib.parse.unquote(params["uddg"][0])
    if raw_url.startswith("http"):
        return raw_url
    if raw_url.startswith("//"):
        return "https:" + raw_url
    return None

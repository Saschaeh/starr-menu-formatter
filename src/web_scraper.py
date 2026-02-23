"""Fetch and extract visible text from a restaurant menu web page."""

from __future__ import annotations

import requests
from bs4 import BeautifulSoup


_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}

_STRIP_TAGS = {"script", "style", "nav", "footer", "header", "noscript", "svg", "iframe"}


def scrape_menu_page(url: str, timeout: int = 20) -> str:
    """Fetch a URL and return cleaned visible text.

    Args:
        url: Full URL of the restaurant menu page.
        timeout: Request timeout in seconds.

    Returns:
        Cleaned text content ready for LLM parsing.

    Raises:
        ValueError: If the page has no extractable text content.
        requests.RequestException: On network / HTTP errors.
    """
    resp = requests.get(url, headers=_HEADERS, timeout=timeout)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    # Remove non-content tags
    for tag in soup.find_all(_STRIP_TAGS):
        tag.decompose()

    text = soup.get_text(separator="\n", strip=True)

    # Collapse runs of blank lines
    lines = [ln.strip() for ln in text.splitlines()]
    cleaned = "\n".join(ln for ln in lines if ln)

    if len(cleaned) < 50:
        raise ValueError(
            "The page returned very little text content. "
            "It may rely on JavaScript to load its menu — try a different URL."
        )

    return cleaned

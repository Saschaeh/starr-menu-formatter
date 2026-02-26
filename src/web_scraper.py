"""Fetch and extract visible text from a restaurant menu web page."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

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


def _validate_url(url: str) -> None:
    """Reject non-HTTPS URLs and URLs that resolve to private/internal IPs."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Only http/https URLs are allowed, got: {parsed.scheme}")
    if not parsed.hostname:
        raise ValueError("URL has no hostname")

    hostname = parsed.hostname
    # Block obvious internal hostnames
    if hostname in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
        raise ValueError("URLs pointing to localhost are not allowed")

    # Resolve hostname and check for private IPs
    try:
        for info in socket.getaddrinfo(hostname, None):
            addr = ipaddress.ip_address(info[4][0])
            if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
                raise ValueError(
                    f"URL resolves to a private/internal address ({addr}). "
                    "Please provide a public URL."
                )
    except socket.gaierror:
        raise ValueError(f"Could not resolve hostname: {hostname}")


def scrape_menu_page(url: str, timeout: int = 20) -> str:
    """Fetch a URL and return cleaned visible text.

    Args:
        url: Full URL of the restaurant menu page.
        timeout: Request timeout in seconds.

    Returns:
        Cleaned text content ready for LLM parsing.

    Raises:
        ValueError: If the URL is invalid/internal or the page has no extractable text.
        requests.RequestException: On network / HTTP errors.
    """
    _validate_url(url)
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

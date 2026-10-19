"""Fetch a grant page or PDF and reduce it to plain text for the extractor."""

import io

import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader

MAX_CHARS = 60_000
HEADERS = {"User-Agent": "GrantAgent/0.1 (education grant research)"}


def fetch_text(url: str, client: httpx.Client | None = None) -> str:
    own = client is None
    client = client or httpx.Client(follow_redirects=True, timeout=30, headers=HEADERS)
    try:
        resp = client.get(url)
        resp.raise_for_status()
    finally:
        if own:
            client.close()

    content_type = resp.headers.get("content-type", "")
    if "pdf" in content_type or url.lower().endswith(".pdf"):
        reader = PdfReader(io.BytesIO(resp.content))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    else:
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "noscript"]):
            tag.decompose()
        text = soup.get_text("\n", strip=True)
    return text[:MAX_CHARS]

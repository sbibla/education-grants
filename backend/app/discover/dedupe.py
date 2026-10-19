import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING = re.compile(r"^(utm_|fbclid|gclid|mc_)")


def canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if not _TRACKING.match(k)])
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower().removeprefix("www."), path, query, ""))


def dedupe_key(url: str) -> str:
    return hashlib.sha256(canonical_url(url).encode()).hexdigest()


def title_key(title: str, funder: str | None) -> str:
    norm = re.sub(r"[^a-z0-9]+", " ", f"{funder or ''} {title}".lower()).strip()
    return hashlib.sha256(norm.encode()).hexdigest()

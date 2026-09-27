"""Extract only already-fetched, bounded HTML. Never invoke a downloader."""

import hashlib
import re
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import urlsplit

from .public_fetch import FetchResult
from .research_types import Passage, Source


class ExtractError(Exception):
    def __init__(self, code: str = "extract_failed"):
        self.code = code
        super().__init__(code)


class _PageGate(HTMLParser):
    """Inspect bounded HTML for access gates, without running scripts or logging in."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text: list[str] = []
        self.hidden = 0
        self.password = False

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        if tag == "input" and (dict(attrs).get("type") or "").lower() == "password":
            self.password = True

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.text.append(data)


def _reject_access_gate(raw: str, content_type: str) -> None:
    gate = _PageGate()
    if content_type != "text/plain":
        gate.feed(raw)
        visible = " ".join(gate.text)
    else:
        visible = raw
    normalized = re.sub(r"\s+", " ", visible).lower()
    if gate.password or any(
        marker in normalized
        for marker in (
            "this page displays a fallback because interactive scripts did not run",
            "enable javascript to continue",
            "please enable javascript to view",
            "javascript is required to view",
            "sign in to continue",
            "log in to continue",
            "login required",
            "authentication required",
            "verify you are human",
            "checking your browser",
            "enable javascript and cookies",
        )
    ):
        # Reuse the sanitized access-gate code: never treat a fallback as evidence.
        raise ExtractError("challenge_page")


def extract_source(result: FetchResult, source_id: str, title: str = "") -> Source:
    # This first slice intentionally does not assert inferred metadata publication
    # dates. text_sha256 hashes exactly the retained, possibly truncated UTF-8 text.
    raw = result.body.decode("utf-8", errors="replace")
    _reject_access_gate(raw, result.content_type)
    lower = raw.lower()
    if any(
        marker in lower
        for marker in (
            "cf-chl-",
            "challenge-platform",
            "g-recaptcha",
            "h-captcha",
            "verify you are human",
            "checking your browser",
            "enable javascript and cookies",
        )
    ):
        raise ExtractError("challenge_page")
    try:
        if result.content_type == "text/plain":
            text = raw.strip()
            extractor = "plain-text.v1"
        else:
            import trafilatura

            # No URL argument, downloads, metadata date guessing, images or links.
            text = (
                trafilatura.extract(
                    result.body,
                    output_format="txt",
                    include_comments=False,
                    include_tables=False,
                    include_images=False,
                    include_links=False,
                    favor_precision=True,
                    with_metadata=False,
                )
                or ""
            )
            extractor = "trafilatura.2.2.0"
    except Exception as exc:
        raise ExtractError() from exc
    text = text.strip()[:6000]
    if not text or len(text) < 40:
        raise ExtractError()
    return Source(
        id=source_id,
        title=title[:300] or urlsplit(result.resolved_url).hostname or "Public source",
        url=result.url,
        resolved_url=result.resolved_url,
        retrieved_at=datetime.now(UTC).isoformat(),
        published_at=None,
        publisher=(urlsplit(result.resolved_url).hostname or "")[:300],
        text=text,
        text_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        extractor=extractor,
    )


def _terms(values: list[str]) -> set[str]:
    return {
        token
        for value in values
        for token in re.findall(r"[\w]+", value.casefold(), flags=re.UNICODE)
        if len(token) >= 2
    }


def source_passages(
    source: Source,
    queries: list[str] | None = None,
    *,
    max_passages: int = 3,
) -> list[Passage]:
    """Select exact windows by lexical overlap across the complete retained text.

    The first bounded snapshot keeps its historical first-three-window shape by
    default. Continuation archives can request all windows, while task-visible
    passages use the query-scored subset. No paraphrase or vector index is used.
    """
    if not 1 <= max_passages <= 8:
        raise ValueError("max_passages must be 1..8")
    windows = []
    terms = _terms(queries or [])
    for index, start in enumerate(range(0, len(source.text), 800), 1):
        end = min(start + 800, len(source.text))
        quote = source.text[start:end]
        score = sum(quote.casefold().count(term) for term in terms)
        windows.append((score, index, start, end, quote))
    if not windows:
        return []
    if terms and any(window[0] for window in windows):
        selected = sorted(windows, key=lambda item: (-item[0], item[1]))[:max_passages]
        selected.sort(key=lambda item: item[1])
    else:
        selected = windows[:max_passages]
    return [
        Passage(
            id=f"{source.id}_p{index}",
            source_id=source.id,
            start=start,
            end=end,
            quote=quote,
        )
        for _, index, start, end, quote in selected
    ]

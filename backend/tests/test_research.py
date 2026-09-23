import asyncio
import hashlib

import pytest
from pydantic import ValidationError

from tianji_lab import research
from tianji_lab.public_fetch import FetchError, FetchResult
from tianji_lab.research_types import ResearchBudget, ResearchOptions, ResearchState, SearchHit
from tianji_lab.search_provider import SearchError
from tianji_lab.source_extract import ExtractError, extract_source, source_passages

TEXT = "这是公开来源的准确陈述，不代表已验证因果。 " * 200


def source():
    return extract_source(
        FetchResult("https://example.com/a", "https://example.com/a", TEXT.encode(), "text/plain"),
        "source_1",
        "Fixture",
    )


def test_snapshot_hash_and_codepoint_slices():
    item = source()
    assert item.text_sha256 == hashlib.sha256(item.text.encode()).hexdigest()
    state = ResearchState(sources=[item], passages=source_passages(item))
    assert state.passages[0].quote == item.text[:800]
    payload = state.model_dump()
    payload["passages"][0]["quote"] = "invented quotation"
    with pytest.raises(ValidationError, match="exact source slice"):
        ResearchState.model_validate(payload)
    payload = state.model_dump()
    payload["sources"][0]["text"] += "changed"
    with pytest.raises(ValidationError, match="hash mismatch"):
        ResearchState.model_validate(payload)


def test_duplicate_source_and_unsafe_origins_rejected():
    item = source()
    with pytest.raises(ValidationError, match="duplicate source"):
        ResearchState(sources=[item, item])
    payload = item.model_dump()
    payload["resolved_url"] = "http://127.0.0.1/"
    with pytest.raises(ValidationError):
        type(item).model_validate(payload)
    with pytest.raises(ValidationError):
        ResearchState(errors=["raw provider error containing secret"])


def test_html_extraction_not_metadata_guessing():
    article = "Public evidence is a source statement, not a proven causal intervention. " * 15
    result = FetchResult(
        "https://example.com/",
        "https://example.com/",
        (
            '<html><head><meta property="article:published_time" content="2025-01-01"></head>'
            f"<body><nav>BOILERPLATE</nav><main><article><h1>Evidence</h1><p>{article}</p>"
            "</article></main></body></html>"
        ).encode(),
        "text/html",
    )
    item = extract_source(result, "source_1")
    assert "Public evidence" in item.text
    assert "BOILERPLATE" not in item.text
    assert item.published_at is None
    assert item.extractor == "trafilatura.2.2.0"
    with pytest.raises(ExtractError, match="challenge_page"):
        extract_source(
            FetchResult(result.url, result.url, b"<html>Verify you are human</html>", "text/html"),
            "source_1",
        )


@pytest.mark.parametrize(
    "gate",
    [
        "Notice: This page displays a fallback because interactive scripts did not run",
        "Notice: This page displays a <strong>fallback</strong> because\n"
        "interactive scripts did not run",
        "Sign in to continue",
        "Log in to continue",
        '<form><input type="PASSWORD"></form>',
        "Enable JavaScript to continue",
        "Verify you are human",
        "<div class='cf-chl-container'>Access check</div>",
    ],
)
def test_access_gates_are_not_evidence(gate):
    # Detect gates beyond the old 12KB scan, including markup/whitespace splits.
    body = (
        "<html><head><!--"
        + "x" * 13000
        + "--></head><body>"
        + gate
        + "<p>"
        + TEXT
        + "</p></body></html>"
    ).encode()
    with pytest.raises(ExtractError, match="challenge_page"):
        extract_source(
            FetchResult("https://example.com/a", "https://example.com/a", body, "text/html"),
            "source_1",
        )


def test_navigation_login_link_is_not_an_access_gate():
    body = (
        '<html><body><nav><a href="/login">Sign in</a></nav><article><p>'
        + TEXT
        + "</p></article></body></html>"
    ).encode()
    assert extract_source(
        FetchResult("https://example.com/a", "https://example.com/a", body, "text/html"), "source_1"
    ).text


def run_collect(monkeypatch, search, fetch, *, options=None, queries=None, check=lambda: None):
    state = ResearchState()
    checkpoints = []
    monkeypatch.setattr(research, "search_public", search)
    monkeypatch.setattr(research.PublicFetcher, "fetch", fetch)

    def checkpoint():
        ResearchState.model_validate(state)
        checkpoints.append(state.model_dump())

    asyncio.run(
        research.collect_research(
            queries or ["public query", " PUBLIC query ", "second query"],
            options or ResearchOptions(),
            state,
            checkpoint,
            check,
        )
    )
    return state, checkpoints


def test_collection_dedup_bounds_and_distinct_search_read(monkeypatch):
    async def search(query, **kwargs):
        return [
            SearchHit(title="Title", url=f"https://example.com/{i}", snippet="NOT EVIDENCE")
            for i in range(5)
        ]

    async def fetch(self, url):
        self.on_bytes(100)
        return FetchResult(url, url, TEXT.encode(), "text/plain")

    state, points = run_collect(monkeypatch, search, fetch)
    assert state.status == "succeeded"
    assert state.pages_used == 3
    assert state.queries_used == 2
    assert len(state.sources) == 1  # Identical text does not multiply independent evidence.
    assert len(state.hits) == 5
    assert all("NOT EVIDENCE" not in p.quote for p in state.passages)
    assert state.fetched_bytes == 300
    assert any(p["pages_used"] == 1 and not p["sources"] for p in points)


@pytest.mark.parametrize(
    ("max_pages", "duplicate", "failure", "expected"),
    [
        (3, False, None, ["search:A", "fetch:A1", "search:B", "fetch:B1", "fetch:A2"]),
        (
            5,
            False,
            None,
            ["search:A", "fetch:A1", "search:B", "fetch:B1", "fetch:A2", "fetch:B2", "fetch:A3"],
        ),
        (3, True, None, ["search:A", "fetch:A1", "search:B", "fetch:B1", "fetch:A2"]),
        (3, True, "fetch", ["search:A", "fetch:A1", "search:B", "fetch:B1", "fetch:A2"]),
        (3, True, "extract", ["search:A", "fetch:A1", "search:B", "fetch:B1", "fetch:A2"]),
        (1, False, None, ["search:A", "fetch:A1"]),
        (1, False, "fetch", ["search:A", "fetch:A1"]),
    ],
)
def test_query_round_robin_attempts(monkeypatch, max_pages, duplicate, failure, expected):
    events = []

    async def search(query, **kwargs):
        events.append(f"search:{query}")
        names = [f"{query}{i}" for i in range(1, 4)]
        if duplicate:
            names = ["A1", "A1", *names]
        return [
            SearchHit(title=name, url=f"https://example.com/{name}", snippet="") for name in names
        ]

    async def fetch(self, url):
        name = url.rsplit("/", 1)[-1]
        events.append(f"fetch:{name}")
        if name == "A1" and failure == "fetch":
            raise FetchError("fetch_failed")
        body = f"{name} {TEXT}".encode()
        content_type = "text/plain"
        if name == "A1" and failure == "extract":
            body = b"<html>Verify you are human</html>"
            content_type = "text/html"
        self.on_bytes(len(body))
        return FetchResult(url, url, body, content_type)

    state, points = run_collect(
        monkeypatch,
        search,
        fetch,
        queries=["A", "B"],
        options=ResearchOptions(budget=ResearchBudget(max_pages=max_pages)),
    )
    assert events == expected
    assert state.pages_used == max_pages
    assert state.queries_used == (1 if max_pages == 1 else 2)
    assert len(state.sources) == max_pages - bool(failure)
    assert len({hit.url for hit in state.hits}) == len(state.hits)
    assert state.status == (
        "failed" if failure and max_pages == 1 else "partial" if failure else "succeeded"
    )
    if failure:
        assert ("fetch_failed" if failure == "fetch" else "challenge_page") in state.errors
    # Every attempt is checkpointed before its source can appear.
    for attempt in range(1, max_pages + 1):
        assert any(p["pages_used"] == attempt and len(p["sources"]) < attempt for p in points)


def test_query_dedup_and_provider_errors_sanitized(monkeypatch):
    async def search(query, **kwargs):
        raise SearchError("search_failed")

    async def fetch(*args):
        pytest.fail("no fetch without hits")

    state, _ = run_collect(monkeypatch, search, fetch)
    assert state.queries_used == 2
    assert state.queries == ["public query", "second query"]
    assert state.status == "failed"
    assert state.errors == ["search_failed", "no_sources"]
    assert not state.passages


def test_robots_failure_keeps_partial_evidence(monkeypatch):
    async def search(*args, **kwargs):
        return [SearchHit(title="", url=f"https://example.com/{i}", snippet="") for i in range(2)]

    async def fetch(self, url):
        if url.endswith("1"):
            raise FetchError("robots_denied")
        return FetchResult(url, url, TEXT.encode(), "text/plain")

    state, _ = run_collect(monkeypatch, search, fetch)
    assert state.status == "partial"
    assert state.errors == ["robots_denied"]
    assert len(state.sources) == 1


def test_fallback_failure_never_publishes_source_or_passage(monkeypatch):
    async def search(*args, **kwargs):
        return [SearchHit(title="About Python", url="https://www.python.org/about/", snippet="hit")]

    async def fetch(self, url):
        return FetchResult(
            url,
            url,
            b"<html><body><p>Notice: This page displays a fallback because interactive "
            b"scripts did not run</p></body></html>",
            "text/html",
        )

    state, checkpoints = run_collect(monkeypatch, search, fetch, queries=["Python"])
    assert state.status == "failed"
    assert "challenge_page" in state.errors
    assert state.hits and state.pages_used == 1
    assert all(not point["sources"] and not point["passages"] for point in checkpoints)


def test_offline_no_network(monkeypatch):
    async def never(*args, **kwargs):
        pytest.fail("offline must not perform network IO")

    state, _ = run_collect(monkeypatch, never, never, options=ResearchOptions(mode="offline"))
    assert state.status == "skipped"
    assert state.queries_used == state.pages_used == 0


def test_byte_budget_stops_further_reads(monkeypatch):
    async def search(*args, **kwargs):
        return [SearchHit(title="", url=f"https://example.com/{i}", snippet="") for i in range(3)]

    async def fetch(self, url):
        self.on_bytes(1024)
        raise FetchError("fetch_byte_limit")

    state, _ = run_collect(
        monkeypatch,
        search,
        fetch,
        options=ResearchOptions(budget=ResearchBudget(max_total_bytes=1024)),
    )
    assert state.pages_used == 1
    assert state.fetched_bytes == 1024
    assert state.status == "failed"


@pytest.mark.parametrize("stop", ["timeout", "cancel"])
def test_round_robin_interruption_keeps_completed_evidence(monkeypatch, stop):
    state = ResearchState()
    cleaned = False
    real_timeout = asyncio.timeout
    if stop == "timeout":
        monkeypatch.setattr(research.asyncio, "timeout", lambda _: real_timeout(0.05))

    async def search(query, **kwargs):
        return [SearchHit(title=query, url=f"https://example.com/{query}", snippet="")]

    async def fetch(self, url):
        nonlocal cleaned
        if url.endswith("B"):
            try:
                if stop == "cancel":
                    raise asyncio.CancelledError()
                await asyncio.sleep(30)
            finally:
                cleaned = True
        return FetchResult(url, url, TEXT.encode(), "text/plain")

    monkeypatch.setattr(research, "search_public", search)
    monkeypatch.setattr(research.PublicFetcher, "fetch", fetch)
    # Avoid a timing-dependent thread startup before the timeout test blocks.
    item = source()
    monkeypatch.setattr(research, "extract_source", lambda *args: item)

    def checkpoint():
        ResearchState.model_validate(state.model_dump())

    async def collect():
        await research.collect_research(
            ["A", "B"], ResearchOptions(), state, checkpoint, lambda: None
        )

    if stop == "cancel":
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(collect())
        assert state.finished_at is None
    else:
        asyncio.run(collect())
        assert state.status == "partial"
        assert state.errors == ["research_timeout"]
    assert cleaned
    assert state.queries_used == state.pages_used == 2
    assert state.sources == [item]
    assert state.passages


def test_caller_halt_propagates_from_network_wait(monkeypatch):
    class Halt(Exception):
        pass

    started = False
    cleaned = False

    async def search(*args, **kwargs):
        return [SearchHit(title="", url="https://example.com/a", snippet="")]

    async def fetch(*args):
        nonlocal started, cleaned
        started = True
        try:
            await asyncio.sleep(30)
        finally:
            cleaned = True

    def check():
        if started:
            raise Halt()

    with pytest.raises(Halt):
        run_collect(monkeypatch, search, fetch, check=check)
    assert cleaned

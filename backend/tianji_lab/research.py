"""Sequential bounded public research. Search snippets are never source passages."""

import asyncio
import contextlib
from collections.abc import Awaitable, Callable, Iterator
from datetime import UTC, datetime
from typing import TypeVar

from .public_fetch import FetchError, PublicFetcher
from .research_types import Passage, ResearchOptions, ResearchState, SearchHit, Source
from .search_provider import SearchError, search_public
from .source_extract import ExtractError, extract_source, source_passages

T = TypeVar("T")


async def _checked_wait[T](awaitable: Awaitable[T], check: Callable[[], None]) -> T:
    task = asyncio.ensure_future(awaitable)
    try:
        while not task.done():
            check()
            await asyncio.wait({task}, timeout=0.1)
        check()
        return task.result()
    finally:
        if not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


async def collect_research(
    queries: list[str],
    options: ResearchOptions,
    state: ResearchState,
    checkpoint: Callable[[], None],
    check: Callable[[], None],
    *,
    passage_limit: int = 3,
    known_sources: dict[str, Source] | None = None,
    normalize_source: Callable[[Source], Source] | None = None,
    on_evidence: Callable[[str, Source, list[Passage], bool], None] | None = None,
    include_known_sources: bool = True,
) -> None:
    """Mutate one bounded snapshot; the caller owns atomic validation/persistence.

    Caller Halt exceptions and cancellation propagate unchanged. Failed reads,
    provider errors and research deadline expiry retain existing evidence. The
    byte counter covers public-fetch accepted body bytes, not DDGS/DNS/headers.
    """
    check()
    if options.mode == "offline":
        state.status = "skipped"
        state.finished_at = datetime.now(UTC).isoformat()
        checkpoint()
        return
    state.status = "running"
    state.started_at = datetime.now(UTC).isoformat()
    checkpoint()
    budget = options.budget

    def error(code: str) -> None:
        if code not in state.errors and len(state.errors) < 10:
            state.errors.append(code)

    def count_bytes(count: int) -> None:
        state.fetched_bytes += count

    fetcher = PublicFetcher(
        budget.max_response_bytes,
        max(0, budget.max_total_bytes - state.fetched_bytes),
        on_bytes=count_bytes,
    )
    known_sources = known_sources or {}
    attempted_urls: set[str] = {s.url for s in state.sources}
    if not include_known_sources:
        attempted_urls.update(key for key in known_sources if not key.startswith("sha256:"))
    seen_hits = {hit.url for hit in state.hits}
    seen_queries = {query.casefold() for query in state.queries}

    def record_source(query: str, source: Source) -> None:
        source_match = next(
            (item for item in state.sources if item.text_sha256 == source.text_sha256), None
        )
        known_source = next(
            (item for item in known_sources.values() if item.text_sha256 == source.text_sha256),
            None,
        )
        is_new = source_match is None and known_source is None and len(state.sources) < 5
        if is_new:
            state.sources.append(source)
            source_match = source
        source_match = source_match or known_source
        selected: list[Passage] = []
        if source_match is not None:
            selected = source_passages(source_match, [query], max_passages=passage_limit)
            if is_new or source_match.id in {item.id for item in state.sources}:
                known_passages = {passage.id for passage in state.passages}
                state.passages.extend(
                    passage
                    for passage in selected
                    if passage.id not in known_passages and len(state.passages) < 15
                )
            if not on_evidence and source_match.id in {item.id for item in state.sources}:
                state.query_sources.setdefault(query, [])
                if source_match.id not in state.query_sources[query]:
                    state.query_sources[query].append(source_match.id)
        if on_evidence:
            on_evidence(query, source_match or source, selected, is_new)

    def can_fetch() -> bool:
        if state.pages_used >= budget.max_pages:
            return False
        if state.fetched_bytes >= budget.max_total_bytes:
            error("fetch_byte_limit")
            return False
        return True

    async def fetch_one(query: str, hits: Iterator[SearchHit]) -> bool:
        """Consume at most one new URL attempt, including failed reads/extraction."""
        for hit in hits:
            if hit.url in attempted_urls:
                if hit.url in known_sources and on_evidence:
                    record_source(query, known_sources[hit.url])
                continue
            if not can_fetch():
                return False
            check()
            attempted_urls.add(hit.url)
            state.pages_used += 1
            checkpoint()
            try:
                result = await _checked_wait(fetcher.fetch(hit.url), check)
            except FetchError as exc:
                error(exc.code)
                checkpoint()
                return True
            check()
            try:
                source = await _checked_wait(
                    asyncio.to_thread(
                        extract_source,
                        result,
                        f"source_{len(state.sources) + 1}",
                        hit.title,
                    ),
                    check,
                )
            except ExtractError as exc:
                error(exc.code)
                checkpoint()
                return True
            check()
            if normalize_source:
                source = normalize_source(source)
            known = next(
                (item for item in known_sources.values() if item.text_sha256 == source.text_sha256),
                None,
            )
            record_source(query, known or source)
            checkpoint()
            return True
        return False

    # These queues are local to this collection, not persisted resume state.
    pending: list[tuple[str, Iterator[SearchHit]]] = []
    try:
        async with asyncio.timeout(budget.max_seconds):
            for raw_query in queries:
                query = " ".join(raw_query.split())[:500]
                if not query or query.casefold() in seen_queries:
                    continue
                if state.queries_used >= budget.max_queries or state.pages_used >= budget.max_pages:
                    break
                check()
                seen_queries.add(query.casefold())
                state.queries.append(query)
                state.queries_used += 1
                checkpoint()
                try:
                    hits = await search_public(
                        query, timeout=min(20, budget.max_seconds), check=check
                    )
                except SearchError as exc:
                    error(exc.code)
                    checkpoint()
                    continue
                check()
                for hit in hits:
                    if hit.url not in seen_hits and len(state.hits) < 15:
                        state.hits.append(hit)
                        seen_hits.add(hit.url)
                checkpoint()
                # Search and read once per query before spending remaining pages.
                queue = iter(hits)
                if await fetch_one(query, queue):
                    pending.append((query, queue))
            while pending and can_fetch():
                next_round = []
                for query, queue in pending:
                    if not can_fetch():
                        break
                    if await fetch_one(query, queue):
                        next_round.append((query, queue))
                pending = next_round
    except TimeoutError:
        error("research_timeout")
    # Deliberately no broad catch: Halt/CancelledError belong to the durable job.
    check()
    if not state.queries:
        error("no_queries")
    if not state.sources:
        error("no_new_evidence" if on_evidence else "no_sources")
    state.status = (
        "skipped"
        if on_evidence and "no_new_evidence" in state.errors
        else (
            "partial"
            if state.sources and state.errors
            else ("succeeded" if state.sources else "failed")
        )
    )
    state.finished_at = datetime.now(UTC).isoformat()
    checkpoint()

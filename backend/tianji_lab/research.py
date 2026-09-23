"""Sequential bounded public research. Search snippets are never source passages."""

import asyncio
import contextlib
from collections.abc import Awaitable, Callable, Iterator
from datetime import UTC, datetime
from typing import TypeVar

from .public_fetch import FetchError, PublicFetcher
from .research_types import ResearchOptions, ResearchState, SearchHit
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
    attempted_urls: set[str] = {s.url for s in state.sources}
    seen_hits = {hit.url for hit in state.hits}
    seen_queries = {query.casefold() for query in state.queries}

    def can_fetch() -> bool:
        if state.pages_used >= budget.max_pages:
            return False
        if state.fetched_bytes >= budget.max_total_bytes:
            error("fetch_byte_limit")
            return False
        return True

    async def fetch_one(hits: Iterator[SearchHit]) -> bool:
        """Consume at most one new URL attempt, including failed reads/extraction."""
        for hit in hits:
            if hit.url in attempted_urls:
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
            if source.text_sha256 not in {s.text_sha256 for s in state.sources}:
                state.sources.append(source)
                state.passages.extend(source_passages(source))
            checkpoint()
            return True
        return False

    # These queues are local to this collection, not persisted resume state.
    pending: list[Iterator[SearchHit]] = []
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
                if await fetch_one(queue):
                    pending.append(queue)
            while pending and can_fetch():
                next_round = []
                for queue in pending:
                    if not can_fetch():
                        break
                    if await fetch_one(queue):
                        next_round.append(queue)
                pending = next_round
    except TimeoutError:
        error("research_timeout")
    # Deliberately no broad catch: Halt/CancelledError belong to the durable job.
    check()
    if not state.queries:
        error("no_queries")
    if not state.sources:
        error("no_sources")
    state.status = (
        "partial"
        if state.sources and state.errors
        else ("succeeded" if state.sources else "failed")
    )
    state.finished_at = datetime.now(UTC).isoformat()
    checkpoint()

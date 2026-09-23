"""Fixed DDGS Brave adapter in a killable, resource-limited subprocess.

Search uses the library's buffered HTTP client: its response bytes are NOT part
of PublicFetcher budgets and are NOT hard network-byte bounded. RLIMIT_AS/CPU,
wall deadlines and bounded IPC are containment, not a network sandbox. Only the
fixed trusted provider is contacted; no model-selected backend or auto fallback.
"""

import asyncio
import contextlib
import json
import os
import sys
from collections.abc import Callable

from pydantic import ValidationError

from .public_fetch import validate_public_url
from .research_types import SearchHit

MAX_OUTPUT_BYTES = 32768


class SearchError(Exception):
    def __init__(self, code: str = "search_failed"):
        self.code = code
        super().__init__(code)


def _child_environment() -> dict[str, str]:
    # No HOME/netrc, DDGS_PROXY, proxy variables, provider keys or parent secrets.
    return {"PATH": os.defpath, "LANG": "C.UTF-8", "PYTHONNOUSERSITE": "1"}


async def _read_output(process: asyncio.subprocess.Process) -> bytes:
    assert process.stdout is not None
    output = await process.stdout.read(MAX_OUTPUT_BYTES + 1)
    # StreamReader.read(n) need not reach EOF; loop while keeping a hard IPC cap.
    while len(output) <= MAX_OUTPUT_BYTES:
        chunk = await process.stdout.read(MAX_OUTPUT_BYTES + 1 - len(output))
        if not chunk:
            return output
        output += chunk
    raise SearchError("search_invalid")


async def search_public(
    query: str, *, timeout: float = 20, check: Callable[[], None] = lambda: None
) -> list[SearchHit]:
    if not query.strip() or len(query) > 500:
        raise SearchError("search_invalid")
    check()
    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "tianji_lab.search_provider",
            "--worker",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=_child_environment(),
            cwd="/",
            limit=MAX_OUTPUT_BYTES + 1,
        )
    except OSError as exc:
        raise SearchError() from exc
    reader = asyncio.create_task(_read_output(process))
    try:
        assert process.stdin is not None
        process.stdin.write(json.dumps({"query": query}).encode("utf-8"))
        await process.stdin.drain()
        process.stdin.close()
        deadline = asyncio.get_running_loop().time() + min(timeout, 25)
        while not reader.done():
            check()
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise SearchError("search_timeout")
            await asyncio.wait({reader}, timeout=min(0.1, remaining))
        output = reader.result()
        check()
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise SearchError("search_timeout")
        try:
            await asyncio.wait_for(process.wait(), timeout=remaining)
        except TimeoutError as exc:
            raise SearchError("search_timeout") from exc
        if process.returncode != 0:
            raise SearchError()
        try:
            items = json.loads(output)
            if not isinstance(items, list) or len(items) > 5:
                raise ValueError("invalid hits")
            hits = [SearchHit.model_validate(item) for item in items]
        except (ValueError, TypeError, ValidationError) as exc:
            raise SearchError("search_invalid") from exc
        if not hits:
            raise SearchError("search_no_results")
        return hits
    except (BrokenPipeError, ConnectionResetError) as exc:
        raise SearchError() from exc
    finally:
        # Both caller-owned Halt and asyncio cancellation reach this cleanup.
        if process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                process.kill()
        await process.wait()
        if not reader.done():
            reader.cancel()
        with contextlib.suppress(asyncio.CancelledError, SearchError):
            await reader


def _worker() -> int:
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (1536 * 1024 * 1024,) * 2)
        resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
        payload = json.loads(sys.stdin.buffer.read(4096))
        query = payload["query"]
        if not isinstance(query, str) or not query.strip() or len(query) > 500:
            return 1
        # Suppress third-party chatter, not merely our own logging. stdout is IPC
        # containing only bounded hits; errors and raw responses are never dumped.
        with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink):
            from ddgs.engines.brave import Brave

            engine = Brave(proxy=None, timeout=10, verify=True)
            if engine.name != "brave" or engine.search_url != "https://search.brave.com/search":
                return 1
            results = engine.search(query, region="us-en", safesearch="moderate", page=1) or []
            hits: list[dict[str, str]] = []
            for result in results:
                try:
                    url = validate_public_url(result.href)
                except (ValueError, TypeError):
                    continue
                hits.append(
                    {
                        "title": result.title[:300],
                        "url": url,
                        "snippet": result.body[:1000],
                    }
                )
                if len(hits) == 5:
                    break
        encoded = json.dumps(hits, ensure_ascii=False).encode("utf-8")
        if len(encoded) > MAX_OUTPUT_BYTES:
            return 1
        sys.stdout.buffer.write(encoded)
        return 0
    except Exception:
        return 1


if __name__ == "__main__":
    raise SystemExit(_worker() if sys.argv[1:] == ["--worker"] else 1)

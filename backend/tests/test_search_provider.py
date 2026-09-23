import asyncio
import sys

import pytest

from tianji_lab import search_provider as sp


def fixture_process(monkeypatch, script):
    original = asyncio.create_subprocess_exec
    processes = []

    async def spawn(*args, **kwargs):
        assert args[0] == sys.executable
        assert args[1:] == ("-m", "tianji_lab.search_provider", "--worker")
        assert set(kwargs["env"]) == {"PATH", "LANG", "PYTHONNOUSERSITE"}
        proc = await original(sys.executable, "-c", script, **kwargs)
        processes.append(proc)
        return proc

    monkeypatch.setattr(sp.asyncio, "create_subprocess_exec", spawn)
    return processes


def test_subprocess_fixture_hits_and_no_ambient_env(monkeypatch):
    monkeypatch.setenv("DDGS_PROXY", "http://secret:password@localhost")
    monkeypatch.setenv("HTTPS_PROXY", "http://secret:password@localhost")
    script = (
        "import sys,json,os; data=json.load(sys.stdin); "
        "assert 'DDGS_PROXY' not in os.environ; assert 'HTTPS_PROXY' not in os.environ; "
        "print(json.dumps([{'title':data['query'],'url':'https://example.com/a','snippet':'snippet'}]))"
    )
    processes = fixture_process(monkeypatch, script)
    hits = asyncio.run(sp.search_public("public query"))
    assert hits[0].title == "public query"
    assert processes[0].returncode == 0


@pytest.mark.parametrize(
    "script,code",
    [
        ("print('not json')", "search_invalid"),
        ("print('x'*40000)", "search_invalid"),
        ("print('[]')", "search_no_results"),
        ("import time; time.sleep(30)", "search_timeout"),
        ("import sys; sys.exit(1)", "search_failed"),
    ],
)
def test_subprocess_failure_limits(monkeypatch, script, code):
    processes = fixture_process(monkeypatch, script)
    with pytest.raises(sp.SearchError, match=code):
        asyncio.run(sp.search_public("query", timeout=0.2))
    assert processes[0].returncode is not None


def test_cancel_kills_and_reaps(monkeypatch):
    processes = fixture_process(monkeypatch, "import time; time.sleep(30)")

    async def run():
        task = asyncio.create_task(sp.search_public("query"))
        while not processes:
            await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert processes[0].returncode is not None

    asyncio.run(run())


def test_caller_halt_propagates_and_reaps(monkeypatch):
    processes = fixture_process(monkeypatch, "import time; time.sleep(30)")

    class Halt(Exception):
        pass

    def check():
        if processes:
            raise Halt("caller-owned")

    with pytest.raises(Halt, match="caller-owned"):
        asyncio.run(sp.search_public("query", check=check))
    assert processes[0].returncode is not None

"""Launcher subprocess checks use only temporary trees and explicit command doubles."""

import json
import os
import shutil
import socket
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def executable(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/usr/bin/env bash\nset -eu\n" + content)
    path.chmod(0o755)


@pytest.fixture
def launcher(tmp_path):
    root = tmp_path / "checkout"
    root.mkdir()
    shutil.copyfile(ROOT / "start.sh", root / "start.sh")
    (root / "web" / "node_modules").mkdir(parents=True)
    lock = root / "web" / "package-lock.json"
    lock.write_text(json.dumps({"test_lock_revision": 1}))
    commands = tmp_path / "commands"
    calls = tmp_path / "calls"
    executable(commands / "uv", 'printf "uv %s\\n" "$*" >> "$TEST_CALLS"\n')
    executable(
        commands / "npm",
        'printf "npm %s\\n" "$*" >> "$TEST_CALLS"\n'
        'if [[ "$*" == "--prefix web ci" ]]; then\n'
        '  [[ "${TEST_CI_FAIL:-0}" == 0 ]] || exit 19\n'
        "  cp web/package-lock.json web/node_modules/test-installed-lock.json\n"
        "fi\n",
    )
    executable(commands / "curl", "exit 1\n")
    executable(
        root / "backend" / ".venv" / "bin" / "python",
        'printf "api %s\\n" "$*" >> "$TEST_CALLS"\nexit 17\n',
    )
    # Reserve only long enough to obtain an ephemeral port; no service is started.
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {
        **os.environ,
        "PATH": str(commands) + os.pathsep + os.environ["PATH"],
        "TEST_CALLS": str(calls),
        "TIANJI_PORT": str(port),
        "TIANJI_MODEL_PORT": "18789",
        "TIANJI_TOKEN": "launcher-test-only",
    }

    def run(data_dir, **overrides):
        return subprocess.run(
            ["bash", str(root / "start.sh"), "--no-model"],
            env={**env, "TIANJI_DATA_DIR": str(data_dir), **overrides},
            cwd=tmp_path,
            text=True,
            capture_output=True,
            timeout=20,
        )

    return root, calls, run


def test_launcher_reconciles_existing_node_modules_on_every_run(launcher):
    root, calls, run = launcher
    lock = root / "web" / "package-lock.json"
    installed = root / "web" / "node_modules" / "test-installed-lock.json"
    for revision in (1, 2):
        lock.write_text(json.dumps({"test_lock_revision": revision}))
        result = run(root / "custom-data")
        assert result.returncode == 1  # The explicit API double exits during readiness.
        assert "Contingent exited during startup" in result.stderr
        assert installed.read_bytes() == lock.read_bytes()
    lines = calls.read_text().splitlines()
    assert lines.count("npm --prefix web ci") == 2
    assert lines.count("npm --prefix web run build") == 2
    assert lines[1:3] == ["npm --prefix web ci", "npm --prefix web run build"]


def test_launcher_ci_failure_prevents_build_and_service_start(launcher):
    root, calls, run = launcher
    data = root / "uncreated-data"
    result = run(data, TEST_CI_FAIL="1")
    assert result.returncode == 19
    assert calls.read_text().splitlines() == [
        "uv sync --project backend --locked",
        "npm --prefix web ci",
    ]
    assert not data.exists()


@pytest.mark.parametrize("relative", [False, True])
def test_launcher_creates_private_custom_data_directory(launcher, relative):
    root, calls, run = launcher
    data = root / "custom data" / "nested"
    result = run(data.relative_to(root) if relative else data)
    assert result.returncode == 1
    assert "api " in calls.read_text()
    assert stat.S_IMODE(data.stat().st_mode) == 0o700
    assert stat.S_IMODE(data.parent.stat().st_mode) == 0o700


def test_launcher_does_not_rewrite_existing_data_or_permissions(launcher):
    root, calls, run = launcher
    data = root / "existing-data"
    data.mkdir(mode=0o750)
    data.chmod(0o750)
    token = data / "token"
    token.write_text("existing-test-only-token")
    token.chmod(0o640)
    database = data / "lab.sqlite3"
    database.write_bytes(b"test-placeholder-not-a-real-database")
    result = run(data)
    assert result.returncode == 1
    assert "api " in calls.read_text()
    assert stat.S_IMODE(data.stat().st_mode) == 0o750
    assert stat.S_IMODE(token.stat().st_mode) == 0o640
    assert token.read_text() == "existing-test-only-token"
    assert database.read_bytes() == b"test-placeholder-not-a-real-database"


def test_runtime_ignores_cover_arbitrary_directories_without_hiding_sources(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    shutil.copyfile(ROOT / ".gitignore", tmp_path / ".gitignore")
    ignored = [
        "token",
        "owner.lock",
        "my-custom-data/token",
        "my-custom-data/owner.lock",
        "deep/custom data/token",
        "deep/custom data/owner.lock",
        "deep/custom data/lab.sqlite3",
    ]
    visible = [
        "backend/tianji_lab/token.py",
        "docs/token.md",
        "web/package-lock.json",
        "backend/uv.lock",
        "custom-data/token-example",
        "custom-data/owner.lock.example",
    ]
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "--stdin"],
        input="\n".join(ignored + visible) + "\n",
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.splitlines() == ignored

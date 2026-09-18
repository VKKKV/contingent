"""Isolated SQLite storage; one connection per transaction, never legacy runs."""

import fcntl
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

MAX_JSON_BYTES = 1_048_576


def canonical(value) -> str:
    text = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    if len(text.encode()) > MAX_JSON_BYTES:
        raise ValueError("JSON exceeds 1 MiB")
    return text


class Store:
    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir).expanduser().resolve()
        if "runs" in self.data_dir.parts:
            raise ValueError("The laboratory must not use a legacy runs directory")
        self.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._owner = (self.data_dir / "owner.lock").open("a+b")
        try:
            fcntl.flock(self._owner.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self._owner.close()
            self._owner = None
            raise RuntimeError("Laboratory data directory is already in use") from exc
        self.path = self.data_dir / "laboratory.sqlite3"
        with self.transaction() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS scenario (
                    id TEXT PRIMARY KEY, revision INTEGER NOT NULL, spec_json TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS branch (
                    id TEXT PRIMARY KEY, scenario_id TEXT NOT NULL REFERENCES scenario(id),
                    parent_id TEXT REFERENCES branch(id), fork_tick INTEGER, name TEXT NOT NULL,
                    trajectory_json TEXT NOT NULL, branch_json TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, status TEXT NOT NULL,
                    input_json TEXT NOT NULL, result_json TEXT, error TEXT,
                    created_at TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status,created_at);
                CREATE TABLE IF NOT EXISTS workspace (
                    id TEXT PRIMARY KEY, revision INTEGER NOT NULL,
                    state_json TEXT NOT NULL, last_seen TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS observation (
                    id TEXT PRIMARY KEY, branch_id TEXT NOT NULL REFERENCES branch(id),
                    observation_json TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS observation_branch ON observation(branch_id);
                CREATE TABLE IF NOT EXISTS adjudication (
                    id TEXT PRIMARY KEY, branch_id TEXT NOT NULL REFERENCES branch(id),
                    observation_id TEXT NOT NULL REFERENCES observation(id),
                    result_json TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS adjudication_branch ON adjudication(branch_id);
                CREATE TABLE IF NOT EXISTS idempotency (
                    operation TEXT NOT NULL, request_id TEXT NOT NULL,
                    arguments_json TEXT NOT NULL, result_json TEXT NOT NULL,
                    PRIMARY KEY(operation,request_id));
            """)

    def close(self):
        if self._owner is not None:
            self._owner.close()
            self._owner = None

    @contextmanager
    def transaction(self):
        if self._owner is None:
            raise RuntimeError("Laboratory store is closed")
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=10000")
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

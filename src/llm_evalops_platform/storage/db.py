"""SQLite connection management.

One Database instance is shared process-wide. Each call to .connection() opens
a per-thread SQLite connection in WAL mode so the API and worker processes can
coexist on the same file without blocking each other.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from llm_evalops_platform.config import settings


class Database:
    def __init__(self, db_url: str) -> None:
        self._path = Path(db_url)
        self._local = threading.local()

    def _get_conn(self) -> sqlite3.Connection:
        if not getattr(self._local, "conn", None):
            self._path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self._path), check_same_thread=False, timeout=10)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return self._local.conn

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        yield self._get_conn()

    def init_db(self) -> None:
        sql = (Path(__file__).parent / "migrations" / "001_initial.sql").read_text()
        with self.connection() as conn:
            conn.executescript(sql)
            conn.commit()


db = Database(settings.database_url)

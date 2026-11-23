"""Run-scoped tool output shared by model pagination and the Web download."""

import os
import sqlite3
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4


@dataclass(frozen=True)
class ToolArtifact:
    id: str
    thread_id: str
    owner: str
    content: str


@contextmanager
def _database():
    root = Path(os.getenv("WEAVER_DATA_DIR") or Path(__file__).resolve().parents[1] / "data")
    root.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(root / "agent_artifacts.sqlite3")) as db, db:
        db.execute("""CREATE TABLE IF NOT EXISTS tool_artifacts (
            id TEXT PRIMARY KEY, thread_id TEXT NOT NULL, owner TEXT NOT NULL,
            call_id TEXT NOT NULL, content TEXT NOT NULL, UNIQUE(thread_id, call_id)
        )""")
        yield db


def save_tool_artifact(thread_id: str, owner: str, call_id: str, content: str) -> ToolArtifact:
    with _database() as db:
        db.execute(
            """INSERT INTO tool_artifacts VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(thread_id, call_id) DO NOTHING""",
            (uuid4().hex, thread_id, owner, call_id, content),
        )
        row = db.execute(
            "SELECT id, thread_id, owner, content FROM tool_artifacts WHERE thread_id=? AND call_id=? AND owner=?",
            (thread_id, call_id, owner),
        ).fetchone()
    if row is None:
        raise ValueError("Tool result already belongs to another owner")
    return ToolArtifact(*row)


def get_tool_artifact(
    artifact_id: str, owner: str, *, thread_id: str | None = None
) -> ToolArtifact | None:
    with _database() as db:
        row = db.execute(
            """SELECT id, thread_id, owner, content FROM tool_artifacts
                WHERE id=? AND owner=? AND (? IS NULL OR thread_id=?)""",
            (artifact_id, owner, thread_id, thread_id),
        ).fetchone()
    return ToolArtifact(*row) if row is not None else None

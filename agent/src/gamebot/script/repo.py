from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from .model import Script


def now() -> str:
    return datetime.now(UTC).isoformat()


class ScriptRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def save(self, s: Script) -> None:
        cur = self.conn.execute("SELECT version FROM scripts WHERE id=?", (s.id,)).fetchone()
        version = (cur["version"] + 1) if cur else 1
        self.conn.execute(
            "INSERT OR REPLACE INTO scripts(id, game_id, mode, graph, ref_width, ref_height,"
            " ref_dpi, updated_at, version, deleted) VALUES (?,?,?,?,?,?,?,?,?,0)",
            (
                s.id,
                s.game_id,
                s.mode,
                s.model_dump_json(),
                s.ref_width,
                s.ref_height,
                s.ref_dpi,
                now(),
                version,
            ),
        )
        self.conn.commit()

    def load(self, script_id: str) -> Script | None:
        r = self.conn.execute(
            "SELECT graph FROM scripts WHERE id=? AND deleted=0", (script_id,)
        ).fetchone()
        return Script.model_validate_json(r["graph"]) if r else None

    def for_game(self, game_id: str, mode: str) -> Script | None:
        r = self.conn.execute(
            "SELECT graph FROM scripts WHERE game_id=? AND mode=? AND deleted=0"
            " ORDER BY updated_at DESC",
            (game_id, mode),
        ).fetchone()
        return Script.model_validate_json(r["graph"]) if r else None

    def delete(self, script_id: str) -> None:
        """Tombstone: keeps the row so the deletion syncs to other machines."""
        self.conn.execute(
            "UPDATE scripts SET deleted=1, updated_at=?, version=version+1"
            " WHERE id=? AND deleted=0",
            (now(), script_id),
        )
        self.conn.commit()

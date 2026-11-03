from __future__ import annotations

import sqlite3

from pydantic import BaseModel, Field

from ..script.repo import now


class Game(BaseModel):
    id: str
    package: str
    popups: list[dict] = Field(default_factory=list)  # serialised PopupHandler dicts
    event_ocr_region: tuple[float, float, float, float] | None = None  # countdown on screen


class GameRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def save(self, g: Game) -> None:
        r = self.conn.execute("SELECT version FROM games WHERE id=?", (g.id,)).fetchone()
        self.conn.execute(
            "INSERT OR REPLACE INTO games(id, package, profile, updated_at, version)"
            " VALUES (?,?,?,?,?)",
            (g.id, g.package, g.model_dump_json(), now(), (r["version"] + 1) if r else 1),
        )
        self.conn.commit()

    def get(self, game_id: str) -> Game | None:
        r = self.conn.execute("SELECT profile FROM games WHERE id=?", (game_id,)).fetchone()
        return Game.model_validate_json(r["profile"]) if r else None

    def list(self) -> list[Game]:
        rows = self.conn.execute("SELECT profile FROM games").fetchall()
        return [Game.model_validate_json(r["profile"]) for r in rows]

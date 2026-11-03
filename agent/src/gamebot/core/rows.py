from __future__ import annotations

import json
import sqlite3
from datetime import datetime, time, timedelta

from pydantic import BaseModel, Field

from ..script.repo import now

MODES = ("event", "task", "train")  # global queue priority, highest first


class Schedule(BaseModel):
    active_from: str = "00:00"  # HH:MM, in the row's local time (utc_offset_min)
    active_to: str = "23:59"
    utc_offset_min: int = 0
    interval_min: dict[str, int] = Field(default_factory=lambda: {"task": 120, "train": 60})
    event_at: dict[str, str] = Field(default_factory=dict)  # mode -> ISO UTC start
    event_window_min: int = 30
    event_lead_min: int = 2
    last_run: dict[str, str] = Field(default_factory=dict)  # mode -> ISO UTC


class Row(BaseModel):
    id: int | None = None
    name: str = ""
    emulator_kind: str = ""
    emulator_ref: str = ""
    game_id: str = ""
    account_id: str = ""
    mode_priority: list[str] = Field(default_factory=lambda: ["event", "task", "train"])
    schedule: Schedule = Field(default_factory=Schedule)
    enabled: bool = True


def _t(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def in_active_hours(sch: Schedule, at: datetime) -> bool:
    local = (at + timedelta(minutes=sch.utc_offset_min)).time()
    a, b = _t(sch.active_from), _t(sch.active_to)
    return a <= local <= b if a <= b else (local >= a or local <= b)  # may wrap midnight


def due_modes(row: Row, at: datetime) -> list[str]:
    """Modes that should run now, ordered by the row's priority (best first)."""
    sch = row.schedule
    if not row.enabled or not in_active_hours(sch, at):
        return []
    due = []
    for mode in row.mode_priority:
        if mode == "event":
            ev = sch.event_at.get("event")
            if not ev:
                continue
            start = datetime.fromisoformat(ev)
            lo = start - timedelta(minutes=sch.event_lead_min)
            hi = start + timedelta(minutes=sch.event_window_min)
            last = sch.last_run.get(mode)
            if lo <= at <= hi and not (last and datetime.fromisoformat(last) >= lo):
                due.append(mode)
        else:
            iv = sch.interval_min.get(mode)
            if iv is None:
                continue
            last = sch.last_run.get(mode)
            if not last or at - datetime.fromisoformat(last) >= timedelta(minutes=iv):
                due.append(mode)
    return due


class RowRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def save(self, row: Row) -> Row:
        vals = (
            row.name,
            row.emulator_kind,
            row.emulator_ref,
            row.game_id,
            row.account_id,
            json.dumps({"order": row.mode_priority, "enabled": row.enabled}),
            row.schedule.model_dump_json(),
            now(),
        )
        if row.id is None:
            cur = self.conn.execute(
                "INSERT INTO rows(name, emulator_kind, emulator_ref, game_id, account_id,"
                " mode_priority, schedule, updated_at, version) VALUES (?,?,?,?,?,?,?,?,1)",
                vals,
            )
            row.id = cur.lastrowid
        else:
            self.conn.execute(
                "UPDATE rows SET name=?, emulator_kind=?, emulator_ref=?, game_id=?, account_id=?,"
                " mode_priority=?, schedule=?, updated_at=?, version=version+1 WHERE id=?",
                (*vals, row.id),
            )
        self.conn.commit()
        return row

    @staticmethod
    def _from(r: sqlite3.Row) -> Row:
        mp = json.loads(r["mode_priority"])
        return Row(
            id=r["id"],
            name=r["name"],
            emulator_kind=r["emulator_kind"],
            emulator_ref=r["emulator_ref"],
            game_id=r["game_id"],
            account_id=r["account_id"],
            mode_priority=mp["order"],
            enabled=mp.get("enabled", True),
            schedule=Schedule.model_validate_json(r["schedule"]),
        )

    def get(self, row_id: int) -> Row | None:
        r = self.conn.execute("SELECT * FROM rows WHERE id=?", (row_id,)).fetchone()
        return self._from(r) if r else None

    def list(self) -> list[Row]:
        return [self._from(r) for r in self.conn.execute("SELECT * FROM rows ORDER BY id")]

    def delete(self, row_id: int) -> None:
        self.conn.execute("DELETE FROM rows WHERE id=?", (row_id,))
        self.conn.commit()

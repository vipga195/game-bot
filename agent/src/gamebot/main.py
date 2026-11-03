from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .core.accounts import AccountRepo, KeyringVault, Vault
from .core.games import Game, GameRepo
from .core.rows import Row, RowRepo
from .core.runner import RowRunner
from .core.scheduler import Scheduler, start_background
from .db import connect, init_db
from .device import Device, connect_serial
from .emulators import AdbGenericDriver, LDPlayerDriver, Registry
from .play import Recorder
from .script import AssetStore
from .script.repo import ScriptRepo
from .sync import SyncClient


def default_registry() -> Registry:
    return Registry([LDPlayerDriver(), AdbGenericDriver()])


class AccountIn(BaseModel):
    game_id: str
    label: str
    username: str
    password: str


class RecorderStart(BaseModel):
    serial: str
    game_id: str
    mode: str = "task"
    script_id: str | None = None


class TapIn(BaseModel):
    x: int
    y: int
    from_screen: str | None = None
    to_screen: str | None = None


class MarkIn(BaseModel):
    name: str
    region: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)


class SyncIn(BaseModel):
    url: str
    token: str
    passphrase: str | None = None


def create_app(
    registry: Registry | None = None,
    data_dir: str | Path | None = None,
    vault: Vault | None = None,
    device_factory=None,
    run_scheduler: bool = False,
) -> FastAPI:
    data = Path(data_dir or os.environ.get("GAMEBOT_DATA", Path.home() / ".gamebot"))
    data.mkdir(parents=True, exist_ok=True)
    conn = connect(str(data / "gamebot.sqlite3"), check_same_thread=False)
    init_db(conn)
    registry = registry or default_registry()
    vault = vault or KeyringVault()
    rows, games, accounts = RowRepo(conn), GameRepo(conn), AccountRepo(conn, vault)
    runner = RowRunner(conn, registry, accounts, data / "assets", device_factory)
    events: list[dict] = []

    def on_event(e: dict) -> None:
        events.append({**e, "ts": datetime.now(UTC).isoformat()})
        del events[:-200]

    sched = Scheduler(rows, runner.run, lambda: datetime.now(UTC), on_event=on_event)
    bg = {}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if run_scheduler:
            bg["s"] = start_background(sched)
        yield
        if "s" in bg:
            bg["s"].shutdown(wait=False)

    app = FastAPI(title="gamebot-agent", lifespan=lifespan)
    app.add_middleware(  # the UI runs on another local origin (Vite dev, Tauri/Electron)
        CORSMiddleware,
        allow_origin_regex=r"^(https?://(localhost|127\.0\.0\.1)(:\d+)?|tauri://localhost|app://.*)$",
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.registry, app.state.scheduler, app.state.conn = registry, sched, conn
    rec: dict[str, Recorder] = {}
    make_dev = device_factory or (lambda serial: Device(connect_serial(serial)))

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/instances")
    def instances() -> list[dict]:
        return [asdict(i) for i in registry.scan()]

    # ---- rows / games / accounts ----------------------------------------
    @app.get("/rows")
    def list_rows() -> list[dict]:
        return [{**r.model_dump(), "state": sched.status.get(r.id, "idle")} for r in rows.list()]

    @app.post("/rows")
    def save_row(row: Row) -> Row:
        return rows.save(row)

    @app.delete("/rows/{row_id}")
    def delete_row(row_id: int) -> dict:
        rows.delete(row_id)
        return {"ok": True}

    @app.post("/rows/{row_id}/run")
    def run_row(row_id: int, mode: str = "task") -> dict:
        row = rows.get(row_id)
        if not row:
            raise HTTPException(404)
        res = runner.run(row, mode)
        return {"ok": res.ok, "error": res.error}

    @app.post("/rows/{row_id}/pause")
    def pause_row(row_id: int, paused: bool = True) -> dict:
        runner.pause(row_id, paused)
        return {"ok": True}

    @app.get("/games")
    def list_games() -> list[Game]:
        return games.list()

    @app.post("/games")
    def save_game(g: Game) -> Game:
        games.save(g)
        return g

    @app.get("/accounts")
    def list_accounts() -> list[dict]:
        return [asdict(a) for a in accounts.list()]  # never includes passwords

    @app.post("/accounts")
    def add_account(a: AccountIn) -> dict:
        return asdict(accounts.add(a.game_id, a.label, a.username, a.password))

    @app.delete("/accounts/{account_id}")
    def delete_account(account_id: str) -> dict:
        accounts.delete(account_id)
        return {"ok": True}

    # ---- live events -----------------------------------------------------
    @app.get("/events")
    def get_events() -> list[dict]:
        return events

    @app.websocket("/ws")
    async def ws(sock: WebSocket) -> None:
        await sock.accept()
        sent = len(events)
        try:
            while True:
                if len(events) != sent:
                    for e in events[sent if sent <= len(events) else 0 :]:
                        await sock.send_json(e)
                    sent = len(events)
                await asyncio.sleep(0.5)
        except WebSocketDisconnect:
            pass

    # ---- recorder (UI shows the live screen and sends clicks) ---------------
    @app.post("/recorder/start")
    def rec_start(b: RecorderStart) -> dict:
        sid = b.script_id or f"{b.game_id}-{b.mode}"
        rec["cur"] = Recorder(
            make_dev(b.serial), AssetStore(data / "assets", sid), sid, b.game_id, b.mode
        )
        return {"script_id": sid}

    def cur() -> Recorder:
        if "cur" not in rec:
            raise HTTPException(409, "recorder not started")
        return rec["cur"]

    @app.get("/recorder/screen")
    def rec_screen() -> Response:
        return Response(cur().dev.screencap(), media_type="image/png")

    @app.post("/recorder/tap")
    def rec_tap(b: TapIn) -> dict:
        s = cur().record_tap(b.x, b.y, b.from_screen, b.to_screen)
        return s.model_dump()

    @app.post("/recorder/mark")
    def rec_mark(b: MarkIn) -> dict:
        cur().mark_screen(b.name, b.region)
        return {"screens": list(cur().script.screens)}

    @app.post("/recorder/finish")
    def rec_finish() -> dict:
        script = cur().finish()
        ScriptRepo(conn).save(script)
        rec.pop("cur")
        return {"script_id": script.id, "steps": len(script.steps)}

    # ---- sync --------------------------------------------------------------
    @app.post("/sync")
    def do_sync(b: SyncIn) -> dict:
        import httpx

        http = httpx.Client(base_url=b.url, headers={"Authorization": f"Bearer {b.token}"})
        return SyncClient(conn, http, data / "assets", vault, b.passphrase).sync()

    return app


def get_app() -> FastAPI:
    """uvicorn factory: `uvicorn gamebot.main:get_app --factory`."""
    return create_app(run_scheduler=True)

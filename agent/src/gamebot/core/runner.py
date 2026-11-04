from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..device import Device, connect_serial
from ..emulators import Registry
from ..learn import Learner, PopupHandler
from ..play import GameLost, Player, PlayerConfig, ScreenChanged, ScreenFrozen, StepFailed
from ..script import AssetStore
from ..script.repo import ScriptRepo
from ..vision import decode, parse_countdown
from .accounts import AccountRepo
from .games import GameRepo
from .rows import Row


@dataclass
class RunResult:
    ok: bool
    error: str | None = None
    screenshot: bytes | None = None


class RowRunner:
    """Runs one workflow (login -> mode script) for a row on its emulator."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        registry: Registry,
        accounts: AccountRepo,
        assets_root: str | Path,
        device_factory: Callable[[str], Device] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        boot_polls: int = 60,
        ocr=None,
    ):
        self.conn, self.registry, self.accounts = conn, registry, accounts
        self.assets_root, self.sleep, self.boot_polls, self.ocr = (
            assets_root,
            sleep,
            boot_polls,
            ocr,
        )
        self.device_factory = device_factory or (lambda serial: Device(connect_serial(serial)))
        self.scripts, self.games = ScriptRepo(conn), GameRepo(conn)
        self.pause_flags: dict[int, bool] = {}
        self.players: dict[int, Player] = {}

    def ensure_serial(self, row: Row) -> str:
        drv = self.registry.driver(row.emulator_kind)
        for attempt in range(self.boot_polls):
            for inst in drv.scan():
                if inst.ref == row.emulator_ref and inst.running and inst.serial:
                    return inst.serial
            if attempt == 0:
                drv.start(row.emulator_ref)
            self.sleep(2)
        raise TimeoutError("emulator did not come up")

    def _play(self, dev: Device, row: Row, script, game) -> None:
        assets = AssetStore(self.assets_root, script.id)
        popup_assets = AssetStore(self.assets_root, f"game_{game.id}")
        popups = [PopupHandler(**p) for p in game.popups]
        learner = Learner(self.conn, script, assets, popup_assets, popups)
        cfg = PlayerConfig(
            secrets=self.accounts.secrets(row.account_id) if row.account_id else None,
            watch_package=game.package,
            still_s=game.still_s,
        )
        player = Player(dev, script, assets, cfg, learner, self.sleep)
        self.players[row.id] = player
        try:
            player.run()
        finally:
            self.players.pop(row.id, None)

    def pause(self, row_id: int, paused: bool) -> None:
        p = self.players.get(row_id)
        if p:
            p.paused = paused

    def run(self, row: Row, mode: str) -> RunResult:
        game = self.games.get(row.game_id)
        script = self.scripts.for_game(row.game_id, mode)
        if game is None or script is None:
            return RunResult(False, f"missing game/script for mode {mode}")
        dev = None
        try:
            dev = self.device_factory(self.ensure_serial(row))
            dev.start_app(game.package)
            self.sleep(3)
            login = self.scripts.for_game(row.game_id, "login")
            if login and mode != "login" and row.account_id:
                lp = Player(dev, login, AssetStore(self.assets_root, login.id), sleep=self.sleep)
                first = login.steps[0].from_screen if login.steps else None
                if first and lp.identify(lp.grab()) == first:
                    self._play(dev, row, login, game)
            self._play(dev, row, script, game)
            return RunResult(True)
        except StepFailed as e:
            return RunResult(False, str(e), e.screenshot)
        except (GameLost, ScreenFrozen) as e:
            return RunResult(False, f"{type(e).__name__}: {e}", self._screenshot(dev))
        except (ScreenChanged, TimeoutError, KeyError) as e:
            return RunResult(False, f"{type(e).__name__}: {e}")

    def _screenshot(self, dev: Device | None) -> bytes | None:
        try:
            return dev.screencap() if dev else None
        except Exception:
            return None

    def read_event_time(self, row: Row, dev: Device, now_utc) -> str | None:
        """OCR the in-game countdown and return the event start (ISO UTC), or None."""
        game = self.games.get(row.game_id)
        if not (game and game.event_ocr_region and self.ocr):
            return None
        img = decode(dev.screencap())
        H, W = img.shape[:2]
        x0, y0, x1, y1 = game.event_ocr_region
        text = self.ocr.read(img[int(y0 * H) : int(y1 * H), int(x0 * W) : int(x1 * W)])
        secs = parse_countdown(text)
        if secs is None:
            return None
        from datetime import timedelta

        return (now_utc + timedelta(seconds=secs)).isoformat()

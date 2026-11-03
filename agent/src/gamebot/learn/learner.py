from __future__ import annotations

import sqlite3
from dataclasses import dataclass

import numpy as np

from ..play.player import NullHooks
from ..script import AssetStore, Script, Step
from ..script.repo import now
from ..vision import find_template

MAX_VARIANTS = 5


@dataclass
class PopupHandler:
    """Known interruption: if `template` is on screen, run `action` ('tap' on it, or 'key')."""

    name: str
    template: str  # asset name in the game's popup AssetStore
    action: str = "tap"
    value: str | None = None  # keycode for action == 'key'


class Learner(NullHooks):
    """Statistics + template variants + popup handlers. Every change is logged and undoable."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        script: Script,
        assets: AssetStore,
        popup_assets: AssetStore | None = None,
        popups: list[PopupHandler] | None = None,
    ):
        self.conn, self.script, self.assets = conn, script, assets
        self.popup_assets, self.popups = popup_assets, popups or []
        self.player = None

    # ---- stats -----------------------------------------------------------
    def record(self, step: Step, ok: bool, wait_ms: int) -> None:
        r = self.conn.execute(
            "SELECT success, fail, avg_wait_ms FROM step_stats WHERE script_id=? AND step_id=?",
            (self.script.id, step.id),
        ).fetchone()
        s, f, avg = (r["success"], r["fail"], r["avg_wait_ms"]) if r else (0, 0, None)
        if ok:
            avg = wait_ms if avg is None else (avg * s + wait_ms) / (s + 1)
            s += 1
        else:
            f += 1
        self.conn.execute(
            "INSERT OR REPLACE INTO step_stats(script_id, step_id, success, fail, avg_wait_ms)"
            " VALUES (?,?,?,?,?)",
            (self.script.id, step.id, s, f, avg),
        )
        self.conn.commit()

    def stats(self, step_id: str) -> dict | None:
        r = self.conn.execute(
            "SELECT * FROM step_stats WHERE script_id=? AND step_id=?", (self.script.id, step_id)
        ).fetchone()
        return dict(r) if r else None

    # ---- template variants ----------------------------------------------
    def variants(self, step: Step) -> list[str]:
        if not step.template:
            return []
        return [step.template, *self.assets.names(f"{step.template}~v")]

    def _log(self, step_id: str, kind: str, asset: str) -> None:
        self.conn.execute(
            "INSERT INTO learn_log(script_id, step_id, kind, asset, created_at) VALUES (?,?,?,?,?)",
            (self.script.id, step_id, kind, asset, now()),
        )
        self.conn.commit()

    def _add_variant(self, step: Step, crop: np.ndarray) -> str | None:
        existing = self.variants(step)
        if len(existing) > MAX_VARIANTS:
            return None
        for n in existing:
            t = self.assets.load(n)
            if t is not None and t.shape == crop.shape and find_template(crop, t, 0.97):
                return None  # near-duplicate of a known variant
        name = f"{step.template}~v{len(existing)}"
        self.assets.save(name, crop)
        self._log(step.id, "variant", name)
        return name

    def on_match(self, step: Step, img: np.ndarray, x: int, y: int, scale: float) -> None:
        """A non-1.0 scale matched: keep the matched pixels as a new variant."""
        if scale == 1.0 or not step.template:
            return
        base = self.assets.load(step.template)
        if base is None:
            return
        h, w = round(base.shape[0] * scale), round(base.shape[1] * scale)
        x0, y0 = max(0, x - w // 2), max(0, y - h // 2)
        crop = img[y0 : y0 + h, x0 : x0 + w]
        if crop.shape[0] >= 4 and crop.shape[1] >= 4:
            self._add_variant(step, crop)

    def reteach(
        self, step: Step, screen: np.ndarray, x: int, y: int, size: int = 120
    ) -> str | None:
        """User shows the target on a failed screen; store it as a new variant of the step."""
        H, W = screen.shape[:2]
        x0, y0 = max(0, min(x - size // 2, W - size)), max(0, min(y - size // 2, H - size))
        return self._add_variant(step, screen[y0 : y0 + size, x0 : x0 + size])

    # ---- popups ----------------------------------------------------------
    def teach_popup(self, handler: PopupHandler, crop: np.ndarray) -> None:
        assert self.popup_assets is not None
        self.popup_assets.save(handler.template, crop)
        self.popups.append(handler)
        self._log("-", "popup", handler.template)

    def recover(self, player, step: Step, screen: np.ndarray) -> bool:
        """Dismiss a known popup; True means 'state changed, retry the step'."""
        if self.popup_assets is None:
            return False
        for h in self.popups:
            t = self.popup_assets.load(h.template)
            if t is None:
                continue
            m = find_template(screen, t, 0.85, player.cfg.scales)
            if not m:
                continue
            if h.action == "key":
                player.dev.key(h.value)
            else:
                player.dev.tap(*player._real(m.x, m.y))
            player.sleep(0.8)
            return True
        return False

    # ---- undo ------------------------------------------------------------
    def changes(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM learn_log WHERE script_id=? ORDER BY id", (self.script.id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def undo(self, log_id: int) -> bool:
        r = self.conn.execute("SELECT * FROM learn_log WHERE id=?", (log_id,)).fetchone()
        if not r:
            return False
        store = self.popup_assets if r["kind"] == "popup" else self.assets
        if store is not None:
            store.delete(r["asset"])
        if r["kind"] == "popup":
            self.popups[:] = [p for p in self.popups if p.template != r["asset"]]
        self.conn.execute("DELETE FROM learn_log WHERE id=?", (log_id,))
        self.conn.commit()
        return True

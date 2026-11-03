from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from ..core.accounts import Vault
from ..script.repo import now
from . import crypto


class SyncClient:
    """Pushes local changes and pulls remote ones (last-write-wins per record).

    `http` only needs post/get/put returning httpx-like responses with the auth header preset.
    Passwords are synced only when a passphrase is given, always encrypted client-side.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        http,
        assets_root: str | Path,
        vault: Vault | None = None,
        passphrase: str | None = None,
        kdf_iterations: int = crypto.ITERATIONS,
    ):
        self.conn, self.http, self.assets_root = conn, http, Path(assets_root)
        self.vault, self.passphrase, self.iters = vault, passphrase, kdf_iterations

    # ---- local state -----------------------------------------------------
    def _state(self, key: str, default: str = "0") -> str:
        r = self.conn.execute("SELECT value FROM sync_state WHERE key=?", (key,)).fetchone()
        return r["value"] if r else default

    def _set_state(self, key: str, value: str) -> None:
        self.conn.execute("INSERT OR REPLACE INTO sync_state VALUES (?,?)", (key, value))

    def _seen(self) -> set[tuple[str, str, int]]:
        return {
            (r[0], r[1], r[2]) for r in self.conn.execute("SELECT kind,id,version FROM sync_seen")
        }

    def _mark(self, kind: str, id_: str, version: int) -> None:
        self.conn.execute("INSERT OR REPLACE INTO sync_seen VALUES (?,?,?)", (kind, id_, version))

    # ---- collect ---------------------------------------------------------
    def _collect(self) -> list[dict]:
        c, out = self.conn, []
        for r in c.execute("SELECT * FROM games"):
            out.append(
                dict(
                    kind="game",
                    id=r["id"],
                    version=r["version"],
                    updated_at=r["updated_at"],
                    data=json.loads(r["profile"]),
                )
            )
        for r in c.execute("SELECT * FROM scripts"):
            out.append(
                dict(
                    kind="script",
                    id=r["id"],
                    version=r["version"],
                    updated_at=r["updated_at"],
                    data=json.loads(r["graph"]),
                )
            )
        for r in c.execute("SELECT * FROM accounts"):
            data = {k: r[k] for k in ("game_id", "label", "username")}
            out.append(
                dict(
                    kind="account",
                    id=r["id"],
                    version=r["version"],
                    updated_at=r["updated_at"],
                    data=data,
                )
            )
            if self.passphrase and self.vault:
                pw = self.vault.get(r["id"])
                if pw is not None:
                    out.append(
                        dict(
                            kind="secret",
                            id=r["id"],
                            version=r["version"],
                            updated_at=r["updated_at"],
                            data=crypto.encrypt(self.passphrase, pw, self.iters),
                        )
                    )
        for r in c.execute("SELECT * FROM rows"):
            data = {
                "name": r["name"],
                "game_id": r["game_id"],
                "account_id": r["account_id"],
                "mode_priority": r["mode_priority"],
                "schedule": r["schedule"],
            }
            out.append(
                dict(
                    kind="row",
                    id=r["name"],
                    version=r["version"],
                    updated_at=r["updated_at"],
                    data=data,
                )
            )
        for r in c.execute("SELECT * FROM step_stats"):
            out.append(
                dict(
                    kind="stats",
                    id=f"{r['script_id']}/{r['step_id']}",
                    version=r["success"] + r["fail"],
                    updated_at=now(),
                    data={
                        k: r[k] for k in ("script_id", "step_id", "success", "fail", "avg_wait_ms")
                    },
                )
            )
        return out

    # ---- apply -----------------------------------------------------------
    def _apply(self, ch: dict) -> None:
        c, k, d = self.conn, ch["kind"], ch["data"]
        v, ts = ch["version"], ch["updated_at"]
        if ch["deleted"]:
            table = {"game": "games", "script": "scripts", "account": "accounts"}.get(k)
            if table:
                c.execute(f"DELETE FROM {table} WHERE id=?", (ch["id"],))  # noqa: S608
            elif k == "row":
                c.execute("DELETE FROM rows WHERE name=?", (ch["id"],))
            return
        if k == "game":
            c.execute(
                "INSERT OR REPLACE INTO games VALUES (?,?,?,?,?)",
                (d["id"], d["package"], json.dumps(d), ts, v),
            )
        elif k == "script":
            c.execute(
                "INSERT OR REPLACE INTO scripts VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    d["id"],
                    d["game_id"],
                    d["mode"],
                    json.dumps(d),
                    d["ref_width"],
                    d["ref_height"],
                    d["ref_dpi"],
                    ts,
                    v,
                ),
            )
        elif k == "account":
            c.execute(
                "INSERT OR REPLACE INTO accounts VALUES (?,?,?,?,?,?)",
                (ch["id"], d["game_id"], d["label"], d["username"], ts, v),
            )
        elif k == "secret":
            if self.passphrase and self.vault:
                self.vault.set(ch["id"], crypto.decrypt(self.passphrase, d))
        elif k == "row":
            # emulator binding is machine-specific and stays local
            cur = c.execute("SELECT id FROM rows WHERE name=?", (d["name"],)).fetchone()
            vals = (d["game_id"], d["account_id"], d["mode_priority"], d["schedule"], ts, v)
            if cur:
                c.execute(
                    "UPDATE rows SET game_id=?, account_id=?, mode_priority=?, schedule=?,"
                    " updated_at=?, version=? WHERE id=?",
                    (*vals, cur["id"]),
                )
            else:
                c.execute(
                    "INSERT INTO rows(game_id, account_id, mode_priority, schedule,"
                    " updated_at, version, name, emulator_kind, emulator_ref)"
                    " VALUES (?,?,?,?,?,?,?,'','')",
                    (*vals, d["name"]),
                )
        elif k == "stats":
            c.execute(
                "INSERT OR REPLACE INTO step_stats VALUES (?,?,?,?,?)",
                (d["script_id"], d["step_id"], d["success"], d["fail"], d["avg_wait_ms"]),
            )

    # ---- sync ------------------------------------------------------------
    def sync(self) -> dict:
        seen = self._seen()
        local = self._collect()
        push = [ch for ch in local if (ch["kind"], ch["id"], ch["version"]) not in seen]
        r = self.http.post("/sync", json={"since": int(self._state("seq")), "changes": push})
        r.raise_for_status()
        body = r.json()
        for ch in push:
            self._mark(ch["kind"], ch["id"], ch["version"])
        by_key = {(c["kind"], c["id"]): c for c in local}
        applied = 0
        for ch in body["changes"]:
            mine = by_key.get((ch["kind"], ch["id"]))
            if mine and (mine["version"], mine["updated_at"]) == (ch["version"], ch["updated_at"]):
                self._mark(ch["kind"], ch["id"], ch["version"])
                continue
            self._apply(ch)
            self._mark(ch["kind"], ch["id"], ch["version"])
            applied += 1
        self._set_state("seq", str(body["seq"]))
        self.conn.commit()
        pulled_blobs = self._sync_blobs()
        return {
            "pushed": len(push),
            "applied": applied,
            "conflicts": body["conflicts"],
            "assets": pulled_blobs,
        }

    def _sync_blobs(self) -> int:
        remote = {b["key"] for b in self.http.get("/blobs").json()}
        local = {
            p.relative_to(self.assets_root).as_posix() for p in self.assets_root.glob("*/*.png")
        }
        for key in local - remote:
            self.http.put(f"/blobs/{key}", content=(self.assets_root / key).read_bytes())
        for key in remote - local:
            dest = self.assets_root / key
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(self.http.get(f"/blobs/{key}").content)
        return len(remote - local)

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from urllib.parse import urlsplit

from ..core.accounts import Vault
from .base import Channel
from .facebook import FacebookChannel
from .teams import TeamsChannel
from .telegram import TelegramChannel
from .zalo import ZaloChannel

FACTORIES = {
    "telegram": lambda cfg, secret: TelegramChannel(
        secret, cfg["chat_id"], send_image=cfg.get("send_image", False)
    ),
    "teams": lambda cfg, secret: TeamsChannel(secret),
    "zalo": lambda cfg, secret: ZaloChannel(secret, cfg["chat_id"]),
    "facebook": lambda cfg, secret: FacebookChannel(secret, cfg["page_id"], cfg["recipient_id"]),
}
LEVELS = ("error", "all")
CONFIG_KEYS = {
    "telegram": ("chat_id", "send_image"),
    "teams": (),
    "zalo": ("chat_id",),
    "facebook": ("page_id", "recipient_id"),
}  # non-secret fields kept per kind


# Teams webhook host suffixes. Source: Microsoft Learn, "Create an Incoming Webhook - Teams"
# https://learn.microsoft.com/en-us/microsoftteams/platform/webhooks-and-connectors/how-to/add-incoming-webhook
# (checked 2026-11-04). That page no longer lists concrete hosts (connectors retired May 2026;
# Workflows URLs are generated per workflow): logic.azure.com appears in Microsoft connector docs,
# powerplatform.com (environment.api.powerplatform.com) only in third-party docs, and
# webhook.office.com is the legacy connector host. outlook.office*.com not confirmed: excluded.
TEAMS_HOST_SUFFIXES = (".webhook.office.com", ".logic.azure.com", ".powerplatform.com")
TG_TOKEN = re.compile(r"[0-9]+:[A-Za-z0-9_-]+")
TG_CHAT = re.compile(r"-?[0-9]+|@[A-Za-z0-9_]+")
ZALO_TOKEN = re.compile(r"[A-Za-z0-9_:.-]+")
ZALO_CHAT = re.compile(r"[A-Za-z0-9_-]+")


def _valid_teams_url(url: str) -> bool:
    try:
        u = urlsplit(url)
        host = u.hostname
        u.port  # noqa: B018 - raises ValueError on a malformed port
    except ValueError:
        return False
    if u.scheme != "https" or not host or u.username is not None or u.password is not None:
        return False
    return host.endswith(TEAMS_HOST_SUFFIXES)


class ChannelRepo:
    def __init__(self, conn: sqlite3.Connection, vault: Vault):
        self.conn, self.vault = conn, vault

    def list(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, kind, name, level, enabled, config FROM notify_channels"
        ).fetchall()
        return [
            {
                "id": r["id"],
                "kind": r["kind"],
                "name": r["name"],
                "level": r["level"],
                "enabled": bool(r["enabled"]),
                "config": json.loads(r["config"]),
            }
            for r in rows
        ]

    def add(self, kind: str, name: str, config: dict, secret: str, level: str = "error") -> dict:
        if kind not in FACTORIES:
            raise ValueError("unknown kind")
        if level not in LEVELS:
            raise ValueError("invalid level")
        if not 1 <= len(name) <= 60:
            raise ValueError("invalid name")
        if not secret:
            raise ValueError("secret required")
        if kind in ("telegram", "zalo"):
            chat_id = config.get("chat_id")
            if not chat_id:
                raise ValueError("chat_id required")
            chat_re, token_re = (
                (TG_CHAT, TG_TOKEN) if kind == "telegram" else (ZALO_CHAT, ZALO_TOKEN)
            )
            if not isinstance(chat_id, str) or not chat_re.fullmatch(chat_id):
                raise ValueError("invalid chat_id")
            if not token_re.fullmatch(secret):
                raise ValueError("invalid token format")
        if kind == "facebook":
            for key in ("page_id", "recipient_id"):
                if not config.get(key):
                    raise ValueError(f"{key} required")
                if not re.fullmatch(r"[0-9]+", str(config[key])):
                    raise ValueError(f"{key} must be digits")
        if kind == "teams" and not _valid_teams_url(secret):
            raise ValueError("webhook url must be an https Microsoft Teams webhook")
        config = {k: config[k] for k in CONFIG_KEYS[kind] if k in config}
        if "send_image" in config and not isinstance(config["send_image"], bool):
            del config["send_image"]  # only bool values are kept
        channel_id = uuid.uuid4().hex
        self.vault.set(f"notify:{channel_id}", secret)  # first: a vault failure leaves no row
        self.conn.execute(
            "INSERT INTO notify_channels(id, kind, name, config, level, enabled)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (channel_id, kind, name, json.dumps(config), level, 1),
        )
        self.conn.commit()
        return {
            "id": channel_id,
            "kind": kind,
            "name": name,
            "level": level,
            "enabled": True,
            "config": config,
        }

    def delete(self, channel_id: str) -> None:
        self.conn.execute("DELETE FROM notify_channels WHERE id=?", (channel_id,))
        self.conn.commit()
        self.vault.delete(f"notify:{channel_id}")

    def build(self) -> list[tuple[Channel, str]]:
        rows = self.conn.execute(
            "SELECT id, kind, config, level FROM notify_channels WHERE enabled=1"
        ).fetchall()
        result: list[tuple[Channel, str]] = []
        for r in rows:
            channel = self._make(r["id"], r["kind"], json.loads(r["config"]))
            if channel is not None:
                result.append((channel, r["level"]))
        return result

    def get_channel(self, channel_id: str) -> Channel | None:
        row = self.conn.execute(
            "SELECT kind, config FROM notify_channels WHERE id=?", (channel_id,)
        ).fetchone()
        if row is None:
            return None
        return self._make(channel_id, row["kind"], json.loads(row["config"]))

    def _make(self, channel_id: str, kind: str, config: dict) -> Channel | None:
        secret = self.vault.get(f"notify:{channel_id}")
        if not secret:
            return None
        return FACTORIES[kind](config, secret)

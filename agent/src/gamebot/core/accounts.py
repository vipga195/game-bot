from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from typing import Protocol

from ..script.repo import now

SERVICE = "gamebot"


class Vault(Protocol):
    def set(self, account_id: str, password: str) -> None: ...
    def get(self, account_id: str) -> str | None: ...
    def delete(self, account_id: str) -> None: ...


class KeyringVault:
    """Passwords live only in the OS credential store (Windows Credential Manager, Keychain)."""

    def set(self, account_id: str, password: str) -> None:
        import keyring

        keyring.set_password(SERVICE, account_id, password)

    def get(self, account_id: str) -> str | None:
        import keyring

        return keyring.get_password(SERVICE, account_id)

    def delete(self, account_id: str) -> None:
        import keyring

        try:
            keyring.delete_password(SERVICE, account_id)
        except keyring.errors.PasswordDeleteError:
            pass


class MemoryVault:
    def __init__(self) -> None:
        self._d: dict[str, str] = {}

    def set(self, account_id, password):
        self._d[account_id] = password

    def get(self, account_id):
        return self._d.get(account_id)

    def delete(self, account_id):
        self._d.pop(account_id, None)


@dataclass
class Account:
    id: str
    game_id: str
    label: str
    username: str


class AccountRepo:
    """Username/label go to SQLite (and may sync); the password goes to the vault only."""

    def __init__(self, conn: sqlite3.Connection, vault: Vault):
        self.conn, self.vault = conn, vault

    def add(self, game_id: str, label: str, username: str, password: str) -> Account:
        acc = Account(uuid.uuid4().hex, game_id, label, username)
        self.conn.execute(
            "INSERT INTO accounts(id, game_id, label, username, updated_at, version)"
            " VALUES (?,?,?,?,?,1)",
            (acc.id, game_id, label, username, now()),
        )
        self.conn.commit()
        self.vault.set(acc.id, password)
        return acc

    def get(self, account_id: str) -> Account | None:
        r = self.conn.execute(
            "SELECT id, game_id, label, username FROM accounts WHERE id=?", (account_id,)
        ).fetchone()
        return Account(**dict(r)) if r else None

    def list(self) -> list[Account]:
        rows = self.conn.execute("SELECT id, game_id, label, username FROM accounts").fetchall()
        return [Account(**dict(r)) for r in rows]

    def delete(self, account_id: str) -> None:
        self.conn.execute("DELETE FROM accounts WHERE id=?", (account_id,))
        self.conn.commit()
        self.vault.delete(account_id)

    def secrets(self, account_id: str):
        """Resolver for script placeholders {username}/{password}; never logs values."""

        def resolve(field: str) -> str:
            acc = self.get(account_id)
            if acc is None:
                raise KeyError("unknown account")
            if field == "username":
                return acc.username
            if field == "password":
                pw = self.vault.get(account_id)
                if pw is None:
                    raise KeyError("password not in vault")
                return pw
            raise KeyError(f"unknown field {field}")

        return resolve

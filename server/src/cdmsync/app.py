from __future__ import annotations

import hashlib
import json
import os
import secrets
from datetime import UTC, datetime

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import (
    Boolean,
    Column,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    select,
)
from sqlalchemy.engine import Engine

meta = MetaData()
users = Table(
    "users",
    meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(100), unique=True),
    Column("token_hash", String(64), unique=True),
)
records = Table(
    "records",
    meta,
    Column("user_id", Integer, primary_key=True),
    Column("kind", String(30), primary_key=True),
    Column("id", String(200), primary_key=True),
    Column("seq", Integer, index=True),
    Column("version", Integer),
    Column("updated_at", String(40)),
    Column("deleted", Boolean, default=False),
    Column("data", Text),
)
history = Table(  # versions that lost a last-write-wins conflict
    "record_history",
    meta,
    Column("n", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer),
    Column("kind", String(30)),
    Column("id", String(200)),
    Column("version", Integer),
    Column("updated_at", String(40)),
    Column("data", Text),
    Column("archived_at", String(40)),
)
blobs = Table(
    "blobs",
    meta,
    Column("user_id", Integer, primary_key=True),
    Column("key", String(300), primary_key=True),
    Column("updated_at", String(40)),
    Column("data", LargeBinary),
)
counters = Table(
    "counters",
    meta,
    Column("user_id", Integer, primary_key=True),
    Column("seq", Integer, default=0),
)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_user(engine: Engine, name: str) -> str:
    """Returns the plaintext token once; only its hash is stored."""
    token = secrets.token_urlsafe(32)
    with engine.begin() as c:
        c.execute(users.insert().values(name=name, token_hash=hash_token(token)))
    return token


class Change(BaseModel):
    kind: str
    id: str
    version: int
    updated_at: str
    deleted: bool = False
    data: dict | None = None


class SyncRequest(BaseModel):
    since: int = 0
    changes: list[Change] = []


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _wins(inc: Change, cur) -> bool:
    """Last-write-wins: later updated_at, then higher version; exact ties keep the stored one."""
    return (inc.updated_at, inc.version) > (cur.updated_at, cur.version)


def create_app(db_url: str | None = None) -> FastAPI:
    url = db_url or os.environ.get("CDM_DATABASE_URL", "sqlite:///cdm.sqlite3")
    kw = {"poolclass": __import__("sqlalchemy").pool.StaticPool} if url == "sqlite://" else {}
    if url.startswith("sqlite"):
        kw["connect_args"] = {"check_same_thread": False}
    engine = create_engine(url, **kw)
    meta.create_all(engine)
    app = FastAPI(title="cdm-sync")
    app.state.engine = engine

    def auth(request: Request, authorization: str = Header(default="")) -> int:
        token = authorization.removeprefix("Bearer ").strip()
        with request.app.state.engine.begin() as c:
            row = c.execute(
                select(users.c.id).where(users.c.token_hash == hash_token(token))
            ).first()
        if not token or row is None:
            raise HTTPException(401, "invalid token")
        return row[0]

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.post("/sync")
    def sync(req: SyncRequest, uid: int = Depends(auth)) -> dict:
        conflicts = []
        with engine.begin() as c:
            ctr = c.execute(select(counters.c.seq).where(counters.c.user_id == uid)).first()
            seq = ctr[0] if ctr else 0
            if not ctr:
                c.execute(counters.insert().values(user_id=uid, seq=0))
            for ch in req.changes:
                key = (
                    (records.c.user_id == uid)
                    & (records.c.kind == ch.kind)
                    & (records.c.id == ch.id)
                )
                cur = c.execute(select(records).where(key)).first()
                payload = json.dumps(ch.data) if ch.data is not None else None
                if cur is not None and not _wins(ch, cur):
                    if (ch.updated_at, ch.version) != (cur.updated_at, cur.version):
                        c.execute(
                            history.insert().values(
                                user_id=uid,
                                kind=ch.kind,
                                id=ch.id,
                                version=ch.version,
                                updated_at=ch.updated_at,
                                data=payload,
                                archived_at=_now(),
                            )
                        )
                        conflicts.append({"kind": ch.kind, "id": ch.id, "kept": "server"})
                    continue
                if cur is not None:
                    c.execute(
                        history.insert().values(
                            user_id=uid,
                            kind=ch.kind,
                            id=ch.id,
                            version=cur.version,
                            updated_at=cur.updated_at,
                            data=cur.data,
                            archived_at=_now(),
                        )
                    )
                    if cur.version != ch.version - 1 and not cur.deleted:
                        conflicts.append({"kind": ch.kind, "id": ch.id, "kept": "client"})
                seq += 1
                vals = dict(
                    seq=seq,
                    version=ch.version,
                    updated_at=ch.updated_at,
                    deleted=ch.deleted,
                    data=payload,
                )
                if cur is None:
                    c.execute(records.insert().values(user_id=uid, kind=ch.kind, id=ch.id, **vals))
                else:
                    c.execute(records.update().where(key).values(**vals))
            c.execute(counters.update().where(counters.c.user_id == uid).values(seq=seq))
            rows = c.execute(
                select(records)
                .where((records.c.user_id == uid) & (records.c.seq > req.since))
                .order_by(records.c.seq)
            ).fetchall()
        return {
            "seq": seq,
            "conflicts": conflicts,
            "changes": [
                {
                    "kind": r.kind,
                    "id": r.id,
                    "version": r.version,
                    "updated_at": r.updated_at,
                    "deleted": bool(r.deleted),
                    "data": json.loads(r.data) if r.data else None,
                }
                for r in rows
            ],
        }

    @app.get("/blobs")
    def list_blobs(uid: int = Depends(auth)) -> list[dict]:
        with engine.begin() as c:
            rows = c.execute(
                select(blobs.c.key, blobs.c.updated_at).where(blobs.c.user_id == uid)
            ).fetchall()
        return [{"key": r.key, "updated_at": r.updated_at} for r in rows]

    @app.put("/blobs/{key:path}")
    async def put_blob(key: str, request: Request, uid: int = Depends(auth)) -> dict:
        data = await request.body()
        with engine.begin() as c:
            k = (blobs.c.user_id == uid) & (blobs.c.key == key)
            if c.execute(select(blobs.c.key).where(k)).first():
                c.execute(blobs.update().where(k).values(data=data, updated_at=_now()))
            else:
                c.execute(blobs.insert().values(user_id=uid, key=key, data=data, updated_at=_now()))
        return {"ok": True}

    @app.get("/blobs/{key:path}")
    def get_blob(key: str, uid: int = Depends(auth)) -> Response:
        with engine.begin() as c:
            r = c.execute(
                select(blobs.c.data).where((blobs.c.user_id == uid) & (blobs.c.key == key))
            ).first()
        if r is None:
            raise HTTPException(404)
        return Response(r[0], media_type="application/octet-stream")

    return app

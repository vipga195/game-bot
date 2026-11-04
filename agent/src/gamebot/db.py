import sqlite3

SQL_TABLES: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS rows (
        id INTEGER PRIMARY KEY,
        name TEXT,
        emulator_kind TEXT,
        emulator_ref TEXT,
        game_id TEXT,
        account_id TEXT,
        mode_priority TEXT,
        schedule TEXT,
        updated_at TEXT,
        version INTEGER DEFAULT 1,
        deleted INTEGER DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS games (
        id TEXT PRIMARY KEY,
        package TEXT,
        profile TEXT,
        updated_at TEXT,
        version INTEGER DEFAULT 1,
        deleted INTEGER DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS scripts (
        id TEXT PRIMARY KEY,
        game_id TEXT,
        mode TEXT,
        graph TEXT,
        ref_width INTEGER,
        ref_height INTEGER,
        ref_dpi INTEGER,
        updated_at TEXT,
        version INTEGER DEFAULT 1,
        deleted INTEGER DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS step_stats (
        script_id TEXT,
        step_id TEXT,
        success INTEGER DEFAULT 0,
        fail INTEGER DEFAULT 0,
        avg_wait_ms REAL,
        PRIMARY KEY(script_id, step_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS accounts (
        id TEXT PRIMARY KEY,
        game_id TEXT,
        label TEXT,
        username TEXT,
        updated_at TEXT,
        version INTEGER DEFAULT 1,
        deleted INTEGER DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sync_state (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sync_seen (
        kind TEXT,
        id TEXT,
        version INTEGER,
        PRIMARY KEY(kind, id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS learn_log (
        id INTEGER PRIMARY KEY,
        script_id TEXT,
        step_id TEXT,
        kind TEXT,
        asset TEXT,
        created_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS notify_channels (
        id TEXT PRIMARY KEY,
        kind TEXT,
        name TEXT,
        config TEXT,
        level TEXT,
        enabled INTEGER DEFAULT 1
    )
    """,
)


def connect(path: str, check_same_thread: bool = True) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=check_same_thread)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


SYNCED_TABLES = ("rows", "games", "scripts", "accounts")


def init_db(conn: sqlite3.Connection) -> None:
    for sql in SQL_TABLES:
        conn.execute(sql)
    for t in SYNCED_TABLES:  # tombstone flag for databases created before it existed
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({t})")}
        if "deleted" not in cols:
            conn.execute(f"ALTER TABLE {t} ADD COLUMN deleted INTEGER DEFAULT 0")  # noqa: S608
    conn.commit()

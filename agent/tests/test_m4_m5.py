from concurrent.futures import Executor, Future
from datetime import UTC, datetime, timedelta

import numpy as np

from gamebot.core.accounts import AccountRepo, MemoryVault
from gamebot.core.games import Game, GameRepo
from gamebot.core.rows import Row, RowRepo, Schedule, due_modes
from gamebot.core.runner import RowRunner
from gamebot.core.scheduler import Scheduler
from gamebot.db import connect, init_db
from gamebot.device import Device
from gamebot.emulators import EmulatorDriver, Instance, Registry
from gamebot.play import Recorder
from gamebot.script import AssetStore
from gamebot.script.repo import ScriptRepo

from .fakes import FakeDevice, make_screen

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def db():
    c = connect(":memory:")
    init_db(c)
    return c


class Inline(Executor):
    def submit(self, fn, *a, **k):
        f = Future()
        f.set_result(fn(*a, **k))
        return f


class Deferred(Executor):
    def __init__(self):
        self.jobs = []

    def submit(self, fn, *a, **k):
        self.jobs.append((fn, a, k))
        return Future()

    def run_all(self):
        jobs, self.jobs = self.jobs, []
        for fn, a, k in jobs:
            fn(*a, **k)


# ---- accounts -----------------------------------------------------------
def test_password_only_in_vault():
    conn, vault = db(), MemoryVault()
    repo = AccountRepo(conn, vault)
    acc = repo.add("g", "main", "bob", "s3cret-pw")
    dump = " ".join(str(tuple(r)) for r in conn.execute("SELECT * FROM accounts"))
    assert "s3cret-pw" not in dump and vault.get(acc.id) == "s3cret-pw"
    res = repo.secrets(acc.id)
    assert res("username") == "bob" and res("password") == "s3cret-pw"
    repo.delete(acc.id)
    assert vault.get(acc.id) is None


# ---- due_modes ----------------------------------------------------------
def test_due_interval_priority_and_hours():
    r = Row(id=1, mode_priority=["task", "train"])
    assert due_modes(r, T0) == ["task", "train"]
    r.schedule.last_run["task"] = (T0 - timedelta(minutes=30)).isoformat()
    assert due_modes(r, T0) == ["train"]
    r.schedule.active_from, r.schedule.active_to = "20:00", "23:00"
    assert due_modes(r, T0) == []
    r.schedule.active_from, r.schedule.active_to = "22:00", "06:00"  # wraps midnight
    r.schedule.utc_offset_min = 600  # 12:00 UTC = 22:00 local
    assert due_modes(r, T0) == ["train"]


def test_event_window():
    r = Row(id=1, mode_priority=["event", "task"])
    r.schedule.event_at["event"] = (T0 + timedelta(minutes=1)).isoformat()
    assert due_modes(r, T0)[0] == "event"
    r.schedule.last_run["event"] = T0.isoformat()
    assert "event" not in due_modes(r, T0)
    r.schedule.last_run.clear()
    assert "event" not in due_modes(r, T0 + timedelta(hours=2))


# ---- scheduler ----------------------------------------------------------
def make_rows(conn, n, mode_priority=("task",)):
    repo = RowRepo(conn)
    for i in range(n):
        repo.save(Row(name=f"r{i}", mode_priority=list(mode_priority)))
    return repo


def test_row_repo_roundtrip():
    repo = make_rows(db(), 1)
    row = repo.get(1)
    row.schedule.interval_min["task"] = 5
    repo.save(row)
    assert repo.get(1).schedule.interval_min["task"] == 5 and len(repo.list()) == 1


def test_concurrency_cap_and_queue():
    rows = make_rows(db(), 3)
    ex, ran = Deferred(), []
    s = Scheduler(rows, lambda r, m: ran.append(r.id), lambda: T0, max_concurrent=2, executor=ex)
    s.tick()
    assert len(s.running) == 2 and len(s.queue) == 1
    ex.run_all()  # finishing a job frees a slot -> third row starts
    assert len(ran) == 2 and s.running == {3}
    ex.run_all()
    assert sorted(ran) == [1, 2, 3] and not s.running
    s.tick()  # last_run recorded, nothing due right away
    assert not s.running and not s.queue


def test_failed_job_reports_error_and_frees_slot():
    rows = make_rows(db(), 1)
    events = []

    def boom(r, m):
        raise RuntimeError("x")

    s = Scheduler(rows, boom, lambda: T0, executor=Inline(), on_event=events.append)
    s.tick()
    assert not s.running and events[-1]["state"] == "error"


def test_priority_order():
    repo = RowRepo(db())
    repo.save(Row(name="a", mode_priority=["train"]))
    repo.save(
        Row(
            name="b",
            mode_priority=["event", "train"],
            schedule=Schedule(event_at={"event": T0.isoformat()}),
        )
    )
    order = []
    s = Scheduler(
        repo,
        lambda r, m: order.append((r.name, m)),
        lambda: T0,
        max_concurrent=1,
        executor=Deferred(),
    )
    s.tick()
    s.executor.run_all()
    s.executor.run_all()
    assert order == [("b", "event"), ("a", "train")]


def test_drift_reschedules_and_warns():
    repo = RowRepo(db())
    repo.save(
        Row(
            mode_priority=["event"],
            schedule=Schedule(event_at={"event": (T0 - timedelta(hours=2)).isoformat()}),
        )
    )
    events = []
    Scheduler(repo, lambda r, m: None, lambda: T0, executor=Inline(), on_event=events.append).tick()
    assert events[0]["state"] == "warning"
    assert datetime.fromisoformat(repo.get(1).schedule.event_at["event"]) > T0


# ---- runner / workflow --------------------------------------------------
class FakeDriver(EmulatorDriver):
    kind = "fake"

    def __init__(self):
        self.started = []

    def scan(self):
        return [Instance("fake", "e", "0", "emu-1", bool(self.started))]

    def start(self, ref):
        self.started.append(ref)

    def stop(self, ref):
        pass


class FakeOcr:
    def read(self, img: np.ndarray) -> str:
        return "Event in 02:15:00"


class Shell:
    """Adapts FakeDevice to the adb shell interface used by Device."""

    def __init__(self, fake):
        self.fake = fake

    def shell(self, cmd, encoding="utf-8"):
        f = self.fake
        if cmd == "screencap -p":
            return f.screencap()
        if cmd.startswith("input tap"):
            _, _, x, y = cmd.split()
            f.tap(int(x), int(y))
        elif cmd.startswith("input text"):
            f.text(cmd.split(" ", 2)[2])
        elif cmd == "wm size":
            return "Physical size: 360x640"
        elif cmd == "wm density":
            return "Physical density: 160"
        return ""


REGION = (100 / 360, 20 / 640, 260 / 360, 80 / 640)


def build_workflow(tmp_path):
    conn = db()
    login = make_screen(1, 11, (120, 300, 120, 50, 21))
    main = make_screen(2, 12)
    fake = FakeDevice(
        {"login": login, "main": main}, {"login": (120, 300, 120, 50, 21, "main")}, "login"
    )
    scripts = ScriptRepo(conn)

    r = Recorder(fake, AssetStore(tmp_path, "login1"), "login1", "g1", "login", lambda s: None)
    r.mark_screen("login", REGION)
    r.record_tap(180, 325, from_screen="login")
    r.mark_screen("main", REGION)
    r.script.steps[0].to_screen = "main"
    scripts.save(r.finish())

    r = Recorder(fake, AssetStore(tmp_path, "task1"), "task1", "g1", "task", lambda s: None)
    r.mark_screen("main", REGION)
    r.record_text("{username}", from_screen="main")
    scripts.save(r.finish())

    fake.cur = "login"
    GameRepo(conn).save(Game(id="g1", package="com.g", event_ocr_region=(0, 0, 1, 0.2)))
    accounts = AccountRepo(conn, MemoryVault())
    acc = accounts.add("g1", "m", "bob", "pw")
    drv = FakeDriver()
    runner = RowRunner(
        conn,
        Registry([drv]),
        accounts,
        tmp_path,
        lambda serial: Device(Shell(fake)),
        sleep=lambda s: None,
        ocr=FakeOcr(),
    )
    row = Row(id=1, emulator_kind="fake", emulator_ref="0", game_id="g1", account_id=acc.id)
    return runner, row, fake, drv


def test_workflow_starts_emulator_logs_in_then_runs_mode(tmp_path):
    runner, row, fake, drv = build_workflow(tmp_path)
    res = runner.run(row, "task")
    assert res.ok, res.error
    assert drv.started == ["0"] and fake.cur == "main" and fake.texts == ["bob"]


def test_workflow_missing_script(tmp_path):
    runner, row, *_ = build_workflow(tmp_path)
    assert not runner.run(row, "train").ok


def test_ocr_updates_event_time(tmp_path):
    runner, row, fake, _ = build_workflow(tmp_path)
    iso = runner.read_event_time(row, Device(Shell(fake)), T0)
    assert datetime.fromisoformat(iso) == T0 + timedelta(hours=2, minutes=15)

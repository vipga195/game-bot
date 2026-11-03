from __future__ import annotations

import heapq
import threading
from collections.abc import Callable
from concurrent.futures import Executor, ThreadPoolExecutor
from datetime import datetime, timedelta

from .rows import MODES, Row, RowRepo, due_modes

MODE_RANK = {m: i for i, m in enumerate(MODES)}


class Scheduler:
    """Queue of (priority, row, mode) jobs with a cap on concurrently running emulators."""

    def __init__(
        self,
        rows: RowRepo,
        run: Callable[[Row, str], object],
        clock: Callable[[], datetime],
        max_concurrent: int = 2,
        executor: Executor | None = None,
        on_event: Callable[[dict], None] | None = None,
        drift_grace_min: int = 10,
    ):
        self.rows, self.run, self.clock = rows, run, clock
        self.max_concurrent = max_concurrent
        self.executor = executor or ThreadPoolExecutor(max_workers=max_concurrent)
        self.on_event = on_event or (lambda e: None)
        self.drift_grace = timedelta(minutes=drift_grace_min)
        self.queue: list[tuple[int, int, int, str]] = []
        self.queued: set[int] = set()
        self.running: set[int] = set()
        self.status: dict[int, str] = {}
        self.lock = threading.RLock()
        self._seq = 0

    def _emit(self, row_id: int, state: str, **kw) -> None:
        self.status[row_id] = state
        self.on_event({"row": row_id, "state": state, **kw})

    def tick(self) -> None:
        now = self.clock()
        with self.lock:
            for row in self.rows.list():
                if row.id in self.running or row.id in self.queued:
                    continue
                self._check_drift(row, now)
                modes = due_modes(row, now)
                if modes:
                    prio = MODE_RANK.get(
                        modes[0], len(MODE_RANK)
                    )  # events first, then tasks, then train
                    self._seq += 1
                    heapq.heappush(self.queue, (prio, self._seq, row.id, modes[0]))
                    self.queued.add(row.id)
                    self._emit(row.id, "queued", mode=modes[0])
            self._dispatch()

    def _check_drift(self, row: Row, now: datetime) -> None:
        """Event start passed with no run: push it by one day and warn (schedule drift)."""
        ev = row.schedule.event_at.get("event")
        if not ev:
            return
        start = datetime.fromisoformat(ev)
        end = start + timedelta(minutes=row.schedule.event_window_min) + self.drift_grace
        if now > end:
            row.schedule.event_at["event"] = (start + timedelta(days=1)).isoformat()
            self.rows.save(row)
            self._emit(row.id, "warning", message="event time drifted, rescheduled +1 day")

    def _dispatch(self) -> None:
        while self.queue and len(self.running) < self.max_concurrent:
            _, _, row_id, mode = heapq.heappop(self.queue)
            self.queued.discard(row_id)
            self.running.add(row_id)
            self._emit(row_id, "running", mode=mode)
            self.executor.submit(self._job, row_id, mode)

    def _job(self, row_id: int, mode: str) -> None:
        row = self.rows.get(row_id)
        ok, err = False, "row deleted"
        if row:
            try:
                res = self.run(row, mode)
                ok, err = getattr(res, "ok", True), getattr(res, "error", None)
            except Exception as e:  # a crashing job must free its slot
                ok, err = False, f"{type(e).__name__}: {e}"
            row = self.rows.get(row_id) or row
            row.schedule.last_run[mode] = self.clock().isoformat()
            self.rows.save(row)
        with self.lock:
            self.running.discard(row_id)
            self._emit(row_id, "idle" if ok else "error", mode=mode, error=err)
            self._dispatch()


def start_background(sched: Scheduler, every_s: int = 30):
    from apscheduler.schedulers.background import BackgroundScheduler

    bg = BackgroundScheduler()
    bg.add_job(sched.tick, "interval", seconds=every_s, max_instances=1)
    bg.start()
    return bg

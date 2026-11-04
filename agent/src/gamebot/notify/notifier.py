from __future__ import annotations

import logging
import queue
import threading
import time
from collections import deque
from collections.abc import Callable

from .base import Channel

logger = logging.getLogger("gamebot.notify")
MAX_LAST = 1000  # prune the dedupe map beyond this many entries


class Notifier:
    def __init__(
        self,
        channels: list[tuple[Channel, str]],
        clock: Callable[[], float] = time.monotonic,
        dedupe_s: float = 300,
        max_per_hour: int = 20,
    ) -> None:
        self.channels = list(channels)
        self._chan_lock = threading.Lock()
        self.clock = clock
        self.dedupe_s = dedupe_s
        self.max_per_hour = max_per_hour
        self._q: queue.Queue = queue.Queue()
        self._lock = threading.Lock()  # guards _last and _errored (scheduler thread)
        self._last: dict[tuple, float] = {}  # (row, detail) -> last time queued
        self._errored: set[int] = set()  # rows whose last state was "error"
        self._sent: deque[float] = deque()  # send times of the last hour (worker thread only)
        self._closed = False
        self._thread = threading.Thread(target=self._run, daemon=True, name="gamebot-notify")
        self._thread.start()

    def set_channels(self, channels: list[tuple[Channel, str]]) -> None:
        with self._chan_lock:
            self.channels = list(channels)

    def handle(self, event: dict) -> None:
        state = event.get("state")
        row = event.get("row")
        mode = event.get("mode", "")
        detail = event.get("error") or event.get("message") or ""
        image = event.get("screenshot")
        item: tuple | None = None
        with self._lock:
            if state == "idle":
                if row in self._errored:
                    self._errored.discard(row)
                    item = (f"gamebot recovered: row {row}", f"mode={mode}", None, "recovered")
            elif state in ("error", "warning"):
                if state == "error":
                    self._errored.add(row)
                key = (row, detail)
                now = self.clock()
                last = self._last.get(key)
                if last is None or now - last >= self.dedupe_s:
                    self._last[key] = now
                    if len(self._last) > MAX_LAST:
                        self._last = {
                            k: t for k, t in self._last.items() if now - t < self.dedupe_s
                        }
                    item = (f"gamebot {state}: row {row}", f"mode={mode}\n{detail}", image, state)
            if item is None:
                return
            inline = self._closed
            if not inline:
                self._q.put(item)  # under the lock: close() cannot slip its sentinel in before
        if inline:  # worker is gone (late job during shutdown): send inline, lock released
            self._deliver(item)

    def _run(self) -> None:
        while True:
            item = self._q.get()
            if item is None:
                break
            self._safe_deliver(item)
        while True:  # drain anything queued before close() flipped the flag
            try:
                item = self._q.get_nowait()
            except queue.Empty:
                break
            if item is not None:
                self._safe_deliver(item)

    def _safe_deliver(self, item: tuple) -> None:
        try:
            self._deliver(item)
        except Exception:
            logger.exception("notify delivery failed")

    def _deliver(self, item: tuple) -> None:
        title, text, image, state = item
        with self._chan_lock:
            targets = [ch for ch, level in self.channels if level == "all" or state != "warning"]
        if not targets:
            return
        now = self.clock()
        while self._sent and now - self._sent[0] > 3600:
            self._sent.popleft()
        if len(self._sent) >= self.max_per_hour:
            logger.warning("hourly notification cap reached, dropped: %s", title)
            return
        self._sent.append(now)
        for ch in targets:
            for attempt in range(2):  # one retry
                try:
                    ch.send(title, text, image)
                    break
                except Exception:
                    if attempt == 1:
                        logger.exception("notify channel %s failed", type(ch).__name__)

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._q.put(None)
        self._thread.join(timeout=5)

from __future__ import annotations

from collections.abc import Callable

from .base import EmulatorDriver, Instance


def default_list_serials() -> list[str]:
    from adbutils import adb

    return [d.serial for d in adb.device_list()]


class AdbGenericDriver(EmulatorDriver):
    """Fallback driver: every device visible to `adb devices` is an instance."""

    kind = "adb"

    def __init__(self, list_serials: Callable[[], list[str]] = default_list_serials):
        self._list = list_serials

    def scan(self) -> list[Instance]:
        return [Instance(self.kind, s, s, s, True) for s in self._list()]

    def start(self, ref: str) -> None:
        raise NotImplementedError("generic ADB devices cannot be started")

    def stop(self, ref: str) -> None:
        raise NotImplementedError("generic ADB devices cannot be stopped")

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class Instance:
    """One emulator instance as seen by a driver."""

    kind: str
    name: str
    ref: str  # driver-specific id (index, name, ...)
    serial: str | None  # adb serial, None until the instance is running
    running: bool = False


class EmulatorDriver(ABC):
    kind: str

    @abstractmethod
    def scan(self) -> list[Instance]: ...

    @abstractmethod
    def start(self, ref: str) -> None: ...

    @abstractmethod
    def stop(self, ref: str) -> None: ...

    def adb_serial(self, ref: str) -> str | None:
        for inst in self.scan():
            if inst.ref == ref:
                return inst.serial
        return None

    def set_resolution(self, ref: str, width: int, height: int, dpi: int) -> bool:
        """Resize through the emulator's own tool; False means use `wm size` fallback."""
        return False

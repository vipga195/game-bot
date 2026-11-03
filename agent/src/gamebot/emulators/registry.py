from __future__ import annotations

from .base import EmulatorDriver, Instance


class Registry:
    def __init__(self, drivers: list[EmulatorDriver]):
        self.drivers = {d.kind: d for d in drivers}

    def scan(self) -> list[Instance]:
        """Scan all drivers; dedupe by adb serial (driver-specific entries win over generic)."""
        found: list[Instance] = []
        seen: set[str] = set()
        ordered = sorted(self.drivers.values(), key=lambda d: d.kind == "adb")
        for drv in ordered:
            try:
                items = drv.scan()
            except Exception:  # a missing emulator install must not break the others
                continue
            for inst in items:
                if inst.serial and inst.serial in seen:
                    continue
                if inst.serial:
                    seen.add(inst.serial)
                found.append(inst)
        return found

    def driver(self, kind: str) -> EmulatorDriver:
        return self.drivers[kind]

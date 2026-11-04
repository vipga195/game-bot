from typing import Protocol


class Channel(Protocol):
    def send(self, title: str, text: str, image: bytes | None = None) -> None:
        """Send one message; raises on failure."""

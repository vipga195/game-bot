from __future__ import annotations

import httpx


class TelegramChannel:
    def __init__(self, token: str, chat_id: str, send_image: bool = False, post=httpx.post) -> None:
        self.token = token
        self.chat_id = chat_id
        self.send_image = send_image
        self.post = post

    def send(self, title: str, text: str, image: bytes | None = None) -> None:
        caption = f"{title}\n{text}"
        if image is not None and self.send_image:
            url = f"https://api.telegram.org/bot{self.token}/sendPhoto"
            data = {"chat_id": self.chat_id, "caption": caption[:1024]}
            files = {"photo": ("screenshot.png", image, "image/png")}
        else:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            data = {"chat_id": self.chat_id, "text": caption[:4096]}
            files = None
        try:
            resp = self.post(url, data=data, files=files, timeout=10)
        except Exception:
            # httpx errors embed the request URL, which contains the bot token
            raise RuntimeError("telegram send failed") from None
        if not 200 <= resp.status_code < 300:
            raise RuntimeError(f"telegram send failed: HTTP {resp.status_code}")

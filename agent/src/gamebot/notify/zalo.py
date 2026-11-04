from __future__ import annotations

import httpx


class ZaloChannel:
    def __init__(self, token: str, chat_id: str, post=httpx.post) -> None:
        self.token = token
        self.chat_id = chat_id
        self.post = post

    def send(self, title: str, text: str, image: bytes | None = None) -> None:
        # sendPhoto only accepts an image URL, so the image is ignored.
        payload = {"chat_id": self.chat_id, "text": f"{title}\n{text}"[:2000]}
        url = f"https://bot-api.zaloplatforms.com/bot{self.token}/sendMessage"
        try:
            resp = self.post(url, json=payload, timeout=10)
        except Exception:
            # httpx errors embed the request URL, which contains the bot token
            raise RuntimeError("zalo send failed") from None
        if not 200 <= resp.status_code < 300:
            raise RuntimeError(f"zalo send failed: HTTP {resp.status_code}")
        try:
            body = resp.json()
        except Exception:
            body = None
        if isinstance(body, dict) and body.get("ok") is False:
            raise RuntimeError("zalo send failed: API returned ok=false")

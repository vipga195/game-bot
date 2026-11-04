from __future__ import annotations

import httpx


class TeamsChannel:
    def __init__(self, webhook_url: str, post=httpx.post) -> None:
        self.webhook_url = webhook_url
        self.post = post

    def send(self, title: str, text: str, image: bytes | None = None) -> None:
        text = text[:4000]
        payload = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "contentUrl": None,
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.2",
                        "body": [
                            {"type": "TextBlock", "text": title, "weight": "Bolder", "wrap": True},
                            {"type": "TextBlock", "text": text, "wrap": True},
                        ],
                    },
                }
            ],
        }
        try:
            resp = self.post(self.webhook_url, json=payload, timeout=10)
        except Exception:
            raise RuntimeError("teams send failed") from None
        if not 200 <= resp.status_code < 300:
            raise RuntimeError(f"teams send failed: HTTP {resp.status_code}")

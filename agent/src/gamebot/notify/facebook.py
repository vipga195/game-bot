from __future__ import annotations

import httpx


class FacebookChannel:
    """
    Only works within the 24h standard messaging window after the recipient last messaged
    the page. Image not sent (upload API unverified).
    """

    def __init__(self, page_token: str, page_id: str, recipient_id: str, post=httpx.post) -> None:
        self.page_token = page_token
        self.page_id = page_id
        self.recipient_id = recipient_id
        self.post = post

    def send(self, title: str, text: str, image: bytes | None = None) -> None:
        # image is ignored.
        url = f"https://graph.facebook.com/v26.0/{self.page_id}/messages"
        params = {"access_token": self.page_token}
        payload = {
            "recipient": {"id": self.recipient_id},
            "messaging_type": "RESPONSE",
            "message": {"text": f"{title}\n{text}"[:2000]},
        }
        try:
            resp = self.post(url, params=params, json=payload, timeout=10)
        except Exception:
            # httpx errors embed the request URL, which contains the page access token
            raise RuntimeError("facebook send failed") from None
        if not 200 <= resp.status_code < 300:
            raise RuntimeError(
                f"facebook send failed: HTTP {resp.status_code} "
                "(24h messaging window may have closed)"
            )

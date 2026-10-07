from fastapi import HTTPException
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import settings


class BodyLimit:
    """Bound bytes before Starlette's multipart parser can spool them to disk."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        size = 0

        async def bounded_receive():
            nonlocal size
            message = await receive()
            if message["type"] == "http.request":
                size += len(message.get("body", b""))
                if size > settings().max_upload_bytes + 1024 * 1024:
                    raise HTTPException(413, "file_too_large")
            return message

        await self.app(scope, bounded_receive, send)

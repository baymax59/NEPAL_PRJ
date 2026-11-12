"""Headers on every API response (Step 14.2). The web server adds the page-level ones (deploy/Caddyfile).

Added here as well, so they hold even if the API is ever reached without that web server.
"""

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class ApiResponseHeaders:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                # Case data must not stay in the browser's cache (shared office computers).
                headers["Cache-Control"] = "no-store"
                # The browser must not guess a different content type (e.g. treat JSON as a page).
                headers["X-Content-Type-Options"] = "nosniff"
            await send(message)

        await self.app(scope, receive, send_with_headers)

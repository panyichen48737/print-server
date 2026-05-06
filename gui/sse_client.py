"""SSE event stream client running in background thread."""
import asyncio
import json
import threading
from typing import Callable
from gui.http_client import get_client

class SSEClient:
    def __init__(self):
        self._callbacks: dict[str, list[Callable]] = {}
        self._running = False
        self._thread: threading.Thread | None = None

    def on(self, event_type: str, callback: Callable):
        self._callbacks.setdefault(event_type, []).append(callback)

    def off(self, event_type: str, callback: Callable):
        self._callbacks.get(event_type, []).remove(callback)

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._stream())
        loop.close()

    async def _stream(self):
        client = get_client()
        try:
            async with client.stream("GET", "/api/events") as response:
                async for line in response.aiter_lines():
                    if not self._running:
                        break
                    if line.startswith("event: "):
                        event_type = line[7:]
                    elif line.startswith("data: "):
                        data = json.loads(line[6:])
                        for cb in self._callbacks.get(event_type, []):
                            cb(data)
        except Exception:
            pass  # Connection error handled by caller

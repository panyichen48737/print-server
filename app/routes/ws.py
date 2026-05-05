"""WebSocket 端点 — 复用 SSEBroadcaster 的发布/订阅机制"""

import asyncio
import queue as _queue
import time as _time

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from loguru import logger

_MAX_DURATION = 3600


def register_ws_routes(app: FastAPI) -> None:
    @app.websocket('/ws/events')
    async def ws_events(websocket: WebSocket):
        broadcaster = app.state.sse
        await websocket.accept()

        sub_id, q = broadcaster.subscribe()
        loop = asyncio.get_running_loop()
        start = _time.monotonic()
        try:
            while True:
                if _time.monotonic() - start > _MAX_DURATION:
                    break
                try:
                    event_type, data = await loop.run_in_executor(None, lambda: q.get(timeout=5))
                    await websocket.send_json(
                        {
                            'event': event_type,
                            'data': data,
                        }
                    )
                except _queue.Empty:
                    continue
        except WebSocketDisconnect:
            pass
        except Exception:
            logger.exception('WebSocket 异常')
        finally:
            broadcaster.unsubscribe(sub_id)

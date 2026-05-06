"""httpx.AsyncClient singleton with keep-alive connection pool."""
import threading

import httpx

_client: httpx.AsyncClient | None = None
_lock = threading.Lock()


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                limits = httpx.Limits(
                    max_keepalive_connections=10,
                    max_connections=20,
                    keepalive_expiry=30.0,
                )
                _client = httpx.AsyncClient(
                    base_url="http://127.0.0.1:5000",
                    limits=limits,
                    timeout=httpx.Timeout(10.0),
                )
    return _client


async def close_client():
    global _client
    if _client:
        with _lock:
            if _client:
                await _client.aclose()
                _client = None

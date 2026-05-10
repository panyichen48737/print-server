"""Integration tests -- in-process ServerHandle, test HTTP API."""

import asyncio

import httpx
import pytest


@pytest.mark.integration
async def test_daemon_health():
    from app.bootstrap import bootstrap
    from app.core.config import Config
    from launcher import ServerHandle, _server_lifespan

    config = Config()
    app, *_ = bootstrap(config, lifespan=_server_lifespan)
    handle = ServerHandle()

    ok = handle.start(app, config)
    assert ok, 'ServerHandle did not start within timeout'

    proto = 'https' if handle.ssl_enabled else 'http'
    for _ in range(10):
        try:
            async with httpx.AsyncClient(verify=False) as c:
                r = await c.get(f'{proto}://127.0.0.1:5000/api/health')
                if r.status_code == 200:
                    break
        except Exception:
            pass
        await asyncio.sleep(1)
    else:
        pytest.fail('Server did not respond within 10 seconds')

    assert handle.is_running

    handle.stop()
    assert not handle.is_running


@pytest.mark.integration
async def test_web_api():
    """Verify the API root returns health info."""
    from app.bootstrap import bootstrap
    from app.core.config import Config
    from launcher import ServerHandle, _server_lifespan

    config = Config()
    app, *_ = bootstrap(config, lifespan=_server_lifespan)
    handle = ServerHandle()

    ok = handle.start(app, config)
    assert ok, 'ServerHandle did not start within timeout'

    proto = 'https' if handle.ssl_enabled else 'http'
    try:
        async with httpx.AsyncClient(verify=False) as c:
            r = await c.get(f'{proto}://127.0.0.1:5000/api/health')
            assert r.status_code == 200
    finally:
        handle.stop()

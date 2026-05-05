"""Integration tests — start real daemon, test HTTP API."""

import subprocess
import sys
import time

import httpx
import pytest


@pytest.mark.integration
async def test_daemon_health():
    proc = subprocess.Popen(
        [sys.executable, '-m', 'console', '--start'], stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    try:
        for _ in range(10):
            try:
                async with httpx.AsyncClient(verify=False) as c:
                    r = await c.get('https://127.0.0.1:5000/api/health')
                    if r.status_code == 200:
                        return
            except Exception:
                pass
            time.sleep(1)
        pytest.fail('Daemon did not respond within 10 seconds')
    finally:
        proc.terminate()
        proc.wait(timeout=5)


@pytest.mark.integration
async def test_web_admin():
    proc = subprocess.Popen(
        [sys.executable, '-m', 'console', '--start'], stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    try:
        time.sleep(3)
        async with httpx.AsyncClient(verify=False) as c:
            r = await c.get('http://127.0.0.1:5001/admin/', follow_redirects=True)
            assert r.status_code == 200
    finally:
        proc.terminate()
        proc.wait(timeout=5)

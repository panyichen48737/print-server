"""Test GUI child process lifecycle."""
import pytest
import time
from gui.child_process import ChildProcess


@pytest.mark.integration
@pytest.mark.asyncio
async def test_child_process_start_stop():
    cp = ChildProcess()
    cp.start()
    time.sleep(2)
    healthy = await cp.health_check()
    assert healthy, "Server should be healthy after start"
    cp.stop()
    assert not cp.is_running(), "Server should stop"


@pytest.mark.asyncio
async def test_child_process_health_check_fails():
    cp = ChildProcess()
    healthy = await cp.health_check()
    assert not healthy, "Health check should fail with no server"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_child_process_restart():
    cp = ChildProcess()
    cp.start()
    time.sleep(2)
    await cp.health_check()
    cp.restart()
    time.sleep(2)
    healthy = await cp.health_check()
    assert healthy, "Server should be healthy after restart"
    cp.stop()

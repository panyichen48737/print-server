"""Subprocess lifecycle management for --headless server."""
import asyncio
import os
import socket
import subprocess
import sys
import threading
import time
from gui.http_client import get_client


class ChildProcess:
    def __init__(self):
        self._process: subprocess.Popen | None = None
        self._restart_count = 0
        self._max_restarts = 3
        self._lock = threading.Lock()

    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def _port_listening(self, port: int = 5000) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(("127.0.0.1", port)) == 0

    async def health_check(self) -> bool:
        try:
            client = get_client()
            resp = await client.get("/api/health", timeout=3.0)
            return resp.status_code == 200
        except Exception:
            return False

    def start(self):
        with self._lock:
            if self._port_listening():
                return  # Already running
            exe = sys.executable
            args = [exe, "-m", "console", "--headless"]
            if getattr(sys, "frozen", False):
                exe = os.path.join(sys._MEIPASS, "iOSPrintServer.exe")
                args = [exe, "--headless"]
            self._process = subprocess.Popen(
                args,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            self._restart_count = 0

    def stop(self):
        with self._lock:
            if self._process:
                self._process.terminate()
                try:
                    self._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                self._process = None

    def restart(self):
        self.stop()
        time.sleep(2)
        self.start()

    async def health_loop(self, on_failure: callable):
        """Called periodically from GUI. Restarts on failure up to 3 times."""
        while True:
            await asyncio.sleep(10)
            if not self.is_running():
                continue
            ok = await self.health_check()
            if ok:
                self._restart_count = 0
                continue
            self._restart_count += 1
            if self._restart_count > self._max_restarts:
                on_failure("服务器崩溃，自动重启失败（已达最大尝试次数）")
                break
            self.restart()

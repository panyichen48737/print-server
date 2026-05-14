"""TCP client for update_service.exe (SYSTEM service)."""

from __future__ import annotations

import json
import os
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_SERVICE_HOST = '127.0.0.1'
_SERVICE_PORT = 48273
_TIMEOUT = 5.0


@dataclass
class ServiceResponse:
    status: str
    message: str = ''
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class PendingUpdate:
    version: str
    zip_path: str
    download_type: str = 'incremental'  # "incremental" | "full"


_PENDING_FILE: Path | None = None


def _pending_file_path() -> Path:
    global _PENDING_FILE
    if _PENDING_FILE is None:
        program_data = os.environ.get('PROGRAMDATA', 'C:\\ProgramData')
        _PENDING_FILE = Path(program_data) / 'iOSPrintServer' / 'update_cache' / 'pending.json'
    return _PENDING_FILE


def read_pending_file() -> PendingUpdate | None:
    """Read pending update info from Go service's pending.json (no TCP call)."""
    path = _pending_file_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text('utf-8'))
        version = data.get('version', '')
        zip_path = data.get('zip_path', '')
        download_type = data.get('download_type', 'incremental')
        if not version or not zip_path:
            return None
        return PendingUpdate(version=version, zip_path=zip_path, download_type=download_type)
    except (json.JSONDecodeError, OSError):
        return None


def _send_request(data: dict) -> ServiceResponse | None:
    """Send a JSON request to the update service. Returns None on connection failure."""
    try:
        sock = socket.create_connection((_SERVICE_HOST, _SERVICE_PORT), timeout=_TIMEOUT)
        with sock:
            sock.sendall(json.dumps(data).encode('utf-8'))
            resp_data = sock.recv(4096)
            if not resp_data:
                return None
            resp = json.loads(resp_data.decode('utf-8'))
            return ServiceResponse(
                status=resp.get('status', 'error'),
                message=resp.get('message', ''),
            )
    except (TimeoutError, ConnectionRefusedError, OSError, json.JSONDecodeError):
        return None


def service_status() -> ServiceResponse | None:
    return _send_request({'cmd': 'STATUS'})


def health() -> ServiceResponse | None:
    """Check backend health via watchdog."""
    return _send_request({'cmd': 'HEALTH'})


def register(port: int) -> ServiceResponse | None:
    """Register GUI with watchdog for crash recovery."""
    return _send_request({'cmd': 'REGISTER', 'port': port})


def shutdown() -> ServiceResponse | None:
    """Notify watchdog that GUI is shutting down intentionally."""
    return _send_request({'cmd': 'SHUTDOWN'})


def pending_update() -> PendingUpdate | None:
    """Check if service has a pre-downloaded update ready to apply."""
    resp = _send_request({'cmd': 'PENDING_UPDATE'})
    if resp is None or resp.status != 'ok' or resp.message == 'none':
        return None
    try:
        data = json.loads(resp.message)
        return PendingUpdate(
            version=data.get('version', ''),
            zip_path=data.get('zip_path', ''),
        )
    except (json.JSONDecodeError, TypeError):
        return None


def trigger_check(app_dir: str | None = None) -> ServiceResponse | None:
    """Tell service to check GitHub for updates now."""
    data: dict[str, Any] = {'cmd': 'CHECK'}
    if app_dir:
        data['app_dir'] = app_dir
    return _send_request(data)


def apply_update(zip_path: str, app_dir: str | None = None) -> ServiceResponse | None:
    """Tell the service to apply an update zip."""
    data: dict[str, Any] = {'cmd': 'APPLY', 'zip_path': zip_path}
    if app_dir:
        data['app_dir'] = app_dir
    return _send_request(data)

"""Named pipe client for update_service.exe (SYSTEM service)."""
from __future__ import annotations

import json
import socket
from dataclasses import dataclass

_SERVICE_HOST = '127.0.0.1'
_SERVICE_PORT = 48273
_TIMEOUT = 5.0


@dataclass
class ServiceResponse:
    status: str
    message: str


def _send_request(data: dict) -> ServiceResponse | None:
    """Send a JSON request to the update service. Returns None on connection failure."""
    try:
        sock = socket.create_connection(
            (_SERVICE_HOST, _SERVICE_PORT), timeout=_TIMEOUT
        )
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
    except (ConnectionRefusedError, socket.timeout, OSError, json.JSONDecodeError):
        return None


def service_status() -> ServiceResponse | None:
    """Check if the update service is running."""
    return _send_request({'cmd': 'STATUS'})


def apply_update(zip_path: str, app_dir: str | None = None) -> ServiceResponse | None:
    """Tell the service to apply an update zip."""
    data = {'cmd': 'APPLY', 'zip_path': zip_path}
    if app_dir:
        data['app_dir'] = app_dir
    return _send_request(data)

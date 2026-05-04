"""认证模块：FastAPI Depends 依赖"""

from fastapi import HTTPException, Request


async def require_auth(request: Request) -> None:
    """FastAPI 依赖：验证 Bearer Token"""
    auth = request.headers.get('Authorization', '')
    config = request.app.state.app_config
    expected = f'Bearer {config.get("api_key", "print-server-key-2026")}'
    if auth != expected:
        raise HTTPException(status_code=401, detail='Unauthorized')

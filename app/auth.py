"""认证模块：提供 require_auth 装饰器和 check_auth 低级函数"""

from collections.abc import Callable
from functools import wraps
from flask import request, jsonify, current_app, Response


def check_auth() -> bool:
    """验证 Bearer Token"""
    auth = request.headers.get('Authorization', '')
    config = current_app.config['app_config']
    expected = f'Bearer {config.api_key}'
    return auth == expected


def require_auth(f: Callable) -> Callable:
    """Flask 路由装饰器：要求请求携带有效的 Bearer Token"""
    @wraps(f)
    def decorated(*args: object, **kwargs: object) -> Response:
        if not check_auth():
            return jsonify({'success': False, 'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated

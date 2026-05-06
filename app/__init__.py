"""FastAPI 应用工厂"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app._paths import data_root, ensure_dir, persistent_dir
from app.exceptions import AuthError, FileTypeError, PrintServerError
from app.version import __version__


@asynccontextmanager
async def _default_lifespan(_app):
    yield


def create_app(lifespan=_default_lifespan) -> FastAPI:
    app = FastAPI(
        title='iOSPrintServer',
        version=__version__,
        description='iOS 云打印服务器 - 管理打印机、提交打印任务、监控状态',
        contact={'name': 'Developer'},
        license_info={'name': 'MIT', 'identifier': 'MIT'},
        lifespan=lifespan,
        docs_url='/docs',
        redoc_url='/redoc',
        openapi_url='/openapi.json',
    )

    @app.exception_handler(FileTypeError)
    async def _filetype_handler(_request, exc):
        return JSONResponse(status_code=400, content={'error': str(exc)})

    @app.exception_handler(AuthError)
    async def _auth_handler(_request, exc):
        return JSONResponse(status_code=403, content={'error': str(exc)})

    @app.exception_handler(PrintServerError)
    async def _print_server_handler(_request, exc):
        return JSONResponse(status_code=500, content={'error': str(exc)})

    @app.get('/scalar', include_in_schema=False)
    async def scalar_html():
        return HTMLResponse(f'''
    <!DOCTYPE html>
    <html>
    <head><title>iOSPrintServer API</title><meta charset="utf-8"/></head>
    <body>
    <script id="api-reference" data-url="{app.openapi_url}"></script>
    <script src="https://cdn.staticfile.org/scalar-api-reference/1.25.10/standalone.min.js"></script>
    </body>
    </html>
    ''')

    static_dir = os.path.join(data_root(), 'app', 'static')
    if os.path.isdir(static_dir):
        app.mount('/static', StaticFiles(directory=static_dir), name='static')

    from app.routes.admin import admin_router
    from app.routes.api import api_router

    app.include_router(api_router, prefix='/api')
    app.include_router(admin_router, prefix='/admin')

    # 根路径重定向到管理后台
    @app.get('/', include_in_schema=False)
    async def root_redirect():
        from fastapi.responses import RedirectResponse

        return RedirectResponse(url='/admin')

    ensure_dir(persistent_dir(), 'jobs')
    ensure_dir(persistent_dir(), 'logs')

    from app.services.sse_broadcaster import init_app

    init_app(app)

    from app.routes.ws import register_ws_routes

    register_ws_routes(app)

    return app

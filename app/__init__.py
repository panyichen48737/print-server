"""FastAPI 应用工厂"""

import sys
import urllib.request
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from app.core._paths import ensure_dir, persistent_dir
from app.core.exceptions import AuthError, FileTypeError, PrintServerError
from app.core.version import __version__

_SCALAR_URL = (
    'https://cdn.jsdelivr.net/npm/@scalar/api-reference@latest/dist/browser/standalone.min.js'
)
_SCALAR_FILE = 'scalar.standalone.min.js'


def _ensure_scalar_js(static_dir: Path) -> None:
    """Download Scalar API Reference JS if not present."""
    target = static_dir / _SCALAR_FILE
    if target.is_file():
        return
    # Frozen mode: static files are at sys.executable.parent/app/static/
    if getattr(sys, 'frozen', False):
        alt = Path(sys.executable).parent / 'app' / 'static' / _SCALAR_FILE
        if alt.is_file():
            static_dir.mkdir(parents=True, exist_ok=True)
            import shutil

            shutil.copy2(alt, target)
            logger.info(f'Scalar JS found at {alt} ({target.stat().st_size / 1024:.0f} KB)')
            return
    try:
        logger.info('Downloading Scalar API Reference JS …')
        urllib.request.urlretrieve(_SCALAR_URL, target)
        logger.info(f'Scalar JS saved ({target.stat().st_size / 1024:.0f} KB)')
    except Exception as exc:
        logger.warning(f'Failed to download Scalar JS: {exc}')


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

    static_dir = Path(__file__).resolve().parent / 'static'
    static_dir.mkdir(parents=True, exist_ok=True)
    _ensure_scalar_js(static_dir)
    app.mount('/static', StaticFiles(directory=str(static_dir)), name='static')

    @app.get('/scalar', include_in_schema=False)
    async def scalar_html():
        return HTMLResponse(f'''
    <!DOCTYPE html>
    <html>
    <head><title>iOSPrintServer API</title><meta charset="utf-8"/></head>
    <body>
    <script id="api-reference" data-url="{app.openapi_url}"></script>
    <script src="/static/{_SCALAR_FILE}"></script>
    </body>
    </html>
    ''')

    from app.routes.api import api_router
    from app.routes.system import system_router

    app.include_router(api_router, prefix='/api')
    app.include_router(system_router, prefix='/api')

    ensure_dir(persistent_dir() / 'jobs')
    ensure_dir(persistent_dir() / 'logs')

    from app.services.sse_broadcaster import init_app

    init_app(app)

    from app.routes.ws import register_ws_routes

    register_ws_routes(app)

    return app

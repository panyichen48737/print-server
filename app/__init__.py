"""FastAPI 应用工厂"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app._paths import app_root, ensure_dir, data_root


@asynccontextmanager
async def _default_lifespan(app):
    yield


def create_app(lifespan=_default_lifespan) -> FastAPI:
    app = FastAPI(title='iOSPrintServer', version='1.0.0', lifespan=lifespan)

    static_dir = os.path.join(data_root(), 'app', 'static')
    if os.path.isdir(static_dir):
        app.mount('/static', StaticFiles(directory=static_dir), name='static')

    from app.routes.api import api_router
    from app.routes.admin import admin_router

    app.include_router(api_router, prefix='/api')
    app.include_router(admin_router, prefix='/admin')

    ensure_dir(app_root(), 'jobs')
    ensure_dir(app_root(), 'logs')

    from app.services.sse_broadcaster import init_app
    init_app(app)

    from app.routes.ws import register_ws_routes
    register_ws_routes(app)

    return app

import os
import logging
from flask import Flask
from app._paths import app_root, ensure_dir


def create_app():
    from app._paths import data_root
    dr = data_root()
    app = Flask(__name__,
                static_folder=os.path.join(dr, 'app', 'static'),
                template_folder=os.path.join(dr, 'app', 'templates'))

    from app.routes.api import api_bp
    from app.routes.admin import admin_bp

    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(admin_bp, url_prefix='/admin')

    ensure_dir(app_root(), 'jobs')
    ensure_dir(app_root(), 'logs')

    from app.services.sse_broadcaster import init_app
    init_app(app)

    return app

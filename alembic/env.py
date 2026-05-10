"""Alembic environment config — dynamic SQLite path resolution."""

import os
from logging.config import fileConfig

from alembic import context

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Resolve %APPDATA% in sqlalchemy.url
db_url = config.get_main_option('sqlalchemy.url', '')
if '%APPDATA%' in db_url:
    appdata = os.environ.get('APPDATA', os.path.expanduser('~'))
    db_url = db_url.replace('%(APPDATA)s', appdata.replace('\\', '/'))
    config.set_main_option('sqlalchemy.url', db_url)

target_metadata = None


def run_migrations_offline() -> None:
    context.configure(
        url=db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={'paramstyle': 'named'},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    import sqlite3
    from urllib.parse import urlparse

    parsed = urlparse(db_url)
    db_path = parsed.path.lstrip('/')
    connectable = sqlite3.connect(db_path)

    with connectable:
        context.configure(
            connection=connectable,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

"""数据库迁移 — 增量式 schema 升级"""

from loguru import logger

MIGRATIONS: dict[str, str] = {
    'duplex': 'INTEGER DEFAULT 0',
    'color': 'INTEGER DEFAULT 1',
    'paper_size': "TEXT DEFAULT 'A4'",
    'source': "TEXT DEFAULT 'api'",
    'retry_count': 'INTEGER DEFAULT 0',
    'page_range': "TEXT DEFAULT ''",
    'nup': 'INTEGER DEFAULT 1',
}


def migrate_db(execute_fn) -> None:
    """检测并执行增量列添加"""
    rows = execute_fn('PRAGMA table_info(jobs)', fetchall=True)
    existing = {row['name'] for row in rows} if rows else set()
    for col, dtype in MIGRATIONS.items():
        if col not in existing:
            execute_fn(f'ALTER TABLE jobs ADD COLUMN {col} {dtype}', commit=True)
            logger.info(f'迁移: 添加列 {col} {dtype}')

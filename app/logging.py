"""日志配置 — loguru 文件 + stderr"""

import sys
from pathlib import Path


def setup_logging(log_dir: str | Path | None = None, level: str = 'INFO'):
    """配置 loguru 日志：文件轮转 + stderr"""
    import loguru

    from app._paths import persistent_dir

    if log_dir is None:
        log_dir = persistent_dir() / 'logs'
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / 'print_server.log'

    loguru.logger.remove()

    loguru.logger.add(
        log_file,
        rotation='00:00',
        retention=7,
        encoding='utf-8',
        format='{time:YYYY-MM-DD HH:mm:ss} [{level}] {message}',
        level=level,
    )

    loguru.logger.add(
        sys.stderr,
        format='{time:HH:mm:ss} [{level}] {message}',
        level='ERROR',
    )

    return loguru.logger

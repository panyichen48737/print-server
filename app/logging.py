"""日志配置 — loguru 文件 + stderr"""
import os
import sys


def setup_logging(log_dir: str | None = None, level: str = 'INFO'):
    """配置 loguru 日志：文件轮转 + stderr"""
    import loguru
    from app._paths import persistent_dir

    if log_dir is None:
        log_dir = os.path.join(persistent_dir(), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, 'print_server.log')

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
        level=level,
    )

    return loguru.logger

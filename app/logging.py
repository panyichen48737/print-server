"""日志配置 — loguru 单文件（含来源标记，GUI 查看器按来源过滤）

单一文件：
  app.log  — 所有日志（[Server]/[GUI] 前缀区分来源）
  watchdog.log — Go 看守服务（外部程序写入）
  update_service.log — Go 更新服务（外部程序写入）"""

import sys
from pathlib import Path


def setup_logging(log_dir_path: str | Path | None = None, level: str = 'INFO'):
    """配置 loguru 日志：单文件，来源标记"""
    import loguru

    from app.core._paths import log_dir

    if log_dir_path is None:
        log_dir_path = log_dir()
    log_dir_path = Path(log_dir_path)
    log_dir_path.mkdir(parents=True, exist_ok=True)

    loguru.logger.remove()
    loguru.logger.configure(extra={'source': 'Server'})

    _fmt = '{time:YYYY-MM-DD HH:mm:ss} [{level}] [{extra[source]}] {message}'

    loguru.logger.add(
        log_dir_path / 'app.log',
        rotation='00:00',
        retention=7,
        encoding='utf-8',
        format=_fmt,
        level=level,
    )

    if sys.stderr is not None:
        loguru.logger.add(
            sys.stderr,
            format='{time:HH:mm:ss} [{level}] {message}',
            level='ERROR',
        )

    return loguru.logger

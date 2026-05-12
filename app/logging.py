"""日志配置 — loguru 文件 + stderr

三文件分流：
  print_server.log  — 后端日志（[Server] 前缀）
  gui.log           — 前端日志（[GUI] 前缀）
  update_service.log — Go 守护服务日志（外部程序写入，不做处理）

GUI 日志查看器合并读取所有文件。"""

import sys
from pathlib import Path


def setup_logging(log_dir_path: str | Path | None = None, level: str = 'INFO'):
    """配置 loguru 日志：后端/前端分流"""
    import loguru

    from app.core._paths import log_dir

    if log_dir_path is None:
        log_dir_path = log_dir()
    log_dir_path = Path(log_dir_path)
    log_dir_path.mkdir(parents=True, exist_ok=True)

    loguru.logger.remove()
    loguru.logger.configure(extra={'source': 'Server'})

    _fmt = '{time:YYYY-MM-DD HH:mm:ss} [{level}] [{extra[source]}] {message}'

    # 后端日志
    loguru.logger.add(
        log_dir_path / 'print_server.log',
        rotation='00:00',
        retention=7,
        encoding='utf-8',
        format=_fmt,
        level=level,
        filter=lambda record: record.get('extra', {}).get('source') != 'GUI',
    )

    # 前端日志（也包含后端日志副本，方便 GUI 查看器合并展示）
    loguru.logger.add(
        log_dir_path / 'gui.log',
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

"""资源管理 — frozen 模式下资源由安装器放置在同级目录，无需运行时释放。"""
from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger


def _resources_dir() -> Path | None:
    """返回资源目录。
    frozen 模式：exe 同级 resources/（安装器放置）
    dev 模式：build/resources/
    """
    if getattr(sys, 'frozen', False):
        d = Path(sys.executable).parent / 'resources'
        return d if d.is_dir() else None
    return None


def _gui_resources_dir() -> Path | None:
    """返回 GUI 资源目录（QSS + 图标）。
    frozen 模式：exe 同级 gui/resources/（安装器放置）
    dev 模式：gui/resources/
    """
    if getattr(sys, 'frozen', False):
        d = Path(sys.executable).parent / 'gui' / 'resources'
        return d if d.is_dir() else None
    return None


def ensure_resources() -> None:
    """frozen 模式下检查资源目录是否存在，不存在则告警。"""
    if not getattr(sys, 'frozen', False):
        return
    res = _resources_dir()
    gui_res = _gui_resources_dir()
    if not res:
        logger.warning("resources/ 目录不存在，请重新安装")
    if not gui_res:
        logger.warning("gui/resources/ 目录不存在，请重新安装")
    if res:
        logger.debug(f"资源目录: {res}")
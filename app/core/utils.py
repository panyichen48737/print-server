"""通用工具函数"""

import os
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from loguru import logger


def safe_int(val: str, default: int) -> int:
    """字符串转整数，失败返回默认值"""
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def format_time(dt: datetime | None = None) -> str:
    """返回 YYYY-MM-DD HH:MM:SS 格式时间字符串"""
    return (dt or datetime.now()).strftime('%Y-%m-%d %H:%M:%S')


def safe_remove(filepath: str | None, label: str = '文件') -> None:
    """安全删除文件，不存在则忽略"""
    if not filepath:
        return
    try:
        os.remove(filepath)
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning(f'删除{label}失败: {filepath} - {e}')


@contextmanager
def temp_print_file(original_path: str, filename: str) -> Iterator[str]:
    """创建打印临时副本并在退出时自动清理"""
    suffix = Path(filename).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp_path = tmp.name
    shutil.copy2(original_path, tmp_path)
    try:
        yield tmp_path
    finally:
        safe_remove(tmp_path)

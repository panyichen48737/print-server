"""通用工具函数"""
import os
from datetime import datetime
from typing import Optional

from loguru import logger


def safe_int(val: str, default: int) -> int:
    """字符串转整数，失败返回默认值"""
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def format_time(dt: Optional[datetime] = None) -> str:
    """返回 YYYY-MM-DD HH:MM:SS 格式时间字符串"""
    return (dt or datetime.now()).strftime('%Y-%m-%d %H:%M:%S')


def safe_remove(filepath: Optional[str], label: str = '文件') -> None:
    """安全删除文件，不存在则忽略"""
    if not filepath:
        return
    try:
        os.remove(filepath)
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning(f'删除{label}失败: {filepath} - {e}')

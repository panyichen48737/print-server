"""通用工具函数"""


def safe_int(val: str, default: int) -> int:
    """字符串转整数，失败返回默认值"""
    try:
        return int(val)
    except (ValueError, TypeError):
        return default

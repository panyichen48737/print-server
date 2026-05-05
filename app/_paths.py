"""路径工具：兼容开发模式（__file__）和 PyInstaller 打包模式（sys._MEIPASS）

分层：
  data_root()   — 只读内置文件（模板/静态文件），frozen → sys._MEIPASS
  app_root()    — exe 所在目录（仅作参考）
  persistent_dir() — 可写持久化数据，frozen → %%APPDATA%%/iOSPrintServer
"""

import os
import sys


def app_root() -> str:
    """返回 exe 所在目录（frozen）或项目根目录（dev）"""
    if getattr(sys, 'frozen', False) or getattr(sys, '__compiled__', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def data_root() -> str:
    """返回只读内置文件目录（模板/静态文件等）

    frozen 模式：sys._MEIPASS（PyInstaller 临时解压目录，退出自动清理）
    dev 模式：app_root()
    """
    if getattr(sys, 'frozen', False) or getattr(sys, '__compiled__', False):
        if hasattr(sys, '_MEIPASS'):
            return sys._MEIPASS
        return os.path.dirname(sys.executable)
    return app_root()


def persistent_dir() -> str:
    """持久化数据目录

    frozen 模式：%%APPDATA%%/iOSPrintServer（配置/日志/数据库持久保留）
    dev 模式：app_root()（开发时与项目文件放在一起）
    """
    if getattr(sys, 'frozen', False) or getattr(sys, '__compiled__', False):
        return os.path.join(
            os.environ.get('APPDATA', os.path.expanduser('~')),
            'iOSPrintServer',
        )
    return app_root()


def ensure_dir(*parts: str) -> str:
    path = os.path.join(*parts)
    os.makedirs(path, exist_ok=True)
    return path

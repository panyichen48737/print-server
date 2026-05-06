"""路径工具：兼容开发模式（__file__）和 PyInstaller 打包模式（sys._MEIPASS）

分层：
  data_root()   — 只读内置文件（模板/静态文件），frozen → sys._MEIPASS
  app_root()    — exe 所在目录（仅作参考）
  persistent_dir() — 可写持久化数据，frozen → %%APPDATA%%/iOSPrintServer
"""

import os
import sys
from pathlib import Path


def app_root() -> Path:
    """返回 exe 所在目录（frozen）或项目根目录（dev）"""
    if getattr(sys, 'frozen', False) or getattr(sys, '__compiled__', False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def data_root() -> Path:
    """返回只读内置文件目录（模板/静态文件等）

    frozen 模式：sys._MEIPASS（PyInstaller 临时解压目录，退出自动清理）
    dev 模式：app_root()
    """
    if getattr(sys, 'frozen', False) or getattr(sys, '__compiled__', False):
        if hasattr(sys, '_MEIPASS'):
            return Path(sys._MEIPASS)
        return Path(sys.executable).parent
    return app_root()


def persistent_dir() -> Path:
    """持久化数据目录

    frozen 模式：%%APPDATA%%/iOSPrintServer（配置/日志/数据库持久保留）
    dev 模式：app_root()（开发时与项目文件放在一起）
    """
    if getattr(sys, 'frozen', False) or getattr(sys, '__compiled__', False):
        appdata = os.environ.get('APPDATA')
        if appdata:
            return Path(appdata) / 'iOSPrintServer'
        return Path.home() / 'iOSPrintServer'
    return app_root()


def ensure_dir(*parts: str | Path) -> Path:
    path = Path(parts[0])
    for p in parts[1:]:
        path /= p
    path.mkdir(parents=True, exist_ok=True)
    return path

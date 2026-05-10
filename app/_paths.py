"""路径工具：兼容开发模式（__file__）和 PyInstaller frozen 模式（sys.executable.parent）

分层：
  app_root()       — exe 所在目录（只读程序文件）
  data_root()      — 只读内置文件（静态文件等）
  config_dir()     — 用户配置（漫游），%APPDATA%/iOSPrintServer
  persistent_dir() — 可写数据（本机），%LOCALAPPDATA%/iOSPrintServer
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
    """返回只读内置文件目录（静态文件等）

    frozen 模式：exe 所在目录（资源由安装器放置在同级目录）
    dev 模式：app_root()
    """
    if getattr(sys, 'frozen', False) or getattr(sys, '__compiled__', False):
        return app_root()
    return app_root()


def config_dir() -> Path:
    """用户配置目录（漫游），存储 config.json

    frozen 模式：%%APPDATA%%/iOSPrintServer
    dev 模式：app_root()（与项目文件放在一起）
    """
    if getattr(sys, 'frozen', False) or getattr(sys, '__compiled__', False):
        appdata = os.environ.get('APPDATA')
        if appdata:
            return Path(appdata) / 'iOSPrintServer'
        return Path.home() / 'iOSPrintServer'
    return app_root()


def persistent_dir() -> Path:
    """可写数据目录（本机），存储 DB/日志/上传文件

    frozen 模式：%%LOCALAPPDATA%%/iOSPrintServer
    dev 模式：app_root()（与项目文件放在一起）
    """
    if getattr(sys, 'frozen', False) or getattr(sys, '__compiled__', False):
        local = os.environ.get('LOCALAPPDATA')
        if local:
            return Path(local) / 'iOSPrintServer'
        return Path.home() / 'iOSPrintServer'
    return app_root()


def ensure_dir(*parts: str | Path) -> Path:
    path = Path(parts[0])
    for p in parts[1:]:
        path /= p
    path.mkdir(parents=True, exist_ok=True)
    return path

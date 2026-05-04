"""路径工具：兼容开发模式（__file__）和 PyInstaller 打包模式（sys._MEIPASS）"""
import os
import sys


def app_root() -> str:
    """返回项目根目录（开发模式或打包模式）"""
    if getattr(sys, 'frozen', False) or getattr(sys, '__compiled__', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def data_root() -> str:
    """返回内置数据文件目录（模板/静态文件等只读资源）"""
    if getattr(sys, 'frozen', False) or getattr(sys, '__compiled__', False):
        if hasattr(sys, '_MEIPASS'):
            return sys._MEIPASS
        return os.path.dirname(sys.executable)
    return app_root()


def ensure_dir(*parts: str) -> str:
    path = os.path.join(*parts)
    os.makedirs(path, exist_ok=True)
    return path

"""路径工具：兼容开发模式（__file__）和 PyInstaller 打包模式（sys._MEIPASS）"""
import os
import sys


def app_root():
    """返回项目根目录（开发模式或打包模式）"""
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包：exe 所在目录
        return os.path.dirname(sys.executable)
    # 开发模式：项目根目录（print_server/）
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def data_root():
    """返回内置数据文件目录（模板/静态文件等只读资源）"""
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return app_root()


def ensure_dir(*parts):
    path = os.path.join(*parts)
    os.makedirs(path, exist_ok=True)
    return path

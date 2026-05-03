"""控制台模式入口（用于 PyInstaller 打包）"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from console import main
main()

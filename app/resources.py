"""按需释放内嵌资源 — 从 PyInstaller 包体内提取到可写目录

打包时将 certs/nssm 等文件通过 --add-data 内嵌到 _internal/resources/，
首次启动时释放到 app_root()/resources/，防止用户误删，也方便更新覆盖。
"""
import os
import sys
import shutil
from pathlib import Path
from loguru import logger


def _bundled_dir() -> str | None:
    """返回打包时内嵌的资源目录（sys._MEIPASS/resources/），
    开发模式返回 None。"""
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        d = os.path.join(sys._MEIPASS, 'resources')
        return d if os.path.isdir(d) else None
    return None


def _target_dir() -> str:
    """资源释放目标目录 — app_root()/resources/"""
    from app._paths import app_root
    d = os.path.join(app_root(), 'resources')
    os.makedirs(d, exist_ok=True)
    return d


def _is_bundled(name: str) -> bool:
    src = _bundled_dir()
    if not src:
        return False
    return os.path.isfile(os.path.join(src, name))


def ensure_resources() -> None:
    """释放所有内嵌资源到可写目录（同名文件已存在时跳过）"""
    src = _bundled_dir()
    if not src:
        return

    dst = _target_dir()
    released = 0
    for entry in os.listdir(src):
        s = os.path.join(src, entry)
        d = os.path.join(dst, entry)
        if os.path.isfile(s) and not os.path.isfile(d):
            shutil.copy2(s, d)
            released += 1
        elif os.path.isdir(s):
            # 子目录（如 certs/）逐文件复制
            os.makedirs(d, exist_ok=True)
            for sub in os.listdir(s):
                ss = os.path.join(s, sub)
                sd = os.path.join(d, sub)
                if os.path.isfile(ss) and not os.path.isfile(sd):
                    shutil.copy2(ss, sd)
                    released += 1

    if released:
        logger.debug(f'已释放 {released} 个内嵌资源到 {dst}')

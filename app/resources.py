"""按需释放内嵌资源 — 从 PyInstaller 包体内提取到可写目录

打包时将 certs/nssm 等文件通过 --add-data 内嵌到 _internal/resources/，
首次启动时释放到 app_root()/resources/，防止用户误删，也方便更新覆盖。
"""

import os
import shutil
import sys
from pathlib import Path

from loguru import logger


def _bundled_dir() -> Path | None:
    """返回打包时内嵌的资源目录（sys._MEIPASS/resources/），
    开发模式返回 None。"""
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        d = Path(sys._MEIPASS) / 'resources'
        return d if d.is_dir() else None
    return None


def _target_dir() -> Path:
    """资源释放目标目录 — persistent_dir()/resources/"""
    from app._paths import persistent_dir

    d = persistent_dir() / 'resources'
    d.mkdir(parents=True, exist_ok=True)
    return d


def _is_bundled(name: str) -> bool:
    src = _bundled_dir()
    if not src:
        return False
    return (src / name).is_file()


def ensure_resources() -> None:
    """释放所有内嵌资源到可写目录

    策略：写入 VERSION 标记文件，版本不同时覆盖所有资源。
    这样 exe 升级后资源自动更新，日常启动无需重复复制。
    """
    src = _bundled_dir()
    if not src:
        return

    dst = _target_dir()
    tag_file = dst / '.resources_version'

    # 读取当前 bundle 的版本标记
    bundled_tag = ''
    tag_src = src / 'version.txt'
    if tag_src.is_file():
        bundled_tag = tag_src.read_text(encoding='utf-8').strip()

    # 读取已释放的版本标记
    released_tag = ''
    if tag_file.is_file():
        released_tag = tag_file.read_text(encoding='utf-8').strip()

    if bundled_tag and bundled_tag == released_tag:
        return  # 版本一致，无需更新

    # 版本不同或首次释放：覆盖所有资源
    released = 0
    for entry in os.listdir(str(src)):
        s = src / entry
        d = dst / entry
        if s.is_file():
            shutil.copy2(str(s), str(d))
            released += 1
        elif s.is_dir():
            d.mkdir(parents=True, exist_ok=True)
            for sub in os.listdir(str(s)):
                ss = s / sub
                sd = d / sub
                if ss.is_file():
                    shutil.copy2(str(ss), str(sd))
                    released += 1

    # 写入版本标记
    if bundled_tag:
        tag_file.write_text(bundled_tag, encoding='utf-8')

    if released:
        logger.debug(f'已释放 {released} 个内嵌资源到 {dst}')

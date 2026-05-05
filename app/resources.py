"""按需释放内嵌资源 — 从 PyInstaller 包体内提取到可写目录

打包时将 certs/nssm 等文件通过 --add-data 内嵌到 _internal/resources/，
首次启动时释放到 app_root()/resources/，防止用户误删，也方便更新覆盖。
"""

import os
import shutil
import sys

from loguru import logger


def _bundled_dir() -> str | None:
    """返回打包时内嵌的资源目录（sys._MEIPASS/resources/），
    开发模式返回 None。"""
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        d = os.path.join(sys._MEIPASS, 'resources')
        return d if os.path.isdir(d) else None
    return None


def _target_dir() -> str:
    """资源释放目标目录 — persistent_dir()/resources/"""
    from app._paths import persistent_dir

    d = os.path.join(persistent_dir(), 'resources')
    os.makedirs(d, exist_ok=True)
    return d


def _is_bundled(name: str) -> bool:
    src = _bundled_dir()
    if not src:
        return False
    return os.path.isfile(os.path.join(src, name))


def ensure_resources() -> None:
    """释放所有内嵌资源到可写目录

    策略：写入 VERSION 标记文件，版本不同时覆盖所有资源。
    这样 exe 升级后资源自动更新，日常启动无需重复复制。
    """
    src = _bundled_dir()
    if not src:
        return

    dst = _target_dir()
    tag_file = os.path.join(dst, '.resources_version')

    # 读取当前 bundle 的版本标记
    bundled_tag = ''
    tag_src = os.path.join(src, 'version.txt')
    if os.path.isfile(tag_src):
        bundled_tag = open(tag_src, encoding='utf-8').read().strip()

    # 读取已释放的版本标记
    released_tag = ''
    if os.path.isfile(tag_file):
        released_tag = open(tag_file, encoding='utf-8').read().strip()

    if bundled_tag and bundled_tag == released_tag:
        return  # 版本一致，无需更新

    # 版本不同或首次释放：覆盖所有资源
    released = 0
    for entry in os.listdir(src):
        s = os.path.join(src, entry)
        d = os.path.join(dst, entry)
        if os.path.isfile(s):
            shutil.copy2(s, d)
            released += 1
        elif os.path.isdir(s):
            os.makedirs(d, exist_ok=True)
            for sub in os.listdir(s):
                ss = os.path.join(s, sub)
                sd = os.path.join(d, sub)
                if os.path.isfile(ss):
                    shutil.copy2(ss, sd)
                    released += 1

    # 写入版本标记
    if bundled_tag:
        with open(tag_file, 'w', encoding='utf-8') as f:
            f.write(bundled_tag)

    if released:
        logger.debug(f'已释放 {released} 个内嵌资源到 {dst}')

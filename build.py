#!/usr/bin/env python3
"""构建脚本 — PyInstaller 打包为 Windows 独立可执行文件"""
import os
import sys
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from app.version import __version__


def get_commit_count() -> int:
    try:
        r = subprocess.run(
            ['git', 'rev-list', '--count', 'HEAD'],
            capture_output=True, text=True, timeout=5,
            cwd=ROOT,
        )
        return int(r.stdout.strip()) if r.returncode == 0 else 0
    except (OSError, ValueError):
        return 0


def clean_build():
    for d in ['build', 'dist']:
        shutil.rmtree(ROOT / d, ignore_errors=True)
    for spec in ROOT.glob('*.spec'):
        spec.unlink(missing_ok=True)
    print('✓ 清理完成')


def run_pyinstaller():
    version = str(__version__).replace('-', '.')
    build_ver = f'{version}.{get_commit_count()}' if get_commit_count() else version

    opts = [
        sys.executable, '-m', 'PyInstaller',
        '--onedir',
        '--name', 'iOSPrintServer',
        '--console',
        f'--file-version={build_ver}',
        f'--product-version={version}',
        '--product-name=iOSPrintServer',
        '--company-name=iOSPrintServer',
        # 数据文件
        '--add-data', f'app/templates{os.pathsep}app/templates',
        '--add-data', f'app/static{os.pathsep}app/static',
        '--add-data', f'certs{os.pathsep}certs',
        '--add-data', f'config.json{os.pathsep}.',
        # 隐式导入
        '--hidden-import=win32ui',
        '--hidden-import=win32print',
        '--hidden-import=win32gui',
        '--hidden-import=win32com.client',
        '--hidden-import=pythoncom',
        '--hidden-import=PIL',
        '--hidden-import=PIL.ImageWin',
        '--hidden-import=PIL.ImageDraw',
        '--hidden-import=uvicorn',
        '--hidden-import=uvicorn.logging',
        '--hidden-import=uvicorn.loops',
        '--hidden-import=uvicorn.protocols',
        '--hidden-import=uvicorn.protocols.http',
        '--hidden-import=uvicorn.protocols.websockets',
        '--hidden-import=textual',
        '--hidden-import=loguru',
        '--hidden-import=httpx',
        '--hidden-import=multipart',
        '--hidden-import=sqlite3',
        '--hidden-import=concurrent.futures',
        '--hidden-import=queue',
        '--hidden-import=ctypes',
        '--hidden-import=win32api',
        '--hidden-import=logging.handlers',
        # 排除
        '--exclude-module=tkinter',
        '--exclude-module=matplotlib',
        '--exclude-module=scipy',
        '--exclude-module=numpy',
        # 入口
        'console_app.py',
    ]

    print(f'🔨 构建版本: {build_ver}')
    print(f'   PyInstaller 打包中...')
    sys.stdout.flush()

    r = subprocess.run(opts, capture_output=False)
    return r.returncode


def main():
    import argparse
    parser = argparse.ArgumentParser(description='iOSPrintServer 构建脚本')
    parser.add_argument('--clean', action='store_true', help='清理构建产物')
    args = parser.parse_args()

    if args.clean:
        clean_build()
        return

    clean_build()
    code = run_pyinstaller()
    if code == 0:
        print(f'\n✅ 构建成功 (v{__version__})')
        print(f'   输出目录: dist/')
    else:
        print(f'\n❌ 构建失败 (exit={code})')
        sys.exit(code)


if __name__ == '__main__':
    main()

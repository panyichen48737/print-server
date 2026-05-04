# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

sys.setrecursionlimit(5000)

root = Path('.').resolve()

a = Analysis(
    ['console_app.py'],
    pathex=[str(root)],
    binaries=[
        (str(root / 'bin' / 'nssm.exe'), '.'),
    ],
    datas=[
        (str(root / 'app' / 'templates'), 'app/templates'),
        (str(root / 'app' / 'static'), 'app/static'),
        (str(root / 'config.json'), '.'),
        (str(root / 'certs' / 'cert.pem'), 'certs'),
        (str(root / 'certs' / 'key.pem'), 'certs'),
        (str(root / 'app' / 'server_daemon.py'), 'app'),
    ],
    hiddenimports=[
        'win32ui', 'win32print', 'win32gui', 'win32com.client',
        'pythoncom',
        'PIL', 'PIL.ImageWin', 'PIL.ImageDraw',
        'rich', 'rich.layout', 'rich.live', 'rich.panel',
        'rich.table', 'rich.text',
        'fastapi',
        'uvicorn',
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.lifespan',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.websockets',
        'loguru',
        'multipart',
        'httpx',
        'pydantic',
        'concurrent.futures',
        'queue',
        'sqlite3',
        'msvcrt',
        'ctypes',
        'win32api',
        'app.config', 'app.routes.api', 'app.routes.admin',
        'app.printing.job_queue', 'app.printing.worker_pool', 'app.printing.engine',
        'app.services.dingtalk',
        'app._paths',
        'console.conflicts', 'console.daemon_manager', 'console.autostart', 'console.log_handler', 'console.tui',
        'logging.handlers',
        'http.client',
        'email.mime.multipart', 'email.mime.text',
        'app.services.printer_monitor',
        'app.services.bark',
        'app.services.log_broadcaster',
        'app.services.sse_broadcaster',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'scipy',
        'numpy',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='iOSPrintServer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_tracker=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='iOSPrintServer',
)

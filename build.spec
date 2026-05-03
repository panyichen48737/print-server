# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

sys.setrecursionlimit(5000)

root = Path('.').resolve()

a = Analysis(
    ['console_app.py'],
    pathex=[str(root)],
    binaries=[],
    datas=[
        (str(root / 'app' / 'templates'), 'app/templates'),
        (str(root / 'app' / 'static'), 'app/static'),
        (str(root / 'config.json'), '.'),
        (str(root / 'certs' / 'cert.pem'), 'certs'),
        (str(root / 'certs' / 'key.pem'), 'certs'),
        (str(root / 'server_daemon.py'), '.'),
    ],
    hiddenimports=[
        'win32ui', 'win32print', 'win32gui', 'win32com.client',
        'pythoncom',
        'fitz',
        'PIL', 'PIL.ImageWin', 'PIL.ImageDraw',
        'pillow_heif',
        'rich', 'rich.layout', 'rich.live', 'rich.panel',
        'rich.table', 'rich.text',
        'flask',
        'requests',
        'pydantic',
        'concurrent.futures',
        'queue',
        'sqlite3',
        'msvcrt',
        'ctypes',
        'win32api',
        'app.config', 'app.routes.api', 'app.routes.admin',
        'app.services.queue_manager', 'app.services.print_engine',
        'app.services.dingtalk',
        'app._paths',
        'console.conflicts', 'console.daemon_manager', 'console.autostart', 'console.log_handler', 'console.tui',
        'logging.handlers',
        'http.client',
        'email.mime.multipart', 'email.mime.text',
        'flask_socketio',
        'eventlet',
        'app.services.printer_monitor',
        'app.services.bark',
        'app.services.log_broadcaster',
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

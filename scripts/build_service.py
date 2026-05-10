"""编译 Go update_service.exe"""
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SERVICE_DIR = PROJECT_ROOT / 'service'
OUTPUT_DIR = PROJECT_ROOT / 'dist' / 'iOSPrintServer'


def build_service():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / 'update_service.exe'

    # Ensure upx is absent (we don't want it anyway for a 2MB binary)
    # Ensure go.sum is up to date
    result = subprocess.run(
        ['go', 'mod', 'tidy'],
        cwd=SERVICE_DIR,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        print(f'[build_service] go mod tidy 失败:')
        print(result.stderr)
        sys.exit(1)

    args = [
        'go', 'build',
        '-mod=mod',
        '-ldflags', '-s -w',  # strip debug info
        '-o', str(out),
        '.',
    ]

    print(f'[build_service] 编译 update_service.exe...')
    result = subprocess.run(
        args,
        cwd=SERVICE_DIR,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        print(f'[build_service] 编译失败:')
        print(result.stderr)
        sys.exit(1)

    size_kb = out.stat().st_size / 1024
    print(f'[build_service] 完成: {out.name} ({size_kb:.1f} KB)')


if __name__ == '__main__':
    build_service()

"""构建脚本 — 使用 PyInstaller 打包 iOS 云打印服务器

用法:
    python scripts/build.py                  # 构建 dev 版本
    python scripts/build.py --release        # 构建发布版本（读取 git tag）
    python scripts/build.py --clean          # 清理构建产物

环境变量:
    RELEASE_VERSION=v1.0.0   # 发布版本号（可跳过 git tag）
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = PROJECT_ROOT / 'dist'
BUILD_DIR = PROJECT_ROOT / 'build'
APP_NAME = 'iOSPrintServer'


def get_version() -> str:
    env_ver = os.environ.get('RELEASE_VERSION')
    if env_ver:
        return env_ver.lstrip('v')
    try:
        desc = subprocess.run(
            ['git', 'describe', '--tags', '--always', '--dirty'],
            capture_output=True,
            text=True,
            timeout=2,
            cwd=PROJECT_ROOT,
        )
        if desc.returncode == 0 and desc.stdout.strip():
            return desc.stdout.strip().lstrip('v')
    except (OSError, subprocess.TimeoutExpired):
        pass
    return '0.0.0-dev'


def clean():
    for d in [DIST_DIR, BUILD_DIR]:
        if d.exists():
            shutil.rmtree(d)
    for spec in PROJECT_ROOT.glob('*.spec'):
        spec.unlink(missing_ok=True)
    print('[clean] 已清理构建产物')


def _run(cmd, **kwargs):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=5, **kwargs)
    except Exception:
        return None


def _generate_version_manifest(version: str, res_dir: Path, env: dict):
    manifest = {
        'app_version': version,
        'build_date': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'build_tools': {},
        'pip_packages': {},
        'github': {},
    }

    r = _run([sys.executable, '--version'])
    if r and r.returncode == 0:
        manifest['build_tools']['python'] = r.stdout.strip()

    try:
        from importlib.metadata import version as pkg_ver

        manifest['build_tools']['pyinstaller'] = pkg_ver('pyinstaller')
    except Exception:
        pass

    r = _run(['uv', '--version'])
    if r and r.returncode == 0:
        manifest['build_tools']['uv'] = r.stdout.strip()

    r = _run(['uv', 'pip', 'list', '--format=json'], env=env)
    if r and r.returncode == 0:
        try:
            for pkg in json.loads(r.stdout):
                manifest['pip_packages'][pkg['name']] = pkg['version']
        except Exception:
            pass

    # GitHub CI metadata
    manifest['github']['run_id'] = os.environ.get('GITHUB_RUN_ID', '')
    manifest['github']['repo'] = os.environ.get('GITHUB_REPOSITORY', '')
    manifest['github']['server_url'] = os.environ.get('GITHUB_SERVER_URL', 'https://github.com')

    # Git commit (full SHA for links)
    r = _run(['git', 'rev-parse', 'HEAD'], cwd=PROJECT_ROOT)
    if r and r.returncode == 0:
        manifest['commit_sha'] = r.stdout.strip()
    else:
        r = _run(['git', 'rev-parse', '--short', 'HEAD'], cwd=PROJECT_ROOT)
        if r and r.returncode == 0:
            manifest['commit_sha'] = r.stdout.strip()

    scalar_js = PROJECT_ROOT / 'app' / 'static' / 'scalar.standalone.min.js'
    if scalar_js.exists():
        manifest['scalar_js_size_kb'] = round(scalar_js.stat().st_size / 1024)

    (res_dir / 'version_info.json').write_text(json.dumps(manifest, indent=2))
    print(f'[build] 版本清单已生成 ({len(manifest["pip_packages"])} 个包)')


def build(version: str):
    print(f'[build] 版本: {version}')

    # 设置环境变量供 app/version.py 读取
    env = os.environ.copy()
    env['RELEASE_VERSION'] = f'v{version}'

    # 将运行时需要的资源文件集中到 build_resources/，供 --add-data 内嵌
    res_dir = BUILD_DIR / 'resources'
    res_dir.mkdir(parents=True, exist_ok=True)
    # version.txt — 运行时显示版本号
    (res_dir / 'version.txt').write_text(f'{version}\n')
    # version_info.json — 构建环境版本清单
    _generate_version_manifest(version, res_dir, env)
    # CHANGELOG.md — 管理后台/用户可查阅更新历史
    changelog = PROJECT_ROOT / 'CHANGELOG.md'
    if changelog.exists():
        shutil.copy2(changelog, res_dir / 'CHANGELOG.md')

    # PyInstaller 参数（--onedir：目录模式，资源文件与 exe 同级放一起，由安装器放置）
    args = [
        sys.executable,
        '-m',
        'PyInstaller',
        '--noconfirm',
        '--name',
        APP_NAME,
        '--windowed',
        '--onedir',
        '--icon',
        str(PROJECT_ROOT / 'gui' / 'resources' / 'icon.ico'),
    ]

    # ── 自动收集应用包 ──
    args += [
        '--collect-all',
        'app',
        '--collect-all',
        'gui',
        '--collect-all',
        'launcher',
        '--collect-all',
        'fastapi',
        '--collect-all',
        'starlette',
        '--collect-all',
        'uvicorn',
        '--collect-all',
        'pydantic_settings',
        '--collect-all',
        'jinja2',
    ]

    # ── pywin32 COM 模块（动态加载，必须显式指定）──
    args += [
        '--hidden-import',
        'win32ui',
        '--hidden-import',
        'win32print',
        '--hidden-import',
        'win32gui',
        '--hidden-import',
        'win32com.client',
        '--hidden-import',
        'pythoncom',
    ]

    # ── 第三方库自动收集 ──
    args += [
        '--collect-all',
        'pydantic',
        '--collect-all',
        'loguru',
    ]

    # ── PySide6：排除未使用的超大模块 ──
    pyside6_excludes = [
        'PySide6.Qt3DCore', 'PySide6.Qt3DRender', 'PySide6.Qt3DInput',
        'PySide6.Qt3DLogic', 'PySide6.Qt3DAnimation', 'PySide6.Qt3DExtras',
        'PySide6.QtQuick', 'PySide6.QtQuick3D', 'PySide6.QtQuickWidgets',
        'PySide6.QtQml', 'PySide6.QtQmlModels',
        'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtWebChannel',
        'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets',
        'PySide6.QtBluetooth', 'PySide6.QtNfc',
        'PySide6.QtCharts', 'PySide6.QtDataVisualization',
        'PySide6.QtSpatialAudio',
        'PySide6.QtPositioning', 'PySide6.QtSensors',
        'PySide6.QtHelp', 'PySide6.QtDesigner', 'PySide6.QtUiTools',
        'PySide6.QtTest', 'PySide6.QtXml',
        'PySide6.Qt3DGeometry',
    ]
    for mod in pyside6_excludes:
        args += ['--exclude-module', mod]
    args += ['--collect-all', 'PySide6']

    # ── 排除不需要的库 ──
    args += [
        '--exclude-module',
        'flet',
        '--exclude-module',
        'tkinter',
        '--exclude-module',
        'matplotlib',
        '--exclude-module',
        'scipy',
        '--exclude-module',
        'numpy',
        '--exclude-module',
        'setuptools',
        '--exclude-module',
        'pip',
    ]

    # 入口
    args.append(str(PROJECT_ROOT / 'gui_main.py'))

    subprocess.run(args, cwd=PROJECT_ROOT, check=True, env=env)

    # 构建后：复制资源文件到 dist/ 目录，与 exe 同级放置
    dist_dir = DIST_DIR / APP_NAME
    if dist_dir.is_dir():
        # 复制 build/resources/（version.txt, version_info.json）
        if res_dir.exists():
            dst = dist_dir / 'resources'
            dst.mkdir(parents=True, exist_ok=True)
            for entry in os.listdir(str(res_dir)):
                s = res_dir / entry
                d = dst / entry
                if s.is_file():
                    shutil.copy2(str(s), str(d))
                elif s.is_dir():
                    shutil.copytree(str(s), str(d), dirs_exist_ok=True)
            print(f'[build] 资源已复制到 {dst}')

        # 复制 gui/resources/（QSS + 图标）
        gui_res_src = PROJECT_ROOT / 'gui' / 'resources'
        if gui_res_src.is_dir():
            gui_res_dst = dist_dir / 'gui' / 'resources'
            shutil.copytree(str(gui_res_src), str(gui_res_dst), dirs_exist_ok=True)
            print(f'[build] GUI 资源已复制到 {gui_res_dst}')

        # 复制 app/static/（Scalar JS，供 frozen 模式使用，目录不存在则跳过）
        static_src = PROJECT_ROOT / 'app' / 'static'
        if static_src.is_dir():
            static_dst = dist_dir / 'app' / 'static'
            shutil.copytree(str(static_src), str(static_dst), dirs_exist_ok=True)
            print(f'[build] 静态文件已复制到 {static_dst}')

        # 复制 certs/（SSL 证书，供 frozen 模式使用）
        certs_src = PROJECT_ROOT / 'certs'
        if certs_src.is_dir():
            certs_dst = dist_dir / 'certs'
            shutil.copytree(str(certs_src), str(certs_dst), dirs_exist_ok=True)
            print(f'[build] 证书已复制到 {certs_dst}')

        # 复制 PySide6 翻译文件（中文右键菜单等）
        try:
            from PySide6.QtCore import QLibraryInfo

            qm_src = Path(QLibraryInfo.path(QLibraryInfo.TranslationsPath))
            qm_dst = dist_dir / 'translations'
            if qm_src.exists():
                qm_dst.mkdir(parents=True, exist_ok=True)
                for qm_file in qm_src.glob('*.qm'):
                    if 'zh_' in qm_file.stem:
                        shutil.copy2(str(qm_file), str(qm_dst / qm_file.name))
                qm_count = len(list(qm_dst.glob('*.qm')))
                print(f'[build] 翻译文件已复制到 {qm_dst} ({qm_count} 个)')
        except Exception as e:
            print(f'[build] 翻译文件复制失败: {e}')

    exe_path = dist_dir / f'{APP_NAME}.exe'
    if exe_path.exists():
        print(f'[build] 构建完成: {exe_path} ({exe_path.stat().st_size / 1024 / 1024:.1f} MB)')
        print(f'[build] 版本: {version}')

        # 构建 update.zip（完整增量更新：_internal/ + exe + 资源文件）
        update_zip = DIST_DIR / f'update-{version}.zip'
        if dist_dir.is_dir():
            import zipfile

            # 要打包的文件模式：排除缓存和日志
            skip_prefixes = {'__pycache__', '.git'}
            with zipfile.ZipFile(update_zip, 'w', zipfile.ZIP_BZIP2) as zf:
                for entry in dist_dir.rglob('*'):
                    if not entry.is_file():
                        continue
                    if any(p in entry.parts for p in skip_prefixes):
                        continue
                    arcname = entry.relative_to(dist_dir)
                    zf.write(entry, arcname)
            print(
                f'[build] 更新包: {update_zip} ({update_zip.stat().st_size / 1024 / 1024:.1f} MB) | {len([e for e in dist_dir.rglob("*") if e.is_file()])} 个文件'
            )
        else:
            print('[build] 警告: dist_dir 不存在，跳过 update.zip')
    else:
        print(f'[build] 构建失败: {exe_path} 未生成')


def main():
    parser = argparse.ArgumentParser(description='构建 iOS 云打印服务器')
    parser.add_argument('--release', action='store_true', help='发布模式（读取 git tag）')
    parser.add_argument('--clean', action='store_true', help='清理构建产物')
    args = parser.parse_args()

    if args.clean:
        clean()
        return

    version = get_version()
    if args.release and version == '0.0.0-dev':
        print('[build] 错误: 发布模式需要 git tag (如 v1.0.0) 或 RELEASE_VERSION 环境变量')
        sys.exit(1)

    # 默认保留 build/ 缓存以加速；传递 --clean 可清理
    build(version)


if __name__ == '__main__':
    main()

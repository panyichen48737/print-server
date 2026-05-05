"""构建脚本 — 使用 PyInstaller 打包 iOS 云打印服务器

用法:
    python scripts/build.py                  # 构建 dev 版本
    python scripts/build.py --release        # 构建发布版本（读取 git tag）
    python scripts/build.py --clean          # 清理构建产物

环境变量:
    RELEASE_VERSION=v1.0.0   # 发布版本号（可跳过 git tag）
"""
import os
import sys
import shutil
import subprocess
import argparse
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
            capture_output=True, text=True, timeout=2,
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
    # CHANGELOG.md — 管理后台/用户可查阅更新历史
    changelog = PROJECT_ROOT / 'CHANGELOG.md'
    if changelog.exists():
        shutil.copy2(changelog, res_dir / 'CHANGELOG.md')
    # SSL 证书（如存在）— 内嵌后按需释放到数据目录
    cert_dir = PROJECT_ROOT / 'certs'
    cert_has_both = (cert_dir / 'cert.pem').exists() and (cert_dir / 'key.pem').exists()
    if cert_has_both:
        shutil.copytree(cert_dir, res_dir / 'certs', dirs_exist_ok=True)
        print(f'[build] 已包含 SSL 证书')
    elif cert_dir.exists():
        print(f'[build] 警告: certs/ 目录存在但缺少 cert.pem 或 key.pem，跳过证书打包')

    # PyInstaller 参数（--onefile：所有内容打包进单一 exe，启动时解压到 %TEMP%）
    args = [
        sys.executable, '-m', 'PyInstaller',
        '--noconfirm',
        '--name', APP_NAME,
        '--console',
        '--onefile',
        # Data 文件（--add-data 资源嵌入 exe，运行时由 MEIPASS 访问）
        '--add-data', f'{PROJECT_ROOT / "app" / "templates"}{os.pathsep}app/templates',
        '--add-data', f'{PROJECT_ROOT / "app" / "static"}{os.pathsep}app/static',
        # 内嵌资源（嵌入 exe，运行时由 MEIPASS 访问，通过 app/resources.py 按需释放）
        '--add-data', f'{res_dir}{os.pathsep}resources',
    ]

    args += [
        '--hidden-import', 'win32ui',
        '--hidden-import', 'win32print',
        '--hidden-import', 'win32gui',
        '--hidden-import', 'win32com.client',
        '--hidden-import', 'pythoncom',
        '--hidden-import', 'python_multipart',
        # 隐式导入 — HTTP/ASGI
        '--hidden-import', 'uvicorn.logging',
        '--hidden-import', 'uvicorn.loops',
        '--hidden-import', 'uvicorn.lifespan',
        '--hidden-import', 'uvicorn.protocols.http',
        '--hidden-import', 'uvicorn.protocols.websockets',
        # 隐式导入 — 文档解析
        '--hidden-import', 'PIL.ImageWin',
        '--hidden-import', 'PIL.ImageDraw',
        '--hidden-import', 'http.client',
        '--hidden-import', 'email.mime.multipart',
        '--hidden-import', 'email.mime.text',
        # 隐式导入 — 应用模块
        '--hidden-import', 'app.config',
        '--hidden-import', 'app.routes.api',
        '--hidden-import', 'app.routes.admin',
        '--hidden-import', 'app.routes.ws',
        '--hidden-import', 'app.services.dingtalk',
        '--hidden-import', 'app.services.bark',
        '--hidden-import', 'app.services.sse_broadcaster',
        '--hidden-import', 'app.services.printer_monitor',
        '--hidden-import', 'app.services.log_broadcaster',
        '--hidden-import', 'app.printing.job_queue',
        '--hidden-import', 'app.printing.worker_pool',
        '--hidden-import', 'app.printing.engine',
        '--hidden-import', 'app.printing.backends',
        # 排除不需要的库（减小体积）
        '--exclude-module', 'tkinter',
        '--exclude-module', 'matplotlib',
        '--exclude-module', 'scipy',
        '--exclude-module', 'numpy',
        '--exclude-module', 'setuptools',
        '--exclude-module', 'pip',
        # 入口
        str(PROJECT_ROOT / 'console_app.py'),
    ]

    subprocess.run(args, cwd=PROJECT_ROOT, check=True, env=env)

    dist_app_dir = DIST_DIR / APP_NAME
    if dist_app_dir.exists():
        print(f'[build] 构建完成: {dist_app_dir}')
        print(f'[build] 版本: {version}')
    else:
        print(f'[build] 构建失败: dist 目录未生成')


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

    # --release 模式保留 build/ 目录以利用缓存
    if not args.release:
        clean()
    build(version)


if __name__ == '__main__':
    main()

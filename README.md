# iOSPrintServer

Windows 打印服务器，提供 REST API 和 Web 管理面板。支持从 iOS 设备（通过 [Scriptable](https://scriptable.app/)）或其他客户端提交打印任务，在 Windows 连接的网络/本地打印机上输出。

## 功能

- **REST API** — 从 iOS 或任何 HTTP 客户端提交、查询、取消打印任务
- **Web 管理面板** — 上传文件、管理打印机、查看任务记录、配置服务器
- **多格式支持** — PDF、Word (.doc/.docx)、Excel (.xls/.xlsx)、PowerPoint (.ppt/.pptx)、图片（JPG, PNG, BMP, GIF, WebP, TIFF, HEIC）
- **实时推送** — Server-Sent Events (SSE) 实时推送任务状态和打印机状态
- **通知渠道** — 支持 [钉钉](https://www.dingtalk.com/) 机器人 和 [Bark](https://github.com/Finb/Bark) 推送通知
- **图片增强** — 可选集成 [夸克扫描王 API](https://scan.quark.cn/) 进行图片预处理
- **TUI 控制台** — 终端界面管理后台守护进程（启动/停止/重启/开机自启）
- **Windows 服务** — 可通过 NSSM 注册为 Windows 服务，无人值守运行
- **PyInstaller 打包** — 可打包为单个可分发 EXE

## 快速开始

### 环境要求

- Windows（需要 win32print / COM 打印支持）
- Python 3.10+
- [Microsoft Edge](https://www.microsoft.com/edge) 或 [Google Chrome](https://www.google.com/chrome)（PDF 打印需要）
- Microsoft Office（Word/Excel/PowerPoint 打印需要）

### 安装

```bash
git clone https://github.com/your-username/print-server.git
cd print-server
pip install -r requirements.txt
```

### 启动

```bash
# 启动 TUI 控制台（推荐）
python console_app.py

# 或直接启动后台守护进程
python -m app.server_daemon
```

默认监听 `http://localhost:5000`。

## 配置

编辑 `config.json` 或通过 Web 面板 → 设置页面修改。

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `api_key` | `print-server-key-2026` | API 认证密钥 |
| `port` | `5000` | 服务端口 |
| `default_printer` | `""` | 默认打印机名称（空=系统默认） |
| `default_copies` | `1` | 默认打印份数 |
| `default_duplex` | `false` | 双面打印 |
| `default_color` | `true` | 彩色打印 |
| `paper_size` | `A4` | 纸张大小：`A4`, `A3`, `Letter` |
| `print_dpi` | `300` | 图片打印分辨率 |
| `max_file_size_mb` | `50` | 文件大小上限 |
| `allowed_extensions` | (见配置文件) | 支持的文件类型 |
| `worker_count` | `2` | 并发工作线程数 |
| `auto_retry_count` | `0` | 失败自动重试次数 |
| `job_timeout` | `300` | 打印超时时间（秒） |
| `job_retention_days` | `30` | 任务记录保留天数 |
| `notify_channel` | `disabled` | 通知渠道：`disabled`, `dingtalk`, `bark` |
| `quark_api_key_id` | `""` | 夸克 API Key ID（可选） |
| `quark_api_key` | `""` | 夸克 API Secret（可选） |

## API

所有 API 请求需携带 `Authorization: Bearer <api_key>` 请求头（打印机列表和 SSE 端点除外）。

### 提交打印任务

```bash
curl -X POST http://localhost:5000/api/print \
  -H "Authorization: Bearer print-server-key-2026" \
  -F "file=@document.pdf" \
  -F "printer=HP LaserJet" \
  -F "copies=2" \
  -F "duplex=1"
```

| 参数 | 类型 | 说明 |
|---|---|---|
| `file` | file | **必填.** 要打印的文件 |
| `printer` | string | 目标打印机名称 |
| `copies` | int | 份数 (1-99) |
| `duplex` | int | `1` 双面, `0` 单面 |
| `color` | int | `1` 彩色, `0` 黑白 |
| `paper_size` | string | `A4`, `A3`, `Letter` |

### 查询任务状态

```bash
curl http://localhost:5000/api/status/<job_id>
```

返回：`{"success": true, "status": "queued|printing|completed|failed", "job_id": "..."}`

### 获取打印机列表

```bash
curl http://localhost:5000/api/printers
```

### 取消任务

```bash
curl -X POST http://localhost:5000/api/cancel/<job_id> \
  -H "Authorization: Bearer print-server-key-2026"
```

### SSE 实时事件

```bash
curl -N http://localhost:5000/api/events
```

事件类型：`job_status`（任务状态变化）、`printer_status`（打印机状态变化）。

## Web 管理面板

浏览器打开 `http://localhost:5000/admin/`

- **工作台** — 打印统计概览和最近任务
- **上传** — 选择文件设置打印参数后上传
- **历史** — 浏览和搜索历史打印任务
- **设置** — 配置所有服务器选项
- **打印机** — 查看已连接打印机及状态

## iOS 集成

使用 [Scriptable](https://scriptable.app/) 应用。脚本位于 `scripts/ios_scriptable.js`：

1. 将脚本复制到 iPhone
2. 在脚本中设置 `SERVER_URL` 和 `API_KEY`
3. 通过分享菜单将文件发送到打印服务器

## TUI 控制台命令

```bash
python console_app.py              # 启动 TUI（自动启动后台服务）
python console_app.py --start      # 仅启动后台服务（无界面）
python console_app.py --stop       # 停止后台服务
python console_app.py --restart    # 重启后台服务
python console_app.py --status     # 查看后台服务状态
```

### TUI 快捷键

| 按键 | 功能 |
|---|---|
| `S` | 启动服务 |
| `T` | 停止服务 |
| `R` | 重启服务 |
| `U` | 开关开机自启 |
| `Q` | 退出 |

## Windows 服务

```bash
# 安装为 Windows 服务（需管理员权限）
nssm install iOSPrintServer "C:\path\to\dist\iOSPrintServer\iOSPrintServer.exe"

# 或在 TUI 中按 U 键注册开机自启
```

## PyInstaller 打包

```bash
pip install pyinstaller
pyinstaller build.spec
```

输出目录：`dist/iOSPrintServer/`

## 项目结构

```
print_server/
├── app/
│   ├── __init__.py           # Flask 应用工厂
│   ├── _paths.py             # 路径解析（开发/打包）
│   ├── auth.py               # Bearer Token 认证
│   ├── bootstrap.py          # 服务装配
│   ├── config.py             # Pydantic 配置管理
│   ├── server_daemon.py      # 守护进程入口
│   ├── upload_helper.py      # 文件上传处理
│   ├── printing/
│   │   ├── backends/         # 打印后端策略模式
│   │   │   ├── base.py       # PrinterBackend 抽象基类
│   │   │   ├── office.py     # Word/Excel/PPT (win32com)
│   │   │   ├── pdf.py        # PDF (Chromium headless)
│   │   │   └── image.py      # 图片 (PIL + GDI)
│   │   ├── engine.py         # 打印调度层
│   │   ├── enhancer.py       # 夸克 API 图片增强
│   │   ├── job_queue.py      # 任务队列
│   │   └── repository.py     # SQLite 持久化
│   ├── routes/
│   │   ├── api.py            # REST API 路由
│   │   └── admin.py          # Web 面板路由
│   ├── services/
│   │   ├── notifier.py       # 错误格式化 + 通知抽象
│   │   ├── dingtalk.py       # 钉钉 Webhook 通知
│   │   ├── bark.py           # Bark 推送通知
│   │   ├── sse_broadcaster.py # 发布/订阅 + 本地监听
│   │   ├── print_service.py  # 打印服务层
│   │   ├── log_broadcaster.py # 日志实时推送
│   │   ├── printer_monitor.py # 打印机状态轮询
│   │   └── sse_broadcaster.py # 发布/订阅
│   └── templates/            # Jinja2 模板
├── console/
│   ├── __init__.py           # CLI 入口 (Typer)
│   ├── _server.py            # ServerHandle 单进程 uvicorn
│   ├── autostart.py          # Windows 开机自启
│   └── __main__.py           # python -m console 入口
├── build.spec                # PyInstaller 配置
├── scripts/
│   └── ios_scriptable.js     # iOS Scriptable 集成脚本
└── config.json               # 默认配置
```

## 协议

MIT

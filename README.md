# iOSPrintServer

Windows 打印服务器，提供 REST API 和 PySide6 桌面 GUI。支持从 iOS 设备（通过 [Scriptable](https://scriptable.app/)）或其他客户端提交打印任务，在 Windows 连接的网络/本地打印机上输出。

## 功能

- **桌面 GUI** — PySide6 桌面控制台（系统托盘、实时状态、任务管理）
- **REST API** — 从 iOS 或任何 HTTP 客户端提交、查询、取消打印任务
- **Web 管理面板** — 上传文件、管理打印机、查看任务记录、配置服务器
- **多格式支持** — PDF、Word (.doc/.docx)、Excel (.xls/.xlsx)、PowerPoint (.ppt/.pptx)、图片（JPG, PNG, BMP, GIF, WebP, TIFF, HEIC）
- **实时推送** — WebSocket + SSE 实时推送任务状态和打印机状态
- **通知渠道** — 支持钉钉机器人和 Bark 推送通知
- **图片增强** — 可选集成夸克扫描王 API 进行图片预处理
- **自动更新** — 后台服务每 6 小时检查 GitHub Releases，静默下载增量更新
- **PyInstaller 打包** — 打包为单目录分发，NSIS 安装程序

## 快速开始

### 环境要求

- Windows（需要 win32print / COM 打印支持）
- Python 3.10+
- Microsoft Office（Word/Excel/PowerPoint 打印需要）

### 安装

```bash
git clone https://github.com/panyichen48737/print-server.git
cd print-server
pip install -r requirements.txt
```

### 启动

```bash
python gui_main.py
```

默认监听 `http://localhost:5000`。

## 配置

通过 GUI 设置页面或 Web 管理面板修改。配置存储在 `%APPDATA%/iOSPrintServer/config.json`。

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `port` | `5000` | 服务端口 |
| `ssl_enabled` | `true` | 启用 HTTPS |
| `api_key` | `print-server-key-2026` | API 认证密钥 |
| `default_printer` | `""` | 默认打印机名称（空=系统默认） |
| `default_copies` | `1` | 默认打印份数 |
| `default_duplex` | `false` | 双面打印 |
| `default_color` | `true` | 彩色打印 |
| `paper_size` | `A4` | 纸张大小 |
| `worker_count` | `2` | 并发工作线程数 |
| `job_retention_days` | `30` | 任务记录保留天数 |
| `notify_channel` | `disabled` | 通知渠道：`disabled`, `dingtalk`, `bark` |

## API

所有 API 请求需携带 `Authorization: Bearer <api_key>` 请求头。

### 提交打印任务

```bash
curl -X POST http://localhost:5000/api/print \
  -H "Authorization: Bearer print-server-key-2026" \
  -F "file=@document.pdf" \
  -F "printer=HP LaserJet" \
  -F "copies=2"
```

### 查询任务状态

```bash
curl http://localhost:5000/api/status/<job_id>
```

### 获取打印机列表

```bash
curl http://localhost:5000/api/printers
```

## Web 管理面板

浏览器打开 `http://localhost:5000/admin/`。提供打印统计概览、文件上传、任务历史、设置管理。

## iOS 集成

使用 [Scriptable](https://scriptable.app/) 应用。脚本位于 `scripts/ios_scriptable.js`：

1. 将脚本复制到 iPhone
2. 设置 `SERVER_URL` 和 `API_KEY`
3. 通过分享菜单将文件发送到打印服务器

## 项目结构

```
app/                    # FastAPI 后端
  ├── printing/         # 打印引擎、任务队列、后端
  ├── routes/           # API 和管理面板路由
  └── services/         # SSE、通知、打印机监控
gui/                    # PySide6 桌面 GUI
  ├── pages/            # 各功能页面
  ├── components/       # 可复用组件
  └── resources/        # QSS 主题、图标
launcher/               # 启动入口（单进程 GUI + 服务器）
service/                # Go 更新服务（Windows 服务）
scripts/                # 构建脚本、iOS Scriptable 脚本
```

## 打包

```bash
python scripts/build.py --release
```

输出目录：`dist/iOSPrintServer/`

## 协议

MIT
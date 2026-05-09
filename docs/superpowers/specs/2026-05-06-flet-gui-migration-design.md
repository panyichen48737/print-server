# Flet 桌面 GUI 迁移设计规格

## 概述

将 iOS 云打印服务器从 Web 后台（FastAPI + Jinja2 + HTMX）和 TUI 命令行（Textual）全面迁移到**现代化 Flet 桌面 GUI 应用**，同时保留已有的 `--headless` 后端模式和服务层代码。

## 架构

### C2 方案：单 exe + 子进程

```
iOSPrintServer.exe (Flet GUI 主进程)
  ├── 系统托盘 / 窗口管理
  │   - 关闭窗口 → 隐藏到托盘，服务器继续运行
  │   - 右键菜单：显示/隐藏/退出
  ├── HTTP keep-alive localhost 通信
  │   - httpx.AsyncClient 连接池复用
  │   - JSON 响应、MsgPack 可选优化
  ├── 7 页面 Flet Material 3 GUI
  └── 子进程生命周期管理
      - 启动时检测端口 5000 是否有进程
      - 无 → 拉起 iOSPrintServer.exe --headless 子进程
      - 每 10s /api/health 健康检查
      - 异常 → 自动重启子进程（最多 3 次，间隔 5s）
      - 退出 → taskkill 子进程 + 自身退出

    ───────────────── 进程边界 ─────────────────

iOSPrintServer.exe --headless (子进程)
  ├── Config / Bootstrap / uvicorn
  ├── JobQueue / WorkerPool / PrintEngine
  ├── PrinterMonitor / Heartbeat
  ├── EventBus + SSEBroadcaster
  └── FastAPI Routes (API)
```

### 双向守护

GUI 崩溃 → 子进程孤儿化，继续运行 → 下次 GUI 启动自动检测并连接。

子进程崩溃 → GUI 健康检查失败 → 自动重启子进程（5 秒间隔，最多 3 次，失败则弹出错误提示）。

### 端口检测

- 启动时：TCP `_port_listening()` 检测 `127.0.0.1:5000` 是否有进程
- 运行时：HTTP `GET /api/health` 检测服务健康（timeout 3s）
- 超时自动继承现有 `ServerHandle` 启动逻辑

---

## 设计原则与交互规范

### 设计系统原则

- **品牌一致性** — Flet Material 3 主题集中管理色值/字体/圆角/间距，所有页面统一引用主题 token，不使用硬编码色值
- **组件状态完备** — 每个交互组件定义完整状态集，不遗漏边缘状态
- **反装饰冗余** — 避免无意义的视觉元素（紫渐变、装饰性图标、圆角卡片+左 border accent），每个元素必须承载信息
- **一个细节做到 120%** — 仪表盘趋势图和打印机状态卡片做精致呈现，其他页面保持干净功能优先
- **信息密度匹配场景** — 监控类页面（仪表盘/任务管理）数据密度高，设置/关于页面保持简洁留白

### 交互设计规范

基于 interaction-design 框架：

**响应时间阈值：**
- 0–100ms：按钮点击反馈、开关切换 — 瞬时视觉响应
- 100ms–1s：页面加载、列表刷新 — 显示 spinner
- 1s–10s：文件上传、打印提交 — 确定进度条 + 取消按钮
- >10s：后台处理（如打印队列等待）— 允许后台进行，完成后通知

**反馈机制：**
- 每个操作必须有即时视觉确认
- 错误状态 = 颜色 + 图标 + 文字说明，不能仅靠颜色区分
- 成功操作显示 transient snackbar（3s 自动消失）
- 破坏性操作（取消任务/退出）需二次确认对话框

**Affordance：**
- 拖拽操作：拖入时边框高亮 + 背景色变化 + 光标变化
- 可点击元素：悬停时有视觉反馈（色变/阴影）
- 禁用控件：透明度降低 + 明确的禁用原因 tooltip

---

## 组件状态设计

### 按钮（Flet ElevatedButton / FilledButton）

| 状态 | 触发条件 | 视觉表现 |
|------|---------|---------|
| 默认 | 初始未交互 | 主题色填充 |
| 悬停 | 鼠标悬停 | 亮度变化 + 阴影 |
| 聚焦 | 键盘/程序聚焦 | 外发光轮廓 |
| 激活 | 正在点击 | 微下沉 + 色值加深 |
| 加载 | 操作进行中 | 按钮内 spinner + 文字变"保存中..." |
| 禁用 | 输入不完整/操作不可用 | 降低透明度 |
| 成功 | 操作完成 | 短暂绿色闪烁 + checkmark（1.5s 恢复） |
| 错误 | 操作失败 | 红色闪烁 + 错误图标（附 tooltip 说明原因）|

### 文本框（Flet TextField）

| 状态 | 表现 |
|------|------|
| 默认 | 标准边框 + label |
| 聚焦 | 主题色下划线 + 光标 |
| 已填写 | 正常显示输入值 |
| 验证中 | 右侧 loading 微图标 |
| 验证通过 | 绿色 checkmark（可选） |
| 验证失败 | 红色边框 + 行内错误文字 |
| 禁用 | 灰色背景 + 半透明 |

### 开关（Flet Switch）

- 开/关状态过渡动画 150ms ease-out
- 禁用状态降低透明度 + 不可交互

### 表格行（Flet DataTable Row）

| 状态 | 表现 |
|------|------|
| 默认 | 隔行变色 |
| 悬停 | 行背景高亮 |
| 选中 | 主题色淡底 + checkbox 选中 |
| 加载中 | 行内 shimmer 动画（骨架屏）|
| 空 | "暂无数据"居中提示 + 操作按钮 |

---

## 页面状态设计

每个页面统一设计三种非正常状态，避免空白页和未处理错误。

### 1. 📊 仪表盘

| 状态 | 表现 |
|------|------|
| 空 | 首次运行无统计数据 → 显示"尚无打印任务" + 快速打印引导按钮 |
| 加载 | 所有卡片显示 skeleton 骨架屏（灰块脉冲动画，Flet `ShaderMask` 或简化灰块）|
| 错误 | 服务器连接失败 → 顶部红色横幅"服务器连接失败，正在重试..." + 手动重试按钮 |
| 实时更新 | 每 3s 轮询刷新，不显示全屏加载，卡片内容单独更新 |

### 2. 🖨️ 快速打印

| 状态 | 表现 |
|------|------|
| 空 | 无选中文件 → 大号虚线拖拽区 + "拖拽文件到此处或点击选择" |
| 加载 | 文件上传中 → 确定进度条 + 取消按钮 |
| 错误 | 文件格式不支持 / 打印失败 → 红色提示 + 原因说明 + 重选文件 |

### 3. 📋 任务管理

| 状态 | 表现 |
|------|------|
| 空（队列） | "队列为空，提交打印任务后将在此显示" |
| 空（历史筛选）| "没有匹配的任务" + 清除筛选按钮 |
| 加载 | 表格 skeleton 行（5 行脉冲动画）|
| 错误 | "加载失败" + 重试按钮 |

### 4. 📝 实时日志

| 状态 | 表现 |
|------|------|
| 空 | "暂无日志，打印任务时将自动显示" |
| 加载（历史）| 顶部提示"正在加载历史日志..." |
| 暂停 | 滚动区顶部显示蓝色标签"已暂停" + 新日志计数 |

### 5. ⚙️ 设置

| 状态 | 表现 |
|------|------|
| 加载 | 表单骨架屏（灰块替代所有控件，缓慢脉冲）|
| 保存成功 | 底部 snackbar "设置已保存"（3s 自动消失）|
| 需重启 | 保存后弹出确认对话框"部分设置需要重启服务器生效，是否立即重启？" |
| 验证错误 | 行内红色提示（端口范围/数字范围/必填项）|

### 6. 🔌 打印机管理

| 状态 | 表现 |
|------|------|
| 空 | "未检测到打印机" + 刷新按钮 + 说明文字"请确保打印机已连接并开启" |
| 加载 | 卡片 skeleton（3 个灰块）|
| 错误 | "获取打印机状态失败" + 重试按钮 |

### 7. ℹ️ 关于

| 状态 | 表现 |
|------|------|
| 检查更新中 | "正在检查更新..." + spinner |
| 检查失败 | "检查更新失败，请稍后重试" + 重试按钮 |
| 已是最新 | "已是最新版本 (v{version})" + 绿色 checkmark |
| 有新版本 | "新版本 v{new_version} 可用" + 下载按钮 |

---

## 主题系统

### 深色/亮色切换

- 使用 Flet `theme_mode` 控制（`ThemeMode.SYSTEM` / `LIGHT` / `DARK`）
- 默认跟随系统主题
- 设置页提供下拉选择：亮色 / 深色 / 跟随系统
- 偏好持久化到 `config.json` 新增 `theme_mode` 字段

### 设计 Token

| Token | 亮色值 | 深色值 | 用途 |
|-------|--------|--------|------|
| `surface` | `#FFFFFF` | `#1E1E2E` | 页面背景 / 卡片底色 |
| `primary` | `#4F46E5` | `#818CF8` | 主按钮 / 激活态 / 链接 |
| `primary_container` | `#EEF2FF` | `#312E81` | 选中行 / 标签底色 |
| `error` | `#DC2626` | `#F87171` | 错误文字 / 错误边框 |
| `on_surface` | `#1F2937` | `#E2E8F0` | 主要文字 |
| `on_surface_variant` | `#6B7280` | `#94A3B8` | 次要文字 / 占位符 |
| `outline` | `#D1D5DB` | `#4B5563` | 边框 / 分割线 |
| `success` | `#16A34A` | `#4ADE80` | 成功状态 |

### 深色模式适配要点

- 打印机状态卡片：状态色（绿/黄/红）在深色模式下饱和度适当降低，避免刺眼
- 日志颜色：深色模式下日志级别颜色亮度提高（INFO 浅蓝、WARNING 浅黄、ERROR 浅红）
- 图表：LineChart 在深色模式下网格线和坐标轴颜色变暗

---

## 微交互设计

| 交互 | 触发 | 规则 | 反馈 |
|------|------|------|------|
| 按钮点击 | 鼠标按下 → 松开 | 提交操作 | 100ms 内状态切换 → spinner → 结果(success/error) |
| 开关切换 | 点击 | flip boolean | 150ms 滑块动画 + 色值过渡 |
| 文件拖拽 | 文件进入拖拽区 | 验证文件类型 | 边框色变主题色 + 背景淡色 |
| 文件拖出 | 文件离开拖拽区 | — | 恢复默认边框和背景 |
| 页面切换 | NavigationRail 点击 | 切换页面路由 | 200ms 内容区淡入 |
| 通知弹窗 | SSE 事件触发 | 3s 自动消失 + 可手动关 | 从右下角滑入 + 类型色标示 |
| 表单保存 | 点击保存按钮 | 验证 → 提交 | 按钮 → spinner → "已保存" snackbar |
| 表格行悬停 | 鼠标进入行区域 | — | 行背景色变浅 |

---

## 键盘快捷键

| 快捷键 | 动作 |
|--------|------|
| `Ctrl+1` ~ `Ctrl+7` | 切换到第 1-7 页 |
| `Ctrl+P` | 快速打印页 |
| `Ctrl+F` | 聚焦搜索/筛选框 |
| `Ctrl+R` | 刷新当前页面 |
| `Escape` | 关闭弹窗 / 取消选择 |
| `F5` | 刷新当前页面数据 |

---

## 窗口状态持久化

- 窗口大小、位置在退出时保存到 `%APPDATA%/iOSPrintServer/window_state.json`
- 启动时恢复上次窗口位置和大小
- 记住最后活跃页面，启动时直接打开
- 表格列排序偏好持久化（每页独立保存）

---

## 页面设计

### 1. 📊 仪表盘

数据源：
- `/api/health` — 服务器运行状态 + 队列大小
- `job_repo.get_stats()` — 6 个统计指标
- `/api/printers/status` — 打印机实时状态
- `job_repo.get_jobs(limit=10)` — 最近 10 条任务

布局：
```
顶部服务器状态条（运行中 / 端口 / SSL / 自启 / 停止/重启按钮）
6 张统计卡片（排队中 / 打印中 / 今日完成 / 今日失败 / 成功率 / 总计）
近 7 天打印趋势图 (LineChart)
左：打印机状态卡片列表    右：最近 10 条任务列表
```

状态设计：空 → 引导按钮 | 加载 → 6 skeleton 卡片 | 错误 → 红色横幅

实时更新：`job_status` 事件刷新统计卡片和任务列表，`printer_status` 事件刷新打印机卡片。

### 2. 🖨️ 快速打印

数据源：
- `/api/printers` — 打印机下拉列表
- `config` — 默认值

布局：
```
文件拖拽区（Flet DragTarget + 文件对话框）
已选文件预览（文件名、大小、类型图标）
打印参数面板：
  打印机（下拉）、份数（数字）、双面（开关）、
  颜色（开关）、纸张大小（下拉 A4/Letter/A3）
[开始打印] 按钮 → 任务状态侧边栏
```

状态设计：空 → 拖拽引导区 | 加载 → 上传进度条 | 错误 → 红色行内提示

实现：文件读取后 `POST /api/print` 提交，响应中包含 `job_id` 后订阅 `job_status` 事件跟踪进度。

### 3. 📋 任务管理

数据源：
- `GET /api/status/{job_id}` — 单个任务
- `job_repo.get_jobs(status, search, limit=20, offset)` — 分页查询
- `POST /api/cancel/{job_id}` — 取消
- `POST /api/retry/{job_id}` — 重试
- `job_repo.count_jobs(status, search)` — 总数统计

布局：
```
┌─ 打印队列 ──────────────────────────┐
│ 正在打印卡片（进度条）               │
│ 排队等待列表                        │
└─────────────────────────────────────┘
┌─ 历史记录 ──────────────────────────┐
│ 筛选栏：状态下拉 + 搜索框 + 日期范围 │
│ 表格：ID / 文件名 / 类型 / 大小 /    │
│       状态 / 提交时间 / 完成时间 / 操作│
│ 批量操作：批量取消 / 批量重试        │
│ 分页控件                            │
└─────────────────────────────────────┘
```

状态设计：空队列 → 引导文字 | 空筛选 → 清除按钮 | 加载 → 5行 skeleton | 错误 → 重试按钮

实时更新：`job_status` 事件更新队列状态 + 高亮变化行。

### 4. 📝 实时日志

数据源：
- `GET /admin/api/logs?lines=200` — 初始加载历史日志
- SSE event type `log` — 实时流式追加

布局：
```
级别筛选（ALL/ERROR/WARNING/INFO/DEBUG）+ 搜索框
暂停/继续、清空、自动滚动开关、打开日志文件夹
日志列表（带颜色编码级别、时间戳、消息）
底部：复制全部日志按钮
```

状态设计：空 → 引导文字 | 暂停 → 蓝色标签+计数 | 加载历史 → 顶部提示

### 5. ⚙️ 设置

数据源：`config` 实例直读（也可通过 `GET /api/config` 获取全部字段），直调 `config.set_many()` + `config.save()`。

布局（7 个分组卡片）：

| 分组 | 字段 | 控件 |
|------|------|------|
| 安全 | `api_key` | 密码输入 + [生成] 按钮 |
| 打印默认值 | `default_printer` | 下拉（列表来自 PrinterMonitor） |
| | `default_copies` | 数字 1-99 |
| | `default_duplex` | 开关 |
| | `default_color` | 开关 |
| | `paper_size` | 下拉 A4/Letter/A3 |
| | `excel_print_all_sheets` | 开关 |
| | `ppt_output_type` | 下拉 slides/handout2/3/6 |
| | `auto_retry_count` | 数字 0-10 |
| 夸克扫描王 API | `quark_api_key_id` | 密码输入框（已配置时显示桥接文字） |
| | `quark_api_key` | 密码输入框 |
| 通知渠道 | `notify_channel` | 下拉 disabled/dingtalk/bark |
| | `dingtalk_webhook` | 密码输入框（条件显示） |
| | `dingtalk_level` | 下拉 error/warning/info |
| | `bark_key` | 密码输入框（条件显示） |
| | `bark_server` | 文本输入 |
| 服务器 | `port` | 数字 1024-65535 |
| | `log_level` | 下拉 DEBUG/INFO/WARNING/ERROR |
| | `ssl_enabled` | 开关 |
| Worker | `worker_count` | 数字 1-16 |
| | `max_file_size_mb` | 数字 1-500 |
| | `job_retention_days` | 数字 1-365 |
| | `print_dpi` | 数字 72-1200 |
| | `job_timeout` | 数字 30-3600 |
| | `word_timeout` | 数字 30-600 |

状态设计：加载 → 表单骨架屏 | 保存成功 → snackbar | 需重启 → 确认对话框

[保存设置] + [测试通知] + 重启提示。

### 6. 🔌 打印机管理

数据源：
- `/api/printers` — 打印机名称列表
- `/api/printers/status` — 实时状态
- `POST /api/set_default_printer` — 设为默认

布局：
```
[刷新状态] 按钮
打印机卡片网格：
  🖨️ 打印机名称（整体状态色标示）
     状态标签（就绪/缺纸/离线/打印中/错误等）
     详细信息（纸张、已打印数）
     设为默认按钮 / 默认标签
底部：说明文字
```

状态设计：空 → "未检测到打印机" + 刷新 | 加载 → 3 skeleton 卡片 | 错误 → 重试按钮

实时更新：`printer_status` 事件更新卡片状态。

### 7. ℹ️ 关于

```
应用图标 + 名称：iOS 云打印服务器
版本：{__version__}
构建时间：{BUILD_DATE}
Python 版本
PyInstaller 版本

[检查更新] [日志文件夹] [配置文件]
版权信息
```

状态设计：检查更新 → spinner → 结果（最新/有新版本/失败）

---

## 实时事件系统

| 事件类型 | 数据格式 | 推送方式 | 消费页面 |
|---------|---------|---------|---------|
| `job_status` | `{job_id, filename, status, source, error?, ts}` | SSE/WS | 仪表盘、任务管理、快速打印 |
| `printer_status` | `{name, overall, statuses: [{key, label}]}` | SSE/WS | 仪表盘、打印机管理 |
| `log` | `{message}` | SSE/WS | 实时日志 |

Flet 通过 `httpx.AsyncClient` 连接 SSE `/api/events`，在后台线程解析事件流，通过线程安全回调更新 UI。

---

## 设计技能应用场景

### huashu-design（花叔Design）

**应用阶段**：GUI 页面视觉设计、交互原型验证、设计变体探索

| 场景 | 具体应用 |
|------|---------|
| 主题系统定义 | 使用设计 Token 体系（色值/字型/间距/圆角）统一管理 Flet Material 3 主题，所有页面引用 token 而非硬编码。遵循"品牌一致性"原则确保 GUI 与原有 Web 后台视觉风格衔接 |
| 反 AI slop 自检 | 贯穿所有页面：避免装饰性元素（无信息量的图标/渐变/边框 accent），不为填空而编造数据，仪表盘卡片数据真实，空状态显示诚实引导文字 |
| 页面视觉层级 | 仪表盘和打印机卡片做到"一个细节 120%"（精致状态指示色和趋势图），设置页和关于页保持简洁留白，信息密度匹配场景 |
| 设计变体 | 关键页面（仪表盘布局/任务管理表格）若存在多种排列方式，通过 iterations 快速对比后选定最优方案 |
| 核心资产协议 | 应用图标、品牌色值集中管理，Logo 和品牌标识从现有项目资源提取，不使用 CSS 剪影/SVG 手画代替 |

### interaction-design（交互设计）

**应用阶段**：组件交互行为定义、反馈机制设计、状态覆盖审查

| 场景 | 具体应用 |
|------|---------|
| 响应时间 4 级阈值 | 按钮点击（<100ms 即时视觉切换）、页面加载（100ms-1s spinner）、文件上传（1-10s 确定进度条+取消）、后台打印（>10s 完成后通知）— 每级对应不同的 UI 反馈 |
| 组件 10 状态完整覆盖 | 按钮/文本框/开关/表格行的 9-10 种状态在实现阶段逐项审查，不遗漏 focus/loading/disabled/error/empty 等非主路径状态 |
| 反馈机制一致性 | 每个操作必有即时视觉确认；错误用 颜色+图标+文字；成功用 transient snackbar（3s）；破坏性操作需二次确认 |
| 微交互 | 文件拖拽的 affordance（拖入时边框高亮+背景+光标变化），按钮点击的 100ms 状态切换，开关 150ms 滑块动画 |
| Affordance | 可点击元素悬停有视觉反馈、禁用控件降低透明度+tooltip 说明原因、拖拽区域视觉引导 |
| 交互审查清单 | Phase 1 完成后按 IxD 审查清单检查所有交互组件是否达到标准 |

### frontend-design（前端设计）

**应用阶段**：GUI 布局结构、响应式适配、代码组织

| 场景 | 具体应用 |
|------|---------|
| NavigationRail 主导航 | 左侧固定导航栏 + 右侧内容区的标准桌面布局，7 个页面通过 NavigationRail 切换 |
| 布局响应式 | 窗口缩放时仪表盘卡片自动重排（2→1 列）、任务管理表格列自适应宽度（隐藏次要列或水平滚动）|
| 代码组织 | GUI 代码按页面/组件/服务三层组织，每个页面独立文件，公共组件（状态卡片/确认对话框/骨架屏）提取复用 |
| 空/加载/错误状态 | 每个页面明确实现三态 UI，不依赖 Flet 默认行为 |

### ui-ux-pro-max（UI/UX 设计）

**应用阶段**：用户体验流程优化、设计系统建设、品牌一致性

| 场景 | 具体应用 |
|------|---------|
| 用户流程设计 | 7 个页面的用户任务流分析：快速打印（选文件→配参数→提交→跟踪进度）、设置（修改→验证→保存→生效），确保最小操作路径 |
| 设计系统 | Flet Material 3 主题配置作为设计系统基础，所有自定义组件（状态卡片/骨架屏/通知弹窗）保持视觉一致性 |
| 品牌一致性 | 颜色/字体/圆角/间距统一管理，所有页面使用一致的设计语言，与原有 Web 后台保持视觉衔接 |
| 可用性优化 | 高频操作（打印提交/任务筛选/设置保存）路径最短，批量操作（批量取消/重试）减少重复点击 |

### 五个技能的分工协作

```
huashu-design       interaction-design     frontend-design      ui-ux-pro-max
  ┌──────────┐       ┌──────────┐           ┌──────────┐         ┌──────────┐
  │ 视觉品质  │       │ 交互行为  │           │ 布局结构  │         │ 用户体验 │
  │ - Token  │       │ - 状态集  │           │ - 导航    │         │ - 流程   │
  │ - 反slop  │       │ - 反馈    │           │ - 响应式  │         │ - 系统   │
  │ - 细节    │       │ - 微交互  │           │ - 代码组织 │         │ - 品牌   │
  └──────────┘       └──────────┘           └──────────┘         └──────────┘
                            │                      │
                            └──────────┬───────────┘
                                       ▼
                              design 🎨 (ckm:design)
                         品牌/设计系统/UI Styling
```

核心工作流：**ui-ux-pro-max** 定义用户流程和设计系统 → **frontend-design** 规划布局结构 → **huashu-design** 把控视觉品质和细节 → **interaction-design** 定义交互行为和状态覆盖 → **design** 在实现阶段统一协调品牌一致性和 UI 样式。

---

## 保留的现有功能

- **TUI 功能全保留**：服务器启动/停止/重启、状态监控、实时日志、自启管理——全部在 GUI 中有对应页面
- **已有控制台命令**：`--headless`、`--start`、`--stop`、`--status`、`--restart`、`--autostart-install`、`--autostart-uninstall` 全部保留
- **Single instance**：PID 文件机制保留（`console.pid`）
- **HTTPS / SSL**：证书检测 + HTTP→HTTPS 重定向保留
- **ServerHandle**：`--headless` 子进程使用现有 `ServerHandle` 启动

## 删除的 Web 后台代码

- `app/templates/admin/` — 所有 Jinja2 模板（7 个 HTML 文件 + base.html）
- `app/templates/helpers/` — 模板辅助函数
- 移除 admin 路由注册（`app/routes/admin.py` 中的模板端点）
- 移除静态文件服务（CSS/JS 资源）
- 保留 `app/routes/api.py`（iOS 客户端依赖）和 `app/routes/ws.py`

注意：如果迁移后 Web 后台不再需要，HTMX + Alpine.js 的静态资源也可以移除。

---

## 安装部署

### NSIS 安装器

1. PyInstaller 构建 `iOSPrintServer.exe`（onefile + console）
2. NSIS 打包为 `iOSPrintServer-Setup-{version}.exe`
3. 安装流程：
   - 选择安装目录（默认 `%LOCALAPPDATA%\iOSPrintServer`）
   - 创建开始菜单快捷方式
   - 可选桌面快捷方式
   - 注册表开机自启（指向 GUI exe）
   - 可选「安装后立即运行」

### 自更新

GUI 内置更新检查：`GET https://api.github.com/repos/{owner}/{repo}/releases/latest`

```
对比版本号
  ├── 一致 → 忽略
  └── 新版本 → 提示用户
       ├── 确认 → 下载新 exe 到 temp/
       ├── 停止子进程
       ├── bat 替换自身 exe（延迟删除）
       └── 重启 GUI → 自动拉起新版子进程
```

### 卸载

- NSIS 卸载器移除开始菜单、桌面快捷方式、自启注册表项
- 保留 `%APPDATA%/iOSPrintServer/`（配置/日志/数据库/证书）

---

## 后端现代化（Phase 2 — 与 Phase 1 GUI 并行或紧随其后）

### P0 — 高价值、低风险

#### 1. aiosqlite — 异步数据库访问

**现状**: `JobRepository` 用 `sqlite3` + `threading.Lock` + `check_same_thread=False`，5 处锁竞争，与 FastAPI 异步路由不匹配。

**目标**: 替换为 `aiosqlite`，数据库操作全部变为 `async`。

改动范围:
- `app/printing/repository.py` — 核心，全部方法改为 `async` + `await`
- `app/printing/job_queue.py` — `add_job()`, `cancel_job()`, `retry_job()`, `get_jobs()`, `count_jobs()`, `cleanup_old_jobs()`, `recover_stuck_jobs()` 改为 async
- `app/printing/worker.py` — `JobExecutor.execute()` 涉及数据库 update 改为 async
- `app/routes/api.py` — 数据库查询路由改为 async await
- `app/routes/admin.py` — 同上
- `app/services/heartbeat.py` — cleanup + recover 改为 async

**价值**: 消除锁竞争风险，减少线程切换开销，与 asyncio 事件循环自然融合。

#### 2. mypy strict — 全项目类型注解

**现状**: `pyproject.toml` 中 `strict_optional = true` 但未启用 strict 模式，大量 `Any` 标注和缺失返回值类型。

**目标**: 启用 `strict = true`，全项目类型注解补齐。

配置变更:
```toml
[tool.mypy]
python_version = "3.10"
strict = true
warn_unused_ignores = true
warn_return_any = true
warn_unreachable = true
ignore_missing_imports = true
files = ["app/", "console/"]
```

推进策略:
- 从 `schemas.py` / `exceptions.py` / `_paths.py` 开始（零成本，纯类型安全）
- 其次 `bootstrap.py` / `config.py`（消除 `Any` 泛型）
- 最后 service 层（`printer_monitor.py`, `sse_broadcaster.py` 等）

**价值**: 显式类型减少运行时 bug，IDE 智能提示提升开发速度，契约式编程。

#### 3. Alembic 迁移 — 替代手写 migrate_db()

**现状**: `repository.py` 中手写 `migrate_db()` 通过 `PRAGMA table_info` + `ALTER TABLE` 逐个检查列是否存在。每次加新列都要改代码。

**目标**: Alembic 管理数据库 Schema 迁移。

```
alembic init alembic
alembic revision --autogenerate -m "initial schema"
# 后续加字段:
alembic revision --autogenerate -m "add paper_size column"
alembic upgrade head
```

改动:
- `alembic/` 目录 + `alembic.ini` 配置
- `pyproject.toml` 添加 `alembic` 依赖
- `migrate_db()` 保留兼容旧数据库，迁移后逐步废弃

**价值**: Schema 变更可追溯、可回滚、可审计。多人协作不会遗漏迁移步骤。

#### 4. Typer CLI — 替换 argparse

**现状**: `console/__init__.py` 用 `argparse` 手写参数解析。无自动补全、无子命令、无参数校验。

**目标**: Typer（基于 Click 的类型安全 CLI 框架），子命令结构。

```python
app = typer.Typer()

@app.command()
def headless():
    """无界面运行服务器"""
    ...

@app.command()
def stop():
    """停止服务器"""
    ...

@app.command()
def status():
    """查看服务器状态"""
    ...
```

改动范围:
- `console/__init__.py` 的 `main()` 重构为 Typer app
- `pyproject.toml` 添加 `typer` 依赖
- `[project.scripts]` 入口点更新

**价值**: 自动 `--help` 输出、bash/zsh 自动补全、输入校验、类型安全、子命令组。

#### 5. 健康检查增强

**现状**: `/api/health` 仅返回 `{"status": "ok", "queue_size": N}`，信息不足。

**目标**: 扩展返回字段，为 GUI 仪表盘提供更丰富数据。

```json
{
  "status": "ok",
  "version": "1.5.0",
  "uptime": 3600,
  "queue_size": 3,
  "workers": {"active": 1, "idle": 1, "total": 2},
  "db_size_mb": 2.4
}
```

改动范围:
- `app/routes/api.py` — `/api/health` 路由扩展
- 新增 `_get_uptime()` 和 `_get_db_size()` 辅助函数

**价值**: GUI 仪表盘可直接展示版本/运行时间/Worker 负载，无需额外 API 调用。

#### 6. 信号处理与优雅关闭

**现状**: `--headless` 模式没有注册信号处理器，taskkill 强制终止可能丢失数据。

**目标**: 注册 `SIGINT`/`SIGTERM` 处理器，确保退出前完成当前任务 + 关闭数据库。

改动范围:
- `console/__init__.py` — `ServerHandle` 增加信号注册
- `app/printing/worker.py` — 增加 `drain()` 方法等待当前任务完成

**价值**: 避免强制退出导致的任务状态不一致和数据损坏。

### P1 — 高价值、中等风险

#### 7. Pydantic request 模型 — 替换 Form() 裸参数

**现状**: `api.py` 中 `printer: str = Form(None)`, `copies: str = Form(None)` 等 5+ 个裸 `Form()` 参数，无类型校验无文档。

**目标**: 统一的 Pydantic 请求模型。

```python
class PrintRequest(BaseModel):
    file: UploadFile
    printer: str | None = None
    copies: int | None = None
    duplex: bool | None = None
    color: bool | None = None
    paper_size: str | None = None
```

改动范围:
- `app/schemas.py` 新增 `PrintRequest`, `SettingsUpdate`, `JobFilter` 等请求模型
- `app/routes/api.py` — 路由改用 `Body` + Pydantic 模型替代 `Form()`
- `app/routes/admin.py` — 同理

注意: FastAPI 不支持 `UploadFile` 直接混入 `Body` 模型，可拆为 `PrintOptions(BaseModel)` 单独接受 `Form()`。

**价值**: 统一校验、自动 OpenAPI 文档、IDE 自动补全、消除参数类型不一致（duplex 有时 str 有时 bool）。

#### 8. 启用 OpenAPI + Scalar API 文档

**现状**: `app/__init__.py` 中已配置 `title/version/description` 且有 `/scalar` 端点，但 `openapi_url` 默认启用但未在文档中提及，DX 不佳。

**目标**: 标配 `/docs`（Swagger UI）+ `/redoc` + `/scalar`。

```python
app = FastAPI(
    title='iOSPrintServer',
    version=__version__,
    description='iOS 云打印服务器 - 管理打印机、提交打印任务、监控状态',
    contact={'name': 'Developer'},
    license_info={'name': 'MIT', 'identifier': 'MIT'},
    lifespan=lifespan,
    docs_url='/docs',
    redoc_url='/redoc',
    openapi_url='/openapi.json',
)
```

**价值**: iOS Scriptable 客户端开发者可在线测试 API，减少"接口字段是啥"的沟通成本。

#### 9. msgspec — SSE/WebSocket 事件序列化

**现状**: `api.py` 中 SSE 生成器用 `json.dumps(data, ensure_ascii=False)` 每次序列化；`sse_broadcaster.py` 的 publish 使用 raw dict。

**目标**: `msgspec.json.encode()` 替代 `json.dumps()`，快 2-5 倍。

```python
import msgspec
encoder = msgspec.json.Encoder()

# SSE 生成器中
yield f'event: {event_type}\ndata: {encoder.encode(data).decode()}\n\n'
```

结构性 schema（替代 plain dict）:
```python
class SSEEvent(msgspec.Struct):
    event: str
    data: dict
```

改动范围:
- `app/routes/api.py` — SSE 生成器
- `app/routes/admin.py` — `/admin/api/logs`
- `pyproject.toml` 添加 `msgspec` 依赖

**价值**: 性能提升（事件频繁推送时明显），类型安全的 event schema，编码解码零分配。

#### 10. Pathlib 全替换 — 消除 os.path.*

**现状**: 项目源码中约 30+ 处混用 `os.path.join()` / `os.path.isfile()` / `os.path.exists()`。

**目标**: 统一为 `pathlib.Path`。

核心改动:
- `app/_paths.py` — 返回 `Path` 而非 `str`（`app_root()` / `data_root()` / `persistent_dir()`）
- `app/config.py` — `_config_path`, `_watch_loop` 等
- `app/services/upload.py` — `save_path`, `jobs_dir`
- `app/printing/repository.py` — `db_path`
- `console/__init__.py` — `_find_cert()`, `_pid_file()`
- `tests/` 中的路径操作

**价值**: 类型安全、操作符重载 `/` 拼接、更少的 import、统一的 API。

#### 11. 版本信息 API

**现状**: 关于页面需要版本信息，目前没有 API 端点，GUI 无法获取。

**目标**: 新增 `GET /api/version` 端点。

```json
{
  "version": "1.5.0",
  "build_date": "2026-05-07",
  "python_version": "3.10.11",
  "pyinstaller": "6.11.0"
}
```

改动范围:
- `app/routes/api.py` — 新增 `/api/version` 路由
- `app/__init__.py` — 注入 `BUILD_DATE` 到 app.state

**价值**: 关于页面直接展示版本信息，更新检查依赖此端点。

### P2 — 中价值

#### 12. ruff 规则集扩展

**现状**: `pyproject.toml` 中 ruff 只启用 E/F/I/N/W/UP/B/SIM/ARG/RUF 基础规则。

**目标**: 增加更多规则集：

```toml
[tool.ruff.lint]
select = [
    "E", "F", "I", "N", "W",       # 基础
    "UP",                           # pyupgrade
    "B", "SIM", "ARG", "RUF",      # 已启用
    "PERF",                         # 性能（enforce-loop, list-copy 等）
    "TCH",                          # 类型检查导入（TYPE_CHECKING 保护）
    "PYI",                          # 类型存根
    "RET",                          # return 语句规范
    "RSE",                          # 空 except 检测
    "G",                            # loguru 日志规范（% 格式化 vs 参数化）
]
```

**价值**: 自动发现性能问题、类型导入保护、日志格式化规范。`--fix` 几乎零人工干预。

#### 13. uv 开发全流程

**现状**: uv 仅用于 CI 中编译 `requirements-dev.txt`，本地仍用 pip。

**目标**: `uv sync` + `uv run` + `uv build` 开发全流程标准化。

```toml
[tool.uv]
dev-dependencies = [
    "pytest>=9", "pytest-cov>=7", "pytest-asyncio>=0.25.0",
    "httpx>=0.28", "pyinstaller>=6",
    "ruff>=0.11.0", "mypy>=1.15.0", "pre-commit>=4.2.0",
    "hypothesis>=6.130.0",
]
```

- `uv sync` — 创建虚拟环境 + 安装所有依赖 + 锁文件
- `uv lock` — 更新锁文件
- `uv run pytest` — 在虚拟环境中运行测试
- `uv build` — 构建 wheel
- 移除 `requirements-dev.txt`，改用 `uv.lock`

**价值**: 统一开发环境，uv 比 pip 快 10-100x，锁定全版本依赖。

#### 14. pytest-xdist 并行测试

**现状**: 99 个测试串行运行约 30s。

**目标**: `pytest -n auto` 并行运行，利用多核 CPU。

前置条件:
- 测试数据库隔离（每个测试用独立的 `tmp_path` 创建临时 db）
- 测试端口隔离（每个测试用唯一端口）
- `pyproject.toml` 添加 `pytest-xdist` 依赖

**价值**: 测试速度提升 2-4x，CI 反馈更快。

#### 15. httpx 连接池优化

**现状**: GUI 通过 httpx.AsyncClient 连接子进程，但没有显式配置连接池。

**目标**: 统一配置连接池参数。

```python
limits = httpx.Limits(
    max_keepalive_connections=10,
    max_connections=20,
    keepalive_expiry=30.0,
)
client = httpx.AsyncClient(limits=limits)
```

改动范围:
- GUI 模块新增 `http_client.py` 或 `_session.py` 统一管理连接

**价值**: 减少 TCP 握手开销，复用连接提升页面切换响应速度。

---

## 整体实现排期

### Phase 1: Flet GUI（桌面界面迁移）
| Step | 工作项 | 前置 |
|------|--------|------|
| 1 | 创建 Flet GUI 项目结构 | — |
| 2 | 子进程管理模块 | — |
| 3 | 仪表盘页面（含空/载/错状态 + skeleton） | — |
| 4 | 任务管理页面（含空/载/错状态 + 分页） | — |
| 5 | 快速打印页面（含拖拽/进度/错误处理） | — |
| 6 | 设置页面（含验证/保存/重启提示） | — |
| 7 | 实时日志页面（含暂停/筛选/自动滚动） | — |
| 8 | 打印机管理页面（含空/载/错状态） | — |
| 9 | 关于页面 + 更新检查 | — |
| 10 | 主题系统（深色/亮色 + 设计 token） | — |
| 11 | 微交互 + 键盘快捷键 | — |
| 12 | 窗口状态持久化 | — |
| 13 | 系统托盘 + 窗口管理 | — |
| 14 | Windows 原生通知 | — |
| 15 | PyInstaller 构建配置更新 | — |
| 16 | NSIS 安装器脚本 | — |
| 17 | 集成测试 | 全上 |
| 18 | CI/CD 更新 | — |

### Phase 2: 后端现代化（可并行或紧随其后）
| Step | 工作项 | 优先级 | 前置 |
|------|--------|--------|------|
| 19 | Typer CLI — 替换 argparse | P0 | — |
| 20 | Pathlib 全替换 | P0 | — |
| 21 | 健康检查增强 | P0 | — |
| 22 | 信号处理 + 优雅关闭 | P0 | — |
| 23 | Ruff 规则集扩展 | P2 | — |
| 24 | uv 开发全流程 | P2 | — |
| 25 | mypy strict 全面覆盖 | P0 | 20 |
| 26 | Pydantic request 模型 | P1 | 25 |
| 27 | OpenAPI + Scalar 文档 | P1 | 26 |
| 28 | 版本信息 API | P1 | — |
| 29 | aiosqlite 异步数据库 | P0 | — |
| 30 | Alembic 迁移 | P0 | 29 |
| 31 | msgspec 事件序列化 | P1 | — |
| 32 | httpx 连接池优化 | P2 | 29 |
| 33 | pytest-xdist 并行测试 | P2 | 29 |

### 否决清单
| 方案 | 否决原因 |
|------|---------|
| Docker / 容器化 | pywin32 COM 组件依赖 Windows，容器无法访问物理打印机 |
| Redis / 消息队列 | 2 worker 单机场景，SQLite 足够 |
| Rust / Go 重写 | 失去 COM 组件访问能力 |
| 依赖注入框架 (dishka) | `bootstrap.py` 模式对 6 个服务足够简洁 |
| structlog | loguru 功能完全覆盖，无替换收益 |
| FastStream / 事件驱动框架 | 没有需要事件流框架的分布式场景 |
| Websocket 替代 SSE | 当前 SSE + WS 双支持已经满足需求 |
| API 版本化 (v1) | 本地单客户端场景，版本化增加复杂度无收益 |
| Prometheus 指标 | 桌面应用不需要主动监控采集 |
| 请求速率限制 | localhost 通信不需要限流 |

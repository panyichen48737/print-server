# PySide6 桌面 GUI 迁移设计规格

## 概述

将 iOS 云打印服务器从 Flet GUI 迁移到 **PySide6 (Qt for Python)** 桌面应用，利用 Qt 原生控件提供完整的桌面体验：系统托盘、原生文件对话框、图表、全局快捷键、暗色/亮色主题。

## 架构

### PySide6 GUI 架构（需构建）

```
┌─────────────────────────────────────────────────────┐
│                 iOSPrintServer.exe                    │
│                                                     │
│  console/main.py → Config → Bootstrap                │
│                                                     │
│  ┌─────────────────────────────────────────────┐    │
│  │         PySide6 GUI (QApplication)           │    │
│  │                                              │    │
│  │  QSystemTrayIcon (系统托盘)                    │    │
│  │    ├── 关闭窗口 → 隐藏到托盘                   │    │
│  │    └── 右键菜单：显示 / 退出                   │    │
│  │                                              │    │
│  │  QMainWindow                                 │    │
│  │  ├── QStackedWidget (7 页面)                  │    │
│  │  ├── 左侧导航栏 (自定义 QWidget)               │    │
│  │  └── 顶部服务器状态栏                          │    │
│  │                                              │    │
│  │  └── EventBus ←→ 方法调用 ←→ ServerHandle      │    │
│  │                     (uvicorn 后台线程)         │    │
│  └─────────────────────────────────────────────┘    │
│                                                     │
│  后端服务 (app/ 目录)                                │
│  ├── FastAPI / uvicorn (后台线程)                    │
│  ├── JobQueue / WorkerPool / PrintEngine            │
│  ├── PrinterMonitor / Heartbeat                     │
│  ├── EventBus + SSEBroadcaster                      │
│  └── SQLite (WAL 模式)                              │
└─────────────────────────────────────────────────────┘
```

### 关键变化（Flet → PySide6）

| 层面 | Flet | PySide6 |
|------|------|---------|
| 进程模型 | 同一进程 | 同一进程（不变） |
| 窗口框架 | Flet Window | QMainWindow + QSystemTrayIcon |
| 导航 | NavigationRail | 自定义 QListWidget 侧边栏 |
| 页面容器 | Column + Stack | QStackedWidget |
| 服务通信 | httpx → localhost HTTP | EventBus 直接信号/槽 |
| 系统托盘 | 不支持 | QSystemTrayIcon ✅ |
| 文件选择 | FilePicker(不支持) | QFileDialog ✅ |
| 图表 | flet_charts.LineChart | QtCharts.QLineSeries ✅ |
| 主题 | Material 3 | Qt Stylesheets (QSS) + QPalette |
| 实时更新 | SSE 事件轮询 | EventBus 信号/槽直连 |
| 线程安全 | asyncio.run_coroutine_threadsafe | QMetaObject.invokeMethod / signal |
| 全局快捷键 | page.on_keyboard_event | QShortcut / keyPressEvent |
| 窗口状态 | 手动 JSON 文件 | QSettings (注册表/INI) |

### 通信方式：EventBus 直连（替换 HTTP 轮询）

GUI 不再通过 HTTP 与服务器通信，而是直接订阅 `EventBus`：

```python
# GUI 启动时
app, config, *_ = bootstrap(config, lifespan=_server_lifespan)

# 直接订阅事件
event_bus = app.state.event_bus
event_bus.on('job_status', self._on_job_status)
event_bus.on('printer_status', self._on_printer_status)

# 直接调用 API 函数
from app.routes.api import get_stats, get_jobs, get_printers_status
stats = await get_stats()
```

SSE 和 WS 端点保留（iOS Scriptable 客户端依赖），但 GUI 不再通过 HTTP 自循环。

---

## 组件状态设计

### QPushButton（按钮）

| 状态 | 触发条件 | 视觉表现 |
|------|---------|---------|
| 默认 | 初始未交互 | 主题色填充，标准圆角 |
| 悬停 | 鼠标悬停 | 亮度变化 + 阴影 QSS `:hover` |
| 聚焦 | Tab 键聚焦 | 外发光轮廓 QSS `:focus` |
| 按下 | 鼠标按下 | 微下沉 + 色值加深 QSS `:pressed` |
| 加载 | 操作进行中 | `setEnabled(False)` + 按钮文字变"保存中..." + QMovie 加载动画 |
| 禁用 | 输入不完整 | `setEnabled(False)`，透明度降低至 40% |
| 成功 | 操作完成 | 短暂绿色闪烁 + checkmark（1.5s 后 QTimer 恢复）|
| 错误 | 操作失败 | 红色闪烁 + 错误图标 + `setToolTip()` 说明原因 |

实现：通过 `QPropertyAnimation` + `QSS` 动态切换，按钮继承 `QPushButton` 包装为 `StatefulButton` 类统一管理状态。

### QLineEdit（文本输入框）

| 状态 | 表现 |
|------|------|
| 默认 | 标准边框 + `setPlaceholderText()` |
| 聚焦 | 主题色下边框 + 光标闪烁 |
| 已填写 | 正常显示输入值 |
| 验证通过 | 右侧绿色 checkmark icon |
| 验证失败 | 红色边框 + 底部 `setToolTip()` 错误文字 |
| 禁用 | `setReadOnly(True)` + 灰色背景 |

实现：`QValidator` 子类（`PortValidator`、`NumberRangeValidator`）绑定到 `QLineEdit.textChanged` 信号实时校验。

### QCheckBox（开关）

- 通过 QSS 美化模拟 Switch 外观
- checked/unchecked 状态过渡动画 150ms `QPropertyAnimation`
- 禁用状态 `setEnabled(False)` + 半透明样式

### QTableView（表格）

| 状态 | 表现 |
|------|------|
| 默认 | 隔行变色 `alternatingRowColors`, `QSortFilterProxyModel` |
| 悬停 | 行背景高亮 `QStyledItemDelegate` |
| 选中 | 主题色淡底 + 行选中 |
| 加载中 | 行内 skeleton 占位（占位文本灰色脉冲）|
| 空 | `setPlaceholderText("暂无数据")` + 居中图标 + 操作按钮 |
| 筛选空 | "没有匹配的任务" + 清除筛选按钮 |

### QProgressBar（进度条）

| 状态 | 表现 |
|------|------|
| 确定 | 百分比 + 主题色填充（文件上传/打印进度）|
| 不确定 | 条纹动画（任务排队等待中）|
| 完成 | 绿色 100% |
| 失败 | 红色 + 错误图标 |

### QDialog（对话框）

| 类型 | 用途 |
|------|------|
| QMessageBox.Question | 二次确认（取消任务/退出/重启）|
| QMessageBox.Information | 成功通知 |
| QMessageBox.Warning | 警告提示 |
| 自定义 QDialog | 需重启确认对话框（"稍后" / "立即重启" 按钮）|

---

## 页面状态设计

每个页面统一设计三种非正常状态，避免空白页和未处理错误。

### 1. 📊 仪表盘

| 状态 | 表现 |
|------|------|
| 空 | 首次运行无统计数据 → 显示"尚无打印任务" + 快速打印引导按钮（跳转到快速打印页）|
| 加载 | 所有卡片显示 skeleton 骨架屏（灰块脉冲动画，QLabel 灰色背景 + QTimer 闪烁）|
| 错误 | 服务器连接失败 → 顶部红色横幅"服务器连接失败，正在重试..." + 手动重试 QPushButton |
| 实时更新 | QTimer 每 3s 轮询刷新，不显示全屏加载，卡片内容单独更新 |

### 2. 🖨️ 快速打印

| 状态 | 表现 |
|------|------|
| 空 | 无选中文件 → 大号虚线拖拽区 + "拖拽文件到此处或输入路径" |
| 加载 | 文件上传中 → 确定进度条 + 取消按钮 |
| 错误 | 文件不存在 / 格式不支持 / 打印失败 → 红色提示 + 原因说明 + 重选文件 |

### 3. 📋 任务管理

| 状态 | 表现 |
|------|------|
| 空（队列） | "队列为空，提交打印任务后将在此显示" |
| 空（历史筛选）| "没有匹配的任务" + 清除筛选按钮 |
| 加载 | 表格 skeleton 行（5 行灰色占位文本脉冲）|
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
| 加载 | 表单骨架屏（灰块替代所有控件，缓慢脉冲 QTimer）|
| 保存成功 | 右下角弹出通知 "设置已保存"（3s 自动消失）|
| 需重启 | 保存后弹出 QDialog 确认对话框"部分设置需要重启服务器生效，是否立即重启？" |
| 验证错误 | 行内红色提示（`setToolTip()` + 红色边框，端口范围/数字范围/必填项）|

### 6. 🔌 打印机管理

| 状态 | 表现 |
|------|------|
| 空 | "未检测到打印机" + 刷新按钮 + 说明文字"请确保打印机已连接并开启" |
| 加载 | 卡片 skeleton（3 个 QWidget 灰色占位脉冲）|
| 错误 | "获取打印机状态失败" + 重试按钮 |

### 7. ℹ️ 关于

| 状态 | 表现 |
|------|------|
| 检查更新中 | "正在检查更新..." + `QMovie` spinner |
| 检查失败 | "检查更新失败，请稍后重试" + 重试按钮 |
| 已是最新 | "已是最新版本 (v{version})" + 绿色 checkmark |
| 有新版本 | "新版本 v{new_version} 可用" + 下载按钮 |

---

## 主题系统

### 设计 Token（不变，继承原规格书色值）

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

### Qt 主题实现

- **亮色/深色切换**：通过 `QPalette` + `QSS` 动态切换
- `ThemeEngine` 单例类，管理所有 token 和 QSS
- `apply_theme(ThemeMode.LIGHT / DARK)` 刷新全局样式
- 偏好持久化到 `config.json` 的 `theme_mode` 字段

```python
class ThemeEngine:
    _tokens: dict[str, str]  # token → hex 值
    
    def qss(self) -> str:
        """根据当前 token 生成全局 QSS"""
        return f"""
        QPushButton {{ background-color: {tokens['primary']}; }}
        QLineEdit:focus {{ border-color: {tokens['primary']}; }}
        ...
        """
    
    def palette(self, mode: ThemeMode) -> QPalette:
        """生成对应模式的 QPalette"""
```

### 深色模式适配要点

- QPalette `ColorRole.Window` / `Text` / `Base` / `Button` 等角色对应 token
- 打印机状态卡片：状态色（绿/黄/红）在深色模式下饱和度降低
- 日志颜色：深色模式下级别颜色亮度提高（INFO `#60A5FA`、WARNING `#FBBF24`、ERROR `#F87171`）
- 图表：QChart 在深色模式下网格线和坐标轴颜色变暗

---

## 微交互设计

| 交互 | 触发 | 规则 | 反馈 |
|------|------|------|------|
| 按钮点击 | 鼠标按下 → 松开 | 提交操作 | 100ms 内状态切换 → spinner → 结果(success/error) |
| 开关切换 | 点击 | flip boolean | 150ms 滑块动画 + 色值过渡（QPropertyAnimation）|
| 文件拖拽 | 文件进入拖拽区 | 验证文件类型 | 边框色变主题色 + 背景淡色（dragEnterEvent）|
| 文件拖出 | 文件离开拖拽区 | — | 恢复默认边框和背景（dragLeaveEvent）|
| 页面切换 | 导航栏点击 | 切换 QStackedWidget index | 内容区瞬时切换（可选 QPropertyAnimation 淡入）|
| 通知弹窗 | EventBus 事件触发 | 3s 自动消失 + 可手动关 | 右下角滑入 + 类型色标示（QPropertyAnimation）|
| 表单保存 | 点击保存按钮 | 验证 → 提交 | 按钮 → spinner → "已保存" 通知 |
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

实现：`QShortcut` 绑定到 QMainWindow。

---

## 窗口状态持久化

- 使用 `QSettings`（Windows 注册表 `HKEY_CURRENT_USER\Software\iOSPrintServer`）持久化：
  - 窗口大小、位置（`saveGeometry()` / `restoreGeometry()`）
  - 最后活跃页面（`QStackedWidget` 的 currentIndex）
  - 表格列宽、排序偏好（每页独立保存）
- 关闭窗口 → 保存几何状态 → `hide()` 到系统托盘（不退出）
- 开机自启通过 `console/autostart.py` 快捷方式方式（不变）

---

## 页面设计

### 1. 📊 仪表盘

数据源：
- `event_bus` 订阅 `health_status` / `job_status` / `printer_status`
- `job_repo.get_stats()` — 6 个统计指标（直接方法调用）
- `job_repo.get_jobs(limit=10)` — 最近 10 条任务

Qt 控件：
| 区域 | Qt 控件 | 说明 |
|------|---------|------|
| 顶部状态条 | 自定义 QWidget | ServerHandle.is_running + 端口 + SSL 标示 |
| 统计卡片 | QFrame × 6 | 排队中/打印中/今日完成/今日失败/成功率/总计 |
| 7 天趋势图 | QChart + QLineSeries | 每日任务数折线图 |
| 打印机卡片 | PrinterCardWidget × N | 自定义 QWidget，状态色圆点 + 名称 + 标签 |
| 最近任务列表 | QTableView + QSortFilterProxyModel | 10 条最新，不可交互仅展示 |

布局（QHBoxLayout + QVBoxLayout 嵌套）：
```
┌──────────────────────────────────────────────────┐
│  ● 运行中 · 端口 5000    [停止] [重启]  [Web]    │  ← 顶部状态栏
├──────────────────────────────────────────────────┤
│ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌─│
│ │排队 3│ │打印 1│ │今日5│ │今日0│ │100% │ │总99│ │  ← 统计卡片行
│ └──────┘ └──────┘ └──────┘ └──────┘ └──────┘ └─│
│ ┌──────────────────────────────────────────┐    │
│ │  近 7 天打印趋势图 (QChart)               │    │  ← 趋势图
│ └──────────────────────────────────────────┘    │
│ ┌──────────────┐  ┌─────────────────────────┐   │
│ │ 🖨️ HP Laser  │  │ #123 report.pdf 完成    │   │  ← 打印机+任务
│ │ ● 就绪       │  │ #122 photo.jpg 打印中   │   │
│ │ [设为默认]    │  │ #121 doc.docx 排队     │   │
│ └──────────────┘  └─────────────────────────┘   │
└──────────────────────────────────────────────────┘
```

状态设计：空 → "尚无打印任务" + 跳转快速打印按钮 | 加载 → 6 灰色卡片脉冲 QTimer | 错误 → 红色 QLabel 横幅 + 重试按钮

实时更新：`QTimer` 每 3s 触发 `_refresh_stats()`，不锁 UI，单独更新每个卡片内容。

### 2. 🖨️ 快速打印

数据源：
- `printer_repo.get_printers()` — 打印机下拉列表（直接调用）
- `config` — 默认打印参数

Qt 控件：
| 区域 | Qt 控件 | 说明 |
|------|---------|------|
| 拖拽区 | 自定义 DropZoneWidget | QWidget + dragEnterEvent/dropEvent，虚线边框 |
| 文件信息 | QLabel (文件名/大小/类型图标) | 选中后显示 |
| 打印机 | QComboBox | 从 PrinterMonitor 获取列表 |
| 份数 | QSpinBox | 1-99 |
| 双面/颜色 | QCheckBox (QSS 美化 Switch) | 默认从 config 读取 |
| 纸张大小 | QComboBox | A4/Letter/A3 |
| 提交按钮 | StatefulButton | 自定义 QPushButton，支持 loading/success/error |
| 进度 | QProgressBar | 上传进度（确定模式）|
| 跟踪 | QLabel | SSE job_status 回调显示状态 |

布局：
```
┌──────────────────────────────────────────────┐
│  快速打印                                      │
│                                              │
│  ╔══════════════════════════════════════╗     │
│  ║     ☁  拖拽文件到此处               ║     │  ← DropZoneWidget
│  ║     未选择文件                      ║     │     (dashed border)
│  ╚══════════════════════════════════════╝     │
│                                              │
│  [文件路径________________]  [浏览...]        │
│                                              │
│  打印机: [▼ HP LaserJet]  份数: [1▲]          │
│  [●] 双面    [●] 颜色    纸张: [▼ A4]        │
│                                              │
│  ████████████░░░░░░ 60%                      │  ← QProgressBar
│                                              │
│  [      开始打印      ]                       │  ← StatefulButton
│  #42 已提交，等待处理...                       │  ← QLabel 跟踪
└──────────────────────────────────────────────┘
```

状态设计：空 → 虚线拖拽区引导 | 加载 → QProgressBar 确定模式 + 取消 | 错误 → 红色 QLabel 行内提示 + 原因

实现：文件通过 `upload_service.save_upload()` 直接调用（非 HTTP 绕行），入队后订阅 `event_bus.on('job_status')` 跟踪进度。

### 3. 📋 任务管理

数据源：
- `job_repo.get_jobs(status, search, limit=20, offset)` — 分页查询
- `job_repo.count_jobs(status, search)` — 总数统计
- `job_queue.cancel_job(job_id)` — 取消
- `job_queue.retry_job(job_id)` — 重试

Qt 控件：
| 区域 | Qt 控件 | 说明 |
|------|---------|------|
| 正在打印卡片 | 自定义 QFrame | 任务名 + QProgressBar + 取消按钮 |
| 队列列表 | QTableView + 自定义 model | 队列中的任务 |
| 历史筛选栏 | QComboBox(状态) + QLineEdit(搜索) + QDateEdit × 2 | 筛选条件 |
| 历史表格 | QTableView + QSortFilterProxyModel | 可排序、可分页 |
| 分页控件 | 自定义 QWidget (QPushButton × N) | 上一页/页码/下一页 |
| 批量操作 | QPushButton × 2 | 批量取消 / 批量重试 |

布局：
```
┌─ 打印队列 ─────────────────────────────────┐
│  ┌──────────────────────────────────────┐   │
│  │ 📄 report.pdf  ● 正在打印 ████░░ 70% │   │  ← 正在打印卡片
│  │ [取消]                               │   │
│  └──────────────────────────────────────┘   │
│  #124 photo.jpg         排队中     [取消]    │
│  #125 invoice.xlsx     排队中     [取消]    │
├─ 历史记录 ─────────────────────────────────┤
│  状态: [▼ 全部] 搜索: [___________] 日期范围 │
│  ┌────┬────────┬────┬──────┬──────────┬──┐ │
│  │ ID │ 文件名  │类型│ 状态 │ 提交时间  │操作│ │  ← QTableView
│  ├────┼────────┼────┼──────┼──────────┼──┤ │
│  │120 │ a.pdf  │PDF │完成  │05-08 10:30│  │ │
│  │119 │ b.doc  │DOC│失败  │05-08 10:25│重试│ │
│  └────┴────────┴────┴──────┴──────────┴──┘ │
│  [批量取消] [批量重试]       ← 1 2 3 ... 10 →│
└─────────────────────────────────────────────┘
```

状态设计：空队列 → QLabel "队列为空" | 空筛选 → QLabel "没有匹配的任务" + 清除筛选按钮 | 加载 → 5 行灰色占位 QLabel 脉冲 | 错误 → QLabel "加载失败" + 重试按钮

实时更新：`event_bus.on('job_status')` 更新队列状态 + 高亮变化行（QPropertyAnimation 背景色闪烁）。

### 4. 📝 实时日志

数据源：
- `log_broadcaster.get_history(lines=200)` — 初始加载历史日志（直接调用）
- `event_bus.on('log')` — 实时流式追加

Qt 控件：
| 区域 | Qt 控件 | 说明 |
|------|---------|------|
| 级别筛选 | QComboBox | ALL/错误/警告/信息/调试 |
| 搜索框 | QLineEdit + QTimer 防抖 | 300ms debounce 过滤 |
| 日志列表 | QListWidget 自定义 | 带颜色编码级别 + 时间戳 + 消息 |
| 暂停/继续 | QPushButton | 暂停时缓冲新日志 |
| 清空 | QPushButton | 清空所有日志 |
| 自动滚动 | QCheckBox | 新日志自动滚动到底部 |
| 暂停标签 | QLabel (蓝色) | "已暂停 (+N 条)" |

布局：
```
┌──────────────────────────────────────────────┐
│  实时日志                                      │
│  级别: [▼ 全部] 搜索: [___________]            │
│  [❚❚暂停] [🗑清空] [⏬自动滚动] [📁打开文件夹] │
├──────────────────────────────────────────────┤
│  10:30:15  INFO  任务 #120 打印完成            │  ← QListWidget
│  10:30:10  WARN  打印机 HP 墨粉不足            │     (颜色编码)
│  10:30:05  INFO  开始打印 report.pdf           │
│  10:29:58  ERROR 打印失败: 纸张用尽             │
│  10:29:50  DEBUG 连接打印机 HP LaserJet        │
│  ...                                          │
├──────────────────────────────────────────────┤
│  暂停时显示: ┌─────────────────────────┐       │
│             │ ⏸ 已暂停 (+7 条)        │       │  ← QLabel 蓝色标签
│             └─────────────────────────┘       │
└──────────────────────────────────────────────┘
```

状态设计：空 → "暂无日志，打印任务时将自动显示" | 加载历史 → 顶部 QLabel "正在加载历史日志..." | 暂停 → 蓝色标签显示缓冲计数

性能：日志行使用 QListWidget（非 QTableView），单次追加不超过 100ms。缓冲队列超过 1000 条时自动丢弃最早 200 条。

### 5. ⚙️ 设置

数据源：`config` 实例直读 + `event_bus` 通知变更

Qt 控件：
| 区域 | Qt 控件 | 说明 |
|------|---------|------|
| 安全分组 | QLineEdit(密码模式) + QPushButton"生成" | API Key |
| 打印默认值分组 | QComboBox × 3 + QSpinBox × 2 + QCheckBox × 3 | 打印机/份数/双面/颜色/纸张/Excel/PPT/重试 |
| 夸克分组 | QLineEdit(密码模式) × 2 | Key ID + API Key |
| 通知分组 | QComboBox + QLineEdit × 2 + QComboBox × 2 | 渠道/Webhook/Key/级别/服务器 |
| 服务器分组 | QSpinBox(port) + QComboBox(log) + QCheckBox(SSL) + QComboBox(theme) | 端口/日志/SSL/主题 |
| Worker 分组 | QSpinBox × 6 | worker_count/max_file_size/job_retention/print_dpi/job_timeout/word_timeout |
| 保存/测试 | StatefulButton × 2 | "保存设置" + "测试通知" |

布局（QScrollArea 内 7 个 QGroupBox）：
```
┌──────────────────────────────────────────────┐
│  设置                              [保存设置]  │
│                                              │
│  ┌─ 安全 ─────────────────────────────────┐   │
│  │ API 密钥:  [****************] [生成]    │   │
│  └────────────────────────────────────────┘   │
│  ┌─ 打印默认值 ───────────────────────────┐   │
│  │ 默认打印机: [▼ HP LaserJet]            │   │
│  │ 默认份数: [1▲] 双面: [●] 颜色: [●]    │   │
│  │ 纸张: [▼ A4]                           │   │
│  └────────────────────────────────────────┘   │
│  ┌─ Worker ───────────────────────────────┐   │
│  │ 工作进程数: [2▲]  最大文件(MB): [50▲]   │   │
│  │ ...                                    │   │
│  └────────────────────────────────────────┘   │
│  ... (共 7 组)                                │
└──────────────────────────────────────────────┘
```

状态设计：加载 → 表单灰块 QTimer 脉冲 | 保存成功 → QLabel "设置已保存" 右下角 3s 自动消失 | 需重启 → QDialog "部分设置需要重启服务器生效，是否立即重启？" | 验证错误 → QLineEdit 红色边框 + setToolTip()

验证：PortValidator(1024-65535)、NumberRangeValidator(min,max) 绑定 QLineEdit.textChanged。

### 6. 🔌 打印机管理

数据源：
- `printer_monitor.get_printers_status()` — 实时状态（直接调用）
- `config.set('default_printer', name)` — 设为默认
- `event_bus.on('printer_status')` — 状态变化推送

Qt 控件：
| 区域 | Qt 控件 | 说明 |
|------|---------|------|
| 卡片网格 | QScrollArea + QFlowLayout(QWidget 容器) | 打印机卡片流式排列 |
| 单张卡片 | PrinterCardWidget (QFrame) | 名称 + 状态色圆点 + 标签列表 + 默认按钮 |
| 刷新按钮 | QPushButton | 手动刷新 |
| 默认标签 | QLabel | "默认打印机" 绿色标签 |

布局：
```
┌──────────────────────────────────────────────┐
│  打印机管理                      [刷新状态]    │
│                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │ 🖨️ HP    │  │ 🖨️ Epson │  │ 🖨️ Canon │    │  ← PrinterCardWidget
│  │ ● 就绪   │  │ ● 就绪   │  │ ○ 离线   │    │     × N
│  │ 纸张: A4  │  │ 纸张: A4 │  │          │    │
│  │ 打印: 120 │  │ 打印: 45 │  │ 打印: 0  │    │
│  │ ★ 默认   │  │ [设为默认]│  │ [设为默认]│    │
│  └──────────┘  └──────────┘  └──────────┘    │
│                                              │
│  打印机状态每 30 秒自动更新                    │
└──────────────────────────────────────────────┘
```

状态设计：空 → "未检测到打印机" + 刷新按钮 + 说明 | 加载 → 3 张灰色骨架卡片 QTimer 脉冲 | 错误 → "获取失败" + 重试按钮

### 7. ℹ️ 关于

Qt 控件：
| 区域 | Qt 控件 | 说明 |
|------|---------|------|
| 应用图标 | QLabel (QPixmap) | 应用 Logo |
| 名称/版本 | QLabel × 2 | "iOS 云打印服务器" + "v1.5.0" |
| 构建信息 | QLabel × 2 | 构建日期 + PyInstaller 版本 |
| 操作按钮 | QPushButton × 3 | 检查更新 / 日志文件夹 / 配置文件 |
| 更新状态 | QLabel + QMovie(spinner) / QLabel | 检查结果区域 |

布局：
```
┌──────────────────────────────────────────────┐
│                    🖨️                        │  ← QLabel (Logo)
│           iOS 云打印服务器                     │
│              版本: 1.5.0                      │
│         Python: 3.10.11                       │
│         构建日期: 2026-05-07                   │
│         PyInstaller: 6.11.0                   │
│                                              │
│    [检查更新]  [日志文件夹]  [配置文件]        │
│                                              │
│    ✅ 已是最新版本 (v1.5.0)                    │  ← 更新状态区
│                                              │
│  ──────────────────────────────────────────   │
│  iOS 云打印服务器                             │
│  接收 iOS Scriptable 和 Web 请求              │
└──────────────────────────────────────────────┘
```

状态设计：检查更新中 → QMovie spinner + "正在检查..." | 失败 → "检查失败，请稍后重试" + 重试按钮 | 最新 → 绿色 checkmark + "已是最新版本" | 有新版本 → "新版本 v{x} 可用" + 下载按钮

---

## 实时事件系统

| 事件类型 | 数据格式 | 推送方式 | 消费页面 |
|---------|---------|---------|---------|
| `job_status` | `{job_id, filename, status, error?, ts}` | EventBus signal/slot | 仪表盘、任务管理、快速打印 |
| `printer_status` | `{name, overall, statuses: [{key, label}]}` | EventBus signal/slot | 仪表盘、打印机管理 |
| `log` | `{level, message, timestamp}` | EventBus signal/slot | 实时日志 |
| `health_status` | `{queue_size, workers, uptime}` | EventBus signal/slot | 仪表盘顶部状态栏 |

### PySide6 事件连接（需实现）

GUI 通过 `EventBus` 直接在进程内订阅事件，不再经过 HTTP SSE 轮询：

```python
# EventBus（现有代码，保持不变）
event_bus = app.state.event_bus

# GUI 初始化时连接（这段代码需要实现）
class MainWindow(QMainWindow):
    def _connect_events(self):
        event_bus.on('job_status', self._on_job_status)
        event_bus.on('printer_status', self._on_printer_status)
        event_bus.on('log', self._on_log)

    @Slot(dict)
    def _on_job_status(self, data: dict):
        # QueuedConnection ensures this runs on GUI thread
        self._update_queue(data)
        self._update_stats()

    @Slot(dict)
    def _on_printer_status(self, data: dict):
        self._update_printer_cards(data)
```

### SSE/WebSocket 保留

SSE `/api/events` 和 WS `/ws/events` 端点**完全保留**，iOS Scriptable 客户端依赖它们。PySide6 GUI 不再使用，但不删除。

---

## 安装部署

### PyInstaller 打包（需更新配置）

```bash
# 构建单文件 EXE
pyinstaller --onefile --name iOSPrintServer ^
    --add-data "app/templates:templates" ^
    --hidden-import PySide6.QtCharts ^
    console/__main__.py
```

输出：`dist/iOSPrintServer.exe`

### QSS 资源打包

- 亮色主题 QSS：`gui/resources/light.qss`
- 深色主题 QSS：`gui/resources/dark.qss`
- 应用图标：`gui/resources/icon.ico` / `gui/resources/icon.png`
- 通过 `PyInstaller --add-data` 打包进 EXE，运行时通过 `QFile` 加载

### NSIS 安装器（需实现）

1. PyInstaller 构建 `iOSPrintServer.exe`
2. NSIS 打包为 `iOSPrintServer-Setup-{version}.exe`
3. 安装流程：
   - 选择安装目录（默认 `%LOCALAPPDATA%\iOSPrintServer`）
   - 创建开始菜单快捷方式
   - 可选桌面快捷方式
   - 注册表开机自启（指向 GUI exe）
   - 可选「安装后立即运行」

### 自更新（已实现）

内置更新检查 `GET /api/version` 对比 GitHub latest release，有新版本时提示用户下载。

---

## 实现排期

| Step | 工作项 | 依赖 |
|------|--------|------|
| 1 | 创建 PySide6 项目结构 + `gui/` 目录重构 | — |
| 2 | QMainWindow + QSystemTrayIcon + QStackedWidget 主框架 | — |
| 3 | 左侧导航栏 (QListWidget 自定义) + 页面路由 | 2 |
| 4 | 顶部服务器状态栏 + ServerHandle 连接 | 2 |
| 5 | 主题系统 (QPalette + QSS + ThemeEngine 单例) | — |
| 6 | 仪表盘页面（统计卡片 + QChart 趋势图 + 3 态） | 2, 4 |
| 7 | 任务管理页面（QTableView + 分页 + 筛选 + 3 态） | 2 |
| 8 | 快速打印页面（DropZoneWidget + QFileDialog + StatefulButton + 3 态） | 2 |
| 9 | 设置页面（QGroupBox × 7 + QValidator + 3 态） | 2 |
| 10 | 实时日志页面（QListWidget + 颜色编码 + 暂停缓冲 + 3 态） | 2 |
| 11 | 打印机管理页面（PrinterCardWidget + 卡片网格 + 3 态） | 2 |
| 12 | 关于页面 + 更新检查 | 2 |
| 13 | EventBus 信号/槽连接（替换 SSE/HTTP） | 5 |
| 14 | 键盘快捷键 QShortcut | 2 |
| 15 | 全局快捷键（全局热键注册） | 2 |
| 16 | 窗口状态持久化 QSettings | 2 |
| 17 | 微交互（按钮动画、开关动画、通知弹窗） | 5 |
| 18 | 系统托盘菜单 + 关闭→隐藏行为 | 2 |
| 19 | Windows 原生通知（QSystemTrayIcon.showMessage） | 18 |
| 20 | PyInstaller 构建配置更新（--add-data QSS/图标） | — |
| 21 | NSIS 安装器脚本 | 20 |
| 22 | 集成测试 + 回归测试 | 全上 |
| 23 | CI/CD 更新 | 22 |

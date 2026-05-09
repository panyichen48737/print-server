# UI Polish: Dashboard StatCards, Printer Cards, Page Consistency

## 目标

改善 GUI 的细节质感：StatCard 数字排版、打印机卡片统一、页面标题统一、整体间距和交互反馈。

## 改动清单

### 1. StatCard 重构

**文件:** `gui/pages/dashboard.py` + `gui/resources/light.qss` + `gui/resources/dark.qss`

**当前问题:** 内边距不足（20px），30px serif 数字在多位数时被挤压；变化值和数值挤在不同行，视觉散乱；缺乏趋势指示。

**修改方案:**
- `StatCard.__init__`: 内边距从 `20,22,20,22` → `24,24,22,24`（左右更大给数字呼吸空间）
- 数值和变化值同行显示（flex row）：大号数值 + 小号变化值 badge，避免垂直挤压
- 底部增加一条 1px 分隔线 + 趋势文字（如"较昨日 ↑ 10.3%"），取代单独的 change_lbl
- Grid 列间距从 16 → 18
- 数字颜色配合语义色：排队中/accent、打印中/default、完成/success、失败/error
- QSS: `#statValue` font-size 保持 30px，增加 `min-width`；`#statCard` padding 在 QSS 中设 0（由代码 layout 控制）

**布局变化:**
```
当前:                   改后:
┌──────────────┐       ┌──────────────────┐
│ 排队中        │       │ 排队中             │
│ 128           │       │ 128    ↑ 10.3%    │
│ ↑ 10.3%       │       │                   │
│               │       │ ───────────────── │
│ 今日完成      │       │ 较昨日 +12 台      │
│ 56            │       └──────────────────┘
└──────────────┘
```

### 2. 打印机卡片统一

**文件:** `gui/components/printer_card.py` + `gui/pages/dashboard.py` + `gui/pages/printer_manager.py` + QSS

**当前问题:** Dashboard 用内联横条卡片（`_build_printer_card`），PrinterManagerPage 用 `PrinterCardWidget`（固定 260×120，不同视觉风格）。两者完全不同。

**修改方案:**
- 重写 `PrinterCardWidget`，去掉 `setFixedSize`，改用灵活的 `sizePolicy`
- 增加图标占位区域（emoji 🖨️ 或首字母 icon），打印机名 + 端口/位置信息
- 状态指示器：圆形 dot + 中文状态文字
- 支持 `compact` 模式（Dashboard 用）和 `full` 模式（管理页用）
  - compact: 水平横条布局，无操作按钮
  - full: 垂直卡片布局，包含"设为默认"按钮
- `is_default` 标记：显示"★ 默认"标签
- 两种模式共享同样的配色、圆角、悬停效果

**`PrinterCardWidget` 接口变化:**
```python
class PrinterCardWidget(QFrame):
    set_default_clicked = Signal(str)

    def __init__(self, name: str, status: str, port: str = "",
                 is_default: bool = False, compact: bool = False, parent=None)
```

**QSS 新增/修改:**
- `QFrame#printerCard` — 通用背景/圆角/悬停（已存在）
- `QFrame#printerCard[compact="true"]` — 横条布局
- `QFrame#printerCard[compact="false"]` — 卡片布局

### 3. 页面标题统一

**文件:** `gui/pages/*.py`（dashboard 除外）+ QSS

**当前问题:** Dashboard 使用 `pageTitle` + `pageSub` 对象名 + theme font（Newsreader serif），其他页面直接 `font-size: 24px; font-weight: bold;` 内联样式。

**修改方案:**
- 所有页面标题统一使用 `QLabel` 加 `#pageTitle` 对象名（不需要 pageSub，但保留风格一致）
- 去掉所有内联 `styleSheet="font-size: 24px; font-weight: bold;"`
- 如果页面有副标题说明，使用 `#pageSub` 对象名
- 受影响页面: QuickPrint、JobManager、PrinterManager、Logs、Settings、About

### 4. 悬停效果增强

**文件:** QSS (`light.qss` / `dark.qss`)

**当前问题:** StatCard 没有悬停效果，printerCard 只有简单 border 变化。

**修改方案:**
- StatCard 增加 hover: 微弱的 `border: 1px solid` + 背景色轻微变化（保持柔和）
- printerCard hover 保留现有边框，增加 `background-color` 微变
- 所有卡片增加 `transition` 效果（QSS 不支持 transition，用 QPropertyAnimation 在 page 级别实现简单的 opacity/geometry 动画）
- 实际上 QSS 不支持 transition，所以 hover 只用即时样式变化（border + background），保持简洁

### 5. 整体间距调整

**文件:** `gui/pages/*.py`

**当前问题:** 不同页面边距不一致（Dashboard 用 `28,28,32,28`，其他页面无统一边距）。

**修改方案:**
- 所有页面统一使用 `28, 28, 32, 28` margins（与 Dashboard 一致），通过 `ScrollArea` 包裹
- 页面内部 section 间距统一 24px
- Dashboard 的 KPI grid 间距 16→18，printer grid 间距 14→16

### 6. 其他细节

- 清理无用的 import
- 确保 dark/light 主题切换后所有新样式正确应用
- PrinterManagerPage 加载状态优化（loading/empty/error 状态保持）

## 涉及文件

| 文件 | 改动 |
|------|------|
| `gui/pages/dashboard.py` | StatCard 重构、printer card 改用统一组件 |
| `gui/components/printer_card.py` | 重写，支持 compact/full 模式 |
| `gui/pages/printer_manager.py` | 使用新版 PrinterCardWidget，标题统一 |
| `gui/pages/quick_print.py` | 标题统一、边距统一 |
| `gui/pages/job_manager.py` | 标题统一、边距统一 |
| `gui/pages/logs.py` | 标题统一、边距统一 |
| `gui/pages/settings.py` | 标题统一、边距统一 |
| `gui/pages/about.py` | 标题统一、边距统一 |
| `gui/resources/light.qss` | StatCard hover、printerCard compact/full 样式 |
| `gui/resources/dark.qss` | 同上（dark 变体） |

## 非目标

- 不改动核心布局结构（sidebar、status bar 保持不变）
- 不新增页面或功能
- 不改动 backend/API 代码
- 不改动 BarChartWidget

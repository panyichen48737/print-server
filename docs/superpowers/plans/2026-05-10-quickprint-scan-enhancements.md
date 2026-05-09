# Quick Print & Scan UI Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enhance Quick Print and Document Scan pages with printer capability detection, file previews, navigation protection, clear buttons, and improved operation feedback.

**Architecture:** Extract printer capability querying into a shared utility; create a reusable `PrintDialog` for scan page; modify both pages incrementally; add navigation guard in MainWindow.

**Tech Stack:** PySide6, pywin32 (win32print), PIL (thumbnails)

---

## File Structure

- **New:** `gui/components/printer_capabilities.py` — `PrinterCapabilities` dataclass + query function via `win32print.DeviceCapabilities`
- **New:** `gui/components/print_dialog.py` — `PrintDialog(QDialog)` modal dialog for scan page printing
- **Modify:** `gui/pages/quick_print.py` — printer capabilities, file preview, clear button, tooltips, unsaved changes tracking
- **Modify:** `gui/pages/scan.py` — print dialog, file preview, clear button, tooltips, export-as-save, unsaved changes tracking
- **Modify:** `gui/app.py` — `_on_nav_changed` guard for unsaved changes

### Task 1: Printer capabilities utility

**Files:**
- Create: `gui/components/printer_capabilities.py`
- Modify: None
- Test: Not directly tested (tested through page integration)

```python
"""Query printer capabilities via win32print.DeviceCapabilities."""
from __future__ import annotations

from dataclasses import dataclass, field

import win32print


DC_COPIES = 17
DC_PAPERNAMES = 16
DC_COLORDEVICE = 23
DC_DUPLEX = 29


@dataclass
class PrinterCapabilities:
    copies_max: int = 99
    supports_color: bool = True
    supports_duplex: bool = True
    paper_names: list[str] = field(default_factory=lambda: ["A4", "Letter", "A3"])


def query_capabilities(printer_name: str) -> PrinterCapabilities:
    """Query printer capabilities from Windows print system."""
    caps = PrinterCapabilities()
    try:
        copies = win32print.DeviceCapabilities(printer_name, None, DC_COPIES, None)
        if copies and copies[0] > 0:
            caps.copies_max = copies[0]
    except Exception:
        pass

    try:
        color = win32print.DeviceCapabilities(printer_name, None, DC_COLORDEVICE, None)
        if color and color[0] == 0:
            caps.supports_color = False
    except Exception:
        pass

    try:
        duplex = win32print.DeviceCapabilities(printer_name, None, DC_DUPLEX, None)
        if duplex and duplex[0] == 0:
            caps.supports_duplex = False
    except Exception:
        pass

    try:
        papers = win32print.DeviceCapabilities(printer_name, None, DC_PAPERNAMES, None)
        if papers and len(papers) > 0:
            caps.paper_names = list(papers)
    except Exception:
        pass

    return caps
```

### Task 2: Print settings dialog

**Files:**
- Create: `gui/components/print_dialog.py`
- Test: `tests/test_print_dialog.py`

```python
"""Modal print settings dialog, shares PrinterCapabilities with inline panel."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QLabel, QPushButton,
    QSpinBox, QVBoxLayout, QWidget,
)

from gui.components.printer_capabilities import (
    PrinterCapabilities, query_capabilities,
)
from gui.components.toggle_switch import LabeledToggle


class PrintDialog(QDialog):
    def __init__(self, printers: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("打印设置")
        self.setMinimumWidth(420)
        self.setModal(True)

        self._caps: PrinterCapabilities = PrinterCapabilities()
        self._result: dict | None = None

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Printer
        printer_row = QHBoxLayout()
        printer_row.addWidget(QLabel("打印机:"))
        self.printer_combo = QComboBox()
        self.printer_combo.addItems(printers)
        self.printer_combo.currentTextChanged.connect(self._on_printer_changed)
        printer_row.addWidget(self.printer_combo, 1)
        layout.addLayout(printer_row)

        # Copies
        copies_row = QHBoxLayout()
        copies_row.addWidget(QLabel("份数:"))
        self.copies_spin = QSpinBox()
        self.copies_spin.setRange(1, 99)
        self.copies_spin.setValue(1)
        copies_row.addWidget(self.copies_spin)
        copies_row.addStretch()
        layout.addLayout(copies_row)

        # Color
        color_row = QHBoxLayout()
        color_row.addWidget(QLabel("颜色:"))
        self.color_combo = QComboBox()
        self.color_combo.addItems(["彩色", "黑白"])
        color_row.addWidget(self.color_combo)
        color_row.addStretch()
        layout.addLayout(color_row)

        # Duplex
        self.duplex_cb = LabeledToggle("双面", checked=True)
        layout.addWidget(self.duplex_cb)

        # Paper
        paper_row = QHBoxLayout()
        paper_row.addWidget(QLabel("纸张:"))
        self.paper_combo = QComboBox()
        paper_row.addWidget(self.paper_combo)
        paper_row.addStretch()
        layout.addLayout(paper_row)

        # Buttons
        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        self.confirm_btn = QPushButton("确认打印")
        self.confirm_btn.setObjectName("primary")
        self.confirm_btn.clicked.connect(self._confirm)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(self.confirm_btn)
        layout.addLayout(btn_row)

        if printers:
            self.printer_combo.setCurrentIndex(0)

    def _on_printer_changed(self, name: str):
        if not name:
            return
        self._caps = query_capabilities(name)
        self.copies_spin.setRange(1, self._caps.copies_max)

        # Color
        self.color_combo.clear()
        if self._caps.supports_color:
            self.color_combo.addItems(["彩色", "黑白"])
        else:
            self.color_combo.addItems(["黑白"])

        # Duplex
        self.duplex_cb.setVisible(self._caps.supports_duplex)
        self.duplex_cb.setChecked(self._caps.supports_duplex)

        # Paper
        self.paper_combo.clear()
        self.paper_combo.addItems(self._caps.paper_names)
        if "A4" in self._caps.paper_names:
            self.paper_combo.setCurrentText("A4")

    def _confirm(self):
        self._result = {
            "printer": self.printer_combo.currentText(),
            "copies": self.copies_spin.value(),
            "color": self.color_combo.currentText() == "彩色",
            "duplex": self.duplex_cb.isChecked() if self.duplex_cb.isVisible() else False,
            "paper_size": self.paper_combo.currentText(),
        }
        self.accept()

    def get_result(self) -> dict | None:
        return self._result
```

### Task 3: Quick Print page enhancements

**Files:**
- Modify: `gui/pages/quick_print.py`
- Test: `tests/test_quick_print.py` (new)

Changes:
1. Import `query_capabilities`, `PrinterCapabilities`
2. Add `_has_unsaved_content()` method
3. Add `_clear_all()` method
4. Add clear button to title row
5. Modify `_refresh_printers()` to auto-select default printer
6. Add `_on_printer_changed()` handler — color→QComboBox, dynamic paper, duplex visibility
7. Add file preview thumbnails in `_FileItemWidget`
8. Add file path display with truncation
9. Click file text to open
10. Add tooltips to controls
11. Connect printer combo to `_on_printer_changed`
12. Wire print process feedback

Implementation details:

**Title row with clear button:**
```python
title_row = QHBoxLayout()
title_lbl = QLabel("快速打印")
title_lbl.setObjectName("pageTitle")
title_row.addWidget(title_lbl)
title_row.addStretch()
self.clear_btn = QPushButton("✕ 清除")
self.clear_btn.setObjectName("ghost")
self.clear_btn.setToolTip("清除所有已选文件和结果，重新开始")
self.clear_btn.clicked.connect(self._confirm_clear)
title_row.addWidget(self.clear_btn)
layout.addLayout(title_row)
```

**_confirm_clear:**
```python
def _confirm_clear(self):
    from PySide6.QtWidgets import QMessageBox
    reply = QMessageBox.question(
        self, "确认清除", "确定要清除所有已选文件吗？此操作不可撤销。",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
    )
    if reply == QMessageBox.StandardButton.Yes:
        self._clear_all()

def _clear_all(self):
    self._file_paths.clear()
    self._tracking_job_ids.clear()
    self.file_list.clear()
    self.file_list.setVisible(False)
    self.progress.setVisible(False)
    self.tracking_label.setVisible(False)
    self.tracking_label.setText("")
    self.submit_btn.reset()

def _has_unsaved_content(self) -> bool:
    return self.file_list.count() > 0
```

**Printer auto-select:**
```python
def _refresh_printers(self):
    monitor = getattr(self._mw._app.state, "printer_monitor", None)
    if monitor is None:
        return
    self.printer_combo.clear()
    raw = monitor.get_all_statuses()
    for name in raw:
        self.printer_combo.addItem(name)

    # Auto-select default
    try:
        import win32print
        default = win32print.GetDefaultPrinter()
        idx = self.printer_combo.findText(default)
        if idx >= 0:
            self.printer_combo.setCurrentIndex(idx)
    except Exception:
        pass
```

**Color toggle → QComboBox:**
Replace `self.color_cb = LabeledToggle("彩色", checked=True)` with:
```python
self.color_combo = QComboBox()
self.color_combo.addItems(["彩色", "黑白"])
```

**Printer changed handler:**
```python
def _on_printer_changed(self, name: str):
    if not name:
        return
    caps = query_capabilities(name)
    self.copies_spin.setRange(1, caps.copies_max)
    self.copies_spin.setToolTip(f"最大复印数: {caps.copies_max}")

    self.color_combo.clear()
    if caps.supports_color:
        self.color_combo.addItems(["彩色", "黑白"])
        self.color_combo.setCurrentText("彩色")
    else:
        self.color_combo.addItems(["黑白"])

    self.duplex_cb.setVisible(caps.supports_duplex)
    if not caps.supports_duplex:
        self.duplex_cb.setChecked(False)

    self.paper_combo.clear()
    self.paper_combo.addItems(caps.paper_names)
    if "A4" in caps.paper_names:
        self.paper_combo.setCurrentText("A4")
```

**_submit() must use self.color_combo.currentText():**
```python
job = queue.enqueue(
    str(file_obj.path),
    printer=self.printer_combo.currentText(),
    copies=self.copies_spin.value(),
    duplex=self.duplex_cb.isChecked() if self.duplex_cb.isVisible() else False,
    color=self.color_combo.currentText() == "彩色",
    paper_size=self.paper_combo.currentText(),
)
```

**File item with thumbnail and path:**
```python
class _FileItemWidget(QWidget):
    def __init__(self, file_path: str, list_widget: QListWidget, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self._list_widget = list_widget
        self.setMinimumHeight(48)
        p = Path(file_path)
        lo = QHBoxLayout(self)
        lo.setContentsMargins(8, 4, 8, 4)
        lo.setSpacing(10)

        # Thumbnail
        thumb = QLabel()
        thumb.setFixedSize(40, 40)
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if p.suffix.lower() in IMAGE_EXTS:
            pixmap = QPixmap(file_path)
            if not pixmap.isNull():
                thumb.setPixmap(pixmap.scaled(40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                thumb.setText("🖼")
        else:
            thumb.setText("📄")
        lo.addWidget(thumb)

        # File name + truncated path
        parent_dir = p.parent.name if p.parent.name else p.parent.drive
        display_path = f"{parent_dir}\\{p.name}"
        if len(display_path) > 55:
            display_path = f"{parent_dir[0]}...\\{p.name}"
        info = QLabel(f"{p.name}")
        info.setToolTip(str(p))
        info.setStyleSheet("font-size: 12px; color: #8A8178;")
        info.setCursor(Qt.CursorShape.PointingHandCursor)
        info.mousePressEvent = lambda e, fp=file_path: _open_file(fp)

        path_lbl = QLabel(display_path)
        path_lbl.setToolTip(str(p))
        path_lbl.setStyleSheet("font-size: 11px; color: #6B7280;")

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        text_col.addWidget(info)
        text_col.addWidget(path_lbl)
        lo.addLayout(text_col, 1)

        open_btn = QPushButton("打开")
        open_btn.setFixedWidth(50)
        open_btn.setObjectName("ghost")
        open_btn.setProperty("compact", True)
        open_btn.clicked.connect(self._open_file)

        del_btn = QPushButton("✕")
        del_btn.setFixedWidth(28)
        del_btn.setObjectName("ghostDanger")
        del_btn.setProperty("compact", True)
        del_btn.clicked.connect(self._delete_self)
        lo.addWidget(open_btn)
        lo.addWidget(del_btn)


def _open_file(file_path: str):
    import subprocess
    subprocess.Popen(["explorer", file_path], shell=True)
```

Note: `IMAGE_EXTS` from scan.py should be shared. Either extract to a common module or duplicate in quick_print.py (simpler, avoid unnecessary abstraction). Add near top:
```python
IMAGE_EXTS = [".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tiff", ".tif", ".heic", ".heif"]
```

**Tooltips on controls:**
```python
self.drop_zone.setToolTip("支持 PDF、Office 文档、图片文件，可拖拽或多选")
self.copies_spin.setToolTip("设置打印份数，最大不超过打印机支持上限")
self.duplex_cb.setToolTip("开启后打印机将双面打印（需打印机支持）")
```

### Task 4: Scan page enhancements

**Files:**
- Modify: `gui/pages/scan.py`
- Test: `tests/test_scan_page.py` (new)

Changes:
1. Replace inline print panel with `PrintDialog` call
2. Add `_has_unsaved_content()` method
3. Add `_clear_all()` method
4. Add clear button to title row
5. Modify `_refresh_printers()` to auto-select default printer
6. Add `_on_printer_changed()` handler matching Quick Print
7. Add file preview thumbnails in `_FileItemWidget`
8. Add file path display with truncation
9. Click file text to open
10. Change export to `QFileDialog.getSaveFileName()`
11. Export completion: show path + "打开文件" and "打开文件夹" buttons
12. Add tooltips

**Title row with clear button — same pattern as Quick Print page.**

**_show_print_dialog:**
```python
def _show_print_dialog(self):
    if not (self._generated_pdf or self._generated_images):
        return

    monitor = getattr(self._mw._app.state, "printer_monitor", None)
    printers = list(monitor.get_all_statuses().keys()) if monitor else []

    from gui.components.print_dialog import PrintDialog
    dlg = PrintDialog(printers, self)
    if dlg.exec() == PrintDialog.DialogCode.Accepted:
        params = dlg.get_result()
        if params:
            self._do_print(params)
```

**Export → save dialog:**
```python
def _export_result(self):
    ext = ".pdf" if self._generated_pdf else ".jpg"
    filter_str = f"PDF (*.pdf)" if self._generated_pdf else "JPEG (*.jpg);;PNG (*.png)"
    file_path, _ = QFileDialog.getSaveFileName(
        self, "导出文件", f"scan_result{ext}", filter_str,
    )
    if not file_path:
        return

    try:
        out = Path(file_path)
        if self._generated_pdf:
            out.write_bytes(self._generated_pdf)
        elif self._generated_images:
            data = self._generated_images[0] if len(self._generated_images) == 1 else None
            if data:
                out.write_bytes(data)
            else:
                # Multiple images — save as zip or first image
                out.write_bytes(self._generated_images[0])
        self._show_export_result(out)
    except Exception as e:
        self._status_label.setText(f"导出失败: {e}")
        self._status_label.setStyleSheet("color: #C53A3A;")

def _show_export_result(self, path: Path):
    self._status_label.setText(f"已导出: {path}")
    self._status_label.setStyleSheet("color: #6B8F6B;")

    # Show action buttons
    from PySide6.QtWidgets import QPushButton
    # Remove old buttons if any
    for btn in self._export_action_widget.findChildren(QPushButton):
        btn.deleteLater()

    open_btn = QPushButton("打开文件")
    open_btn.clicked.connect(lambda: subprocess.Popen(["explorer", str(path)], shell=True))
    open_folder_btn = QPushButton("打开所在文件夹")
    open_folder_btn.clicked.connect(
        lambda: subprocess.Popen(["explorer", "/select,", str(path)], shell=True)
    )

    lo = self._export_action_widget.layout() or QHBoxLayout(self._export_action_widget)
    lo.addWidget(open_btn)
    lo.addWidget(open_folder_btn)
    self._export_action_widget.setVisible(True)
```

Add `_export_action_widget` to `__init__`:
```python
self._export_action_widget = QWidget()
self._export_action_widget.setVisible(False)
layout.addWidget(self._export_action_widget)
```

**File item with thumbnail — same as Quick Print _FileItemWidget.**

### Task 5: Navigation guard in MainWindow

**Files:**
- Modify: `gui/app.py`

**Changes to `_on_nav_changed`:**
```python
def _on_nav_changed(self, index: int):
    current = self.stack.currentWidget()
    if current and getattr(current, "_has_unsaved_content", lambda: False)():
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, "未保存更改",
            "当前页面有未提交的文件，离开后数据将清空，是否离开？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            # Block navigation — revert sidebar selection
            self.sidebar.blockSignals(True)
            self.sidebar.setCurrentRow(self.stack.currentIndex())
            self.sidebar.blockSignals(False)
            return
        # Clear current page
        if hasattr(current, "_clear_all"):
            current._clear_all()

    self.stack.setCurrentIndex(index)
    w = self.stack.currentWidget()
    if w:
        anim = QPropertyAnimation(w, b"windowOpacity")
        anim.setDuration(200)
        anim.setStartValue(0.7)
        anim.setEndValue(1.0)
        anim.start()
```

### Task 6: Tests

**Files:**
- Create: `tests/test_quick_print.py`
- Create: `tests/test_scan_page.py`
- Create: `tests/test_print_dialog.py`
- Create: `tests/test_printer_capabilities.py`

**test_printer_capabilities.py:**
```python
"""Test printer capabilities query utility."""
from gui.components.printer_capabilities import PrinterCapabilities, query_capabilities


def test_default_capabilities():
    caps = PrinterCapabilities()
    assert caps.copies_max == 99
    assert caps.supports_color is True
    assert caps.supports_duplex is True
    assert "A4" in caps.paper_names


def test_query_with_invalid_printer():
    caps = query_capabilities("NONEXISTENT_PRINTER_12345")
    # Should fall back to defaults without crashing
    assert caps.copies_max == 99
```

**test_print_dialog.py:**
```python
"""Test PrintDialog modal."""
import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_print_dialog_initial_state(qapp):
    from gui.components.print_dialog import PrintDialog
    dlg = PrintDialog(["Printer1", "Printer2"])
    assert dlg.printer_combo.count() == 2
    assert dlg.color_combo.currentText() == "彩色"
    assert dlg.copies_spin.value() == 1
```

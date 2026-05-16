"""Shared printer combo-box with capability-aware refresh."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox

from gui.components.printer_capabilities import PrinterCapabilities, query_capabilities


class PrinterComboBox(QComboBox):
    """QComboBox that auto-populates from printer monitor and emits capabilities.

    Usage:
        combo = PrinterComboBox()
        combo.capabilities_changed.connect(lambda caps: ...)
    """

    def __init__(self, config=None, parent=None):
        super().__init__(parent)
        self._config = config
        self._caps: PrinterCapabilities = PrinterCapabilities()
        self.setPlaceholderText('选择打印机')
        self.currentTextChanged.connect(self._on_text_changed)

    # ── Public API ──

    @property
    def caps(self) -> PrinterCapabilities:
        return self._caps

    def refresh(self, app_state) -> None:
        """Populate from printer_monitor."""
        monitor = getattr(app_state, 'printer_monitor', None)
        if monitor is None:
            return
        self.blockSignals(True)
        old = self.currentText()
        self.clear()
        raw = monitor.get_all_statuses()
        for name in raw:
            self.addItem(name)
        # restore selection
        idx = self.findText(old)
        if idx >= 0:
            self.setCurrentIndex(idx)
        self.blockSignals(False)
        # auto-select Windows default printer
        if self.count() and not old:
            self._select_default()

    def configure_copies(self, spin, visible=True) -> None:
        """Update a QSpinBox range based on printer caps."""
        if visible:
            spin.setRange(1, self._caps.copies_max)
            spin.setToolTip(f'最大复印数: {self._caps.copies_max}')

    def configure_color(self, combo) -> None:
        """Update a color QComboBox based on printer caps."""
        combo.clear()
        if self._caps.supports_color:
            combo.addItems(['彩色', '黑白'])
            if self._config:
                default_color = self._config.get('default_color', True)
                combo.setCurrentText('彩色' if default_color else '黑白')
        else:
            combo.addItems(['黑白'])

    def configure_duplex(self, toggle) -> None:
        """Update a LabeledToggle visibility/checked based on printer caps."""
        toggle.setVisible(self._caps.supports_duplex)
        if not self._caps.supports_duplex:
            toggle.setChecked(False)
        elif self._config:
            toggle.setChecked(self._config.get('default_duplex', False))

    def configure_paper(self, combo) -> None:
        """Update a paper-size QComboBox based on printer caps."""
        combo.clear()
        combo.addItems(self._caps.paper_names)
        if 'A4' in self._caps.paper_names:
            combo.setCurrentText('A4')

    # ── Internals ──

    def _on_text_changed(self, name: str):
        if not name:
            return
        self._caps = query_capabilities(name)

    def _select_default(self):
        try:
            import win32print

            default = win32print.GetDefaultPrinter()
            idx = self.findText(default)
            if idx >= 0:
                self.setCurrentIndex(idx)
        except Exception:
            pass

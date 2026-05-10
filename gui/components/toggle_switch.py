"""Toggle switch using QSlider + QSS for iOS-style sliding knob with capsule track."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QPropertyAnimation, Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QSlider, QWidget


TRACK_QSS = """
QSlider {{
    min-height: 30px; max-height: 30px;
}}
QSlider::groove:horizontal {{
    background: {color};
    height: 30px; border-radius: 15px; border: none;
}}
QSlider::sub-page:horizontal {{
    background: transparent; height: 30px; border-radius: 15px;
}}
QSlider::add-page:horizontal {{
    background: transparent; height: 30px; border-radius: 15px;
}}
QSlider::handle:horizontal {{
    background: {knob};
    width: 28px; height: 28px; margin: 1px 0;
    border-radius: 14px; border: none;
}}
"""


class ToggleSwitch(QSlider):
    toggled = Signal(bool)

    def __init__(self, checked: bool = False, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setRange(0, 1)
        self.setValue(1 if checked else 0)
        self._checked = checked
        self._animating = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(52, 30)
        self._refresh_qss()
        self.valueChanged.connect(self._on_value_changed)

    def _animate_toggle(self, target: int):
        self._animating = True
        anim = QPropertyAnimation(self, b"value")
        anim.setDuration(150)
        anim.setStartValue(self.value())
        anim.setEndValue(target)
        anim.finished.connect(lambda: setattr(self, '_animating', False))
        anim.start()

    def _track_color(self) -> str:
        if self._checked:
            return "#8B7355"  # light on
        return "#D0C8BE"  # light off

    def _knob_color(self) -> str:
        return "#FFFFFF"

    def _refresh_qss(self):
        opacity = "0.4" if not self.isEnabled() else "1.0"
        self.setStyleSheet(TRACK_QSS.format(
            color=self._track_color(),
            knob=self._knob_color(),
        ) + f"QSlider {{ opacity: {opacity}; }}")

    def changeEvent(self, event):
        if event.type() == QEvent.Type.EnabledChange:
            self._refresh_qss()
        super().changeEvent(event)

    def _on_value_changed(self, val: int):
        checked = val == 1
        if checked != self._checked:
            self._checked = checked
            self._refresh_qss()
            self.toggled.emit(checked)

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool):
        if checked == self._checked:
            return
        self._checked = checked
        self._animate_toggle(1 if checked else 0)
        self._refresh_qss()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._checked = not self._checked
            self._animate_toggle(1 if self._checked else 0)
            self._refresh_qss()
            self.toggled.emit(self._checked)
            return
        super().mousePressEvent(event)


class LabeledToggle(QWidget):
    """Label + ToggleSwitch in a horizontal row."""

    toggled = Signal(bool)

    def __init__(self, text: str = "", checked: bool = False, parent=None):
        super().__init__(parent)
        lo = QHBoxLayout(self)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(10)
        self._toggle = ToggleSwitch(checked)
        self._label = QLabel(text)
        lo.addWidget(self._toggle)
        lo.addWidget(self._label)
        lo.addStretch()
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)

        self._toggle.toggled.connect(self.toggled.emit)

    def isChecked(self) -> bool:
        return self._toggle.isChecked()

    def setChecked(self, checked: bool):
        self._toggle.setChecked(checked)

    @property
    def toggle(self) -> ToggleSwitch:
        return self._toggle
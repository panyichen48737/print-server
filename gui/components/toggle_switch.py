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
    background: {color};
    height: 30px; border-radius: 15px;
}}
QSlider::add-page:horizontal {{
    background: {color};
    height: 30px; border-radius: 15px;
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
        self._anim = QPropertyAnimation(self, b'value')
        self._anim.setDuration(150)
        self._anim.setStartValue(self.value())
        self._anim.setEndValue(target)
        self._anim.finished.connect(lambda: setattr(self, '_animating', False))
        self._anim.start()

    def _refresh_qss(self):
        opacity = '0.4' if not self.isEnabled() else '1.0'
        color = '#8B7355' if self._checked else '#D0C8BE'
        self.setStyleSheet(
            TRACK_QSS.format(color=color, knob='#FFFFFF') + f'QSlider {{ opacity: {opacity}; }}'
        )

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
            target = 0 if self._checked else 1
            self._animate_toggle(target)
            return
        super().mousePressEvent(event)


class LabeledToggle(QWidget):
    """Label + ToggleSwitch in a horizontal row."""

    toggled = Signal(bool)

    def __init__(
        self, text: str = '', checked: bool = False, parent=None, label_first: bool = False
    ):
        super().__init__(parent)
        lo = QHBoxLayout(self)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(10)
        self._toggle = ToggleSwitch(checked)
        self._label = QLabel(text)
        if label_first:
            lo.addWidget(self._label)
            lo.addWidget(self._toggle)
        else:
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

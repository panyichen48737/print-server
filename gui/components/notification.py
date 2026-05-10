"""Toast notification widget and confirmation dialog."""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class NotificationWidget(QFrame):
    def __init__(self, text: str, color: str = "#4F46E5", parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            NotificationWidget {{
                background-color: {color};
                border-radius: 8px;
                padding: 12px 20px;
            }}
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        self._label = QLabel(text)
        self._label.setStyleSheet("color: white; font-size: 13px;")
        close_btn = QPushButton("×")
        close_btn.setStyleSheet("color: white; border: none; font-size: 16px;")
        close_btn.clicked.connect(self.hide)
        layout.addWidget(self._label)
        layout.addWidget(close_btn)

        self._slide_in()

        # Auto-hide after 3s
        QTimer.singleShot(3000, self._fade_out)

    def _slide_in(self):
        parent_w = self.parent().width() if self.parent() else 400
        start_x = parent_w
        end_x = parent_w - self.width() - 24
        anim = QPropertyAnimation(self, b"pos")
        anim.setDuration(250)
        anim.setStartValue(QPoint(start_x, self.y()))
        anim.setEndValue(QPoint(end_x, self.y()))
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()

    def _fade_out(self):
        anim = QPropertyAnimation(self, b"windowOpacity")
        anim.setDuration(300)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.finished.connect(self.deleteLater)
        anim.start()


class NotificationStack(QWidget):
    """Stack of notification toasts at bottom-right."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)
        self.setLayout(layout)

    def show_notification(self, text: str, color: str = "#4F46E5"):
        n = NotificationWidget(text, color, self)
        self.layout().addWidget(n)


# 通用确认对话框
def confirm_dialog(parent, title: str, text: str,
                   buttons: dict[str, QMessageBox.ButtonRole]) -> str | None:
    """返回用户点击的按钮文本，或 None。"""
    from PySide6.QtWidgets import QMessageBox
    msg = QMessageBox(parent)
    msg.setWindowTitle(title)
    msg.setText(text)
    for btn_text, role in buttons.items():
        msg.addButton(btn_text, role)
    msg.exec()
    clicked = msg.clickedButton()
    return clicked.text() if clicked else None

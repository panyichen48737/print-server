"""QValidator subclasses for port and number range."""

from __future__ import annotations

from PySide6.QtGui import QIntValidator, QValidator


class PortValidator(QIntValidator):
    def __init__(self, parent=None):
        super().__init__(1024, 65535, parent)

    def validate(self, input_text: str, pos: int) -> tuple[QValidator.State, str, int]:
        if not input_text:
            return QValidator.State.Intermediate, input_text, pos
        return super().validate(input_text, pos)


class NumberRangeValidator(QIntValidator):
    def __init__(self, minimum: int, maximum: int, parent=None):
        super().__init__(minimum, maximum, parent)

"""Test PySide6 GUI lifecycle without showing window."""
import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_theme_engine(qapp):
    from gui.theme import ThemeEngine
    t = ThemeEngine.instance()
    t.apply("light", qapp)
    assert t.tokens["primary"] == "#4F46E5"
    t.apply("dark", qapp)
    assert t.tokens["primary"] == "#B4BEFE"


def test_stateful_button():
    from gui.components.stateful_button import StatefulButton
    btn = StatefulButton("测试")
    assert btn.text() == "测试"
    btn.set_loading()
    assert "..." in btn.text()
    btn.set_success()
    assert "✓" in btn.text()


def test_port_validator():
    from gui.components.validators import PortValidator
    v = PortValidator()
    state, _, _ = v.validate("8080", 4)
    assert state == v.State.Acceptable
    state, _, _ = v.validate("80", 2)
    assert state == v.State.Intermediate
    state, _, _ = v.validate("99999", 5)
    assert state == v.State.Intermediate
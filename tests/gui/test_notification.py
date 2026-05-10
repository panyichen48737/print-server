"""Tests for notification components."""
from PySide6.QtWidgets import QApplication, QWidget
import pytest

from gui.components.notification import NotificationStack, NotificationWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_notification_creation(qapp):
    nw = NotificationWidget("测试消息", "#6B8F6B")
    assert nw is not None


def test_notification_stack(qapp):
    parent = QWidget()
    stack = NotificationStack(parent)
    stack.show_notification("测试", "#6B8F6B")
    assert stack.layout().count() == 1
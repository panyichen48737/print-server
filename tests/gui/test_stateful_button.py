"""Tests for StatefulButton states."""

import pytest
from PySide6.QtWidgets import QApplication

from gui.components.stateful_button import StatefulButton


@pytest.fixture(scope='module')
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_default_state(qapp):
    btn = StatefulButton('提交')
    assert btn.text() == '提交'
    assert btn.isEnabled()


def test_loading_state(qapp):
    btn = StatefulButton('提交')
    btn.set_loading()
    assert '...' in btn.text()
    assert not btn.isEnabled()


def test_success_state(qapp):
    btn = StatefulButton('提交')
    btn.set_success()
    assert '✓' in btn.text()


def test_error_state_tooltip(qapp):
    btn = StatefulButton('提交')
    btn.set_error('连接失败')
    assert btn.toolTip() == '连接失败'


def test_reset(qapp):
    btn = StatefulButton('提交')
    btn.set_loading()
    btn.reset()
    assert btn.text() == '提交'
    assert btn.isEnabled()

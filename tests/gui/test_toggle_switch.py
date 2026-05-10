"""Tests for ToggleSwitch states."""

import pytest
from PySide6.QtWidgets import QApplication

from gui.components.toggle_switch import ToggleSwitch


@pytest.fixture(scope='module')
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_default_off(qapp):
    ts = ToggleSwitch(checked=False)
    assert not ts.isChecked()
    assert ts.value() == 0


def test_default_on(qapp):
    ts = ToggleSwitch(checked=True)
    assert ts.isChecked()
    assert ts.value() == 1


def test_set_checked(qapp):
    ts = ToggleSwitch(checked=False)
    ts.setChecked(True)
    assert ts.isChecked()


def test_disabled_state(qapp):
    ts = ToggleSwitch(checked=False)
    ts.setEnabled(False)
    assert not ts.isEnabled()

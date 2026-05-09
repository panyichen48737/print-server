"""Test Quick Print page."""
import pytest
from PySide6.QtWidgets import QApplication, QListWidgetItem
from PySide6.QtCore import Qt


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class FakeMainWindow:
    class _App:
        class State:
            printer_monitor = None
        state = State()
    _app = _App()


def test_quick_print_initial_state(qapp):
    from gui.pages.quick_print import QuickPrintPage
    page = QuickPrintPage(FakeMainWindow())
    assert page.printer_combo.count() == 0
    assert page.copies_spin.value() == 1
    assert page.color_combo.currentText() == "彩色"
    assert page._has_unsaved_content() is False


def test_quick_print_no_files_no_submit(qapp):
    from gui.pages.quick_print import QuickPrintPage
    page = QuickPrintPage(FakeMainWindow())
    # Should not crash when submitting with no files
    page._submit()


def test_quick_print_clear_all(qapp):
    from gui.pages.quick_print import QuickPrintPage
    page = QuickPrintPage(FakeMainWindow())
    page._clear_all()
    assert page._has_unsaved_content() is False

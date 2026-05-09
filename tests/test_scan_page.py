"""Test Scan page."""
import pytest
from PySide6.QtWidgets import QApplication


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


def test_scan_page_initial_state(qapp):
    from gui.pages.scan import ScanPage
    page = ScanPage(FakeMainWindow())
    assert page.output_combo.currentText() == "PDF"
    assert page._has_unsaved_content() is False


def test_scan_page_clear_all(qapp):
    from gui.pages.scan import ScanPage
    page = ScanPage(FakeMainWindow())
    page._clear_all()
    assert page._has_unsaved_content() is False
    assert page._generated_pdf is None
    assert page._generated_images == []


def test_scan_page_output_format_switch(qapp):
    from gui.pages.scan import ScanPage
    page = ScanPage(FakeMainWindow())
    page.output_combo.setCurrentText("图片")
    assert page.output_combo.currentText() == "图片"
    page.output_combo.setCurrentText("PDF")
    assert page.output_combo.currentText() == "PDF"

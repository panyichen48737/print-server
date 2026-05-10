"""Test PrintDialog modal."""

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope='module')
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_print_dialog_initial_state(qapp):
    from gui.components.print_dialog import PrintDialog

    dlg = PrintDialog(['Printer1', 'Printer2'])
    assert dlg.printer_combo.count() == 2
    assert dlg.color_combo.currentText() == '彩色'
    assert dlg.copies_spin.value() == 1


def test_print_dialog_empty_printers(qapp):
    from gui.components.print_dialog import PrintDialog

    dlg = PrintDialog([])
    assert dlg.printer_combo.count() == 0


def test_print_dialog_get_result_before_confirm(qapp):
    from gui.components.print_dialog import PrintDialog

    dlg = PrintDialog(['TestPrinter'])
    assert dlg.get_result() is None

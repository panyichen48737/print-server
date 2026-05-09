"""Test printer capabilities query utility."""
from gui.components.printer_capabilities import PrinterCapabilities, query_capabilities


def test_default_capabilities():
    caps = PrinterCapabilities()
    assert caps.copies_max == 99
    assert caps.supports_color is True
    assert caps.supports_duplex is True
    assert "A4" in caps.paper_names


def test_query_with_invalid_printer():
    caps = query_capabilities("NONEXISTENT_PRINTER_12345")
    # Should fall back to defaults without crashing
    assert caps.copies_max == 99

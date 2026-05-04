"""测试 PrinterDiscoveryService"""
from unittest.mock import MagicMock

import pytest

from app.services.printer_discovery import PrinterDiscoveryService


class TestPrinterDiscoveryService:
    def test_no_monitor_returns_empty(self):
        pd = PrinterDiscoveryService(None)
        assert pd.list_printers() == []
        assert pd.get_all_statuses() == {}

    def test_list_printers_delegates(self):
        monitor = MagicMock()
        monitor.get_all_statuses.return_value = {'HP1020': {}, 'EPSON': {}}
        pd = PrinterDiscoveryService(monitor)
        printers = pd.list_printers()
        assert set(printers) == {'HP1020', 'EPSON'}

    def test_get_all_statuses_delegates(self):
        monitor = MagicMock()
        monitor.get_all_statuses.return_value = {'HP': {'status': 'idle'}}
        pd = PrinterDiscoveryService(monitor)
        assert pd.get_all_statuses() == {'HP': {'status': 'idle'}}

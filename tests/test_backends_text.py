"""TextBackend 测试"""

from unittest.mock import MagicMock, patch

from app.printing.backends.base import discover_backends
from app.printing.backends.text import TextBackend


def test_registered():
    """TextBackend should be registered for .txt and .csv"""
    backends = discover_backends()
    assert backends['.txt'] is TextBackend
    assert backends['.csv'] is TextBackend


def test_not_registered_for_other():
    backends = discover_backends()
    assert '.pdf' not in backends or backends['.pdf'] is not TextBackend


@patch('app.printing.backends.text.win32print')
def test_print_txt(mock_win32print, tmp_path):
    txt = tmp_path / 'test.txt'
    txt.write_text('Hello World', encoding='utf-8')

    mock_win32print.GetDefaultPrinter.return_value = 'Test Printer'

    backend = TextBackend(MagicMock())
    result = backend.print_file(str(txt), 'job-1', {'printer_name': 'Test Printer'})
    assert result is True
    mock_win32print.OpenPrinter.assert_called_once_with('Test Printer')
    mock_win32print.StartDocPrinter.assert_called_once()
    mock_win32print.WritePrinter.assert_called_once()


@patch('app.printing.backends.text.win32print')
def test_print_csv(mock_win32print, tmp_path):
    csv = tmp_path / 'test.csv'
    csv.write_text('a,b,c', encoding='utf-8')

    backend = TextBackend(MagicMock())
    result = backend.print_file(str(csv), 'job-2', {'printer_name': 'Test'})
    assert result is True


@patch('app.printing.backends.text.win32print')
def test_print_default_printer(mock_win32print, tmp_path):
    """当不传 printer_name 且 config 无 default_printer 时，应使用系统默认打印机"""
    mock_win32print.GetDefaultPrinter.return_value = 'Default Printer'

    txt = tmp_path / 'test.txt'
    txt.write_text('test', encoding='utf-8')

    config = MagicMock()
    config.get.return_value = ''  # config.get('default_printer', '') → ''
    backend = TextBackend(config)
    result = backend.print_file(str(txt), 'job-default', {})
    assert result is True
    mock_win32print.OpenPrinter.assert_called_once_with('Default Printer')


@patch('app.printing.backends.text.win32print')
def test_print_config_default_printer(mock_win32print, tmp_path):
    """当不传 printer_name 但 config 有 default_printer 时，应使用 config 的默认打印机"""
    txt = tmp_path / 'test.txt'
    txt.write_text('test', encoding='utf-8')

    config = MagicMock()
    config.get.return_value = 'Config Printer'
    backend = TextBackend(config)
    result = backend.print_file(str(txt), 'job-default', {})
    assert result is True
    mock_win32print.OpenPrinter.assert_called_once_with('Config Printer')
    mock_win32print.GetDefaultPrinter.assert_not_called()


@patch('app.printing.backends.text.win32print')
def test_print_failure(mock_win32print, tmp_path):
    mock_win32print.OpenPrinter.side_effect = Exception('Printer not found')

    txt = tmp_path / 'test.txt'
    txt.write_text('Hello', encoding='utf-8')

    backend = TextBackend(MagicMock())
    import pytest

    with pytest.raises(Exception, match='Printer not found'):
        backend.print_file(str(txt), 'job-3', {'printer_name': 'BadPrinter'})


def test_cancel_returns_true():
    """cancel() should always return True - document already spooled"""
    backend = TextBackend(MagicMock())
    assert backend.cancel('job-x', {}) is True

"""PrinterMonitor 测试 — parse_status + 轮询和事件发布

win32print 是 Windows 原生库，在 mock 环境中测试逻辑层。
"""
from unittest.mock import MagicMock, patch

import pytest


# =============================================================================
# parse_status 位掩码解析
# =============================================================================

class TestParseStatus:
    """parse_status 各种位掩码组合"""

    def test_status_zero_returns_ready(self):
        from app.services.printer_monitor import parse_status
        overall, statuses = parse_status(0)
        assert overall == 'ready'
        assert statuses == []

    def test_ready_single_bit(self):
        from app.services.printer_monitor import parse_status
        # 节能模式（非错误/繁忙）
        overall, statuses = parse_status(0x01000000)
        assert overall == 'warning'
        assert len(statuses) == 1
        assert statuses[0]['key'] == 'power_save'

    def test_error_bit_returns_error_overall(self):
        from app.services.printer_monitor import parse_status
        overall, statuses = parse_status(0x00000080)  # offline
        assert overall == 'error'
        assert statuses[0]['label'] == '离线'

    def test_busy_bit_returns_busy_overall(self):
        from app.services.printer_monitor import parse_status
        overall, statuses = parse_status(0x00000400)  # printing
        assert overall == 'busy'
        assert statuses[0]['label'] == '打印中'

    def test_unknown_bit_returns_ready(self):
        from app.services.printer_monitor import parse_status
        # 未知位 0x10000000，不在 STATUS_BITS 中
        overall, statuses = parse_status(0x10000000)
        assert overall == 'ready'
        assert statuses == []

    def test_multiple_bits_error_priority(self):
        """多个位同时存在时 error > warning > busy"""
        from app.services.printer_monitor import parse_status
        overall, statuses = parse_status(0x00000080 | 0x00000400)  # offline + printing
        assert overall == 'error'  # error 优先
        keys = [s['key'] for s in statuses]
        assert 'offline' in keys
        assert 'printing' in keys

    def test_multiple_bits_warning_no_error(self):
        """warning + busy → warning"""
        from app.services.printer_monitor import parse_status
        overall, statuses = parse_status(0x00000001 | 0x00000400)  # paused + printing
        assert overall == 'warning'  # warning > busy
        keys = [s['key'] for s in statuses]
        assert 'paused' in keys
        assert 'printing' in keys

    def test_all_bits_no_error(self):
        """只有 busy 位"""
        from app.services.printer_monitor import parse_status
        overall, statuses = parse_status(0x00000100)  # io_active
        assert overall == 'busy'


# =============================================================================
# PrinterMonitor 轮询
# =============================================================================

class TestPrinterMonitorPoll:
    """PrinterMonitor._poll — mock win32print"""

    @pytest.fixture
    def mock_printers(self):
        """模拟 win32print.EnumPrinters(2) 返回 PRINTER_INFO_2 元组

        pywin32 PRINTER_INFO_2: (flags, desc, name, comment, ...)
        index 2 = printer name
        """
        return [
            (0, 'HP LaserJet on USB001', 'HP LaserJet', 'HP LaserJet'),
            (0, 'Canon MG3600 on USB002', 'Canon MG3600', 'Canon MG3600'),
        ]

    @pytest.fixture
    def monitor(self):
        from app.services.printer_monitor import PrinterMonitor
        broadcaster = MagicMock()
        m = PrinterMonitor(broadcaster=broadcaster)
        return m, broadcaster

    def test_poll_updates_cache(self, mock_printers, monitor):
        m, broadcaster = monitor
        with patch('app.services.printer_monitor.win32print.EnumPrinters', return_value=mock_printers), \
             patch('app.services.printer_monitor.win32print.OpenPrinter') as open_mock, \
             patch('app.services.printer_monitor.win32print.GetPrinter', return_value={'Status': 0}), \
             patch('app.services.printer_monitor.win32print.ClosePrinter'):

            m._poll()

            statuses = m.get_all_statuses()
            assert 'HP LaserJet' in statuses
            assert 'Canon MG3600' in statuses

    def test_poll_publishes_events(self, mock_printers, monitor):
        m, broadcaster = monitor
        with patch('app.services.printer_monitor.win32print.EnumPrinters', return_value=mock_printers), \
             patch('app.services.printer_monitor.win32print.OpenPrinter'), \
             patch('app.services.printer_monitor.win32print.GetPrinter', return_value={'Status': 0}), \
             patch('app.services.printer_monitor.win32print.ClosePrinter'):

            m._poll()

            # 每个打印机发布一次 printer_status 事件
            assert broadcaster.publish.call_count == 2
            call_args = broadcaster.publish.call_args_list[0]
            assert call_args[0][0] == 'printer_status'

    def test_poll_detects_removed_printer(self, mock_printers, monitor):
        m, broadcaster = monitor
        # 先塞一个已存在的打印机到缓存
        with m._cache_lock:
            m._cache['Old Printer'] = {'name': 'Old Printer', 'overall': 'ready', 'statuses': []}

        with patch('app.services.printer_monitor.win32print.EnumPrinters', return_value=mock_printers), \
             patch('app.services.printer_monitor.win32print.OpenPrinter'), \
             patch('app.services.printer_monitor.win32print.GetPrinter', return_value={'Status': 0}), \
             patch('app.services.printer_monitor.win32print.ClosePrinter'):

            m._poll()

            # 应包含 removed 事件
            removed_calls = [c for c in broadcaster.publish.call_args_list
                             if c[0][1].get('overall') == 'removed']
            assert len(removed_calls) == 1
            assert removed_calls[0][0][1]['name'] == 'Old Printer'

    def test_poll_no_change_does_not_publish(self, mock_printers, monitor):
        m, broadcaster = monitor
        # 第一次 poll 填充缓存
        with patch('app.services.printer_monitor.win32print.EnumPrinters', return_value=mock_printers), \
             patch('app.services.printer_monitor.win32print.OpenPrinter'), \
             patch('app.services.printer_monitor.win32print.GetPrinter', return_value={'Status': 0}), \
             patch('app.services.printer_monitor.win32print.ClosePrinter'):

            m._poll()
            broadcaster.publish.reset_mock()

            # 第二次相同数据，不应触发 publish
            m._poll()
            assert broadcaster.publish.call_count == 0

    def test_enum_failure_does_not_crash(self, monitor):
        m, broadcaster = monitor
        with patch('app.services.printer_monitor.win32print.EnumPrinters', side_effect=Exception('access denied')):
            m._poll()  # 不应抛出异常
            broadcaster.publish.assert_not_called()

    def test_poll_printer_with_status(self, mock_printers, monitor):
        m, broadcaster = monitor
        # 第一个打印机离线状态，第二个正常
        status_map = {
            'HP LaserJet': {'Status': 0x00000080},   # offline
            'Canon MG3600': {'Status': 0},
        }

        def fake_open(name):
            return name  # 直接用名字当 handle

        def fake_get_printer(handle, level):
            return status_map.get(handle, {'Status': 0})

        with patch('app.services.printer_monitor.win32print.EnumPrinters', return_value=mock_printers), \
             patch('app.services.printer_monitor.win32print.OpenPrinter', side_effect=fake_open), \
             patch('app.services.printer_monitor.win32print.GetPrinter', side_effect=fake_get_printer), \
             patch('app.services.printer_monitor.win32print.ClosePrinter'):

            m._poll()

            all_statuses = m.get_all_statuses()
            assert 'HP LaserJet' in all_statuses
            assert all_statuses['HP LaserJet']['overall'] == 'error'
            assert 'Canon MG3600' in all_statuses
            assert all_statuses['Canon MG3600']['overall'] == 'ready'


# =============================================================================
# PrinterMonitor 启动/停止
# =============================================================================

class TestPrinterMonitorLifecycle:
    """start/stop 生命周期"""

    def test_start_creates_thread(self):
        from app.services.printer_monitor import PrinterMonitor
        m = PrinterMonitor()
        m.start()
        assert m._thread is not None
        assert m._thread.is_alive()
        m.stop()

    def test_double_start_idempotent(self):
        from app.services.printer_monitor import PrinterMonitor
        m = PrinterMonitor()
        m.start()
        thread = m._thread
        m.start()  # 第二次应该不创建新线程
        assert m._thread is thread
        m.stop()

    def test_stop_sets_event(self):
        from app.services.printer_monitor import PrinterMonitor
        m = PrinterMonitor()
        m.start()
        m.stop()
        assert m._stop_evt.is_set()

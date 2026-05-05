"""测试打印模块工具函数"""

from unittest.mock import MagicMock, patch

from app.printing.utils import cancel_all_spooler_jobs


def _with_win32print(mock):
    """将 mock win32print 注入 sys.modules 并返回上下文"""
    return patch.dict('sys.modules', {'win32print': mock})


class TestCancelAllSpoolerJobs:
    def test_cancels_all_jobs(self):
        mock_w32 = MagicMock()
        mock_handle = MagicMock()
        mock_w32.OpenPrinter.return_value = mock_handle
        mock_w32.EnumJobs.return_value = [{'JobId': 1}, {'JobId': 2}, {'JobId': 3}]

        with _with_win32print(mock_w32):
            cancel_all_spooler_jobs('HP1020')

        mock_w32.OpenPrinter.assert_called_once_with('HP1020')
        assert mock_w32.SetJob.call_count == 3
        mock_w32.ClosePrinter.assert_called_once_with(mock_handle)

    def test_no_jobs_does_nothing(self):
        mock_w32 = MagicMock()
        mock_handle = MagicMock()
        mock_w32.OpenPrinter.return_value = mock_handle
        mock_w32.EnumJobs.return_value = []

        with _with_win32print(mock_w32):
            cancel_all_spooler_jobs('HP1020')

        mock_w32.SetJob.assert_not_called()
        mock_w32.ClosePrinter.assert_called_once()

    def test_exception_logged_not_raised(self):
        mock_w32 = MagicMock()
        mock_w32.OpenPrinter.side_effect = Exception('printer error')

        with _with_win32print(mock_w32):
            cancel_all_spooler_jobs('HP1020')  # 不应抛出

"""文本打印后端 — .txt / .csv"""

from pathlib import Path

from loguru import logger

from app.printing.backends.base import PrinterBackend, register

try:
    import win32print
except ImportError:
    win32print = None


@register('.txt', '.csv')
class TextBackend(PrinterBackend):
    """使用 win32print 直接打印文本文件"""

    def __init__(self, config):
        self.config = config

    def print_file(self, filepath: str, _job_id: str, print_params: dict, _lock=None) -> bool:
        content = Path(filepath).read_bytes()
        printer_name = print_params.get('printer_name', '')
        if not printer_name:
            printer_name = win32print.GetDefaultPrinter()

        try:
            hprinter = win32print.OpenPrinter(printer_name)
            try:
                win32print.StartDocPrinter(hprinter, 1, (Path(filepath).name, None, 'RAW'))
                win32print.StartPagePrinter(hprinter)
                win32print.WritePrinter(hprinter, content)
                win32print.EndPagePrinter(hprinter)
                win32print.EndDocPrinter(hprinter)
            finally:
                win32print.ClosePrinter(hprinter)
            logger.info(f'Text 打印完成: {filepath}')
            return True
        except Exception as e:
            logger.error(f'Text 打印失败: {e}')
            return False

    def cancel(self, _job_id: str, _info: dict) -> bool:
        """Text 打印无法取消 — 文档已直接发送到 Spooler"""
        return True

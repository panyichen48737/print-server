"""打印机发现服务：枚举打印机与聚合状态"""
from typing import Any

from loguru import logger


class PrinterDiscoveryService:
    def __init__(self, printer_monitor: Any = None) -> None:
        self._printer_monitor = printer_monitor

    def list_printers(self) -> list[str]:
        """枚举本机所有打印机名称"""
        try:
            import win32print
            printers = win32print.EnumPrinters(2)
            return [p[2] for p in printers]
        except Exception as e:
            logger.error(f'枚举打印机失败: {e}')
            return []

    def get_all_statuses(self) -> dict[str, dict[str, Any]]:
        """获取所有打印机缓存状态"""
        if not self._printer_monitor:
            return {}
        return self._printer_monitor.get_all_statuses()

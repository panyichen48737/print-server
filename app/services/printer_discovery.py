"""打印机发现服务：枚举打印机与聚合状态"""
from typing import Any


class PrinterDiscoveryService:
    def __init__(self, printer_monitor: Any = None) -> None:
        self._printer_monitor = printer_monitor

    def list_printers(self) -> list[str]:
        """枚举本机所有打印机名称"""
        if not self._printer_monitor:
            return []
        return list(self._printer_monitor.get_all_statuses().keys())

    def get_all_statuses(self) -> dict[str, dict[str, Any]]:
        """获取所有打印机缓存状态"""
        if not self._printer_monitor:
            return {}
        return self._printer_monitor.get_all_statuses()

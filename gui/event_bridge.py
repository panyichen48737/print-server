"""Bridge EventBus (thread-safe) to Qt signal/slot."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot

from app.services.sse_broadcaster import EventBus


class EventBridge(QObject):
    """Wraps EventBus subscriptions in Qt signals for thread-safe GUI updates."""

    job_status = Signal(dict)
    printer_status = Signal(dict)
    log = Signal(dict)

    def __init__(self, event_bus: EventBus | None, parent: QObject | None = None):
        super().__init__(parent)
        self._bus = event_bus
        if self._bus:
            self._bus.on('job_status', self._emit_job_status)
            self._bus.on('printer_status', self._emit_printer_status)
            self._bus.on('log', self._emit_log)

    @Slot(dict)
    def _emit_job_status(self, data: dict):
        self.job_status.emit(data)

    @Slot(dict)
    def _emit_printer_status(self, data: dict):
        self.printer_status.emit(data)

    @Slot(dict)
    def _emit_log(self, data: dict):
        self.log.emit(data)

    def stop(self):
        if self._bus:
            self._bus.off('job_status', self._emit_job_status)
            self._bus.off('printer_status', self._emit_printer_status)
            self._bus.off('log', self._emit_log)

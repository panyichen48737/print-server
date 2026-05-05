"""打印机状态监控 — 每30s轮询 win32print, 通过 SSE 广播器推送"""

import threading
from typing import Any

import win32print
from loguru import logger

# 打印机状态位 → (bit_mask, 中文标签)
STATUS_BITS: dict[str, tuple[int, str]] = {
    'paused': (0x00000001, '已暂停'),
    'error': (0x00000002, '错误'),
    'pending_deletion': (0x00000004, '待删除'),
    'paper_jam': (0x00000008, '卡纸'),
    'paper_out': (0x00000010, '缺纸'),
    'manual_feed': (0x00000020, '手动进纸'),
    'paper_problem': (0x00000040, '纸张问题'),
    'offline': (0x00000080, '离线'),
    'io_active': (0x00000100, 'IO 活动中'),
    'busy': (0x00000200, '忙'),
    'printing': (0x00000400, '打印中'),
    'output_bin_full': (0x00000800, '出纸槽已满'),
    'not_available': (0x00001000, '不可用'),
    'waiting': (0x00002000, '等待中'),
    'processing': (0x00004000, '处理中'),
    'initializing': (0x00008000, '初始化中'),
    'warming_up': (0x00010000, '预热中'),
    'toner_low': (0x00020000, '墨量低'),
    'no_toner': (0x00040000, '缺墨'),
    'page_punt': (0x00080000, '页跳过'),
    'user_intervention': (0x00100000, '需用户干预'),
    'out_of_memory': (0x00200000, '内存不足'),
    'door_open': (0x00400000, '盖板打开'),
    'power_save': (0x01000000, '节能模式'),
}

# overall 分类
ERROR_BITS: set[str] = {
    'offline',
    'error',
    'paper_jam',
    'paper_out',
    'no_toner',
    'door_open',
    'not_available',
    'out_of_memory',
}
WARNING_BITS: set[str] = {
    'toner_low',
    'user_intervention',
    'output_bin_full',
    'manual_feed',
    'paper_problem',
    'power_save',
    'paused',
}
BUSY_BITS: set[str] = {'printing', 'busy', 'io_active', 'processing', 'initializing', 'warming_up'}


def parse_status(status: int) -> tuple[str, list[dict[str, str]]]:
    """解析 win32print status 位掩码，返回 (overall, active_statuses)"""
    if status == 0:
        return 'ready', []
    active: list[dict[str, str]] = []
    for key, (bit, label) in STATUS_BITS.items():
        if status & bit:
            active.append({'key': key, 'label': label})
    if not active:
        return 'ready', []
    # 确定 overall
    keys = {s['key'] for s in active}
    if keys & ERROR_BITS:
        overall = 'error'
    elif keys & WARNING_BITS:
        overall = 'warning'
    elif keys & BUSY_BITS:
        overall = 'busy'
    else:
        overall = 'ready'
    return overall, active


class PrinterMonitor:
    def __init__(self, broadcaster: Any = None) -> None:
        self._broadcaster = broadcaster
        self._stop_evt = threading.Event()
        self._thread: threading.Thread | None = None
        self._cache: dict[str, dict[str, Any]] = {}
        self._cache_lock = threading.Lock()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_evt.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info('打印机监控已启动')

    def stop(self) -> None:
        self._stop_evt.set()
        logger.info('打印机监控已停止')

    def _loop(self) -> None:
        while not self._stop_evt.is_set():
            try:
                self._poll()
            except Exception as e:
                logger.error(f'打印机状态轮询异常: {e}')
            self._stop_evt.wait(30)

    def _poll(self) -> None:
        printers: list[dict[str, Any]] = []
        try:
            for p in win32print.EnumPrinters(2):
                name = p[2]
                handle = win32print.OpenPrinter(name)
                try:
                    info = win32print.GetPrinter(handle, 2)
                    status = info.get('Status', 0)
                    overall, active = parse_status(status)
                finally:
                    win32print.ClosePrinter(handle)
                printers.append(
                    {
                        'name': name,
                        'overall': overall,
                        'statuses': active,
                    }
                )
        except Exception as e:
            logger.warning(f'枚举打印机失败: {e}')
            return

        # 检测变化（在锁内）
        changed: list[dict[str, Any]] = []
        removed: list[str] = []
        with self._cache_lock:
            current_names = {p['name'] for p in printers}
            for pr in printers:
                name = pr['name']
                old = self._cache.get(name)
                if old != pr:
                    self._cache[name] = pr
                    changed.append(pr)
            for name in list(self._cache.keys()):
                if name not in current_names:
                    removed.append(name)
                    self._cache.pop(name)

        # 在锁外推送，避免网络 IO 持锁
        for pr in changed:
            if self._broadcaster:
                try:
                    self._broadcaster.publish('printer_status', pr)
                except Exception as e:
                    logger.warning(f'PrinterMonitor error: {e}')
        for name in removed:
            if self._broadcaster:
                try:
                    self._broadcaster.publish(
                        'printer_status', {'name': name, 'overall': 'removed', 'statuses': []}
                    )
                except Exception as e:
                    logger.warning(f'PrinterMonitor error: {e}')

    def get_all_statuses(self) -> dict[str, dict[str, Any]]:
        with self._cache_lock:
            return dict(self._cache)

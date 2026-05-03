"""打印机状态监控 — 每30s轮询 win32print, 通过 SSE 广播器推送"""
import logging
import threading
import win32print

logger = logging.getLogger('print_server')

# 打印机状态位常量
PRINTER_STATUS_PAUSED = 0x00000001
PRINTER_STATUS_ERROR = 0x00000002
PRINTER_STATUS_PENDING_DELETION = 0x00000004
PRINTER_STATUS_PAPER_JAM = 0x00000008
PRINTER_STATUS_PAPER_OUT = 0x00000010
PRINTER_STATUS_MANUAL_FEED = 0x00000020
PRINTER_STATUS_PAPER_PROBLEM = 0x00000040
PRINTER_STATUS_OFFLINE = 0x00000080
PRINTER_STATUS_IO_ACTIVE = 0x00000100
PRINTER_STATUS_BUSY = 0x00000200
PRINTER_STATUS_PRINTING = 0x00000400
PRINTER_STATUS_OUTPUT_BIN_FULL = 0x00000800
PRINTER_STATUS_NOT_AVAILABLE = 0x00001000
PRINTER_STATUS_WAITING = 0x00002000
PRINTER_STATUS_PROCESSING = 0x00004000
PRINTER_STATUS_INITIALIZING = 0x00008000
PRINTER_STATUS_WARMING_UP = 0x00010000
PRINTER_STATUS_TONER_LOW = 0x00020000
PRINTER_STATUS_NO_TONER = 0x00040000
PRINTER_STATUS_PAGE_PUNT = 0x00080000
PRINTER_STATUS_USER_INTERVENTION = 0x00100000
PRINTER_STATUS_OUT_OF_MEMORY = 0x00200000
PRINTER_STATUS_DOOR_OPEN = 0x00400000
PRINTER_STATUS_POWER_SAVE = 0x01000000

STATUS_BITS = {
    'paused':            (PRINTER_STATUS_PAUSED, '已暂停'),
    'error':             (PRINTER_STATUS_ERROR, '错误'),
    'pending_deletion':  (PRINTER_STATUS_PENDING_DELETION, '待删除'),
    'paper_jam':         (PRINTER_STATUS_PAPER_JAM, '卡纸'),
    'paper_out':         (PRINTER_STATUS_PAPER_OUT, '缺纸'),
    'manual_feed':       (PRINTER_STATUS_MANUAL_FEED, '手动进纸'),
    'paper_problem':     (PRINTER_STATUS_PAPER_PROBLEM, '纸张问题'),
    'offline':           (PRINTER_STATUS_OFFLINE, '离线'),
    'io_active':         (PRINTER_STATUS_IO_ACTIVE, 'IO 活动中'),
    'busy':              (PRINTER_STATUS_BUSY, '忙'),
    'printing':          (PRINTER_STATUS_PRINTING, '打印中'),
    'output_bin_full':   (PRINTER_STATUS_OUTPUT_BIN_FULL, '出纸槽已满'),
    'not_available':     (PRINTER_STATUS_NOT_AVAILABLE, '不可用'),
    'waiting':           (PRINTER_STATUS_WAITING, '等待中'),
    'processing':        (PRINTER_STATUS_PROCESSING, '处理中'),
    'initializing':      (PRINTER_STATUS_INITIALIZING, '初始化中'),
    'warming_up':        (PRINTER_STATUS_WARMING_UP, '预热中'),
    'toner_low':         (PRINTER_STATUS_TONER_LOW, '墨量低'),
    'no_toner':          (PRINTER_STATUS_NO_TONER, '缺墨'),
    'page_punt':         (PRINTER_STATUS_PAGE_PUNT, '页跳过'),
    'user_intervention': (PRINTER_STATUS_USER_INTERVENTION, '需用户干预'),
    'out_of_memory':     (PRINTER_STATUS_OUT_OF_MEMORY, '内存不足'),
    'door_open':         (PRINTER_STATUS_DOOR_OPEN, '盖板打开'),
    'power_save':        (PRINTER_STATUS_POWER_SAVE, '节能模式'),
}

# overall 分类
ERROR_BITS = {'offline', 'error', 'paper_jam', 'paper_out', 'no_toner', 'door_open', 'not_available', 'out_of_memory'}
WARNING_BITS = {'toner_low', 'user_intervention', 'output_bin_full', 'manual_feed', 'paper_problem', 'power_save', 'paused'}
BUSY_BITS = {'printing', 'busy', 'io_active', 'processing', 'initializing', 'warming_up'}


def parse_status(status):
    """解析 win32print status 位掩码，返回 (overall, active_statuses)"""
    if status == 0:
        return 'ready', []
    active = []
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
    def __init__(self, broadcaster=None):
        self._broadcaster = broadcaster
        self._stop_evt = threading.Event()
        self._thread = None
        self._cache = {}  # printer_name -> last_status_dict
        self._cache_lock = threading.Lock()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_evt.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info('打印机监控已启动')

    def stop(self):
        self._stop_evt.set()
        logger.info('打印机监控已停止')

    def _loop(self):
        while not self._stop_evt.is_set():
            try:
                self._poll()
            except Exception as e:
                logger.error(f'打印机状态轮询异常: {e}')
            threading.Event().wait(30)

    def _poll(self):
        printers = []
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
                printers.append({
                    'name': name,
                    'overall': overall,
                    'statuses': active,
                })
        except Exception as e:
            logger.warning(f'枚举打印机失败: {e}')
            return

        # 检测变化（在锁内）
        changed = []
        removed = []
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
                except Exception:
                    pass
        for name in removed:
            if self._broadcaster:
                try:
                    self._broadcaster.publish('printer_status', {'name': name, 'overall': 'removed', 'statuses': []})
                except Exception:
                    pass

    def get_all_statuses(self):
        with self._cache_lock:
            return dict(self._cache)

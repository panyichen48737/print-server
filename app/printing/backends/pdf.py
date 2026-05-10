"""PDF 打印后端 — IPP → RAW → Chromium 三阶策略"""

import contextlib
import os
import subprocess
import threading
from pathlib import Path

from loguru import logger

from app.core.exceptions import PrintError
from app.printing.backends.base import PrinterBackend, register
from app.printing.ipp_client import get_printer_ip, print_via_ipp
from app.printing.utils import cancel_all_spooler_jobs


@register('.pdf')
class PdfBackend(PrinterBackend):
    """PDF 打印后端 — IPP(直送) → RAW(Spooler) → Chromium(渲染) 三阶降级"""

    def __init__(self, config):
        self.config = config
        self._active_jobs = {}
        self._active_jobs_lock = threading.Lock()
        self._chrome_path = None

    def print_file(self, filepath, job_id, print_params, _lock=None):
        printer_name = self._resolve_printer(print_params)
        self._track_job(job_id, printer_name, 'pending')

        try:
            # ❶ IPP Everywhere — PDF 直送打印机硬件 RIP，质量最高
            printer_ip = get_printer_ip(printer_name)
            if printer_ip and self._try_ipp(printer_ip, filepath, job_id, print_params):
                return True

            # ❷ RAW — PDF 字节直送 Windows Spooler，零渲染
            if self._try_raw(printer_name, filepath, job_id):
                return True

            # ❸ Chromium — 软件渲染保底
            self._try_chromium(printer_name, filepath, job_id, print_params)
            return True

        except Exception as e:
            logger.error(f'打印失败: {filepath} - {e}')
            raise
        finally:
            with self._active_jobs_lock:
                self._active_jobs.pop(job_id, None)

    # ── 内部方法 ──

    def _track_job(self, job_id, printer_name, method, pid=None):
        with self._active_jobs_lock:
            entry = {'printer': printer_name, 'method': method}
            if pid:
                entry['pid'] = pid
            self._active_jobs[job_id] = entry

    def _resolve_printer(self, print_params):
        printer_name = print_params.get('printer_name') or self.config.get('default_printer', '')
        if not printer_name:
            import win32print

            printer_name = win32print.GetDefaultPrinter()
        return printer_name

    def _try_ipp(self, printer_ip, filepath, job_id, print_params):
        copies = int(print_params.get('copies') or 1)
        duplex = bool(print_params.get('duplex', False))
        try:
            self._track_job(job_id, printer_ip, 'ipp')
            result = print_via_ipp(printer_ip, str(Path(filepath).resolve()), copies, duplex)
            if result:
                logger.info(f'IPP 打印成功: {Path(filepath).name} → {printer_ip}')
                return True
        except Exception as e:
            logger.warning(f'IPP 失败 ({printer_ip}): {e}')
        return False

    def _try_raw(self, printer_name, filepath, job_id):
        import win32print

        try:
            self._track_job(job_id, printer_name, 'raw')
            with open(filepath, 'rb') as f:
                pdf_data = f.read()
            hprinter = win32print.OpenPrinter(printer_name)
            try:
                win32print.StartDocPrinter(hprinter, 1, (Path(filepath).name, None, 'RAW'))
                win32print.WritePrinter(hprinter, pdf_data)
                win32print.EndDocPrinter(hprinter)
            finally:
                win32print.ClosePrinter(hprinter)
            logger.info(f'RAW 打印成功: {Path(filepath).name} → {printer_name}')
            return True
        except Exception as e:
            logger.warning(f'RAW 失败 ({printer_name}): {e}')
            return False

    def _try_chromium(self, printer_name, filepath, job_id, _print_params):
        chrome_path = self._find_chromium()
        if not chrome_path:
            raise PrintError('未找到 Chromium 浏览器 (Chrome/Edge)')

        # 净化打印机名称：移除可能干扰 Chrome 参数解析的字符
        safe_printer = printer_name.replace('"', '').replace("'", '')

        proc = subprocess.Popen(
            [
                chrome_path,
                '--headless',
                '--disable-gpu',
                f'--print-to-printer="{safe_printer}"',
                '--no-margins',
                '--no-pdf-header-footer',
                str(Path(filepath).resolve()),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._track_job(job_id, printer_name, 'chromium', pid=proc.pid)

        _, stderr = proc.communicate(timeout=self.config.get('job_timeout', 300))
        if proc.returncode != 0:
            raise PrintError(
                f'Chrome 打印失败: {proc.returncode}\n{stderr[:500].decode("utf-8", errors="replace")}'
            )

    def cancel(self, job_id, _info):
        with self._active_jobs_lock:
            job_info = self._active_jobs.get(job_id)
        if job_info:
            pid = job_info.get('pid')
            if pid:
                with contextlib.suppress(Exception):
                    subprocess.run(
                        ['taskkill', '/F', '/PID', str(pid)], capture_output=True, timeout=5
                    )
            cancel_all_spooler_jobs(job_info['printer'])
        return True

    def get_active_job(self, job_id):
        with self._active_jobs_lock:
            return self._active_jobs.get(job_id)

    def _find_chromium(self):
        if self._chrome_path:
            return self._chrome_path

        browsers = ['msedge.exe', 'chrome.exe']
        for browser in browsers:
            try:
                result = subprocess.run(['where', browser], capture_output=True, text=True)
                if result.returncode == 0:
                    path = result.stdout.strip().split('\n')[0]
                    if Path(path).exists():
                        self._chrome_path = path
                        return path
            except Exception:
                pass

        candidates = [
            os.path.expandvars(r'%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe'),
            os.path.expandvars(r'%ProgramFiles%\Microsoft\Edge\Application\msedge.exe'),
            os.path.expandvars(r'%LocalAppData%\Microsoft\Edge\Application\msedge.exe'),
            os.path.expandvars(r'%ProgramFiles%\Google\Chrome\Application\chrome.exe'),
            os.path.expandvars(r'%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe'),
            os.path.expandvars(r'%LocalAppData%\Google\Chrome\Application\chrome.exe'),
        ]
        for path in candidates:
            if Path(path).exists():
                self._chrome_path = path
                return path
        return None

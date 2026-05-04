"""PDF 打印后端（Chromium headless）"""
import os
import logging
import subprocess
import threading

from app.printing.backends.base import PrinterBackend

logger = logging.getLogger('print_server')


def _cancel_all_spooler_jobs(printer_name):
    import win32print
    try:
        handle = win32print.OpenPrinter(printer_name)
        try:
            info = win32print.GetPrinter(handle, 2)
            for job in info.get('cJobs', []):
                win32print.SetJob(handle, job['JobId'], 0, win32print.JOB_CONTROL_DELETE)
        finally:
            win32print.ClosePrinter(handle)
    except Exception as e:
        logger.warning(f'取消 Spooler 作业失败: {e}')


class PdfBackend(PrinterBackend):
    """使用 Chromium (Chrome/Edge) headless 打印 PDF"""

    def __init__(self, config):
        self.config = config
        self._active_jobs = {}
        self._active_jobs_lock = threading.Lock()

    def print_file(self, filepath, job_id, print_params, lock=None):
        chrome_path = self._find_chromium()
        if not chrome_path:
            raise RuntimeError('未找到 Chromium 浏览器 (Chrome/Edge)')

        printer_name = print_params.get('printer_name') or self.config.get('default_printer', '')
        if not printer_name:
            import win32print
            printer_name = win32print.GetDefaultPrinter()

        proc = subprocess.Popen(
            [chrome_path, '--headless', '--disable-gpu',
             f'--print-to-printer="{printer_name}"',
             '--no-margins', '--no-pdf-header-footer',
             os.path.abspath(filepath)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        with self._active_jobs_lock:
            self._active_jobs[job_id] = {
                'printer': printer_name,
                'pid': proc.pid,
                'method': 'chromium'
            }
        stdout, stderr = proc.communicate(timeout=self.config.get('job_timeout', 300))
        if proc.returncode != 0:
            raise RuntimeError(f'Chrome 打印失败: {proc.returncode}\n{stderr[:500]}')
        with self._active_jobs_lock:
            self._active_jobs.pop(job_id, None)

        logger.info(f'Chromium PDF 打印成功: {filepath}')
        return True

    def cancel(self, job_id, info):
        pid = info.get('pid')
        if pid:
            try:
                subprocess.run(['taskkill', '/F', '/PID', str(pid)], capture_output=True, timeout=5)
            except Exception:
                pass
        _cancel_all_spooler_jobs(info['printer'])
        return True

    def _find_chromium(self):
        """查找 Edge 或 Chrome 的安装路径（优先 Edge）"""
        try:
            result = subprocess.run(['where', 'msedge.exe'], capture_output=True, text=True)
            if result.returncode == 0:
                path = result.stdout.strip().split('\n')[0]
                if os.path.exists(path):
                    return path
        except Exception:
            pass
        try:
            result = subprocess.run(['where', 'chrome.exe'], capture_output=True, text=True)
            if result.returncode == 0:
                path = result.stdout.strip().split('\n')[0]
                if os.path.exists(path):
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
            expanded = os.path.expandvars(path)
            if os.path.exists(expanded):
                return expanded
        return None

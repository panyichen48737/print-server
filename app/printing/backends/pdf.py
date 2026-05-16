"""PDF 打印后端 — IPP → RAW → Chromium 三阶策略"""

import contextlib
import os
import subprocess
import tempfile
import threading
from pathlib import Path

from loguru import logger

from app.core.exceptions import PrintError
from app.printing.backends.base import PrinterBackend, cancel_all_spooler_jobs, register
from app.printing.ipp_client import get_printer_ip, print_via_ipp


@register('.pdf')
class PdfBackend(PrinterBackend):
    """PDF 打印后端 — IPP(直送) → RAW(Spooler) → Chromium(渲染) 三阶降级"""

    def __init__(self, config):
        self.config = config
        self._active_jobs = {}
        self._active_jobs_lock = threading.Lock()
        self._chrome_path = None

    def print_file(self, filepath, job_id, print_params, _lock=None):
        prepared = self._prepare_pdf(filepath, print_params)
        try:
            printer_name = self._resolve_printer(print_params)
            self._track_job(job_id, printer_name, 'pending')

            try:
                # ❶ IPP Everywhere — PDF 直送打印机硬件 RIP，质量最高
                printer_ip = get_printer_ip(printer_name)
                if printer_ip and self._try_ipp(printer_ip, prepared, job_id, print_params):
                    return True

                # ❷ RAW — PDF 字节直送 Windows Spooler，零渲染
                if self._try_raw(printer_name, prepared, job_id):
                    return True

                # ❸ Chromium — 软件渲染保底
                self._try_chromium(printer_name, prepared, job_id, print_params)
                return True

            except Exception as e:
                logger.error(f'打印失败: {filepath} - {e}')
                raise
            finally:
                with self._active_jobs_lock:
                    self._active_jobs.pop(job_id, None)
        finally:
            # Clean up temporary PDF if _prepare_pdf created one
            if prepared != filepath:
                Path(prepared).unlink(missing_ok=True)

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

    # ── 页码范围 + N-up 预处理 ──

    def _parse_page_range(self, spec: str, total: int) -> list[int]:
        """Parse '1-3,5,7-9' into [0,1,2,4,6,7,8] (0-indexed)."""
        if not spec or not spec.strip():
            return list(range(total))
        pages: list[int] = []
        for part in spec.split(','):
            part = part.strip()
            if not part:
                continue
            if '-' in part:
                try:
                    start, end = part.split('-', 1)
                    s, e = int(start.strip()), int(end.strip())
                    if s > e:
                        s, e = e, s
                    pages.extend(range(max(1, s), min(e, total) + 1))
                except ValueError:
                    continue
            else:
                try:
                    pages.append(int(part))
                except ValueError:
                    continue
        result = sorted(set(p for p in pages if 1 <= p <= total))
        return [p - 1 for p in result]  # convert to 0-indexed

    def _prepare_pdf(self, filepath: str, print_params: dict) -> str:
        """Apply page range and N-up transformations. Returns path to final PDF."""
        import fitz

        current = filepath

        # Step 1: Page range
        page_range = print_params.get('page_range', '')
        if page_range and page_range.strip():
            doc = fitz.open(current)
            total = len(doc)
            pages = self._parse_page_range(page_range, total)
            if pages and len(pages) < total:
                new_doc = fitz.open()
                for p in pages:
                    new_doc.insert_pdf(doc, from_page=p, to_page=p)
                with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
                    tmp_path = tmp.name
                new_doc.save(tmp_path)
                new_doc.close()
                doc.close()
                current = tmp_path
            else:
                doc.close()

        # Step 2: N-up
        nup = int(print_params.get('nup', 1))
        if nup > 1:
            from app.printing.backends.pdf_render import nup_compose

            composed = nup_compose(current, nup)
            if composed != current:
                # Clean up intermediate file from step 1
                if current != filepath:
                    Path(current).unlink(missing_ok=True)
                current = composed

        return current

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

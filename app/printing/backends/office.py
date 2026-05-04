"""Office 文档打印后端（Word/Excel/PPT via win32com）"""
import os
import logging
import threading
from contextlib import contextmanager

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


class OfficeBackend(PrinterBackend):
    """Word / Excel / PowerPoint 打印"""

    def __init__(self, config, excel_lock=None, ppt_lock=None):
        self.config = config
        self.excel_lock = excel_lock or threading.Lock()
        self.ppt_lock = ppt_lock or threading.Lock()
        self._active_jobs = {}
        self._active_jobs_lock = threading.Lock()

    # ------------------------------------------------------------------ #
    #  上下文管理器：COM 初始化 / 清理
    # ------------------------------------------------------------------ #
    @contextmanager
    def _com_context(self, app_name, lock, job_id, print_params, display_alerts=None):
        printer_name = print_params.get('printer_name') or self.config.get('default_printer', '')
        with self._active_jobs_lock:
            self._active_jobs[job_id] = {
                'printer': printer_name,
                'method': 'com'
            }
        with lock:
            import win32com.client
            import pythoncom
            app = None
            try:
                pythoncom.CoInitialize()
                app = win32com.client.Dispatch(app_name)
                app.Visible = False
                if display_alerts is not None:
                    app.DisplayAlerts = display_alerts
                if printer_name:
                    app.ActivePrinter = printer_name
                yield app
            finally:
                try:
                    if app:
                        app.Quit(SaveChanges=0)
                except Exception:
                    pass
                try:
                    pythoncom.CoUninitialize()
                except Exception:
                    pass
                with self._active_jobs_lock:
                    self._active_jobs.pop(job_id, None)

    # ------------------------------------------------------------------ #
    #  主入口
    # ------------------------------------------------------------------ #
    def print_file(self, filepath, job_id, print_params, lock=None):
        ext = print_params.get('_file_type', '').lower()
        if ext in ('.doc', '.docx'):
            return self._print_word(filepath, job_id, lock, print_params)
        elif ext in ('.xls', '.xlsx'):
            return self._print_excel(filepath, job_id, print_params)
        elif ext in ('.ppt', '.pptx'):
            return self._print_ppt(filepath, job_id, print_params)
        raise ValueError(f'Office 后端不支持的文件类型: {ext}')

    # ------------------------------------------------------------------ #
    #  Word
    # ------------------------------------------------------------------ #
    def _print_word(self, filepath, job_id, word_lock, print_params=None):
        if print_params is None:
            print_params = {}
        with self._com_context('Word.Application', word_lock, job_id, print_params, display_alerts=0) as word:
            doc = word.Documents.Open(os.path.abspath(filepath))
            copies = print_params.get('copies') or self.config.get('default_copies', 1)
            doc.PrintOut(Background=False, Copies=copies)
            doc.Close(SaveChanges=0)
        return True

    # ------------------------------------------------------------------ #
    #  Excel
    # ------------------------------------------------------------------ #
    def _print_excel(self, filepath, job_id, print_params=None):
        if print_params is None:
            print_params = {}
        with self._com_context('Excel.Application', self.excel_lock, job_id, print_params, display_alerts=False) as excel:
            workbook = excel.Workbooks.Open(os.path.abspath(filepath))
            copies = print_params.get('copies') or self.config.get('default_copies', 1)
            all_sheets = self.config.get('excel_print_all_sheets', True)
            if all_sheets:
                for ws in workbook.Worksheets:
                    ws.Select(False)
            workbook.PrintOut(Copies=copies)
            workbook.Close(SaveChanges=False)
        return True

    # ------------------------------------------------------------------ #
    #  PowerPoint
    # ------------------------------------------------------------------ #
    def _print_ppt(self, filepath, job_id, print_params=None):
        if print_params is None:
            print_params = {}
        with self._com_context('PowerPoint.Application', self.ppt_lock, job_id, print_params) as ppt:
            presentation = ppt.Presentations.Open(os.path.abspath(filepath))
            copies = print_params.get('copies') or self.config.get('default_copies', 1)
            output_type = self.config.get('ppt_output_type', 'slides')
            output_map = {
                'slides': 1,
                'handout2': 2,
                'handout3': 3,
                'handout6': 4,
            }
            presentation.PrintOptions.OutputType = output_map.get(output_type, 1)
            presentation.PrintOut(Copies=copies)
            presentation.Close(SaveChanges=0)
        return True

    # ------------------------------------------------------------------ #
    #  取消
    # ------------------------------------------------------------------ #
    def cancel(self, job_id, info):
        _cancel_all_spooler_jobs(info['printer'])
        return True

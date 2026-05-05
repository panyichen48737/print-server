"""Office 文档 → PDF 转换（win32com），然后通过 PDF 后端打印"""

import contextlib
import os
import threading
from contextlib import contextmanager
from tempfile import NamedTemporaryFile

from app.exceptions import FileTypeError, PrintError
from app.printing.backends.base import PrinterBackend, register


@register('.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx')
class OfficeBackend(PrinterBackend):
    """Word / Excel / PowerPoint → PDF 转换器"""

    def __init__(self, config, excel_lock=None, ppt_lock=None):
        self.config = config
        self.excel_lock = excel_lock or threading.Lock()
        self.ppt_lock = ppt_lock or threading.Lock()

    @contextmanager
    def _com_context(self, app_name, lock, display_alerts=None):
        with lock:
            import win32com.client

            app = None
            try:
                app = win32com.client.Dispatch(app_name)
                app.Visible = False
                if display_alerts is not None:
                    app.DisplayAlerts = display_alerts
                yield app
            finally:
                if app:
                    with contextlib.suppress(Exception):
                        app.Quit(SaveChanges=0)

    # ── 外部入口 ──

    def convert_to_pdf(self, filepath: str, print_params: dict) -> str:
        """打开 Office 文件并另存为 PDF，返回临时 PDF 路径"""
        ext = print_params.get('_file_type', '').lower()
        with NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            pdf_path = tmp.name

        if ext in ('.doc', '.docx'):
            self._word_to_pdf(filepath, pdf_path, print_params)
        elif ext in ('.xls', '.xlsx'):
            self._excel_to_pdf(filepath, pdf_path, print_params)
        elif ext in ('.ppt', '.pptx'):
            self._ppt_to_pdf(filepath, pdf_path, print_params)
        else:
            raise FileTypeError(f'Office 后端不支持的文件类型: {ext}')

        return pdf_path

    # ── 转换方法 ──

    def _word_to_pdf(self, filepath, pdf_path, print_params):
        word_lock = print_params.get('_word_lock')
        with self._com_context('Word.Application', word_lock, display_alerts=0) as word:
            doc = word.Documents.Open(os.path.abspath(filepath))
            try:
                doc.SaveAs2(pdf_path, FileFormat=17)  # wdFormatPDF
            finally:
                doc.Close(SaveChanges=0)

    def _excel_to_pdf(self, filepath, pdf_path, _print_params):
        with self._com_context('Excel.Application', self.excel_lock, display_alerts=False) as excel:
            wb = excel.Workbooks.Open(os.path.abspath(filepath))
            try:
                wb.ExportAsFixedFormat(0, pdf_path)  # xlTypePDF
            finally:
                wb.Close(SaveChanges=False)

    def _ppt_to_pdf(self, filepath, pdf_path, _print_params):
        with self._com_context('PowerPoint.Application', self.ppt_lock) as ppt:
            pres = ppt.Presentations.Open(os.path.abspath(filepath))
            try:
                pres.SaveAs(pdf_path, 32)  # ppSaveAsPDF
            finally:
                pres.Close(SaveChanges=0)

    # ── PrinterBackend 存根（实际打印委托给 PdfBackend）──

    def print_file(self, _filepath, _job_id, _print_params, _lock=None):
        raise PrintError('OfficeBackend 不再直接打印，请通过 convert_to_pdf + PdfBackend')

    def cancel(self, _job_id, _info):
        return True

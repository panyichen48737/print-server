"""图片打印后端（PIL 排版 + GDI 渲染）"""
import os
import io
import logging
import threading

from PIL import Image, ImageOps, ImageWin
import win32print
import win32ui
import win32gui
import win32con

from app.printing.backends.base import PrinterBackend
from app.printing.enhancer import QuarkEnhancer

logger = logging.getLogger('print_server')

HORZRES = 110
VERTRES = 111


def _cancel_all_spooler_jobs(printer_name):
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


class ImageBackend(PrinterBackend):
    """图片打印：Quark API 预处理 → PIL 排版 → GDI 渲染"""

    def __init__(self, config):
        self.config = config
        self._quark = QuarkEnhancer(config)
        self._active_jobs = {}
        self._active_jobs_lock = threading.Lock()

    def print_file(self, filepath, job_id, print_params, lock=None):
        return self._print_image(filepath, job_id, print_params)

    def cancel(self, job_id, info):
        if info['method'] == 'gdi':
            handle = win32print.OpenPrinter(info['printer'])
            try:
                win32print.SetJob(handle, info['spool_job_id'], 0, win32print.JOB_CONTROL_DELETE)
                logger.info(f'GDI Spooler 作业 #{info["spool_job_id"]} 已取消')
            finally:
                win32print.ClosePrinter(handle)
            return True
        return False

    def _print_image(self, filepath, job_id, print_params=None):
        if print_params is None:
            print_params = {}
        try:
            # Step 1: Quark API 预处理
            processed = self._quark.enhance(filepath)

            # Step 2: 加载图片
            if processed:
                img = Image.open(io.BytesIO(processed))
            else:
                img = Image.open(filepath)

            # Auto rotate based on EXIF
            if self.config.get('auto_rotate', True):
                try:
                    img = ImageOps.exif_transpose(img)
                except Exception:
                    pass

            # Step 3: 适配 A4 居中
            dpi = self.config.get('print_dpi', 300)
            paper_size = print_params.get('paper_size') or self.config.get('paper_size', 'A4')
            if paper_size == 'A4':
                pw, ph = int(8.27 * dpi), int(11.69 * dpi)
            elif paper_size == 'Letter':
                pw, ph = int(8.5 * dpi), int(11 * dpi)
            elif paper_size == 'A3':
                pw, ph = int(11.69 * dpi), int(16.54 * dpi)
            else:
                pw, ph = int(8.27 * dpi), int(11.69 * dpi)

            img_w, img_h = img.size
            if (img_w > img_h and pw < ph) or (img_w < img_h and pw > ph):
                pw, ph = ph, pw

            scale = min(pw / img_w, ph / img_h)
            new_w = int(img_w * scale)
            new_h = int(img_h * scale)

            color_val = print_params.get('color')
            if color_val is not None:
                use_color = bool(color_val)
            else:
                use_color = self.config.get('default_color', True)

            if use_color:
                canvas = Image.new('RGB', (pw, ph), (255, 255, 255))
                img_resized = img.resize((new_w, new_h), Image.LANCZOS)
            else:
                canvas = Image.new('L', (pw, ph), (255))
                img_resized = img.resize((new_w, new_h), Image.LANCZOS).convert('L')

            x = (pw - new_w) // 2
            y = (ph - new_h) // 2
            if img_resized.mode == 'RGBA':
                canvas.paste(img_resized, (x, y), img_resized)
            elif img_resized.mode == 'P':
                img_resized = img_resized.convert('RGBA')
                canvas.paste(img_resized, (x, y), img_resized)
            else:
                canvas.paste(img_resized, (x, y))

            # Step 4: Print via GDI
            self._send_to_printer(canvas, job_id, print_params)

            return True

        except Exception as e:
            logger.error(f'图片打印失败: {e}')
            raise

    def _send_to_printer(self, pil_image, job_id, print_params=None):
        if print_params is None:
            print_params = {}

        printer_name = print_params.get('printer_name') or self.config.get('default_printer', '')
        if not printer_name:
            printer_name = win32print.GetDefaultPrinter()

        logger.info(f'ImageBackend: image={pil_image.size} mode={pil_image.mode} printer={printer_name}')

        img_w, img_h = pil_image.size
        need_landscape = img_w > img_h

        handle = win32print.OpenPrinter(printer_name)
        try:
            dm = win32print.GetPrinter(handle, 2)['pDevMode']
            dm.Orientation = 2 if need_landscape else 1
            dm.Fields = dm.Fields | win32con.DM_ORIENTATION

            duplex_val = print_params.get('duplex')
            if duplex_val is not None:
                dm.Duplex = 2 if duplex_val else 1
                dm.Fields = dm.Fields | win32con.DM_DUPLEX
            elif self.config.get('default_duplex', False):
                dm.Duplex = 2
                dm.Fields = dm.Fields | win32con.DM_DUPLEX
            else:
                dm.Duplex = 1
                dm.Fields = dm.Fields | win32con.DM_DUPLEX

            dc_handle = win32gui.CreateDC('WINSPOOL', printer_name, dm)
        finally:
            win32print.ClosePrinter(handle)

        hdc = win32ui.CreateDCFromHandle(dc_handle)

        try:
            spool_job_id = hdc.StartDoc('Print Job')
            with self._active_jobs_lock:
                self._active_jobs[job_id] = {
                    'printer': printer_name,
                    'spool_job_id': spool_job_id,
                    'method': 'gdi'
                }
            try:
                hdc.StartPage()

                page_width = hdc.GetDeviceCaps(HORZRES)
                page_height = hdc.GetDeviceCaps(VERTRES)

                color_val = print_params.get('color')
                if color_val is not None:
                    use_color = bool(color_val)
                else:
                    use_color = self.config.get('default_color', True)

                if use_color:
                    img = pil_image.convert('RGB')
                else:
                    img = pil_image.convert('L')

                img_w, img_h = img.size
                scale = min(page_width / img_w, page_height / img_h)
                draw_w = int(img_w * scale)
                draw_h = int(img_h * scale)
                x = (page_width - draw_w) // 2
                y = (page_height - draw_h) // 2

                dib = ImageWin.Dib(img)
                dib.draw(hdc.GetHandleOutput(), (x, y, x + draw_w, y + draw_h))

                hdc.EndPage()
                hdc.EndDoc()
                logger.info(f'GDI 打印发送成功: 页面 {page_width}x{page_height}, 图片 {draw_w}x{draw_h}')
            except Exception:
                raise
        finally:
            hdc.DeleteDC()
            with self._active_jobs_lock:
                self._active_jobs.pop(job_id, None)

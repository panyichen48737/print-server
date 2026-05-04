"""图片打印后端（现代化方式：PIL 排版 → PDF → Chromium 打印）"""
import os
import io
import tempfile
from loguru import logger

from PIL import Image, ImageOps

from app.printing.backends.base import PrinterBackend
from app.printing.backends.pdf import PdfBackend
from app.printing.enhancer import QuarkEnhancer


class ImageBackend(PrinterBackend):
    """图片打印：Quark API 预处理 → PIL 排版 → PDF 中间格式 → Chromium 打印"""

    PAPER_SIZES = {
        'A4':     (8.27, 11.69),
        'Letter': (8.5,  11.0),
        'A3':     (11.69, 16.54),
    }

    def __init__(self, config, pdf_backend: PdfBackend = None):
        self.config = config
        self._quark = QuarkEnhancer(config)
        self._pdf_backend = pdf_backend or PdfBackend(config)

    def print_file(self, filepath, job_id, print_params, lock=None):
        return self._print_image(filepath, job_id, print_params)

    def cancel(self, job_id, info):
        """委托给 PdfBackend 的取消逻辑（kill Chrome PID + 清理 Spooler）"""
        pdf_info = self._pdf_backend.get_active_job(job_id)
        if pdf_info:
            return self._pdf_backend.cancel(job_id, pdf_info)
        return False

    def _print_image(self, filepath, job_id, print_params=None):
        print_params = print_params or {}
        try:
            processed = self._quark.enhance(filepath)

            if processed:
                img = Image.open(io.BytesIO(processed))
            else:
                img = Image.open(filepath)

            if self.config.get('auto_rotate', True):
                try:
                    img = ImageOps.exif_transpose(img)
                except Exception:
                    pass

            dpi = self.config.get('print_dpi', 300)
            paper_size = print_params.get('paper_size') or self.config.get('paper_size', 'A4')
            dims = self.PAPER_SIZES.get(paper_size, (8.27, 11.69))
            pw, ph = int(dims[0] * dpi), int(dims[1] * dpi)

            img_w, img_h = img.size
            if (img_w > img_h and pw < ph) or (img_w < img_h and pw > ph):
                pw, ph = ph, pw

            scale = min(pw / img_w, ph / img_h)
            new_w, new_h = int(img_w * scale), int(img_h * scale)

            color_val = print_params.get('color')
            use_color = bool(color_val) if color_val is not None else self.config.get('default_color', True)

            mode = 'RGB' if use_color else 'L'
            canvas = Image.new(mode, (pw, ph), 255)
            img_resized = img.resize((new_w, new_h), Image.LANCZOS)
            if mode == 'L':
                img_resized = img_resized.convert('L')

            x = (pw - new_w) // 2
            y = (ph - new_h) // 2
            if img_resized.mode in ('RGBA', 'P'):
                if img_resized.mode == 'P':
                    img_resized = img_resized.convert('RGBA')
                canvas.paste(img_resized, (x, y), img_resized)
            else:
                canvas.paste(img_resized, (x, y))

            temp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
            try:
                canvas.save(temp_pdf, 'PDF', resolution=dpi)
                temp_pdf.close()
                logger.info(f'图片已渲染为 PDF 临时文件: {temp_pdf.name}')
                return self._pdf_backend.print_file(temp_pdf.name, job_id, print_params)
            finally:
                try:
                    os.unlink(temp_pdf.name)
                except Exception as e:
                    logger.warning(f'删除临时 PDF 失败: {temp_pdf.name} - {e}')

        except Exception as e:
            logger.error(f'图片打印失败: {e}')
            raise

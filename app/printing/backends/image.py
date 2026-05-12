"""图片打印后端（现代化方式：PIL 排版 → PDF → Chromium 打印）"""

import contextlib
import io
import tempfile
from typing import ClassVar

from loguru import logger
from PIL import Image, ImageOps

from app.core.utils import safe_remove
from app.printing.backends.base import PrinterBackend, register
from app.printing.backends.pdf import PdfBackend
from app.services.image_processing import QuarkEnhancer


@register('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp', '.tiff', '.tif', '.heic', '.heif')
class ImageBackend(PrinterBackend):
    """图片打印：Quark API 预处理 → PIL 排版 → PDF 中间格式 → Chromium 打印"""

    PAPER_SIZES: ClassVar[dict[str, tuple[float, float]]] = {
        'A4': (8.27, 11.69),
        'Letter': (8.5, 11.0),
        'A3': (11.69, 16.54),
    }

    def __init__(self, config, pdf_backend: PdfBackend):
        self.config = config
        self._quark = QuarkEnhancer(config)
        self._pdf_backend = pdf_backend

    def print_file(self, filepath, job_id, print_params, _lock=None):
        return self._print_image(filepath, job_id, print_params)

    def cancel(self, job_id, _info):
        """委托给 PdfBackend 的取消逻辑（kill Chrome PID + 清理 Spooler）"""
        pdf_info = self._pdf_backend.get_active_job(job_id)
        if pdf_info:
            return self._pdf_backend.cancel(job_id, pdf_info)
        return False

    def _print_image(self, filepath, job_id, print_params=None):
        print_params = print_params or {}
        try:
            processed = self._quark.enhance(filepath)
            img = Image.open(io.BytesIO(processed))

            if self.config.get('auto_rotate', True):
                with contextlib.suppress(Exception):
                    img = ImageOps.exif_transpose(img)

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
            use_color = (
                bool(color_val) if color_val is not None else self.config.get('default_color', True)
            )

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

            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_pdf:
                canvas.save(temp_pdf, 'PDF', resolution=dpi)
                pdf_path = temp_pdf.name
            logger.info(f'图片已渲染为 PDF 临时文件: {pdf_path}')
            try:
                return self._pdf_backend.print_file(pdf_path, job_id, print_params)
            finally:
                safe_remove(pdf_path, '临时 PDF')

        except Exception as e:
            logger.error(f'图片打印失败: {e}')
            raise

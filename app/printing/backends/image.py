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
    """图片打印：Quark API 预处理 → PIL 排版 → PDF 中间格式 → Chromium 打印

    相较于传统 GDI 方案：
    - 色彩管理由 Chrome 引擎处理，更准确
    - 打印机驱动兼容性更好（不依赖 GDI 设备上下文）
    - 支持更高级的渲染特性（ICC 配置文件、抗锯齿等）
    - 复用 PdfBackend，减少重复代码
    """

    def __init__(self, config):
        self.config = config
        self._quark = QuarkEnhancer(config)
        self._pdf_backend = PdfBackend(config)

    def print_file(self, filepath, job_id, print_params, lock=None):
        return self._print_image(filepath, job_id, print_params)

    def cancel(self, job_id, info):
        """委托给 PdfBackend 的取消逻辑（kill Chrome PID + 清理 Spooler）"""
        pdf_info = self._pdf_backend.get_active_job(job_id)
        if pdf_info:
            return self._pdf_backend.cancel(job_id, pdf_info)
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

            # Step 3: 适配纸张尺寸（dpi 决定页面物理大小）
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

            # 自动匹配方向：横图横排，竖图竖排
            img_w, img_h = img.size
            if (img_w > img_h and pw < ph) or (img_w < img_h and pw > ph):
                pw, ph = ph, pw

            # 等比缩放并居中
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

            # Step 4: 保存为 PDF 临时文件 → 委托 PdfBackend 打印
            temp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
            try:
                canvas.save(temp_pdf, 'PDF', resolution=dpi)
                temp_pdf.close()
                logger.info(f'图片已渲染为 PDF 临时文件: {temp_pdf.name}')
                return self._pdf_backend.print_file(temp_pdf.name, job_id, print_params)
            finally:
                try:
                    if os.path.exists(temp_pdf.name):
                        os.unlink(temp_pdf.name)
                except Exception as e:
                    logger.warning(f'删除临时 PDF 失败: {temp_pdf.name} - {e}')

        except Exception as e:
            logger.error(f'图片打印失败: {e}')
            raise

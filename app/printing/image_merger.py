"""多图片合并为多页 PDF — 支持排序后合并打印"""

from __future__ import annotations

import contextlib
import os
import tempfile

from PIL import Image, ImageOps

from app.core.utils import safe_remove

PAPER_SIZES: dict[str, tuple[float, float]] = {
    'A4': (8.27, 11.69),
    'Letter': (8.5, 11.0),
    'A3': (11.69, 16.54),
}


def merge_images_to_pdf(
    image_paths: list[str],
    *,
    dpi: int = 300,
    paper_size: str = 'A4',
    auto_rotate: bool = True,
    color: bool = True,
) -> str:
    """将多张图片按顺序合并为一个多页 PDF，返回临时 PDF 路径。

    每张图片独立排版在一页纸上，图片居中、缩放适应页面。
    """
    if not image_paths:
        raise ValueError('至少需要一张图片')

    dims = PAPER_SIZES.get(paper_size, (8.27, 11.69))
    pw, ph = int(dims[0] * dpi), int(dims[1] * dpi)
    mode = 'RGB' if color else 'L'

    pages: list[Image.Image] = []
    for path in image_paths:
        img = Image.open(path)
        if auto_rotate:
            with contextlib.suppress(Exception):
                img = ImageOps.exif_transpose(img)

        img_w, img_h = img.size
        page_w, page_h = pw, ph
        if (img_w > img_h and page_w < page_h) or (img_w < img_h and page_w > page_h):
            page_w, page_h = ph, pw

        scale = min(page_w / img_w, page_h / img_h)
        new_w, new_h = int(img_w * scale), int(img_h * scale)

        canvas = Image.new(mode, (page_w, page_h), 255)
        img_resized = img.resize((new_w, new_h), Image.LANCZOS)
        if mode == 'L':
            img_resized = img_resized.convert('L')

        x = (page_w - new_w) // 2
        y = (page_h - new_h) // 2
        if img_resized.mode in ('RGBA', 'P'):
            if img_resized.mode == 'P':
                img_resized = img_resized.convert('RGBA')
            canvas.paste(img_resized, (x, y), img_resized)
        else:
            canvas.paste(img_resized, (x, y))
        pages.append(canvas)

    if not pages:
        raise RuntimeError('没有可合并的图片')

    # 多页 PDF：第一页用 save，后续页用 append_images
    first = pages[0]
    rest = pages[1:] if len(pages) > 1 else None

    fd, pdf_path = tempfile.mkstemp(suffix='.pdf')
    os.close(fd)
    try:
        if rest:
            first.save(pdf_path, 'PDF', resolution=dpi, save_all=True, append_images=rest)
        else:
            first.save(pdf_path, 'PDF', resolution=dpi)
    except Exception:
        safe_remove(pdf_path, '合并 PDF')
        raise

    return pdf_path

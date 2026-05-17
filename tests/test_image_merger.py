"""测试多图片合并为多页 PDF"""

import io
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from app.printing.image_merger import merge_images_to_pdf


def _create_test_image(size=(100, 100), color=(255, 0, 0), mode='RGB') -> bytes:
    """生成测试图片字节"""
    img = Image.new(mode, size, color)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def _save_temp_image(data: bytes, suffix='.png') -> str:
    """保存测试图片到临时文件，返回路径"""
    import tempfile

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
        f.write(data)
        return f.name


class TestMergeImagesToPdf:
    """测试 merge_images_to_pdf 函数"""

    def test_single_image(self):
        """单张图片应生成单页 PDF"""
        img_path = _save_temp_image(_create_test_image())
        try:
            pdf_path = merge_images_to_pdf([img_path])
            assert Path(pdf_path).exists()
            assert Path(pdf_path).suffix == '.pdf'
            # 验证 PDF 文件非空
            assert Path(pdf_path).stat().st_size > 0
        finally:
            Path(img_path).unlink(missing_ok=True)
            Path(pdf_path).unlink(missing_ok=True)

    def test_multiple_images(self):
        """多张图片应生成多页 PDF"""
        img_paths = []
        colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
        for c in colors:
            img_paths.append(_save_temp_image(_create_test_image(color=c)))
        try:
            pdf_path = merge_images_to_pdf(img_paths)
            assert Path(pdf_path).exists()
            assert Path(pdf_path).stat().st_size > 0
        finally:
            for p in img_paths:
                Path(p).unlink(missing_ok=True)
            Path(pdf_path).unlink(missing_ok=True)

    def test_empty_list_raises(self):
        """空图片列表应抛出 ValueError"""
        with pytest.raises(ValueError, match='至少需要一张图片'):
            merge_images_to_pdf([])

    def test_different_paper_sizes(self):
        """不同纸张大小应正常生成"""
        img_path = _save_temp_image(_create_test_image())
        try:
            for size in ('A4', 'Letter', 'A3'):
                pdf_path = merge_images_to_pdf([img_path], paper_size=size)
                assert Path(pdf_path).exists()
                assert Path(pdf_path).stat().st_size > 0
                Path(pdf_path).unlink(missing_ok=True)
        finally:
            Path(img_path).unlink(missing_ok=True)

    def test_grayscale_mode(self):
        """灰度模式应正常生成"""
        img_path = _save_temp_image(_create_test_image(mode='L', color=128))
        try:
            pdf_path = merge_images_to_pdf([img_path], color=False)
            assert Path(pdf_path).exists()
            assert Path(pdf_path).stat().st_size > 0
        finally:
            Path(img_path).unlink(missing_ok=True)
            Path(pdf_path).unlink(missing_ok=True)

    def test_rgba_image(self):
        """RGBA 图片应正常处理"""
        img_path = _save_temp_image(_create_test_image(mode='RGBA', color=(255, 0, 0, 128)))
        try:
            pdf_path = merge_images_to_pdf([img_path])
            assert Path(pdf_path).exists()
            assert Path(pdf_path).stat().st_size > 0
        finally:
            Path(img_path).unlink(missing_ok=True)
            Path(pdf_path).unlink(missing_ok=True)

    def test_large_image_ratio_handling(self):
        """横向图片应自动旋转纸张方向"""
        # 宽图（横向）
        img_path = _save_temp_image(_create_test_image(size=(300, 100)))
        try:
            pdf_path = merge_images_to_pdf([img_path], paper_size='A4')
            assert Path(pdf_path).exists()
            assert Path(pdf_path).stat().st_size > 0
        finally:
            Path(img_path).unlink(missing_ok=True)
            Path(pdf_path).unlink(missing_ok=True)

    def test_portrait_image(self):
        """纵向图片正常排版"""
        img_path = _save_temp_image(_create_test_image(size=(100, 300)))
        try:
            pdf_path = merge_images_to_pdf([img_path])
            assert Path(pdf_path).exists()
            assert Path(pdf_path).stat().st_size > 0
        finally:
            Path(img_path).unlink(missing_ok=True)
            Path(pdf_path).unlink(missing_ok=True)

"""PDF 后端测试 — 页码范围"""

from unittest.mock import MagicMock

import fitz

from app.printing.backends.pdf import PdfBackend


def test_parse_page_range_all():
    backend = PdfBackend(MagicMock())
    assert backend._parse_page_range('', 5) == [0, 1, 2, 3, 4]


def test_parse_page_range_simple():
    backend = PdfBackend(MagicMock())
    assert backend._parse_page_range('1-3', 10) == [0, 1, 2]


def test_parse_page_range_complex():
    backend = PdfBackend(MagicMock())
    assert backend._parse_page_range('1,3,5-7', 10) == [0, 2, 4, 5, 6]


def test_parse_page_range_clamp():
    backend = PdfBackend(MagicMock())
    assert backend._parse_page_range('1-999', 5) == [0, 1, 2, 3, 4]


def test_parse_page_range_invalid():
    backend = PdfBackend(MagicMock())
    assert backend._parse_page_range('abc', 5) == []


def test_parse_page_range_reverse():
    backend = PdfBackend(MagicMock())
    assert backend._parse_page_range('5-3', 10) == [2, 3, 4]


def test_parse_page_range_single():
    backend = PdfBackend(MagicMock())
    assert backend._parse_page_range('3', 10) == [2]


# ── _prepare_pdf tests ──


def test_prepare_pdf_no_op(tmp_path):
    """No page_range and no nup → returns original filepath"""
    backend = PdfBackend(MagicMock())
    pdf = tmp_path / 'test.pdf'
    doc = fitz.open()
    doc.new_page(width=595, height=842)
    doc.save(str(pdf))
    doc.close()

    result = backend._prepare_pdf(str(pdf), {})
    assert result == str(pdf)


def test_prepare_pdf_page_range(tmp_path):
    """page_range='1' extracts single page"""
    backend = PdfBackend(MagicMock())
    pdf = tmp_path / 'test.pdf'
    doc = fitz.open()
    doc.new_page(width=595, height=842)  # page 1
    doc.new_page(width=595, height=842)  # page 2
    doc.save(str(pdf))
    doc.close()

    result = backend._prepare_pdf(str(pdf), {'page_range': '1'})
    assert result != str(pdf)  # returns temp file
    with fitz.open(result) as out:
        assert len(out) == 1
    import os

    os.unlink(result)


def test_prepare_pdf_nup(tmp_path):
    """nup=2 merges 2 pages into 1"""
    backend = PdfBackend(MagicMock())
    pdf = tmp_path / 'test.pdf'
    doc = fitz.open()
    doc.new_page(width=595, height=842)
    doc.new_page(width=595, height=842)
    doc.save(str(pdf))
    doc.close()

    result = backend._prepare_pdf(str(pdf), {'nup': 2})
    assert result != str(pdf)
    with fitz.open(result) as out:
        assert len(out) == 1
    import os

    os.unlink(result)


def test_prepare_pdf_page_range_nup_combo(tmp_path):
    """page_range + nup combined"""
    backend = PdfBackend(MagicMock())
    pdf = tmp_path / 'test.pdf'
    doc = fitz.open()
    for _ in range(4):
        doc.new_page(width=595, height=842)
    doc.save(str(pdf))
    doc.close()

    result = backend._prepare_pdf(str(pdf), {'page_range': '1-2', 'nup': 2})
    assert result != str(pdf)
    with fitz.open(result) as out:
        assert len(out) == 1
    import os

    os.unlink(result)

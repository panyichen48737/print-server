"""PDF 后端测试 — 页码范围"""

from unittest.mock import MagicMock

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

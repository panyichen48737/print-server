"""N-up 拼版测试"""

from pathlib import Path

import fitz

from app.printing.backends.pdf_render import nup_compose


def test_nup_2up_reduces_pages(tmp_path):
    """2 pages → N-up 2 → 1 output page"""
    doc = fitz.open()
    doc.new_page(width=595, height=842)
    doc.new_page(width=595, height=842)
    src = str(tmp_path / 'src.pdf')
    doc.save(src)
    doc.close()

    result = nup_compose(src, 2)
    assert result != src
    with fitz.open(result) as out:
        assert len(out) == 1
    Path(result).unlink()


def test_nup_4up_reduces_pages(tmp_path):
    """4 pages → N-up 4 → 1 output page"""
    doc = fitz.open()
    for _ in range(4):
        doc.new_page(width=595, height=842)
    src = str(tmp_path / 'src4.pdf')
    doc.save(src)
    doc.close()

    result = nup_compose(src, 4)
    assert result != src
    with fitz.open(result) as out:
        assert len(out) == 1
    Path(result).unlink()


def test_nup_single_page_returns_original(tmp_path):
    """1 page → N-up 2 → returns original (no change)"""
    doc = fitz.open()
    doc.new_page(width=595, height=842)
    src = str(tmp_path / 'single.pdf')
    doc.save(src)
    doc.close()

    result = nup_compose(src, 2)
    assert result == src


def test_nup_empty_pdf(tmp_path):
    """1-page PDF → N-up 2 → returns original (no N-up possible)"""
    doc = fitz.open()
    doc.new_page(width=595, height=842)
    src = str(tmp_path / 'single2.pdf')
    doc.save(src)
    doc.close()

    result = nup_compose(src, 2)
    assert result == src


def test_nup_cleanup(tmp_path):
    """Verify composed file can be deleted"""
    doc = fitz.open()
    doc.new_page(width=595, height=842)
    doc.new_page(width=595, height=842)
    src = str(tmp_path / 'del_test.pdf')
    doc.save(src)
    doc.close()

    result = nup_compose(src, 2)
    assert Path(result).exists()
    Path(result).unlink()
    assert not Path(result).exists()

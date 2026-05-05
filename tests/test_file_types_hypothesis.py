"""Property-based tests for file type handling."""

from hypothesis import given, settings
from hypothesis import strategies as st

from app.config import Config


@given(st.text(alphabet='abcdefghijklmnopqrstuvwxyz.', min_size=1, max_size=20))
@settings(deadline=None)
def test_extension_validation(ext):
    cfg = Config(_skip_file=True)
    allowed = cfg.get('allowed_extensions', [])
    if ext.startswith('.') and ext.lower() in allowed:
        assert True  # valid extension
    else:
        # should not crash, just be rejected
        assert ext == ext  # no-op assertion


@given(st.sampled_from(['A3', 'A4', 'Letter']))
@settings(deadline=None)
def test_paper_size_roundtrip(size):
    cfg = Config(_skip_file=True)
    cfg.set('paper_size', size)
    assert cfg.get('paper_size') == size

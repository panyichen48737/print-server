"""Property-based tests for configuration validation."""

import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from app.core.config import Config

config_kwargs = st.fixed_dictionaries(
    {
        'default_copies': st.integers(min_value=1, max_value=999),
        'paper_size': st.sampled_from(['A3', 'A4', 'Letter']),
        'notify_channel': st.sampled_from(['disabled', 'dingtalk', 'bark']),
    }
)


@given(config_kwargs)
@settings(deadline=None)
def test_config_roundtrip(kwargs):
    # tempfile inside the test body — function-scoped fixtures don't reset between Hypothesis examples
    with tempfile.TemporaryDirectory() as tmp:
        path = str(Path(tmp) / 'config.json')
        cfg = Config(config_path=path, **kwargs, _skip_file=True)
        cfg.save()
        cfg2 = Config(config_path=path)
        for k, v in kwargs.items():
            assert getattr(cfg2, k) == v


@given(st.integers(min_value=1, max_value=16))
@settings(deadline=None)
def test_worker_count_in_range_accepted(count):
    cfg = Config(_skip_file=True, worker_count=count)
    assert cfg.worker_count == count


@given(st.integers().filter(lambda n: n < 1 or n > 16))
@settings(deadline=None)
def test_worker_count_out_of_range_rejected(count):
    with pytest.raises(ValidationError):
        Config(_skip_file=True, worker_count=count)

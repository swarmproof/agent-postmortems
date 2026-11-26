"""Feed timestamps used in the coverage digest."""
import importlib.util
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests


def load_script(name):
    path = Path(__file__).resolve().parents[1] / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("value,wanted", [
    ("Thu, 12 Nov 2026 09:00:00 GMT", "2026-11-12"),
    ("2026-11-12T09:00:00Z", "2026-11-12"),
    ("2026-11-12", "2026-11-12"),
    ("bad timestamp", ""), ("", ""),
])
def test_coverage_feed_date(value, wanted, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    assert load_script("coverage_gaps").feed_date(value) == wanted

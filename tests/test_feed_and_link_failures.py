"""Regression cases for transient sources and mixed feed date formats."""
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


@pytest.mark.parametrize("status,expected", [(521, "unreachable"), (404, "fail"), (410, "fail")])
def test_source_http_failures(monkeypatch, status, expected):
    mod = load_script("check_links")
    monkeypatch.setattr(mod.requests, "head", Mock(return_value=Mock(status_code=status)))
    monkeypatch.setattr(mod.requests, "get", Mock(return_value=Mock(status_code=status)))
    monkeypatch.setattr(mod.time, "sleep", Mock())
    assert mod.probe("https://source.example")[0] == expected


def test_last_network_failure_is_transient(monkeypatch):
    mod = load_script("check_links")
    monkeypatch.setattr(mod.requests, "head", Mock(side_effect=[Mock(status_code=404), requests.Timeout(), requests.Timeout()]))
    monkeypatch.setattr(mod.requests, "get", Mock(return_value=Mock(status_code=404)))
    monkeypatch.setattr(mod.time, "sleep", Mock())
    assert mod.probe("https://source.example")[0] == "unreachable"



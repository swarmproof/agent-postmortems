"""Source links must be http(s) web URLs.

Run: uv run --with pytest --with pyyaml --with jsonschema pytest -q tests/test_source_urls.py
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

REPO = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location("validate", REPO / "scripts" / "validate.py")
validate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(validate)

VALIDATOR = Draft202012Validator(json.loads(validate.SCHEMA_PATH.read_text()), format_checker=FormatChecker())

HOSTILE = [
    "javascript:alert(1)",
    "JavaScript:alert(1)",
    " javascript:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "vbscript:msgbox(1)",
    "file:///etc/passwd",
    "ftp://example.com/x",
    "mailto:someone@example.com",
    "//example.com/protocol-relative",
    "/relative/path",
    "https://",
    "https:///no-host",
    "http://[::1",
]


def record_with(url="https://example.com/a", archive_url=None) -> dict:
    record = validate.load_yaml(validate.FIXTURES_DIR / "2099-valid-minimal.yaml")
    source = {"url": url, "type": "other"}
    if archive_url is not None:
        source["archive_url"] = archive_url
    record["sources"] = [source]
    return record


@pytest.mark.parametrize("url", HOSTILE)
def test_non_web_source_url_rejected(url):
    errs = validate.gate_source_urls(record_with(url=url))
    assert len(errs) == 1 and "sources/0/url" in errs[0]


@pytest.mark.parametrize("url", HOSTILE)
def test_non_web_archive_url_rejected(url):
    errs = validate.gate_source_urls(record_with(archive_url=url))
    assert len(errs) == 1 and "sources/0/archive_url" in errs[0]


@pytest.mark.parametrize("url", [
    "https://example.com/a",
    "http://example.com/a",
    "HTTPS://Example.com/a",
    "http://web.archive.org/web/2099/https://example.com/a",
])
def test_web_urls_accepted(url):
    assert validate.gate_source_urls(record_with(url=url, archive_url=url)) == []


def test_schema_format_alone_does_not_catch_javascript_urls():
    """Why the gate exists: the schema's `format: uri` accepts these."""
    assert list(VALIDATOR.iter_errors(record_with(url="javascript:alert(1)"))) == []


def test_malformed_sources_left_to_schema_gate():
    record = record_with()
    record["sources"] = ["https://example.com/bare", {"url": 42, "type": "other"}]
    errs = validate.gate_source_urls(record)
    assert errs == ["G-SCHEMA: sources/1/url: 42 is not an http(s) URL with a host"]


@pytest.mark.parametrize("name", [
    "2099-invalid-source-url-scheme.yaml",
    "2099-invalid-archive-url-scheme.yaml",
])
def test_hostile_fixtures_fail_only_on_url_scheme(name):
    errs = validate.validate_file(validate.FIXTURES_DIR / name, VALIDATOR,
                                  *validate.load_taxonomy(), {})
    assert len(errs) == 1 and "is not an http(s) URL" in errs[0]


def test_every_corpus_source_is_a_web_url():
    paths = sorted(p for p in validate.INCIDENTS_DIR.glob("*.yaml") if not p.name.startswith("_"))
    assert len(paths) >= 180
    for path in paths:
        assert validate.gate_source_urls(validate.load_yaml(path)) == [], path.name

"""Third-party text in the discovery/coverage issue bodies is rendered inert."""
from __future__ import annotations

import importlib
import re
import sys
import types
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
HOSTILE = ("@octocat ping <img src=x onerror=alert(1)> **bold** [x](javascript:alert(1)) "
           "`tick` # head\n- injected item\r\n<details> " + "A" * 400)
CODE_SPAN = re.compile(r"`[^`\n]*`")


@pytest.fixture()
def mods(monkeypatch):
    # The scripts import requests for fetching; rendering never touches it.
    monkeypatch.setitem(sys.modules, "requests", types.ModuleType("requests"))
    monkeypatch.syspath_prepend(str(SCRIPTS))
    for name in ("issue_markdown", "discover_incidents", "coverage_gaps"):
        sys.modules.pop(name, None)
    return (importlib.import_module("issue_markdown"),
            importlib.import_module("discover_incidents"),
            importlib.import_module("coverage_gaps"))


def _outside_code(body: str) -> str:
    return CODE_SPAN.sub("", body)


def _assert_inert(body: str, trusted_extra: tuple[str, ...] = ()):
    for line in body.splitlines():
        assert line.count("`") % 2 == 0, f"unbalanced code span: {line!r}"
    rest = _outside_code(body)
    for bad in ("@octocat", "<img", "onerror", "javascript:", "**bold**", "- injected", "<details> "):
        assert bad not in rest, f"{bad!r} escaped its code span"
    for line in body.splitlines():
        assert len(line) < 1200, "line not length-capped"


def test_code_and_link_helpers(mods):
    md, _, _ = mods
    span = md.code(HOSTILE)
    assert span.startswith("`") and span.endswith("`") and span.count("`") == 2
    assert "\n" not in span and len(span) <= md.MAX_TEXT + 2 and span.endswith("…`")
    assert md.link("javascript:alert(1)") == "(no link)"
    assert md.link("data:text/html,x") == "(no link)"
    assert md.link("https://e.x/" + "a" * 600) == "(no link)"
    assert md.link("https://e.x/a) [click](https://evil.x") == \
        "[link](https://e.x/a%29%5Bclick%5D%28https://evil.x)"
    assert md.link("https://e.x/p?q=1&r=%20") == "[link](https://e.x/p?q=1&r=%20)"


def test_discover_markdown_is_inert(mods):
    _, di, _ = mods
    cand = {"title": HOSTILE, "source": "@feed <b>x</b>", "url": "javascript:alert(1)",
            "date": "2026-01-01 <script>", "relevance": 5, "likely_duplicate": False}
    dupe = dict(cand, likely_duplicate=True, url="https://ok.example/a(b)")
    body = di.emit_markdown([cand, dupe])
    _assert_inert(body)
    assert "<details><summary>" in body and body.rstrip().endswith("</details>")
    assert "(no link)" in body and "[link](https://ok.example/a%28b%29)" in body


def test_coverage_markdown_is_inert(mods):
    _, _, cg = mods
    gap = {"date": "2026-02-02 @octocat", "title": HOSTILE, "url": "https://ok.example/x",
           "cves": {"CVE-2026-12345", "CVE-1 <img src=x onerror=1>"}}
    body = cg.emit_markdown([gap], 1)
    _assert_inert(body)
    assert "CVE-2026-12345" in body and "CVE-1 " not in body


def test_body_capped_under_issue_limit(mods):
    md, di, _ = mods
    cands = [{"title": HOSTILE, "source": "s" * 300, "url": "https://e.x/" + "p" * 480,
              "date": "2026-01-01", "relevance": 1, "likely_duplicate": False} for _ in range(400)]
    body = di.emit_markdown(cands)
    assert len(body) <= md.MAX_BODY and "more omitted" in body

"""Record pages must label hazards as hazards and never present them as realized failures.

Run: uv run --with pytest --with pyyaml --with jsonschema pytest -q tests/test_publication.py
"""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


build_site = _load("build_site")
RECORDS = build_site.load_incidents()
IDS = {r["incident_id"] for r in RECORDS}
HAZARDS = [r for r in RECORDS if r.get("incident_type") == "hazard"]
INCIDENTS = [r for r in RECORDS if r.get("incident_type") == "incident"]
MISLEADING = ("realized incident", "post-mortem of a real", "postmortem of a real",
              "real ai-agent failure")


def _scrub(obj, word: str):
    """Replace record-supplied strings containing `word`, so only the site's own wording remains."""
    if isinstance(obj, dict):
        return {k: _scrub(v, word) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_scrub(v, word) for v in obj]
    if isinstance(obj, str) and word in obj.lower():
        return "scrubbed"
    return obj


def test_corpus_has_both_types():
    assert HAZARDS and INCIDENTS


@pytest.mark.parametrize("rec", HAZARDS, ids=lambda r: r["incident_id"])
def test_hazard_page_shows_hazard_label(rec):
    html = build_site.render_incident(rec, IDS)
    assert "badge-type-hazard" in html
    assert "<strong>Demonstrated hazard</strong>" in html
    lower = html.lower()
    for phrase in MISLEADING:
        assert phrase not in lower, phrase


@pytest.mark.parametrize("rec", HAZARDS, ids=lambda r: r["incident_id"])
def test_hazard_page_chrome_never_says_realized(rec):
    # Some hazard records say "no realized harm" in their own prose; only the
    # site's template text is under test here.
    html = build_site.render_incident(_scrub(copy.deepcopy(rec), "realiz"), IDS)
    assert "realiz" not in html.lower()


@pytest.mark.parametrize("rec", INCIDENTS, ids=lambda r: r["incident_id"])
def test_incident_page_shows_incident_label(rec):
    html = build_site.render_incident(rec, IDS)
    assert "badge-type-incident" in html
    assert "<strong>Realized incident</strong>" in html
    assert "Demonstrated hazard" not in html


def test_unknown_type_gets_no_note():
    assert build_site.type_note("other") == ""
    assert build_site.type_note(None) == ""


def test_record_text_is_escaped():
    rec = copy.deepcopy(HAZARDS[0])
    rec["title"] = "<script>alert(1)</script>"
    rec["summary"] = '"><img src=x onerror=alert(1)>'
    rec["incident_type"] = 'hazard"><script>x()</script>'
    page = build_site.render_incident(rec, IDS)
    index = build_site.render_archive([rec])
    for html in (page, index):
        assert "<script>alert(1)" not in html
        assert "<img src=x" not in html
        assert "<script>x()" not in html
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html

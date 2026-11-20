"""Tests for claim-level evidence rendering and the flagship case-page layout.

Self-contained (no conftest). Run with:
  uv run --with pytest --with pyyaml --with jsonschema pytest -q tests/test_case_pages.py

Flagship evidence data is curated separately, so these tests use fixture records:
real corpus records with evidence assessments added that restate only what the
record already says and cite only its own sources. Fixtures are never written to
incidents/.
"""
from __future__ import annotations

import copy
import html
import html.parser
import importlib.util
import json
import os
import subprocess
import sys
import tarfile
import io
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

REPO = Path(__file__).resolve().parent.parent


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


bs = _load("build_site_cases", REPO / "scripts" / "build_site.py")
validate = _load("validate_cases", REPO / "scripts" / "validate.py")
RECS = bs.load_incidents()
BY_ID = {r["incident_id"]: r for r in RECS}
IDS = set(BY_ID)
HOSTILE = '<script>alert(1)</script> " onmouseover="alert(2)'


# --------------------------------------------------------------------------- fixtures
def flagship_fixture() -> dict:
    """The Replit record with one assessment per evidence status (fixture only)."""
    rec = copy.deepcopy(BY_ID["2025-replit-prod-db-deletion"])
    fortune, register, aiid = (s["url"] for s in rec["sources"])
    rec["published_on"] = "2025-07-23"
    rec["evidence_assessments"] = [
        {"field_path": "/blast_radius/data/description", "evidence_status": "direct",
         "claim": "A production database was deleted during a test session.",
         "source_urls": [fortune], "reviewed_at": "2026-11-01", "reviewer": "fixture-reviewer"},
        {"field_path": "/trigger", "evidence_status": "corroborated",
         "claim": "The deletion happened while a code-and-action freeze was in place.",
         "source_urls": [fortune, register], "reviewed_at": "2026-11-01"},
        {"field_path": "/root_cause", "evidence_status": "inferred",
         "claim": "No enforced approval gate stood between the agent and production data.",
         "source_urls": [register],
         "analyst_note": "The sources describe the agent acting without approval; none describes the "
                         "platform's permission model.",
         "uncertainty": "A first-party description of the permission model would settle it.",
         "reviewed_at": "2026-11-02"},
        {"field_path": "/recovery", "evidence_status": "disputed",
         "claim": "Rollback was unavailable.",
         "source_urls": [register],
         "analyst_note": "The agent stated rollback would not work; the user later restored the data by rollback.",
         "reviewed_at": "2026-11-02"},
        {"field_path": "/detection", "evidence_status": "unknown",
         "claim": "How the platform's own monitoring responded.",
         "uncertainty": "No cited source reports platform-side detection.",
         "reviewed_at": "2026-11-02"},
    ]
    assert aiid  # three sources, the third deliberately left uncited
    return rec


def hazard_fixture() -> dict:
    rec = copy.deepcopy(BY_ID["2025-echoleak-m365-copilot"])
    rec["evidence_assessments"] = [
        {"field_path": "/summary", "evidence_status": "direct", "claim": "The issue was disclosed as a vulnerability.",
         "source_urls": [rec["sources"][0]["url"]], "reviewed_at": "2026-11-02"},
    ]
    return rec


def gate_errors(rec: dict) -> list[str]:
    schema = json.loads(validate.SCHEMA_PATH.read_text())
    v = Draft202012Validator(schema, format_checker=FormatChecker())
    return (validate.gate_schema(rec, v) + validate.gate_source_urls(rec) + validate.gate_evidence(rec)
            + validate.gate_dates(rec) + validate.gate_neutrality(rec))


class Doc(html.parser.HTMLParser):
    """Element tree light: records each start tag with its ancestor chain and text."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, dict]] = []
        self.nodes: list[dict] = []

    def handle_starttag(self, tag, attrs):
        node = {"tag": tag, "attrs": {k: v or "" for k, v in attrs}, "text": "",
                "ancestors": [dict(t=t, a=a) for t, a in self.stack]}
        self.nodes.append(node)
        if tag not in ("br", "img", "meta", "link", "input", "hr"):
            self.stack.append((tag, node["attrs"]))
            node["_open"] = True

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        for n in self.nodes:
            if n.get("_open") and any(a is n["attrs"] for _, a in self.stack):
                n["text"] += data


def parse(text: str) -> Doc:
    d = Doc()
    d.feed(text)
    return d


def claims_by_section(page, d: Doc | None = None) -> dict[str, list[dict]]:
    """section id ('ev-established' ...) -> list of claim <li> nodes inside it."""
    d = d or parse(page)
    out: dict[str, list[dict]] = {}
    for n in d.nodes:
        if n["tag"] == "li" and "claim" in n["attrs"].get("class", "").split():
            sec = next(a["a"] for a in reversed(n["ancestors"]) if a["t"] == "section")
            out.setdefault(sec.get("aria-labelledby", ""), []).append(n)
    return out


# --------------------------------------------------------------------------- data validity
@pytest.mark.parametrize("make", [flagship_fixture, hazard_fixture])
def test_fixtures_pass_the_real_validator_gates(make):
    assert gate_errors(make()) == []


# --------------------------------------------------------------------------- evidence grouping
SECTION_FOR = {"direct": "ev-established", "corroborated": "ev-established", "inferred": "ev-assessment",
               "unknown": "ev-open", "disputed": "ev-open"}


@pytest.mark.parametrize("render", ["flagship", "generic"])
def test_claims_render_under_the_heading_for_their_status(render):
    rec = flagship_fixture()
    if render == "generic":
        rec["incident_id"] = "2025-not-a-flagship"
    page = bs.render_incident(rec, IDS | {rec["incident_id"]})
    assert ('class="incident case"' in page) == (render == "flagship")
    got = claims_by_section(page)
    expected: dict[str, list[str]] = {}
    for a in rec["evidence_assessments"]:
        expected.setdefault(SECTION_FOR[a["evidence_status"]], []).append(a["claim"])
    assert {k: [html.unescape(n["text"]) for n in v] for k, v in got.items()}.keys() == expected.keys()
    for sec, claims in expected.items():
        texts = [n["text"] for n in got[sec]]
        assert len(texts) == len(claims)
        for claim, text in zip(claims, texts):
            assert text.startswith(claim)
    headings = {"ev-established": "What the sources establish", "ev-assessment": "Assessment, not established fact",
                "ev-open": "Unknown or contested"}
    for sec, title in headings.items():
        assert f'<h2 id="{sec}">{title}</h2>' in page


def test_every_claim_link_is_one_of_the_records_sources():
    rec = flagship_fixture()
    page = bs.render_incident(rec, IDS)
    sources = {s["url"] for s in rec["sources"]}
    by_claim = {a["claim"]: a for a in rec["evidence_assessments"]}
    d = parse(page)
    checked = 0
    for nodes in claims_by_section(page, d).values():
        for li in nodes:
            checked += 1
            claim = next(c for c in by_claim if li["text"].startswith(c))
            links = [n for n in d.nodes if n["tag"] == "a"
                     and any(a["a"] is li["attrs"] for a in n["ancestors"])]
            hrefs = [n["attrs"]["href"] for n in links]
            assert set(hrefs) <= sources, claim
            assert hrefs == by_claim[claim].get("source_urls", []), claim  # one click per cited source
            for n in links:
                assert n["attrs"].get("rel") == "noopener"
    assert checked == len(by_claim)


def test_claim_link_outside_sources_or_unsafe_is_not_rendered_as_a_link():
    rec = flagship_fixture()
    rec["evidence_assessments"][0]["source_urls"] = ["javascript:alert(1)", "https://not-a-cited-source.example/"]
    page = bs.render_incident(rec, IDS)
    assert "javascript:" not in page and "not-a-cited-source" not in page


def test_inferred_claims_carry_the_assessment_label():
    rec = flagship_fixture()
    for page in (bs.render_incident(rec, IDS), bs.render_evidence(rec)):
        nodes = [n for sec in claims_by_section(page).values() for n in sec]
        inferred = [n for n in nodes if "claim-inferred" in n["attrs"]["class"]]
        assert inferred
        for n in inferred:
            assert "Assessment, not established fact" in n["text"]
            assert "Analyst note:" in n["text"]
        for n in nodes:
            if "claim-inferred" not in n["attrs"]["class"]:
                assert "Assessment, not established fact" not in n["text"]


def test_hostile_claim_text_is_escaped():
    rec = flagship_fixture()
    for a in rec["evidence_assessments"]:
        a["claim"] = f"Claim {HOSTILE}"
        a["analyst_note"] = f"Note {HOSTILE}"
        a["uncertainty"] = f"Uncertain {HOSTILE}"
    rec["sources"][0]["title"] = f"Source {HOSTILE}"
    rec["prevention"] = f"Prevention {HOSTILE}"
    for page in (bs.render_incident(rec, IDS), bs.render_evidence(rec)):
        assert "<script>alert" not in page and '" onmouseover=' not in page
        assert html.escape(HOSTILE) in page
        tags = [n["tag"] for n in parse(page).nodes]
        assert tags.count("script") == page.count("<script")  # nothing beyond what the page shell emits


# --------------------------------------------------------------------------- flagship sections
def test_flagship_has_every_case_section_in_reading_order():
    page = bs.render_incident(flagship_fixture(), IDS)
    order = ["Summary", "At a glance", "What the sources establish", "Assessment, not established fact",
             "Unknown or contested", "How it happened, as recorded", "Impact and reversibility",
             "Proposed safeguards", "Timeline", "Coverage and limitations", "References", "Sources",
             "Cite and reuse"]
    positions = [page.index(f">{h}</h2>") for h in order]
    assert positions == sorted(positions)
    assert "<strong>Reported incident</strong>" in page
    url = f"{bs.SITE_BASE}/2025-replit-prod-db-deletion/"
    assert f'<a href="{url}">' in page and '<a href="incident.json">' in page
    assert "@misc{2025-replit-prod-db-deletion" in page


def test_hazard_flagship_says_demonstrated_hazard_not_reported_incident():
    page = bs.render_incident(hazard_fixture(), IDS)
    assert 'class="incident case"' in page
    assert "<strong>Demonstrated hazard</strong>" in page and "Reported incident" not in page
    assert "realized" not in page.lower().replace("no realized", "")  # only the record's own prose may say it


def test_test_cta_is_plain_text_never_a_control():
    page = bs.render_incident(flagship_fixture(), IDS)
    d = parse(page)
    holders = [n for n in d.nodes if bs.TEST_STATUS in n["text"]]
    innermost = [n for n in holders if not any(bs.TEST_STATUS in m["text"] and any(
        a["a"] is n["attrs"] for a in m["ancestors"]) for m in holders)]
    assert innermost
    for n in innermost:
        assert n["tag"] not in ("a", "button", "input", "select", "summary")
        assert not {"href", "onclick", "role", "tabindex"} & set(n["attrs"])
        assert not [a for a in n["ancestors"] if a["t"] in ("a", "button", "summary", "label")]
    # nothing interactive on the page mentions tests, and no runnable-test claims
    for n in d.nodes:
        if n["tag"] in ("a", "button"):
            assert "test" not in n["text"].lower(), n["text"]
    lower = page.lower()
    for phrase in ("run this test", "run the test", "test available", "download the test", "swarmproof test"):
        assert phrase not in lower
    css = bs.CSS[bs.CSS.index(".test-status"):]
    rule = css[: css.index("}")]
    assert "cursor:default" in rule and "border" not in rule and "background" not in rule


def test_coverage_counts_and_unassessed_fields_follow_the_data():
    rec = flagship_fixture()
    page = bs.render_incident(rec, IDS)
    assert "5 statements assessed: 2 established by sources, 1 assessment, 2 unknown or contested." in page
    # contributing factors and prevention carry no assessment in the fixture
    cov = page[page.index(">Coverage and limitations</h2>"):]
    cov = cov[: cov.index("</section>")]
    assert "Contributing factors" in cov and "Proposed safeguards" in cov and "Root cause" not in cov
    assert "Assessments reviewed 2026-11-01 to 2026-11-02." in cov
    assert "Record confidence: confirmed (first-party/vendor/court-confirmed)." in cov


# --------------------------------------------------------------------------- dates
def test_dates_are_labelled_by_their_basis():
    rec = flagship_fixture()
    rows = dict(bs.date_rows(rec))
    assert rows["Principal source published"] == "2025-07-23"
    assert "may be the date it occurred or the date it was first publicly disclosed" in rows["Record date"]
    rec["temporal_basis"] = "disclosed"
    rec["disclosed_on"] = rec["date"]
    assert gate_errors(rec) == []
    assert dict(bs.date_rows(rec))["Record date"] == f"{rec['date']} (the date it was first publicly disclosed)"
    hz = hazard_fixture()
    hz["occurred_on"] = hz["date"]
    assert "First demonstrated" in dict(bs.date_rows(hz))
    # a record using only date-basis fields still gets the dates block, without evidence sections
    only_dates = copy.deepcopy(BY_ID["2024-air-canada-chatbot-liability"])
    only_dates["temporal_basis"] = "unknown"
    page = bs.render_incident(only_dates, IDS)
    assert "<h2>Dates</h2>" in page and "may be the date it occurred" in page and 'id="ev-' not in page


# --------------------------------------------------------------------------- unchanged pages
def test_flagship_ids_without_evidence_keep_the_standard_layout():
    for rid in bs.FLAGSHIP_IDS:
        rec = BY_ID[rid]
        if rec.get("evidence_assessments"):
            continue
        page = bs.render_incident(rec, IDS)
        assert 'class="incident case"' not in page and "<h2>Dates</h2>" not in page


def _baseline_module(ref: str, tmp: Path):
    archive = subprocess.run(["git", "archive", ref, "scripts", "schema", "incidents"], cwd=REPO,
                             capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as tf:
        tf.extractall(tmp, filter="data")
    return _load("build_site_baseline", tmp / "scripts" / "build_site.py")


def test_records_without_new_fields_render_exactly_as_the_baseline(tmp_path):
    ref = os.environ.get("SITE_BASELINE_REF", "registry/integration")
    if subprocess.run(["git", "rev-parse", "--verify", "--quiet", ref + "^{commit}"], cwd=REPO,
                      capture_output=True).returncode != 0:
        pytest.skip(f"baseline ref {ref!r} not available; set SITE_BASELINE_REF to compare")
    base = _baseline_module(ref, tmp_path)
    legacy = [r for r in RECS if not bs.has_provenance(r)]
    assert legacy
    for r in legacy:
        assert bs.render_incident(r, IDS) == base.render_incident(r, IDS), r["incident_id"]


def test_json_export_only_for_flagship_pages(tmp_path, monkeypatch):
    fixture = flagship_fixture()
    recs = [fixture if r["incident_id"] == fixture["incident_id"] else r for r in RECS]
    monkeypatch.setattr(bs, "load_incidents", lambda: recs)
    monkeypatch.setattr(bs, "OUT", tmp_path)
    assert bs.main() == 0
    exported = sorted(p.parent.name for p in tmp_path.glob("*/incident.json"))
    assert exported == ["2025-replit-prod-db-deletion"]
    assert json.loads((tmp_path / exported[0] / "incident.json").read_text()) == fixture

"""Tests for claim-level evidence rendering and the flagship case-page layout.

Self-contained (no conftest). Run with:
  uv run --with pytest --with pyyaml --with jsonschema pytest -q tests/test_case_pages.py

Layout and rendering tests use synthetic records (built on tests/fixtures/2099-valid-full.yaml)
under synthetic ids that are added to FLAGSHIP_IDS for the test run, so they do not depend on
corpus content. Separate tests check the real flagship records.
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
import re
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
PRIMARY, NEWS, VENDOR = ("https://example.com/fixture-primary", "https://example.com/fixture-news",
                         "https://example.com/fixture-vendor")
FLAGSHIP_FIXTURE_ID = "2099-flagship-incident"
HAZARD_FIXTURE_ID = "2099-flagship-hazard"
FIXTURE_IDS = frozenset({FLAGSHIP_FIXTURE_ID, HAZARD_FIXTURE_ID})


@pytest.fixture(autouse=True)
def fixture_flagships(monkeypatch):
    """Treat the synthetic fixture ids as flagships, alongside the real ones."""
    monkeypatch.setattr(bs, "FLAGSHIP_IDS", bs.FLAGSHIP_IDS | FIXTURE_IDS)


def synthetic(rid: str, incident_type: str = "incident") -> dict:
    """A schema-valid synthetic record with no provenance fields."""
    rec = validate.load_yaml(validate.FIXTURES_DIR / "2099-valid-full.yaml")
    rec.update(incident_id=rid, incident_type=incident_type, related_incidents=[],
               title=f"Fixture record {rid}")
    rec.pop("last_updated", None)
    rec["sources"] = [
        {"url": PRIMARY, "title": "Fixture primary write-up", "publisher": "Example", "type": "primary-research",
         "date_accessed": "2099-01-01"},
        {"url": NEWS, "title": "Fixture news report", "publisher": "Example News", "type": "news",
         "date_accessed": "2099-01-01"},
        {"url": VENDOR, "title": "Fixture vendor response", "publisher": "Fixture Corp", "type": "vendor-response",
         "date_accessed": "2099-01-01"},
    ]
    return rec


def flagship_fixture() -> dict:
    """A synthetic incident with one assessment per evidence status."""
    rec = synthetic(FLAGSHIP_FIXTURE_ID, "incident")
    rec["published_on"] = "2099-01-03"
    rec["evidence_assessments"] = [
        {"field_path": "/blast_radius/data/description", "evidence_status": "direct",
         "claim": "One fixture record was exposed.",
         "source_urls": [PRIMARY], "reviewed_at": "2099-02-01", "reviewer": "fixture-reviewer"},
        {"field_path": "/trigger", "evidence_status": "corroborated",
         "claim": "The fixture trigger condition started the run.",
         "source_urls": [PRIMARY, NEWS], "reviewed_at": "2099-02-01"},
        {"field_path": "/root_cause", "evidence_status": "inferred",
         "claim": "No enforced approval gate stood between the agent and the fixture data.",
         "source_urls": [NEWS],
         "analyst_note": "The sources describe the action; none describes the permission model.",
         "uncertainty": "A first-party description of the permission model would settle it.",
         "reviewed_at": "2099-02-02"},
        {"field_path": "/recovery", "evidence_status": "disputed",
         "claim": "Rollback was unavailable.",
         "source_urls": [VENDOR],
         "analyst_note": "The vendor response says a rollback path existed.",
         "reviewed_at": "2099-02-02"},
        {"field_path": "/detection", "evidence_status": "unknown",
         "claim": "How the fixture monitor responded.",
         "uncertainty": "No cited source reports detection.",
         "reviewed_at": "2099-02-02"},
    ]
    return rec


def hazard_fixture() -> dict:
    rec = synthetic(HAZARD_FIXTURE_ID, "hazard")
    rec["evidence_assessments"] = [
        {"field_path": "/summary", "evidence_status": "direct", "claim": "The issue was disclosed as a vulnerability.",
         "source_urls": [PRIMARY], "reviewed_at": "2099-02-02"},
    ]
    return rec


def page_ids(*recs) -> set[str]:
    return IDS | {r["incident_id"] for r in recs}


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
        rec["incident_id"] = "2099-not-a-flagship"
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
    assert "<strong>Realized incident</strong>" in page  # same label as every other incident page
    url = f"{bs.SITE_BASE}/{FLAGSHIP_FIXTURE_ID}/"
    assert f'<a href="{url}">' in page and '<a href="incident.json">' in page
    assert "@misc{" + FLAGSHIP_FIXTURE_ID in page


def test_hazard_flagship_says_demonstrated_hazard():
    page = bs.render_incident(hazard_fixture(), IDS)
    assert 'class="incident case"' in page
    assert "<strong>Demonstrated hazard</strong>" in page and "Realized incident" not in page
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
    assert "Assessments reviewed 2099-02-01 to 2099-02-02." in cov
    assert f"Record confidence: {rec['confidence']} ({bs.CONFIDENCE_DEFS[rec['confidence']]})." in cov


# --------------------------------------------------------------------------- dates
def test_dates_are_labelled_by_their_basis():
    rec = flagship_fixture()
    rows = dict(bs.date_rows(rec))
    assert rows["Principal source published"] == "2099-01-03"
    assert "may be the date it occurred or the date it was first publicly disclosed" in rows["Record date"]
    rec["temporal_basis"] = "disclosed"
    rec["disclosed_on"] = rec["date"]
    assert gate_errors(rec) == []
    assert dict(bs.date_rows(rec))["Record date"] == f"{rec['date']} (the date it was first publicly disclosed)"
    hz = hazard_fixture()
    hz["occurred_on"] = hz["date"]
    assert "First demonstrated" in dict(bs.date_rows(hz))
    # a record using only date-basis fields still gets the dates block, without evidence sections
    only_dates = synthetic("2099-dates-only")
    only_dates["temporal_basis"] = "unknown"
    page = bs.render_incident(only_dates, IDS)
    assert "<h2>Dates</h2>" in page and "may be the date it occurred" in page and 'id="ev-' not in page


# --------------------------------------------------------------------------- unchanged pages
def test_flagship_id_without_evidence_keeps_the_standard_layout():
    rec = synthetic(FLAGSHIP_FIXTURE_ID)  # a flagship id, but no evidence or date-basis fields
    assert rec["incident_id"] in bs.FLAGSHIP_IDS and not bs.is_flagship(rec)
    page = bs.render_incident(rec, page_ids(rec))
    assert 'class="incident case"' not in page and "<h2>Dates</h2>" not in page
    assert page.count('class="date-note"') == 1


@pytest.mark.parametrize("kind, phrase", [("incident", "when it occurred"), ("hazard", "when it was first demonstrated")])
def test_legacy_date_note_explains_the_ambiguous_date(kind, phrase):
    rec = synthetic("2099-legacy-date", kind)
    note = bs.legacy_date_note(rec)
    assert phrase in note and "first publicly disclosed" in note and "does not say which" in note
    assert f'href="{bs.METHODS_DATE_URL}"' in note and bs.METHODS_DATE_URL.endswith("#what-date-means-and-its-limits")
    assert bs.render_incident(rec, page_ids(rec)).count(note) == 1
    rec["temporal_basis"] = "disclosed"
    rec["disclosed_on"] = rec["date"]
    assert bs.legacy_date_note(rec) == ""  # pages with date-basis fields explain dates in the Dates block


def test_every_legacy_corpus_page_has_the_date_note_and_provenance_pages_do_not():
    for r in RECS:
        n = bs.render_incident(r, IDS).count('class="date-note"')
        assert n == (0 if bs.has_provenance(r) else 1), r["incident_id"]


def _baseline_module(ref: str, tmp: Path):
    archive = subprocess.run(["git", "archive", ref, "scripts", "schema", "incidents"], cwd=REPO,
                             capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as tf:
        tf.extractall(tmp, filter="data")
    return _load("build_site_baseline", tmp / "scripts" / "build_site.py")


# Page-shell changes made on the site branches this one is stacked on (skip link, main
# landmark target, list wording). Applied to the baseline so the comparison isolates what
# this branch changes on legacy pages. Each is a no-op when the baseline already has it.
SHELL_UPDATES = [
    ("<body>\n<header", '<body>\n<a class="skip-link" href="#main">Skip to content</a>\n<header'),
    ("<main>\n", '<main id="main" tabindex="-1">\n'),
    ('<a href="../">← all incidents</a>', '<a href="../">← all records</a>'),
]


def shell_updated(page: str) -> str:
    for old, new in SHELL_UPDATES:
        page = page.replace(old, new)
    return page


def test_legacy_pages_differ_from_the_baseline_only_by_the_date_note(tmp_path):
    ref = os.environ.get("SITE_BASELINE_REF", "registry/integration")
    if subprocess.run(["git", "rev-parse", "--verify", "--quiet", ref + "^{commit}"], cwd=REPO,
                      capture_output=True).returncode != 0:
        pytest.skip(f"baseline ref {ref!r} not available; set SITE_BASELINE_REF to compare")
    base = _baseline_module(ref, tmp_path)
    legacy = [r for r in RECS if not bs.has_provenance(r)]
    assert legacy
    for r in legacy:
        now, before = bs.render_incident(r, IDS), shell_updated(base.render_incident(r, IDS))
        note = bs.legacy_date_note(r)
        # beyond the shared page-shell updates, the only change is the date note after the id/date line
        assert now.count(note) == 1 and now.replace(note, "", 1) == before, r["incident_id"]


def test_json_export_only_for_flagship_pages(tmp_path, monkeypatch):
    # a temporary corpus of synthetic records only
    fixture, hazard, legacy = flagship_fixture(), hazard_fixture(), synthetic("2099-legacy-fixture")
    monkeypatch.setattr(bs, "load_incidents", lambda: [fixture, hazard, legacy])
    monkeypatch.setattr(bs, "OUT", tmp_path)
    assert bs.main() == 0
    exported = sorted(p.parent.name for p in tmp_path.glob("*/incident.json"))
    assert exported == sorted(FIXTURE_IDS)
    assert json.loads((tmp_path / FLAGSHIP_FIXTURE_ID / "incident.json").read_text()) == fixture
    assert (tmp_path / "2099-legacy-fixture" / "index.html").exists()


def test_only_source_stated_claims_say_view_source():
    rec = flagship_fixture()
    page = bs.render_incident(rec, IDS)
    for sec, nodes in claims_by_section(page).items():
        for n in nodes:
            if sec == "ev-established":
                assert "View source:" in n["text"]
            else:
                assert "View source:" not in n["text"]
    assert "Reasoned from:" in page and "Related source:" in page


# --------------------------------------------------------------------------- real flagship records
REAL_FLAGSHIP_IDS = ("2025-replit-prod-db-deletion", "2025-echoleak-m365-copilot")
REAL_FLAGSHIPS = [r for r in RECS if bs.is_flagship(r)]


@pytest.mark.parametrize("rid", REAL_FLAGSHIP_IDS)
def test_real_flagship_pages_render_the_flagship_layout(rid):
    rec = BY_ID[rid]
    assert rid in bs.FLAGSHIP_IDS and rec.get("evidence_assessments") and bs.is_flagship(rec)
    page = bs.render_incident(rec, IDS)
    assert 'class="incident case"' in page and ">Coverage and limitations</h2>" in page
    assert '<a href="incident.json">' in page and 'class="date-note"' not in page
    assert "← all records</a>" in page and "all incidents" not in page


def _row(page: str, label: str) -> str:
    """Text of the <dd> following <dt>label</dt> (first occurrence)."""
    i = page.index(f"<dt>{label}</dt>")
    dd = page[i:]
    dd = dd[dd.index("<dd>") + 4: dd.index("</dd>")]
    return html.unescape(re.sub(r"<[^>]+>", " ", dd))


@pytest.mark.parametrize("rec", REAL_FLAGSHIPS, ids=lambda r: r["incident_id"])
def test_real_flagship_states_each_claim_at_its_reviewed_status(rec):
    page = bs.render_incident(rec, IDS)
    assert 'class="incident case"' in page
    got = claims_by_section(page)
    for a in rec["evidence_assessments"]:
        nodes = [n for n in got[SECTION_FOR[a["evidence_status"]]]
                 if " ".join(n["text"].split()).startswith(" ".join(a["claim"].split()))]
        assert len(nodes) == 1, a["claim"]
        assert bs.STATUS_LABELS[a["evidence_status"]] in nodes[0]["text"]
        if a.get("uncertainty"):
            assert " ".join(a["uncertainty"].split())[:60] in " ".join(nodes[0]["text"].split())


def test_replit_root_cause_is_shown_as_assessment_and_reversibility_as_unknown():
    rec = BY_ID["2025-replit-prod-db-deletion"]
    page = bs.render_incident(rec, IDS)
    narrative = page[page.index(">How it happened, as recorded</h2>"):]
    root = narrative[narrative.index("<h3>Root cause</h3>"):]
    root = root[: root.index("</div>")]
    assert "Assessment, not established fact" in root
    assert not [s for s in ("Stated by a cited source", "Stated by two or more") if s in root]
    rev = _row(page, "Reversibility")
    assert "Not established by the cited sources" in rev


def test_echoleak_score_shows_both_authorities_and_occurrence_is_not_dated():
    rec = BY_ID["2025-echoleak-m365-copilot"]
    page = bs.render_incident(rec, IDS)
    sev = _row(page, "Severity")
    assert "9.3" in sev and "7.5" in sev and "NVD" in sev
    assert _row(page, "First demonstrated").startswith(bs.NOT_RECORDED)
    assert "<strong>Demonstrated hazard</strong>" in page
    mech = next(a for a in rec["evidence_assessments"] if a["field_path"] == "/root_cause")
    assert "discoverer" in mech["uncertainty"] and "discoverer" in page  # researcher-sourced caveat shown

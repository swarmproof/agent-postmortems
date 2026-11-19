"""Tests for the static site's search index, client search and index page.

Self-contained (no conftest). Run with:
  uv run --with pytest --with pyyaml --with jsonschema pytest -q tests/test_site_search.py

Query tests execute the real site/search.js in node, so they exercise the same
matcher the browser runs; they are skipped if node is not installed.
"""
from __future__ import annotations

import copy
import html
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("build_site", REPO / "scripts" / "build_site.py")
bs = importlib.util.module_from_spec(_spec)
sys.modules["build_site"] = bs
_spec.loader.exec_module(bs)

RECS = bs.load_incidents()
INDEX = bs.build_search_index(RECS)
NODE = shutil.which("node")
XSS_SCRIPT = "<script>alert(1)</script>"
XSS_ATTR = '" onmouseover="alert(1)'


# --------------------------------------------------------------------------- helpers
def _norm(s: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", s).lower().split())


def raw_text(rec: dict) -> str:
    """Every searchable field, read straight from the record (independent of the index builder)."""
    sysm = rec.get("system") or {}
    parts = [rec.get("title"), rec["incident_id"], rec.get("primary_failure_class"), rec.get("attack_vector"),
             sysm.get("vendor"), sysm.get("framework"), *(sysm.get("models") or []), *(sysm.get("tools") or []),
             *(rec.get("tags") or []), *(rec.get("cve") or []), *(rec.get("cwe") or []),
             *[i for ids in (rec.get("mappings") or {}).values() for i in ids or []],
             *[fc.get("class") for fc in rec.get("failure_classes", [])],
             *[fc.get("subclass") for fc in rec.get("failure_classes", [])],
             rec.get("summary"), rec.get("trigger"), rec.get("root_cause"), *(rec.get("contributing_factors") or []),
             rec.get("detection"), rec.get("recovery"), rec.get("prevention")]
    return _norm(" ".join(str(p) for p in parts if p))


def expected_ids(query: str, recs=RECS) -> set[str]:
    terms = [t.strip(bs.EDGE_PUNCT) for t in _norm(query).split()]
    terms = [t for t in terms if t]
    return {r["incident_id"] for r in recs if all(t in raw_text(r) for t in terms)}


def js_search(cases: list[tuple[str, dict]], index: dict = INDEX, tmp: Path | None = None) -> list[list[str]]:
    """Run the shipped search.js in node for each (query, filters) case."""
    if not NODE:
        pytest.skip("node is not installed; client search not executed")
    import tempfile
    d = Path(tmp or tempfile.mkdtemp())
    (d / "search.js").write_text(bs.SEARCH_JS, encoding="utf-8")
    (d / "index.json").write_text(json.dumps(index), encoding="utf-8")
    (d / "cases.json").write_text(json.dumps(cases), encoding="utf-8")
    prog = ("const s=require(process.argv[1]+'/search.js'),d=require(process.argv[1]+'/index.json'),"
            "c=require(process.argv[1]+'/cases.json');"
            "process.stdout.write(JSON.stringify(c.map(([q,f])=>s.search(d.records,q,f))));")
    out = subprocess.run([NODE, "-e", prog, str(d)], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def card_ids(page_html: str) -> list[str]:
    return [html.unescape(m) for m in re.findall(r'<a class="card" href="[^"]*" data-id="([^"]*)"', page_html)]


# --------------------------------------------------------------------------- index content
def test_index_covers_every_record_in_display_order():
    assert [r["id"] for r in INDEX["records"]] == [r["incident_id"] for r in RECS]
    n_files = len([p for p in (REPO / "incidents").glob("*.yaml") if not p.name.startswith("_")])
    assert len(INDEX["records"]) == n_files


def test_index_includes_prevention_text_and_system_fields():
    by_id = {r["id"]: r for r in INDEX["records"]}
    checked_vendor = checked_tool = 0
    for rec in RECS:
        entry = by_id[rec["incident_id"]]
        for word in _norm(rec["prevention"]).split():
            w = word.strip(bs.EDGE_PUNCT)
            if w:
                assert w in entry["b"], (rec["incident_id"], w)
        sysm = rec.get("system") or {}
        if sysm.get("vendor"):
            assert _norm(sysm["vendor"]) in entry["k"]
            assert entry["vendor"] == sysm["vendor"]
            checked_vendor += 1
        if sysm.get("framework"):
            assert _norm(sysm["framework"]) in entry["k"]
        for tool in sysm.get("tools") or []:
            assert _norm(tool) in entry["k"] and tool in entry["tools"]
            checked_tool += 1
    assert checked_vendor and checked_tool


def test_index_is_text_only_and_compact():
    allowed = {"id", "t", "k", "b", "d", "sev", "type", "year", "conf", "auto", "vendor", "classes", "tools"}
    for r in INDEX["records"]:
        assert set(r) == allowed  # no source objects or other full-record payloads
    payload = bs.search_index_json(RECS)
    urls = {s["url"] for r in RECS for s in r.get("sources", [])}
    assert urls and not [u for u in urls if json.dumps(u)[1:-1] in payload]


# --------------------------------------------------------------------------- known queries
def _prevention_only_term() -> str:
    """A term some record matches only through its prevention text."""
    for term in ("allowlist", "least privilege", "sandbox", "rate limit", "human approval", "egress"):
        for rec in RECS:
            others = _norm(" ".join(str(rec.get(f) or "") for f in
                                    ("title", "summary", "trigger", "root_cause", "detection", "recovery")))
            if all(t in _norm(rec["prevention"]) for t in term.split()) and not all(t in others for t in term.split()):
                return term
    pytest.fail("no prevention-only term found in the corpus")


def test_known_queries_return_expected_records():
    vendor = max({(r.get("system") or {}).get("vendor") for r in RECS} - {None},
                 key=lambda v: sum((r.get("system") or {}).get("vendor") == v for r in RECS))
    cve = sorted(c for r in RECS for c in r.get("cve") or [])[0]
    queries = ["database", "cost", vendor, cve, _prevention_only_term(), "prompt-injection", "prompt injection",
               "  DATABASE  ", "database,"]
    results = js_search([(q, {}) for q in queries])
    for q, got in zip(queries, results):
        exp = expected_ids(q)
        assert exp, f"fixture expectation for {q!r} is empty"
        assert set(got) == exp, q
        assert len(got) == len(set(got)), q
    # the CVE query finds the record that lists it; every record classed prompt-injection is found
    assert {r["incident_id"] for r in RECS if cve in (r.get("cve") or [])} <= set(results[3])
    classed = {r["incident_id"] for r in RECS if any(fc.get("class") == "prompt-injection"
                                                      for fc in r.get("failure_classes", []))}
    assert classed and classed <= set(results[5])
    # case and whitespace do not matter
    assert results[7] == results[0] == results[8]


def test_ranking_title_before_keys_before_body():
    got = js_search([("database", {})])[0]
    by_id = {r["id"]: r for r in INDEX["records"]}
    tier = [0 if "database" in by_id[i]["t"] else 1 if "database" in by_id[i]["k"] else 2 for i in got]
    assert tier == sorted(tier)
    assert tier[0] == 0 and tier[-1] == 2  # the corpus has title and body-only hits


def test_filters_intersect_with_each_other_and_the_query():
    def py(filters, recs=INDEX["records"]):
        out = []
        for r in recs:
            ok = True
            for param, want in filters.items():
                have = r[bs_facets[param]]
                ok &= (want in have) if isinstance(have, list) else (have == want)
            if ok:
                out.append(r["id"])
        return out

    bs_facets = {"class": "classes", "severity": "sev", "type": "type", "year": "year",
                 "confidence": "conf", "autonomy": "auto", "vendor": "vendor", "tool": "tools"}
    cases = [("", {"severity": "critical"}), ("", {"severity": "critical", "type": "incident"}),
             ("", {"class": "prompt-injection", "confidence": "confirmed"}),
             ("", {"tool": "shell", "autonomy": "fully-autonomous"}),
             ("database", {"type": "incident"})]
    results = js_search(cases)
    for (q, f), got in zip(cases, results):
        exp = py(f)
        if q:
            exp = [i for i in exp if i in expected_ids(q)]
            assert set(got) == set(exp)
        else:
            assert got == exp  # no query: display order is preserved
    # intersection really narrows
    assert set(results[1]) < set(results[0])


def test_every_offered_filter_option_matches_a_record():
    opts = bs.facet_options(RECS)
    assert [p for p, _, _ in bs.FILTERS] == list(opts)
    cases = [("", {p: v}) for p, values in opts.items() for v in values]
    for (_, f), got in zip(cases, js_search(cases)):
        assert got, f
    assert opts["confidence"] and opts["vendor"] and opts["tool"] and opts["autonomy"]


# --------------------------------------------------------------------------- default list
def test_default_list_contains_all_records_in_deterministic_order():
    page = bs.render_index(RECS)
    ids = card_ids(page)
    assert ids == [r["incident_id"] for r in RECS]
    assert len(ids) == len(set(ids)) == len(RECS)
    # newest first; records sharing a date are ordered by incident_id
    keyed = [(r.get("date", ""), r["incident_id"]) for r in RECS]
    assert all(a[0] > b[0] or (a[0] == b[0] and a[1] < b[1]) for a, b in zip(keyed, keyed[1:]))
    assert bs.render_index(bs.load_incidents()) == page
    # every card links to its permanent /<incident_id>/ URL
    for rid in ids:
        assert f'href="{html.escape(rid)}/"' in page
    # an empty query with no filters shows everything, in that order
    assert js_search([("", {})])[0] == ids


def test_index_page_controls_are_labelled_and_progressive():
    page = bs.render_index(RECS)
    assert re.search(r'<form class="filters"[^>]*\bhidden\b', page)  # revealed by JS only
    assert 'aria-live="polite"' in page and 'id="count"' in page
    assert '<label for="q">' in page
    for param, _, _ in bs.FILTERS:
        assert f'<label for="f-{param}">' in page and f'id="f-{param}" name="{param}"' in page
    assert 'id="empty"' in page and 'class="clear"' in page
    assert 'data-text=' not in page


# --------------------------------------------------------------------------- injection
def _hostile_record() -> dict:
    rec = copy.deepcopy(next(r for r in RECS if r.get("sources")))
    rec["incident_id"] = "2099-xss-fixture"
    rec["date"] = "2099-01-01"
    rec["title"] = f"Title {XSS_SCRIPT} {XSS_ATTR}"
    rec["summary"] = f"Summary {XSS_SCRIPT} {XSS_ATTR}"
    rec["prevention"] = f"Prevention {XSS_SCRIPT}"
    rec["tags"] = [XSS_SCRIPT, XSS_ATTR]
    rec["system"] = {**(rec.get("system") or {}), "vendor": f"Vendor {XSS_ATTR}", "tools": [XSS_SCRIPT, XSS_ATTR]}
    rec["sources"] = [{**rec["sources"][0], "title": f"Source {XSS_SCRIPT} {XSS_ATTR}",
                       "url": "javascript:alert(1)", "archive_url": "JavaScript:alert(2)"},
                      {**rec["sources"][0], "title": "data link", "url": "data:text/html,<script>alert(3)</script>"}]
    return rec


def _assert_inert(page: str):
    assert XSS_SCRIPT not in page
    assert "<script>alert" not in page
    assert XSS_ATTR not in page and '" onmouseover=' not in page
    assert not re.search(r'href\s*=\s*"\s*(javascript|data):', page, re.I)
    # the only script elements are the ones the generator itself emits
    allowed = {'<script src="search.js" defer>', '<script type="application/ld+json">'}
    assert set(re.findall(r"<script\b[^>]*>", page)) <= allowed


def test_hostile_record_is_schema_valid_so_rendering_must_neutralise_it():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((REPO / "schema" / "incident.schema.json").read_text())
    jsonschema.validate(_hostile_record(), schema)  # the schema alone does not stop these strings


def test_xss_payloads_render_inert_in_static_html():
    bad = _hostile_record()
    recs = [bad, *RECS]
    index_page = bs.render_index(recs)
    incident_page = bs.render_incident(bad, {r["incident_id"] for r in recs})
    _assert_inert(index_page)
    _assert_inert(incident_page)
    assert html.escape(XSS_SCRIPT) in index_page and html.escape(XSS_SCRIPT) in incident_page  # shown as text
    assert "data link" in incident_page and 'href="data:' not in incident_page


def test_xss_payloads_are_inert_data_in_search_index():
    bad = _hostile_record()
    payload = bs.search_index_json([bad])
    assert "<" not in payload and ">" not in payload
    data = json.loads(payload)["records"][0]
    assert "<script>alert(1)</script>" in data["t"]  # preserved as data, not dropped
    assert data["vendor"] == f"Vendor {XSS_ATTR}"
    got = js_search([("onmouseover", {}), ("", {"vendor": f"Vendor {XSS_ATTR}"})], index=json.loads(payload))
    assert got == [["2099-xss-fixture"], ["2099-xss-fixture"]]


def test_client_script_never_builds_html_from_strings():
    for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"):
        assert sink not in bs.SEARCH_JS, sink


def test_safe_url_allows_only_http_and_https():
    assert bs.safe_url("https://example.com/a?b=1") == "https://example.com/a?b=1"
    assert bs.safe_url(" HTTP://example.com ") == "HTTP://example.com"
    for bad in ("javascript:alert(1)", " JavaScript:alert(1)", "data:text/html,x", "vbscript:x",
                "//example.com", "/relative", "", None):
        assert bs.safe_url(bad) == ""

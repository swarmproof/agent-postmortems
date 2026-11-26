"""Published corpus figures must equal the counts in the export built from the records.

Run: uv run --with pytest --with pyyaml --with jsonschema pytest -q tests/test_counts.py
"""
from __future__ import annotations

import importlib.util
import re
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


build_exports = _load("build_exports")
gen_readme_stats = _load("gen_readme_stats")
build_site = _load("build_site")


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _export_counts() -> dict[str, int]:
    """Counts read from the incidents export, built exactly as build_exports.py builds it."""
    records = build_exports.load_incidents()
    doc = build_exports.build_incidents(records, build_exports.taxonomy_version(records), "test")
    types = Counter(r["incident_type"] for r in doc["incidents"])
    return {"total": doc["count"], "incident": types["incident"], "hazard": types["hazard"]}


def _sentence(c: dict[str, int]) -> str:
    return (f"{c['total']} sourced records: {c['incident']} realized incidents "
            f"and {c['hazard']} demonstrated hazards")


def test_export_types_partition_the_corpus():
    c = _export_counts()
    assert c["total"] > 0
    assert c["incident"] + c["hazard"] == c["total"]


def test_stats_generator_uses_export_counts():
    assert gen_readme_stats.corpus_counts(gen_readme_stats.load_records()) == _export_counts()


def test_readme_states_export_counts():
    readme = _squash((REPO / "README.md").read_text())
    assert _sentence(_export_counts()) in readme


def test_readme_stats_block_is_current():
    readme = (REPO / "README.md").read_text()
    block = gen_readme_stats.compute_rows(gen_readme_stats.load_records())
    assert block in readme, "run: uv run scripts/gen_readme_stats.py"


def test_site_intro_states_export_counts():
    html = _squash(build_site.render_archive(build_site.load_incidents()))
    assert _sentence(_export_counts()) in html


def test_site_and_readme_carry_reporting_limits():
    readme = _squash((REPO / "README.md").read_text()).lower()
    html = _squash(build_site.render_archive(build_site.load_incidents())).lower()
    for text in (readme, html):
        assert "not a representative prevalence sample" in text
        assert "safety ranking" in text


def test_no_uniqueness_or_real_failure_overclaims():
    readme = (REPO / "README.md").read_text().lower()
    html = build_site.render_archive(build_site.load_incidents()).lower()
    for phrase in ("no shared, structured record", "real ai-agent failures",
                   "post-mortems of real", "postmortems of real"):
        assert phrase not in readme, phrase
        assert phrase not in html, phrase

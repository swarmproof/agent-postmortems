"""Release assets: reproducible bytes, valid checksums, honest counts, inert hints."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
EPOCH = 1_767_225_600  # 2026-01-01T00:00:00Z


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


br = _load("build_release")
be = _load("build_exports")


def _build(tmp_path: Path, sub: str) -> Path:
    # Drift is skipped: incident branches change the corpus without committing
    # exports, and drift detection has its own test below.
    out = tmp_path / sub
    br.build(out, epoch=EPOCH, tag="test", check_drift=False)
    return out


def test_same_epoch_gives_identical_bytes(tmp_path):
    a, b = _build(tmp_path, "a"), _build(tmp_path, "b")
    names = sorted(p.name for p in a.iterdir())
    assert names == sorted(p.name for p in b.iterdir())
    assert {"incidents.json", "scenarios.json", "seeds.json", "incident.schema.json",
            "CITATION.cff", "manifest.json", "SHA256SUMS"} <= set(names)
    for n in names:
        assert (a / n).read_bytes() == (b / n).read_bytes(), f"{n} differs between builds"


def test_sha256sums_match_files(tmp_path):
    out = _build(tmp_path, "r")
    lines = (out / "SHA256SUMS").read_text().splitlines()
    listed = {}
    for line in lines:
        m = re.fullmatch(r"([0-9a-f]{64})  (\S+)", line)
        assert m, f"not sha256sum format: {line!r}"
        listed[m.group(2)] = m.group(1)
    assert set(listed) == {p.name for p in out.iterdir()} - {"SHA256SUMS"}
    for name, digest in listed.items():
        assert hashlib.sha256((out / name).read_bytes()).hexdigest() == digest, name
    manifest = json.loads((out / "manifest.json").read_text())
    for name, meta in manifest["files"].items():
        assert listed[name] == meta["sha256"]


def test_manifest_counts_equal_records(tmp_path):
    out = _build(tmp_path, "r")
    m = json.loads((out / "manifest.json").read_text())
    recs = [yaml.safe_load(p.read_text()) for p in sorted((REPO / "incidents").glob("*.yaml"))
            if not p.name.startswith("_")]
    c = m["counts"]
    assert c["records"] == len(recs)
    assert c["incidents"] == sum(r["incident_type"] == "incident" for r in recs)
    assert c["hazards"] == sum(r["incident_type"] == "hazard" for r in recs)
    assert c["incidents"] + c["hazards"] == c["records"]
    for name in ("incidents", "scenarios", "seeds"):
        doc = json.loads((out / f"{name}.json").read_text())
        assert doc["count"] == len(doc[name])
    assert c["scenarios"] == json.loads((out / "scenarios.json").read_text())["count"]
    assert c["seeds"] == json.loads((out / "seeds.json").read_text())["count"]
    assert re.fullmatch(r"[0-9a-f]{40}", m["git_commit"])
    assert m["source_date_epoch"] == EPOCH and m["built_at"] == "2026-01-01T00:00:00Z"
    assert m["taxonomy_version"] and m["schema_version"] and m["export_schema_version"]


SCENARIO_KEYS = {"incident_id", "failure_class", "attack_vector", "system_profile", "trigger_shape",
                 "expected_failure", "success_criteria", "source"}
SEED_KEYS = {"incident_id", "failure_class", "cost_dimension", "observed_cost_usd", "seed_shape",
             "guardrail_under_test", "source"}
EXECUTABLE_KEY = re.compile(r"code|command|cmd|shell|script|exec|payload|run", re.IGNORECASE)


def _strings(x):
    if isinstance(x, str):
        yield x
    elif isinstance(x, dict):
        for v in x.values():
            yield from _strings(v)
    elif isinstance(x, list):
        for v in x:
            yield from _strings(v)


def test_scenarios_and_seeds_are_non_executable_hints(tmp_path):
    out = _build(tmp_path, "r")
    for name, allowed in (("scenarios", SCENARIO_KEYS), ("seeds", SEED_KEYS)):
        for entry in json.loads((out / f"{name}.json").read_text())[name]:
            assert set(entry) <= allowed, f"{name} {entry['incident_id']}: new field {set(entry) - allowed}"
            for key in entry:
                assert not EXECUTABLE_KEY.search(key), f"{name}: executable-looking field {key}"
            for text in _strings(entry):
                assert not be.PAYLOAD_MARKERS.search(text), f"{name} {entry['incident_id']}: payload marker"


def test_drift_detects_stale_committed_export(tmp_path):
    rendered = {"incidents": '{"count": 1}\n'}
    (tmp_path / "incidents.json").write_text('{"count": 1}\n')
    assert br.drift(rendered, tmp_path) == []
    (tmp_path / "incidents.json").write_text('{"count": 0}\n')
    assert br.drift(rendered, tmp_path) == ["incidents"]
    assert br.drift({"seeds": "{}\n"}, tmp_path) == ["seeds"]  # missing file is drift


def test_enriched_download_preserves_all_record_fields(tmp_path):
    out = _build(tmp_path, "enriched")
    doc = json.loads((out / "incidents.v2.json").read_text())
    expected = be.load_incidents()
    assert doc["export_schema_version"] == "2.0"
    assert doc["incidents"] == expected
    assert doc["corpus_as_of"] == doc["generated_at"]
    core = json.loads((out / "incidents.json").read_text())
    assert "corpus_as_of" not in core
    assert core["count"] == doc["count"]
    assert core["export_schema_version"] == "1.0"
    enriched_by_id = {r["incident_id"]: r for r in expected}
    for record in core["incidents"]:
        assert all(enriched_by_id[record["incident_id"]][key] == value
                   for key, value in record.items())
    assert any("evidence_assessments" in r for r in doc["incidents"])
    assert all("evidence_assessments" not in r for r in core["incidents"])


def test_all_attached_export_schemas_validate_their_download(tmp_path):
    from jsonschema import Draft202012Validator

    out = _build(tmp_path, "schemas")
    for name in br.EXPORT_NAMES:
        schema = json.loads((out / f"{name}.export.schema.json").read_text())
        assert list(Draft202012Validator(schema).iter_errors(
            json.loads((out / f"{name}.json").read_text()))) == []


def test_invalid_source_property_cannot_disappear_in_projection(monkeypatch):
    import pytest

    records = be.load_incidents()
    records[0]["undeclared_property"] = "unexpected"
    monkeypatch.setattr(be, "load_incidents", lambda: records)
    with pytest.raises(SystemExit, match="failed its schema"):
        be.build_artifacts()

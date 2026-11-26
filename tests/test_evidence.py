"""Claim-level provenance (evidence_assessments) rules.

Run: uv run --with pytest --with pyyaml --with jsonschema pytest -q tests/test_evidence.py
"""
from __future__ import annotations

import copy
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
PRIMARY = "https://example.com/primary"
NEWS = "https://example.com/news"
VENDOR = "https://example.com/vendor"


def base_record() -> dict:
    record = validate.load_yaml(validate.FIXTURES_DIR / "2099-valid-minimal.yaml")
    record["sources"] = [
        {"url": PRIMARY, "type": "primary-research"},
        {"url": NEWS, "type": "news"},
        {"url": VENDOR, "type": "vendor-response"},
    ]
    return record


def assessment(**overrides) -> dict:
    item = {
        "field_path": "/root_cause",
        "claim": "The retry policy had no upper bound.",
        "evidence_status": "direct",
        "source_urls": [PRIMARY],
        "reviewed_at": "2099-01-02",
    }
    item.update(overrides)
    return {k: v for k, v in item.items() if v is not None}


def errors_for(*items) -> list[str]:
    record = base_record()
    record["evidence_assessments"] = list(items)
    errs = validate.gate_schema(record, VALIDATOR)
    errs += validate.gate_neutrality(record)
    errs += validate.gate_evidence(record)
    return errs


def test_good_assessment_passes():
    assert errors_for(assessment(reviewer="reviewer-01", uncertainty="None beyond the source.")) == []


def test_record_without_assessments_is_unaffected():
    record = base_record()
    assert validate.gate_evidence(record) == []
    assert validate.gate_schema(record, VALIDATOR) == []


def test_empty_assessment_list_is_valid():
    assert errors_for() == []


def test_source_url_not_in_record_sources_fails():
    errs = errors_for(assessment(source_urls=["https://example.com/elsewhere"]))
    assert len(errs) == 1 and errs[0].startswith("G-EVIDENCE") and "elsewhere" in errs[0]


def test_source_url_must_match_exactly():
    errs = errors_for(assessment(source_urls=[PRIMARY + "/"]))
    assert any("is not one of this record's sources" in e for e in errs)


def test_archive_url_is_not_a_substitute_for_source_url():
    record = base_record()
    record["sources"][0]["archive_url"] = "https://web.archive.org/web/2099/" + PRIMARY
    record["evidence_assessments"] = [assessment(source_urls=[record["sources"][0]["archive_url"]])]
    assert any(e.startswith("G-EVIDENCE") for e in validate.gate_evidence(record))


@pytest.mark.parametrize("pointer", [
    "/does_not_exist",
    "/blast_radius/cost",          # absent in the minimal record
    "/failure_classes/1",          # index out of range
    "/failure_classes/00",         # leading zero is not a valid array index
    "/failure_classes/-",          # past-the-end marker never resolves to a value
    "/title/0",                    # cannot index into a string
])
def test_unresolvable_pointer_fails(pointer):
    errs = errors_for(assessment(field_path=pointer))
    assert any(e.startswith("G-EVIDENCE") and "does not resolve" in e for e in errs), errs


@pytest.mark.parametrize("pointer", ["root_cause", "", "/bad~2escape"])
def test_malformed_pointer_rejected_by_schema(pointer):
    errs = errors_for(assessment(field_path=pointer))
    assert any(e.startswith("G-SCHEMA") for e in errs), errs


@pytest.mark.parametrize("pointer", [
    "/root_cause",
    "/failure_classes/0/subclass",
    "/sources/1/url",
    "/system/framework",
])
def test_resolvable_pointers_pass(pointer):
    assert errors_for(assessment(field_path=pointer)) == []


def test_escaped_pointer_tokens_resolve():
    record = base_record()
    record["tags"] = ["a/b"]
    assert validate.resolve_pointer({"a/b": {"m~n": 1}}, "/a~1b/m~0n") == 1
    assert validate.resolve_pointer(record, "/tags/0") == "a/b"


def test_pointer_into_assessments_is_rejected():
    errs = errors_for(assessment(field_path="/evidence_assessments/0/claim"))
    assert any("must not point into evidence_assessments" in e for e in errs)


def test_disputed_is_representable():
    item = assessment(evidence_status="disputed", source_urls=[VENDOR],
                      analyst_note="The vendor response attributes the loop to a scheduler fault.")
    assert errors_for(item) == []


def test_inferred_is_representable_without_sources():
    item = assessment(evidence_status="inferred", source_urls=None,
                      analyst_note="Logs show unbounded retries; the policy itself is not named.",
                      uncertainty="A first-party post-mortem would settle it.")
    assert errors_for(item) == []


def test_unknown_is_representable_without_sources():
    item = assessment(evidence_status="unknown", source_urls=None,
                      uncertainty="No cited source says how the loop was noticed.")
    assert errors_for(item) == []


@pytest.mark.parametrize("status", ["inferred", "disputed"])
def test_inferred_and_disputed_require_analyst_note(status):
    errs = errors_for(assessment(evidence_status=status))
    assert any("'analyst_note' is a required property" in e for e in errs), errs


def test_direct_requires_a_source():
    assert any("'source_urls' is a required property" in e for e in errors_for(assessment(source_urls=None)))
    assert any("should be non-empty" in e for e in errors_for(assessment(source_urls=[])))


def test_corroborated_requires_two_sources():
    assert errors_for(assessment(evidence_status="corroborated")) != []
    assert errors_for(assessment(evidence_status="corroborated", source_urls=[PRIMARY, NEWS])) == []


def test_duplicate_source_urls_rejected():
    errs = errors_for(assessment(evidence_status="corroborated", source_urls=[PRIMARY, PRIMARY]))
    assert any("non-unique" in e for e in errs), errs


def test_unknown_status_rejected():
    assert any(e.startswith("G-SCHEMA") for e in errors_for(assessment(evidence_status="likely")))


@pytest.mark.parametrize("missing", ["field_path", "claim", "evidence_status", "reviewed_at"])
def test_required_keys(missing):
    item = assessment()
    del item[missing]
    assert any(f"'{missing}' is a required property" in e for e in errors_for(item))


@pytest.mark.parametrize("reviewed_at", ["2099-01", "2099", "02/01/2099"])
def test_reviewed_at_must_be_full_date(reviewed_at):
    assert any(e.startswith("G-SCHEMA") for e in errors_for(assessment(reviewed_at=reviewed_at)))


@pytest.mark.parametrize("reviewer", ["jane@example.com", "Jane Doe", "-leading-dash"])
def test_reviewer_must_be_a_handle(reviewer):
    assert any(e.startswith("G-SCHEMA") for e in errors_for(assessment(reviewer=reviewer)))


def test_extra_key_rejected():
    assert any(e.startswith("G-SCHEMA") for e in errors_for(assessment(score=0.9)))


def test_neutrality_lint_covers_assessment_prose():
    errs = errors_for(assessment(analyst_note="The operator was reckless."))
    assert any(e.startswith("G-NEUTRAL") and "analyst_note" in e for e in errs), errs


def test_traceable_claim_resolves_to_a_cited_source():
    """A sample claim can be traced from the field it assesses to a source object in the record."""
    record = base_record()
    record["evidence_assessments"] = [assessment()]
    item = record["evidence_assessments"][0]
    assert validate.resolve_pointer(record, item["field_path"]) == record["root_cause"]
    cited = [s for s in record["sources"] if s["url"] in item["source_urls"]]
    assert cited and cited[0]["type"] == "primary-research"


def test_confidence_is_not_touched_by_assessments():
    record = base_record()
    record["confidence"] = "reported"
    before = copy.deepcopy(record)
    record["evidence_assessments"] = [assessment(evidence_status="disputed", analyst_note="Contested.")]
    validate.gate_evidence(record)
    assert record["confidence"] == before["confidence"]

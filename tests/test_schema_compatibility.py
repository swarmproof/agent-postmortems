"""Schema v1 backward-compatibility harness.

The v1 schema may only grow by optional, additive fields. These tests pin that
property against a frozen copy of the schema as originally adopted
(tests/compat/incident.schema.v1.0.json) and frozen v1 records, so a change that
would reject existing data fails here even if the live corpus is edited later.

Run: uv run --with pytest --with pyyaml --with jsonschema pytest -q tests/test_schema_compatibility.py
"""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

REPO = Path(__file__).resolve().parent.parent
COMPAT = REPO / "tests" / "compat"

_spec = importlib.util.spec_from_file_location("validate", REPO / "scripts" / "validate.py")
validate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(validate)

FROZEN_SCHEMA = json.loads((COMPAT / "incident.schema.v1.0.json").read_text())
LIVE_SCHEMA = json.loads(validate.SCHEMA_PATH.read_text())
FROZEN = Draft202012Validator(FROZEN_SCHEMA, format_checker=FormatChecker())
LIVE = Draft202012Validator(LIVE_SCHEMA, format_checker=FormatChecker())
TAX_VERSION, CLASSES = validate.load_taxonomy()

CORPUS = sorted(p for p in validate.INCIDENTS_DIR.glob("*.yaml") if not p.name.startswith("_"))
FROZEN_SAMPLES = sorted(COMPAT.glob("v1-sample-*.yaml"))


def record_errors(record: dict) -> list[str]:
    """Every record-level gate the corpus validator applies (G-ID needs the corpus, so is excluded)."""
    errors = validate.gate_schema(record, LIVE)
    errors += validate.gate_taxonomy(record, TAX_VERSION, CLASSES)
    errors += validate.gate_neutrality(record)
    for name in ("gate_evidence", "gate_dates"):
        gate = getattr(validate, name, None)
        if gate is not None:
            errors += gate(record)
    return errors


def test_corpus_is_not_empty():
    assert len(CORPUS) >= 180


@pytest.mark.parametrize("path", CORPUS, ids=lambda p: p.stem)
def test_corpus_record_valid_under_frozen_v1_schema(path):
    record = validate.load_yaml(path)
    assert list(FROZEN.iter_errors(record)) == []


@pytest.mark.parametrize("path", CORPUS, ids=lambda p: p.stem)
def test_corpus_record_valid_under_live_validator(path):
    assert record_errors(validate.load_yaml(path)) == []


@pytest.mark.parametrize("path", FROZEN_SAMPLES, ids=lambda p: p.stem)
def test_frozen_v1_sample_valid_under_both(path):
    record = validate.load_yaml(path)
    assert list(FROZEN.iter_errors(record)) == []
    assert record_errors(record) == []


def test_frozen_sample_is_not_mutated_by_validation():
    path = COMPAT / "v1-sample-full.yaml"
    record = validate.load_yaml(path)
    before = copy.deepcopy(record)
    record_errors(record)
    assert record == before


def test_live_schema_keeps_every_frozen_property_unchanged():
    """Existing property definitions are untouched; only new optional keys may appear."""
    for name, definition in FROZEN_SCHEMA["properties"].items():
        assert LIVE_SCHEMA["properties"].get(name) == definition, name
    for name, definition in FROZEN_SCHEMA["$defs"].items():
        assert LIVE_SCHEMA["$defs"].get(name) == definition, name


def test_live_schema_required_core_unchanged():
    assert LIVE_SCHEMA["required"] == FROZEN_SCHEMA["required"]
    assert LIVE_SCHEMA["additionalProperties"] is False


def test_live_schema_adds_only_optional_top_level_fields():
    added = set(LIVE_SCHEMA["properties"]) - set(FROZEN_SCHEMA["properties"])
    assert not added & set(LIVE_SCHEMA["required"])

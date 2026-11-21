"""Date-semantics fields (occurred_on / disclosed_on / published_on / temporal_basis).

Run: uv run --with pytest --with pyyaml --with jsonschema pytest -q tests/test_dates.py
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


def errors_for(**fields) -> list[str]:
    record = validate.load_yaml(validate.FIXTURES_DIR / "2099-valid-minimal.yaml")  # date: 2099-01-01
    record.update(fields)
    return validate.gate_schema(record, VALIDATOR) + validate.gate_dates(record)


def test_legacy_record_with_only_date_is_valid():
    assert errors_for() == []


def test_all_fields_in_order_pass():
    assert errors_for(occurred_on="2098-12-30", disclosed_on="2099-01-01",
                      published_on="2099-01-03", temporal_basis="disclosed") == []


def test_same_day_is_in_order():
    assert errors_for(occurred_on="2099-01-01", disclosed_on="2099-01-01", published_on="2099-01-01") == []


@pytest.mark.parametrize("fields", [
    {"occurred_on": "2099-01-02", "disclosed_on": "2099-01-01"},
    {"disclosed_on": "2099-01-05", "published_on": "2099-01-01"},
    {"occurred_on": "2099-02-01", "published_on": "2099-01-01"},  # gap in the middle still ordered
])
def test_out_of_order_fails(fields):
    assert any(e.startswith("G-DATES") and "is after" in e for e in errors_for(**fields))


@pytest.mark.parametrize("basis,field", [("occurred", "occurred_on"),
                                         ("disclosed", "disclosed_on"),
                                         ("published", "published_on")])
def test_basis_field_must_equal_date(basis, field):
    assert errors_for(temporal_basis=basis, **{field: "2099-01-01"}) == []
    assert any("temporal_basis" in e for e in errors_for(temporal_basis=basis, **{field: "2098-06-01"}))


def test_basis_without_its_field_is_allowed():
    assert errors_for(temporal_basis="occurred") == []


def test_unknown_basis_places_no_constraint():
    assert errors_for(temporal_basis="unknown", occurred_on="2098-01-01") == []


def test_unrecognised_basis_rejected():
    assert any(e.startswith("G-SCHEMA") for e in errors_for(temporal_basis="reported"))


@pytest.mark.parametrize("value", ["2099", "2099-01", "2099/01/01", "01-01-2099", "2099-13-01"])
@pytest.mark.parametrize("field", ["occurred_on", "disclosed_on", "published_on"])
def test_only_full_iso_dates_accepted(field, value):
    """Partial dates are rejected, consistent with how `date` itself is validated."""
    assert any(e.startswith("G-SCHEMA") for e in errors_for(**{field: value}))


@pytest.mark.parametrize("value", ["2099", "2099-01"])
def test_legacy_date_rejects_partial_dates_too(value):
    """Pins the precedent the new fields follow."""
    assert any(e.startswith("G-SCHEMA") for e in errors_for(date=value))


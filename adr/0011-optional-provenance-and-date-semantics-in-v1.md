# ADR-0011 — Claim-level provenance and date semantics as optional v1 fields

> The export compatibility policy below is superseded by [ADR-0012](0012-compatible-v1-downloads-and-enriched-export.md). Source fields and their editorial semantics remain supported.

**Status:** Accepted

## Context
Two gaps limit how far a reader can trust or reuse a record:

- `confidence` rates a record as a whole. A record can be `confirmed` overall while one statement in it — often the root cause — is the curator's inference rather than something a source says. Nothing in the record shows which statements are sourced and which are not.
- The required `date` means "occurred *or* first publicly disclosed". For any given record a reader cannot tell which, so timelines and time-to-disclosure analysis built on it are unreliable.

Both are additive information. The question is whether they can be added to schema v1 without breaking existing records, exports or consumers, or whether they need a v2.

## Decision
Add five optional top-level fields to schema v1. `schema_version` stays `"1.0"`; no existing property, `$defs` entry or the required core changes.

1. **`evidence_assessments[]`** — each entry assesses one statement in the record: `field_path` (RFC 6901 JSON Pointer into the record), `claim`, `evidence_status` (`direct` / `corroborated` / `inferred` / `unknown` / `disputed`), `source_urls[]`, `analyst_note`, `reviewed_at`, optional pseudonymous `reviewer`, and `uncertainty`.
   - `source_urls` may only cite URLs already in the record's `sources[]`, matched exactly. A claim's evidence must be the record's own public, linkable evidence — the one rule — and adding a new source means adding it to `sources[]` first, where link checking and archiving already apply. Archive URLs are not accepted in place of the source URL.
   - `field_path` must resolve in the record and must not point into `evidence_assessments`, so every assessment is attached to a real value.
   - `direct` needs ≥1 cited source, `corroborated` ≥2 (mirroring `confidence: corroborated`), and `inferred` / `disputed` need an `analyst_note`, so non-sourced and contested claims always carry their reasoning.
   - Assessments never change `confidence`. They are a finer layer beside it, not a replacement for it.
2. **`occurred_on`, `disclosed_on`, `published_on`** — the three dates `date` conflates (for a hazard, `occurred_on` is when it was first demonstrated; `published_on` is the principal cited source's publication date).
3. **`temporal_basis`** — `occurred` / `disclosed` / `published` / `unknown`: what the legacy `date` holds for this record.

**Partial dates are not allowed.** The new dates are full `YYYY-MM-DD`, the same as `date`, `last_updated` and `date_accessed`, which the validator already restricts to full dates. When a source gives only a month or a year the field is left out rather than padded to the first of the month, because padding states a precision nobody reported. Allowing partial dates later would be a loosening that every reader parsing these fields as dates would have to handle, so it should only come with a version change.

**No date is inferred or backfilled.** The fields are set by editorial review from the cited sources only; records without them remain valid, and absence means "not recorded".

`validate.py` enforces what the schema cannot express: G-EVIDENCE (pointer resolution, source membership) and G-DATES (`occurred_on` ≤ `disclosed_on` ≤ `published_on`; the field named by `temporal_basis`, when present, equals `date`). The neutrality lint covers assessment prose.

## Compatibility
> **Consumer warning — readers pinned to the pre-change schema.** The schema keeps `additionalProperties: false` (ADR-0007). A consumer that validates records against a copy of `incident.schema.json` taken before this change **will reject every record that uses one of the new fields**, from the first records that adopt them onward. Such a reader must refresh its schema copy or ignore unknown keys. At adoption no record used the new fields, so the corpus as it stood then was unaffected.

Additive optional fields are only acceptable in v1 if they demonstrably break nothing. Verified at adoption, with the change applied, against a baseline taken before it:

- **Records:** all 180 records in the corpus at adoption validate, with validator output identical to the baseline. `tests/test_schema_compatibility.py` validates every record against both the live schema and a frozen copy of the schema as adopted (`tests/compat/incident.schema.v1.0.json`), plus frozen v1 sample records, and asserts every original property and definition is unchanged and the required core is identical.
- **Fixtures:** every pre-existing fixture passes or fails as before, with the same first error.
- **Exports:** `export/incidents.json`, `scenarios.json` and `seeds.json` rebuild byte-identical for the corpus at adoption.
- **In-repo consumers:** the site build is byte-identical; `apply_mappings.py --check`, `gen_readme_stats.py --check` and the SCHEMA.md drift gate pass. With a record that uses every new field, the validator, exporter, mapping tool, stats generator and site build all run cleanly and the mapping tool preserves the new fields when it rewrites the file.

Records keep `schema_version: "1.0"` because nothing a v1 record could previously express has changed; the consumer warning above is the cost of that choice.

## Exports
`export/incidents.json` carries each record verbatim, so the new fields pass through as additional keys on the records that have them. That keeps the export a complete copy of the corpus rather than a filtered view. `scenarios.json` and `seeds.json` build their entries from named fields only and are unaffected.

`export_schema_version` stays `"1.0"`. The export envelope is unchanged and its `incidents[]` items are open objects, so a 1.0 export containing the new keys still conforms to the 1.0 export schema, while changing the version string would itself break consumers that pin `"1.0"`. A minor export version bump is warranted only when the export adds or changes its own fields, for example if scenarios or seeds start projecting the date basis.

## Migration and deprecation path
- **No migration.** Existing records need no change, and none is made mechanically.
- **Adoption** is per record, through editorial review against the record's sources; new records should state `temporal_basis` when the sources make it clear.
- **`date` is not deprecated in v1.** It stays required with its current meaning, so sorting, filtering, the export stamp and every existing reader keep working.
- **If `date` is ever narrowed** (for example to always mean occurrence) or a new field becomes required, that is a breaking change. It goes into a v2 schema with a v2 export published alongside 1.0 for a stated deprecation window, plus a mechanical migration script that sets `temporal_basis: unknown` where nothing is recorded and never infers a date.

## Alternatives rejected
- **Ship as v2 now.** It would force a version change on every consumer for fields that no record used at adoption, and the checks above show v1 can carry them without breaking existing data.
- **Change `confidence` per claim or reinterpret it.** That would silently change what published records mean.
- **Free-form source citations in assessments.** These would bypass link checking and archiving and could cite evidence the record does not show.
- **Allow partial dates.** This is inconsistent with every existing date field and pushes precision handling onto every reader; leaving the field out is the honest encoding.
- **Redefine `date` in place.** This would be a breaking change to every existing record's meaning.

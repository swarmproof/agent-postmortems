# The Agent Post-Mortem Standard — v1

A schema for recording AI-agent failures in a comparable, machine-validated form.

Machine-validated by [`schema/incident.schema.json`](./schema/incident.schema.json) (JSON Schema draft 2020-12) in CI. Every record carries `schema_version: "1.0"`. The failure taxonomy lives in [`schema/taxonomy.yaml`](./schema/taxonomy.yaml), rendered as [`TAXONOMY.md`](./TAXONOMY.md).

## Design

- **Machine-first, human-readable second.** The record is valid typed data before it is prose; validation is the merge gate.
- **Small required core, large optional body.** Contribution stays cheap; power fields are opt-in.
- **Sourcing and neutrality are schema properties**, not just norms: structured `sources[]`, `confidence`, `status`, `incident_type`. Every `sources[].url` and `archive_url` must be a web link — `http` or `https` with a host and no userinfo (`user@` before the host); other schemes such as `javascript:`, `data:` or `file:` are rejected. Plain `http` is accepted because some archive snapshots are recorded that way.
- **One incident = one file** (`incidents/<incident_id>.yaml`), atomic and permalinkable. Unknown top-level fields are rejected (`additionalProperties: false`).

## Fields

Required-core fields are **bold**; everything else is optional but encouraged.

| Field | Meaning |
|-------|---------|
| **`schema_version`** | Standard version of the record — always `"1.0"` |
| `taxonomy_version` | Version of `taxonomy.yaml` used to classify (`"1.0"`) |
| **`incident_id`** | Stable, immutable slug `<year>-<kebab>`, e.g. `2025-whatsapp-mcp-tool-poisoning`; must equal the filename |
| **`title`** | Neutral, factual one-line title (8–140 chars) |
| `summary` | Neutral 1–3 sentence factual summary (≤500 chars), no editorializing |
| **`date`** | When it happened or was first publicly disclosed (`YYYY-MM-DD`); which of the two is stated by `temporal_basis` where known — see [Date semantics](#date-semantics) |
| `last_updated` | Date the record was last revised |
| `occurred_on` | Date it happened (for a hazard: first demonstrated), `YYYY-MM-DD`; only when a source states it |
| `disclosed_on` | Date it was first made public by anyone, `YYYY-MM-DD`; only when a source establishes it |
| `published_on` | Publication date of the principal cited source report, `YYYY-MM-DD` |
| `temporal_basis` | What `date` represents: `occurred` / `disclosed` / `published` / `unknown` |
| **`incident_type`** | `incident` (realized harm) or `hazard` (demonstrated PoC / near-miss, OECD-style) |
| `status` | Report maturity: `preliminary` / `factual` / `final` (NTSB-style) |
| `confidence` | Sourcing certainty: `reported` / `corroborated` / `confirmed` / `disputed` (VERIS-style) |
| `severity` | Impact band: `critical` / `high` / `moderate` / `low` / `informational` |
| `severity_rationale` | Why that severity band |
| **`system`** | The stack: `framework`, `models[]`, `tools[]`, `vendor`, `autonomy_level` |
| **`primary_failure_class`** | The inducing taxonomy class (see `TAXONOMY.md`) |
| **`failure_classes`** | Ordered causal chain of `{class, subclass}`; first entry equals `primary_failure_class` |
| `attack_vector` | How induced: `direct-user` / `untrusted-content` / `tool-metadata` / `supply-chain` / `multimodal` / `self-induced` / `n-a` |
| `causation` | MIT-style dimensions: `entity` (human/ai/both), `intentionality`, `timing` |
| **`trigger`** | What set it off — as (near-)reproducible input/condition where sources allow |
| **`root_cause`** | The underlying cause; blameless — systemic, not personal |
| `contributing_factors` | 2–5 systemic contributing factors (SRE blameless style) |
| **`detection`** | How it was noticed |
| **`recovery`** | How it was stopped/fixed |
| **`prevention`** | What would stop a recurrence |
| **`blast_radius`** | Structured impact: `cost` ($, estimated flag), `data` (records, classification), `user_harm` (categories, counts), `scope`, `reversibility` |
| `timeline` | Ordered `{at, event}` entries |
| `external_ids` | Cross-references: `aiid`, `oecd_aim`, `aiaaic` (de-dup, not clone) |
| `cve` | Related CVE identifiers |
| `cwe` | Related CWE identifiers |
| `mappings` | External security-framework cross-references (`owasp_llm`, `owasp_agentic`, `mitre_atlas`), derived from `failure_classes` via [`schema/framework-mappings.yaml`](./schema/framework-mappings.yaml) |
| `related_incidents` | Other `incident_id`s in this corpus |
| `tags` | Free-form tags; **required in practice when `primary_failure_class: other`** |
| `submitted_by` | Contributor handle (optional) |
| **`sources`** | **≥1 required.** Structured objects: `url`, `type`, `title`, `publisher`, `date_accessed`, `archive_url`. No rumors. |
| `evidence_assessments` | Optional claim-level provenance: `{field_path, claim, evidence_status, source_urls, analyst_note, reviewed_at, reviewer, uncertainty}` — see [Claim-level provenance](#claim-level-provenance) |
| `machine_export` | Export hints: `replayable`, `stampede_scenario_hint`, `costbomb_seed_hint` |

## The one rule

Every incident needs at least one **public, linkable source**. Report factually. Name systems without editorializing. Hazards (researcher PoCs, near-misses) are recorded but must be labeled `incident_type: hazard`. Disputed records are annotated (`confidence: disputed`), never deleted (ADR-0008).

## Date semantics

The required `date` has historically meant "occurred *or* first publicly disclosed", so on its own it does not say which. Four optional fields make that explicit without changing `date`:

- `occurred_on` — when the incident happened; for a hazard, when it was first demonstrated.
- `disclosed_on` — when it was first made public, by anyone.
- `published_on` — when the principal cited source report was published.
- `temporal_basis` — which of those the legacy `date` holds: `occurred`, `disclosed`, `published`, or `unknown`.

Rules:

- **Full dates only** (`YYYY-MM-DD`), exactly like `date`, `last_updated` and `sources[].date_accessed`. When a source gives only a month or a year, leave the field out rather than padding it to the first of the month; record the coarser fact in an `evidence_assessments` entry on `/date` if it matters.
- **Never inferred.** Each field is set only when a cited source states it. Records without them stay valid, and an absent field means "not recorded", not "unknown to the world".
- The validator (G-DATES) requires `occurred_on` ≤ `disclosed_on` ≤ `published_on` for whichever are present, and, when `temporal_basis` names a field that is present, that field must equal `date`.
- `date` stays required and keeps its meaning, so existing sorting, filtering and export stamps are unchanged.

## Claim-level provenance

`confidence` rates the record as a whole. `evidence_assessments[]` is an optional, finer-grained layer: each entry says how well one specific statement in the record is supported by the record's own sources. It never replaces or silently changes `confidence`.

| Key | Meaning |
|-----|---------|
| `field_path` | **Required.** RFC 6901 JSON Pointer to the assessed value in this record, e.g. `/root_cause`, `/blast_radius/cost/amount_usd`, `/failure_classes/0/subclass`. It must resolve in the record and must not point into `evidence_assessments` itself. |
| `claim` | **Required.** The specific statement being assessed, in neutral words. |
| `evidence_status` | **Required.** `direct` / `corroborated` / `inferred` / `unknown` / `disputed` (below). |
| `source_urls` | URLs supporting the claim. Each must equal a `url` already listed in this record's `sources[]`, character for character — add the source to `sources[]` first. |
| `analyst_note` | Reasoning behind the status. Required for `inferred` and `disputed`. |
| `reviewed_at` | **Required.** Date the assessment was made (`YYYY-MM-DD`). |
| `reviewer` | Optional pseudonymous handle (letters, digits, `.`, `_`, `-`). Never a legal name or email address. |
| `uncertainty` | What remains unestablished, and what evidence would settle it. |

Status meanings:

- **`direct`** — a cited source states it. Needs ≥1 `source_urls`.
- **`corroborated`** — two or more independent cited sources state it. Needs ≥2 `source_urls`.
- **`inferred`** — analyst reasoning from cited facts; no source states it. Needs `analyst_note`.
- **`unknown`** — the sources do not establish it. Use `uncertainty` to say what is missing.
- **`disputed`** — a cited source or a named party contests it. Needs `analyst_note`; cite the contesting source.

The validator (G-EVIDENCE) rejects an unresolvable `field_path` and any `source_urls` entry not in `sources[]`. Prose in `claim`, `analyst_note` and `uncertainty` is held to the same neutrality lint as the factual fields.

Both extensions — provenance and date semantics — are optional and additive within v1. [ADR-0011](./adr/0011-optional-provenance-and-date-semantics-in-v1.md) records the compatibility evidence, the export behaviour, and the effect on readers that validate against an older copy of the schema.

## What changed vs. v0

v0 was 11 flat fields with a single `failure_class` enum and bare-string sources. v1 keeps all 11 (renamed/nested where noted) and adds the optional body:

- `failure_class` (single) → `primary_failure_class` + ordered `failure_classes[]` chain against a versioned two-level taxonomy.
- `sources: [uri]` → structured source objects with `type` and archival fields.
- `blast_radius` loose strings → typed `cost` / `data` / `user_harm` / `scope` / `reversibility`.
- New: `title`, `summary`, `incident_type`, `status`, `confidence`, `severity`, `causation`, `attack_vector`, `contributing_factors`, `timeline`, cross-references, `machine_export`.
- Unknown top-level fields now rejected.

Migrate old records mechanically with [`scripts/migrate_v0_to_v1.py`](./scripts/migrate_v0_to_v1.py).

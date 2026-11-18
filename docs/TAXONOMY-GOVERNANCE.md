# TAXONOMY-GOVERNANCE — how the failure taxonomy changes

*Who proposes a class, what evidence a proposal needs, who decides, and what an accepted
change does to `taxonomy_version` and to existing records.*

[`schema/taxonomy.yaml`](../schema/taxonomy.yaml) is the authority file and
[`TAXONOMY.md`](../TAXONOMY.md) is its rendered view; the two must stay in lockstep.
[ADR-0002](../adr/0002-multivalued-versioned-taxonomy.md) records why the taxonomy is a
versioned file in the first place. This document covers the process that ADR left open.

## Who decides

The maintainers: the people listed as owners of the `swarmproof/agent-postmortems`
repository on GitHub. Names are deliberately not written here, so the repository's
ownership stays the single source of truth and this document cannot go stale. Anyone may
propose a change; a maintainer accepts or declines it in the proposal issue, and the
accepting maintainer merges the PR.

## Proposing a class or subclass

Open an issue titled `taxonomy: <proposed-name>` containing:

1. **The name and definition.** Kebab-case, in the register of the existing entries
   (one sentence, e.g. "Untrusted input overrides intended instructions.").
2. **Its place.** A new class, or a subclass of a named existing class.
3. **The motivating records.** The `incident_id`s currently classified `other` — or forced
   into an ill-fitting class — and the `tags` they share. `other` requires descriptive
   `tags` (validator gate G-TAX) precisely so these candidates can be found:
   `grep -l "primary_failure_class: other" incidents/*.yaml`.
4. **The `cairn_map` value** (see [cairn-protocol alignment](#cairn-protocol-alignment-cairn_map)).
5. **The framework crosswalk entry** proposed for
   [`schema/framework-mappings.yaml`](../schema/framework-mappings.yaml), or the reason the
   class has no OWASP or MITRE ATLAS counterpart.

## The evidence bar

**Convention: at least three records classified `other` that share a tag.** Three is a
convention, not a rule. A maintainer may accept a clear-cut mechanism on fewer records
(for example a new attack class with one CVE-backed record and published research behind
it), and may ask for more when the shared tag names a product rather than a failure
mechanism. The bar exists to ensure a class describes a *recurring* failure, not one
incident.

A subclass proposal meets the same bar, counted among records of the parent class whose
chain entry carries no subclass or a subclass that fits poorly.

## What an accepted change ships as

One PR that contains all of the following:

- **An ADR** in [`adr/`](../adr/) (next free number) recording the decision, the motivating
  records, and the alternatives rejected.
- **The authority file and its rendering**: the change to `schema/taxonomy.yaml` and the
  matching row in the `TAXONOMY.md` table.
- **The version bump**, applied twice: `version` in `taxonomy.yaml`, and the same value in
  every record's `taxonomy_version`. The validator's G-TAX gate rejects a record whose
  `taxonomy_version` differs from the current taxonomy version, so a bump touches every
  record in the same PR.
- **The crosswalk entry** in `schema/framework-mappings.yaml` — an id list, or `{}` with a
  comment saying why no framework equivalent exists — followed by
  `uv run scripts/apply_mappings.py`, which regenerates each record's derived `mappings`.
  `mappings` is never hand-edited.
- **Reclassification** of the motivating records from `other` to the new class, keeping
  their `tags`.

Before opening the PR run `uv run scripts/validate.py`,
`uv run scripts/apply_mappings.py --check` and `uv run scripts/gen_readme_stats.py`. The
examples block in `TAXONOMY.md` and the coverage row in `README.md` are regenerated from
the corpus and will show the new class.

## Versioning

`taxonomy_version` is `<major>.<minor>`.

| Change | Bump | Effect on existing records |
|---|---|---|
| Add a class or subclass | **minor** (`1.0` → `1.1`) | Only the `taxonomy_version` field changes; existing classifications stay valid as they are. |
| Rename or remove a class or subclass; move a subclass to another parent | **major** (`1.x` → `2.0`) | Every record that uses the old name is migrated by a script in the style of [`scripts/migrate_v0_to_v1.py`](../scripts/migrate_v0_to_v1.py): mechanical, idempotent, run across the whole corpus in the same PR, and leaving a `TODO` marker wherever the new value needs a human decision instead of guessing one. |
| Clarify a definition without changing which incidents it covers | none | None. No ADR is needed; `TAXONOMY.md` is updated in lockstep. |

A removal never deletes records ([ADR-0008](../adr/0008-never-delete-annotate-disputed.md)).
Records of a removed class are migrated to its successor class, or to `other` with a tag
that preserves the old class name so the history stays searchable.

## cairn-protocol alignment (`cairn_map`)

Every class carries `cairn_map`, the name of the corresponding class in cairn-protocol's
failure taxonomy; the `TAXONOMY.md` table renders it as the *cairn map* column. A proposal
must name the cairn class it maps to. Where cairn-protocol has no counterpart, or the two
definitions diverge, the header of `taxonomy.yaml` requires the class to be flagged
`divergent: true` and the divergence to be documented in the ADR. The field is never left
empty and never reuses another class's value for convenience.

## PR checklist for a taxonomy change

- [ ] Proposal issue links the motivating records (three or more `other` records with a shared tag, or a stated exception)
- [ ] ADR added under `adr/`
- [ ] `schema/taxonomy.yaml` and the `TAXONOMY.md` table changed in lockstep
- [ ] `version` bumped (minor for additions, major for renames or removals) and every record's `taxonomy_version` updated
- [ ] `schema/framework-mappings.yaml` entry added (ids, or `{}` with a reason) and `scripts/apply_mappings.py` run
- [ ] `cairn_map` set; `divergent: true` and ADR note if cairn-protocol has no equivalent
- [ ] Migration script added and run for a rename or removal
- [ ] `validate.py`, `apply_mappings.py --check` and `gen_readme_stats.py --check` pass

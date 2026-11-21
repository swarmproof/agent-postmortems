# METHODS — how the corpus is built, and what it can and cannot tell you

*A short reader's guide to the method behind the records. It links to the detailed
documents rather than repeating them: [`SCHEMA.md`](../SCHEMA.md) for the fields,
[`TAXONOMY.md`](../TAXONOMY.md) for the failure classes,
[`docs/CURATION-PIPELINE.md`](./CURATION-PIPELINE.md) for the automation, and
[`docs/DATASHEET.md`](./DATASHEET.md) for measured properties of the current corpus.*

## What a record is

Each file in `incidents/` describes one failure in which an AI agent **took or
recommended an action** (a tool call, a write, a payment, a code execution, a message
sent) and something went wrong. Model outputs on their own, vendor marketing, funding
news and general commentary are out of scope.

A record is a structured, sourced description: what set the failure off, the ordered
chain of failure classes, the root cause written in blameless style, how it was detected
and stopped, and its reported impact. Records are **descriptions, not executable tests**.
The `scenarios.json` and `seeds.json` exports carry natural-language hints that other
tools can consume; this repository does not run them.

## How records are found and curated

Candidates arrive by three routes:

1. **Automated discovery.** A weekly job searches security-research feeds, first-party
   lab and vendor disclosures, arXiv, Google News, the NVD CVE database and the GitHub
   Advisory Database, removes likely duplicates, and posts a ranked list as an issue.
2. **Completeness check.** A second weekly job compares the corpus against a curated
   external index of agent attacks and files what is missing as an issue.
3. **Contributions.** Anyone can report a failure through the
   [issue form](https://github.com/swarmproof/agent-postmortems/issues/new/choose) without
   writing YAML, or open a pull request with a full record
   ([`CONTRIBUTING.md`](../CONTRIBUTING.md)).

Both automated jobs, and the optional job that drafts records as review pull requests,
are described in [`docs/CURATION-PIPELINE.md`](./CURATION-PIPELINE.md).

**Every record passes human review before it is merged.** Automation finds, de-duplicates,
drafts and validates; it never merges. A maintainer reads the cited sources, checks the
classification and the neutral wording, and approves the pull request. Continuous
integration then enforces the schema, the taxonomy, unique ids, a neutrality lint and
source-link liveness on every change. A passing check is not editorial review, and the
review is not skipped because checks pass. How maintainers handle issue-form reports is
in [`docs/TRIAGE.md`](./TRIAGE.md).

The admission rule is the same for every route: **at least one public, linkable source**.
No rumours, no private accounts, no speculation about intent. A candidate that cannot be
sourced is discarded, not guessed.

## Incident or hazard

Every record carries `incident_type`:

| Value | Meaning |
|---|---|
| `incident` | Realized harm in the wild: the failure happened in real use. |
| `hazard` | A demonstrated proof of concept, evaluation finding or near miss that could plausibly cause harm, following the OECD incident/hazard distinction. |

Hazards are recorded because many agent failure modes are first shown by researchers
before anyone is harmed ([ADR-0005](../adr/0005-admit-hazards.md)). They are labelled so
the two are never mixed by accident. When you count or compare records, decide first
whether you want incidents, hazards, or both.

## How much to trust a record: the legend

These fields are assigned by a curator from the sources and checked in review. They are
judgements, not measurements.

**`confidence`: how well the facts are sourced.**

| Value | Meaning |
|---|---|
| `reported` | A single source. |
| `corroborated` | Multiple independent sources. |
| `confirmed` | Confirmed first-party: by the vendor or operator, or by a court or regulator. |
| `disputed` | The facts are contested, and both accounts are carried in the record. |

`confidence` is optional in the schema, so a record may not carry it.

**`status`: how mature the report is**, in the style of transportation-safety reports:
`preliminary`, `factual` (the default) or `final`. Contested facts are expressed through `confidence`, not
`status`.

**`severity`: an impact band.** `critical`, `high`, `moderate`, `low` or `informational`,
with the reasoning in `severity_rationale`. It is a band, not a score, and should not be
converted into a number.

**`sources[].type`** says what kind of evidence each source is: `primary-research`,
`vendor-disclosure`, `vendor-response`, `regulatory-court`, `news`, `academic`,
`social-primary` or `other`. A `vendor-response` source is a named party's reply to the
record (see [Corrections and disputes](#corrections-and-disputes)).

## What `date` means, and its limits

The schema defines `date` as the date the failure **occurred or was first publicly
disclosed**. The field does not say which of the two it holds. For many records the
occurrence date was never published, so the disclosure date is used. A failure that ran
for weeks before a researcher wrote it up may therefore be dated by the writeup.

Where the sources give both, the record's optional `timeline` may list them as separate
events. The site sorts records and filters by year using `date`, and the year at the start
of an `incident_id` normally matches it.

In practice: `date` is good for ordering records roughly and finding them. It is not a
reliable basis for claims about *when* failures happen. For that, read the timeline and
the sources.

## Coverage: what the corpus does not tell you

The corpus records **what has been publicly reported**, not how often agents fail.

- **Public reporting is not prevalence.** Most agent failures are never written up.
  Failures that are written up skew towards security research, severe outcomes, and
  English-language technical and trade press.
- **Counts per vendor are not a ranking.** Vendors and researchers that publish more,
  such as detailed postmortems, evaluation reports and disclosure programmes, appear more
  often. A vendor with many records may simply be more transparent. Nothing in this corpus
  is a safety ranking of vendors, products or models.
- **Counts over time measure attention.** Growth in records per month reflects when the
  corpus was curated and where researchers were looking, as much as any change in failure
  rates.
- **Coded fields are judgement calls.** Severity, confidence, autonomy level and the causal
  chain are assigned by people from the sources, and reviewed.

[`docs/DATASHEET.md`](./DATASHEET.md) quantifies these biases for a given snapshot.
Figures there describe the corpus at the time it was written, so recompute them from
`export/incidents.json` for current work.

## Corrections and disputes

Records are **corrected, never deleted** ([ADR-0008](../adr/0008-never-delete-annotate-disputed.md)).
A factual error shown by a public source is fixed. Where sources genuinely conflict, the
record carries both accounts and `confidence: disputed`. A named party's public reply is
added as a `vendor-response` source.

The full process, including who can dispute, what to include and what is out of scope, is
in [`DISPUTES.md`](../DISPUTES.md). A record that exposes personal data or a runnable
payload is a security defect: report it under [`SECURITY.md`](../SECURITY.md). Every change
to a record is visible in its git history.

## Versioning

| What | Version | Where it is defined |
|---|---|---|
| Record format | `schema_version: "1.0"` on every record | [`SCHEMA.md`](../SCHEMA.md), [`schema/incident.schema.json`](../schema/incident.schema.json) |
| Failure taxonomy | `taxonomy_version` on every record; minor bump to add a class, major to rename or remove | [`docs/TAXONOMY-GOVERNANCE.md`](./TAXONOMY-GOVERNANCE.md) |
| Export files | `export_schema_version` in each JSON export | [`schema/export/`](../schema/export/) |
| Corpus snapshots | CalVer release tags (`YYYY.MM`, then `YYYY.MM.N`) with the exports attached | [`docs/RELEASING.md`](./RELEASING.md) |

`incident_id`s are stable and are never renamed once published, so permalinks and
citations keep working. The exports on `main` are regenerated when a change to records, schema or scripts is
merged, and daily.
To cite a fixed corpus, cite a release tag ([`CITATION.cff`](../CITATION.cff)).

## FAQ

**Why is a failure I know about missing?**
Either nobody has submitted it yet, or no public source supports it. Use the
[issue form](https://github.com/swarmproof/agent-postmortems/issues/new/choose); one link
is enough to start.

**Can a record about my product be removed or anonymised?**
No. Records name the systems involved; that is what makes the corpus useful. If the record
is wrong, it will be corrected; if the facts are contested, your public response becomes
part of it. See [`DISPUTES.md`](../DISPUTES.md).

**Does a vendor with many records have less safe products?**
Not on this evidence. Record counts track disclosure and research attention. See
[Coverage](#coverage-what-the-corpus-does-not-tell-you).

**Why are proofs of concept included?**
Because many agent failure modes are first demonstrated, not first suffered. They are
labelled `hazard` and can be filtered out.

**Who writes the records?**
Maintainers and contributors, sometimes starting from a machine-drafted pull request. In
every case a human reviews the sources and approves the record before it is merged.

**Can I use the data?**
Yes. Records and exports are CC-BY-4.0 ([`LICENSE-DATA`](../LICENSE-DATA)); code and schema
are Apache-2.0 ([`LICENSE`](../LICENSE)).

**Do records contain working exploits?**
No. Triggers are described as natural-language shapes, and the export build rejects
scenario and seed hints that look like exploit code. If you find one, report it under
[`SECURITY.md`](../SECURITY.md).

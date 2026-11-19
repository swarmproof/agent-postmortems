# Contributing to agent-postmortems

Thanks for helping build **agent-postmortems** — part of the [Swarm Proof toolkit](https://github.com/swarmproof).

## Ways to contribute
- **Report an agent failure** — no YAML needed. Use the [Report an agent failure](https://github.com/swarmproof/agent-postmortems/issues/new/choose) issue form with at least one public source; a maintainer turns it into a record. Writing the record yourself (below) is the faster route if you are comfortable with YAML.
- **Good first issues** — look for the `good-first-issue` label. A few are seeded to get you started.
- **Bug reports** — open an issue with a minimal reproduction.
- **Features & discussion** — open an issue before a large PR so we can align on direction.

## Development
1. Fork and clone.
2. Create a branch: `git checkout -b feat/<short-name>`.
3. Keep commits atomic and use [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, ...).
4. Open a PR describing *what* changed and *why*.

## Contributing an incident

1. Copy [`incidents/_TEMPLATE.yaml`](./incidents/_TEMPLATE.yaml) to `incidents/<incident_id>.yaml` — the filename must equal `incident_id` (`YYYY-kebab-slug`).
2. Fill the required core; add as much of the optional body as the sources support. Classify with the taxonomy in [`TAXONOMY.md`](./TAXONOMY.md).
3. Validate locally: `uv run scripts/validate.py`, then `uv run scripts/check_links.py incidents/<incident_id>.yaml` — the scoped link check CI runs on a pull request. With no arguments, `check_links.py` checks the whole corpus.
4. Open a PR — the PR template contains the checklist below, and CI enforces every gate.

### Sourcing rules (the one rule)

- Every incident needs **at least one public, linkable source**. No rumors, no anonymous accounts, no speculation about intent.
- Prefer the strongest source type available: primary research writeup, vendor disclosure, or court/regulatory record over news coverage.
- Set `confidence` honestly: `reported` (single source) · `corroborated` (multiple independent) · `confirmed` (first-party/vendor/court) · `disputed` (facts contested).
- Label researcher PoCs and near-misses `incident_type: hazard`, distinct from realized incidents.

### Neutrality rules

- Report factually; name systems as data, never as targets. No blame adjectives (CI lints for these).
- Root causes are **systemic, not personal** (blameless post-mortem style).
- Never identify harmed individuals beyond what public sources already published.
- If a vendor disputes a record, we add their response as a `vendor-response` source and set `confidence: disputed` — sourced incidents are never deleted (ADR-0008).

### Disputing a record

A named party who contests the facts of a record follows the process in [`DISPUTES.md`](./DISPUTES.md). The dispute becomes part of the record; the record itself is annotated, never removed.

### Security and personal data

A record that carries a runnable payload or personal data beyond its sources, or a vulnerability in the tooling, is reported under [`SECURITY.md`](./SECURITY.md), not in a public issue.

### Method and triage

[`docs/METHODS.md`](./docs/METHODS.md) explains how records are found and reviewed, the incident/hazard and confidence definitions, what `date` means, and the limits of the corpus. Maintainers handle issue-form reports with [`docs/TRIAGE.md`](./docs/TRIAGE.md); nothing is published without a human reviewing its sources.

## Principles
- **Provider-agnostic** — no hard dependency on a single model vendor.
- **Factual over promotional** — document what happened and its boundaries; don't editorialize.
- **Reproducible** — validation and exports regenerate deterministically from the repo.

By contributing you agree that code (schema, validators, scripts, site) is licensed under [Apache-2.0](./LICENSE) and incident records (`incidents/`, `export/`) under [CC-BY-4.0](./LICENSE-DATA), as set out in [ADR-0009](./adr/0009-data-license.md).

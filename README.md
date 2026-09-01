# agent-postmortems

A public, structured database of real AI-agent failures, plus a schema for reporting them.

**Browse the corpus → https://swarmproof.github.io/agent-postmortems/**

## Why

Agents fail in production in novel, repeating ways — runaway loops, tool misuse, prompt injection, double side-effects, cost blowups — but there's no shared, structured record of these failures. This repository provides a reporting schema and a corpus of incidents that conform to it, so the same failures are documented once and reusable across teams.

## The post-mortem standard

Every incident is one YAML file conforming to [`schema/incident.schema.json`](./schema/incident.schema.json) (draft 2020-12), documented in [`SCHEMA.md`](./SCHEMA.md) and validated fail-closed in CI. The record carries a small required core — `incident_id` · `title` · `date` · `incident_type` · `system` · `primary_failure_class` · `failure_classes` · `trigger` · `blast_radius` · `root_cause` · `detection` · `recovery` · `prevention` · `sources` — plus an optional body (`severity`, `confidence`, `causation`, `attack_vector`, `timeline`, cross-references, and more).

Failures are classified as an ordered causal **chain** against the versioned taxonomy in [`TAXONOMY.md`](./TAXONOMY.md) (authority file: [`schema/taxonomy.yaml`](./schema/taxonomy.yaml)). Realized incidents and demonstrated hazards/near-misses are both recorded, labeled honestly via `incident_type`.

**The one rule:** every incident needs a public, linkable source. No rumors, no speculation, no editorializing. Report failures factually; name systems without attacking them. Credibility depends on this rigor — and CI enforces it (schema, taxonomy, id-uniqueness, link-liveness, and a neutrality lint).

## Browse and cite

The corpus is published as a static site at **[swarmproof.github.io/agent-postmortems](https://swarmproof.github.io/agent-postmortems/)** — a filterable index (by failure class, severity, incident/hazard, year), a permalink page per incident with a copyable **BibTeX** citation, and an [RSS feed](https://swarmproof.github.io/agent-postmortems/feed.xml). The site is generated from `incidents/*.yaml` by [`scripts/build_site.py`](./scripts/build_site.py) and redeployed on every merge.

## Contribute an incident

Copy [`incidents/_TEMPLATE.yaml`](./incidents/_TEMPLATE.yaml), fill it in, validate locally with `uv run scripts/validate.py`, and open a PR. The PR template carries the sourcing + neutrality checklist; CI runs every gate. See [`CONTRIBUTING.md`](./CONTRIBUTING.md).

## Automated curation pipeline

Weekly workflows find new and not-yet-documented agent incidents and file them for review — **automating the toil (discovery, de-dup, drafting, validation) but never merging anything without a human**:

- **Discovery** harvests candidates from keyless sources — security-research feeds, first-party lab/vendor disclosures, arXiv, Google News, and the **NVD CVE / GitHub advisory** databases — de-dupes against the corpus, and posts a ranked "candidate incidents" issue (zero setup).
- **Completeness critic** diffs the corpus against curated external agent-incident lists each week and files a "coverage gaps" issue — the "what did we miss?" review, automated.
- **Auto-draft** (opt-in, set an `ANTHROPIC_API_KEY` secret) has Claude research each candidate and open review-ready PRs.

See [`docs/CURATION-PIPELINE.md`](./docs/CURATION-PIPELINE.md).

## How it feeds the toolkit

CI regenerates a machine-readable export under [`export/`](./export/): the full corpus (`incidents.json`), a scenario feed for [stampede](https://github.com/swarmproof/stampede) (`scenarios.json`), and a seed feed for [costbomb](https://github.com/swarmproof/costbomb) (`seeds.json`). Export entries are natural-language trigger descriptions, never runnable exploit payloads.

## Related projects

Part of the Swarm Proof toolkit for agent reliability:

| Project | What it does |
|---------|--------------|
| [stampede](https://github.com/swarmproof/stampede) | Drives simulated agent traffic at a system under test |
| [mockworld](https://github.com/swarmproof/mockworld) | Mock external services (payments, email, exchange) for agent tests |
| [mcp-probe](https://github.com/swarmproof/mcp-probe) | Lint, contract-test, benchmark, and load-test MCP servers |
| [costbomb](https://github.com/swarmproof/costbomb) | Fuzzing for denial-of-wallet / unbounded-spend inputs |
| [exactly-once](https://github.com/swarmproof/exactly-once) | Idempotency middleware for agent side-effects |
| [awesome-agent-reliability](https://github.com/swarmproof/awesome-agent-reliability) | Curated list of agent-reliability resources |

## Licensing

Dual-licensed to separate the tooling from the corpus:

- **Code** (schema, validators, scripts, site) — [Apache-2.0](./LICENSE).
- **Incident data & schema content** (the `incidents/` corpus and `SCHEMA.md`) — [CC-BY-4.0](./LICENSE-DATA). Reuse freely with attribution.

Citable via [`CITATION.cff`](./CITATION.cff).

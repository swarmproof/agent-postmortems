# agent-postmortems

### The aviation-incident database for the agent economy

> A public, structured database of real agent failures in the wild — plus a post-mortem *standard* for reporting them. Each team relearns the same failures privately; this makes the field's mistakes legible so they stop recurring.

> **Status:** ✅ v1 live. Standard + taxonomy + rigor CI + 18 sourced incidents + machine-readable export. Site is the next wave.

---

## Why

Agents fail in production in novel, repeating ways — runaway loops, tool misuse, prompt-injection incidents, double side-effects, cost blowups — but there's no shared, structured record. Software has public post-mortem culture; aviation has incident reports. The agent economy has nothing. **Publishing a standard is more valuable than the data itself** — it makes the field legible.

## The post-mortem standard

Every incident is one YAML file conforming to [`schema/incident.schema.json`](./schema/incident.schema.json) (draft 2020-12), documented in [`SCHEMA.md`](./SCHEMA.md) and validated fail-closed in CI. The record carries a small required core — `incident_id` · `title` · `date` · `incident_type` · `system` · `primary_failure_class` · `failure_classes` · `trigger` · `blast_radius` · `root_cause` · `detection` · `recovery` · `prevention` · `sources` — plus an optional body (`severity`, `confidence`, `causation`, `attack_vector`, `timeline`, cross-references, and more).

Failures are classified as an ordered causal **chain** against the versioned taxonomy in [`TAXONOMY.md`](./TAXONOMY.md) (authority file: [`schema/taxonomy.yaml`](./schema/taxonomy.yaml)). Realized incidents and demonstrated hazards/near-misses are both recorded, labeled honestly via `incident_type`.

**The one rule:** every incident needs a public, linkable source. No rumors, no speculation, no editorializing. Report failures factually; name systems without attacking them. The trust brand depends on this rigor — and CI enforces it (schema, taxonomy, id-uniqueness, link-liveness, and a neutrality lint).

## Contribute an incident

Copy [`incidents/_TEMPLATE.yaml`](./incidents/_TEMPLATE.yaml), fill it in, validate locally with `uv run scripts/validate.py`, and open a PR. The PR template carries the sourcing + neutrality checklist; CI runs every gate. See [`CONTRIBUTING.md`](./CONTRIBUTING.md).

## How it feeds the toolkit

CI regenerates a machine-readable export under [`export/`](./export/): the full corpus (`incidents.json`), a [stampede](https://github.com/swarmproof/stampede) chaos-scenario feed (`scenarios.json`), and a [costbomb](https://github.com/swarmproof/costbomb) denial-of-wallet seed feed (`seeds.json`) — the contract behind *"replay last month's real incidents against your stack."* Export shapes are natural-language triggers, never runnable exploit payloads.

## Part of the Swarm Proof toolkit

*Trust infrastructure for the agent economy — seven projects, one thesis.*

| Project | What it does |
|---------|--------------|
| [stampede](https://github.com/swarmproof/stampede) | Point a herd of realistic agents at your system before real ones arrive |
| [mockworld](https://github.com/swarmproof/mockworld) | A synthetic internet for agents — fake Stripe, Gmail, exchange, instantly |
| [mcp-probe](https://github.com/swarmproof/mcp-probe) | The CI quality suite for MCP servers — lint, contract-test, benchmark, load |
| [costbomb](https://github.com/swarmproof/costbomb) | Denial-of-wallet fuzzing — find the inputs that make your agent spend $500 |
| [exactly-once](https://github.com/swarmproof/exactly-once) | Idempotency middleware so agent side-effects fire once |
| **agent-postmortems** ← *you are here* | A structured incident database + post-mortem standard for agent failures |
| [awesome-agent-reliability](https://github.com/swarmproof/awesome-agent-reliability) | The curated map of the field |

## Licensing

This project is dual-licensed to separate the tooling from the corpus:

- **Code** (schema, validators, scripts, site) — [Apache-2.0](./LICENSE).
- **Incident data & schema content** (the `incidents/` corpus and `SCHEMA.md`) — [CC-BY-4.0](./LICENSE-DATA). Reuse freely with attribution.

Citable via [`CITATION.cff`](./CITATION.cff).

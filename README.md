# agent-postmortems

### The aviation-incident database for the agent economy

> A public, structured database of real agent failures in the wild — plus a post-mortem *standard* for reporting them. Each team relearns the same failures privately; this makes the field's mistakes legible so they stop recurring.

> **Status:** 📖 v0. Standard first, then seeded incidents. Ships in the first wave.

---

## Why

Agents fail in production in novel, repeating ways — runaway loops, tool misuse, prompt-injection incidents, double side-effects, cost blowups — but there's no shared, structured record. Software has public post-mortem culture; aviation has incident reports. The agent economy has nothing. **Publishing a standard is more valuable than the data itself** — it makes the field legible.

## The post-mortem standard

Every incident conforms to the schema in [`SCHEMA.md`](./SCHEMA.md) (JSON Schema in [`schema/incident.schema.json`](./schema/incident.schema.json)), validated in CI:

`incident_id` · `date` · `system` (framework/models/tools) · `failure_class` (taxonomy) · `trigger` · `blast_radius` (cost / data / user harm) · `root_cause` · `detection` · `recovery` · `prevention` · `sources`.

**The one rule:** every incident needs a public, linkable source. No rumors, no speculation, no editorializing. Report failures factually; name systems without attacking them. The trust brand depends on this rigor.

## Contribute an incident

Copy [`incidents/_TEMPLATE.yaml`](./incidents/_TEMPLATE.yaml), fill it in, and open a PR. CI validates it against the schema. See [`CONTRIBUTING.md`](./CONTRIBUTING.md).

## How it feeds the toolkit

Each incident becomes a [stampede](https://github.com/swarmproof/stampede) chaos scenario, a [costbomb](https://github.com/swarmproof/costbomb) fuzz seed, and evidence for the trust thesis — *"replay last month's real incidents against your stack."*

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

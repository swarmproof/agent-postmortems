# agent-postmortems — Roadmap

## Shipped
- **Post-mortem standard** — JSON Schema (`schema/incident.schema.json`) + human-readable `SCHEMA.md`
- **Versioned two-level failure taxonomy** (`schema/taxonomy.yaml` + `TAXONOMY.md`)
- **Fail-closed CI** — schema, taxonomy conformance, id-uniqueness, link-liveness, neutrality lint, drift check, export build, and site smoke build
- **Corpus** — sourced, schema-valid public incidents (realized incidents and demonstrated hazards); the current count is the README stats block and the `incidents` badge, both generated from `export/incidents.json`
- **Machine-readable export** (`export/incidents.json`, `scenarios.json`, `seeds.json`) + export schemas, regenerated on merge
- **Versioned releases** — tagged GitHub releases carrying `incidents.json`, `scenarios.json` and `seeds.json` as assets, so consumers can pin a snapshot
- **Contribution flow** — template, PR template with sourcing/neutrality checklist, architecture decision records
- **Curation pipeline** (`docs/CURATION-PIPELINE.md`):
  - discovery from security-research feeds, first-party lab disclosures, arXiv, Google News, and the NVD CVE / GitHub advisory databases
  - candidate dedup against the corpus by cited URL and by CVE id, plus title-overlap flagging (`scripts/discover_incidents.py`)
  - a completeness critic that diffs the corpus against curated external lists and files coverage gaps
  - an opt-in auto-draft layer that turns candidates into review PRs
- **Static site** at [swarmproof.github.io/agent-postmortems](https://swarmproof.github.io/agent-postmortems/) (`scripts/build_site.py`) — filterable index, per-incident permalinks, BibTeX citation, RSS; deployed by `.github/workflows/pages.yml`

## Ongoing
- Add incidents per notable public failure (candidates surface weekly via the pipeline)
- Weekly link re-check (`.github/workflows/links.yml`): archive backfill for sources, and an issue for dead links; sources are never auto-deleted (`adr/0008-never-delete-annotate-disputed.md`)
- Export + site redeploy on every merge

## Planned
- Two-stage LLM triage to raise candidate precision as volume grows
- First-party-feed daily cadence for faster catch of critical disclosures (discovery currently runs weekly)
- Consume the `scenarios.json` / `seeds.json` export in downstream replay/fuzzing tooling
- Optional custom domain (`agent-postmortems.dev`) and richer site search

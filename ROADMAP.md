# agent-postmortems — Roadmap

## Shipped
- Post-mortem standard — JSON Schema (`schema/incident.schema.json`) + human-readable `SCHEMA.md`
- Versioned two-level failure taxonomy (`schema/taxonomy.yaml` + `TAXONOMY.md`)
- Fail-closed CI: schema, taxonomy conformance, id-uniqueness, link-liveness, neutrality lint, drift check
- Seed corpus of 18 well-documented, sourced public incidents (all schema-valid, all sources live)
- Machine-readable export (`export/incidents.json`, `scenarios.json`, `seeds.json`) + export schemas
- Contribution flow: template, PR template with sourcing/neutrality checklist, architecture decision records
- Automated weekly discovery pipeline that finds and files candidate incidents for human review (`docs/CURATION-PIPELINE.md`)

## Ongoing
- Add one incident per notable public failure
- Weekly link re-check; open issues on rot, never auto-delete (see `adr/0008-never-delete-annotate-disputed.md`)
- Periodic export refresh

## Planned
- Generated static site with per-incident permalinks, filters by failure class / blast radius, "Cite this", and RSS (see `adr/0003-astro-for-site.md`)
- Consume the `scenarios.json` / `seeds.json` export in downstream replay/fuzzing tooling
- Cross-linking with external incident databases; full-text search

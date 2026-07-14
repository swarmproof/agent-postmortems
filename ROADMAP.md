# agent-postmortems — Roadmap

## v1 (shipped)
- ✅ Post-mortem standard v1 — JSON Schema (`schema/incident.schema.json`) + human-readable `SCHEMA.md`
- ✅ Versioned two-level failure taxonomy (`schema/taxonomy.yaml` + `TAXONOMY.md`), cairn-aligned
- ✅ Fail-closed CI: schema, taxonomy conformance, id-uniqueness, link-liveness, neutrality lint, drift check
- ✅ 18 well-documented, sourced public incidents (all schema-valid, all sources live)
- ✅ Machine-readable export contract (`export/incidents.json`, `scenarios.json`, `seeds.json`) + export schemas
- ✅ Contribution flow: v1 template, PR template with sourcing/neutrality checklist, ADRs
- ⬜ Announce via a Trust Layer issue: "We Need Post-Mortems for Agents"

## Ongoing cadence
- Add one incident per notable public failure (steady, low-effort, permanent)
- Weekly scheduled link re-check; open issues on rot, never auto-delete (ADR-0008)
- Monthly export refresh

## Later (second wave)
- Generated static site (agent-postmortems.dev), Astro — permalinks, filters by failure class / blast radius, "Cite this", RSS (ADR-0003)
- Wire `scenarios.json` / `seeds.json` into stampede and costbomb
- AIID / OECD auto-cross-linking; full-text search

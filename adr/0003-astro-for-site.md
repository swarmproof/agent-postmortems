# ADR-0003 — Astro for the static site

**Status:** Accepted (site ships in the second wave, M5)

## Decision
The site under `site/` will be built with Astro, binding incidents to a content collection whose schema mirrors `incident.schema.json`.

## Rationale
Content-collection schema validation makes the site build itself fail if an incident drifts from the schema — a second validation gate for free. Islands keep the filter UI cheap with no backend.

## Alternatives rejected
- Hugo — fast, but data-schema validation is manual.
- Docusaurus — docs framing, not data-catalog framing.

# The Agent Post-Mortem Standard

A single, boring, rigorous schema so agent failures become comparable across the industry. Publishing the *standard* is the contribution; the data compounds on top of it.

## Fields

| Field | Meaning |
|-------|---------|
| `incident_id` | Stable slug, e.g. `2025-whatsapp-mcp-exfiltration` |
| `date` | When it happened (`YYYY-MM-DD`) |
| `system` | Framework, models, tools involved |
| `failure_class` | Taxonomy term (see below) |
| `trigger` | What set it off |
| `blast_radius` | Cost ($), data exposed/lost, user harm |
| `root_cause` | The actual underlying cause |
| `detection` | How it was noticed |
| `recovery` | How it was stopped/fixed |
| `prevention` | What would stop a recurrence |
| `sources` | **Required.** Public, linkable. No rumors. |

## Failure taxonomy
`runaway-loop` · `tool-misuse` · `prompt-injection` · `double-side-effect` · `cost-blowup` · `data-exfiltration` · `unsafe-action` · `other`

## The one rule
Every incident needs at least one public, linkable source. Report factually. Name systems without editorializing. Machine-validated by [`schema/incident.schema.json`](./schema/incident.schema.json) in CI.

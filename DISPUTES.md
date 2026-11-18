# Disputes and corrections

This corpus names real systems and real vendors. If a record about your system, your product, or your research says something you believe is wrong, this page explains what you can do and what will happen.

The short version: **we correct records, we never delete them.** Where the facts are genuinely contested, the record says so, and your response becomes part of it.

## Who can dispute a record

Anyone. In practice disputes come from:

- the vendor or operator of the system named in a record
- the researcher whose work a record describes
- a person or organisation the record identifies
- a reader who has found a public source that contradicts the record

You do not need to be a contributor, and you do not need to represent anyone. You do need a public source.

## How to dispute

Open a [GitHub issue](https://github.com/swarmproof/agent-postmortems/issues/new) with three things:

1. **The `incident_id`.** It is the filename under `incidents/` and the slug in the site permalink, for example `2025-replit-prod-db-deletion`.
2. **The statement you contest.** Quote the field and the words. "The record is unfair" is not actionable; "`root_cause` says the approval gate was absent, but it was present and bypassed" is.
3. **A public, linkable source for the correction.** A published statement, a changelog, a postmortem, a court or regulator filing, a press release, a public bug tracker entry. The same rule that admits a record applies to correcting one: at least one public source, no private assurances.

A maintainer may ask for clarification in the issue. Everything stays public.

If the correction needs a code change, you can also open a pull request against the record. The PR template carries the sourcing and neutrality checklist.

## What happens

The record's `sources` list and `confidence` field are the mechanism. They are defined in [`schema/incident.schema.json`](./schema/incident.schema.json) and the policy is [ADR-0008](./adr/0008-never-delete-annotate-disputed.md).

**Your response is added to the record.** Your public source is appended to `sources` with `type: vendor-response`. The schema reserves that type specifically for the named party's reply, so readers and downstream tools can always see that the record carries a right of reply.

**Where the source shows an error, the record is corrected.** If your source establishes that a field is wrong, that field is changed. A wrong date, a mis-stated blast radius, a `root_cause` that the vendor's postmortem contradicts: these are edited, and the edit is visible in git history.

**Where the facts are contested, `confidence` is set to `disputed`.** The schema defines `disputed` as "facts contested". It is used when your source and the existing sources disagree and neither clearly settles the question. The record then carries both accounts, labelled, and the reader decides. `disputed` is not a penalty against the record or against you. It is an honest statement of what the sources support.

**The record is never deleted.** Permalinks, citations, and exports depend on it, and the history of a dispute is itself data. This is the project's standing decision, not a case-by-case judgement.

**Neutrality is enforced on the result, too.** Records name systems as data, never as targets. Root causes are written as systemic, not personal. CI runs a neutrality lint on every change. If a record uses blame language, say so in the issue and it will be fixed whether or not the underlying facts are in dispute.

## What is out of scope

These requests are declined, with the reason in the issue:

- **Removing a sourced record.** A record that cites a public source stays. If the source itself has been retracted or corrected, that retraction is a public source and the record will be corrected to match it.
- **Anonymising the system.** Records identify the agent, framework, or model involved. That is the point of the corpus. A record will not be edited to refer to "a coding assistant" instead of the product name.
- **Reclassifying a hazard as a non-event.** A researcher proof-of-concept or a near-miss is recorded with `incident_type: hazard`, distinct from a realised incident. If a record labels something an `incident` that was only ever a demonstration, that is a correction we will make. Asking that a demonstrated hazard not be recorded at all is not.
- **Disputes without a public source.** "That did not happen" with nothing linkable cannot be acted on. A public statement from you saying it did not happen is a source, and will be added as `vendor-response`.
- **Disputes about individuals the record does not name.** Records never identify harmed individuals beyond what the cited sources published. If a record does, that is a defect: report it under [SECURITY.md](./SECURITY.md).

## Timing

This project is maintained by volunteers. Disputes are handled in the order received, on a best-effort basis. A well-formed issue with a clear source is normally acknowledged within a week, and a correction with an unambiguous source is usually a small pull request. Disputes where the sources genuinely conflict can take longer, because the outcome is a judgement about what the sources support, not a mechanical edit.

While an issue is open, the record stays as it is. The `confidence` change and the `vendor-response` source land together when the dispute is resolved.

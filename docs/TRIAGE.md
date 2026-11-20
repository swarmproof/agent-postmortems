# TRIAGE — turning a reported failure into a record

*For maintainers. How to handle an issue opened with the "Report an agent failure" form:
from a public report to a valid v1 record in about fifteen minutes, or to a clear decline.*

Reports land as issues labelled `needs-review` (and `submission`, once that label exists).
Open queue:
[`is:issue is:open label:needs-review`](https://github.com/swarmproof/agent-postmortems/issues?q=is%3Aissue+is%3Aopen+label%3Aneeds-review).

## The rule

**Nothing is published without source review.** A report becomes a record only through a
pull request that a maintainer approves after reading every cited source. No workflow reads
these issues, and nothing in the repository turns an issue into a record automatically.
CI checks on the pull request verify format and links. They do not verify that the record
is true, fair or neutral; that is the reviewer's job.

Do not add the `candidates` label to a report. The weekly discovery job rewrites the body
of an open issue carrying that label with its own candidate list.

## 1. Screen (2 minutes)

Before anything else, check the issue for content that must not stay public:

- **Personal data, credentials, private logs, unpublished information, or an exploit
  payload.** Edit the issue to remove it, then delete the earlier revision from the edit
  history (the "edited" menu on the issue body). Tell the reporter why in a comment that
  does not repeat the removed content. If a payload or personal data has already reached a
  record, handle it under [`SECURITY.md`](../SECURITY.md).
- **A dispute about an existing record.** Point the reporter to
  [`DISPUTES.md`](../DISPUTES.md) and handle it there.
- **Out of scope.** No agent took or recommended an action (a model output on its own,
  marketing, funding news, general commentary). Close as not planned, with the reason.
- **No public source**, or only a private account. Ask once for a public link; close if
  none comes. Do not research around a missing source to rescue the report.

## 2. Check for duplicates (2 minutes)

Search the corpus for each source URL, the CVE and the system name:

```bash
git grep -n -i "<distinctive part of the URL>" incidents/
git grep -n "CVE-2025-12345" incidents/
git grep -l -i "<product name>" incidents/
```

If the event is already recorded, either add the new source to the existing record (a new
independent source can raise `confidence` from `reported` to `corroborated`) or close the
issue as a duplicate with a link to the record. Different events involving the same
system are separate records, linked through `related_incidents`.

## 3. Read the sources (5 minutes)

Open every link. Write the record from the sources, not from the report: the report tells
you where to look. Note:

- whether this is real use (`incident`) or a demonstration or near miss (`hazard`). The
  reporter's choice is a hint, not a decision;
- the date and what it refers to;
- the strongest source type available. Look for the researcher writeup or vendor
  disclosure behind a news article and cite it first.

If the sources do not support a claim in the report, leave the claim out.

## 4. Draft the record (5 minutes)

```bash
cp incidents/_TEMPLATE.yaml incidents/<YYYY-kebab-slug>.yaml
```

The filename must equal `incident_id`. Map the form fields as follows:

| Form field | Record field(s) | Notes |
|---|---|---|
| Public source URL(s) | `sources[]` | `url` and `type` are required by the schema. Add `title`, `publisher` and `date_accessed` (today). `archive_url` is backfilled by CI. |
| What happened | `title`, `summary`, `trigger`, `root_cause`, `detection`, `recovery`, `prevention` | Rewrite in neutral, blameless language. `trigger` is a shape, never a payload. If a source does not say how it was detected or stopped, write that it is not publicly reported. |
| Product or system involved | `system.framework`, `system.models`, `system.tools`, `system.vendor` | Only what the sources name. |
| Realized incident / demonstrated hazard | `incident_type` | `incident` or `hazard`, decided from the sources. |
| Reported impact | `blast_radius`, `severity`, `severity_rationale` | Use `unknown` and `null` where the sources are silent. Set `estimated: true` for estimated amounts. |
| Date and what it refers to | `date`, `timeline[]` | `date` is when it occurred, or else when it was first publicly disclosed. Record the basis as a `timeline` entry, for example `{at: "2025-07-18", event: "Publicly disclosed by ..."}`. |
| Known CVE | `cve[]` | |
| Credit | `submitted_by` | Only if the reporter filled it in. |
| (none) | `primary_failure_class`, `failure_classes[]` | Classify the causal chain against [`TAXONOMY.md`](../TAXONOMY.md); the first entry equals `primary_failure_class`. |
| (none) | `confidence`, `status` | `confidence` from the sources: one source `reported`, independent sources `corroborated`, first-party or court `confirmed`. |

Leave `mappings` out: it is derived from `failure_classes` by `scripts/apply_mappings.py`.

## 5. Validate and open the pull request (1 minute)

```bash
uv run scripts/validate.py
uv run scripts/check_links.py incidents/<incident_id>.yaml
```

Do not commit `export/*.json`; it is regenerated after merge. Open the pull request with
`Closes #<issue>` in the body and complete the incident checklist in the template. The
pull request, not the issue, is where the record is reviewed and approved.

If the report needs more than fifteen minutes (conflicting sources, unclear scope,
classification questions), say so on the issue and leave it open. Speed matters less than
getting the record right.

## Spam and abuse

The form cannot rate-limit submissions. Use GitHub's moderation tools:

- **Spam or junk:** close as not planned, add `invalid`, and lock the conversation.
  Delete the issue if it carries anything harmful.
- **Abusive comments:** hide them, and lock the issue if it continues. Apply the
  [Code of Conduct](../CODE_OF_CONDUCT.md).
- **Repeat offenders:** block the account from the organisation, and report it to GitHub
  if appropriate.
- **A flood of reports:** set a temporary interaction limit (repository settings,
  Moderation options, Interaction limits) to restrict issues to prior contributors or
  collaborators until it passes.
- **Reports that read as targeted at a person or company,** rather than at an event, are
  declined. Records describe failures in systems; they are not a channel for grievances.

Declining is always done in a short, neutral comment that gives the reason, so the
reporter can come back with a public source if one exists.

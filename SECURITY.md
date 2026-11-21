# Security policy

agent-postmortems is a public corpus of AI-agent security incidents. Almost everything in it is *about* vulnerabilities, so this page is specific about what counts as a security issue **in this repository** and how to report one.

## Scope

Report these here:

- **The tooling and workflows.** Anything under `scripts/`, `schema/`, `tests/`, `.github/workflows/`, or the site build that could be abused: for example, a validator or export script that executes untrusted input from a record or a source archive, or a workflow that leaks a secret or accepts unreviewed content into `main`.
- **A record that carries a runnable exploit payload.** Records describe a failure *class* and a *trigger shape* in natural language. If an incident file, a source archive, or an export (`export/*.json`) contains a working payload, prompt-injection string, or exploit chain that could be copied and run, that is a defect in the corpus.
- **A record that carries personal data beyond its published sources.** Records never identify harmed individuals beyond what the cited public sources already published. Anything that goes further is a defect, whether or not the information is accurate.

Not in scope here:

- **The incidents themselves.** A vulnerability in a vendor's agent, framework, or model belongs with that vendor. This repository only documents what public sources already report.
- **Corrections to a record's facts.** Those follow [DISPUTES.md](./DISPUTES.md).
- **Dead links, schema errors, or taxonomy questions.** Those are ordinary bugs: open a normal issue.

## How to report

GitHub private vulnerability reporting is **not currently enabled** on this repository, so there is no "Report a vulnerability" button on the Security tab.

Until it is:

1. Open a [GitHub issue](https://github.com/swarmproof/agent-postmortems/issues/new) titled `Security contact request` and say only that you have a private report. **Do not put details, payloads, or the affected file in the issue.**
2. A maintainer will open a private [security advisory](https://github.com/swarmproof/agent-postmortems/security/advisories) draft and add you as a collaborator on it. Details go there.

If private vulnerability reporting is enabled later, the "Report a vulnerability" button on the [Security tab](https://github.com/swarmproof/agent-postmortems/security) becomes the preferred route and this page will be updated.

There is no security email address for this project. Any address claiming to be one is not ours.

## What we do not accept

- **Runnable exploit payloads in records or exports.** The curator standard and the export contract both require natural-language trigger shapes only. A pull request that adds a working payload will be asked to remove it, regardless of how well-sourced the incident is.
- **Proof-of-concept code against third-party systems.** Link to the public writeup; do not reproduce the exploit here.
- **Reports about vendors' systems addressed to us.** We cannot fix them and we will not relay them.

## Response

This project is maintained by volunteers. There is no SLA.

- A `Security contact request` issue is normally acknowledged within a week.
- A confirmed payload or personal-data defect in a record is treated as the highest priority the maintainers have and is fixed by editing the record, never by deleting it (see [ADR-0008](./adr/0008-never-delete-annotate-disputed.md)).
- Tooling fixes ship as ordinary pull requests once a fix is ready. If a workflow is the problem, it may be disabled first and fixed later.

We will credit reporters in the fixing pull request unless asked not to.

## Related

- [`DISPUTES.md`](./DISPUTES.md): correcting or contesting the facts of a record.
- [`CONTRIBUTING.md`](./CONTRIBUTING.md): reporting a new failure or writing a record.
- [`docs/METHODS.md`](./docs/METHODS.md): how records are sourced and reviewed, and the limits of the corpus.

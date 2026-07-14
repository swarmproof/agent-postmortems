# CURATION-PIPELINE — automated weekly incident discovery

*How new incidents get found, drafted, and reviewed — without compromising the sourcing
rigor and neutrality the corpus depends on.*

## The principle: automate the toil, keep the human gate

Unreviewed auto-publishing would undermine the corpus's credibility, which rests entirely
on sourcing rigor and neutrality. This pipeline keeps that credibility intact: it
automates **discovery, de-duplication, drafting, and validation**, but **nothing is
added to the corpus without a human approving a pull request**. The weekly job prepares
work; a maintainer decides what becomes an incident.

## Two layers

```
                          ┌────────────────────────── weekly (Mondays) ──────────────────────────┐
                          │                                                                        │
  discover_incidents.py ──┤  LAYER 1  weekly-discovery.yml    (always on, no secrets)              │
  (Google News RSS,       │    discover + dedup ──> open/update the "Candidate incidents" issue    │
   arXiv API, RSS feeds)  │                                                                        │
                          │  LAYER 2  weekly-autocurate.yml   (opt-in: needs ANTHROPIC_API_KEY)    │
                          │    discover + dedup ──> Claude drafts v1 YAML ──> validate ──> PR       │
                          └────────────────────────────────────────────────────────────────────────┘
                                                        │
                                       human reviews the issue / PR ──> merges
                                       (CI gates already green; editorial review is still required)
```

### Layer 1 — discovery digest (always on)

`.github/workflows/discover.yml` runs `scripts/discover_incidents.py` every Monday. The
script:

- harvests candidates from public, keyless feeds configured in
  `scripts/discovery_sources.yaml` (Google News RSS queries, the arXiv API, and any plain
  RSS/Atom feeds you list);
- **de-dupes** against the corpus: drops any candidate whose URL is already cited, and
  flags candidates whose title strongly overlaps an existing incident (conservative — a
  possible duplicate is shown, not hidden, so a human decides);
- **scores relevance** by how many agent-failure keywords each candidate matches, and
  ranks accordingly;
- posts the result as a checklist in a single reused GitHub issue labeled `candidates`.

This layer needs no secrets — it uses the default `GITHUB_TOKEN`. A maintainer picks a
candidate, drafts it from `incidents/_TEMPLATE.yaml`, and opens a PR.

Run it by hand anytime:

```bash
uv run scripts/discover_incidents.py                 # ranked summary
uv run scripts/discover_incidents.py --markdown       # issue-ready checklist
uv run scripts/discover_incidents.py --json out.json  # machine-readable
```

### Layer 2 — auto-draft PRs (opt-in)

`.github/workflows/autocurate.yml` goes one step further: it runs Claude Code headless
(instructions in `.github/curation-prompt.md`, standard in
`.claude/agents/incident-curator.md`) to research each new candidate, draft a full v1
record, validate it, and open a review PR labeled `needs-review`. It **never merges**.

It is dormant until you enable it:

1. Create an Anthropic API key.
2. Add it as a repository secret named `ANTHROPIC_API_KEY`
   (`Settings → Secrets and variables → Actions → New repository secret`).

Without the secret, the `guard` job logs a notice and skips — Layer 1 keeps working.
With it, the job drafts at most 5 incidents per run (quality over volume) and every draft
still passes the full CI gate suite before the PR opens. Automated validation is not
editorial review: a human verifies sources, tone, and incident-vs-hazard labels before
merging, per the PR checklist.

## Tuning discovery

Edit `scripts/discovery_sources.yaml` — no code change needed:

- `google_news_queries` — keep them agent-action-oriented (the engineering lens), not
  generic "AI news".
- `arxiv_queries` — for hazards / demonstrated PoCs.
- `rss_feeds` — primary-research blogs worth watching.
- `relevance_keywords` — the vocabulary that scores and filters candidates.

## What the pipeline deliberately does NOT do

- It does not merge, publish, or bypass review (ADR-0008: the human gate is the point).
- It does not scrape paywalled or private content, or fabricate detail when a candidate
  cannot be sourced — an unsourceable candidate is discarded, not guessed.
- It does not emit weaponized payloads; drafts carry natural-language trigger shapes only.

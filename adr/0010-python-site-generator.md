# ADR-0010 — Python static-site generator

**Status:** Accepted (supersedes ADR-0003)

## Decision
The site is built by `scripts/build_site.py`, a self-contained Python generator (stdlib + PyYAML, declared inline for `uv run`). It reads `incidents/*.yaml` and emits a static site to `site/`: an index with client-side filters and search, a permalink page per incident with a copyable BibTeX citation, an RSS feed (`feed.xml`), and a shared stylesheet. Navigation links are relative; absolute URLs for citations and the feed come from `SITE_BASE_URL`.

`.github/workflows/pages.yml` runs the generator on pushes to `main` that touch `incidents/**`, the script, or the workflow itself, uploads `site/` as a Pages artifact, and deploys it to GitHub Pages. `validate.yml` runs the same build on every pull request as a smoke test (G-SITE).

## Rationale
The second validation gate that motivated Astro is already provided by `scripts/validate.py` (G-SCHEMA), so a framework's content-collection validation would be redundant. The repo is Python-tooled end to end (validate, exports, discovery); a Python generator adds no Node toolchain, keeps the build fast and reproducible, and leaves the whole output inspectable in-repo.

## Alternatives rejected
- Astro (ADR-0003) — schema validation already covered by `validate.py`; adds a Node/npm toolchain. Still a reasonable choice if the site grows to need MDX content or richer interactivity.
- Hugo / Docusaurus — extra toolchains without a validation advantage.

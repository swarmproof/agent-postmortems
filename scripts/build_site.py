#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""Static-site generator for the agent-postmortems corpus (M5).

Reads incidents/*.yaml and emits a self-contained static site to site/:
  site/index.html          browsable index with client-side filters + search
  site/<incident_id>/index.html   per-incident permalink page + "Cite this"
  site/feed.xml            RSS feed of incidents, newest first
  site/style.css           shared styles (light/dark)

No backend, no build framework — plain HTML/CSS + a little vanilla JS for the
filters. Navigation links are relative, so the output works at any base path
(GitHub Pages project subpath, a custom domain, or file://). Absolute URLs
(citations, RSS) use SITE_BASE_URL.

Usage:
  uv run scripts/build_site.py
  SITE_BASE_URL=https://agent-postmortems.dev uv run scripts/build_site.py
"""
from __future__ import annotations

import datetime
import email.utils
import html
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
import urllib.parse
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
INCIDENTS_DIR = REPO / "incidents"
OUT = REPO / "site"
SITE_BASE = os.environ.get("SITE_BASE_URL", "https://swarmproof.github.io/agent-postmortems").rstrip("/")
REPO_URL = "https://github.com/swarmproof/agent-postmortems"
RAW_BASE = "https://raw.githubusercontent.com/swarmproof/agent-postmortems/main"

SEVERITY_ORDER = {"critical": 0, "high": 1, "moderate": 2, "low": 3, "informational": 4}
FRAMEWORKS = yaml.safe_load((REPO / "schema" / "framework-mappings.yaml").read_text())["frameworks"]
FRAMEWORK_LABELS = {"owasp_llm": "OWASP LLM", "owasp_agentic": "OWASP Agentic", "mitre_atlas": "MITRE ATLAS"}


def esc(x) -> str:
    return html.escape(str(x if x is not None else ""), quote=True)


def normalize(obj):
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: normalize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [normalize(v) for v in obj]
    return obj


def load_incidents() -> list[dict]:
    recs = []
    for p in sorted(INCIDENTS_DIR.glob("*.yaml")):
        if p.name.startswith("_"):
            continue
        recs.append(normalize(yaml.safe_load(p.read_text())))
    recs.sort(key=lambda r: r.get("date", ""), reverse=True)
    return recs


# --------------------------------------------------------------------------- page shell
def json_for_html(obj) -> str:
    """Compact JSON with <, > and & \\u-escaped, safe inside a <script> element or file."""
    s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return s.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def meta_description(text, limit: int = 200) -> str:
    """Collapse whitespace and cut at a word boundary so snippets stay readable."""
    t = " ".join(str(text or "").split())
    if len(t) <= limit:
        return t
    cut = t[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:—-")
    return cut + "…"


def page(title: str, body: str, css_href: str, description: str = "", *,
         canonical: str, og_type: str = "website", og_title: str | None = None,
         jsonld: dict | None = None) -> str:
    social_title = esc(og_title or title)
    ld = (f'\n<script type="application/ld+json">{json_for_html(jsonld)}</script>' if jsonld else "")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<link rel="canonical" href="{esc(canonical)}">
<meta property="og:type" content="{esc(og_type)}">
<meta property="og:site_name" content="agent-postmortems">
<meta property="og:title" content="{social_title}">
<meta property="og:description" content="{esc(description)}">
<meta property="og:url" content="{esc(canonical)}">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="{social_title}">
<meta name="twitter:description" content="{esc(description)}">{ld}
<link rel="stylesheet" href="{css_href}">
<link rel="alternate" type="application/rss+xml" title="agent-postmortems" href="{SITE_BASE}/feed.xml">
</head>
<body>
<a class="skip-link" href="#main">Skip to content</a>
<header class="site-head">
  <a class="brand" href="{'.' if css_href == 'style.css' else '..'}/">agent-postmortems</a>
  <span class="tagline">a structured database of AI-agent incidents and hazards</span>
</header>
<main id="main" tabindex="-1">
{body}
</main>
<footer class="site-foot">
  <nav aria-label="Project">
    <a href="{REPO_URL}">Source on GitHub</a>
    <a href="{REPO_URL}/blob/main/docs/METHODS.md">Methods</a>
    <a href="{REPO_URL}/blob/main/DISPUTES.md">Corrections &amp; disputes</a>
    <a href="{REPO_URL}/blob/main/CONTRIBUTING.md">Contribute</a>
    <a href="{REPO_URL}/blob/main/SECURITY.md">Security</a>
    <a href="{SITE_BASE}/feed.xml">RSS feed</a>
  </nav>
  <p>Data <a href="{REPO_URL}/blob/main/LICENSE-DATA">CC-BY-4.0</a> ·
  code <a href="{REPO_URL}/blob/main/LICENSE">Apache-2.0</a></p>
</footer>
</body>
</html>
"""


def badge(text: str, kind: str) -> str:
    return f'<span class="badge badge-{esc(kind)}">{esc(text)}</span>'


def chain_str(rec: dict) -> str:
    parts = []
    for fc in rec.get("failure_classes", []):
        c = fc.get("class", "")
        s = fc.get("subclass")
        parts.append(f"{c}/{s}" if s else c)
    return " → ".join(parts)


# --------------------------------------------------------------------------- search index
# The browsable list is rendered server-side; client search loads a compact,
# text-only index (search-index.json) and only hides/reorders those cards.
_SCHEMA_PROPS = json.loads((REPO / "schema" / "incident.schema.json").read_text())["properties"]
CONFIDENCE_VALUES = _SCHEMA_PROPS["confidence"]["enum"]
AUTONOMY_VALUES = _SCHEMA_PROPS["system"]["properties"]["autonomy_level"]["enum"]
TOOL_FACET_MIN = 2  # tools used by fewer records stay searchable but are not offered as a filter

# Body fields searched as free text (lowest ranking tier).
SEARCH_BODY_FIELDS = ("summary", "trigger", "root_cause", "contributing_factors",
                      "detection", "recovery", "prevention")


def norm_text(*parts) -> str:
    """Lower-case, NFKC-fold and collapse whitespace; mirrors norm() in search.js."""
    flat: list[str] = []
    for p in parts:
        if p is None:
            continue
        if isinstance(p, (list, tuple)):
            flat.extend(str(x) for x in p if x is not None)
        else:
            flat.append(str(p))
    return " ".join(unicodedata.normalize("NFKC", " ".join(flat)).lower().split())


EDGE_PUNCT = "()[]{}.,;:!?\"'`«»“”‘’"  # must match EDGE in search.js


def body_tokens(text: str) -> str:
    """Sorted unique words with edge punctuation stripped.

    Body text is matched term-by-term (no phrase matching), so word order and
    repeats carry no signal; dropping them roughly halves the index size.
    """
    return " ".join(sorted({w.strip(EDGE_PUNCT) for w in text.split()} - {""}))


def _spaced_variants(values) -> list[str]:
    """Add 'prompt injection' next to 'prompt-injection' so either spelling matches."""
    out = []
    for v in values:
        if not v:
            continue
        v = str(v)
        out.append(v)
        if re.search(r"[-_/]", v):
            out.append(re.sub(r"[-_/]+", " ", v))
    return out


def search_record(rec: dict) -> dict:
    """One compact index entry: three ranked text tiers plus exact facet values."""
    sysm = rec.get("system") or {}
    fcs = rec.get("failure_classes") or []
    mappings = [i for ids in (rec.get("mappings") or {}).values() for i in (ids or [])]
    keys = [
        rec["incident_id"], rec.get("primary_failure_class"), rec.get("attack_vector"),
        *[fc.get("class") for fc in fcs], *[fc.get("subclass") for fc in fcs],
        *(rec.get("tags") or []), *(rec.get("cve") or []), *(rec.get("cwe") or []), *mappings,
        sysm.get("vendor"), sysm.get("framework"),
        *(sysm.get("models") or []), *(sysm.get("tools") or []),
    ]
    return {
        "id": rec["incident_id"],
        "t": norm_text(rec.get("title", "")),
        "k": norm_text(_spaced_variants(keys)),
        "b": body_tokens(norm_text(*(rec.get(f) for f in SEARCH_BODY_FIELDS))),
        "sev": rec.get("severity") or "",
        "type": rec.get("incident_type") or "",
        "d": rec.get("date") or "",
        "year": (rec.get("date") or "")[:4],
        "conf": rec.get("confidence") or "",
        "auto": sysm.get("autonomy_level") or "",
        "vendor": sysm.get("vendor") or "",
        "classes": sorted({fc.get("class") for fc in fcs if fc.get("class")}),
        "tools": sorted({str(t) for t in (sysm.get("tools") or [])}),
    }


def build_search_index(recs: list[dict]) -> dict:
    """Index records in display order (the same order as the static card list)."""
    return {"version": 1, "records": [search_record(r) for r in recs]}


def search_index_json(recs: list[dict]) -> str:
    # <, > and & are \u-escaped so the payload stays inert even if ever inlined in HTML.
    s = json.dumps(build_search_index(recs), ensure_ascii=False, separators=(",", ":"))
    return s.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def facet_options(recs: list[dict]) -> dict[str, list[str]]:
    """Filter values offered in the UI, keyed by URL parameter name."""
    tool_counts: dict[str, int] = {}
    for r in recs:
        for t in {str(t) for t in ((r.get("system") or {}).get("tools") or [])}:
            tool_counts[t] = tool_counts.get(t, 0) + 1
    present = lambda f: {f(r) for r in recs} - {"", None}  # noqa: E731
    return {
        "class": sorted({fc.get("class") for r in recs for fc in r.get("failure_classes", [])} - {None}),
        "severity": [s for s in SEVERITY_ORDER if s in present(lambda r: r.get("severity"))],
        "type": [t for t in ("incident", "hazard") if t in present(lambda r: r.get("incident_type"))],
        "year": sorted(present(lambda r: (r.get("date") or "")[:4]), reverse=True),
        "confidence": [c for c in CONFIDENCE_VALUES if c in present(lambda r: r.get("confidence"))],
        "autonomy": [a for a in AUTONOMY_VALUES
                     if a in present(lambda r: (r.get("system") or {}).get("autonomy_level"))],
        "vendor": sorted(present(lambda r: (r.get("system") or {}).get("vendor")), key=str.casefold),
        "tool": sorted((t for t, n in tool_counts.items() if n >= TOOL_FACET_MIN), key=str.casefold),
    }


# --------------------------------------------------------------------------- index
# (URL parameter, visible label, "all" option text) for each filter, in display order.
FILTERS = [
    ("class", "Failure class", "All classes"),
    ("severity", "Severity", "All severities"),
    ("type", "Type", "Incident &amp; hazard"),
    ("year", "Year", "All years"),
    ("confidence", "Confidence", "Any confidence"),
    ("autonomy", "Autonomy", "Any autonomy"),
    ("vendor", "Vendor", "All vendors"),
    ("tool", "Tool", "All tools"),
]


# Sort orders offered. Only neutral orders: no ranking by severity or "danger".
SORTS = [
    ("", "Best match, else newest"),
    ("newest", "Newest first (date occurred or disclosed)"),
    ("oldest", "Oldest first (date occurred or disclosed)"),
    ("title", "Title, A to Z"),
]


def render_filters(recs: list[dict]) -> str:
    options = facet_options(recs)
    fields = []
    for param, label, all_text in FILTERS:
        opts = "".join(f'<option value="{esc(v)}">{esc(v)}</option>' for v in options[param])
        fields.append(f'<div class="f"><label for="f-{param}">{label}</label>'
                      f'<select id="f-{param}" name="{param}"><option value="">{all_text}</option>{opts}</select></div>')
    sorts = "".join(f'<option value="{v}">{label}</option>' for v, label in SORTS)
    return f"""<form class="filters" id="filters" role="search" aria-label="Search and filter incidents" hidden>
  <div class="f f-q"><label for="q">Search</label>
    <input type="search" id="q" name="q" autocomplete="off" spellcheck="false" aria-describedby="q-hint"
      placeholder="Title, cause, prevention, vendor, tool, CVE, tag…"></div>
  <div class="f f-sort"><label for="sort">Sort</label>
    <select id="sort" name="sort" aria-describedby="sort-hint">{sorts}</select></div>
  <details class="facets" id="facets">
    <summary>Filters <span id="facet-count"></span></summary>
    <div class="facet-grid">
      {''.join(fields)}
      <div class="f f-actions"><button type="button" class="clear">Clear search and filters</button></div>
    </div>
    <p id="q-hint" class="hint">Every word must match. Title matches rank first, then tags, IDs and system names,
    then body text. Filters combine with each other and with the search. Press <kbd>/</kbd> to search.</p>
    <p id="sort-hint" class="hint">Dates are when an incident occurred or was first publicly disclosed.</p>
  </details>
</form>
<p id="count" class="count" role="status" aria-live="polite"></p>
<div id="empty" class="empty" hidden>
  <p>No records match this search and these filters.</p>
  <button type="button" class="clear">Clear search and filters</button>
</div>"""


def card_date_label(rec: dict) -> str:
    """What the record's date may mean: the legacy date is occurrence (or, for a hazard,
    first demonstration) or first public disclosure, without saying which."""
    return "Demonstrated or disclosed" if rec.get("incident_type") == "hazard" else "Occurred or disclosed"


def render_index(recs: list[dict]) -> str:
    rows = []
    for r in recs:
        rid = r["incident_id"]
        rows.append(f"""<a class="card" href="{esc(rid)}/" data-id="{esc(rid)}">
  <div class="card-head">
    <span class="card-date">{esc(card_date_label(r))}: <time datetime="{esc(r.get('date',''))}">{esc(r.get('date',''))}</time></span>
    {badge(r.get('incident_type','?'), 'type-' + esc(r.get('incident_type','')))}
    {badge(r.get('severity','?'), 'sev-' + esc(r.get('severity','')))}
  </div>
  <h2 class="card-title">{esc(r.get('title', rid))}</h2>
  <div class="card-chain">{esc(chain_str(r))}</div>
</a>""")

    n_incident = sum(1 for r in recs if r.get("incident_type") == "incident")
    n_hazard = sum(1 for r in recs if r.get("incident_type") == "hazard")
    body = f"""
<section class="intro">
  <h1>AI-agent incidents and hazards</h1>
  <p>{len(recs)} sourced records: {n_incident} realized incidents and {n_hazard} demonstrated hazards
  of AI agents — prompt injection, tool misuse, data exfiltration, sandbox escapes, cost blowups,
  and more. Every record follows
  <a href="https://github.com/swarmproof/agent-postmortems/blob/main/SCHEMA.md">one schema</a> and
  cites public sources. <a href="{SITE_BASE}/feed.xml">RSS</a>.</p>
  <p class="limits">Records come from public reporting, which is not a representative prevalence
  sample; counts do not measure how often agents fail and are not a vendor safety ranking.</p>
</section>
{render_filters(recs)}
<section class="cards" id="cards" aria-label="Records" data-index="search-index.json">
{''.join(rows)}
</section>
<script src="search.js" defer></script>
"""
    description = "A structured, sourced database of AI-agent incidents and demonstrated hazards."
    return page("agent-postmortems — AI-agent failure database", body, "style.css", description,
                canonical=f"{SITE_BASE}/", jsonld=dataset_jsonld(description))


def dataset_jsonld(description: str) -> dict:
    """schema.org Dataset limited to facts the repository itself establishes."""
    return {
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": "agent-postmortems",
        "description": description,
        "url": f"{SITE_BASE}/",
        "license": "https://creativecommons.org/licenses/by/4.0/",
        "isAccessibleForFree": True,
        "distribution": [{
            "@type": "DataDownload",
            "encodingFormat": "application/json",
            "contentUrl": f"{RAW_BASE}/export/incidents.json",
        }],
    }


# --------------------------------------------------------------------------- incident page
def field(label: str, value: str) -> str:
    return f'<div class="kv"><dt>{esc(label)}</dt><dd>{value}</dd></div>' if value else ""


def prose(label: str, text) -> str:
    return f'<section class="prose"><h2>{esc(label)}</h2><p>{esc(text)}</p></section>' if text else ""


def safe_url(url) -> str:
    """Return the URL only if it is an absolute http(s) link, else ''.

    Source URLs are contributor data; `format: uri` alone admits schemes such as
    javascript: or data:, which must never become a clickable href.
    """
    u = str(url or "").strip()
    return u if urllib.parse.urlsplit(u).scheme.lower() in ("http", "https") else ""


def render_sources(rec: dict) -> str:
    items = []
    for s in rec.get("sources", []):
        url = safe_url(s.get("url"))
        title = s.get("title") or s.get("url") or ""
        meta = " · ".join(filter(None, [s.get("publisher"), s.get("type")]))
        archive = safe_url(s.get("archive_url"))
        arch = f' · <a href="{esc(archive)}">archived</a>' if archive else ""
        link = f'<a href="{esc(url)}">{esc(title)}</a>' if url else esc(title)
        items.append(f'<li>{link}<span class="src-meta">{esc(meta)}{arch}</span></li>')
    return f'<section class="prose"><h2>Sources</h2><ul class="sources">{"".join(items)}</ul></section>' if items else ""


def render_blast(rec: dict) -> str:
    b = rec.get("blast_radius") or {}
    rows = []
    cost = b.get("cost") or {}
    if cost.get("amount_usd") is not None:
        amt = f"${cost['amount_usd']:,.0f}" + (" (est.)" if cost.get("estimated") else "")
        rows.append(field("Cost", esc(amt)))
    data = b.get("data") or {}
    if data.get("description") or data.get("classification"):
        d = esc(data.get("description", ""))
        cls = f' <span class="tag">{esc(data.get("classification"))}</span>' if data.get("classification") else ""
        rows.append(field("Data", d + cls))
    uh = b.get("user_harm") or {}
    if uh.get("description") or uh.get("categories"):
        cats = " ".join(f'<span class="tag">{esc(c)}</span>' for c in uh.get("categories", []))
        rows.append(field("User harm", esc(uh.get("description", "")) + " " + cats))
    if b.get("scope"):
        rows.append(field("Scope", esc(b["scope"])))
    if b.get("reversibility"):
        rows.append(field("Reversibility", esc(b["reversibility"])))
    return f'<section class="prose"><h2>Blast radius</h2><dl class="kvs">{"".join(rows)}</dl></section>' if rows else ""


def bibtex(rec: dict, url: str) -> str:
    year = (rec.get("date") or "")[:4]
    return (f"@misc{{{rec['incident_id']},\n"
            f"  title = {{{rec.get('title','')}}},\n"
            f"  year = {{{year}}},\n"
            f"  howpublished = {{agent-postmortems}},\n"
            f"  url = {{{url}}}\n}}")


TYPE_NOTES = {
    "incident": ("Realized incident", "the cited sources report that harm or an unintended agent action occurred."),
    "hazard": ("Demonstrated hazard", "a proof of concept, disclosed vulnerability or near-miss, "
               "recorded without evidence that harm occurred."),
}


def type_note(incident_type) -> str:
    if incident_type not in TYPE_NOTES:
        return ""
    label, text = TYPE_NOTES[incident_type]
    return (f'<p class="type-note type-note-{esc(incident_type)}">'
            f'<strong>{esc(label)}</strong>: {esc(text)}</p>')


def render_incident(rec: dict, all_ids: set[str]) -> str:
    rid = rec["incident_id"]
    url = f"{SITE_BASE}/{rid}/"
    sys = rec.get("system") or {}
    sys_rows = "".join([
        field("Framework", esc(sys.get("framework"))),
        field("Models", esc(", ".join(sys.get("models", [])))),
        field("Tools", esc(", ".join(sys.get("tools", [])))),
        field("Vendor", esc(sys.get("vendor"))),
        field("Autonomy", esc(sys.get("autonomy_level"))),
    ])
    caus = rec.get("causation") or {}
    class_rows = "".join([
        field("Primary class", esc(rec.get("primary_failure_class"))),
        field("Chain", esc(chain_str(rec))),
        field("Attack vector", esc(rec.get("attack_vector"))),
        field("Causation", esc(" · ".join(f"{k}: {v}" for k, v in caus.items())) if caus else ""),
    ])
    mapping_rows = ""
    for key, label in FRAMEWORK_LABELS.items():
        ids = (rec.get("mappings") or {}).get(key)
        if not ids:
            continue
        names = FRAMEWORKS[key]["ids"]
        chips = " ".join(f'<span class="tag" title="{esc(names.get(i, ""))}">{esc(i)}</span>' for i in ids)
        lbl = f'<a href="{esc(FRAMEWORKS[key]["url"])}">{esc(label)}</a>'
        mapping_rows += f'<div class="kv"><dt>{lbl}</dt><dd>{chips}</dd></div>'
    xref = "".join([
        field("CVE", " ".join(f'<a href="https://nvd.nist.gov/vuln/detail/{esc(c)}">{esc(c)}</a>' for c in rec.get("cve", []))),
        field("CWE", esc(", ".join(rec.get("cwe", [])))),
        mapping_rows,
        field("Related", " ".join(
            f'<a href="../{esc(r)}/">{esc(r)}</a>' if r in all_ids else esc(r)
            for r in rec.get("related_incidents", []))),
        field("Tags", " ".join(f'<span class="tag">{esc(t)}</span>' for t in rec.get("tags", []))),
    ])
    factors = ""
    if rec.get("contributing_factors"):
        lis = "".join(f"<li>{esc(x)}</li>" for x in rec["contributing_factors"])
        factors = f'<section class="prose"><h2>Contributing factors</h2><ul>{lis}</ul></section>'
    timeline = ""
    if rec.get("timeline"):
        lis = "".join(f'<li><span class="tl-at">{esc(e.get("at",""))}</span> {esc(e.get("event",""))}</li>'
                      for e in rec["timeline"])
        timeline = f'<section class="prose"><h2>Timeline</h2><ul class="timeline">{lis}</ul></section>'

    body = f"""
<article class="incident">
  <p class="crumb"><a href="../">← all records</a></p>
  <div class="badges">
    {badge(rec.get('incident_type','?'), 'type-' + esc(rec.get('incident_type','')))}
    {badge(rec.get('severity','?'), 'sev-' + esc(rec.get('severity','')))}
    {badge('confidence: ' + esc(rec.get('confidence','?')), 'neutral') if rec.get('confidence') else ''}
    {badge('status: ' + esc(rec.get('status','?')), 'neutral') if rec.get('status') else ''}
  </div>
  {type_note(rec.get('incident_type'))}
  <h1>{esc(rec.get('title', rid))}</h1>
  <p class="sub"><code>{esc(rid)}</code> · {esc(rec.get('date',''))}</p>
  {f'<p class="summary">{esc(rec.get("summary"))}</p>' if rec.get('summary') else ''}

  <section class="prose"><h2>System</h2><dl class="kvs">{sys_rows}</dl></section>
  <section class="prose"><h2>Classification</h2><dl class="kvs">{class_rows}</dl></section>
  {prose('Trigger', rec.get('trigger'))}
  {prose('Root cause', rec.get('root_cause'))}
  {factors}
  {prose('Detection', rec.get('detection'))}
  {prose('Recovery', rec.get('recovery'))}
  {prose('Prevention', rec.get('prevention'))}
  {render_blast(rec)}
  {timeline}
  <section class="prose"><h2>References</h2><dl class="kvs">{xref}</dl></section>
  {render_sources(rec)}

  <section class="cite">
    <h2>Cite this incident</h2>
    <p class="permalink">Permalink: <a href="{url}">{esc(url)}</a></p>
    <pre id="bib">{esc(bibtex(rec, url))}</pre>
    <button onclick="navigator.clipboard.writeText(document.getElementById('bib').textContent)">Copy BibTeX</button>
  </section>
</article>
"""
    return page(f"{rec.get('title', rid)} — agent-postmortems", body, "../style.css",
                meta_description(rec.get("summary") or rec.get("trigger")),
                canonical=url, og_type="article", og_title=rec.get("title", rid))


# --------------------------------------------------------------------------- feed
FEED_LIMIT = 50
# Characters XML 1.0 forbids even when escaped (C0 controls except tab/LF/CR).
_XML_ILLEGAL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]")


def xml_text(x) -> str:
    """Escape a value for XML character data or attributes, dropping illegal chars."""
    return esc(_XML_ILLEGAL.sub("", str(x if x is not None else "")))


def rfc822(dt: datetime.datetime) -> str:
    """RFC 822 / RSS 2.0 date in GMT. Naive datetimes are rejected, not guessed."""
    if dt.tzinfo is None:
        raise ValueError("feed datetimes must be timezone-aware")
    return email.utils.format_datetime(dt.astimezone(datetime.timezone.utc), usegmt=True)


def build_time() -> datetime.datetime:
    """Build time for lastBuildDate: SOURCE_DATE_EPOCH when set, else now (UTC)."""
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch:
        return datetime.datetime.fromtimestamp(int(epoch), tz=datetime.timezone.utc)
    return datetime.datetime.now(datetime.timezone.utc)


def git_first_added(repo: Path = REPO) -> dict[str, datetime.datetime]:
    """Map incident_id -> time its file first landed on the mainline.

    Walks first-parent history and diffs each commit (merges included) against its
    first parent, so a file added on a pull-request branch is dated by the merge
    that published it, not by the earlier branch commit. Renames are not followed:
    an id is published under its current filename. Returns {} when history is not
    usable: no git, not a work tree, or a shallow clone (the shallow boundary
    commit would appear to add every file at once).
    """
    def git(*args: str) -> str:
        return subprocess.run(["git", "-C", str(repo), *args], check=True,
                              capture_output=True, text=True).stdout
    try:
        if git("rev-parse", "--is-shallow-repository").strip() != "false":
            print("feed: shallow clone, falling back to in-record dates", file=sys.stderr)
            return {}
        log = git("log", "--first-parent", "--diff-merges=first-parent", "--no-renames",
                  "--diff-filter=A", "--name-only", "--format=@%ct", "--", "incidents/")
    except (OSError, subprocess.CalledProcessError):
        return {}
    added: dict[str, datetime.datetime] = {}
    ts = None
    for line in log.splitlines():
        if line.startswith("@"):
            ts = datetime.datetime.fromtimestamp(int(line[1:]), tz=datetime.timezone.utc)
        elif line.endswith(".yaml") and ts is not None:
            rid = Path(line).stem
            # log is newest-first; keep overwriting so the earliest add wins
            added[rid] = ts
    return added


def first_accessed(rec: dict) -> datetime.datetime | None:
    """Earliest sources[].date_accessed at 00:00 UTC (set at curation, never rewritten)."""
    days = sorted(s["date_accessed"] for s in rec.get("sources", []) if s.get("date_accessed"))
    if not days:
        return None
    d = datetime.date.fromisoformat(days[0])
    return datetime.datetime(d.year, d.month, d.day, tzinfo=datetime.timezone.utc)


def render_feed(recs: list[dict], built: datetime.datetime | None = None,
                published: dict[str, datetime.datetime] | None = None) -> str:
    """RSS 2.0 feed of the most recently published records.

    pubDate is when a record was first published in this registry, NOT when the
    incident happened (that is the record's `date`). Source, in order:
      1. the commit that first added incidents/<id>.yaml on the mainline
         (git_first_added; needs full history, hence fetch-depth: 0 in CI);
      2. the record's earliest sources[].date_accessed, for builds without usable
         history or for a file not yet committed;
      3. the build time.
    Items are the FEED_LIMIT records with the latest incident `date`, in that
    order (ties keep filename order, as load_incidents returns them). Selection
    and order are unchanged from earlier feeds; only the dates are publication
    times, so pubDate is not monotonic across items.

    lastBuildDate is the build time (SOURCE_DATE_EPOCH when set).

    <guid> is the incident permalink, unchanged from earlier builds so existing
    subscribers are not re-notified; it depends only on SITE_BASE and the id.
    """
    built = built or build_time()
    if published is None:
        published = git_first_added()

    def pub(r: dict) -> datetime.datetime:
        return published.get(r["incident_id"]) or first_accessed(r) or built

    # Stable sort: re-sorting load_incidents() output is a no-op.
    ordered = sorted(recs, key=lambda r: r.get("date") or "", reverse=True)
    items = []
    for r in ordered[:FEED_LIMIT]:
        link = f"{SITE_BASE}/{r['incident_id']}/"
        items.append(f"""  <item>
    <title>{xml_text(r.get('title', r['incident_id']))}</title>
    <link>{xml_text(link)}</link>
    <guid isPermaLink="true">{xml_text(link)}</guid>
    <pubDate>{rfc822(pub(r))}</pubDate>
    <description>{xml_text(r.get('summary',''))}</description>
  </item>""")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
  <title>agent-postmortems</title>
  <link>{xml_text(SITE_BASE)}/</link>
  <description>A structured, sourced database of AI-agent incidents and demonstrated hazards.</description>
  <lastBuildDate>{rfc822(built)}</lastBuildDate>
{chr(10).join(items)}
</channel>
</rss>
"""


# --------------------------------------------------------------------------- crawl files
def render_sitemap(recs: list[dict]) -> str:
    """Index plus every permalink. lastmod only where the record states last_updated."""
    urls = [f"  <url><loc>{esc(SITE_BASE)}/</loc></url>"]
    for r in sorted(recs, key=lambda r: r["incident_id"]):
        lastmod = f"<lastmod>{esc(r['last_updated'])}</lastmod>" if r.get("last_updated") else ""
        urls.append(f"  <url><loc>{esc(SITE_BASE)}/{esc(r['incident_id'])}/</loc>{lastmod}</url>")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "\n".join(urls) + "\n</urlset>\n")


def render_robots() -> str:
    return f"User-agent: *\nAllow: /\n\nSitemap: {SITE_BASE}/sitemap.xml\n"


CSS = """
:root { --bg:#fbfbfa; --fg:#1a1a1a; --muted:#666; --card:#fff; --line:#e5e5e3; --accent:#3b5bdb; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#15161a; --fg:#e8e8ea; --muted:#9a9aa2; --card:#1e1f25; --line:#2c2d34; --accent:#8aa0ff; }
}
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--fg); font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }
a { color:var(--accent); text-decoration:none; } a:hover { text-decoration:underline; }
main { max-width:820px; margin:0 auto; padding:0 20px 64px; }
.site-head { max-width:820px; margin:0 auto; padding:20px; display:flex; gap:12px; align-items:baseline; flex-wrap:wrap; }
.brand { font-weight:700; font-size:18px; color:var(--fg); }
.tagline { color:var(--muted); font-size:14px; }
.site-foot { max-width:820px; margin:0 auto; padding:24px 20px; border-top:1px solid var(--line); color:var(--muted); font-size:13px; }
.site-foot nav { display:flex; flex-wrap:wrap; gap:6px 16px; margin-bottom:8px; }
.site-foot nav a { padding:4px 0; }
.site-foot p { margin:0; }
h1 { font-size:28px; line-height:1.25; margin:8px 0 12px; }
h2 { font-size:15px; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); margin:28px 0 8px; }
.intro p { color:var(--fg); }
[hidden] { display:none !important; }
.skip-link { position:absolute; left:8px; top:-48px; z-index:10; padding:8px 12px; border-radius:8px; background:var(--card); color:var(--accent); border:1px solid var(--accent); }
.skip-link:focus { top:8px; }
main:focus { outline:none; }
.filters { display:grid; grid-template-columns:1fr; gap:8px 10px; margin:20px 0 8px; }
@media (min-width: 720px) { .filters { grid-template-columns:1fr 280px; } }
.facets { grid-column:1 / -1; border:1px solid var(--line); border-radius:8px; background:var(--card); }
.facets > summary { cursor:pointer; padding:8px 10px; font-size:14px; font-weight:600; }
.facets[open] > summary { border-bottom:1px solid var(--line); }
.facet-grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(150px, 1fr)); gap:8px 10px; padding:10px; }
.facets .hint { padding:0 10px 8px; }
#facet-count { color:var(--muted); font-weight:400; }
.filters .f { display:flex; flex-direction:column; gap:2px; min-width:0; }
.filters label { font-size:12px; font-weight:600; color:var(--muted); }
.filters input, .filters select, .filters button, .empty button { width:100%; min-width:0; padding:7px 9px; border:1px solid var(--line); border-radius:8px; background:var(--card); color:var(--fg); font:inherit; font-size:14px; }
.filters button, .empty button { cursor:pointer; width:auto; }
.filters .f-q input { font-size:16px; }
.filters .f-actions { justify-content:flex-end; }
.hint { margin:0; color:var(--muted); font-size:12px; }
kbd { font:12px ui-monospace,SFMono-Regular,Menlo,monospace; padding:0 4px; border:1px solid var(--line); border-radius:4px; }
.count { color:var(--muted); font-size:13px; margin:0 0 10px; min-height:1.6em; }
.empty { padding:20px 16px; border:1px dashed var(--line); border-radius:12px; text-align:center; }
.empty p { margin:0 0 10px; }
a:focus-visible, input:focus-visible, select:focus-visible, button:focus-visible, summary:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
.card:focus-visible { border-color:var(--accent); }
.cards { display:flex; flex-direction:column; gap:10px; }
.card { display:block; padding:14px 16px; border:1px solid var(--line); border-radius:12px; background:var(--card); color:var(--fg); }
.card:hover { border-color:var(--accent); text-decoration:none; }
.card-head { display:flex; flex-wrap:wrap; gap:6px 8px; align-items:center; margin-bottom:6px; }
.card-date { color:var(--muted); font-size:13px; font-variant-numeric:tabular-nums; }
.card-title { font-weight:600; font-size:16px; line-height:1.4; margin:0; color:var(--fg); text-transform:none; letter-spacing:normal; }
.card-chain { color:var(--muted); font-size:13px; margin-top:4px; }
.badges { display:flex; gap:6px; flex-wrap:wrap; margin:4px 0 8px; }
.badge { font-size:12px; font-weight:600; padding:2px 8px; border-radius:999px; border:1px solid var(--line); white-space:nowrap; }
.badge-sev-critical { background:#fdecec; color:#b42318; border-color:#f6c9c4; }
.badge-sev-high { background:#fdf1e7; color:#b54708; border-color:#f6d5b3; }
.badge-sev-moderate { background:#fffaeb; color:#7a5d00; border-color:#f5e3a1; }
.badge-sev-low { background:#ecfdf3; color:#137a3e; border-color:#bbe9cc; }
.badge-sev-informational { background:#f2f4f7; color:#475467; border-color:#e0e4ea; }
.badge-type-incident { background:#eef2ff; color:#3538cd; border-color:#cfd6ff; }
.badge-type-hazard { background:#f2f4f7; color:#475467; border-color:#e0e4ea; }
.badge-neutral { color:var(--muted); }
.type-note { font-size:14px; color:var(--muted); margin:0 0 8px; } .limits { color:var(--muted); font-size:14px; }
@media (prefers-color-scheme: dark) { /* dark-badges: text colours keep >= 4.5:1 on --bg and --card */
  .badge { background:transparent !important; }
  .badge-sev-critical { color:#ff8b80; }
  .badge-sev-high { color:#ffa46b; }
  .badge-sev-moderate { color:#e6c35c; }
  .badge-sev-low { color:#6fd49a; }
  .badge-sev-informational { color:#b6bfcc; }
  .badge-type-incident { color:#a6b4ff; }
  .badge-type-hazard { color:#b6bfcc; }
}
.crumb { margin:0 0 12px; font-size:14px; }
.sub { color:var(--muted); margin:0 0 16px; }
.sub code { background:var(--card); padding:2px 6px; border-radius:6px; border:1px solid var(--line); }
.summary { font-size:18px; line-height:1.5; }
.prose p { margin:0 0 8px; }
.kvs { margin:0; } .kv { display:flex; gap:12px; padding:5px 0; border-bottom:1px solid var(--line); }
.kv dt { flex:0 0 130px; color:var(--muted); font-size:14px; } .kv dd { margin:0; flex:1; }
.tag { display:inline-block; font-size:12px; padding:1px 7px; border-radius:6px; background:var(--card); border:1px solid var(--line); color:var(--muted); margin:1px 2px; }
.sources { margin:0; padding-left:18px; } .sources li { margin:6px 0; }
.src-meta { color:var(--muted); font-size:13px; margin-left:6px; }
.timeline { list-style:none; padding:0; } .timeline li { padding:4px 0; border-bottom:1px solid var(--line); }
.tl-at { color:var(--muted); font-variant-numeric:tabular-nums; margin-right:8px; }
.cite { margin-top:36px; padding:16px; border:1px solid var(--line); border-radius:12px; background:var(--card); }
.cite pre { overflow-x:auto; background:var(--bg); padding:12px; border-radius:8px; border:1px solid var(--line); font-size:13px; }
.cite button { padding:7px 12px; border:1px solid var(--line); border-radius:8px; background:var(--bg); color:var(--fg); cursor:pointer; }
"""


# Client search. It never builds HTML from data: cards are rendered server-side
# (escaped) and this script only hides, shows and reorders them by id. The pure
# functions are exported for tests (node) via module.exports.
SEARCH_JS = r"""(function () {
'use strict';
var EDGE = '()[]{}.,;:!?"\'`\u00ab\u00bb\u201c\u201d\u2018\u2019'; // must match EDGE_PUNCT in build_site.py
// URL parameter -> index field. Array fields match by membership; all filters AND.
var FACETS = { 'class': 'classes', severity: 'sev', type: 'type', year: 'year',
               confidence: 'conf', autonomy: 'auto', vendor: 'vendor', tool: 'tools' };

function norm(s) {
  return String(s == null ? '' : s).normalize('NFKC').toLowerCase().split(/\s+/).filter(Boolean).join(' ');
}
function stripEdge(w) {
  var a = 0, b = w.length;
  while (a < b && EDGE.indexOf(w[a]) >= 0) a++;
  while (b > a && EDGE.indexOf(w[b - 1]) >= 0) b--;
  return w.slice(a, b);
}
function terms(q) {
  var out = [];
  norm(q).split(' ').forEach(function (w) { w = stripEdge(w); if (w && out.indexOf(w) < 0) out.push(w); });
  return out;
}
function facetOk(rec, filters) {
  for (var p in FACETS) {
    var want = filters[p];
    if (!want) continue;
    var have = rec[FACETS[p]];
    if (Array.isArray(have) ? have.indexOf(want) < 0 : have !== want) return false;
  }
  return true;
}
// Every term must match somewhere; each term scores by its best tier: title > keys > body.
function score(rec, ts) {
  var s = 0;
  for (var i = 0; i < ts.length; i++) {
    var t = ts[i];
    if (rec.t.indexOf(t) >= 0) s += 100;
    else if (rec.k.indexOf(t) >= 0) s += 10;
    else if (rec.b.indexOf(t) >= 0) s += 1;
    else return -1;
  }
  if (ts.length > 1) {
    var phrase = ts.join(' ');
    if (rec.t.indexOf(phrase) >= 0) s += 50; else if (rec.k.indexOf(phrase) >= 0) s += 5;
  }
  return s;
}
// Returns matching ids: ranked when there is a query, otherwise in index (display) order.
function search(records, query, filters) {
  var ts = terms(query), hits = [];
  records.forEach(function (rec, i) {
    if (!facetOk(rec, filters || {})) return;
    var s = score(rec, ts);
    if (s >= 0) hits.push({ id: rec.id, s: s, i: i });
  });
  hits.sort(function (a, b) { return b.s - a.s || a.i - b.i; });
  return hits.map(function (h) { return h.id; });
}

// Neutral orders only (never by severity). Ties fall back to incident id.
var SORTS = ['newest', 'oldest', 'title'];
function sortIds(records, ids, sort) {
  if (SORTS.indexOf(sort) < 0) return ids;
  var by = {};
  records.forEach(function (r) { by[r.id] = r; });
  function c(x, y) { return x < y ? -1 : x > y ? 1 : 0; }
  function alpha(t) { return t.replace(/^[^\p{L}\p{N}]+/u, ''); }  // ignore leading quotes
  var key = { newest: function (a, b) { return c(b.d, a.d); },
              oldest: function (a, b) { return c(a.d, b.d); },
              title: function (a, b) { return c(alpha(a.t), alpha(b.t)); } }[sort];
  return ids.slice().sort(function (x, y) { return key(by[x], by[y]) || c(x, y); });
}

var api = { norm: norm, terms: terms, search: search, sortIds: sortIds, FACETS: FACETS, SORTS: SORTS };
if (typeof module !== 'undefined' && module.exports) module.exports = api;
if (typeof document === 'undefined') return;

var list = document.getElementById('cards'), form = document.getElementById('filters');
if (!list || !form) return;
var count = document.getElementById('count'), empty = document.getElementById('empty');
var q = form.elements.namedItem('q'), sortSel = form.elements.namedItem('sort');
var facets = document.getElementById('facets'), facetCount = document.getElementById('facet-count');
var cards = new Map(), defaultOrder = [];
list.querySelectorAll('.card[data-id]').forEach(function (el) { cards.set(el.dataset.id, el); defaultOrder.push(el.dataset.id); });
var records = null;

function state() {
  var f = {};
  for (var p in FACETS) f[p] = form.elements.namedItem(p).value;
  return { q: q.value, f: f, sort: sortSel.value };
}
function syncUrl(st) {
  var sp = new URLSearchParams();
  if (norm(st.q)) sp.set('q', norm(st.q));
  for (var p in FACETS) if (st.f[p]) sp.set(p, st.f[p]);
  if (st.sort) sp.set('sort', st.sort);
  var qs = sp.toString();
  history.replaceState(null, '', (qs ? '?' + qs : location.pathname) + location.hash);
}
function render() {
  var st = state(), ids = sortIds(records, search(records, st.q, st.f), st.sort), shown = new Set(ids);
  var nFacets = Object.keys(st.f).filter(function (p) { return st.f[p]; }).length;
  var active = !!norm(st.q) || nFacets > 0;
  var order = ids.concat(defaultOrder.filter(function (id) { return !shown.has(id); }));
  var frag = document.createDocumentFragment();
  order.forEach(function (id) { var el = cards.get(id); if (el) { el.hidden = !shown.has(id); frag.appendChild(el); } });
  list.appendChild(frag);
  count.textContent = active
    ? ids.length + ' of ' + cards.size + (cards.size === 1 ? ' record matches' : ' records match')
    : 'Showing all ' + cards.size + ' records';
  empty.hidden = ids.length > 0;
  facetCount.textContent = nFacets ? '(' + nFacets + ' active)' : '';
  syncUrl(st);
}
function fromUrl() {
  var sp = new URLSearchParams(location.search);
  q.value = sp.get('q') || '';
  for (var p in FACETS) {
    var sel = form.elements.namedItem(p), v = sp.get(p) || '';
    sel.value = v;
    if (sel.value !== v) sel.value = '';  // unknown value in a shared link: ignore it
  }
  sortSel.value = sp.get('sort') || '';
  if (sortSel.value !== (sp.get('sort') || '')) sortSel.value = '';
}
function clearAll() {
  q.value = '';
  for (var p in FACETS) form.elements.namedItem(p).value = '';
  render();
  q.focus();
}

form.addEventListener('submit', function (e) { e.preventDefault(); });
document.querySelectorAll('button.clear').forEach(function (b) { b.addEventListener('click', clearAll); });
document.addEventListener('keydown', function (e) {
  var tag = (document.activeElement && document.activeElement.tagName) || '';
  if (e.key === '/' && !e.ctrlKey && !e.metaKey && !e.altKey && !/^(INPUT|SELECT|TEXTAREA|BUTTON)$/.test(tag)) {
    e.preventDefault(); q.focus();
  }
});

fetch(list.dataset.index)
  .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
  .then(function (data) {
    records = data.records;
    form.addEventListener('input', render);
    form.addEventListener('change', render);
    facets.open = window.matchMedia('(min-width: 720px)').matches;  // collapsed on narrow screens
    form.hidden = false;
    fromUrl();
    render();
  })
  .catch(function () {
    count.textContent = 'Search is unavailable here; all ' + cards.size + ' records are listed below.';
  });
})();
"""


def main() -> int:
    recs = load_incidents()
    ids = {r["incident_id"] for r in recs}
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    (OUT / "style.css").write_text(CSS)
    (OUT / "index.html").write_text(render_index(recs))
    (OUT / "search-index.json").write_text(search_index_json(recs), encoding="utf-8")
    (OUT / "search.js").write_text(SEARCH_JS, encoding="utf-8")
    (OUT / "sitemap.xml").write_text(render_sitemap(recs), encoding="utf-8")
    (OUT / "robots.txt").write_text(render_robots(), encoding="utf-8")
    (OUT / "feed.xml").write_text(render_feed(recs))
    for r in recs:
        d = OUT / r["incident_id"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(render_incident(r, ids))
    # .nojekyll so GitHub Pages serves files/dirs verbatim
    (OUT / ".nojekyll").write_text("")
    print(f"built site/ — {len(recs)} incidents, index + feed, base {SITE_BASE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

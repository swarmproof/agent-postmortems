"""Tests for page metadata, crawl files, footer links and third-party isolation.

Self-contained (no conftest). Run with:
  uv run --with pytest --with pyyaml --with jsonschema pytest -q tests/test_site_meta.py

The whole site is built once into a temporary directory with the real main().
"""
from __future__ import annotations

import copy
import html.parser
import importlib.util
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("build_site_meta", REPO / "scripts" / "build_site.py")
bs = importlib.util.module_from_spec(_spec)
sys.modules["build_site_meta"] = bs
_spec.loader.exec_module(bs)

RECS = bs.load_incidents()
HOSTILE = '"><script>alert(1)</script> " onmouseover="alert(2)'


class Head(html.parser.HTMLParser):
    """Collects the tags and attributes the metadata tests care about."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, dict]] = []
        self.title_parts: list[str] = []
        self._in_title = False
        self.ld: list[str] = []
        self._in_ld = False

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        self.tags.append((tag, a))
        self._in_title = tag == "title"
        self._in_ld = tag == "script" and a.get("type") == "application/ld+json"

    def handle_endtag(self, tag):
        self._in_title = self._in_ld = False

    def handle_data(self, data):
        if self._in_title:
            self.title_parts.append(data)
        if self._in_ld:
            self.ld.append(data)

    def all(self, tag, **match):
        return [a for t, a in self.tags if t == tag and all(a.get(k) == v for k, v in match.items())]

    def meta(self, key):
        return [a.get("content", "") for t, a in self.tags
                if t == "meta" and (a.get("name") == key or a.get("property") == key)]


def parse(text: str) -> Head:
    h = Head()
    h.feed(text)
    return h


@pytest.fixture(scope="module")
def site(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("site")
    old = bs.OUT
    bs.OUT = out
    try:
        assert bs.main() == 0
    finally:
        bs.OUT = old
    return out


def pages(site: Path) -> dict[str, Path]:
    """URL path ('' for the index, '<id>/' for permalinks) -> built file."""
    found = {"": site / "index.html"}
    for p in site.glob("*/index.html"):
        found[f"{p.parent.name}/"] = p
    return found


# --------------------------------------------------------------------------- per-page metadata
def test_every_page_has_one_canonical_title_and_description(site):
    built = pages(site)
    assert len(built) == len(RECS) + 1
    canonicals = []
    for path, f in built.items():
        h = parse(f.read_text())
        canon = [a["href"] for a in h.all("link", rel="canonical")]
        assert canon == [f"{bs.SITE_BASE}/{path}"], path
        canonicals.append(canon[0])
        assert len(h.all("title")) == 1 and "".join(h.title_parts).strip(), path
        desc = h.meta("description")
        assert len(desc) == 1 and desc[0].strip(), path
        assert len(desc[0]) <= 200
        assert h.meta("og:url") == canon and h.meta("og:description") == desc
        assert len(h.meta("og:title")) == 1 and h.meta("og:title")[0].strip()
        assert h.meta("twitter:card") == ["summary"]
        assert not h.meta("og:image") and not h.meta("twitter:image")  # text-only cards, no remote assets
    assert len(canonicals) == len(set(canonicals))


def test_incident_page_title_and_description_come_from_the_record(site):
    rec = next(r for r in RECS if len(r.get("summary", "")) > 200)
    h = parse((site / rec["incident_id"] / "index.html").read_text())
    assert "".join(h.title_parts) == f"{rec['title']} — agent-postmortems"
    assert h.meta("og:title") == [rec["title"]] and h.meta("og:type") == ["article"]
    desc = h.meta("description")[0]
    flat = " ".join(rec["summary"].split())
    assert desc.endswith("…") and flat.startswith(desc[:-1])
    assert flat[len(desc) - 1] == " "  # cut at a word boundary


def test_meta_description_helper():
    assert bs.meta_description("  short\n text ") == "short text"
    long = "word " * 100
    out = bs.meta_description(long)
    assert len(out) <= 200 and out.endswith("…") and not out[:-1].endswith(" ")


def test_index_dataset_jsonld_states_only_verifiable_facts(site):
    h = parse((site / "index.html").read_text())
    assert len(h.ld) == 1
    ld = json.loads(h.ld[0])
    assert set(ld) == {"@context", "@type", "name", "description", "url", "license",
                       "isAccessibleForFree", "distribution"}
    assert ld["@type"] == "Dataset" and ld["url"] == f"{bs.SITE_BASE}/"
    assert ld["description"] == h.meta("description")[0]
    # licence matches the data licence file
    assert ld["license"] == "https://creativecommons.org/licenses/by/4.0/"
    assert "Attribution 4.0 International" in (REPO / "LICENSE-DATA").read_text()
    # the download points at a file the repository tracks
    url = ld["distribution"][0]["contentUrl"]
    rel = url.removeprefix(bs.RAW_BASE + "/")
    tracked = subprocess.run(["git", "ls-files", rel], cwd=REPO, capture_output=True, text=True).stdout.strip()
    assert tracked == rel
    # incident pages carry no structured data (no truthful mapping to a schema.org type yet)
    rec = RECS[0]
    assert not parse((site / rec["incident_id"] / "index.html").read_text()).ld


# --------------------------------------------------------------------------- crawl files
def test_sitemap_lists_index_and_every_permalink(site):
    root = ET.parse(site / "sitemap.xml").getroot()
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    entries = root.findall("s:url", ns)
    locs = [e.find("s:loc", ns).text for e in entries]
    expected = {f"{bs.SITE_BASE}/"} | {f"{bs.SITE_BASE}/{r['incident_id']}/" for r in RECS}
    assert len(locs) == len(set(locs)) and set(locs) == expected
    assert set(locs) == {f"{bs.SITE_BASE}/{p}" for p in pages(site)}  # every loc is a built page
    by_id = {r["incident_id"]: r for r in RECS}
    for e in entries:
        rid = e.find("s:loc", ns).text.removeprefix(bs.SITE_BASE + "/").rstrip("/")
        lastmod = e.find("s:lastmod", ns)
        stated = by_id[rid].get("last_updated") if rid else None
        assert (lastmod.text if lastmod is not None else None) == stated  # never invented


def test_robots_points_to_sitemap(site):
    robots = (site / "robots.txt").read_text()
    assert "User-agent: *" in robots and f"Sitemap: {bs.SITE_BASE}/sitemap.xml" in robots
    assert "Disallow: /\n" not in robots


# --------------------------------------------------------------------------- footer
def test_footer_links_licences_policies_methods_and_feed(site):
    for path in ("", f"{RECS[0]['incident_id']}/"):
        text = (site / (path or ".") / "index.html").read_text()
        foot = text[text.index('<footer class="site-foot">'):]
        hrefs = [a["href"] for a in parse(foot).all("a")]
        for target in ("LICENSE", "LICENSE-DATA", "DISPUTES.md", "SECURITY.md", "CONTRIBUTING.md",
                       "docs/METHODS.md"):
            assert f"{bs.REPO_URL}/blob/main/{target}" in hrefs, target
        assert f"{bs.SITE_BASE}/feed.xml" in hrefs
        assert "CC-BY-4.0" in foot and "Apache-2.0" in foot
    for f in ("LICENSE", "LICENSE-DATA", "DISPUTES.md", "SECURITY.md", "CONTRIBUTING.md"):
        assert (REPO / f).exists(), f


# --------------------------------------------------------------------------- third parties
EXTERNAL = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|//)", re.I)
TRACKERS = ("google-analytics.com", "googletagmanager.com", "gtag(", "plausible.io", "umami.is", "segment.com",
            "segment.io", "hotjar.com", "matomo", "clarity.ms", "connect.facebook.net", "doubleclick.net")


def test_no_external_script_style_or_media_hosts(site):
    code = []  # everything that can load or run: URLs, inline script bodies, JS and CSS
    for path, f in pages(site).items():
        h = parse(f.read_text())
        loads = ([a.get("src", "") for a in h.all("script") if a.get("src")]
                 + [a["href"] for a in h.all("link") if a.get("rel") in ("stylesheet", "preload", "icon",
                                                                          "modulepreload", "manifest")]
                 + [a.get("src", "") for t in ("img", "iframe", "audio", "video", "source", "embed")
                    for a in h.all(t)])
        assert loads and not [u for u in loads if EXTERNAL.match(u)], (path, loads)
        code += loads + h.ld
    css = (site / "style.css").read_text()
    assert "@import" not in css and "url(" not in css
    js = (site / "search.js").read_text()
    assert not re.search(r"""fetch\(\s*['"]https?:""", js) and "XMLHttpRequest" not in js
    blob = "\n".join(code) + css + js
    assert not [t for t in TRACKERS if t in blob]


# --------------------------------------------------------------------------- escaping
def test_hostile_title_and_summary_are_escaped_in_meta(site):
    rec = copy.deepcopy(RECS[0])
    rec["incident_id"] = "2099-meta-xss-fixture"
    rec["title"] = f"Title {HOSTILE}"
    rec["summary"] = f"Summary {HOSTILE}"
    page = bs.render_incident(rec, {rec["incident_id"]})
    head = page[: page.index("</head>")]
    assert "<script>alert" not in page and '" onmouseover=' not in page
    assert re.findall(r"<script\b", head) == []
    h = parse(page)
    # attribute values round-trip to the original text, so escaping is correct rather than lossy
    assert h.meta("og:title") == [rec["title"]] and h.meta("twitter:title") == [rec["title"]]
    assert h.meta("description") == [bs.meta_description(rec["summary"])]
    assert "".join(h.title_parts) == f"{rec['title']} — agent-postmortems"
    assert [a["href"] for a in h.all("link", rel="canonical")] == [f"{bs.SITE_BASE}/2099-meta-xss-fixture/"]


def test_jsonld_payload_cannot_close_its_script_element():
    out = bs.json_for_html({"x": "</script><script>alert(1)</script>&"})
    assert "<" not in out and ">" not in out and "&" not in out
    assert json.loads(out) == {"x": "</script><script>alert(1)</script>&"}


# --------------------------------------------------------------------------- accessibility
def test_every_page_starts_with_a_skip_link_to_main(site):
    for path, f in pages(site).items():
        text = f.read_text()
        body = text[text.index("<body>"):]
        first_link = re.search(r"<a\b[^>]*>", body).group(0)
        assert first_link == '<a class="skip-link" href="#main">', path
        assert text.count('<main id="main" tabindex="-1">') == 1, path
    css = bs.CSS
    assert ".skip-link:focus { top:8px; }" in css  # hidden off-screen until focused, then visible


def test_index_result_cards_have_one_heading_each(site):
    text = (site / "index.html").read_text()
    cards = re.findall(r'<a class="card"[^>]*>(.*?)</a>', text, re.S)
    assert len(cards) == len(RECS)
    for c in cards:
        assert len(re.findall(r"<h2 class=\"card-title\">", c)) == 1
    levels = [int(h) for h in re.findall(r"<h([1-6])\b", text)]
    assert levels.count(1) == 1 and levels[0] == 1 and all(b - a <= 1 for a, b in zip(levels, levels[1:]))

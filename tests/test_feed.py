"""RSS feed correctness: well-formed XML, RFC 822 dates, stable GUIDs, determinism."""
from __future__ import annotations

import datetime
import email.utils
import importlib.util
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
UTC = datetime.timezone.utc
BUILT = datetime.datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def _load_build_site():
    spec = importlib.util.spec_from_file_location("build_site", REPO / "scripts" / "build_site.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bs = _load_build_site()


def _items(feed: str):
    root = ET.fromstring(feed.encode("utf-8"))
    return root, root.findall("./channel/item")


def _aware(text: str) -> datetime.datetime:
    dt = email.utils.parsedate_to_datetime(text)
    assert dt.tzinfo is not None, f"naive date in feed: {text!r}"
    return dt


def test_corpus_feed_parses_with_rfc822_dates():
    recs = bs.load_incidents()
    root, items = _items(bs.render_feed(recs, built=BUILT))
    assert len(items) == min(bs.FEED_LIMIT, len(recs))
    assert _aware(root.findtext("./channel/lastBuildDate")) == BUILT
    pubs = [_aware(i.findtext("pubDate")) for i in items]
    assert pubs == sorted(pubs, reverse=True), "items must be newest-published first"


def test_pubdate_is_publication_not_occurrence():
    rec = {"incident_id": "2019-old-event", "title": "t", "date": "2019-05-05",
           "sources": [{"url": "https://example.org", "date_accessed": "2026-03-04"}]}
    published = {"2019-old-event": datetime.datetime(2026, 3, 9, 12, 0, tzinfo=UTC)}
    _, items = _items(bs.render_feed([rec], built=BUILT, published=published))
    assert _aware(items[0].findtext("pubDate")) == published["2019-old-event"]
    # Without git history the record's earliest date_accessed is used, never `date`.
    _, items = _items(bs.render_feed([rec], built=BUILT, published={}))
    assert _aware(items[0].findtext("pubDate")) == datetime.datetime(2026, 3, 4, tzinfo=UTC)


def test_guids_are_stable_permalinks_across_builds():
    recs = bs.load_incidents()
    a = _items(bs.render_feed(recs, built=BUILT))[1]
    b = _items(bs.render_feed(recs, built=BUILT + datetime.timedelta(days=3)))[1]
    guids_a = [i.findtext("guid") for i in a]
    assert guids_a == [i.findtext("guid") for i in b]
    assert len(set(guids_a)) == len(guids_a), "duplicate guid in feed"
    for item in a:
        # The guid format predates this test; changing it re-notifies every subscriber.
        assert item.find("guid").get("isPermaLink") == "true"
        assert item.findtext("guid") == item.findtext("link")
        assert item.findtext("guid").startswith(bs.SITE_BASE + "/")
        assert item.findtext("guid").endswith("/")


def test_hostile_title_stays_well_formed():
    hostile = 'a <script>alert(1)</script> & b ]]> "q" \'s\x01\x0b'
    rec = {"incident_id": "2026-hostile", "title": hostile, "summary": hostile,
           "date": "2026-01-01", "sources": []}
    _, items = _items(bs.render_feed([rec], built=BUILT, published={}))
    title = items[0].findtext("title")
    assert "<script>alert(1)</script>" in title and "& b ]]>" in title
    assert "\x01" not in title and "\x0b" not in title
    assert items[0].find("title/script") is None, "markup leaked into the element tree"
    # No git date and no date_accessed: falls back to the build time.
    assert _aware(items[0].findtext("pubDate")) == BUILT


def test_deterministic_with_injected_build_date(monkeypatch):
    recs = bs.load_incidents()
    published = bs.git_first_added()
    assert bs.render_feed(recs, built=BUILT, published=published) == \
        bs.render_feed(recs, built=BUILT, published=published)
    monkeypatch.setenv("SOURCE_DATE_EPOCH", str(int(BUILT.timestamp())))
    assert bs.build_time() == BUILT
    assert bs.render_feed(recs) == bs.render_feed(recs, built=BUILT, published=published)


def test_naive_datetime_rejected():
    try:
        bs.rfc822(datetime.datetime(2026, 1, 1))
    except ValueError:
        return
    raise AssertionError("naive datetime accepted")

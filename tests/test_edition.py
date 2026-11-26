"""The first edition preserves the distinction between a case and a proposed check."""
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("edition_site", REPO / "scripts/build_site.py")
site = importlib.util.module_from_spec(spec)
spec.loader.exec_module(site)
RECORDS = site.load_incidents()
BY_ID = {record["incident_id"]: record for record in RECORDS}
EPOCH = "2026-trajectory-epoch-evaluation-live-site"
BINANCE = "2026-binance-internal-ai-tool-lateral-movement"


def test_feature_order_and_archive_search_are_independent():
    page = site.render_index(RECORDS)
    features = page.split('aria-label="Featured investigations"', 1)[1].split('id="archive"', 1)[0]
    assert features.index(EPOCH) < features.index(BINANCE)
    assert 'href="#archive"' in page
    assert 'data-index="search-index.json"' in page
    assert page.count('class="card"') == len(RECORDS)
    assert 'a SwarmProof publication' in page


def test_epoch_dates_consent_and_reader_question_survive_rendering():
    rec = BY_ID[EPOCH]
    assert rec["date"] == "2026-10-20"
    assert rec["disclosed_on"] == "2026-11-13"
    page = site.render_incident(rec, set(BY_ID))
    assert "36,411" in page and "487" in page
    assert "October 23" in page and "October 26" in page
    assert "Epoch’s consent" in page
    assert "no private or confidential information" in page
    assert site.INVESTIGATIONS[EPOCH]["question"] in page
    assert "Detection" in page
    assert "Request a correction" in page


def test_binance_does_not_turn_unknown_autonomy_into_a_measured_cause():
    rec = BY_ID[BINANCE]
    assert rec["system"]["autonomy_level"] == "unknown"
    assert rec["causation"]["entity"] == "human"
    assert any(a["evidence_status"] == "unknown" and a["field_path"] == "/root_cause"
               for a in rec["evidence_assessments"])
    page = site.render_incident(rec, set(BY_ID))
    assert "The loss belongs to the whole incident" in page
    assert "autonomy" in page
    assert site.INVESTIGATIONS[BINANCE]["question"] in page


def test_each_feature_claim_uses_its_record_sources():
    for rid in (EPOCH, BINANCE):
        rec = BY_ID[rid]
        urls = {source["url"] for source in rec["sources"]}
        assert all(set(a["source_urls"]) <= urls for a in rec["evidence_assessments"])
        assert all(a.get("uncertainty") for a in rec["evidence_assessments"]
                   if a["evidence_status"] in ("unknown", "inferred"))

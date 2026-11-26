#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml", "requests"]
# ///
"""G-LINK / G-ARCHIVE — source link-liveness and Wayback archive backfill.

Liveness policy:
  2xx/3xx                       -> ok
  403/405/429                   -> warn (bot-blocked or rate-limited; reachable to humans)
  404/410, other definitive 4xx -> FAIL, UNLESS the
                                   source carries a reachable archive_url, in which case the
                                   citation survives via Wayback -> warn.
  5xx / timeout / connection error -> "unreachable": transient failure, not evidence of removal.
                                   warn if the source carries an archive_url (whether or not
                                   Wayback itself answered just now); FAIL only when there is
                                   no archive on file, i.e. nothing else vouches for the cite.
  Only a dead primary AND a dead/absent archive blocks the gate.

Usage:
  uv run scripts/check_links.py                 # check every sources[].url in the corpus
  uv run scripts/check_links.py incidents/a.yaml incidents/b.yaml
                                                # check only the given records (CI scopes a
                                                #  pull request to the records it changes)
  uv run scripts/check_links.py --backfill      # also write archive_url for sources lacking one
                                                # (uses the Wayback availability API, then falls
                                                #  back to requesting a fresh snapshot)
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import requests
import yaml

REPO = Path(__file__).resolve().parent.parent
INCIDENTS_DIR = REPO / "incidents"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 agent-postmortems-linkcheck"}
RETRIES = 2
# "Reachable but refusing this client" — anti-bot / auth responses, not dead links.
# These warn (verify manually) rather than fail; only 404/410, other 4xx, 5xx and
# DNS/connection errors without an archive block the link gate.
WARN_CODES = {401, 403, 405, 406, 429, 451}


def probe(url: str) -> tuple[str, str]:
    """Return (verdict, detail) where verdict is ok | warn | fail | unreachable.

    fail means the host answered with a dead status; unreachable means no answer at all
    (timeout, DNS, reset) after retries, which is a transient-or-dead ambiguity.
    """
    last = ""
    verdict = "unreachable"
    for attempt in range(RETRIES + 1):
        try:
            resp = requests.head(url, headers=UA, timeout=15, allow_redirects=True)
            if resp.status_code in (405, 501) or resp.status_code >= 400:
                resp = requests.get(url, headers=UA, timeout=20, allow_redirects=True, stream=True)
                resp.close()
            code = resp.status_code
            if code < 400:
                return "ok", str(code)
            if code in WARN_CODES:
                return "warn", f"{code} (likely bot-block; verify manually)"
            last = f"HTTP {code}"
            verdict = "unreachable" if code >= 500 else "fail"
        except requests.RequestException as exc:
            last = type(exc).__name__
            verdict = "unreachable"
        if attempt < RETRIES:
            time.sleep(5 * (attempt + 1))
    return verdict, last


def wayback_lookup(url: str) -> str | None:
    try:
        resp = requests.get("https://archive.org/wayback/available",
                            params={"url": url}, headers=UA, timeout=20)
        snap = resp.json().get("archived_snapshots", {}).get("closest", {})
        if snap.get("available"):
            return snap["url"].replace("http://", "https://", 1)
    except (requests.RequestException, ValueError):
        pass
    return None


def wayback_save(url: str) -> str | None:
    try:
        resp = requests.get(f"https://web.archive.org/save/{url}", headers=UA, timeout=90)
        if resp.status_code < 400:
            return resp.url if "web.archive.org/web/" in resp.url else None
    except requests.RequestException:
        pass
    return None


def backfill_archive(path: Path, url: str, archive_url: str) -> bool:
    """Insert archive_url after the source's date_accessed line, preserving formatting."""
    text = path.read_text()
    escaped = re.escape(url)
    pattern = re.compile(
        rf'(- url: "{escaped}"(?:\n {{4}}\S[^\n]*)*?\n( {{4}})date_accessed: "[^"]*")',
        re.MULTILINE,
    )
    m = pattern.search(text)
    if not m:
        return False
    insertion = f'{m.group(1)}\n{m.group(2)}archive_url: "{archive_url}"'
    path.write_text(text[: m.start(1)] + insertion + text[m.end(1):])
    return True


def main() -> int:
    do_backfill = "--backfill" in sys.argv
    selected = [Path(a) for a in sys.argv[1:] if not a.startswith("--")]
    paths = selected or sorted(INCIDENTS_DIR.glob("*.yaml"))
    failures = warnings = archived = 0
    for path in paths:
        if path.name.startswith("_"):
            continue
        record = yaml.safe_load(path.read_text())
        for src in record.get("sources", []):
            url = src["url"] if isinstance(src, dict) else src
            verdict, detail = probe(url)
            # Link rot is expected; archive_url is the permanence mechanism (ADR-0004).
            # A dead primary whose archive is still reachable degrades to a warning
            # rather than blocking the gate.
            has_archive = isinstance(src, dict) and bool(src.get("archive_url"))
            if verdict == "fail" and has_archive:
                arc_verdict, arc_detail = probe(src["archive_url"])
                detail += f"; archive {arc_verdict}: {arc_detail}"
                if arc_verdict != "fail":
                    verdict, detail = "warn", f"{detail}; primary dead, archive live"
            # No answer is not evidence of death. With an archive on file the citation
            # is preserved whatever this probe saw, so a transient outage of the primary
            # (or of Wayback itself) must not fail an unrelated gate run.
            elif verdict == "unreachable":
                if has_archive:
                    verdict, detail = "warn", f"{detail}; primary unreachable, archive on file"
                else:
                    verdict, detail = "fail", f"{detail}; unreachable and no archive_url"
            marker = {"ok": "ok  ", "warn": "WARN", "fail": "FAIL"}[verdict]
            print(f"{marker} [{path.stem}] {url} ({detail})")
            if verdict == "fail":
                failures += 1
            elif verdict == "warn":
                warnings += 1
            if do_backfill and isinstance(src, dict) and not src.get("archive_url"):
                snapshot = wayback_lookup(url) or wayback_save(url)
                if snapshot and backfill_archive(path, url, snapshot):
                    archived += 1
                    print(f"     archived -> {snapshot}")
    print(f"\n{failures} dead link(s), {warnings} warning(s)"
          + (f", {archived} archive_url(s) backfilled" if do_backfill else ""))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml", "jsonschema"]
# ///
"""Build the assets of a corpus release from a clean checkout of its tag.

Writes into --out (default dist/release/):
  incidents.json, scenarios.json, seeds.json   compatible v1 exports, rebuilt from incidents/
  incidents.v2.json                             full enriched records, envelope version 2.0
  incident.schema.json                          frozen v1 reader schema
  incident.enriched.schema.json                 current source-record schema
  *.export.schema.json                          matching envelope schemas
  CITATION.cff                                  verbatim
  manifest.json                                 counts, versions, git commit, per-file sha256
  SHA256SUMS                                    `sha256sum -c` format, covers every file above

Reproducible: the exports are a pure function of the corpus (their stamp is the
newest incident date, not the clock), and the only time in the manifest is
SOURCE_DATE_EPOCH, defaulting to the committer time of HEAD. Two builds of the
same commit with the same SOURCE_DATE_EPOCH are byte-identical.

Drift: the rebuilt exports must equal export/*.json as committed. Releases tag
the publish-workflow commit, where they always do; a mismatch means the tag is
not such a commit, or the build is not deterministic, and the build fails.
Pull requests do not commit exports, so this check belongs here and in the
publish workflow, never on pull-request CI.

Usage:
  uv run scripts/build_release.py [--out DIR] [--tag TAG] [--allow-dirty]
  cd dist/release && sha256sum -c SHA256SUMS
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
EXPORT_NAMES = ("incidents", "scenarios", "seeds", "incidents.v2")
# Paths whose uncommitted edits would make the assets differ from the tag.
TRACKED_INPUTS = ("incidents", "schema", "scripts", "export", "CITATION.cff")


def _load_build_exports():
    spec = importlib.util.spec_from_file_location("build_exports", REPO / "scripts" / "build_exports.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(REPO), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def source_date_epoch() -> int:
    env = os.environ.get("SOURCE_DATE_EPOCH")
    return int(env) if env else int(git("log", "-1", "--format=%ct"))


def current_tag() -> str | None:
    try:
        return git("describe", "--tags", "--exact-match", "HEAD") or None
    except subprocess.CalledProcessError:
        return None


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def drift(rendered: dict[str, str], export_dir: Path) -> list[str]:
    """Names whose committed export differs byte-for-byte from the rebuild."""
    stale = []
    for name, text in rendered.items():
        path = export_dir / f"{name}.json"
        if not path.exists() or path.read_text() != text:
            stale.append(name)
    return stale


def counts(incidents_dir: Path) -> dict[str, int]:
    records = [yaml.safe_load(p.read_text()) for p in sorted(incidents_dir.glob("*.yaml"))
               if not p.name.startswith("_")]
    return {
        "records": len(records),
        "incidents": sum(r.get("incident_type") == "incident" for r in records),
        "hazards": sum(r.get("incident_type") == "hazard" for r in records),
    }


def build(out: Path, *, epoch: int, tag: str | None = None, check_drift: bool = True) -> dict:
    """Write every release asset into `out` (emptied first) and return the manifest."""
    be = _load_build_exports()
    artifacts = be.build_artifacts()
    rendered = {name: be.render(artifacts[name]) for name in EXPORT_NAMES}
    if check_drift:
        stale = drift(rendered, REPO / "export")
        if stale:
            raise SystemExit(f"export drift: committed export/{{{','.join(stale)}}}.json differ from "
                             "a rebuild; tag the publish-workflow commit (docs/RELEASING.md)")

    files: dict[str, bytes] = {f"{n}.json": rendered[n].encode("utf-8") for n in EXPORT_NAMES}
    files["incident.schema.json"] = (REPO / "schema" / "incident.v1.schema.json").read_bytes()
    files["incident.enriched.schema.json"] = (REPO / "schema" / "incident.schema.json").read_bytes()
    for name in EXPORT_NAMES:
        files[f"{name}.export.schema.json"] = (REPO / "schema" / "export" / f"{name}.schema.json").read_bytes()
    files["CITATION.cff"] = (REPO / "CITATION.cff").read_bytes()

    inc = artifacts["incidents"]
    schema_versions = sorted({r.get("schema_version") for r in inc["incidents"]})
    manifest = {
        "name": "agent-postmortems",
        "release": tag,
        "git_commit": git("rev-parse", "HEAD"),
        "source_date_epoch": epoch,
        "built_at": datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc)
                    .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "corpus_as_of": artifacts["incidents.v2"]["corpus_as_of"],
        "enriched_export_schema_version": "2.0",
        "schema_version": schema_versions[0] if len(schema_versions) == 1 else schema_versions,
        "taxonomy_version": inc["taxonomy_version"],
        "export_schema_version": inc["export_schema_version"],
        "counts": {
            **counts(REPO / "incidents"),
            "scenarios": artifacts["scenarios"]["count"],
            "seeds": artifacts["seeds"]["count"],
        },
        "files": {name: {"sha256": sha256(data), "bytes": len(data)} for name, data in sorted(files.items())},
    }
    if manifest["counts"]["records"] != inc["count"]:
        raise SystemExit(f"count mismatch: {manifest['counts']['records']} incident files, "
                         f"{inc['count']} exported")
    files["manifest.json"] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    sums = "".join(f"{sha256(files[n])}  {n}\n" for n in sorted(files))

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for name, data in files.items():
        (out / name).write_bytes(data)
    (out / "SHA256SUMS").write_text(sums)
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=REPO / "dist" / "release")
    ap.add_argument("--tag", help="release tag recorded in the manifest (default: exact tag at HEAD)")
    ap.add_argument("--allow-dirty", action="store_true",
                    help="build despite uncommitted changes to corpus, schema, scripts or exports")
    a = ap.parse_args()

    dirty = git("status", "--porcelain", "--", *TRACKED_INPUTS)
    if dirty and not a.allow_dirty:
        print(dirty, file=sys.stderr)
        raise SystemExit("working tree has uncommitted changes; build from a clean checkout of the tag")

    m = build(a.out, epoch=source_date_epoch(), tag=a.tag or current_tag())
    c = m["counts"]
    print(f"release {m['release'] or '(untagged)'} @ {m['git_commit'][:12]}: {c['records']} records "
          f"({c['incidents']} incidents · {c['hazards']} hazards), {c['scenarios']} scenarios, "
          f"{c['seeds']} seeds -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

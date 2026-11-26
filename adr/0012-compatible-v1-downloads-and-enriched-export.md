# ADR-0012 — Compatible v1 downloads and an enriched export

Status — accepted implementation for review, 26 November 2026.

The schema at release 2026.11.2 rejects extra record properties. Its three export
envelopes also reject `corpus_as_of`. Keeping the required core and removing
extensions inside a test proved only that a projection was possible. It did not
prove the downloaded file satisfied the pinned reader.

The producer now performs that projection for `incidents.json`, preserving all
fields defined in the frozen v1 record schema. The original three export files
keep their names and envelope version 1.0. All validate directly against the
2026.11.2 schemas. Unknown or invalid source properties fail validation of the
complete enriched records. Only declared source extensions are omitted from
the v1 projection. Source YAML remains the editorial representation.

`incidents.v2.json` preserves every source field, carries the complete corpus,
and declares export schema version 2.0. Its envelope adds `corpus_as_of`. Its
inner record version retains its existing meaning and uses the current source
schema, supplied separately as `incident.enriched.schema.json` in a release.
`incident.schema.json` attached to the release is the frozen v1 schema matching
the original download. Each export also receives its matching envelope schema.

Both variants are built by the ordinary export command and included in release
drift checks, manifest hashes and checksums. Actual release bytes are validated
against frozen pinned-reader schemas in regression tests. The tests compare
the full enriched records with source YAML to catch accidental evidence loss.
This supersedes ADR-0011’s verbatim v1 export policy. Any future change to the
v1 files must keep passing those frozen consumer tests, or introduce an explicit
new representation with a migration path.

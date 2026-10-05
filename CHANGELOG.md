# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.3] - 2026-10-05

### Fixed

- **Usage errors now exit `5`, not `2`.** `argparse` exits `2` on a bad argument,
  which collided with the documented "findings at WARNING severity" code: a
  script gating on `rc == 2` could not tell a warning from a typo. The CLI now
  overrides argparse's exit code, so `2` unambiguously means WARNING and a
  malformed command line exits `5`. This changes the observed exit code for bad
  usage from `2` to `5`.
- **The `--help` epilog no longer contradicts the README exit-code table.** It
  previously listed `2` as "findings at ERROR severity" and `3` as "usage error",
  omitting WARNING entirely; it now matches the README exactly.
- **An unreadable file is recorded in machine-readable output.** With
  `--format sarif` or `--format json`, a file that cannot be read now also emits
  a structured record to stdout (a SARIF result with
  `executionSuccessful: false`, or a JSON object with `"readable": false`), so
  `pdfua check *.pdf --format sarif > results.sarif` no longer exits `4` while
  producing a log with no trace of the failure.

### Added

- `TestDocumentedExitCodeContract` runs the real CLI in a subprocess and pins
  every documented exit code (0/1/2/3/4/5), including that usage errors are `5`
  and that the `--help` epilog documents every code the CLI emits.

## [0.1.2] - 2026-10-04

### Changed

- Documentation only: the install instructions now point at PyPI, and the PyPI
  badge was added.

## [0.1.1] - 2026-10-04

### Changed

- Packaging and release metadata only; no code or behaviour changes. Added
  complete PyPI metadata (PEP 639 `license` expression, author, project URLs
  and classifiers) and a Trusted Publishing (OIDC) release workflow that
  publishes on `v*` tags.

## [0.1.0] - 2026-09-29

Initial release.

### Added

- `pdfua check <file>` with `--format text|json|sarif`, `--rules`,
  `--min-severity`, `--certain-only`, `--fail-fast`, `--quiet`.
- `pdfua rules` listing implemented rules and the clauses with no coverage.
- 12 checks covering 16 of the 106 machine-checkable PDF/UA-1 rules (15%):
  - `UA-01-005` structure tree present
  - `UA-01-002` `/MarkInfo` `/Marked` true
  - `UA-01-003` page content tagged or marked as artifact
  - `UA-06-001` document language
  - `UA-07-001` document title
  - `UA-07-002` `DisplayDocTitle`
  - `UA-13-004` figure alternative text
  - `UA-14-001` non-empty headings
  - `UA-15-003` determinable table structure
  - `UA-18-001` annotation descriptions
  - `UA-18-005` link descriptions
  - `UA-28-004` PDF/UA identification in XMP
- SARIF 2.1.0 output for GitHub code scanning and Azure DevOps.
- Severity-ordered exit codes (0 clean, 1 info, 2 warning, 3 error).
- Full type annotations, `py.typed` marker, strict `mypy` configuration.

### Notes

- This is 12 checks covering 16 of the 106 machine-checkable rules in the
  PDF/UA-1 profile. The other 90 are not checked. See the README section
  "What this does NOT check".
- Development was validated against veraPDF 1.30.2 on a 16-file corpus (15
  distinct documents) of real `govinfo.gov`, `irs.gov` and `ada.gov` PDFs. See
  `docs/FALSIFICATION.md` for the evidence.

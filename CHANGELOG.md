# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
- Development was validated against veraPDF 1.30.2 on a 16-document corpus of
  real `govinfo.gov`, `irs.gov` and `ada.gov` PDFs. See
  `docs/FALSIFICATION.md` for the evidence.

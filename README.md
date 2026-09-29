# pdfua

**Check the machine-checkable subset of PDF/UA-1 and WCAG 2.1 for PDFs — in pure
Python, with no JVM.**

```bash
pip install pdfua
pdfua check report.pdf --format sarif
```

**This implements 12 checks covering 16 of the 106 machine-checkable rules in the
PDF/UA-1 profile — 15%.** Read
[What this does NOT check](#what-this-does-not-check) before you rely on it. It is
a fast triage gate, not a conformance certifier. For a conformance claim, run
[veraPDF](https://verapdf.org).

---

## The problem

There is a dated legal forcing function and no tool that fits a CI pipeline.

The U.S. Department of Justice's Title II rule requires state and local
governments to meet **WCAG 2.1 Level AA** for their web content and mobile apps.
PDFs are explicitly named as covered content. The compliance dates, from
`ada.gov`:

| State and local government size | Compliance date |
|---|---|
| 50,000 or more persons | **April 26, 2027** |
| 0 to 49,999 persons | **April 26, 2028** |
| Special district governments | **April 26, 2028** |

> "UPDATE: On April 20, 2026, the Department published an Interim Final Rule (IFR)
> extending the compliance date for State and local government entities with a
> total population of 50,000 or more to April 26, 2027. The compliance date for
> public entities with a total population of less than 50,000, or any special
> district government, is extended to April 26, 2028."
>
> — <https://www.ada.gov/title-ii-web-rule/>

> "The documents are word processing, presentation, PDF, or spreadsheet files"
> — <https://www.ada.gov/resources/2024-03-08-web-rule/>

So there is a hard deadline, a large population of PDFs that must comply, and
consequently a need to *check* PDFs automatically.

### Why the existing options do not fit

| Option | Why it does not work in CI |
|---|---|
| **veraPDF** — the authoritative validator | **Java.** Requires a JVM on every build agent. GPL-3.0 (dual MPLv2+). |
| **opendataloader-pdf** | The PyPI package is *"a Python wrapper for the opendataloader-pdf **Java CLI**"*. Its free tier is auto-tagging (producing a Tagged PDF); **PDF/UA export is an enterprise add-on**. It is a *remediator*, not an *auditor*. |
| **pdf-a11y** | A remediation pipeline whose `validator.py` is a `subprocess` wrapper around the veraPDF binary. It needs the JVM too. |
| **wcag_pdf_pytest** | Regex-scans raw PDF bytes for `/StructTreeRoot` and returns hardcoded passes for most criteria ("Heuristic pass: … not applicable"). It reports PASS on criteria it never examined. |
| Commercial services | Per-document pricing; not a build gate. |

`pdfua` occupies the empty slot: **`pip install`, no JVM, structured output, exit
codes.** It checks the failure classes that actually dominate real government
PDFs, and it says plainly what it did not check.

### What the evidence showed

This library was built only after a falsification pass against veraPDF 1.30.2 on
16 real government PDF files from `govinfo.gov`, `irs.gov` and `ada.gov` (15
distinct documents — see below). The full
evidence is in [`docs/FALSIFICATION.md`](docs/FALSIFICATION.md). The two findings
that shaped the design:

- **veraPDF reports 0 of 16 compliant.** All 16 fail PDF/UA-1.
- **99.55% of the 643,471 failed checks are two rules** — `7.1-3` ("content shall
  be marked as Artifact or tagged as real content") and `7.2-34` ("natural
  language for text in page content shall be determined"). Both are pure-Python
  reachable, and both are implemented here. A prototype's untagged-text counter
  tracked veraPDF's `7.1-3` at 92–99.9% agreement (e.g. 86,118 vs 86,131 on one
  1,039-page document).

Those totals cover **16 validated files, but only 15 distinct documents**: two
corpus files (`p08.pdf` and `7ef8534308.pdf`) are byte-identical (sha256
`9f5806…a853`), so the 643,471 figure double-counts 172,257 checks. Across the 15
distinct documents the de-duplicated total is **471,214**, of which the same two
rules account for 468,314 — **99.38%**, down from 99.55%. The concentration claim
holds either way, which is what the design argument rests on.

That is the honest case for this tool: the failures that dominate real documents
are cheap to detect and currently require a JVM to detect.

---

## Install

```bash
pip install pdfua
```

Requires Python 3.10+ and `pikepdf`. No JVM, no Java, no external binary.

### Why `pikepdf`

A PDF/UA check has to walk the COS object graph: `/StructTreeRoot`, `/K` child
chains, indirect references, content streams. `pikepdf` binds QPDF, ships binary
wheels for Linux/macOS/Windows (so `pip install` needs no compiler), and exposes
references rather than flattening them. `pypdf` was the alternative; it hides
indirect references, which PDF/UA rules care about. **You are not expected to
write a PDF parser, and this package does not contain one.**

---

## Usage

### CLI

```bash
pdfua check document.pdf
pdfua check *.pdf --format sarif > results.sarif
pdfua check document.pdf --rules UA-01,UA-13-004
pdfua check document.pdf --min-severity warning --certain-only
pdfua rules                     # what is implemented, and what is not
```

### Exit codes

| Code | Meaning |
|---|---|
| `0` | No findings |
| `1` | Findings at INFO severity |
| `2` | Findings at WARNING severity |
| `3` | Findings at ERROR severity |
| `4` | The file could not be read as a PDF |

With `--min-severity` set, any surviving finding exits `1`. Without it, the exit
code is ordered by severity, so the obvious thing works:

```bash
pdfua check report.pdf || echo "PDF/UA problems found"
```

### Library

```python
from pdfua import validate, Severity

report = validate("document.pdf")

print(report.exit_code)  # 0 clean, 1 info, 2 warning, 3 error
print(report.worst_severity())  # Severity.ERROR or None

for finding in report.findings:
    print(finding.rule_id, finding.severity.name, finding.location.describe())
    print("   ", finding.message)
    print("    fix:", finding.remediation)
```

Filtering, and the coverage figure:

```python
from pdfua import coverage, describe_rules
from pdfua.model import filter_findings, Confidence

cov = coverage()
print(cov.summary())  # "16 of 106 PDF/UA-1 rules (15%) across 12 implemented checks"

certain = filter_findings(report.findings, min_confidence=Confidence.CERTAIN)
```

---

## What this checks

12 checks, covering 16 PDF/UA-1 rule identifiers. Each is decidable from the PDF
alone, with no interpretation. `pdfua rules` prints this table from the registry,
so the numbers cannot drift from the code.

| Rule | PDF/UA-1 clause | WCAG | Severity | What it decides |
|---|---|---|---|---|
| `UA-01-005` | §7.1 | 1.3.1 | error | `/StructTreeRoot` is present |
| `UA-01-002` | §6.2 | 1.3.1 | error | `/MarkInfo /Marked` is true |
| `UA-01-003` | §7.1 | 1.3.1 | error | Page content is tagged or marked as an artifact |
| `UA-06-001` | §7.2 | 3.1.1 | error | Catalog `/Lang` is present and well-formed |
| `UA-07-001` | §7.1 | 2.4.2 | warning | A document `/Title` exists |
| `UA-07-002` | §7.1 | 2.4.2 | warning | `DisplayDocTitle` is true |
| `UA-13-004` | §7.3 | 1.1.1 | error | Every `/Figure` has non-empty `/Alt` or `/ActualText` |
| `UA-14-001` | §7.4 | 1.3.1, 2.4.6 | warning | No empty heading elements |
| `UA-15-003` | §7.5 | 1.3.1 | error | Table structure is determinable |
| `UA-18-001` | §7.18.1 | 1.1.1, 4.1.2 | warning | Annotations have descriptions |
| `UA-18-005` | §7.18.5 | 2.4.4 | warning | Link annotations have descriptions |
| `UA-28-004` | §5 | — | warning | PDF/UA identification in XMP |

---

## What this does NOT check

**A validator that overstates its coverage is worse than no validator.** This
section is the most important one in this file.

### It implements 12 checks, covering 16 of 106 rules

The public veraPDF PDF/UA-1 profile enumerates **106 machine-checkable rules** for
ISO 14289-1. This tool implements **12 checks**, which decide **16** of those
rules. `pdfua rules` prints both counts from the registry, so neither can drift.

**The other 90 rules are not checked.** A clean run means "these 16 rules found
nothing", never "this document conforms".

Coverage is counted at *rule* granularity, not per section, and that distinction
is the point. Clause 7.2 alone contains **41** rules; implementing one `/Lang`
check does not make the other forty checked. A tool that reported "7.2: 41/41"
because of a single check would be producing exactly the false comfort this
project exists to avoid.

Notably **not** checked:

- **Font embedding, `CIDSet`, glyph widths, font descriptors** (§7.21). These are
  the rules veraPDF uses to catch professionally-remediated files — `ada.gov`'s
  own web-rule PDF is `105/106` clean and fails only `7.21.4.2-2` (CIDSet). This
  tool will report that document as clean, because it does not look at fonts.
- **Reading order correctness** (§7.2). The tool confirms content *is* marked; it
  cannot judge whether the order is *meaningful*.
- **Colour spaces, output intents, transparency, ICC profiles.**
- **WTPDF 1.0** and **PDF/UA-2** (ISO 14289-2 / ISO 32005).
- **PDF/A** of any flavour.
- **Encrypted documents.** They raise, rather than guess.

### It cannot judge quality, only presence

This is the fundamental line, and the tool never crosses it:

| Machine-checkable (this tool) | Requires a human |
|---|---|
| A `/Figure` has an `/Alt` entry | Whether the alt text is *accurate* |
| The `/Alt` entry is non-empty | Whether it is *appropriate in context* |
| A table has `/TH` cells | Whether the header association is *correct* |
| Content is marked | Whether the reading order is *sensible* |
| A title exists | Whether the title is *descriptive* |

A figure whose alt text is `" "` (a single space) is structurally present and
semantically worthless. The tool flags the empty case (`UA-13-004`) but cannot
tell you that `"image"` or `"figure 3"` is a bad description. **Automated checks
reduce manual review; they do not replace it.**

### Findings marked `heuristic` are questions, not verdicts

Three finding sites carry `confidence: heuristic`, and in each case it is the
*site*, not the whole rule, that is a judgement call:

- **`UA-07-001`** (`DocumentTitleRule`) — every finding it emits is heuristic
  (`src/pdfua/rules/language.py:60` sets the class-level confidence).
- **`UA-13-004`** (`FigureAltTextRule`) — only the *empty or whitespace-only
  `/Alt`* branch, which is stricter than the letter of §7.3 and that veraPDF
  passes (`src/pdfua/rules/structure.py:73`). A figure with *no* `/Alt` at all
  is a certain finding.
- **`UA-15-003`** (`TableHeaderRule`) — only the *association* branch, where
  header cells exist but none carry `/Scope` or `/Headers`
  (`src/pdfua/rules/structure.py:144`). The rule itself has class-level severity
  `ERROR`, and its other branches are certain.

They narrow the question for a human. Use `--certain-only` to see only findings
the tool is certain about.

### A mistake this project made, recorded on purpose

An early version reported `"TH cells lack Scope"` on documents veraPDF passes.
That was **wrong about the standard**: ISO 14289-1 §7.5 requires `Scope` only *if
the structure is not determinable via `Headers` and `IDs`*. It is a fallback, not
a universal requirement. The IRS W-9 has `/TH` cells with neither, and is valid.

The rule was removed. It is documented in `docs/FALSIFICATION.md` and in the
`structure.py` module docstring because this is exactly the failure mode that
makes accessibility tooling distrusted, and the credibility of this tool depends
on not repeating it.

---

## For a conformance claim, use veraPDF

`pdfua` and veraPDF are complements, not competitors.

```bash
# Every commit: fast, no JVM
pdfua check report.pdf --format sarif || true

# Before you claim conformance: the authority
verapdf --flavour ua1 --format json report.pdf
```

`pdfua` gives you a JVM-free gate that produces SARIF for code scanning. Runtime
scales with document size and structure, so treat any single figure with care:
measured on this project's corpus (median of five runs) it is **~2–3 ms for a
184 KB document** and **~1.4 s for the 3.9 MB `ada.gov` web-rule PDF** — fast on
typical documents, seconds on very large ones, and always far below the cost of
starting a JVM. veraPDF remains the reference implementation. **If your CI has a JVM and
you need a conformance claim, use veraPDF and do not install this.** The tool
exists for the pipelines where a JVM is the reason nothing is checked at all.

---

## Development

```bash
uv venv && uv pip install -e ".[dev]"
.venv/bin/pytest
.venv/bin/mypy src/pdfua
.venv/bin/ruff check .
```

Test fixtures that violate exactly one rule each are **generated in code** by
`tests/fixtures/build.py` using `pikepdf`; no binary PDFs are committed. See
`tests/fixtures/README.md`.

## License

MIT. See [LICENSE](LICENSE).

The bundled `pdfua1_rules.json` contains **rule identifiers only** (ISO clause
number, test number, validation-object name) — no descriptive text is reproduced
from any validation profile, because that text belongs to its authors.

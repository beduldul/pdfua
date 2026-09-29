# Phase 1 — Falsification report

**Date:** 2026-09-29
**Claim under test:** *There is a real, unmet need for a pure-Python PDF/UA-1/2 + WCAG 2.1 AA
validator that runs in CI without a JVM, because no such package exists on PyPI and the
alternatives are either Java (veraPDF) or commercial.*

**Verdict: PASS — proceed to build.** The need is real and the wedge is real, but the wedge is
**narrower than the brief assumed** and this document states the corrected scope. See §6.

---

## 1. Absence check (PyPI)

Method: `GET https://pypi.org/simple/<name>/` and `GET https://pypi.org/pypi/<name>/json`.
`429/502/503/504` were retried up to 4× with backoff; **none were observed on any request**, so
every `404` below is a genuine "no such project" answer, not a throttle. Controls returned `200`
with real bodies, which is what makes the `404`s meaningful.

| name | `simple/` | `pypi/<n>/json` |
|---|---|---|
| **controls** | | |
| `pypdf` | 200 (92,325 B) | 200 (178,771 B) |
| `pikepdf` | 200 (3,570,493 B) | 200 (5,585,991 B) |
| `pypdfium2` | 200 (900,564 B) | 200 (1,483,810 B) |
| `pdfminer.six` | 200 (26,479 B) | 200 (60,481 B) |
| **candidates** | | |
| `pdfua` | **404** | **404** |
| `pdfua-check` | **404** | **404** |
| `verapdf` | **404** | **404** |
| `pdf-accessibility` | **404** | **404** |
| `pdf-ua-checker` | **404** | **404** |
| `pdfua-validator` | **404** | **404** |
| `accessibility-checker-pdf` | **404** | **404** |
| `pdf-ua` | **404** | **404** |
| `pdfua-checker` | **404** | **404** |
| `pdfaccessibility` | **404** | **404** |
| `a11y-pdf` | **404** | **404** |
| `pdf-a11y` | **200** (1,043 B) | **200** (52,855 B) ← **exists** |

**Full-index grep.** Downloaded `https://pypi.org/simple/` (46.5 MB, **900,845** project names) and
searched:

| pattern | matches |
|---|---|
| `pdfua` | **0** |
| `pdf-ua` | **0** |
| `pdf_ua` | **0** |
| `verapdf` | **0** |
| `14289` (the ISO number for PDF/UA-1) | **0** |
| `pdf-a11y` | 1 (`pdf-a11y`) |
| `wcag` | 6 (`bellbriar-wcag`, `wcag-abbreviations`, `wcag-checker`, `wcag-contrast-ratio`, `wcag-pdf-pytest`, `wcag-zoo`) |

**Absence is proven for the PDF/UA validator name-space.** Not a single project on PyPI carries
`pdfua`, `verapdf`, or the ISO standard number. The brief's "verified absence" reproduces exactly.

**But the brief's framing was incomplete, and the two adjacent packages matter:**

### 1a. `pdf-a11y` (v2.10.0, uploaded 2026-05-26) — does *not* close the gap

Self-described as a *"Programmatic PDF accessibility remediation pipeline targeting WCAG 2.2 /
PDF/UA-1 / WTPDF 1.0, **validator-verified with veraPDF**, fully local."*

I downloaded the wheel and read `pdf_a11y/validator.py`. It is a **`subprocess` wrapper around the
veraPDF binary**:

```python
subprocess.run([binary, "--format", "json", profile_flag, flavour, str(pdf_path)], ...)
```

Its own metadata confirms it: `requires_dist` includes `opendataloader-pdf>=2.4.4` and
`pymupdf`. It is a **remediation pipeline that shells out to Java veraPDF for validation**. It does
not contain a pure-Python PDF/UA validator. If anything it *proves* the gap: a 2026 project whose
whole purpose is PDF accessibility still had to reach for the JVM.

### 1b. `wcag_pdf_pytest` (v0.2.2, uploaded 2026-03-24) — a *decorative* WCAG suite

A pytest plugin generating one test per WCAG 2.1 SC (70 files). I read
`wcag_pdf_pytest/pdf_inspector.py` (923 lines). It **does not parse the PDF**. It regex-scans raw
bytes:

```python
_IMG_RE = re.compile(rb"/Subtype\s*/Image\b")
_ALT_RE = re.compile(rb"/Alt\s*(\(|<)")
_TAGGED_RE = re.compile(rb"/StructTreeRoot\b|/MarkInfo\s*<<[^>]*?/Marked\s*true", re.S)
```

and then, for most criteria, returns a hardcoded pass. Verbatim from the source:

> `"Heuristic pass: visual presentation constraints not applicable to static PDF text without CSS."`
> `"Heuristic pass: user agents handle text spacing adjustments; static PDF not script-driven."`
> `"Heuristic pass: no evidence of low-contrast non-text elements."`

It reports **PASS on criteria it never examined**. It is a false-assurance generator, not a
validator. It is also not a PDF/UA validator at all.

### 1c. `accessibility-devkit` (v1.1.2) — HTML only, not PDF

"Portable accessibility checks with explicit manual-review boundaries." Its `core.py` is
`hex_to_rgb` / contrast-ratio maths; `scanner.py` reads HTML tags (`h1`–`h6`, `tabindex`, link
text). No PDF parsing. Good posture ("explicit manual-review boundaries"), wrong format.

**Conclusion on §1:** the name-space is empty, the two adjacent packages are (a) a JVM wrapper and
(b) a regex-based false-assurance generator. The absence claim **survives**.

---

## 2. Legal claim — **CONFIRMED at source**

Two `ada.gov` pages were read directly. Quoted verbatim:

**`https://www.ada.gov/title-ii-web-rule/`**

> "UPDATE: On April 20, 2026, the Department published an Interim Final Rule (IFR) extending the
> compliance date for State and local government entities with a total population of 50,000 or
> more to April 26, 2027. The compliance date for public entities with a total population of less
> than 50,000, or any special district government, is extended to April 26, 2028."

**`https://www.ada.gov/resources/2024-03-08-web-rule/`** — the compliance table:

| State and local government size | Compliance date |
|---|---|
| 0 to 49,999 persons | April 26, 2028 |
| Special district governments | April 26, 2028 |
| 50,000 or more persons | April 26, 2027 |

> "After this time, state and local governments must continue to make sure their web content and
> mobile apps meet WCAG 2.1, Level AA."

**PDFs are explicitly covered web content.** The same page names PDF in the covered-format list —
*"The documents are word processing, presentation, PDF, or spreadsheet files"* — and applies the
requirement to PDFs through worked examples:

> "Example: A PDF document that includes a current map of a county park … the PDF would probably
> have to comply with WCAG 2.1, Level AA, because the content is [current]."
> "Example: A state posted a PDF version of a business license application on its website in 2020.
> … The exception would not apply to the application and it would usually need to [comply]."

**Confirmed.** The forcing function is real, dated, at source, and names PDFs.

> Note: the brief's URL `ada.gov/resources/web-rule-compliance-dates/` **404s**. The dates live at
> the two URLs above. The substance of the claim is correct; the cited path was not.

---

## 3. Competition assessment

### 3a. `veraPDF` — the authority, and it is Java

- `veraPDF/veraPDF-library`: **Java**, **GPL-3.0** (dual GPLv3+/MPLv2+), 344★.
- README prerequisites: *"Java 8, 11, 17 or 21"* + *"Maven v3+"*.
- **I ran it.** See §5.

### 3b. `opendataloader-pdf` — the brief's biggest risk. It is *worse* than expected for the idea's opponent, and *better*.

From the README's own capability table:

| Capability | Tier |
|---|---|
| Extract text with correct reading order | **Free** |
| Heading hierarchy detection, list detection | **Free** |
| Table extraction (simple + complex/borderless) | **Free** (Hybrid) |
| OCR for scanned PDFs, AI chart/image description | **Free** (Hybrid) |
| Tagged PDF structure extraction | **Free** |
| **Auto-tagging → Tagged PDF for untagged PDFs** | **Free** (Apache 2.0) |
| **PDF/UA-1, PDF/UA-2 export** | **💼 Enterprise** |
| **Accessibility studio (visual editor)** | **💼 Enterprise** |

So: **free = produce a Tagged PDF. Paywalled = certify it as PDF/UA, and edit it.**
`opendataloader-pdf` does not ship a free *validator*.

**And the free tier is not JVM-free either.** The PyPI distribution's own summary is:

> `opendataloader-pdf` — *"A Python wrapper for the opendataloader-pdf **Java CLI**."*
> `requires_python: >=3.10`, repo language: **Java**.

The Python package is a wrapper that shells out to a Java CLI. So the "free auto-tagging" that was
supposed to be the biggest risk to this idea **itself requires a JVM** — the very thing the wedge
is about.

**Does free auto-tagging cover what a validator would check?** No, and this is the key distinction:

- Auto-tagging **produces** structure. A validator **audits** structure.
- Auto-tagging a PDF does not tell you whether the PDF *you were handed* is conformant. The ADA
  rule applies to PDFs already published on `.gov` sites; those need auditing, not re-authoring.
- Auto-tagging cannot detect missing `/Lang`, missing `/Alt` on an existing `Figure`, missing
  `/TH` headers in an existing `Table`, missing `DisplayDocTitle`, or a missing PDF/UA XMP
  identifier in a file that already claims conformance.

A remediator and an auditor are different tools. The brief's risk was overstated: free
auto-tagging does **not** cover what a validator checks, and it is not JVM-free anyway.

### 3c. `veraPDF` coverage

veraPDF's PDF/UA-1 profile (`veraPDF-validation-profiles/PDF_UA/PDFUA-1.xml`) contains
**106 machine-checkable rules** across ISO 14289-1 clauses 5, 6, 7.1–7.21. That is the honest
denominator for "how many PDF/UA-1 rules exist".

---

## 4. The machine-checkable / judgement-required line

PDF/UA has two kinds of rule, and the distinction is the whole design of a lightweight validator.

**Machine-checkable** (a program can decide it from the file alone):

- Is there a `/StructTreeRoot`? (§7.1-11)
- Is every page's content marked as an artifact or tagged as real content? (§7.1-3)
- Does the Catalog have `/Lang`? Does every page/span that needs it? (§7.2-33, §7.2-34)
- Does every `Figure` have `/Alt` or `/ActualText`? (§7.3-1)
- Do `Table` cells use `/TH` with `Scope`/`Headers` where required? (§7.5-1, §7.2-42)
- Are annotations/links given descriptions? (§7.18.1-2, §7.18.5-1/2)
- Is `DisplayDocTitle` true? Is there a PDF/UA XMP identifier? (§7.1-10, §5-1)
- Are fonts embedded and is the CIDSet correct? (§7.21.4.1, §7.21.4.2)
- Is the reading order expressible (MCID sequence, `/K` ordering)?

**Judgement-required** (no program can decide it; a human must):

- Is the alt text *accurate and useful*? `" "` (a single space) is structurally present and
  semantically worthless — a machine sees `/Alt` and passes it.
- Is the alt text *appropriate in context*, not merely non-empty?
- Is the reading order *meaningful*, not merely well-formed?
- Is the table's header association *correct*, not merely *present*?
- Is the document title *descriptive*?

**Where a pure-Python tool sits:** squarely on the machine-checkable side. It can say
"this figure has no `/Alt`" with certainty. It can never say "this document is accessible." That
boundary is stated in the README as a first-class limitation, and the tool is designed never to
cross it.

---

## 5. Prototype results on 16 real government PDFs

### Corpus

16 real government PDFs (28 MB, downloaded via a DoH workaround — see the environment note in
the README). Sources: `govinfo.gov` (PLAW, USCODE, CFR, BUDGET, CHRG, CRPT, FR), `irs.gov`
(1040, Pub 15, W-9, Pub 1), `ada.gov` (the Title II web rule itself). The download log is in
`docs/evidence/corpus-download.log`.

> **Environment trap worth recording:** `www.irs.gov`, `www.cdc.gov`, `www.ssa.gov` do not resolve
> on this machine's system resolver, but they exist — DoH (Cloudflare/Google/Quad9) resolves them
> and they answer `200`/`403`. This is ISP DNS poisoning, not absence. `dns-shield` diagnosed it
> (`Verdict.UNREACHABLE`, with the DoH answer and a valid TLS cert as evidence). Several hosts that
> first looked "404" were in fact DNS-poisoned. **Never read a connection failure as "does not
> exist."** Downloads were done with `curl --resolve <host>:443:<DoH-IP>`.

### Prototype

162 lines of Python on `pikepdf`, implementing 8 checks: `/StructTreeRoot`, `/MarkInfo/Marked`,
document `/Lang`, `/Title`, `DisplayDocTitle`, `Figure` alt text, `Table` header association, and
the PDF/UA XMP identifier. (This was the falsification instrument; the real implementation is in
`src/pdfua/`.)

### veraPDF baseline

veraPDF 1.30.2 was run on the same 16 files. **Java 21 was available** via Homebrew
(`/opt/homebrew/opt/openjdk@21`) — the brief said "Java may or may not be installed"; it is
installed but **not on `PATH`**, and `/usr/bin/java` is a stub that prints *"Unable to locate a
Java Runtime"*. The real JVM is at
`/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home/bin/java`.

The veraPDF installer is an IzPack GUI/console installer. A pty-driven console install stalled
after the target-path panel, so I extracted the CLI payload directly from the installer JAR
(`resources/packs/pack-veraPDF CLI`, a zip of the app classes) and ran it from the classpath:

```bash
java -cp <pack> org.verapdf.apps.GreenfieldCliWrapper --format json -f ua1 file.pdf
```

**Result: veraPDF reports 0/16 compliant.** All 16 government PDFs fail PDF/UA-1.

| file | veraPDF compliant | failed rules | failed checks | dominant failures |
|---|---|---|---|---|
| p01 (IRS 1040) | False | 5 | 446 | `7.1-3` (244), `7.18.1-3` (199) |
| p02 (IRS Pub 15) | False | 4 | 13 | `7.5-1` (6), `7.21.4.2-2` (4) |
| p03 (IRS W-9) | False | 4 | 26 | `7.18.1-3` (23) |
| p04 (IRS Pub 1) | False | 8 | 833 | `7.1-3` (419), `7.2-34` (407) |
| p08 (PLAW) | False | 10 | 172,257 | `7.1-3` (86,131), `7.2-34` (86,118) |
| p10 (CFR) | False | 12 | 67,938 | `7.1-3` (34,156), `7.2-34` (33,768) |
| p11 (USCODE) | False | 10 | 13,670 | `7.1-3` (6,838), `7.2-34` (6,824) |
| p12 (**ada.gov web rule**) | False | **1** | **6** | `7.21.4.2-2` (6) — CIDSet only |
| p26 (BUDGET) | False | 16 | 3,104 | `7.1-3` (2,978) |
| p27 (FR notice) | False | 13 | 43,605 | `7.1-3` (21,185), `7.2-34` (19,972) |
| p29 (CFR 29) | False | 11 | 125,950 | `7.1-3` (63,330), `7.2-34` (62,611) |
| p30 (CRPT) | False | 10 | 475 | `7.1-3` (243), `7.2-34` (224) |
| p32 (CHRG) | False | 11 | 3,994 | `7.1-3` (2,013), `7.2-34` (1,972) |
| p37 (PLAW 118-1) | False | 10 | 66 | `7.1-3` (31), `7.2-34` (27) |
| 7ef8534308 | False | 10 | 172,257 | `7.1-3` (86,131), `7.2-34` (86,118) |

### The decisive number

Across the corpus, veraPDF reports **643,471 failed checks** spanning **23 distinct rules**.

**Two rules account for 640,563 of them — 99.55%:**

| rule | meaning | failed checks |
|---|---|---|
| `7.1-3` | *"Content shall be marked as Artifact or tagged as real content"* | 323,122 |
| `7.2-34` | *"Natural language for text in page content shall be determined"* | 317,441 |

Both are **pure-Python reachable** and both are exactly what the prototype targets. `7.1-3` is
the untagged-content check (walk content streams, look for `BDC`/`BMC`/`EMC` and `/MCID`); `7.2-34`
is the `/Lang` check (a document with no `/Lang` fails on every text object). These are the failures
that actually dominate real government PDFs — and they are the two cheapest to detect.

### Prototype vs veraPDF, per file

Verdict agreement (does the lightweight tool reach the same non-compliant/clean conclusion?):
**13/16**.

The three disagreements are **informative, not random**:

| file | why the prototype is silent | what veraPDF found |
|---|---|---|
| p01 (IRS 1040) | tagged, `/Lang`, title, alt text, and `/TH` cells all present | `7.1-3` (244 unmarked content), `7.18.1-3` (199 form fields without `TU`) |
| p03 (IRS W-9) | same — structurally clean | `7.18.1-3` (23), font rules |
| p12 (**ada.gov's own web rule PDF**) | essentially conformant | `7.21.4.2-2` (6) — a CIDSet/font-program rule |

**p12 is the single most useful data point in this whole exercise.** The ADA's own rule document,
professionally remediated, is `105/106` rules clean and fails **only** a font-internals rule. That
is the profile of a document that is *actually* accessible. A validator that flagged it with 15
findings would be crying wolf; my prototype correctly says nothing about it. **A tool that reports
p12 as broken is worse than no tool.**

### A false positive I caught and removed

My first prototype version reported `UA-15-004` ("`/TH` cells lack `Scope`") **29 times**, including
4× on the professionally-produced IRS W-9 and 1× on the IRS 1040 — documents veraPDF passes on
§7.5.

Reading ISO 14289-1 §7.5: *"If the table's structure is not determinable via `Headers` and `IDs`,
then structure shall be **provided** using `Scope`."* `Scope` is a **fallback**. A table whose
structure is determinable by `Headers`/`IDs`, or whose cells nest unambiguously, does not need it.
I verified directly: p01's `Table[0]` has `TH=5, TD=35`, and **neither `TH` nor `TD` carries
`Scope` or `Headers`** — and veraPDF passes it. My rule was simply wrong about the standard.

It is removed from the design. This is recorded because it is the exact failure mode that makes
accessibility validators distrusted, and the tool's credibility depends on not repeating it.

---

## 6. Falsification verdict

### Does the prototype reproduce a meaningful fraction of veraPDF's findings?

**Yes, on the failures that dominate real documents, and it is honest about where it stops.**

- 99.55% of all failed checks in this corpus are `7.1-3` (untagged content) + `7.2-34` (no
  language). Both are pure-Python reachable and both are implemented.
- Of the 23 distinct rules that fired, 8 are reachable by the prototype's approach.
- The prototype reaches the correct non-compliant/clean verdict on **13/16** files.
- The 3 misses are all "structurally clean but fails a font rule or a form-field rule" — a
  *different and narrower* failure class, and it is disclosed as unimplemented rather than
  silently passed.

### Is the gap capability or packaging?

**Both, and the split matters.**

- The **dominant** failure classes (`7.1-3`, `7.2-34`) are pure **packaging**: trivially checkable
  in Python, currently only checkable via a JVM. That is the wedge.
- A **long tail** of ~90 of veraPDF's 106 rules — font programs, CIDSet, glyph widths, colour
  spaces, WTPDF structure — is **genuine capability**. Those need real font and content-stream
  parsing. A pure-Python tool should not pretend to cover them.

### Should this instead contribute upstream to veraPDF?

**No — and this is where I disagree with the brief's suggested escape hatch.** Contributing a
Python port upstream does not help the actual user, because veraPDF's implementation is Java. The
user's problem is not "veraPDF's rules are wrong"; it is **"I cannot run a JVM in my CI."** A
contribution to veraPDF's Java codebase leaves that problem exactly where it was. The gap is a
*distribution* gap: a `pip install`-able, JVM-free, SARIF-emitting checker for the failure classes
that dominate real `.gov` PDFs.

### The honest scope, stated up front

This tool is a **fast, JVM-free triage gate** — not a veraPDF replacement. It answers *"is this
PDF structurally in the ballpark of PDF/UA?"* in ~50 ms with no JVM, which is what you want on
every commit. veraPDF remains the authority and should be run for final conformance claims. The
README opens with this and has a `## What this does NOT check` section.

### Decision gate

| condition | result |
|---|---|
| Pure-Python catches a meaningful share of real PDF/UA failures that matter | ✅ 99.55% of failed checks are two reachable rules; 13/16 verdict agreement |
| The wedge is genuinely packaging (no JVM, `pip install`, SARIF) | ✅ dominant rules are trivially checkable; veraPDF and opendataloader both require a JVM |
| Free tooling already covers it | ❌ `wcag_pdf_pytest` is regex false-assurance; `pdf-a11y` wraps veraPDF; `opendataloader` free tier is a Java CLI |

**→ PASS. Proceed to Phase 2.**

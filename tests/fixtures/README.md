# Test fixtures

**No PDF is committed to this repository.** Every fixture is built in code at
test time by [`build.py`](build.py), using `pikepdf`.

## Why generated, not committed

- **Auditability.** A fixture that is 40 lines of `pikepdf` calls can be read and
  verified. A committed binary cannot.
- **No rot.** A committed fixture can silently become something other than what
  its filename claims after a re-save by some other tool. A generated one cannot.
- **No binary in git.** Keeps clones small and diffs meaningful.

## The design rule

`valid_document()` satisfies **every implemented rule**. Each other builder
changes **exactly one thing** relative to it. This matters: if a builder changed
two things, a test for either rule could pass for the wrong reason.

`tests/test_rules_contract.py` enforces the contract from the other side — it
fails if a registered rule has no positive fixture, so a rule cannot be added
without a test that proves it fires.

## Fixtures

| Builder | Violates | Notes |
|---|---|---|
| `valid_document()` | nothing | the negative case for every rule |
| `untagged()` | `UA-01-005`, `UA-01-002` | no structure tree, no `/MarkInfo` |
| `marked_false()` | `UA-01-002` | tree present, `/Marked` false |
| `untagged_content()` | `UA-01-003` | text outside any `BDC`/`EMC` |
| `no_language()` | `UA-06-001` | catalog has no `/Lang` |
| `malformed_language()` | `UA-06-001` (warning) | `/Lang (english please)` |
| `no_title()` | `UA-07-001` | no `/Title`, no `dc:title` |
| `no_display_doc_title()` | `UA-07-002` | no `/ViewerPreferences` |
| `no_pdfua_identifier()` | `UA-28-004` | XMP present, no `pdfuaid:part` |
| `figure_without_alt()` | `UA-13-004` | `/Figure` with neither `/Alt` nor `/ActualText` |
| `figure_with_empty_alt()` | `UA-13-004` (heuristic) | `/Alt (   )` |
| `table_without_headers()` | `UA-15-003` | `/TD` cells, no `/TH` |
| `table_headers_without_association()` | `UA-15-003` (heuristic) | `/TH` with no `/Scope` |
| `link_without_description()` | `UA-18-005` | `/Link` with no `/Contents` |
| `annotation_without_description()` | `UA-18-001` | `/Text` with no `/Contents` |
| `unreadable()` | — | raw bytes, not a PDF |

## Downloaded documents

The real-document tests in `tests/test_real_documents.py` need a corpus that is
**not** committed, because these are third-party documents and they are large.
Reproduce it with:

```bash
python scripts/fetch_corpus.py --out corpus
PDFUA_CORPUS=corpus pytest tests/test_real_documents.py
```

The tests skip when no corpus is present, so a fresh clone is green offline.

> Some `.gov` hostnames do not resolve through a poisoned system resolver (see
> `docs/FALSIFICATION.md`). `fetch_corpus.py --doh` prints the `curl --resolve`
> command needed in that case. **A connection failure is never evidence that a
> document does not exist.**

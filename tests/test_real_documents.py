"""Tests against real government PDFs.

These run only when the corpus has been fetched (``scripts/fetch_corpus.py``),
because the PDFs are not committed — they are third-party documents, and several
hundred megabytes of them. When the corpus is absent the module skips, so a
clone with no network still has a green suite.

The assertions here encode the findings from ``docs/FALSIFICATION.md``. They are
regression tests for the *evidence*, not just the code: if a change makes this
tool stop detecting the failure class that dominates real documents, or makes it
start reporting a professionally-remediated document as broken, these fail.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from pdfua import Severity, validate

CORPUS_ENV = "PDFUA_CORPUS"
DEFAULT_CORPUS = Path(__file__).parent.parent / "corpus"


def _corpus_dir() -> Path | None:
    candidate = Path(os.environ.get(CORPUS_ENV, DEFAULT_CORPUS))
    if not candidate.is_dir():
        return None
    pdfs = sorted(candidate.glob("*.pdf"))
    return candidate if pdfs else None


CORPUS = _corpus_dir()
needs_corpus = pytest.mark.skipif(
    CORPUS is None,
    reason=f"no corpus; run scripts/fetch_corpus.py or set {CORPUS_ENV}",
)


def _pdfs() -> list[Path]:
    assert CORPUS is not None
    return sorted(CORPUS.glob("*.pdf"))


@needs_corpus
class TestRealDocuments:
    def test_every_corpus_file_is_analysable(self) -> None:
        """No real document crashes a rule; unreadable files are reported, not fatal."""
        from pdfua.errors import PdfuaError

        unreadable: list[str] = []
        for path in _pdfs():
            try:
                validate(str(path))
            except PdfuaError:
                unreadable.append(path.name)
        assert not unreadable, f"corpus files could not be parsed: {unreadable}"

    def test_untagged_documents_are_detected(self) -> None:
        """The dominant real-world failure must be caught.

        On the development corpus, 11 of 16 government PDFs have no structure
        tree at all. If this drops to zero, the traversal has regressed.
        """
        untagged = [
            p.name
            for p in _pdfs()
            if any(f.rule_id == "UA-01-005" for f in validate(str(p)).findings)
        ]
        assert len(untagged) >= 5, (
            f"expected several untagged government PDFs, found {len(untagged)}"
        )

    def test_missing_language_is_detected_on_untagged_documents(self) -> None:
        """UA-06-001 is the second-largest failure class; it must fire."""
        missing = [
            p.name
            for p in _pdfs()
            if any(f.rule_id == "UA-06-001" for f in validate(str(p)).findings)
        ]
        assert len(missing) >= 5, f"expected missing /Lang in several files, found {len(missing)}"

    def test_untagged_content_is_counted_on_tagged_documents(self) -> None:
        """UA-01-003 must fire on tagged files whose page content is unmarked.

        This is the pure-Python-reachable rule that tracked veraPDF's 7.1-3 at
        92-99.9% agreement during development.
        """
        counted = [
            p.name
            for p in _pdfs()
            if any(f.rule_id == "UA-01-003" for f in validate(str(p)).findings)
        ]
        assert counted, "no corpus file reported untagged page content"

    def test_professionally_remediated_document_is_not_reported_as_broken(self) -> None:
        """The tool must not cry wolf on a document that is essentially conformant.

        ``ada.gov``'s own Title II web-rule PDF is 105 of 106 rules clean under
        veraPDF — it fails only a CIDSet/font rule that this tool does not check.
        Reporting it as broken would be worse than reporting nothing, so it is
        asserted clean here. This is the strongest anti-false-positive test in
        the suite.
        """
        candidates = [p for p in _pdfs() if "web-rule" in p.name.lower() or p.name == "p12.pdf"]
        if not candidates:
            pytest.skip("the ada.gov web-rule PDF is not in this corpus")
        report = validate(str(candidates[0]))
        assert report.worst_severity() in (None, Severity.INFO, Severity.WARNING), (
            "the ada.gov web rule PDF was reported with errors: "
            + "; ".join(
                f"{f.rule_id}: {f.message}" for f in report.findings if f.severity is Severity.ERROR
            )
        )

    def test_reports_are_deterministic(self) -> None:
        """Two runs on the same file produce identical findings."""
        path = _pdfs()[0]
        first = validate(str(path)).to_dict()
        second = validate(str(path)).to_dict()
        first.pop("duration_ms", None)
        second.pop("duration_ms", None)
        assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)

    def test_no_rule_crashes_across_the_corpus(self) -> None:
        """Every rule either evaluates or explicitly skips; none fails silently."""
        for path in _pdfs():
            report = validate(str(path))
            for outcome in report.skipped:
                assert outcome.skipped_reason, f"{path.name}: {outcome.rule_id} skipped silently"

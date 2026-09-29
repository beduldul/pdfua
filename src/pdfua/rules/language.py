"""Language, title and metadata rules.

WCAG 2.1 SC 3.1.1 (Language of Page) is the criterion the ADA rule's
"WCAG 2.1 Level AA" requirement pulls in most often for PDFs, and it is the
second-largest failure class in real documents: a PDF with no ``/Lang`` fails
once per text object.
"""

from __future__ import annotations

from collections.abc import Iterable

from ..document import PdfDocument, is_well_formed_language
from ..model import Confidence, Finding, Location, Severity
from .base import Rule


class DocumentLanguageRule(Rule):
    """PDF/UA-1 §7.2 / WCAG 2.1 SC 3.1.1: the document language shall be set."""

    id = "UA-06-001"
    covers = (
        "7.2-33",
        "7.2-34",
    )
    title = "Document declares a natural language"
    severity = Severity.ERROR
    pdfua_clause = "7.2"
    wcag = ("3.1.1",)
    remediation = (
        "Set /Lang on the document catalog, e.g. /Lang (en-US). Use a BCP-47 "
        "tag. Screen readers pick a voice from this; without it they guess."
    )

    def check(self, doc: PdfDocument) -> Iterable[Finding]:
        if doc.lang is None:
            yield self.finding(
                "Catalog has no /Lang entry, so assistive technology cannot "
                "determine the document's natural language (WCAG 3.1.1).",
                location=Location(object_path="/Root/Lang"),
                evidence={"lang": "absent"},
            )
            return
        if not is_well_formed_language(doc.lang):
            yield self.finding(
                f"/Lang value {doc.lang!r} is not a well-formed BCP-47 language tag.",
                location=Location(object_path="/Root/Lang"),
                severity=Severity.WARNING,
                evidence={"lang": doc.lang},
            )


class DocumentTitleRule(Rule):
    """PDF/UA-1 §7.1 / WCAG 2.4.2: the document shall have a title."""

    id = "UA-07-001"
    covers = ("7.1-9",)
    title = "Document has a title"
    severity = Severity.WARNING
    confidence = Confidence.HEURISTIC
    pdfua_clause = "7.1"
    wcag = ("2.4.2",)
    remediation = (
        "Set /Title in the document information dictionary and the dc:title "
        "property in XMP. A screen reader announces the title when the document "
        "opens; an untitled PDF is announced by filename."
    )

    def check(self, doc: PdfDocument) -> Iterable[Finding]:
        title = doc.title
        if title is None or not title.strip():
            yield self.finding(
                "Document has no /Title, so assistive technology falls back to "
                "the file name (WCAG 2.4.2).",
                location=Location(object_path="/Info/Title"),
                evidence={"title": "absent"},
            )
        # A present title produces no finding. Emitting an informational
        # "a title exists" note on every clean document would make a clean run
        # non-empty and train users to ignore the output. Whether a title is
        # *descriptive* is not decidable here and is stated in the README, not
        # in the report.


class DisplayDocTitleRule(Rule):
    """PDF/UA-1 §7.1: ``/ViewerPreferences /DisplayDocTitle`` shall be true."""

    id = "UA-07-002"
    covers = ("7.1-10",)
    title = "Viewer is asked to show the document title"
    severity = Severity.WARNING
    pdfua_clause = "7.1"
    wcag = ("2.4.2",)
    remediation = (
        "Set /ViewerPreferences << /DisplayDocTitle true >> in the catalog. "
        "Without it, readers show the file name in their title bar even when a "
        "proper /Title exists."
    )

    def check(self, doc: PdfDocument) -> Iterable[Finding]:
        if not doc.display_doc_title:
            yield self.finding(
                "/ViewerPreferences/DisplayDocTitle is not true, so the viewer "
                "shows the file name instead of the document title.",
                location=Location(object_path="/Root/ViewerPreferences"),
                evidence={"display_doc_title": False},
            )


class PdfUaIdentifierRule(Rule):
    """PDF/UA-1 §5: conformance shall be declared in the XMP metadata."""

    id = "UA-28-004"
    covers = ("5-1",)
    title = "PDF/UA identification present in XMP"
    severity = Severity.WARNING
    pdfua_clause = "5"
    remediation = (
        "Add the PDF/UA identification extension schema to the XMP metadata: "
        "pdfuaid:part = 1 for PDF/UA-1. This is the machine-readable claim of "
        "conformance; its absence means the file does not claim PDF/UA."
    )

    def check(self, doc: PdfDocument) -> Iterable[Finding]:
        metadata = doc.xmp_metadata()
        if metadata is None:
            yield self.finding(
                "Document has no XMP metadata packet, so it cannot declare PDF/UA conformance.",
                location=Location(object_path="/Root/Metadata"),
                evidence={"xmp": "absent"},
            )
            return
        lowered = metadata.lower()
        if "pdfuaid" not in lowered and "pdf/ua" not in lowered:
            yield self.finding(
                "XMP metadata contains no PDF/UA identification "
                "(pdfuaid:part), so the file does not declare PDF/UA conformance.",
                location=Location(object_path="/Root/Metadata"),
                evidence={"xmp_pdfua_id": False},
            )

"""Rules for document-level tagging: is this file tagged at all?

These are the highest-yield rules in practice. On a 16-file corpus of real
``.gov`` PDFs, an untagged document produced veraPDF's ``7.1-3`` ("content
shall be marked as Artifact or tagged as real content") and ``7.2-34`` ("natural
language for text in page content shall be determined") thousands of times each,
because an untagged document fails those rules once per text object.
"""

from __future__ import annotations

from collections.abc import Iterable

from ..document import PdfDocument
from ..model import Finding, Location, Severity
from .base import Rule


class StructTreeRootRule(Rule):
    """PDF/UA-1 §7.1: the logical structure shall be described by a tree."""

    id = "UA-01-005"
    covers = ("7.1-11",)
    title = "Document has a structure tree"
    severity = Severity.ERROR
    pdfua_clause = "7.1"
    wcag = ("1.3.1",)
    remediation = (
        "Tag the document (Acrobat: Accessibility > Autotag Document, or "
        "remediate with a tool that writes /StructTreeRoot). A document with no "
        "structure tree cannot be navigated by assistive technology."
    )

    def check(self, doc: PdfDocument) -> Iterable[Finding]:
        if doc.struct_root is None:
            yield self.finding(
                "Document has no /StructTreeRoot: it is untagged, so no reading "
                "order, headings, tables or figure descriptions are conveyed to "
                "assistive technology.",
                location=Location(object_path="/Root"),
                evidence={"struct_tree_root": False},
            )


class MarkInfoRule(Rule):
    """PDF/UA-1 §6.2: the catalog shall contain ``/MarkInfo`` with ``/Marked true``."""

    id = "UA-01-002"
    covers = ("6.2-1",)
    title = "MarkInfo/Marked is true"
    severity = Severity.ERROR
    pdfua_clause = "6.2"
    wcag = ("1.3.1",)
    remediation = (
        "Set /MarkInfo << /Marked true >> in the document catalog. This is the "
        "flag that tells readers the document intends to be tagged."
    )

    def check(self, doc: PdfDocument) -> Iterable[Finding]:
        if not doc.marked:
            yield self.finding(
                "Catalog /MarkInfo is absent or /Marked is not true, so the file "
                "does not claim to be a tagged PDF.",
                location=Location(object_path="/Root/MarkInfo"),
                evidence={"marked": False},
            )


class UntaggedContentRule(Rule):
    """PDF/UA-1 §7.1: content shall be tagged as real content or as an artifact.

    Every text-showing operator outside a ``BDC``/``BMC`` … ``EMC`` sequence is
    neither, which is the single most common failure in real government PDFs.
    """

    id = "UA-01-003"
    covers = ("7.1-3",)
    title = "Page content is tagged or marked as artifact"
    severity = Severity.ERROR
    pdfua_clause = "7.1"
    wcag = ("1.3.1",)
    remediation = (
        "Wrap page content in marked-content sequences: real content inside "
        "/P, /H1, /Figure etc., and decoration (rules, headers, footers, page "
        "numbers) inside an /Artifact sequence."
    )

    #: Report at most this many offending pages individually, then summarise.
    max_reported_pages = 10

    def check(self, doc: PdfDocument) -> Iterable[Finding]:
        if doc.struct_root is None:
            # UA-01-005 already reports the untagged document; repeating it per
            # page would bury the real signal in noise.
            return
        offenders = []
        total_text = 0
        total_xobject = 0
        for content in doc.pages:
            if content.errors:
                yield self.finding(
                    "Could not analyse page content: " + "; ".join(content.errors),
                    location=Location(page=content.page_number),
                    severity=Severity.INFO,
                    evidence={"parse_error": True},
                )
                continue
            if content.unmarked.total == 0:
                continue
            total_text += content.unmarked.unmarked_text_operators
            total_xobject += content.unmarked.unmarked_xobjects
            offenders.append(content)

        for content in offenders[: self.max_reported_pages]:
            parts = []
            if content.unmarked.unmarked_text_operators:
                parts.append(f"{content.unmarked.unmarked_text_operators} text-showing operator(s)")
            if content.unmarked.unmarked_xobjects:
                parts.append(f"{content.unmarked.unmarked_xobjects} image/form paint(s)")
            yield self.finding(
                "Content is neither tagged nor marked as an artifact: "
                + " and ".join(parts)
                + " occur outside any marked-content sequence.",
                location=Location(page=content.page_number),
                evidence={
                    "unmarked_text_operators": content.unmarked.unmarked_text_operators,
                    "unmarked_xobjects": content.unmarked.unmarked_xobjects,
                },
            )
        if len(offenders) > self.max_reported_pages:
            remaining = offenders[self.max_reported_pages :]
            yield self.finding(
                f"{len(remaining)} further page(s) also contain untagged content "
                f"(pages {remaining[0].page_number}-{remaining[-1].page_number}).",
                location=Location(page=remaining[0].page_number),
                severity=Severity.INFO,
                evidence={
                    "additional_pages": len(remaining),
                    "total_unmarked_text_operators": total_text,
                    "total_unmarked_xobjects": total_xobject,
                },
            )

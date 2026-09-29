"""Rules that trace to WCAG 2.1 criteria via annotations.

PDF/UA-1 §7.18 requires every annotation to be either a real tagged element or
an artifact, and requires links to carry an alternate description. These are the
WCAG-facing checks that a pure-Python tool can decide with certainty.
"""

from __future__ import annotations

from collections.abc import Iterable

import pikepdf

from ..document import PdfDocument
from ..model import Finding, Location, Severity
from .base import Rule


class LinkDescriptionRule(Rule):
    """PDF/UA-1 §7.18.5 / WCAG 2.4.4: links need a description.

    A link annotation must carry a ``/Contents`` alternate description, or the
    tagged link element it belongs to must carry one.
    """

    id = "UA-18-005"
    covers = (
        "7.18.5-1",
        "7.18.5-2",
    )
    title = "Link annotations have an alternate description"
    severity = Severity.WARNING
    pdfua_clause = "7.18.5"
    wcag = ("2.4.4",)
    remediation = (
        "Give each /Link annotation a /Contents entry describing the "
        "destination, or put /Alt on the tagged /Link element. 'Click here' is "
        "technically a description and is not sufficient in substance — this "
        "rule checks presence only."
    )

    def check(self, doc: PdfDocument) -> Iterable[Finding]:
        described = self._tagged_link_descriptions(doc)
        for page_number, annot in self._annotations(doc, "/Link"):
            contents = annot.get("/Contents")
            has_contents = contents is not None and str(contents).strip() != ""
            if not has_contents and not described:
                yield self.finding(
                    "Link annotation has no /Contents description and no "
                    "corresponding tagged /Link element with alternative text.",
                    location=Location(page=page_number, object_path="/Annots"),
                    evidence={"contents": "absent", "tagged_link_alt": False},
                )

    @staticmethod
    def _tagged_link_descriptions(doc: PdfDocument) -> bool:
        return any(
            (e.alt or "").strip() or (e.actual_text or "").strip()
            for e in doc.elements_with_role("/Link")
        )

    @staticmethod
    def _annotations(doc: PdfDocument, subtype: str) -> Iterable[tuple[int, pikepdf.Dictionary]]:
        for page_number, page in enumerate(doc._pdf.pages, start=1):
            annots = page.obj.get("/Annots")
            if annots is None:
                continue
            try:
                entries = list(annots)
            except TypeError:
                continue
            for entry in entries:
                if isinstance(entry, pikepdf.Dictionary) and entry.get("/Subtype") == subtype:
                    yield page_number, entry


class AnnotationDescriptionRule(Rule):
    """PDF/UA-1 §7.18.1: non-widget annotations need an alternate description.

    Widget annotations (form fields) are excluded here because their
    description requirement is governed by ``/TU`` and is checked separately.
    """

    id = "UA-18-001"
    covers = ("7.18.1-2",)
    title = "Annotations have an alternate description"
    severity = Severity.WARNING
    pdfua_clause = "7.18.1"
    wcag = ("1.1.1", "4.1.2")
    remediation = (
        "Give each annotation a /Contents description. An annotation with no "
        "description is announced by type only ('link', 'note') with no "
        "indication of what it does."
    )

    #: Subtypes that carry their own description mechanism, or that are not
    #: presented to the user as content.
    _exempt = frozenset({"/Widget", "/Link", "/Popup"})

    def check(self, doc: PdfDocument) -> Iterable[Finding]:
        for page_number, annot in self._annotations(doc):
            subtype = annot.get("/Subtype")
            if subtype is None or str(subtype) in self._exempt:
                continue
            contents = annot.get("/Contents")
            if contents is None or str(contents).strip() == "":
                yield self.finding(
                    f"Annotation of type {subtype} has no /Contents description.",
                    location=Location(page=page_number, object_path=str(subtype)),
                    evidence={"subtype": str(subtype), "contents": "absent"},
                )

    @staticmethod
    def _annotations(doc: PdfDocument) -> Iterable[tuple[int, pikepdf.Dictionary]]:
        for page_number, page in enumerate(doc._pdf.pages, start=1):
            annots = page.obj.get("/Annots")
            if annots is None:
                continue
            try:
                entries = list(annots)
            except TypeError:
                continue
            for entry in entries:
                if isinstance(entry, pikepdf.Dictionary):
                    yield page_number, entry

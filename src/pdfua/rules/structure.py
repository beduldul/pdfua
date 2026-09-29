"""Structure-element rules: figures, tables, and heading nesting.

Design note on table rules — read before editing.

An earlier version of this check reported "/TH cells lack Scope" on documents
that veraPDF passes. That was wrong about the standard. ISO 14289-1 §7.5 says
``Scope`` is required only *if the table's structure is not determinable via
``Headers`` and ``IDs``*. ``Scope`` is a fallback, not a universal requirement.
On the corpus used to develop this package, the IRS W-9 has ``/TH`` cells with
neither ``Scope`` nor ``Headers`` and is perfectly valid.

The lesson is encoded below: this module never asserts that a table is *bad*.
It asserts only that a table is *not determinable* — no header cells at all, or
no association mechanism of any kind. Anything subtler is left to a human, and
the finding says so.
"""

from __future__ import annotations

from collections.abc import Iterable

import pikepdf

from ..document import PdfDocument, StructElement, as_integer
from ..model import Confidence, Finding, Location, Severity
from .base import Rule


class FigureAltTextRule(Rule):
    """PDF/UA-1 §7.3: figures shall have an alternative representation."""

    id = "UA-13-004"
    covers = ("7.3-1",)
    title = "Figure elements have alternative text"
    severity = Severity.ERROR
    pdfua_clause = "7.3"
    wcag = ("1.1.1",)
    remediation = (
        "Give every /Figure either /Alt (a short description) or /ActualText. "
        "For decorative images, mark the content as an artifact instead of "
        "tagging it as a figure."
    )

    def check(self, doc: PdfDocument) -> Iterable[Finding]:
        for figure in doc.elements_with_role("/Figure"):
            alt = figure.alt
            actual = figure.actual_text
            if alt is None and actual is None:
                yield self.finding(
                    "Figure has neither /Alt nor /ActualText, so it is invisible "
                    "to a screen reader (WCAG 1.1.1).",
                    location=Location(
                        page=figure.page,
                        struct_role="/Figure",
                        object_path="/StructTreeRoot",
                    ),
                    evidence={"alt": "absent", "actual_text": "absent"},
                )
            elif alt is not None and not alt.strip():
                # Stricter than the letter of §7.3, which only requires that an
                # alternative representation be *present*. veraPDF passes a
                # whitespace /Alt. It is reported as a warning with heuristic
                # confidence precisely because it is a judgement call, not a
                # rule violation, and calling it an error would make this tool
                # stricter than the reference validator.
                yield self.finding(
                    "Figure has an /Alt entry that is empty or whitespace only. "
                    "The entry is present, so §7.3 and veraPDF accept it, but it "
                    "conveys nothing to a screen reader (WCAG 1.1.1 intent). "
                    "This finding is stricter than the letter of the standard.",
                    location=Location(page=figure.page, struct_role="/Figure"),
                    severity=Severity.WARNING,
                    confidence=Confidence.HEURISTIC,
                    evidence={"alt_length": len(alt)},
                )


class TableHeaderRule(Rule):
    """PDF/UA-1 §7.5: table structure shall be determinable.

    Fires only when a table has data cells but no header cells, or when header
    cells exist but nothing associates them with data cells. A table that uses
    ``Scope``, or ``Headers``/``IDs``, or that has a single unambiguous cell per
    row, is left alone.
    """

    id = "UA-15-003"
    covers = (
        "7.5-1",
        "7.2-42",
    )
    title = "Table structure is determinable"
    severity = Severity.ERROR
    pdfua_clause = "7.5"
    wcag = ("1.3.1",)
    remediation = (
        "Mark header cells as /TH and associate them with data cells using "
        "either /Scope (Column, Row, Both) or /Headers and /IDs. Where a table "
        "is purely presentational, tag it as an artifact instead of a /Table."
    )

    def check(self, doc: PdfDocument) -> Iterable[Finding]:
        for table in doc.elements_with_role("/Table"):
            rows = doc.table_rows(table)
            if not rows:
                yield self.finding(
                    "Table element contains no /TR rows, so its structure cannot be determined.",
                    location=Location(page=table.page, struct_role="/Table"),
                    severity=Severity.WARNING,
                    evidence={"rows": 0},
                )
                continue

            headers = 0
            data = 0
            associated = 0
            for row in rows:
                for cell in doc.table_cells(row):
                    if cell.role == "/TH":
                        headers += 1
                        if cell.has_scope or cell.has_headers:
                            associated += 1
                    else:
                        data += 1

            if data == 0:
                continue
            if headers == 0:
                yield self.finding(
                    f"Table has {data} data cell(s) and no header cell (/TH), so "
                    "nothing identifies what the columns mean.",
                    location=Location(page=table.page, struct_role="/Table"),
                    evidence={"data_cells": data, "header_cells": 0, "rows": len(rows)},
                )
            elif associated == 0:
                yield self.finding(
                    f"Table has {headers} header cell(s) but none carry /Scope or "
                    "/Headers, so the association between headers and the "
                    f"{data} data cell(s) is not machine-determinable. If the "
                    "structure is unambiguous by cell position this may be "
                    "acceptable — a human should confirm.",
                    location=Location(page=table.page, struct_role="/Table"),
                    severity=Severity.WARNING,
                    confidence=Confidence.HEURISTIC,
                    evidence={
                        "header_cells": headers,
                        "data_cells": data,
                        "associated_headers": 0,
                    },
                )


class EmptyHeadingRule(Rule):
    """PDF/UA-1 §7.4: heading elements shall not be empty.

    An empty heading is a structural defect with a certain fix, unlike the
    question of whether a heading's text is *well chosen*.
    """

    id = "UA-14-001"
    covers = (
        "7.4.2-1",
        "7.4.4-1",
    )
    title = "Heading elements are not empty"
    severity = Severity.WARNING
    pdfua_clause = "7.4"
    wcag = ("1.3.1", "2.4.6")
    remediation = (
        "Remove the empty heading element, or give it content. An empty heading "
        "appears in a screen reader's heading list as a blank entry."
    )

    def check(self, doc: PdfDocument) -> Iterable[Finding]:
        for element in doc.struct_elements:
            role = element.role or ""
            is_heading = len(role) == 3 and role.startswith("/H") and role[2].isdigit()
            if is_heading and not self._has_text(element):
                yield self.finding(
                    f"Empty heading element {role}.",
                    location=Location(page=element.page, struct_role=role),
                    evidence={"role": role},
                )

    @staticmethod
    def _has_text(element: StructElement) -> bool:
        """True if the element or any descendant marks real page content.

        A heading's text lives in content items, not in the structure tree: the
        ``/K`` of a ``/Span`` under an ``/H1`` is an ``/MCID`` integer, or an
        array of them, or a ``/MCR`` dictionary. Checking only for a bare integer
        ``/K`` reports every real heading as empty — which is what an earlier
        version of this rule did, flagging 81 headings in a correctly tagged IRS
        publication. The check must descend through both arrays and nested
        structure elements.
        """
        return EmptyHeadingRule._marks_content(element.obj)

    @staticmethod
    def _marks_content(node: object) -> bool:
        """True if ``node``'s ``/K`` chain reaches at least one content item."""
        if not isinstance(node, pikepdf.Dictionary):
            return False
        kid = node.get("/K")
        if kid is None:
            return False
        # A content item is a numeric /MCID. pikepdf models "is this a number?"
        # as Object.is_integer rather than an int subclass, so that predicate is
        # what decides it.
        if as_integer(kid) is not None:
            return True
        if isinstance(kid, pikepdf.Array):
            return any(
                as_integer(item) is not None or EmptyHeadingRule._marks_content(item)
                for item in kid
            )
        if isinstance(kid, pikepdf.Dictionary):
            if kid.get("/Type") == pikepdf.Name("/MCR"):
                return True
            return EmptyHeadingRule._marks_content(kid)
        return False

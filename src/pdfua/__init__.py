"""pdfua — check the machine-checkable subset of PDF/UA-1 without a JVM.

Quick start::

    from pdfua import validate

    report = validate("document.pdf")
    print(report.exit_code)
    for finding in report.findings:
        print(finding.rule_id, finding.severity.name, finding.message)

This library checks a subset of PDF/UA-1 (ISO 14289-1) and the WCAG 2.1
criteria that are decidable from the PDF alone. It does not certify
conformance. See :func:`pdfua.catalog.coverage` for what is implemented.
"""

from __future__ import annotations

from .catalog import Coverage, coverage, describe_rules
from .document import PdfDocument
from .errors import PdfuaError, RuleSelectionError, UnreadableDocumentError
from .model import Confidence, Finding, Location, Report, Severity
from .rules import default_registry
from .validator import Validator, ValidatorOptions, validate

__version__ = "0.1.3"

__all__ = [
    "Confidence",
    "Coverage",
    "Finding",
    "Location",
    "PdfDocument",
    "PdfuaError",
    "Report",
    "RuleSelectionError",
    "Severity",
    "UnreadableDocumentError",
    "Validator",
    "ValidatorOptions",
    "__version__",
    "coverage",
    "default_registry",
    "describe_rules",
    "validate",
]

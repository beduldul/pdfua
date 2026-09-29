"""Exception types for pdfua."""

from __future__ import annotations


class PdfuaError(Exception):
    """Base class for every error this package raises deliberately."""


class UnreadableDocumentError(PdfuaError):
    """The file could not be opened or parsed as a PDF."""


class RuleSelectionError(PdfuaError):
    """A rule selector matched nothing, or a rule id was unknown."""


class ConfigurationError(PdfuaError):
    """The caller supplied an invalid option."""

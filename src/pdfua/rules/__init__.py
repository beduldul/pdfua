"""The set of rules this package implements, in report order."""

from __future__ import annotations

from .base import Rule, RuleRegistry
from .language import (
    DisplayDocTitleRule,
    DocumentLanguageRule,
    DocumentTitleRule,
    PdfUaIdentifierRule,
)
from .structure import EmptyHeadingRule, FigureAltTextRule, TableHeaderRule
from .tagging import MarkInfoRule, StructTreeRootRule, UntaggedContentRule
from .wcag import AnnotationDescriptionRule, LinkDescriptionRule

#: Rules whose failures dominate real documents, ordered so the report leads
#: with the most consequential finding rather than the first discovered.
ALL_RULES: tuple[Rule, ...] = (
    StructTreeRootRule(),
    MarkInfoRule(),
    UntaggedContentRule(),
    DocumentLanguageRule(),
    FigureAltTextRule(),
    TableHeaderRule(),
    LinkDescriptionRule(),
    AnnotationDescriptionRule(),
    EmptyHeadingRule(),
    DocumentTitleRule(),
    DisplayDocTitleRule(),
    PdfUaIdentifierRule(),
)


def default_registry() -> RuleRegistry:
    """Return the registry containing every implemented rule."""
    return RuleRegistry(ALL_RULES)


__all__ = ["ALL_RULES", "Rule", "RuleRegistry", "default_registry"]

"""Rule interface and the registry that drives the CLI.

Rules are deliberately tiny and independent: each one declares its identity and
returns findings. They never mutate the document and never call each other.
"""

from __future__ import annotations

import abc
from collections.abc import Iterable, Iterator, Sequence
from typing import TYPE_CHECKING

from ..model import Confidence, Finding, Location, Severity

if TYPE_CHECKING:
    from ..document import PdfDocument


class Rule(abc.ABC):
    """One machine-checkable PDF/UA rule.

    Subclasses set the class attributes and implement :meth:`check`.
    """

    id: str
    title: str
    severity: Severity
    confidence: Confidence = Confidence.CERTAIN
    pdfua_clause: str | None = None
    wcag: tuple[str, ...] = ()
    remediation: str = ""

    #: The exact PDF/UA-1 rule identifiers (``clause``-``test``, as enumerated in
    #: the public validation profile) that this check decides. Empty means the
    #: check does not correspond to a single profile rule, and it is counted as
    #: covering nothing — see :mod:`pdfua.catalog`.
    covers: tuple[str, ...] = ()

    def finding(
        self,
        message: str,
        *,
        location: Location | None = None,
        severity: Severity | None = None,
        confidence: Confidence | None = None,
        evidence: dict[str, str | int | float | bool] | None = None,
    ) -> Finding:
        """Build a :class:`Finding` carrying this rule's identity."""
        return Finding(
            rule_id=self.id,
            severity=severity or self.severity,
            message=message,
            location=location or Location(),
            confidence=confidence or self.confidence,
            pdfua_clause=self.pdfua_clause,
            wcag=self.wcag,
            remediation=self.remediation or None,
            evidence=evidence or {},
        )

    @abc.abstractmethod
    def check(self, doc: PdfDocument) -> Iterable[Finding]:
        """Return every finding this rule produces for ``doc``.

        Implementations must not raise for malformed input: a rule that cannot
        evaluate the document should return a finding explaining that, not
        crash the run.
        """
        raise NotImplementedError


class RuleRegistry:
    """An ordered, name-addressable collection of rules."""

    def __init__(self, rules: Sequence[Rule]) -> None:
        self._rules: tuple[Rule, ...] = tuple(rules)
        seen: set[str] = set()
        for rule in self._rules:
            if rule.id in seen:
                raise ValueError(f"duplicate rule id: {rule.id}")
            seen.add(rule.id)

    def __iter__(self) -> Iterator[Rule]:
        return iter(self._rules)

    def __len__(self) -> int:
        return len(self._rules)

    def ids(self) -> tuple[str, ...]:
        return tuple(r.id for r in self._rules)

    def select(self, patterns: Sequence[str] | None) -> RuleRegistry:
        """Return a registry containing only rules matching ``patterns``.

        A pattern matches by exact ID or by prefix (``UA-01`` selects every
        ``UA-01-*`` rule). An empty or ``None`` selection returns everything.

        Raises:
            ValueError: if a pattern matches no rule, so a typo fails loudly
                instead of silently validating nothing.
        """
        if not patterns:
            return self
        chosen: list[Rule] = []
        unmatched: list[str] = []
        for pattern in patterns:
            hits = [r for r in self._rules if r.id == pattern or r.id.startswith(f"{pattern}-")]
            if not hits:
                unmatched.append(pattern)
            for hit in hits:
                if hit not in chosen:
                    chosen.append(hit)
        if unmatched:
            raise ValueError(
                "no rule matches: "
                + ", ".join(sorted(unmatched))
                + f" (known ids: {', '.join(self.ids())})"
            )
        return RuleRegistry(chosen)

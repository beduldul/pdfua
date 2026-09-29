"""The PDF/UA-1 rule catalogue, and coverage accounting over it.

This module is named ``catalog`` rather than ``coverage`` deliberately: the
package exports a ``coverage()`` function as its public API, and a module of the
same name would shadow it, so ``pdfua.coverage`` would sometimes be a function
and sometimes a module depending on import order. ``pdfua.catalog.coverage()``
and ``from pdfua import coverage`` both work and never collide.

Coverage accounting: how many PDF/UA-1 rules this tool actually checks.

The point of this module is honesty, and honesty here is subtler than it looks.

A validator that reports "PASS" is making an implicit claim about everything it
did not check. The obvious way to quantify that is per ISO clause: "we cover
clauses 5, 6.2, 7.1, 7.2, …". That measure is *misleading*, and this module
rejects it. Clause 7.2 contains **41** distinct rules; implementing one rule that
mentions clause 7.2 does not make the other forty checked. Reporting "7.2: 41/41"
because of a single `/Lang` check would be exactly the false comfort this project
exists to avoid.

Coverage is therefore counted at **rule granularity**: each implemented rule
declares, via :attr:`Rule.covers`, the exact set of PDF/UA-1 rule identifiers
(``clause``-``test``) it decides. The union of those sets is the numerator; the
106 identifiers in the bundled catalogue are the denominator. A rule that
declares no identifier — because its check does not correspond to a single
profile rule — contributes nothing, and says so.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

from .rules import RuleRegistry, default_registry

#: Number of machine-checkable rules in the PDF/UA-1 (ISO 14289-1) profile
#: published by veraPDF. This is the denominator used throughout the README and
#: the CLI. It is asserted in tests against the bundled identifier list, so it
#: cannot silently drift.
PDFUA1_TOTAL_RULES = 106


@dataclass(frozen=True, slots=True)
class RuleInfo:
    """Public description of one implemented rule."""

    id: str
    title: str
    severity: str
    confidence: str
    pdfua_clause: str | None
    wcag: tuple[str, ...]
    covers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Coverage:
    """How much of PDF/UA-1 this build checks, counted at rule granularity."""

    covered: int
    total: int
    implemented_rules: int
    partial: bool = False

    @property
    def fraction(self) -> float:
        return self.covered / self.total if self.total else 0.0

    def summary(self) -> str:
        return (
            f"{self.covered} of {self.total} PDF/UA-1 rules "
            f"({self.fraction:.0%}) across {self.implemented_rules} implemented checks"
        )


@lru_cache(maxsize=1)
def pdfua1_rule_identifiers() -> tuple[Mapping[str, str], ...]:
    """Return the clause/test/object identifiers of every PDF/UA-1 rule.

    The data file contains identifiers only — clause number, test number, and
    the name of the validation object. It deliberately does not reproduce the
    descriptive text of any validation profile, which belongs to its authors.
    """
    text = resources.files("pdfua.data").joinpath("pdfua1_rules.json").read_text("utf-8")
    payload = json.loads(text)
    rules = payload["rules"]
    if not isinstance(rules, list):
        raise ValueError("bundled rule catalogue is malformed")
    return tuple(rules)


def _identifier(entry: Mapping[str, str]) -> str:
    return f"{entry['clause']}-{entry['test']}"


@lru_cache(maxsize=1)
def _all_identifiers() -> frozenset[str]:
    return frozenset(_identifier(e) for e in pdfua1_rule_identifiers())


def coverage(registry: RuleRegistry | None = None) -> Coverage:
    """Return the rule-granularity coverage of ``registry``.

    Unknown identifiers declared by a rule are counted in the numerator only if
    they exist in the bundled catalogue; a typo in ``covers`` therefore lowers
    the reported coverage rather than inflating it. Tests assert that every
    declared identifier is real.
    """
    reg = registry if registry is not None else default_registry()
    known = _all_identifiers()
    declared: set[str] = set()
    for rule in reg:
        declared.update(i for i in rule.covers if i in known)
    return Coverage(
        covered=len(declared),
        total=PDFUA1_TOTAL_RULES,
        implemented_rules=len(reg),
    )


def describe_rules(registry: RuleRegistry | None = None) -> tuple[RuleInfo, ...]:
    """Return a public description of every rule in ``registry``."""
    reg = registry if registry is not None else default_registry()
    return tuple(
        RuleInfo(
            id=r.id,
            title=r.title,
            severity=r.severity.name.lower(),
            confidence=r.confidence.value,
            pdfua_clause=r.pdfua_clause,
            wcag=r.wcag,
            covers=r.covers,
        )
        for r in reg
    )


def unchecked_rules(registry: RuleRegistry | None = None) -> tuple[Mapping[str, str], ...]:
    """Return the PDF/UA-1 rules with no implemented check.

    This is the honest "what is missing" list, at rule granularity. It is the
    list the README's "What this does NOT check" section is built from.
    """
    reg = registry if registry is not None else default_registry()
    covered = {i for rule in reg for i in rule.covers}
    return tuple(e for e in pdfua1_rule_identifiers() if _identifier(e) not in covered)


def clause_summary(
    registry: RuleRegistry | None = None,
) -> tuple[tuple[str, int, int], ...]:
    """Return ``(clause, covered, total)`` per clause, at rule granularity.

    ``total`` is the number of PDF/UA-1 rules in that clause and ``covered`` is
    how many of them this tool decides. Both numbers are real; neither is
    inferred from the presence of a single check.
    """
    reg = registry if registry is not None else default_registry()
    covered_ids = {i for rule in reg for i in rule.covers}

    counts: dict[str, list[int]] = {}
    for entry in pdfua1_rule_identifiers():
        clause = str(entry["clause"])
        bucket = counts.setdefault(clause, [0, 0])
        bucket[1] += 1
        if _identifier(entry) in covered_ids:
            bucket[0] += 1

    def sort_key(item: tuple[str, list[int]]) -> tuple[int, ...]:
        return tuple(int(p) for p in item[0].split(".") if p.isdigit())

    return tuple(
        (clause, checked, total)
        for clause, (checked, total) in sorted(counts.items(), key=sort_key)
    )


def uncovered_clause_rules(
    registry: RuleRegistry | None = None,
) -> Sequence[Mapping[str, str]]:
    """Alias for :func:`unchecked_rules`, kept for readability at call sites."""
    return unchecked_rules(registry)

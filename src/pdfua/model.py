"""Typed result model for pdfua findings.

Every value that crosses the API boundary is a frozen dataclass or an enum.
No bare ``Any`` appears in this module or anywhere else in the package.
"""

from __future__ import annotations

import enum
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field


class Severity(enum.IntEnum):
    """Finding severity, ordered so that comparisons and exit codes are trivial.

    ``IntEnum`` is used deliberately: ``max(severities)`` is the worst severity,
    and the integer value is the process exit code.
    """

    INFO = 0
    WARNING = 1
    ERROR = 2

    @classmethod
    def from_name(cls, name: str) -> Severity:
        """Parse a case-insensitive severity name.

        Raises:
            ValueError: if ``name`` is not a known severity.
        """
        try:
            return cls[name.strip().upper()]
        except KeyError:
            valid = ", ".join(s.name.lower() for s in cls)
            raise ValueError(f"unknown severity {name!r}; expected one of: {valid}") from None


class Confidence(enum.Enum):
    """How much weight a finding can bear.

    ``CERTAIN`` means the rule decided it from the file alone, with no
    interpretation. ``HEURISTIC`` means the rule narrows the question but a
    human still has to look. Only ``CERTAIN`` findings should fail a build by
    default; see ``--min-confidence``.
    """

    CERTAIN = "certain"
    HEURISTIC = "heuristic"


@dataclass(frozen=True, slots=True)
class Location:
    """Where in the PDF a finding applies.

    All fields are optional because different rules can localise differently:
    a document-level rule sets only ``object_path``; a page rule sets ``page``.
    """

    page: int | None = None
    object_path: str | None = None
    struct_role: str | None = None
    mcids: tuple[int, ...] = ()

    def describe(self) -> str:
        """Render a short human-readable location, e.g. ``page 3 (/Figure)``."""
        parts: list[str] = []
        if self.page is not None:
            parts.append(f"page {self.page}")
        if self.struct_role:
            parts.append(self.struct_role)
        if self.object_path:
            parts.append(self.object_path)
        if self.mcids:
            shown = ", ".join(str(m) for m in self.mcids[:4])
            more = "" if len(self.mcids) <= 4 else f", +{len(self.mcids) - 4} more"
            parts.append(f"MCID {shown}{more}")
        return " ".join(parts) if parts else "document"


@dataclass(frozen=True, slots=True)
class Finding:
    """A single rule violation, or an explicit "could not check" notice.

    A rule that cannot evaluate a file must emit a ``SKIP`` finding rather than
    silently passing. Silence is indistinguishable from success, and that is
    the failure mode this project exists to avoid.
    """

    rule_id: str
    severity: Severity
    message: str
    location: Location = field(default_factory=Location)
    confidence: Confidence = Confidence.CERTAIN
    pdfua_clause: str | None = None
    wcag: tuple[str, ...] = ()
    remediation: str | None = None
    evidence: Mapping[str, str | int | float | bool] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serialisable mapping."""
        return {
            "rule_id": self.rule_id,
            "severity": self.severity.name.lower(),
            "confidence": self.confidence.value,
            "message": self.message,
            "location": self.location.describe(),
            "page": self.location.page,
            "pdfua_clause": self.pdfua_clause,
            "wcag": list(self.wcag),
            "remediation": self.remediation,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True, slots=True)
class RuleOutcome:
    """The result of running one rule against one document."""

    rule_id: str
    findings: tuple[Finding, ...] = ()
    skipped_reason: str | None = None
    duration_ms: float = 0.0

    @property
    def skipped(self) -> bool:
        return self.skipped_reason is not None


@dataclass(frozen=True, slots=True)
class Report:
    """The complete result of validating one document."""

    path: str
    outcomes: tuple[RuleOutcome, ...]
    pdfua_version: str = "PDF/UA-1"
    duration_ms: float = 0.0

    @property
    def findings(self) -> tuple[Finding, ...]:
        return tuple(f for o in self.outcomes for f in o.findings)

    @property
    def skipped(self) -> tuple[RuleOutcome, ...]:
        return tuple(o for o in self.outcomes if o.skipped)

    def worst_severity(self) -> Severity | None:
        """Return the highest severity present, or ``None`` if the file is clean."""
        found = [f.severity for f in self.findings]
        return max(found) if found else None

    @property
    def exit_code(self) -> int:
        """Exit code ordered by severity: 0 clean, 1 info, 2 warning, 3 error."""
        worst = self.worst_severity()
        return 0 if worst is None else int(worst) + 1

    def count_by_severity(self) -> Mapping[Severity, int]:
        counts = dict.fromkeys(Severity, 0)
        for f in self.findings:
            counts[f.severity] += 1
        return counts

    def to_dict(self) -> dict[str, object]:
        counts = self.count_by_severity()
        return {
            "file": self.path,
            "pdfua_version": self.pdfua_version,
            "exit_code": self.exit_code,
            "duration_ms": round(self.duration_ms, 2),
            "summary": {
                "findings": len(self.findings),
                "errors": counts[Severity.ERROR],
                "warnings": counts[Severity.WARNING],
                "info": counts[Severity.INFO],
                "rules_run": len(self.outcomes) - len(self.skipped),
                "rules_skipped": len(self.skipped),
            },
            "findings": [f.to_dict() for f in self.findings],
            "skipped": [{"rule_id": o.rule_id, "reason": o.skipped_reason} for o in self.skipped],
        }


def filter_findings(
    findings: Iterable[Finding],
    *,
    min_severity: Severity | None = None,
    min_confidence: Confidence | None = None,
    only_rules: Sequence[str] | None = None,
) -> tuple[Finding, ...]:
    """Return the findings that pass every supplied filter.

    Filters are applied conjunctively. ``only_rules`` matches rule IDs by exact
    string or by prefix (``"UA-01"`` selects ``UA-01-002`` and ``UA-01-005``).
    """
    out: list[Finding] = []
    for f in findings:
        if min_severity is not None and f.severity < min_severity:
            continue
        if min_confidence is Confidence.CERTAIN and f.confidence is not Confidence.CERTAIN:
            continue
        if only_rules is not None and not any(
            f.rule_id == r or f.rule_id.startswith(f"{r}-") for r in only_rules
        ):
            continue
        out.append(f)
    return tuple(out)

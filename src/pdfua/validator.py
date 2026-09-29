"""The validation engine: run rules over a document and collect a report."""

from __future__ import annotations

import time
from dataclasses import dataclass

from .catalog import Coverage, coverage
from .document import PdfDocument
from .errors import PdfuaError
from .model import Report, RuleOutcome, Severity
from .rules import RuleRegistry, default_registry
from .rules.base import Rule


@dataclass(frozen=True, slots=True)
class ValidatorOptions:
    """Knobs that change which rules run, never how a rule decides."""

    registry: RuleRegistry | None = None
    fail_fast: bool = False

    def resolved_registry(self) -> RuleRegistry:
        return self.registry if self.registry is not None else default_registry()


class Validator:
    """Runs a registry of rules against PDF documents."""

    def __init__(self, options: ValidatorOptions | None = None) -> None:
        self.options = options or ValidatorOptions()

    @property
    def registry(self) -> RuleRegistry:
        return self.options.resolved_registry()

    @property
    def coverage(self) -> Coverage:
        return coverage(self.registry)

    def validate(self, path: str) -> Report:
        """Validate the PDF at ``path`` and return a :class:`Report`.

        Raises:
            PdfuaError: if the file cannot be parsed as a PDF. A malformed file
                is a caller error, not a conformance finding.
        """
        started = time.perf_counter()
        with PdfDocument.open(path) as doc:
            outcomes = self._run_rules(doc)
        elapsed = (time.perf_counter() - started) * 1000.0
        return Report(
            path=path,
            outcomes=outcomes,
            duration_ms=elapsed,
        )

    def _run_rules(self, doc: PdfDocument) -> tuple[RuleOutcome, ...]:
        outcomes: list[RuleOutcome] = []
        for rule in self.registry:
            outcomes.append(self._run_rule(rule, doc))
            if self.options.fail_fast and outcomes[-1].findings:
                break
        return tuple(outcomes)

    @staticmethod
    def _run_rule(rule: Rule, doc: PdfDocument) -> RuleOutcome:
        started = time.perf_counter()
        try:
            findings = tuple(rule.check(doc))
        except PdfuaError as exc:
            # A rule that cannot evaluate the document must say so rather than
            # silently pass. Silence is indistinguishable from success.
            return RuleOutcome(
                rule_id=rule.id,
                skipped_reason=str(exc),
                duration_ms=(time.perf_counter() - started) * 1000.0,
            )
        except Exception as exc:
            return RuleOutcome(
                rule_id=rule.id,
                skipped_reason=f"rule raised {type(exc).__name__}: {exc}",
                duration_ms=(time.perf_counter() - started) * 1000.0,
            )
        return RuleOutcome(
            rule_id=rule.id,
            findings=findings,
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )


def validate(path: str, registry: RuleRegistry | None = None) -> Report:
    """Convenience wrapper: validate one file with an optional rule selection."""
    return Validator(ValidatorOptions(registry=registry)).validate(path)


def worst_severity(report: Report) -> Severity | None:
    """Return the worst severity in ``report``, or ``None`` when clean."""
    return report.worst_severity()

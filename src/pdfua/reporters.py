"""Output formatters: SARIF, JSON, and human-readable text.

SARIF 2.1.0 is the format CI systems already understand (GitHub code scanning,
Azure DevOps). Emitting it means a `.gov` PDF that fails a rule shows up as an
annotation on the pull request that introduced it, with no bespoke glue.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from .catalog import Coverage
from .model import Finding, Report, Severity

SARIF_VERSION = "2.1.0"
# The canonical OASIS schema location for SARIF 2.1.0. The widely-copied
# raw.githubusercontent.com/.../Schemata/... path returns 404, so it is not
# used: a validator that advertises a schema URL which does not resolve is
# advertising a lie, and tooling that fetches it fails.
SARIF_SCHEMA = (
    "https://docs.oasis-open.org/sarif/sarif/v2.1.0/errata01/os/schemas/sarif-schema-2.1.0.json"
)

#: SARIF has three levels; pdfua's INFO has no SARIF equivalent, so it maps to
#: "note", which is the lowest level and does not fail a build by default.
_SARIF_LEVEL: Mapping[Severity, str] = {
    Severity.INFO: "note",
    Severity.WARNING: "warning",
    Severity.ERROR: "error",
}

_RULE_TAGS: Mapping[Severity, str] = {
    Severity.INFO: "informational",
    Severity.WARNING: "warning",
    Severity.ERROR: "error",
}


def _file_uri(path: str) -> str:
    return path.replace("\\", "/")


def format_json(report: Report, *, coverage_info: Coverage | None = None) -> str:
    """Render ``report`` as a JSON document."""
    payload: dict[str, object] = report.to_dict()
    if coverage_info is not None:
        payload["coverage"] = {
            "covered_rules": coverage_info.covered,
            "total_rules": coverage_info.total,
            "implemented_checks": coverage_info.implemented_rules,
            "summary": coverage_info.summary(),
        }
    return json.dumps(payload, indent=2, sort_keys=False)


def format_sarif(report: Report, *, coverage_info: Coverage | None = None) -> str:
    """Render ``report`` as a SARIF 2.1.0 log."""
    rules: list[dict[str, object]] = []
    seen: set[str] = set()
    results: list[dict[str, object]] = []

    for finding in report.findings:
        if finding.rule_id not in seen:
            seen.add(finding.rule_id)
            rules.append(_sarif_rule(finding))
        results.append(_sarif_result(finding, report.path))

    payload: dict[str, object] = {
        "$schema": SARIF_SCHEMA,
        "version": SARIF_VERSION,
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "pdfua",
                        "informationUri": "https://github.com/beduldul/pdfua",
                        "rules": rules,
                        "properties": {
                            "coverage": (
                                coverage_info.summary() if coverage_info is not None else "unknown"
                            ),
                            "pdfuaVersion": report.pdfua_version,
                        },
                    }
                },
                "results": results,
                "invocations": [
                    {
                        "executionSuccessful": True,
                        "toolExecutionNotifications": [
                            {
                                "level": "note",
                                "message": {
                                    "text": (
                                        f"rule {o.rule_id} was not evaluated: {o.skipped_reason}"
                                    )
                                },
                            }
                            for o in report.skipped
                        ],
                    }
                ],
            }
        ],
    }
    return json.dumps(payload, indent=2, sort_keys=False)


def _sarif_rule(finding: Finding) -> dict[str, object]:
    properties: dict[str, object] = {"tags": [_RULE_TAGS[finding.severity]]}
    if finding.pdfua_clause:
        properties["pdfuaClause"] = finding.pdfua_clause
    if finding.wcag:
        properties["wcag"] = list(finding.wcag)
    rule: dict[str, object] = {
        "id": finding.rule_id,
        "name": finding.rule_id,
        "shortDescription": {"text": finding.message.split(".")[0][:120]},
        "defaultConfiguration": {"level": _SARIF_LEVEL[finding.severity]},
        "properties": properties,
    }
    if finding.remediation:
        rule["help"] = {"text": finding.remediation}
    return rule


def _sarif_result(finding: Finding, path: str) -> dict[str, object]:
    message = finding.message
    if finding.remediation:
        message = f"{message}\n\nHow to fix: {finding.remediation}"
    result: dict[str, object] = {
        "ruleId": finding.rule_id,
        "level": _SARIF_LEVEL[finding.severity],
        "message": {"text": message},
        "locations": [
            {
                "physicalLocation": {
                    "artifactLocation": {"uri": _file_uri(path)},
                    "region": {"startLine": finding.location.page or 1},
                },
                "logicalLocations": [{"fullyQualifiedName": finding.location.describe()}],
            }
        ],
    }
    if finding.evidence:
        result["properties"] = {
            "confidence": finding.confidence.value,
            "evidence": dict(finding.evidence),
        }
    return result


def format_text(report: Report, *, coverage_info: Coverage | None = None) -> str:
    """Render ``report`` for a human reading a terminal."""
    lines: list[str] = []
    lines.append(f"{report.path}")
    if coverage_info is not None:
        lines.append(
            f"  checked against {coverage_info.summary()} "
            "(machine-checkable subset; see 'pdfua rules')"
        )
    counts = report.count_by_severity()
    worst = report.worst_severity()
    status = "PASS (no findings)" if worst is None else worst.name
    lines.append(
        f"  result: {status}   "
        f"errors={counts[Severity.ERROR]} "
        f"warnings={counts[Severity.WARNING]} "
        f"info={counts[Severity.INFO]}   "
        f"{report.duration_ms:.0f} ms"
    )

    for finding in report.findings:
        marker = {Severity.ERROR: "ERROR", Severity.WARNING: "WARN ", Severity.INFO: "info "}[
            finding.severity
        ]
        lines.append(f"  [{marker}] {finding.rule_id}  {finding.location.describe()}")
        lines.append(f"          {finding.message}")
        if finding.remediation:
            lines.append(f"          fix: {finding.remediation}")

    for outcome in report.skipped:
        lines.append(f"  [skip ] {outcome.rule_id}  not evaluated: {outcome.skipped_reason}")

    if worst is None:
        checks = coverage_info.implemented_rules if coverage_info else 0
        lines.append("")
        lines.append(
            "  This is NOT a statement of PDF/UA conformance. It means the "
            f"{checks} implemented checks this tool runs found nothing. "
            "Run veraPDF before claiming conformance."
        )
    return "\n".join(lines)


def format_unreadable(path: str, message: str, fmt: str) -> str | None:
    """Render a structured record for a file that could not be read as a PDF.

    The human ``text`` format has nothing useful to add to the error already
    written to stderr, so it returns ``None``. The machine formats do, because
    a redirection such as ``pdfua check *.pdf --format sarif > results.sarif``
    must not silently lose the file: it would exit 4 while the SARIF log
    contained no record of the failure at all.

    Args:
        path: The file that could not be read.
        message: The error text (already printed to stderr).
        fmt: One of ``text``, ``json`` or ``sarif``.

    Returns:
        The serialised record, or ``None`` when the format has no structured
        representation to emit.
    """
    if fmt == "text":
        return None
    if fmt == "json":
        return json.dumps(
            {
                "file": path,
                "readable": False,
                "error": message,
                "exit_code": 4,  # the documented "could not be read" code
            },
            indent=2,
        )
    if fmt == "sarif":
        payload = {
            "$schema": SARIF_SCHEMA,
            "version": SARIF_VERSION,
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": "pdfua",
                            "informationUri": "https://github.com/beduldul/pdfua",
                            "rules": [],
                        }
                    },
                    "results": [
                        {
                            "ruleId": "PDFUA-READ-001",
                            "level": "error",
                            "message": {"text": f"could not be read as a PDF: {message}"},
                            "locations": [
                                {
                                    "physicalLocation": {
                                        "artifactLocation": {"uri": _file_uri(path)},
                                    }
                                }
                            ],
                        }
                    ],
                    "invocations": [{"executionSuccessful": False}],
                }
            ],
        }
        return json.dumps(payload, indent=2, sort_keys=False)
    return None


FORMATTERS = {
    "json": format_json,
    "sarif": format_sarif,
    "text": format_text,
}


def format_report(
    report: Report,
    fmt: str,
    *,
    coverage_info: Coverage | None = None,
) -> str:
    """Dispatch to the formatter named by ``fmt``.

    Raises:
        ValueError: if ``fmt`` is not a known format.
    """
    try:
        formatter = FORMATTERS[fmt]
    except KeyError:
        raise ValueError(
            f"unknown format {fmt!r}; expected one of: {', '.join(sorted(FORMATTERS))}"
        ) from None
    return formatter(report, coverage_info=coverage_info)


__all__ = [
    "FORMATTERS",
    "format_json",
    "format_report",
    "format_sarif",
    "format_text",
    "format_unreadable",
]

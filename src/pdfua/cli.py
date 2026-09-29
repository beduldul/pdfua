"""Command-line interface: ``pdfua check <file>`` and ``pdfua rules``."""

from __future__ import annotations

import argparse
import contextlib
import io
import os
import sys
from collections.abc import Sequence

from . import __version__
from .catalog import (
    PDFUA1_TOTAL_RULES,
    clause_summary,
    coverage,
    describe_rules,
    pdfua1_rule_identifiers,
    unchecked_rules,
)
from .errors import PdfuaError
from .model import Severity, filter_findings
from .reporters import FORMATTERS, format_report
from .rules import RuleRegistry, default_registry
from .validator import Validator, ValidatorOptions

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_USAGE = 3
EXIT_UNREADABLE = 4

_EPILOG = """\
exit codes:
  0  no findings
  1  findings at or above --min-severity (default: any)
  2  findings at ERROR severity (see below)
  3  usage error
  4  the file could not be read as a PDF

When --min-severity is the default, the exit code is ordered by severity:
0 clean, 1 info, 2 warning, 3 error. So `pdfua check f.pdf || alert` alerts on
anything, and `pdfua check f.pdf; case $? in 3) alert;; esac` alerts only on
errors. Gate on SARIF or JSON if you need the finding detail.
"""


def build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser for the ``pdfua`` CLI."""
    parser = argparse.ArgumentParser(
        prog="pdfua",
        description=(
            "Check the machine-checkable subset of PDF/UA-1 and the related "
            "WCAG 2.1 criteria. No JVM required."
        ),
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"pdfua {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="validate one or more PDF files")
    check.add_argument("files", nargs="+", metavar="FILE", help="PDF file(s) to check")
    check.add_argument(
        "--format",
        "-f",
        choices=sorted(FORMATTERS),
        default="text",
        help="output format (default: text)",
    )
    check.add_argument(
        "--rules",
        metavar="ID[,ID...]",
        default=None,
        help="only run these rules; a prefix selects a family (e.g. UA-01)",
    )
    check.add_argument(
        "--min-severity",
        choices=[s.name.lower() for s in Severity],
        default=None,
        help="suppress findings below this severity",
    )
    check.add_argument(
        "--certain-only",
        action="store_true",
        help="suppress heuristic findings (those needing human judgement)",
    )
    check.add_argument(
        "--fail-fast",
        action="store_true",
        help="stop after the first rule that reports a finding",
    )
    check.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="with multiple files, print only files that have findings",
    )

    rules_cmd = sub.add_parser("rules", help="list implemented and unimplemented rules")
    rules_cmd.add_argument(
        "--format",
        "-f",
        choices=("text", "json"),
        default="text",
        help="output format (default: text)",
    )
    return parser


def _select_registry(spec: str | None) -> RuleRegistry:
    registry = default_registry()
    if spec is None:
        return registry
    patterns = [p.strip() for p in spec.split(",") if p.strip()]
    try:
        return registry.select(patterns)
    except ValueError as exc:
        raise PdfuaError(str(exc)) from exc


def _cmd_check(args: argparse.Namespace) -> int:
    try:
        registry = _select_registry(args.rules)
    except PdfuaError as exc:
        print(f"pdfua: {exc}", file=sys.stderr)
        return EXIT_USAGE

    min_severity = Severity.from_name(args.min_severity) if args.min_severity else None
    options = ValidatorOptions(registry=registry, fail_fast=args.fail_fast)
    validator = Validator(options)
    coverage_info = coverage(registry)

    exit_code = EXIT_OK
    for path in args.files:
        try:
            report = validator.validate(path)
        except PdfuaError as exc:
            print(f"pdfua: {exc}", file=sys.stderr)
            exit_code = max(exit_code, EXIT_UNREADABLE)
            continue

        kept = filter_findings(
            report.findings,
            min_severity=min_severity,
            min_confidence=None,
            only_rules=None,
        )
        if args.certain_only:
            from .model import Confidence

            kept = filter_findings(kept, min_confidence=Confidence.CERTAIN)

        if args.quiet and not kept:
            continue

        # Rebuild the report so the formatter sees only the kept findings.
        from .model import Report, RuleOutcome

        filtered = Report(
            path=report.path,
            outcomes=tuple(
                RuleOutcome(
                    rule_id=o.rule_id,
                    findings=tuple(f for f in o.findings if f in kept),
                    skipped_reason=o.skipped_reason,
                    duration_ms=o.duration_ms,
                )
                for o in report.outcomes
            ),
            pdfua_version=report.pdfua_version,
            duration_ms=report.duration_ms,
        )
        print(format_report(filtered, args.format, coverage_info=coverage_info))

        worst = filtered.worst_severity()
        if worst is not None:
            code = int(worst) + 1 if min_severity is None else EXIT_FINDINGS
            exit_code = max(exit_code, code)

    return exit_code


def _cmd_rules(args: argparse.Namespace) -> int:
    implemented = describe_rules()
    cov = coverage()
    if args.format == "json":
        import json

        payload = {
            "pdfua1_total_rules": PDFUA1_TOTAL_RULES,
            "implemented": [
                {
                    "id": r.id,
                    "title": r.title,
                    "severity": r.severity,
                    "confidence": r.confidence,
                    "pdfua_clause": r.pdfua_clause,
                    "wcag": list(r.wcag),
                    "covers": list(r.covers),
                }
                for r in implemented
            ],
            "covered_rule_identifiers": sorted({i for r in describe_rules() for i in r.covers}),
            "clause_summary": [
                {"clause": c, "covered": n, "total": t} for c, n, t in clause_summary()
            ],
            "unchecked_rules": [
                {"clause": e["clause"], "test": e["test"], "object": e["object"]}
                for e in unchecked_rules()
            ],
        }
        print(json.dumps(payload, indent=2))
        return EXIT_OK

    print(f"pdfua {__version__}")
    print()
    print(f"Implemented: {cov.summary()}")
    print("  (denominator = machine-checkable rules in the PDF/UA-1 profile,")
    print(f"   {len(pdfua1_rule_identifiers())} rule identifiers bundled)")
    print()
    print(f"{'RULE ID':<12} {'SEV':<8} {'CONF':<10} {'PDF/UA-1':<20} {'WCAG':<14} TITLE")
    for r in implemented:
        wcag = ",".join(r.wcag) if r.wcag else "-"
        covers = ",".join(r.covers) if r.covers else "(no profile rule)"
        print(f"{r.id:<12} {r.severity:<8} {r.confidence:<10} {covers:<20} {wcag:<14} {r.title}")
    print()
    print("Coverage by ISO 14289-1 clause, counted at rule granularity.")
    print("Clause 7.21 covers font embedding, CIDSet and glyph widths — the rules")
    print("that catch professionally-remediated files:")
    print()
    print(f"  {'CLAUSE':<10} {'COVERED/TOTAL':<15} BAR")
    for clause, checked, total in clause_summary():
        bar = "#" * round(12 * checked / total)
        flag = "  <-- no coverage" if checked == 0 else ""
        print(f"  {clause:<10} {f'{checked}/{total}':<15} {bar:<12}{flag}")
    print()
    print("Everything not listed above is unimplemented. In particular this tool")
    print("does NOT check font embedding, CIDSet, glyph widths, colour spaces,")
    print("reading order, or WTPDF structure. See the README section")
    print("'What this does NOT check'.")
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            return _cmd_check(args)
        if args.command == "rules":
            return _cmd_rules(args)
    except PdfuaError as exc:
        print(f"pdfua: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except KeyboardInterrupt:
        return 130
    except BrokenPipeError:
        # `pdfua check *.pdf | head` is a normal thing to do. Python turns the
        # closed pipe into an exception on the next write, which would print a
        # traceback for a command that did exactly what the user asked. Redirect
        # stdout to devnull so the interpreter's own flush at shutdown does not
        # raise a second time.
        # The documented recipe: redirect the underlying file descriptor to
        # devnull so the interpreter's final flush does not raise a second time.
        # A new Python file object is avoided deliberately, because it would be
        # collected unclosed and emit a ResourceWarning.
        with contextlib.suppress(OSError, ValueError, io.UnsupportedOperation):
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, sys.stdout.fileno())
            os.close(devnull)
        return EXIT_OK
    parser.print_help()
    return EXIT_USAGE


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

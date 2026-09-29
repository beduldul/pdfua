"""Tests for the result model: severities, filtering, and exit-code ordering."""

from __future__ import annotations

import dataclasses

import pytest

from pdfua.model import (
    Confidence,
    Finding,
    Location,
    Report,
    RuleOutcome,
    Severity,
    filter_findings,
)


def _finding(
    rule_id: str = "UA-00-000",
    severity: Severity = Severity.ERROR,
    confidence: Confidence = Confidence.CERTAIN,
    **location: object,
) -> Finding:
    return Finding(
        rule_id=rule_id,
        severity=severity,
        message="m",
        location=Location(**location),  # type: ignore[arg-type]
        confidence=confidence,
    )


def _report(*findings: Finding) -> Report:
    return Report(path="x.pdf", outcomes=(RuleOutcome(rule_id="r", findings=findings),))


class TestSeverity:
    def test_int_values_are_the_basis_of_exit_codes(self) -> None:
        assert int(Severity.INFO) == 0
        assert int(Severity.WARNING) == 1
        assert int(Severity.ERROR) == 2

    def test_max_is_the_worst_severity(self) -> None:
        assert max([Severity.INFO, Severity.ERROR, Severity.WARNING]) is Severity.ERROR

    @pytest.mark.parametrize(
        ("text", "expected"),
        [("info", Severity.INFO), ("WARNING", Severity.WARNING), (" Error ", Severity.ERROR)],
    )
    def test_from_name_is_case_and_space_insensitive(self, text: str, expected: Severity) -> None:
        assert Severity.from_name(text) is expected

    def test_from_name_rejects_unknown_values(self) -> None:
        with pytest.raises(ValueError, match="unknown severity"):
            Severity.from_name("catastrophe")


class TestExitCodes:
    def test_clean_report_exits_zero(self) -> None:
        assert _report().exit_code == 0
        assert _report().worst_severity() is None

    @pytest.mark.parametrize(
        ("severity", "expected"),
        [(Severity.INFO, 1), (Severity.WARNING, 2), (Severity.ERROR, 3)],
    )
    def test_exit_code_is_severity_plus_one(self, severity: Severity, expected: int) -> None:
        assert _report(_finding(severity=severity)).exit_code == expected

    def test_exit_code_tracks_the_worst_finding(self) -> None:
        report = _report(
            _finding(severity=Severity.INFO),
            _finding(severity=Severity.ERROR),
            _finding(severity=Severity.WARNING),
        )
        assert report.exit_code == 3


class TestReportAggregation:
    def test_counts_by_severity(self) -> None:
        report = _report(
            _finding(severity=Severity.ERROR),
            _finding(severity=Severity.ERROR),
            _finding(severity=Severity.INFO),
        )
        counts = report.count_by_severity()
        assert counts[Severity.ERROR] == 2
        assert counts[Severity.INFO] == 1
        assert counts[Severity.WARNING] == 0

    def test_skipped_outcomes_are_separated(self) -> None:
        report = Report(
            path="x.pdf",
            outcomes=(
                RuleOutcome(rule_id="a", findings=(_finding(),)),
                RuleOutcome(rule_id="b", skipped_reason="cannot evaluate"),
            ),
        )
        assert [o.rule_id for o in report.skipped] == ["b"]

    def test_to_dict_is_json_shaped(self) -> None:
        payload = _report(_finding(rule_id="UA-01-005", page=3)).to_dict()
        assert payload["exit_code"] == 3
        assert payload["summary"]["errors"] == 1  # type: ignore[index]
        assert payload["findings"][0]["rule_id"] == "UA-01-005"  # type: ignore[index]


class TestFiltering:
    def test_min_severity_suppresses_lower(self) -> None:
        findings = [_finding(severity=Severity.INFO), _finding(severity=Severity.ERROR)]
        kept = filter_findings(findings, min_severity=Severity.WARNING)
        assert [f.severity for f in kept] == [Severity.ERROR]

    def test_certain_only_drops_heuristics(self) -> None:
        findings = [
            _finding(confidence=Confidence.CERTAIN),
            _finding(confidence=Confidence.HEURISTIC),
        ]
        kept = filter_findings(findings, min_confidence=Confidence.CERTAIN)
        assert [f.confidence for f in kept] == [Confidence.CERTAIN]

    def test_rule_filter_matches_exactly_and_by_prefix(self) -> None:
        findings = [_finding("UA-01-005"), _finding("UA-13-004"), _finding("UA-01-002")]
        exact = filter_findings(findings, only_rules=["UA-13-004"])
        assert [f.rule_id for f in exact] == ["UA-13-004"]
        prefixed = filter_findings(findings, only_rules=["UA-01"])
        assert [f.rule_id for f in prefixed] == ["UA-01-005", "UA-01-002"]

    def test_filters_compose_conjunctively(self) -> None:
        findings = [
            _finding("UA-01-005", Severity.ERROR, Confidence.CERTAIN),
            _finding("UA-01-005", Severity.INFO, Confidence.HEURISTIC),
        ]
        kept = filter_findings(
            findings,
            min_severity=Severity.WARNING,
            min_confidence=Confidence.CERTAIN,
            only_rules=["UA-01"],
        )
        assert len(kept) == 1
        assert kept[0].severity is Severity.ERROR


class TestLocation:
    def test_describe_includes_page_and_role(self) -> None:
        assert Location(page=7, struct_role="/Figure").describe() == "page 7 /Figure"

    def test_describe_defaults_to_document(self) -> None:
        assert Location().describe() == "document"

    def test_mcid_list_is_truncated_with_a_count(self) -> None:
        described = Location(mcids=(1, 2, 3, 4, 5, 6)).describe()
        assert "1, 2, 3, 4" in described
        assert "+2 more" in described


class TestImmutability:
    def test_findings_are_frozen(self) -> None:
        """A frozen dataclass raises FrozenInstanceError, which is an AttributeError."""
        finding = _finding()
        with pytest.raises(dataclasses.FrozenInstanceError):
            finding.severity = Severity.INFO  # type: ignore[misc]

    def test_to_dict_does_not_expose_mutable_state(self) -> None:
        finding = _finding()
        first = finding.to_dict()
        first["rule_id"] = "tampered"
        assert finding.to_dict()["rule_id"] == "UA-00-000"

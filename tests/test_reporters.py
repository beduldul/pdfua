"""Tests for the SARIF, JSON and text reporters."""

from __future__ import annotations

import json

import pytest

from pdfua.catalog import coverage
from pdfua.model import Confidence, Finding, Location, Report, RuleOutcome, Severity
from pdfua.reporters import format_json, format_report, format_sarif, format_text


def _report(*findings: Finding, path: str = "docs/a.pdf") -> Report:
    return Report(
        path=path,
        outcomes=(RuleOutcome(rule_id="UA-01-005", findings=findings),),
    )


def _finding(**kwargs: object) -> Finding:
    base: dict[str, object] = {
        "rule_id": "UA-01-005",
        "severity": Severity.ERROR,
        "message": "Document has no /StructTreeRoot.",
        "location": Location(page=2, struct_role="/Document"),
        "pdfua_clause": "7.1",
        "wcag": ("1.3.1",),
        "remediation": "Tag the document.",
        "evidence": {"struct_tree_root": False},
    }
    base.update(kwargs)
    return Finding(**base)  # type: ignore[arg-type]


class TestSarif:
    def test_schema_url_is_the_canonical_oasis_location(self) -> None:
        """The advertised ``$schema`` must resolve.

        The widely-copied ``raw.githubusercontent.com/.../Schemata/...`` URL is
        a 404. A SARIF log that points at a schema which does not exist is
        advertising a lie, and tooling that fetches it fails.
        """
        from pdfua.reporters import SARIF_SCHEMA

        assert SARIF_SCHEMA.startswith("https://docs.oasis-open.org/sarif/")
        assert "Schemata" not in SARIF_SCHEMA
        assert SARIF_SCHEMA.endswith("sarif-schema-2.1.0.json")

    def test_sarif_shape_is_2_1_0(self) -> None:
        payload = json.loads(format_sarif(_report(_finding())))
        assert payload["version"] == "2.1.0"
        assert "sarif-schema-2.1.0" in payload["$schema"]
        assert payload["runs"][0]["tool"]["driver"]["name"] == "pdfua"

    def test_severity_maps_to_sarif_levels(self) -> None:
        cases = {
            Severity.ERROR: "error",
            Severity.WARNING: "warning",
            Severity.INFO: "note",
        }
        for severity, level in cases.items():
            payload = json.loads(format_sarif(_report(_finding(severity=severity))))
            assert payload["runs"][0]["results"][0]["level"] == level

    def test_artifact_location_carries_the_path(self) -> None:
        payload = json.loads(format_sarif(_report(_finding())))
        location = payload["runs"][0]["results"][0]["locations"][0]
        assert location["physicalLocation"]["artifactLocation"]["uri"] == "docs/a.pdf"

    def test_rule_metadata_is_emitted_once_per_rule(self) -> None:
        payload = json.loads(format_sarif(_report(_finding(), _finding(), _finding())))
        run = payload["runs"][0]
        assert len(run["tool"]["driver"]["rules"]) == 1
        assert len(run["results"]) == 3

    def test_remediation_is_included_in_the_message(self) -> None:
        payload = json.loads(format_sarif(_report(_finding())))
        text = payload["runs"][0]["results"][0]["message"]["text"]
        assert "How to fix" in text

    def test_coverage_is_advertised_on_the_tool(self) -> None:
        payload = json.loads(format_sarif(_report(_finding()), coverage_info=coverage()))
        props = payload["runs"][0]["tool"]["driver"]["properties"]
        assert "PDF/UA-1 rules" in props["coverage"]

    def test_skipped_rules_become_notifications(self) -> None:
        report = Report(
            path="a.pdf",
            outcomes=(RuleOutcome(rule_id="UA-01-003", skipped_reason="parse error"),),
        )
        payload = json.loads(format_sarif(report))
        notifications = payload["runs"][0]["invocations"][0]["toolExecutionNotifications"]
        assert "UA-01-003" in notifications[0]["message"]["text"]

    def test_clean_report_has_no_results(self) -> None:
        payload = json.loads(format_sarif(_report()))
        assert payload["runs"][0]["results"] == []


class TestJson:
    def test_json_round_trips(self) -> None:
        payload = json.loads(format_json(_report(_finding())))
        assert payload["file"] == "docs/a.pdf"
        assert payload["findings"][0]["rule_id"] == "UA-01-005"
        assert payload["findings"][0]["pdfua_clause"] == "7.1"

    def test_coverage_block_is_optional_but_correct(self) -> None:
        with_coverage = json.loads(format_json(_report(), coverage_info=coverage()))
        assert with_coverage["coverage"]["total_rules"] == 106
        without = json.loads(format_json(_report()))
        assert "coverage" not in without


class TestText:
    def test_clean_report_says_it_is_not_a_conformance_statement(self) -> None:
        rendered = format_text(_report(), coverage_info=coverage())
        assert "NOT a statement of PDF/UA conformance" in rendered

    def test_findings_show_rule_location_and_remediation(self) -> None:
        rendered = format_text(_report(_finding()), coverage_info=coverage())
        assert "UA-01-005" in rendered
        assert "page 2" in rendered
        assert "fix: Tag the document." in rendered

    def test_skipped_rules_are_shown(self) -> None:
        report = Report(
            path="a.pdf",
            outcomes=(RuleOutcome(rule_id="UA-01-003", skipped_reason="boom"),),
        )
        assert "not evaluated: boom" in format_text(report)


class TestDispatch:
    def test_unknown_format_is_rejected_with_a_helpful_message(self) -> None:
        with pytest.raises(ValueError, match="unknown format"):
            format_report(_report(), "yaml")

    @pytest.mark.parametrize("fmt", ["text", "json", "sarif"])
    def test_every_advertised_format_produces_output(self, fmt: str) -> None:
        assert format_report(_report(_finding()), fmt).strip()


class TestConfidenceIsPreserved:
    def test_heuristic_confidence_survives_serialisation(self) -> None:
        payload = json.loads(format_json(_report(_finding(confidence=Confidence.HEURISTIC))))
        assert payload["findings"][0]["confidence"] == "heuristic"

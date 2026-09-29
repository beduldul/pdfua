"""Tests for the CLI: argument handling, exit codes, and output routing."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pdfua.cli import main


class TestExitCodes:
    def test_clean_file_exits_zero(
        self, valid_pdf: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["check", str(valid_pdf)]) == 0

    def test_error_findings_exit_three(
        self, violating_pdfs: dict[str, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["check", str(violating_pdfs["untagged"])]) == 3

    def test_warning_only_findings_exit_two(
        self, violating_pdfs: dict[str, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["check", str(violating_pdfs["no_title"])]) == 2

    def test_unreadable_file_exits_four(
        self, unreadable_pdf: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["check", str(unreadable_pdf)]) == 4

    def test_missing_file_exits_four(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["check", str(tmp_path / "nope.pdf")]) == 4

    def test_unknown_rule_selector_exits_three(
        self, valid_pdf: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["check", str(valid_pdf), "--rules", "UA-99-999"]) == 3

    def test_min_severity_flattens_exit_code_to_one(
        self, violating_pdfs: dict[str, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(["check", str(violating_pdfs["untagged"]), "--min-severity", "error"])
        assert code == 1

    def test_min_severity_can_silence_everything(
        self, violating_pdfs: dict[str, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(["check", str(violating_pdfs["no_title"]), "--min-severity", "error"])
        assert code == 0

    def test_quiet_suppresses_clean_files(
        self, valid_pdf: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["check", str(valid_pdf), "--quiet"]) == 0
        assert capsys.readouterr().out == ""


class TestFormats:
    def test_sarif_output_is_valid_json(
        self, violating_pdfs: dict[str, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        main(["check", str(violating_pdfs["untagged"]), "--format", "sarif"])
        payload = json.loads(capsys.readouterr().out)
        assert payload["version"] == "2.1.0"

    def test_json_output_is_valid_json(
        self, violating_pdfs: dict[str, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        main(["check", str(violating_pdfs["untagged"]), "--format", "json"])
        payload = json.loads(capsys.readouterr().out)
        assert payload["file"].endswith("untagged.pdf")

    def test_text_output_mentions_the_coverage_denominator(
        self, valid_pdf: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        main(["check", str(valid_pdf)])
        assert "106" in capsys.readouterr().out

    def test_multiple_files_are_each_reported(
        self,
        valid_pdf: Path,
        violating_pdfs: dict[str, Path],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        code = main(["check", str(valid_pdf), str(violating_pdfs["untagged"]), "--format", "json"])
        assert code == 3
        # One JSON document per file, so count the top-level objects.
        assert capsys.readouterr().out.count('"file":') == 2


class TestRuleSelection:
    def test_selecting_one_rule_suppresses_the_others(
        self, violating_pdfs: dict[str, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        main(
            [
                "check",
                str(violating_pdfs["untagged"]),
                "--rules",
                "UA-01-002",
                "--format",
                "json",
            ]
        )
        payload = json.loads(capsys.readouterr().out)
        assert {f["rule_id"] for f in payload["findings"]} == {"UA-01-002"}

    def test_prefix_selection_runs_a_family(
        self, violating_pdfs: dict[str, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        main(
            [
                "check",
                str(violating_pdfs["untagged"]),
                "--rules",
                "UA-01",
                "--format",
                "json",
            ]
        )
        payload = json.loads(capsys.readouterr().out)
        assert {f["rule_id"] for f in payload["findings"]} == {"UA-01-002", "UA-01-005"}

    def test_certain_only_drops_heuristic_findings(
        self, violating_pdfs: dict[str, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        main(
            [
                "check",
                str(violating_pdfs["table_headers_without_association"])
                if "table_headers_without_association" in violating_pdfs
                else str(violating_pdfs["figure_without_alt"]),
                "--certain-only",
                "--format",
                "json",
            ]
        )
        payload = json.loads(capsys.readouterr().out)
        assert all(f["confidence"] == "certain" for f in payload["findings"])


class TestRulesSubcommand:
    def test_rules_text_lists_coverage_and_the_missing_font_rules(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["rules"]) == 0
        out = capsys.readouterr().out
        assert "of 106 PDF/UA-1 rules" in out
        assert "7.21" in out
        assert "no coverage" in out

    def test_rules_json_is_machine_readable(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["rules", "--format", "json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["pdfua1_total_rules"] == 106
        assert len(payload["implemented"]) == 12
        assert len(payload["unchecked_rules"]) == 106 - len(payload["covered_rule_identifiers"])

    def test_rules_json_reports_the_font_clause_as_unchecked(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        main(["rules", "--format", "json"])
        payload = json.loads(capsys.readouterr().out)
        unchecked = {(r["clause"], r["test"]) for r in payload["unchecked_rules"]}
        assert ("7.21.4.2", "2") in unchecked


class TestPiping:
    def test_piping_to_a_closed_reader_does_not_traceback(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """`pdfua rules | head` is normal usage and must not print a traceback.

        Python raises BrokenPipeError on the write after the reader closes. The
        CLI swallows it and exits zero, because the command did what was asked.
        """
        import io

        class ClosedPipe(io.StringIO):
            def write(self, _data: str) -> int:  # type: ignore[override]
                raise BrokenPipeError(32, "Broken pipe")

        import sys as _sys

        original = _sys.stdout
        _sys.stdout = ClosedPipe()  # type: ignore[assignment]
        try:
            code = main(["rules"])
        finally:
            _sys.stdout = original
        assert code == 0


class TestFailFast:
    def test_fail_fast_stops_after_the_first_rule_with_findings(
        self, violating_pdfs: dict[str, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        main(["check", str(violating_pdfs["untagged"]), "--fail-fast", "--format", "json"])
        payload = json.loads(capsys.readouterr().out)
        assert payload["summary"]["rules_run"] == 1

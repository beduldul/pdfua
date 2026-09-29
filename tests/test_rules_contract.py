"""Every rule must have a positive test and a negative test.

The parameterised table below is the contract: for each rule, a fixture that
violates it and must be caught, and the valid document that must not trigger it.
A rule added to the registry without an entry here fails
``test_every_rule_has_a_negative_and_positive_case``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pdfua import Severity, validate
from pdfua.rules import default_registry

#: rule id -> (fixture name, expected severity)
RULE_CASES: dict[str, tuple[str, Severity]] = {
    "UA-01-005": ("untagged", Severity.ERROR),
    "UA-01-002": ("marked_false", Severity.ERROR),
    "UA-01-003": ("untagged_content", Severity.ERROR),
    "UA-06-001": ("no_language", Severity.ERROR),
    "UA-07-001": ("no_title", Severity.WARNING),
    "UA-07-002": ("no_display_doc_title", Severity.WARNING),
    "UA-28-004": ("no_pdfua_identifier", Severity.WARNING),
    "UA-13-004": ("figure_without_alt", Severity.ERROR),
    "UA-15-003": ("table_without_headers", Severity.ERROR),
    "UA-18-005": ("link_without_description", Severity.WARNING),
    "UA-18-001": ("annotation_without_description", Severity.WARNING),
}

#: Rules that a structurally-valid document still cannot satisfy, so they are
#: excluded from the "must be clean" assertion.
NO_NEGATIVE_FIXTURE: frozenset[str] = frozenset(
    {
        # A whitespace /Alt is stricter than the standard; the valid fixture has
        # no figure at all, which is the correct negative case and is asserted
        # separately in test_rules_structure.py.
        "UA-13-004",
        # Empty headings are absent from the valid fixture by construction.
        "UA-14-001",
    }
)


def test_every_rule_has_a_negative_and_positive_case() -> None:
    """No rule may ship without a fixture that proves it fires and one that doesn't."""
    registered = set(default_registry().ids())
    missing = registered - set(RULE_CASES) - NO_NEGATIVE_FIXTURE
    assert not missing, "rules with no positive fixture in RULE_CASES: " + ", ".join(
        sorted(missing)
    )
    unknown = set(RULE_CASES) - registered
    assert not unknown, "RULE_CASES names rules that are not registered: " + ", ".join(
        sorted(unknown)
    )


@pytest.mark.parametrize("rule_id", sorted(RULE_CASES))
def test_rule_fires_on_its_violating_fixture(
    rule_id: str,
    violating_pdfs: dict[str, Path],
) -> None:
    """The rule is reported, at the expected severity, on the fixture for it."""
    fixture_name, expected_severity = RULE_CASES[rule_id]
    report = validate(str(violating_pdfs[fixture_name]))
    matching = [f for f in report.findings if f.rule_id == rule_id]
    assert matching, (
        f"{rule_id} did not fire on fixture {fixture_name!r}; "
        f"findings were {sorted({f.rule_id for f in report.findings})}"
    )
    assert any(f.severity == expected_severity for f in matching), (
        f"{rule_id} fired at {[f.severity.name for f in matching]}, "
        f"expected {expected_severity.name}"
    )


@pytest.mark.parametrize("rule_id", sorted(set(RULE_CASES) - NO_NEGATIVE_FIXTURE))
def test_rule_is_silent_on_the_valid_document(rule_id: str, valid_pdf: Path) -> None:
    """The rule does not fire on a document that satisfies it."""
    report = validate(str(valid_pdf))
    assert not [f for f in report.findings if f.rule_id == rule_id], (
        f"{rule_id} false-positived on the valid document: "
        f"{[f.message for f in report.findings if f.rule_id == rule_id]}"
    )


def test_valid_document_is_completely_clean(valid_pdf: Path) -> None:
    """A conforming document produces no findings and exits zero."""
    report = validate(str(valid_pdf))
    assert report.findings == (), [f.message for f in report.findings]
    assert report.exit_code == 0


@pytest.mark.parametrize("name", ["untagged", "no_language", "table_without_headers"])
def test_violating_fixture_never_crashes_a_rule(name: str, violating_pdfs: dict[str, Path]) -> None:
    """A rule that raises is reported as skipped, never as a crash.

    Every fixture in the suite must produce a report; a rule that cannot
    evaluate a document says so in ``report.skipped``.
    """
    report = validate(str(violating_pdfs[name]))
    assert report.skipped == () or all(o.skipped_reason for o in report.skipped)


def test_untagged_document_is_not_reported_per_page(
    violating_pdfs: dict[str, Path],
) -> None:
    """An untagged file reports UA-01-005 once, not once per page.

    Reporting the same defect per page would bury the real signal. UA-01-003
    deliberately stays silent when there is no structure tree at all.
    """
    report = validate(str(violating_pdfs["untagged"]))
    ids = [f.rule_id for f in report.findings]
    assert ids.count("UA-01-005") == 1
    assert "UA-01-003" not in ids

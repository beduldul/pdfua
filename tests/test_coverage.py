"""Tests that the coverage claim cannot drift or be inflated.

These are the tests that keep the README honest. If someone adds a rule and
forgets to declare what it covers, or declares an identifier that does not
exist, these fail.
"""

from __future__ import annotations

from pdfua.catalog import (
    PDFUA1_TOTAL_RULES,
    clause_summary,
    coverage,
    describe_rules,
    pdfua1_rule_identifiers,
    unchecked_rules,
)
from pdfua.rules import default_registry


class TestCatalogueIntegrity:
    def test_denominator_matches_the_bundled_catalogue(self) -> None:
        assert len(pdfua1_rule_identifiers()) == PDFUA1_TOTAL_RULES

    def test_catalogue_identifiers_are_unique(self) -> None:
        ids = [f"{r['clause']}-{r['test']}" for r in pdfua1_rule_identifiers()]
        assert len(ids) == len(set(ids))

    def test_catalogue_carries_identifiers_only(self) -> None:
        """No descriptive text is bundled; that text belongs to its authors."""
        for entry in pdfua1_rule_identifiers():
            assert set(entry) == {"clause", "test", "object"}


class TestCoverageAccounting:
    def test_every_declared_identifier_exists_in_the_catalogue(self) -> None:
        known = {f"{r['clause']}-{r['test']}" for r in pdfua1_rule_identifiers()}
        for rule in default_registry():
            for identifier in rule.covers:
                assert identifier in known, (
                    f"{rule.id} declares {identifier!r}, which is not a PDF/UA-1 rule"
                )

    def test_coverage_never_exceeds_the_denominator(self) -> None:
        cov = coverage()
        assert 0 < cov.covered <= cov.total
        assert cov.total == PDFUA1_TOTAL_RULES

    def test_coverage_counts_rule_identifiers_not_sections(self) -> None:
        """The whole point: one rule in clause 7.2 must not claim all 41.

        Clause 7.2 contains 41 PDF/UA-1 rules. This tool implements three of
        them. A coverage measure that reported 41/41 because a single rule
        mentions clause 7.2 would be the false comfort this project rejects.
        """
        summary = {clause: (covered, total) for clause, covered, total in clause_summary()}
        covered, total = summary["7.2"]
        assert total == 41
        assert covered < total

    def test_font_clause_is_reported_as_unchecked(self) -> None:
        """Clause 7.21 is where professionally-remediated files fail."""
        summary = {clause: (covered, total) for clause, covered, total in clause_summary()}
        for clause in ("7.21.4.1", "7.21.4.2", "7.21.6"):
            assert summary[clause][0] == 0

    def test_unchecked_plus_covered_equals_the_total(self) -> None:
        covered = {i for r in default_registry() for i in r.covers}
        assert len(unchecked_rules()) + len(covered) == PDFUA1_TOTAL_RULES

    def test_summary_text_states_the_denominator(self) -> None:
        text = coverage().summary()
        assert "106" in text
        assert "PDF/UA-1 rules" in text


class TestRuleDescriptions:
    def test_every_rule_declares_a_severity_and_title(self) -> None:
        for info in describe_rules():
            assert info.title
            assert info.severity in {"info", "warning", "error"}

    def test_rule_ids_are_unique_and_well_formed(self) -> None:
        ids = [info.id for info in describe_rules()]
        assert len(ids) == len(set(ids))
        for rule_id in ids:
            assert rule_id.startswith("UA-")

    def test_rules_with_a_pdfua_clause_declare_what_they_cover(self) -> None:
        """A rule claiming a clause must say which rule identifier it decides."""
        for rule in default_registry():
            if rule.pdfua_clause is not None:
                assert rule.covers, f"{rule.id} names clause {rule.pdfua_clause} but covers nothing"

# Contributing to pdfua

Thanks for looking. This project has one governing value: **do not overclaim.**

A validator that says "PASS" is making a claim about everything it did not check.
Every design decision here follows from that.

## The one rule

**If you add a check, you must declare exactly which PDF/UA-1 rule identifiers it
decides, and you must add a fixture that proves it fires.**

A rule declares its coverage with the `covers` attribute:

```python
class MyRule(Rule):
    id = "UA-99-001"
    title = "Something decidable"
    severity = Severity.ERROR
    pdfua_clause = "7.9"
    covers = ("7.9-1",)  # clause-test, as enumerated in the PDF/UA-1 profile
```

`tests/test_coverage.py` fails if a declared identifier is not a real PDF/UA-1
rule, and `tests/test_rules_contract.py` fails if a registered rule has no
positive fixture. Both exist to stop the coverage number in the README from
drifting away from the truth.

## Adding a rule

1. Implement it in the appropriate `src/pdfua/rules/*.py` module.
2. Set `covers` to the identifiers it decides. If it does not correspond to a
   single profile rule, leave `covers` empty — it then contributes nothing to the
   coverage figure, which is the honest outcome.
3. Add a builder to `tests/fixtures/build.py` that changes **exactly one thing**
   from `valid_document()`.
4. Add the rule to `RULE_CASES` in `tests/test_rules_contract.py`.
5. Run the suite.

## The fixture design rule

`valid_document()` satisfies every rule. Each `*_violating` builder changes one
thing. If your builder changes two, a test for either rule can pass for the wrong
reason, which is worse than no test.

## What will be rejected

- **A check that guesses.** If a rule needs human judgement, it must set
  `confidence=Confidence.HEURISTIC` and say in its message that a human must
  confirm. See `TableHeaderRule` for the pattern.
- **A check that is stricter than the standard without saying so.** If you flag
  something the specification permits, the finding must state that explicitly.
  See the whitespace-`/Alt` branch in `FigureAltTextRule`.
- **A rule that reports per-instance when one finding suffices.** Reporting an
  untagged document's defect once per page buries the signal.
- **A silent skip.** A rule that cannot evaluate a document must raise
  `PdfuaError` with a reason, so it appears in `report.skipped`. Never return
  nothing and let it look like a pass.

## Development

```bash
uv venv
uv pip install -e ".[dev]"
.venv/bin/pytest
.venv/bin/mypy src/pdfua
.venv/bin/ruff check .
```

The suite must stay green, coverage at or above 80%, and `mypy --strict` must
pass with no `Any`. The package ships `py.typed`; annotations are part of the
public interface.

## Commits

Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`).
Small and focused. **Never use `--no-verify`** — if a hook fails, fix the cause.

## Reporting a false positive

This matters more than a missed detection. If the tool reports a problem in a
document that is actually fine, please open an issue with the document (or a
minimal reproduction) and the rule ID. A false positive is how accessibility
tooling loses its users' trust, and it is treated as a bug of the highest
severity.

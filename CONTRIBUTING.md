# Contributing to viyapy

Thanks for your interest in improving viyapy! This guide covers local setup, the
test tiers, and the contribution workflow.

## Development setup

```bash
git clone https://github.com/Shai-Alit/viyapy
cd viyapy
python -m pip install -e ".[dev]"   # runtime + dev tools
pre-commit install                  # ruff/mypy/hooks on commit
```

Use a Python between **3.9 and 3.13** for running the test suite (viyapy's
supported range). Newer interpreters are fine for building docs.

## Quality gates

All of these run in CI; run them locally before opening a PR. They are also
exposed as `nox` sessions so local and CI runs are identical:

```bash
nox -s lint      # ruff check + ruff format --check (incl. docstring rules)
nox -s type      # mypy --strict on src
nox -s test      # pytest with the coverage gate (>=90%)
nox -s docs      # mkdocs build --strict
```

Or directly: `ruff check src tests examples noxfile.py`, `mypy`, `pytest`.

Standards enforced by the gates: no bare/blind `except`, no `print` in library
code, full type hints (`mypy --strict`), docstrings on the public API
(pydocstyle, Google style), and ≥90% coverage on the package.

## Test tiers

| Tier | How to run | Notes |
|---|---|---|
| **Unit** | `pytest` | Mocked HTTP (`responses`); no network. The default. |
| **Property** | `pytest tests/unit/test_properties.py` | Hypothesis fuzzing of the input builder / output flattener. |
| **Example smoke** | `pytest tests/test_examples.py` | Imports + mock-runs `examples/` so they can't drift. |
| **Integration** | `pytest -m integration` | Opt-in; hits a real Viya. Skipped unless env is set. |

The integration tier reads per-generation environment variables and is skipped
by default — see [`tests/integration/README.md`](tests/integration/README.md).
No credentials are ever committed.

## Refreshing contract fixtures

Sanitized real-Viya payloads live under `tests/fixtures/<generation>/`
(`viya4/`, `viya35/`) and shared error shapes under `tests/fixtures/errors/`.
To refresh one, capture the real response from a Viya instance, **remove any
secrets, hostnames, and personal data**, and replace the corresponding JSON.
Keep the two generations' shapes distinct (notably MAS `output` vs `outputs`).

## Branch, commit, and PR conventions

- Branch off `main`; never push to `main` directly.
- Use [Conventional Commits](https://www.conventionalcommits.org/):
  `type(scope): summary` (`feat`, `fix`, `docs`, `test`, `chore`, `refactor`,
  `ci`). Keep commits scoped and logical.
- Every PR: green CI, a `CHANGELOG.md` entry under `[Unreleased]`, and updated
  docs/tests for any behavior change.
- PRs are reviewed before merge; `main` stays releasable at all times.

## Reporting bugs and security issues

Open a GitHub issue for bugs and feature requests using the templates. For
security vulnerabilities, follow [`SECURITY.md`](SECURITY.md) instead — please do
not open a public issue.

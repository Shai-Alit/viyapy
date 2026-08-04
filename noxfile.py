"""Nox sessions for viyapy.

Run everything:      nox
List sessions:       nox -l
Single session:      nox -s lint
These mirror CI exactly so local and pipeline runs are identical.
"""

from __future__ import annotations

import nox

nox.options.sessions = ["lint", "type", "test"]
nox.options.reuse_existing_virtualenvs = True

PYTHON_VERSIONS = ["3.9", "3.10", "3.11", "3.12", "3.13"]


@nox.session(python=PYTHON_VERSIONS)
def test(session: nox.Session) -> None:
    """Run the unit test suite with coverage (no network)."""
    session.install("-e", ".[dev]")
    session.run("pytest", *session.posargs)


@nox.session(python="3.11")
def lint(session: nox.Session) -> None:
    """Lint and check formatting with ruff."""
    session.install("ruff>=0.5")
    session.run("ruff", "check", "src", "tests", "examples", "noxfile.py")
    session.run("ruff", "format", "--check", "src", "tests", "examples", "noxfile.py")


@nox.session(python="3.11")
def format(session: nox.Session) -> None:
    """Auto-format the codebase with ruff."""
    session.install("ruff>=0.5")
    session.run("ruff", "format", "src", "tests", "examples", "noxfile.py")
    session.run("ruff", "check", "--fix", "src", "tests", "examples", "noxfile.py")


@nox.session(python="3.11")
def type(session: nox.Session) -> None:
    """Static type-check the package with mypy (strict)."""
    session.install("-e", ".[dev]")
    session.run("mypy")


@nox.session(python="3.11")
def audit(session: nox.Session) -> None:
    """Security + supply-chain checks (mirrors the Security workflow)."""
    session.install("pip-audit", "bandit")
    session.run("pip-audit", ".")
    session.run("bandit", "-r", "src", "--severity-level", "high", "--confidence-level", "medium")


@nox.session(python="3.11")
def docs(session: nox.Session) -> None:
    """Build the documentation site (fails on warnings)."""
    session.install("-e", ".[docs]")
    session.run("mkdocs", "build", "--strict")


@nox.session(python="3.11")
def build(session: nox.Session) -> None:
    """Build sdist + wheel and validate metadata."""
    session.install("build", "twine")
    session.run("python", "-m", "build")
    session.run("twine", "check", "dist/*")

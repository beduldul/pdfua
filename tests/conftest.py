"""Shared pytest fixtures.

The PDF fixtures are built in code at session scope so the whole suite shares
one build. Nothing binary is committed.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pikepdf
import pytest

sys.path.insert(0, str(Path(__file__).parent))

from fixtures import build


@pytest.fixture(scope="session")
def fixture_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A directory holding every generated fixture PDF."""
    return tmp_path_factory.mktemp("pdfua-fixtures")


@pytest.fixture(scope="session")
def write_pdf(fixture_dir: Path) -> Callable[[str, pikepdf.Pdf], Path]:
    """Return a helper that saves a built PDF under a given name."""

    def _write(name: str, pdf: pikepdf.Pdf) -> Path:
        path = fixture_dir / f"{name}.pdf"
        pdf.save(path)
        return path

    return _write


@pytest.fixture(scope="session")
def valid_pdf(write_pdf: Callable[[str, pikepdf.Pdf], Path]) -> Path:
    """A PDF that satisfies every implemented rule."""
    return write_pdf("valid", build.valid_document())


@pytest.fixture(scope="session")
def violating_pdfs(
    write_pdf: Callable[[str, pikepdf.Pdf], Path],
) -> dict[str, Path]:
    """Map fixture name to the path of a PDF violating exactly that one rule."""
    return {name: write_pdf(name, pdf) for name, pdf in build.all_violating()}


@pytest.fixture(scope="session")
def unreadable_pdf(fixture_dir: Path) -> Path:
    """A file that is not a PDF."""
    path = fixture_dir / "unreadable.pdf"
    path.write_bytes(build.unreadable())
    return path


@pytest.fixture
def pdf_builder() -> Iterator[Callable[[build.DocSpec], pikepdf.Pdf]]:
    """Yield a callable that builds a PDF from a :class:`build.DocSpec`."""
    yield build.build

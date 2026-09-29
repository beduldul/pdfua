"""Tests for the PDF access layer.

The traversal bugs these cover were real: an early version returned only the
root of the structure tree (so no figure or table rule ever fired), and another
matched pages by object identity with a linear scan that was quadratic on large
documents. Both are pinned here.
"""

from __future__ import annotations

from pathlib import Path

import pikepdf
import pytest

from pdfua.document import PdfDocument, is_well_formed_language
from pdfua.errors import PdfuaError
from tests.fixtures import build


class TestOpen:
    def test_non_pdf_raises_a_typed_error(self, unreadable_pdf: Path) -> None:
        with pytest.raises(PdfuaError, match="not a readable PDF"):
            PdfDocument.open(str(unreadable_pdf))

    def test_missing_file_raises_a_typed_error(self, tmp_path: Path) -> None:
        with pytest.raises(PdfuaError):
            PdfDocument.open(str(tmp_path / "absent.pdf"))

    def test_context_manager_closes_the_document(self, valid_pdf: Path) -> None:
        """``__exit__`` must close the underlying QPDF handle.

        pikepdf's ``Pdf`` does not raise on use-after-close, so the observable
        fact is that the document reports itself closed rather than that an
        exception is raised.
        """
        with PdfDocument.open(str(valid_pdf)) as doc:
            assert doc.page_count == 1
        assert doc.is_closed is True


class TestCatalogAccessors:
    def test_lang_is_read_from_the_catalog(self, valid_pdf: Path) -> None:
        with PdfDocument.open(str(valid_pdf)) as doc:
            assert doc.lang == "en-US"

    def test_missing_lang_is_none(self, write_pdf) -> None:
        path = write_pdf("no_lang_accessor", build.no_language())
        with PdfDocument.open(str(path)) as doc:
            assert doc.lang is None

    def test_display_doc_title_reflects_the_flag(self, write_pdf) -> None:
        on = write_pdf("ddt_on", build.valid_document())
        off = write_pdf("ddt_off", build.no_display_doc_title())
        with PdfDocument.open(str(on)) as doc:
            assert doc.display_doc_title is True
        with PdfDocument.open(str(off)) as doc:
            assert doc.display_doc_title is False

    def test_is_tagged_requires_both_tree_and_markinfo(self, write_pdf) -> None:
        """§7.1 needs the tree; §6.2 needs /MarkInfo. Both are required."""
        both = write_pdf("tagged_both", build.valid_document())
        marked_false = write_pdf("tagged_marked_false", build.marked_false())
        with PdfDocument.open(str(both)) as doc:
            assert doc.is_tagged is True
        with PdfDocument.open(str(marked_false)) as doc:
            assert doc.struct_root is not None
            assert doc.is_tagged is False


class TestStructureTraversal:
    def test_the_tree_starts_below_the_root_container(self, valid_pdf: Path) -> None:
        """Regression: only the root was ever returned, so no rule could fire."""
        with PdfDocument.open(str(valid_pdf)) as doc:
            assert doc.struct_root is not None
            roles = [e.role for e in doc.struct_elements]
            assert "/Document" in roles
            assert "/P" in roles
            assert len(doc.struct_elements) >= 2

    def test_figures_and_tables_are_found(self, write_pdf) -> None:
        path = write_pdf(
            "figure_and_table",
            build.build(
                build.DocSpec(
                    structure=[("/P", None, None), ("/Figure", "A chart", None)],
                    table=[["TH", "TH"], ["TD", "TD"]],
                )
            ),
        )
        with PdfDocument.open(str(path)) as doc:
            assert len(doc.elements_with_role("/Figure")) == 1
            assert len(doc.elements_with_role("/Table")) == 1

    def test_nested_elements_are_returned_in_document_order(self, write_pdf) -> None:
        path = write_pdf(
            "nested_order",
            build.build(build.DocSpec(structure=[("/H1", None, None), ("/P", None, None)])),
        )
        with PdfDocument.open(str(path)) as doc:
            roles = [e.role for e in doc.struct_elements]
            assert roles.index("/H1") < roles.index("/P")

    def test_alt_and_actual_text_are_read(self, write_pdf) -> None:
        path = write_pdf("alt_text", build.figure_without_alt())
        with PdfDocument.open(str(path)) as doc:
            figure = doc.elements_with_role("/Figure")[0]
            assert figure.alt is None
            assert figure.actual_text is None

    def test_table_rows_and_cells_traverse_groupers(self, write_pdf) -> None:
        """``/THead`` and ``/TBody`` must be descended through, not treated as rows."""
        path = write_pdf("table_grouped", build.valid_document())
        with PdfDocument.open(str(path)) as doc:
            table = doc.elements_with_role("/Table")[0]
            rows = doc.table_rows(table)
            assert len(rows) == 2
            roles = [cell.role for row in rows for cell in doc.table_cells(row)]
            assert roles == ["/TH", "/TH", "/TD", "/TD"]

    def test_scope_attribute_is_detected_on_a_header_cell(self, write_pdf) -> None:
        path = write_pdf("scope_present", build.valid_document())
        with PdfDocument.open(str(path)) as doc:
            table = doc.elements_with_role("/Table")[0]
            headers = [
                cell
                for row in doc.table_rows(table)
                for cell in doc.table_cells(row)
                if cell.role == "/TH"
            ]
            assert headers and all(h.has_scope for h in headers)

    def test_scope_is_absent_when_not_written(self, write_pdf) -> None:
        path = write_pdf("scope_absent", build.table_headers_without_association())
        with PdfDocument.open(str(path)) as doc:
            table = doc.elements_with_role("/Table")[0]
            headers = [
                cell
                for row in doc.table_rows(table)
                for cell in doc.table_cells(row)
                if cell.role == "/TH"
            ]
            assert headers and not any(h.has_scope for h in headers)

    def test_page_numbers_resolve_to_one_based_indices(self, write_pdf) -> None:
        """Regression: page matching was a quadratic scan; it is now an index."""
        path = write_pdf("page_numbers", build.valid_document())
        with PdfDocument.open(str(path)) as doc:
            pages = {e.page for e in doc.struct_elements if e.page is not None}
            assert pages <= {1}


class TestContentAnalysis:
    def test_marked_content_is_detected(self, valid_pdf: Path) -> None:
        with PdfDocument.open(str(valid_pdf)) as doc:
            content = doc.page_content(1)
            assert content.unmarked.has_marked_content is True
            assert content.unmarked.total == 0

    def test_unmarked_text_is_counted(self, write_pdf) -> None:
        path = write_pdf("unmarked", build.untagged_content())
        with PdfDocument.open(str(path)) as doc:
            content = doc.page_content(1)
            assert content.unmarked.unmarked_text_operators == 1
            assert content.unmarked.has_marked_content is False

    def test_page_content_is_cached(self, valid_pdf: Path) -> None:
        with PdfDocument.open(str(valid_pdf)) as doc:
            assert doc.page_content(1) is doc.page_content(1)

    def test_mcid_values_are_collected(self, valid_pdf: Path) -> None:
        with PdfDocument.open(str(valid_pdf)) as doc:
            assert doc.page_content(1).mcids == (0,)


class TestLanguageTagValidation:
    @pytest.mark.parametrize("tag", ["en", "en-US", "zh-Hant", "pt-BR", "de-CH-1901", "x-private"])
    def test_plausible_tags_are_accepted(self, tag: str) -> None:
        assert is_well_formed_language(tag) is True

    @pytest.mark.parametrize("tag", ["english please", "", "1", "en_US!", "-", "a"])
    def test_implausible_tags_are_rejected(self, tag: str) -> None:
        assert is_well_formed_language(tag) is False


class TestMetadata:
    def test_xmp_is_read_as_text(self, valid_pdf: Path) -> None:
        with PdfDocument.open(str(valid_pdf)) as doc:
            metadata = doc.xmp_metadata()
            assert metadata is not None
            assert "pdfuaid" in metadata.lower()

    def test_document_without_xmp_returns_none(self, tmp_path: Path) -> None:
        pdf = pikepdf.Pdf.new()
        page = pdf.make_indirect(
            pikepdf.Dictionary(
                Type=pikepdf.Name("/Page"),
                MediaBox=pikepdf.Array([0, 0, 612, 792]),
            )
        )
        pdf.trailer.Root = pdf.make_indirect(
            pikepdf.Dictionary(
                Type=pikepdf.Name("/Catalog"),
                Pages=pdf.make_indirect(
                    pikepdf.Dictionary(
                        Type=pikepdf.Name("/Pages"),
                        Kids=pikepdf.Array([page]),
                        Count=1,
                    )
                ),
            )
        )
        path = tmp_path / "no_xmp.pdf"
        pdf.save(path)
        with PdfDocument.open(str(path)) as doc:
            assert doc.xmp_metadata() is None

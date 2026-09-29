"""Build minimal PDFs in code, each violating exactly one rule.

No binary PDF is committed. Every fixture here is constructed with ``pikepdf``
at test time, which keeps the repository small, makes each fixture readable as
code, and means a fixture cannot silently rot into something other than what its
name claims.

The design rule for this module: :func:`valid_document` satisfies every
implemented rule, and each ``*_violating`` builder changes exactly one thing
relative to it. If a change makes two rules fire, the test for the other rule
would pass for the wrong reason.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from pikepdf import Array, Dictionary, Name, Pdf, String


@dataclass
class DocSpec:
    """A declarative description of the PDF to build.

    Every field defaults to the compliant choice, so a builder changes only what
    it means to change.
    """

    lang: str | None = "en-US"
    title: str | None = "A Test Document"
    display_doc_title: bool = True
    tagged: bool = True
    marked: bool = True
    pdfua_identifier: bool = True
    #: Structure elements to emit, as ``(role, alt_or_none, actual_text_or_none)``.
    structure: list[tuple[str, str | None, str | None]] = field(
        default_factory=lambda: [("/P", None, None)]
    )
    #: Table definition, emitted as a /Table when not None:
    #: ``(cell_roles,)`` where each entry is a row of roles like "TH"/"TD".
    table: list[list[str]] | None = None
    #: Wrap page content in a marked-content sequence with an /MCID.
    mark_page_content: bool = True
    #: Extra annotations to add, as ``(subtype, has_contents)``.
    annotations: list[tuple[str, bool]] = field(default_factory=list)
    #: Whether /TH cells carry an /A attribute dictionary with /Scope.
    header_scope: bool = True

    def content_stream(self) -> bytes:
        """Return a one-page content stream honouring :attr:`mark_page_content`."""
        text = b"BT /F1 12 Tf 72 720 Td (Fixture text) Tj ET"
        if not self.mark_page_content:
            return text
        return b"/P <</MCID 0>> BDC " + text + b" EMC"


def _xmp(spec: DocSpec) -> bytes:
    """Return an XMP packet, optionally declaring PDF/UA-1 conformance."""
    identification = ""
    if spec.pdfua_identifier:
        identification = (
            '  <rdf:Description xmlns:pdfuaid="http://www.aiim.org/pdfua/ns/id/">\n'
            "   <pdfuaid:part>1</pdfuaid:part>\n"
            "  </rdf:Description>\n"
        )
    return (
        '<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>\n'
        '<x:xmpmeta xmlns:x="adobe:ns:meta/">\n'
        ' <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
        '  <rdf:Description xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
        '   <dc:title><rdf:Alt><rdf:li xml:lang="x-default">'
        f"{spec.title or ''}"
        "</rdf:li></rdf:Alt></dc:title>\n"
        "  </rdf:Description>\n" + identification + " </rdf:RDF>\n"
        "</x:xmpmeta>\n"
        '<?xpacket end="w"?>\n'
    ).encode("utf-8")


def build(spec: DocSpec) -> Pdf:
    """Build a PDF matching ``spec``.

    The result is a single-page document with a font, an optional marked-content
    sequence, an optional structure tree, and metadata.
    """
    pdf = Pdf.new()

    font = pdf.make_indirect(
        Dictionary(
            Type=Name("/Font"),
            Subtype=Name("/Type1"),
            BaseFont=Name("/Helvetica"),
        )
    )

    page = pdf.make_indirect(
        Dictionary(
            Type=Name("/Page"),
            MediaBox=Array([0, 0, 612, 792]),
            Resources=Dictionary(Font=Dictionary(F1=font)),
        )
    )
    pages = pdf.make_indirect(Dictionary(Type=Name("/Pages"), Kids=Array([page]), Count=1))
    page.Parent = pages

    stream = pdf.make_stream(spec.content_stream())
    page.Contents = pdf.make_indirect(stream)

    root = Dictionary(Type=Name("/Catalog"), Pages=pages)
    if spec.lang is not None:
        root.Lang = String(spec.lang)
    if spec.display_doc_title:
        root.ViewerPreferences = Dictionary(DisplayDocTitle=True)
    if spec.marked:
        root.MarkInfo = Dictionary(Marked=True)

    if spec.tagged:
        struct_root = _build_structure(pdf, spec)
        root.StructTreeRoot = pdf.make_indirect(struct_root)
        root.ParentTree = pdf.make_indirect(_parent_tree(pdf, struct_root))

    root.Metadata = pdf.make_indirect(pdf.make_stream(_xmp(spec)))
    # pikepdf exposes Pdf.Root as a read-only property; the trailer entry is
    # writable, which is the supported way to install a new catalog.
    pdf.trailer.Root = pdf.make_indirect(root)

    if spec.title is not None:
        pdf.docinfo = pdf.make_indirect(Dictionary(Title=String(spec.title)))

    if spec.annotations:
        annots = Array()
        for subtype, has_contents in spec.annotations:
            entry = Dictionary(
                Type=Name("/Annot"),
                Subtype=Name(subtype),
                Rect=Array([0, 0, 10, 10]),
            )
            if has_contents:
                entry.Contents = String("A description of this annotation")
            annots.append(pdf.make_indirect(entry))
        page.Annots = annots

    return pdf


def _parent_tree(pdf: Pdf, struct_root: Dictionary) -> Dictionary:
    """Return a minimal /ParentTree covering the MCIDs used by the fixture."""
    return Dictionary(
        Nums=Array([0, Array([pdf.make_indirect(Dictionary(Type=Name("/MCR"), Pg=0, MCID=0))])])
    )


def _build_structure(pdf: Pdf, spec: DocSpec) -> Dictionary:
    """Return a /StructTreeRoot holding the elements described by ``spec``."""
    document = pdf.make_indirect(Dictionary(Type=Name("/StructElem"), S=Name("/Document")))
    kids = Array()

    for role, alt, actual_text in spec.structure:
        element = pdf.make_indirect(
            Dictionary(Type=Name("/StructElem"), S=Name(role), K=Array([0]))
        )
        if alt is not None:
            element.Alt = String(alt)
        if actual_text is not None:
            element.ActualText = String(actual_text)
        kids.append(element)

    if spec.table is not None:
        table = pdf.make_indirect(Dictionary(Type=Name("/StructElem"), S=Name("/Table")))
        rows = Array()
        for row_roles in spec.table:
            row = pdf.make_indirect(Dictionary(Type=Name("/StructElem"), S=Name("/TR")))
            cells = Array()
            for role in row_roles:
                attributes = None
                if role == "TH" and spec.header_scope:
                    # A header cell carries /Scope so the table's structure is
                    # machine-determinable, which is what §7.5 asks for. Omitting
                    # it is the separate `table_headers_without_association`
                    # fixture's whole point.
                    attributes = Dictionary(O=Name("/Table"), Scope=Name("/Column"))
                cell = pdf.make_indirect(
                    Dictionary(
                        Type=Name("/StructElem"),
                        S=Name(f"/{role}"),
                        K=Array([0]),
                        **({"A": pdf.make_indirect(attributes)} if attributes else {}),
                    )
                )
                cells.append(cell)
            row.K = cells
            rows.append(row)
        table.K = rows
        kids.append(table)

    document.K = kids
    return Dictionary(Type=Name("/StructTreeRoot"), K=Array([document]))


# --------------------------------------------------------------------- writers


def write(pdf: Pdf, path: str) -> str:
    """Save ``pdf`` to ``path`` and return the path."""
    pdf.save(path)
    return path


def valid_document() -> Pdf:
    """A document that satisfies every implemented rule."""
    return build(
        DocSpec(
            structure=[("/P", None, None)],
            table=[["TH", "TH"], ["TD", "TD"]],
        )
    )


# Each builder below changes exactly one thing from valid_document().


def untagged() -> Pdf:
    """No structure tree and no /MarkInfo."""
    return build(DocSpec(tagged=False, marked=False, mark_page_content=False))


def marked_false() -> Pdf:
    """Tagged, but /MarkInfo/Marked is false."""
    return build(DocSpec(marked=False))


def untagged_content() -> Pdf:
    """Tagged, but page content is not inside a marked-content sequence."""
    return build(DocSpec(mark_page_content=False))


def no_language() -> Pdf:
    """Tagged, but the catalog has no /Lang."""
    return build(DocSpec(lang=None))


def malformed_language() -> Pdf:
    """A /Lang that is not a plausible BCP-47 tag."""
    return build(DocSpec(lang="english please"))


def no_title() -> Pdf:
    """No /Title and no dc:title."""
    return build(DocSpec(title=None))


def no_display_doc_title() -> Pdf:
    """ViewerPreferences is absent."""
    return build(DocSpec(display_doc_title=False))


def no_pdfua_identifier() -> Pdf:
    """XMP present, but with no PDF/UA identification."""
    return build(DocSpec(pdfua_identifier=False))


def figure_without_alt() -> Pdf:
    """A /Figure with neither /Alt nor /ActualText."""
    return build(DocSpec(structure=[("/P", None, None), ("/Figure", None, None)]))


def figure_with_empty_alt() -> Pdf:
    """A /Figure whose /Alt is whitespace."""
    return build(DocSpec(structure=[("/P", None, None), ("/Figure", "   ", None)]))


def table_without_headers() -> Pdf:
    """A table with data cells and no /TH cells."""
    return build(DocSpec(table=[["TD", "TD"], ["TD", "TD"]]))


def table_headers_without_association() -> Pdf:
    """A table whose /TH cells carry no /Scope and no /Headers."""
    return build(DocSpec(table=[["TH", "TH"], ["TD", "TD"]], header_scope=False))


def link_without_description() -> Pdf:
    """A /Link annotation with no /Contents and no tagged /Link element."""
    return build(DocSpec(annotations=[("/Link", False)]))


def annotation_without_description() -> Pdf:
    """A /Text annotation with no /Contents."""
    return build(DocSpec(annotations=[("/Text", False)]))


def unreadable() -> bytes:
    """Bytes that are not a PDF at all."""
    return b"this is not a PDF\n"


def all_violating() -> Iterable[tuple[str, Pdf]]:
    """Yield ``(name, pdf)`` for every single-rule-violating fixture."""
    yield "untagged", untagged()
    yield "marked_false", marked_false()
    yield "untagged_content", untagged_content()
    yield "no_language", no_language()
    yield "no_title", no_title()
    yield "no_display_doc_title", no_display_doc_title()
    yield "no_pdfua_identifier", no_pdfua_identifier()
    yield "figure_without_alt", figure_without_alt()
    yield "table_without_headers", table_without_headers()
    yield "link_without_description", link_without_description()
    yield "annotation_without_description", annotation_without_description()

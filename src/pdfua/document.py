"""A thin, defensive access layer over ``pikepdf``.

Why ``pikepdf``: it is a mature binding to QPDF, ships manylinux/macOS/Windows
wheels (so ``pip install`` needs no compiler and no JVM), and exposes the COS
object graph that PDF/UA rules must inspect. ``pypdf`` was the alternative, but
its object model hides indirect references, and PDF/UA rules care about
reference identity and about ``/StructTreeRoot`` walking. ``pikepdf`` is the
right parser; this module is not one.

Everything here is total: a malformed PDF yields ``None`` or an empty tuple
rather than an exception. Rules decide what a missing value means.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import cast

import pikepdf
from pikepdf import Dictionary, Object, Pdf

# Text-showing operators per ISO 32000-1 Table 109.
TEXT_OPERATORS = frozenset({"Tj", "TJ", "'", '"'})
MARKED_CONTENT_BEGIN = frozenset({"BDC", "BMC"})
MARKED_CONTENT_END = "EMC"
XOBJECT_PAINT = "Do"

# Structural elements that group their children rather than being children.
_TABLE_GROUPERS = frozenset({"/THead", "/TBody", "/TFoot"})

_MAX_STRUCT_DEPTH = 256


@dataclass(frozen=True, slots=True)
class StructElement:
    """A node of the logical structure tree."""

    role: str | None
    obj: Dictionary
    page: int | None
    alt: str | None
    actual_text: str | None
    has_scope: bool
    has_headers: bool
    children: tuple[StructElement, ...] = ()


@dataclass(frozen=True, slots=True)
class UnmarkedContent:
    """Counts of content that is neither tagged nor marked as an artifact."""

    unmarked_text_operators: int = 0
    unmarked_xobjects: int = 0
    has_marked_content: bool = False

    @property
    def total(self) -> int:
        return self.unmarked_text_operators + self.unmarked_xobjects


@dataclass(frozen=True, slots=True)
class PageContent:
    """Per-page content statistics gathered in a single stream pass."""

    page_number: int
    unmarked: UnmarkedContent
    mcids: tuple[int, ...] = ()
    errors: tuple[str, ...] = field(default=())


class PdfDocument:
    """A read-only view of a PDF, with helpers PDF/UA rules need.

    Instances are used as context managers so the underlying file handle is
    always released::

        with PdfDocument.open("file.pdf") as doc:
            doc.struct_root is not None
    """

    def __init__(self, pdf: Pdf, path: str) -> None:
        self._pdf = pdf
        self.path = path
        self._struct_cache: tuple[StructElement, ...] | None = None
        self._content_cache: dict[int, PageContent] = {}
        self._page_index: dict[tuple[int, int], int] | None = None
        self._closed = False

    # ---------------------------------------------------------------- open

    @classmethod
    def open(cls, path: str) -> PdfDocument:
        """Open ``path`` for reading.

        Raises:
            PdfuaError: if the file cannot be parsed as a PDF.
        """
        from .errors import PdfuaError

        try:
            return cls(Pdf.open(path), path)
        except pikepdf.PasswordError as exc:
            raise PdfuaError(
                f"{path}: encrypted and no password supplied; PDF/UA checks "
                "cannot run on an encrypted document"
            ) from exc
        except (pikepdf.PdfError, OSError, ValueError) as exc:
            raise PdfuaError(f"{path}: not a readable PDF ({exc})") from exc

    def close(self) -> None:
        """Release the underlying file handle. Safe to call more than once.

        pikepdf exposes no ``is_closed``, so the flag is tracked here. Without
        it, a caller cannot tell a released handle from an open one, and the
        context-manager contract is untestable.
        """
        if not self._closed:
            self._pdf.close()
            self._closed = True

    @property
    def is_closed(self) -> bool:
        """True once :meth:`close` has run."""
        return self._closed

    def __enter__(self) -> PdfDocument:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # ------------------------------------------------------------ catalog

    @property
    def root(self) -> Dictionary:
        """The document catalog.

        pikepdf types ``Pdf.Root`` as a generic handle. For any PDF that QPDF
        parsed, the trailer ``/Root`` is a dictionary, and pikepdf raises at
        open time otherwise, so the cast reflects an invariant the parser
        already enforces rather than suppressing a real possibility.
        """
        return cast(Dictionary, self._pdf.Root)

    @property
    def struct_root(self) -> Dictionary | None:
        """The ``/StructTreeRoot``, or ``None`` if the document is untagged."""
        try:
            value = self.root.get("/StructTreeRoot")
        except Exception:
            return None
        return value if isinstance(value, Dictionary) else None

    @property
    def is_tagged(self) -> bool:
        """True when ``/StructTreeRoot`` exists and ``/MarkInfo/Marked`` is true.

        PDF/UA-1 §6.2 requires ``/MarkInfo`` with ``/Marked true``; §7.1
        requires the structure tree. Both are needed to call a file tagged.
        """
        return self.struct_root is not None and self.marked

    @property
    def marked(self) -> bool:
        try:
            mark_info = self.root.get("/MarkInfo")
        except Exception:
            return False
        return bool(isinstance(mark_info, Dictionary) and mark_info.get("/Marked"))

    @property
    def lang(self) -> str | None:
        """The catalog ``/Lang`` value, or ``None``."""
        return self._text(self.root.get("/Lang"))

    @property
    def title(self) -> str | None:
        """``/Info /Title``, or ``None``."""
        try:
            info = self._pdf.trailer.get("/Info")
        except Exception:
            return None
        if not isinstance(info, Dictionary):
            return None
        return self._text(info.get("/Title"))

    @property
    def display_doc_title(self) -> bool:
        """True when ``/ViewerPreferences /DisplayDocTitle`` is true."""
        try:
            prefs = self.root.get("/ViewerPreferences")
        except Exception:
            return False
        return bool(isinstance(prefs, Dictionary) and prefs.get("/DisplayDocTitle"))

    @property
    def page_count(self) -> int:
        return len(self._pdf.pages)

    def page_labels(self) -> dict[int, str]:
        """Map 1-based page index to the value of a ``/Lang`` on the page object."""
        out: dict[int, str] = {}
        for index, page in enumerate(self._pdf.pages, start=1):
            value = self._text(page.obj.get("/Lang"))
            if value is not None:
                out[index] = value
        return out

    # ------------------------------------------------------- structure tree

    @property
    def struct_elements(self) -> tuple[StructElement, ...]:
        """Every element of the structure tree, in document order, cached.

        The ``/StructTreeRoot`` is a container rather than an element; the tree
        starts at its ``/K`` children (normally a single ``/Document`` element).
        The flat sequence is what rules iterate, so it is built once.
        """
        if self._struct_cache is None:
            root = self.struct_root
            if root is None:
                self._struct_cache = ()
            else:
                self._struct_cache = tuple(
                    element for kid in self._kids(root) for element in self._walk(kid, 0, None)
                )
        return self._struct_cache

    def _walk(self, node: Object, depth: int, page: int | None) -> Iterator[StructElement]:
        """Yield ``node`` and every element beneath it, depth-first, parent first."""
        element = self._build(node, depth, page)
        if element is None:
            return
        yield element
        for child in element.children:
            yield from self._walk(child.obj, depth + 1, element.page)

    def _build(self, node: Object, depth: int, page: int | None) -> StructElement | None:
        """Build one :class:`StructElement` with its *direct* children resolved."""
        if depth > _MAX_STRUCT_DEPTH or not isinstance(node, Dictionary):
            return None
        current_page = page
        page_ref = node.get("/Pg")
        if page_ref is not None:
            current_page = self._page_number(page_ref) or page
        children: list[StructElement] = []
        for kid in self._kids(node):
            built = self._build(kid, depth + 1, current_page)
            if built is not None:
                children.append(built)
        attributes = self._attribute_dicts(node)
        return StructElement(
            role=self._name(node.get("/S")),
            obj=node,
            page=current_page,
            alt=self._text(node.get("/Alt")),
            actual_text=self._text(node.get("/ActualText")),
            has_scope=any(a.get("/Scope") is not None for a in attributes),
            has_headers=node.get("/Headers") is not None
            or any(a.get("/Headers") is not None for a in attributes),
            children=tuple(children),
        )

    def _kids(self, node: Dictionary) -> Iterator[Object]:
        if "/K" not in node:
            return
        kid = node.K
        if isinstance(kid, pikepdf.Array):
            yield from kid
        else:
            yield kid

    def _attribute_dicts(self, node: Dictionary) -> tuple[Dictionary, ...]:
        """Return the element's attribute dictionaries.

        ``/A`` may be a single dictionary, an array of dictionaries, or a
        reference to a property list. Only direct dictionaries are resolved;
        property lists are skipped rather than guessed at.
        """
        value = node.get("/A")
        if value is None:
            return ()
        candidates = list(value) if isinstance(value, pikepdf.Array) else [value]
        return tuple(c for c in candidates if isinstance(c, Dictionary))

    def elements_with_role(self, *roles: str) -> tuple[StructElement, ...]:
        """Return every structure element whose role is in ``roles``."""
        wanted = set(roles)
        return tuple(e for e in self.struct_elements if e.role in wanted)

    def direct_children(
        self, element: StructElement, *, unwrap: bool = True
    ) -> tuple[StructElement, ...]:
        """Return ``element``'s direct children.

        With ``unwrap``, ``/THead``/``/TBody``/``/TFoot`` grouping nodes are
        replaced by their own children. PDF/UA table rules operate on the
        ``/TR`` rows inside those groups, and treating the group as a row
        produces false positives.
        """
        out: list[StructElement] = []
        for child in element.children:
            if unwrap and child.role in _TABLE_GROUPERS:
                out.extend(self.direct_children(child, unwrap=True))
            else:
                out.append(child)
        return tuple(out)

    def table_rows(self, table: StructElement) -> tuple[StructElement, ...]:
        """Return the ``/TR`` rows of ``table``, descending through groupers."""
        return tuple(c for c in self.direct_children(table) if c.role == "/TR")

    def table_cells(self, row: StructElement) -> tuple[StructElement, ...]:
        """Return the ``/TH`` and ``/TD`` cells of ``row``."""
        return tuple(c for c in self.direct_children(row, unwrap=False) if c.role in ("/TH", "/TD"))

    # ------------------------------------------------------- content streams

    @property
    def pages(self) -> tuple[PageContent, ...]:
        """Per-page content statistics, computed once and cached."""
        return tuple(self.page_content(i) for i in range(1, self.page_count + 1))

    def page_content(self, page_number: int) -> PageContent:
        """Analyse page ``page_number`` (1-based) for marked content."""
        if page_number in self._content_cache:
            return self._content_cache[page_number]
        result = self._analyse_page(page_number)
        self._content_cache[page_number] = result
        return result

    def _analyse_page(self, page_number: int) -> PageContent:
        errors: list[str] = []
        try:
            page = self._pdf.pages[page_number - 1]
        except (IndexError, pikepdf.PdfError) as exc:
            return PageContent(page_number, UnmarkedContent(), (), (f"page not readable: {exc}",))
        try:
            stream = list(pikepdf.parse_content_stream(page))
        except Exception as exc:
            return PageContent(
                page_number, UnmarkedContent(), (), (f"content stream not parseable: {exc}",)
            )

        depth = 0
        seen_marked = False
        unmarked_text = 0
        unmarked_xobject = 0
        mcids: list[int] = []
        for instruction in stream:
            # parse_content_stream yields either ContentStreamInstruction or
            # ContentStreamInlineImage. Inline images (BI ... ID ... EI) are
            # image data, not operators, so they are skipped rather than
            # unpacked: treating one as an operator would be a type error and a
            # counting error.
            if isinstance(instruction, pikepdf.ContentStreamInlineImage):
                continue
            operands, operator = instruction.operands, instruction.operator
            op = str(operator)
            if op in MARKED_CONTENT_BEGIN:
                depth += 1
                seen_marked = True
                mcid = self._mcid_from_operands(operands)
                if mcid is not None:
                    mcids.append(mcid)
            elif op == MARKED_CONTENT_END:
                depth = max(0, depth - 1)
            elif op in TEXT_OPERATORS:
                if depth == 0:
                    unmarked_text += 1
            elif op == XOBJECT_PAINT:
                if depth == 0:
                    unmarked_xobject += 1
        return PageContent(
            page_number=page_number,
            unmarked=UnmarkedContent(unmarked_text, unmarked_xobject, seen_marked),
            mcids=tuple(sorted(set(mcids))),
            errors=tuple(errors),
        )

    @staticmethod
    def _mcid_from_operands(operands: pikepdf._core._ObjectList) -> int | None:
        """Extract ``/MCID`` from the operands of a ``BDC``/``BMC`` operator."""
        if not operands:
            return None
        properties = operands[-1]
        if isinstance(properties, Dictionary):
            return as_integer(properties.get("/MCID"))
        return None

    # ------------------------------------------------------------- metadata

    def xmp_metadata(self) -> str | None:
        """Return the document's XMP packet as text, or ``None``.

        ``open_metadata()`` synthesises an empty packet when the catalog has no
        ``/Metadata`` entry, so its output cannot distinguish "no XMP" from
        "empty XMP". The presence check is therefore done on the catalog first:
        a document that declares nothing must not be reported as declaring
        something empty.
        """
        if self.root.get("/Metadata") is None:
            return None
        try:
            with self._pdf.open_metadata() as meta:
                return str(meta)
        except Exception:
            return None

    # --------------------------------------------------------------- utils

    @staticmethod
    def _name(value: Object | None) -> str | None:
        if value is None:
            return None
        text = str(value)
        return text if text.startswith("/") else None

    @staticmethod
    def _text(value: Object | None) -> str | None:
        if value is None:
            return None
        try:
            return str(value)
        except Exception:
            return None

    def _page_index_map(self) -> dict[tuple[int, int], int]:
        """Map each page's ``(obj, gen)`` to its 1-based index, built once.

        Structure elements reference their page by object, and a linear scan per
        element is quadratic on large documents (a 1,000-page PDF with 26,000
        elements is 26 million comparisons). QPDF exposes the object number and
        generation, which are unique per indirect object, so a dict lookup
        replaces the scan.
        """
        if self._page_index is None:
            index: dict[tuple[int, int], int] = {}
            for position, page in enumerate(self._pdf.pages, start=1):
                objgen = getattr(page.obj, "objgen", None)
                if objgen is not None:
                    index[(int(objgen[0]), int(objgen[1]))] = position
            self._page_index = index
        return self._page_index

    def _page_number(self, page_ref: Object) -> int | None:
        objgen = getattr(page_ref, "objgen", None)
        if objgen is None:
            return None
        return self._page_index_map().get((int(objgen[0]), int(objgen[1])))


# Standard tags, plus the two BCP-47 forms that do not start with a 2-3 letter
# primary subtag: private-use ("x-...") and grandfathered ("i-...", "sgn-...").
# Accepting them matters because a validator that rejects a legal tag produces a
# false positive, and a wrong language tag is worse than a missing check.
def as_integer(value: object) -> int | None:
    """Return ``value`` as an int when it is numeric, otherwise ``None``.

    ``pikepdf`` returns a plain Python ``int`` for a numeric object such as
    ``/MCID``, but annotates ``Dictionary.get`` as returning ``Object``, whose
    stubs do not model the int subclassing. Typing the parameter as ``object``
    makes the ``isinstance`` check meaningful to a type checker *and* correct at
    runtime, which a cast would not.

    Booleans are excluded: ``True`` is an ``int`` in Python, and a boolean where
    a number is expected is a malformed file, not the number one.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return int(value)
    if getattr(value, "is_integer", False) is True:
        # pikepdf objects are int-convertible for numeric values, but the stubs
        # do not declare SupportsInt, so the conversion goes through str-free
        # indexing on the object's own int representation.
        numeric = value.__int__() if hasattr(value, "__int__") else None
        return numeric if isinstance(numeric, int) else None
    return None


_BCP47 = re.compile(
    r"^(?:"
    r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{1,8})*"  # en, en-US, zh-Hant, de-CH-1901
    r"|x(?:-[A-Za-z0-9]{1,8})+"  # private use: x-private
    r"|i(?:-[A-Za-z0-9]{1,8})+"  # grandfathered: i-klingon
    r"|sgn(?:-[A-Za-z0-9]{1,8})+"  # sign languages: sgn-BE-FR
    r")$"
)


def is_well_formed_language(tag: str) -> bool:
    """Return True if ``tag`` is a syntactically plausible BCP-47 language tag.

    This checks shape only. It does not verify that the subtag is registered,
    and it deliberately accepts the private-use and grandfathered forms that a
    strict registry lookup would reject.
    """
    return bool(_BCP47.match(tag.strip()))


__all__ = [
    "PageContent",
    "PdfDocument",
    "StructElement",
    "UnmarkedContent",
    "as_integer",
    "is_well_formed_language",
]

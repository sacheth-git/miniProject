"""PDF text extraction with two-column layout handling (PyMuPDF)."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

import fitz  # PyMuPDF

from app.core.logging import get_logger

log = get_logger(__name__)

MAX_PAGES = 10
# A block "belongs" to a column if it lies fully on one side of the gutter (+/- tolerance).
GUTTER_TOLERANCE = 0.04


class PDFParseError(ValueError):
    """The upload is not a readable PDF or contains no extractable text."""


@dataclass
class Block:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    page: int


@dataclass
class ParsedPDF:
    text: str
    pages: int
    two_column_pages: list[int] = field(default_factory=list)


def _clean(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)  # ligatures (ﬀ -> "ff"), full-width chars
    text = text.replace(" ", " ").replace("​", "")
    text = re.sub(r"[ \t]+", " ", text)
    # Normalise common bullet glyphs to "-" so line-based heuristics see them.
    text = re.sub(r"^[•●▪◦‣⁃➢►*]\s*", "- ", text, flags=re.M)
    return text.strip()


def find_gutter(blocks: list[Block], page_width: float) -> float | None:
    """Find a vertical line that splits the page into two text columns.

    Scans x positions in the middle 60% of the page and picks the one crossed by
    the fewest blocks. It qualifies as a gutter if at most 25% of blocks cross it
    (name headers / footers may span), each side has >= 2 blocks, and the smaller
    side holds >= 15% of the text (so right-aligned dates don't count as a column).
    """
    total_chars = sum(len(b.text) for b in blocks) or 1
    best: tuple[int, float, float] | None = None  # (crossings, -balance, x)
    x = page_width * 0.2
    while x <= page_width * 0.8:
        crossing = sum(1 for b in blocks if b.x0 < x < b.x1)
        left = [b for b in blocks if b.x1 <= x]
        right = [b for b in blocks if b.x0 >= x]
        if len(left) >= 2 and len(right) >= 2 and crossing <= 0.25 * len(blocks):
            lc = sum(len(b.text) for b in left) / total_chars
            rc = sum(len(b.text) for b in right) / total_chars
            if min(lc, rc) >= 0.15:
                key = (crossing, -min(lc, rc), x)
                if best is None or key < best:
                    best = key
        x += page_width * GUTTER_TOLERANCE / 4
    return best[2] if best else None


def order_blocks(blocks: list[Block], page_width: float) -> tuple[list[Block], bool]:
    """Return blocks in reading order and whether the page looked two-column.

    Full-width blocks above the columns (e.g. a name header) come first, then the
    left column top-to-bottom, then the right column, then any full-width blocks below.
    """
    if not blocks:
        return [], False
    gutter = find_gutter(blocks, page_width)
    if gutter is None:
        return sorted(blocks, key=lambda b: (round(b.y0, 1), b.x0)), False
    left = [b for b in blocks if b.x1 <= gutter]
    right = [b for b in blocks if b.x0 >= gutter]
    spanning = [b for b in blocks if b.x0 < gutter < b.x1]

    col_top = min(b.y0 for b in left + right)
    header = [b for b in spanning if b.y1 <= col_top + 1]
    footer = [b for b in spanning if b not in header]
    by_y = lambda b: (b.y0, b.x0)  # noqa: E731
    ordered = sorted(header, key=by_y) + sorted(left, key=by_y) + sorted(right, key=by_y) + sorted(footer, key=by_y)
    return ordered, True


def extract_text(pdf_bytes: bytes) -> ParsedPDF:
    if not pdf_bytes.startswith(b"%PDF"):
        raise PDFParseError("File is not a PDF")
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except (fitz.FileDataError, RuntimeError) as exc:
        raise PDFParseError(f"Cannot open PDF: {exc}") from exc

    parts: list[str] = []
    two_col: list[int] = []
    with doc:
        if doc.needs_pass:
            raise PDFParseError("PDF is password protected")
        for pno, page in enumerate(doc):
            if pno >= MAX_PAGES:
                log.warning("Resume has more than %d pages; truncating", MAX_PAGES)
                break
            raw = page.get_text("blocks", sort=False)
            blocks = [
                Block(x0, y0, x1, y1, txt, pno)
                for (x0, y0, x1, y1, txt, _bno, btype) in raw
                if btype == 0 and txt.strip()
            ]
            ordered, is_two = order_blocks(blocks, page.rect.width)
            if is_two:
                two_col.append(pno)
            parts.extend(_clean(b.text) for b in ordered)
        n_pages = min(len(doc), MAX_PAGES)

    text = "\n".join(p for p in parts if p)
    if len(text) < 30:
        raise PDFParseError("No extractable text (scanned PDF? OCR is not supported)")
    return ParsedPDF(text=text, pages=n_pages, two_column_pages=two_col)

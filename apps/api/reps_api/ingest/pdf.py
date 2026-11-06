"""PDF text extraction and chunking for course material.

Every chunk remembers its page, so a generated question can cite where its
answer comes from. Scanned PDFs (images with no text layer) are detected and
refused with a clear message instead of being "processed" into nothing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import pymupdf

MAX_BYTES = 25 * 1024 * 1024
MAX_PAGES = 400
MIN_CHARS_PER_PAGE = 40  # below this on average, assume there's no text layer
CHUNK_TARGET = 1200  # characters
CHUNK_OVERLAP = 150


class ExtractionError(ValueError):
    """The file can't be used as source material. Message is safe to show users."""


@dataclass(frozen=True)
class Page:
    number: int  # 1-based
    text: str


@dataclass(frozen=True)
class Chunk:
    index: int
    page_start: int
    page_end: int
    text: str


@dataclass(frozen=True)
class Extraction:
    pages: list[Page]
    chunks: list[Chunk]
    page_count: int
    text_pages: int
    char_count: int


def _clean(text: str) -> str:
    text = text.replace("­", "")  # soft hyphens
    text = re.sub(r"-\n(?=[a-z])", "", text)  # words split across lines
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_pdf(data: bytes) -> Extraction:
    if len(data) > MAX_BYTES:
        raise ExtractionError(f"File is larger than {MAX_BYTES // (1024 * 1024)} MB.")
    if not data.startswith(b"%PDF"):
        raise ExtractionError("That file isn't a PDF.")
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as err:
        raise ExtractionError("The PDF couldn't be opened. It may be corrupted.") from err
    with doc:
        if doc.needs_pass:
            raise ExtractionError("The PDF is password-protected. Remove the password and upload it again.")
        if doc.page_count == 0:
            raise ExtractionError("The PDF has no pages.")
        if doc.page_count > MAX_PAGES:
            raise ExtractionError(f"The PDF has more than {MAX_PAGES} pages. Split it and upload the parts.")
        pages = [Page(number=i + 1, text=_clean(page.get_text("text"))) for i, page in enumerate(doc)]

    char_count = sum(len(p.text) for p in pages)
    text_pages = sum(1 for p in pages if len(p.text) >= MIN_CHARS_PER_PAGE)
    if char_count / len(pages) < MIN_CHARS_PER_PAGE or text_pages == 0:
        raise ExtractionError("This PDF looks scanned (no selectable text). OCR isn't set up yet, so upload a PDF exported from the original slides or notes.")
    return Extraction(pages=pages, chunks=chunk_pages(pages), page_count=len(pages), text_pages=text_pages, char_count=char_count)


def chunk_pages(pages: list[Page], target: int = CHUNK_TARGET, overlap: int = CHUNK_OVERLAP) -> list[Chunk]:
    """Pack paragraphs into ~target-sized chunks without splitting mid-paragraph
    when possible, carrying a short overlap so a concept on a boundary appears whole."""
    units: list[tuple[int, str]] = []
    for page in pages:
        for para in re.split(r"\n\s*\n", page.text):
            para = para.strip()
            while len(para) > target:  # a single giant paragraph gets hard-split
                cut = para.rfind(" ", 0, target)
                cut = cut if cut > target // 2 else target
                units.append((page.number, para[:cut]))
                para = para[cut:].strip()
            if para:
                units.append((page.number, para))

    chunks: list[Chunk] = []
    buf: list[tuple[int, str]] = []
    size = 0
    for page_no, para in units:
        if buf and size + len(para) > target:
            chunks.append(_make_chunk(len(chunks), buf))
            tail = buf[-1]
            buf = [tail] if len(tail[1]) <= overlap else [(tail[0], tail[1][-overlap:])]
            size = len(buf[0][1])
        buf.append((page_no, para))
        size += len(para) + 2
    if buf:
        chunks.append(_make_chunk(len(chunks), buf))
    return chunks


def _make_chunk(index: int, buf: list[tuple[int, str]]) -> Chunk:
    return Chunk(index=index, page_start=buf[0][0], page_end=buf[-1][0], text="\n\n".join(p for _, p in buf))


def combine(named: list[tuple[str, Extraction]]) -> Extraction:
    """Merge several PDFs into one source. Pages are numbered straight through, and each chunk names its file."""
    pages: list[Page] = []
    chunks: list[Chunk] = []
    offset = 0
    for name, ex in named:
        label = f"[{name}] " if len(named) > 1 else ""
        pages += [Page(number=pg.number + offset, text=pg.text) for pg in ex.pages]
        for c in ex.chunks:
            chunks.append(Chunk(index=len(chunks), page_start=c.page_start + offset, page_end=c.page_end + offset, text=label + c.text))
        offset += ex.page_count
    return Extraction(
        pages=pages,
        chunks=chunks,
        page_count=sum(ex.page_count for _, ex in named),
        text_pages=sum(ex.text_pages for _, ex in named),
        char_count=sum(ex.char_count for _, ex in named),
    )


TEXT_PAGE_CHARS = 3000


def extract_text(text: str) -> Extraction:
    """Pasted notes or a .txt/.md file: split into ~3,000-character "pages" on paragraph breaks."""
    text = _clean(text.replace("\r\n", "\n"))
    if len(text.strip()) < 200:
        raise ExtractionError("That's too little text to build questions from. Paste at least a paragraph or two.")
    pages: list[Page] = []
    buf = ""
    for para in re.split(r"\n\s*\n", text):
        if buf and len(buf) + len(para) > TEXT_PAGE_CHARS:
            pages.append(Page(number=len(pages) + 1, text=buf.strip()))
            buf = ""
        buf += para + "\n\n"
    if buf.strip():
        pages.append(Page(number=len(pages) + 1, text=buf.strip()))
    return Extraction(pages=pages, chunks=chunk_pages(pages), page_count=len(pages), text_pages=len(pages), char_count=sum(len(p.text) for p in pages))

"""Word (.docx) and PowerPoint (.pptx) text, read with the standard library.

Both formats are zip files of XML. A .docx becomes ~3,000-character pages split on
paragraphs; a .pptx becomes one page per slide, so page numbers are slide numbers.
"""

from __future__ import annotations

import io
import re
import zipfile
from xml.etree import ElementTree

from .pdf import Extraction, ExtractionError, Page, chunk_pages, extract_text

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
MAX_UNZIPPED = 80 * 1024 * 1024


def _open(data: bytes, kind: str) -> zipfile.ZipFile:
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as err:
        raise ExtractionError(f"That isn't a readable {kind} file.") from err
    if sum(i.file_size for i in z.infolist()) > MAX_UNZIPPED:
        raise ExtractionError(f"That {kind} file is too large once unpacked.")
    return z


def _paragraphs(xml: bytes, para_tag: str, text_tag: str) -> list[str]:
    root = ElementTree.fromstring(xml)
    out = []
    for p in root.iter(para_tag):
        text = "".join(t.text or "" for t in p.iter(text_tag)).strip()
        if text:
            out.append(text)
    return out


def extract_docx(data: bytes) -> Extraction:
    z = _open(data, "Word")
    if "word/document.xml" not in z.namelist():
        raise ExtractionError("That Word file has no document body.")
    paras = _paragraphs(z.read("word/document.xml"), f"{W}p", f"{W}t")
    # Short lines with no full stop read as headings, so keep each paragraph on its own line block.
    return extract_text("\n\n".join(paras))


def extract_pptx(data: bytes) -> Extraction:
    z = _open(data, "PowerPoint")
    slides = sorted(
        (n for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
        key=lambda n: int(re.search(r"(\d+)", n.rsplit("/", 1)[1]).group(1)),
    )
    if not slides:
        raise ExtractionError("That PowerPoint file has no slides.")
    pages = []
    for i, name in enumerate(slides):
        paras = _paragraphs(z.read(name), f"{A}p", f"{A}t")
        if not paras:
            continue
        # The first text box is usually the slide title: keep it as a heading line.
        body = "\n".join(b if b.endswith((".", "!", "?")) else b + "." for b in paras[1:])
        text = paras[0] + "\n\n" + body
        pages.append(Page(number=i + 1, text=text.strip()))
    if sum(len(p.text) for p in pages) < 200:
        raise ExtractionError("Those slides have too little text to build questions from.")
    return Extraction(pages=pages, chunks=chunk_pages(pages), page_count=len(slides), text_pages=len(pages), char_count=sum(len(p.text) for p in pages))

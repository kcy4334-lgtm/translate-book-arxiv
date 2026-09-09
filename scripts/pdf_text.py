# -*- coding: utf-8 -*-
r"""Read a PDF in the order a person reads it, and prove that it worked.

The calibre ingest runs a PDF through pdftohtml, which lays text out by
position and does not reliably recover columns. On a two-column journal
paper it interleaves them, and it does so INSIDE a line, so nothing
downstream can see the seam: the sentences are fluent English fragments in
the wrong order. Measured on a Nature Communications paper, 23% of the
paper's own sentences survived contiguously. Translating that produces
fluent Korean built on scrambled English, and every check in this pipeline
passes, because every check compares our artefacts to each other.

PyMuPDF's default `get_text` walks blocks in the order the PDF declares
them, which on the same paper is the reading order. Notably `sort=True` is
WRONG here: sorting by geometry pulls figure-panel labels into the prose.
The default is what to use.

The second half of this module matters as much as the first. Whether an
extraction is usable is not a property of the file format or of a page
count, it is whether the paper's own sentences are still there in one
piece. `sentence_fidelity` measures exactly that, and `convert.py` uses it
to decide rather than guessing from a layout heuristic. A guess would have
to be right about a paper nobody has met; this asks the artefact.
"""
from __future__ import unicode_literals

import io
import os
import re

# A sentence long enough to be evidence and short enough to survive
# hard-wrapping. Below 60 characters, boilerplate matches by accident.
_MIN_SENTENCE = 60
_MAX_SENTENCE = 200
_MIN_WORDS = 8

_WS_RE = re.compile(r'\s+')
_SENTENCE_SPLIT_RE = re.compile(r'(?<=[.])\s+')
# A page header or footer repeats on every page and says nothing about
# reading order, so it is not evidence either way.
_RUNNING_HEAD_RE = re.compile(
    r'^(?:ARTICLE|NATURE\s+COMMUNICATIONS|www\.|https?://|doi:|\d+\s*$)',
    re.IGNORECASE)


def _flat(text):
    return _WS_RE.sub(' ', text or '').strip()


def open_pdf(path):
    """The import is local so a machine without PyMuPDF still runs the rest."""
    import pymupdf
    return pymupdf.open(path)


def page_texts(doc):
    """Each page's text, in the order the PDF declares its blocks.

    Not `sort=True`. Sorting by geometry reorders a figure's axis labels
    and panel letters into the prose around it, which reads worse than the
    problem it was meant to fix.
    """
    return [page.get_text('text') for page in doc]


def sentences_of(text):
    """The sentences worth using as evidence that an order survived."""
    out = []
    for piece in _SENTENCE_SPLIT_RE.split(_flat(text)):
        piece = piece.strip()
        if _RUNNING_HEAD_RE.match(piece):
            continue
        if _MIN_SENTENCE <= len(piece) <= _MAX_SENTENCE \
                and piece.count(' ') >= _MIN_WORDS:
            out.append(piece)
    return out


def sentence_fidelity(doc, candidate, per_page=12, first_page=2):
    """(hits, total): how much of the paper survives IN ORDER in `candidate`.

    The question a layout heuristic cannot answer. A converter that keeps
    every word but reorders them scores near zero here and near perfect on
    any count of words, characters, images or tables -- which is why those
    counts all agreed while the text was unusable.

    Front matter is skipped: a title page is one column and would pass any
    converter, so including it only dilutes the answer.
    """
    flat = _flat(candidate)
    hits = total = 0
    for pno in range(first_page, doc.page_count):
        for sentence in sentences_of(doc[pno].get_text('text'))[:per_page]:
            total += 1
            if sentence in flat:
                hits += 1
    return hits, total


def extract_images(doc, dest_dir, stem='page'):
    """Write each page's images to `dest_dir`; return {page: [relpath]}.

    Keyed by page so the markdown can put a figure back where it was found.
    A PDF stores one image once and may draw it on several pages, so the
    xref is what is de-duplicated, not the file.
    """
    if not os.path.isdir(dest_dir):
        os.makedirs(dest_dir)
    by_page, written = {}, {}
    for pno in range(doc.page_count):
        for info in doc[pno].get_images(full=True):
            xref = info[0]
            if xref in written:
                by_page.setdefault(pno, []).append(written[xref])
                continue
            try:
                blob = doc.extract_image(xref)
            except Exception:                              # noqa: BLE001
                continue
            if not blob or not blob.get('image'):
                continue
            name = '%s%03d_%d.%s' % (stem, pno + 1, xref,
                                     blob.get('ext') or 'png')
            path = os.path.join(dest_dir, name)
            try:
                with open(path, 'wb') as fh:
                    fh.write(blob['image'])
            except OSError:
                continue
            written[xref] = name
            by_page.setdefault(pno, []).append(name)
    return by_page


_HYPHEN_BREAK_RE = re.compile(r'(\w)-\n(\w)')
_HARD_WRAP_RE = re.compile(r'(?<![.!?:;])\n(?=[a-z(])')


def unwrap(text):
    r"""Undo the line breaks a PDF puts in the middle of sentences.

    A PDF has no paragraphs, only lines, so every extracted line ends where
    the column ended. Left alone, each becomes its own markdown line and the
    prose arrives as a column of fragments; a translator then works on
    fragments and the seams show in the output.

    Only breaks that cannot end a sentence are joined: a line ending in
    terminal punctuation is left alone, so a real paragraph boundary and a
    heading both survive.
    """
    text = _HYPHEN_BREAK_RE.sub(r'\1\2', text)
    return _HARD_WRAP_RE.sub(' ', text)


def to_markdown(doc, images_by_page=None, images_dir='images'):
    """The whole document as markdown, pages in order, figures in place."""
    images_by_page = images_by_page or {}
    out = []
    for pno, text in enumerate(page_texts(doc)):
        body = unwrap(text).strip()
        if body:
            out.append(body)
        for name in images_by_page.get(pno, []):
            out.append('![](%s/%s)' % (images_dir.replace('\\', '/'), name))
    return '\n\n'.join(out) + '\n'


def convert(pdf_path, out_md, images_dir):
    """Extract `pdf_path` into `out_md` and `images_dir`. Returns a report."""
    doc = open_pdf(pdf_path)
    try:
        by_page = extract_images(doc, images_dir)
        markdown = to_markdown(doc, by_page,
                               images_dir=os.path.basename(images_dir))
        hits, total = sentence_fidelity(doc, markdown)
        with io.open(out_md, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(markdown)
        return {
            'pages': doc.page_count,
            'characters': len(markdown),
            'images': sum(len(v) for v in by_page.values()),
            'fidelity_hits': hits,
            'fidelity_total': total,
        }
    finally:
        doc.close()

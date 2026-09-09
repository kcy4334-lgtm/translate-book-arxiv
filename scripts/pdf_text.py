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

Reading order is necessary and not sufficient. A page also carries material
that is *on* the paper without being *in* it: the running head, the footer,
the axis labels drawn inside a figure, a solid colour chip the typesetter
left behind. Emitting all of it was this module's first version, and it put
a journal footer between two sentences ten times, printed a figure's rotated
y-axis label as prose (`) V m ( e g a tlo V t u p t u O`), and turned a page
of the built book into seven blank rectangles.

Each of those is dropped here by asking the artefact rather than the text:

  furniture     repeats in the same margin band across pages;
  marginalia    is written in a direction the body never uses;
  figure text   lies inside a figure's own image rectangle;
  a dead image  contains exactly one colour, so it carries no information.

None of those is a guess about wording, and none of them can be defeated by
a paper that phrases its footer differently.

Headings are the exception, and the comment above `_SECTION_NAMES` says why
the typographic version of them was measured, written, and then taken back
out again.

The last section matters as much as the rest. Whether an extraction is
usable is not a property of the file format or of a page count, it is
whether the paper's own sentences are still there in one piece.
`sentence_fidelity` measures exactly that, and `convert.py` uses it to
decide rather than guessing from a layout heuristic. A guess would have to
be right about a paper nobody has met; this asks the artefact.
"""
from __future__ import unicode_literals

import io
import os
import re
from collections import Counter, defaultdict

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

    The reference sentences come from the whole page, furniture included,
    which is deliberate: this score must not improve merely because we
    started dropping things. Furniture is far too short to qualify as a
    sentence here, so it never enters the total either way.
    """
    flat = _flat(candidate)
    hits = total = 0
    for pno in range(first_page, doc.page_count):
        for sentence in sentences_of(doc[pno].get_text('text'))[:per_page]:
            total += 1
            if sentence in flat:
                hits += 1
    return hits, total


# --------------------------------------------------------------------------
# What is on the page without being in the paper
# --------------------------------------------------------------------------

# The band at the top and bottom of a page in which a running head or footer
# can live. Measured on the paper that prompted this: every running head sat
# at 2.0% of page height and every footer ended at 97.0%, and no body block
# entered either band. 12% is loose enough not to depend on that measurement.
_MARGIN_BAND = 0.12

# How many pages must agree before a repeated line is called furniture.
# A journal that alternates its recto and verso heads gives each wording
# only half the pages, so a "most pages" rule would keep one of the two --
# which is exactly what this paper does. A quarter clears both with room,
# and the floor of 3 means a two-page document can never lose anything.
_FURNITURE_MIN_SHARE = 0.25
_FURNITURE_MIN_PAGES = 3

_DIGITS_RE = re.compile(r'\d+')

# How much of a text block must lie inside a figure before it is that
# figure's own label rather than prose. Measured: axis labels, panel letters
# and legends scored 0.35 to 1.00, and every caption scored 0.
_FIGURE_TEXT_OVERLAP = 0.3
# An image this large is a page background, a watermark or a scan of the
# whole page, not a figure. Text over it is the page, so keep the text.
_FIGURE_MAX_PAGE_SHARE = 0.8

# A caption is never furniture, whatever it overlaps. Cheap insurance: this
# is the one block on the page whose loss would not be noticed, because the
# figure it describes is still there.
_CAPTION_RE = re.compile(
    r'^\s*(?:supplementary\s+)?'
    r'(?:fig(?:ure)?|table|scheme|chart|box|algorithm|extended\s+data)'
    r'[\s.:]*\d',
    re.IGNORECASE)


def _furniture_key(text):
    """Two footers differing only in their page number are one footer."""
    return _DIGITS_RE.sub('#', _flat(text))


def _zone_of(bbox, height, band=_MARGIN_BAND):
    """'top', 'bottom' or None: which margin band this block sits in."""
    if not height:
        return None
    if bbox[1] / height <= band:
        return 'top'
    if bbox[3] / height >= 1.0 - band:
        return 'bottom'
    return None


def furniture_keys(pages, band=_MARGIN_BAND,
                   min_share=_FURNITURE_MIN_SHARE,
                   min_pages=_FURNITURE_MIN_PAGES):
    """The (zone, key) pairs that repeat in a margin band across pages.

    `pages` is [(height, [(bbox, text), ...]), ...], one entry per page.

    Repetition is the whole test. A running head is not recognised by what
    it says -- this one says ARTICLE, the next journal's will not -- but by
    saying the same thing in the same band on page after page. Body text
    never does that, because a paper does not repeat a paragraph.
    """
    if not pages:
        return set()
    seen = defaultdict(set)
    for index, (height, blocks) in enumerate(pages):
        for bbox, text in blocks:
            zone = _zone_of(bbox, height, band)
            key = _furniture_key(text)
            if zone and key:
                seen[(zone, key)].add(index)
    need = max(min_pages, int(len(pages) * min_share))
    return {pair for pair, on in seen.items() if len(on) >= need}


def is_marginalia(block):
    """Is this block written in a direction the body text never uses?

    A paper's prose runs left to right, `dir == (1, 0)`, on every page. What
    does not is the spine stamp, the "downloaded from" bar, the typesetter's
    artefact string, and a figure's rotated axis label. Nature Communications
    prints `1234567890():,;` up the left margin of page 1; it arrived in the
    book between two paragraphs.

    A page rotated as a whole (a landscape table) is NOT caught here: PyMuPDF
    applies `/Rotate` before reporting, so its text is upright and its
    direction is (1, 0) like any other. Only text rotated against its own
    page is dropped.
    """
    for line in block.get('lines') or ():
        direction = tuple(round(v, 2) for v in (line.get('dir') or (1, 0)))
        if direction != (1.0, 0.0):
            return True
    return False


def overlap_fraction(bbox, rect):
    """How much of `bbox` lies inside `rect`, as a share of `bbox`."""
    x0 = max(bbox[0], rect[0])
    y0 = max(bbox[1], rect[1])
    x1 = min(bbox[2], rect[2])
    y1 = min(bbox[3], rect[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    own = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
    if own <= 0:
        return 0.0
    return ((x1 - x0) * (y1 - y0)) / own


def is_figure_text(bbox, image_rects, page_area,
                   overlap=_FIGURE_TEXT_OVERLAP,
                   max_page_share=_FIGURE_MAX_PAGE_SHARE):
    """Does this block sit inside a figure, making it that figure's label?

    Axis labels, tick numbers, panel letters and legends are text drawn on
    top of the plot. Read as prose they cut a sentence in half and place its
    verb two pages later, which is what a translator then works on.

    The caller must have excluded captions first: a caption sits below the
    figure and scores zero here, but a caption typeset into the figure's own
    box would not, and losing it costs more than any label is worth.
    """
    for rect in image_rects:
        area = (rect[2] - rect[0]) * (rect[3] - rect[1])
        if area <= 0:
            continue
        if page_area and area / page_area > max_page_share:
            continue       # a background or a full-page scan, not a figure
        if overlap_fraction(bbox, rect) >= overlap:
            return True
    return False


# --------------------------------------------------------------------------
# Headings
# --------------------------------------------------------------------------
#
# Only the sections a paper can be relied on to name. This looks timid next
# to reading the typography, and reading the typography is what was tried
# first: find the fonts setting a small share of the document whose runs
# start a line, and call those headings. It is measurable, it is derived
# from the artefact, and on this paper it is right.
#
# It is also unusable. Measured over the nine PDFs on hand it produced 222
# headings on AlphaQ and 141 on OpenVLA -- `## ViT`, `## Weights`,
# `## November 26, 2025` -- because those papers draw their figures in
# vector, so `is_figure_text` finds no rectangle to test against, the axis
# labels stay in the prose, and a font rule then promotes them. Heading
# detection cannot be safe until figure regions are known on a page with no
# raster image, and that is a separate piece of work.
#
# So: match the section names, as whole lines, and nothing else. A line
# reading exactly `References` in a paper IS a heading; that is not a guess
# about typography and no figure label can imitate it. Everything this
# misses stays prose, which is what it was before.
#
# The list earns its keep downstream as well as on the page. `convert.py`
# splits the bibliography off so it is never sent to a translator, and it
# finds it by looking for a `References` HEADING -- which this path never
# emitted, so a chunk of this paper's reference list went to a sub-agent to
# be translated, which is the one thing a reference must not be.
_SECTION_NAMES = (
    'abstract', 'introduction', 'background', 'related work',
    'results', 'results and discussion', 'discussion', 'conclusion',
    'conclusions', 'conclusion and future work', 'limitations',
    'methods', 'method', 'materials and methods', 'experimental section',
    'experiments', 'evaluation', 'implementation details',
    'references', 'bibliography', 'references and notes',
    'acknowledgement', 'acknowledgements', 'acknowledgment',
    'acknowledgments', 'author contributions', 'competing interests',
    'conflicts of interest', 'declaration of interests', 'funding',
    'data availability', 'code availability', 'additional information',
    'supplementary information', 'ethics declarations',
    'appendix', 'supporting information',
)
_SECTION_TRIM_RE = re.compile(r'^[\s\d.:|)•-]+|[\s.:]+$')


def section_heading(line):
    """The section name this line is, or None. Whole line or nothing.

    A trailing colon and a leading section number are stripped, so
    `4. Methods` and `Methods:` are both the section they say they are.
    """
    flat = _flat(line)
    if not flat or len(flat) > 60:
        return None
    bare = _SECTION_TRIM_RE.sub('', flat)
    if bare.lower() in _SECTION_NAMES:
        return bare
    return None


# A paper has one Methods section. A results table has a `Method` column
# header on every page it spans, and each one is a whole line of its own.
# Measured: AlphaQ produced eight `## Method` headings and MoLe-VLA seven,
# every one of them a table header; no real section name in any of the nine
# papers occurred more than twice.
_SECTION_MAX_OCCURRENCES = 2


def section_names_used(texts, limit=_SECTION_MAX_OCCURRENCES):
    """Which section names occur few enough times to be real headings."""
    counts = Counter()
    for text in texts:
        for line in (text or '').split('\n'):
            name = section_heading(line)
            if name:
                counts[name.lower()] += 1
    return {name for name, n in counts.items() if n <= limit}


def split_sections(text, allowed=None):
    """[(is_heading, text), ...] for a block, split at its section names."""
    out, buffer = [], []

    def flush():
        joined = '\n'.join(buffer).strip()
        if joined:
            out.append((False, joined))
        del buffer[:]

    for line in (text or '').split('\n'):
        name = section_heading(line)
        if name and (allowed is None or name.lower() in allowed):
            flush()
            out.append((True, name))
        else:
            buffer.append(line)
    flush()
    return out


# A PDF line may open with a `#` and mean it: `# Trials`, `# Modules` and
# `# LLM layers` are all column headers reading "number of". Emitted raw
# they become markdown headings, and they outnumbered the real ones.
_LEADING_HASH_RE = re.compile(r'^(\s*)(#+)', re.MULTILINE)


def escape_markdown(text):
    """Stop the paper's own punctuation from being read as markup."""
    return _LEADING_HASH_RE.sub(lambda m: '%s\\%s' % (m.group(1), m.group(2)),
                                text or '')


def _span_text(span):
    return span.get('text') or ''


def _block_lines(block):
    return block.get('lines') or ()


# --------------------------------------------------------------------------
# Images
# --------------------------------------------------------------------------

# How many colours to look for before giving up and calling it a real image.
_COLOUR_CAP = 4
# How many pixels to sample. A colour chip is uniform, so a sparse sample
# finds its second colour if it has one.
_COLOUR_SAMPLES = 4000


def distinct_colours(pixmap, cap=_COLOUR_CAP, samples=_COLOUR_SAMPLES):
    """How many different pixel values this image has, counted up to `cap`.

    Not a size test. Measured on the paper that prompted this, the seven
    dead images ran from 18x24 to 301x341 pixels and from 104 to 1042 bytes,
    while a real figure was 282x238 and 9 KB: every threshold on size or on
    bytes puts at least one of them on the wrong side. The number of colours
    separates them completely, and it is not a heuristic -- an image with
    one colour is a filled rectangle and carries no information at all.

    Two colours is a silhouette, a line drawing, a 1-bit scan or, in this
    paper, the publication date set as a bitmap. Those are kept.
    """
    width = getattr(pixmap, 'width', 0)
    height = getattr(pixmap, 'height', 0)
    depth = getattr(pixmap, 'n', 0)
    data = getattr(pixmap, 'samples', b'')
    count = width * height
    if not (count and depth) or len(data) < count * depth:
        return cap                      # unreadable: treat it as real
    step = max(1, count // max(1, samples))
    seen = set()
    for i in range(0, count, step):
        seen.add(bytes(data[i * depth:(i + 1) * depth]))
        if len(seen) >= cap:
            break
    return len(seen)


def _image_is_dead(doc, xref, smask=0):
    """A one-colour image is a leftover fill. Anything unreadable is kept.

    The colours must be counted on the COMPOSITED image, never on the base.
    An icon, a silhouette or a label shipped as a bitmap is often a single
    flat colour whose entire shape lives in its soft mask, so the base
    pixmap is one colour and looks exactly like a junk fill.

    Measured across the nine PDFs on hand, the separation is total: 13
    images have one base colour AND a mask, and every one of them is real
    content -- DeeR-VLA's padlock icons, TinyVLA's `latency` label,
    OpenVLA's teaser logos. The 7 with one colour and NO mask are the junk
    fills. Counting the base alone would have deleted all 13.
    """
    try:
        import pymupdf
        pix = pymupdf.Pixmap(doc, xref)
        if smask:
            # Keep the alpha channel: it IS the shape. Compositing and then
            # flattening the alpha away collapses the icon back to the one
            # flat colour it is drawn in, and deletes it after all.
            pix = pymupdf.Pixmap(pix, pymupdf.Pixmap(doc, smask))
        elif pix.alpha:
            pix = pymupdf.Pixmap(pix, 0)
    except Exception:                                      # noqa: BLE001
        return False
    return distinct_colours(pix) <= 1


def extract_images(doc, dest_dir, stem='page'):
    """Write each page's images to `dest_dir`; return {page: [relpath]}.

    Keyed by page so the markdown can put a figure back where it was found.
    A PDF stores one image once and may draw it on several pages, so the
    xref is what is de-duplicated, not the file.

    Images carrying a single colour are skipped. They are the typesetter's
    leftovers, and seven of them turned one page of a built book into a
    column of blank rectangles.
    """
    if not os.path.isdir(dest_dir):
        os.makedirs(dest_dir)
    by_page, written, dead = {}, {}, set()
    for pno in range(doc.page_count):
        for info in doc[pno].get_images(full=True):
            xref = info[0]
            if xref in dead:
                continue
            if xref in written:
                by_page.setdefault(pno, []).append(written[xref])
                continue
            # info[1] is the soft-mask xref, 0 when there is none.
            if _image_is_dead(doc, xref, info[1] if len(info) > 1 else 0):
                dead.add(xref)
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
    return by_page, len(dead)


def image_rects(page):
    """Every rectangle a raster image is drawn into on this page."""
    out = []
    try:
        images = page.get_images(full=True)
    except Exception:                                      # noqa: BLE001
        return out
    for info in images:
        try:
            for rect in page.get_image_rects(info[0]):
                out.append((rect.x0, rect.y0, rect.x1, rect.y1))
        except Exception:                                  # noqa: BLE001
            continue
    return out


# --------------------------------------------------------------------------
# Assembling the markdown
# --------------------------------------------------------------------------

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


def block_text(block):
    """A block's text, with the line breaks the PDF declared."""
    out = []
    for line in _block_lines(block):
        out.append(''.join(_span_text(s) for s in (line.get('spans') or ())))
    return '\n'.join(out)


def page_records(doc):
    """[(height, area, [block, ...], [image rect, ...]), ...], pages in order.

    Blocks are PyMuPDF's own `get_text('dict')` dictionaries, unmodified and
    in declaration order, so everything below works on the shape the library
    actually produces and a test can build one by hand.
    """
    out = []
    for page in doc:
        try:
            blocks = [b for b in page.get_text('dict')['blocks']
                      if b.get('type') == 0 and _block_lines(b)]
        except Exception:                                  # noqa: BLE001
            blocks = []
        rect = page.rect
        out.append((rect.height, rect.width * rect.height,
                    blocks, image_rects(page)))
    return out


def render_blocks(records, images_by_page=None, images_dir='images'):
    """The document as markdown: furniture dropped, headings marked.

    Returns (markdown, report) where the report counts what was dropped, so
    a caller can print it and a person can see whether it was too much.
    """
    images_by_page = images_by_page or {}
    pages = [(height, [(b['bbox'], block_text(b)) for b in blocks])
             for height, _area, blocks, _rects in records]
    furniture = furniture_keys(pages)
    allowed = section_names_used(
        block_text(b) for _h, _a, blocks, _r in records for b in blocks)

    out = []
    dropped = Counter()
    headings = 0
    for pno, (height, area, blocks, rects) in enumerate(records):
        for block in blocks:
            text = block_text(block)
            if not text.strip():
                continue
            caption = bool(_CAPTION_RE.match(_flat(text)))
            zone = _zone_of(block['bbox'], height)
            if not caption:
                if zone and (zone, _furniture_key(text)) in furniture:
                    dropped['furniture'] += 1
                    continue
                if is_marginalia(block):
                    dropped['marginalia'] += 1
                    continue
                if is_figure_text(block['bbox'], rects, area):
                    dropped['figure_text'] += 1
                    continue
            # A section name is regularly glued to the paragraph under it:
            # this paper puts `References` and its first entry in one block.
            # Split the block at its section names rather than hunting for
            # a block that happens to be a heading on its own.
            for is_heading, piece in split_sections(text, allowed):
                if is_heading and not caption:
                    out.append('## %s' % piece)
                    headings += 1
                else:
                    out.append(escape_markdown(unwrap(piece).strip()))
        for name in images_by_page.get(pno, []):
            out.append('![](%s/%s)' % (images_dir.replace('\\', '/'), name))
    report = {
        'headings': headings,
        'dropped_furniture': dropped['furniture'],
        'dropped_marginalia': dropped['marginalia'],
        'dropped_figure_text': dropped['figure_text'],
    }
    return '\n\n'.join(x for x in out if x) + '\n', report


def to_markdown(doc, images_by_page=None, images_dir='images'):
    """The whole document as markdown, pages in order, figures in place."""
    markdown, _report = render_blocks(page_records(doc), images_by_page,
                                      images_dir)
    return markdown


def convert(pdf_path, out_md, images_dir):
    """Extract `pdf_path` into `out_md` and `images_dir`. Returns a report."""
    doc = open_pdf(pdf_path)
    try:
        by_page, dead = extract_images(doc, images_dir)
        markdown, detail = render_blocks(
            page_records(doc), by_page,
            images_dir=os.path.basename(images_dir))
        hits, total = sentence_fidelity(doc, markdown)
        with io.open(out_md, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(markdown)
        report = {
            'pages': doc.page_count,
            'characters': len(markdown),
            'images': sum(len(v) for v in by_page.values()),
            'dropped_images': dead,
            'fidelity_hits': hits,
            'fidelity_total': total,
        }
        report.update(detail)
        return report
    finally:
        doc.close()

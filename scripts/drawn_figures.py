#!/usr/bin/env python3
r"""
drawn_figures.py - A figure the paper DRAWS, cropped from the paper's own PDF.

A figure written as `tikzpicture` (TikZ, pgfplots) or `picture` has no image
file anywhere in the source, and no stage of this pipeline can typeset it.
It used to be reported and left out: VAE's graphical model, BERT's plot and
five of DDPM's rate-distortion plots were missing from their books, caption
and number included, while the text kept pointing at them. One VAE run had
its agent redraw Figure 1 by hand.

The printed figure is already in the original PDF, as vector drawing, on the
page whose caption reads "Figure N". This finds that caption, takes the
drawing above it (or below, for a caption set on top), renders that region,
and puts an `\includegraphics` of the result where the drawing was. The
caption, label and number stay the paper's own.

A figure that cannot be located (no caption line, no drawing next to it) is
left exactly as before, so the build still reports it.
"""
import os
import re

from build_common import _balanced_group, strip_tex_comments
from numbering import float_units

DRAWN_ENVS = ('tikzpicture', 'pgfpicture', 'pspicture', 'picture')
_DRAWN_RE = re.compile(r'\\begin\s*\{(%s)\}' % '|'.join(DRAWN_ENVS))
_TIKZ_INPUT_RE = re.compile(r'\\input\s*\{[^{}]*\.(?:tikz|pgf|tex)\}')
_FIGURE_RE = re.compile(r'\\begin\{(figure\*?)\}(.*?)\\end\{\1\}', re.DOTALL)

# Render resolution: 3x the PDF's 72 dpi is 216 dpi, sharp in print and
# small enough for the EPUB.
_ZOOM = 3.0
# How far apart two pieces of one drawing may sit, in PDF points.
_JOIN_GAP = 24.0
# A text block wider than this share of its column is body text, not a label.
_BODY_TEXT_SHARE = 0.8


def drawn_figures(flat):
    r"""[(number, start, stop)] for each numbered figure drawn rather than
    included, with its span in `flat`."""
    # float_units reads comment-stripped text, whose offsets differ from
    # `flat`'s; the figures are matched to it in order instead.
    numbered = [u for u in float_units(strip_tex_comments(flat))
                if u['kind'] == 'figure']
    stripped = strip_tex_comments(flat)
    order = [m for m in _FIGURE_RE.finditer(stripped)]
    by_label = {}
    for u in numbered:
        for label in u['labels']:
            by_label[label] = u['number']
    out = []
    for m in _FIGURE_RE.finditer(flat):
        if _commented(flat, m.start()):
            continue
        body = m.group(2)
        if '\\includegraphics' in body:
            continue
        if not (_DRAWN_RE.search(body) or _TIKZ_INPUT_RE.search(body)):
            continue
        labels = re.findall(r'\\label\{([^}]+)\}', body)
        number = next((by_label[l] for l in labels if l in by_label), None)
        if number is None:
            # No label: the figure's place among the figures decides.
            index = sum(1 for o in _FIGURE_RE.finditer(flat[:m.start()])
                        if not _commented(flat, o.start()))
            if index < len(order):
                caps = [u for u in numbered
                        if u['start'] >= order[index].start()
                        and u['stop'] <= order[index].end()]
                number = caps[-1]['number'] if caps else None
        if number is not None:
            out.append((number, m.start(), m.end()))
    return out


def _commented(text, at):
    line = text[text.rfind('\n', 0, at) + 1:at]
    return re.search(r'(?<!\\)%', line) is not None


def _caption_block(page, number):
    """The text block that opens with this figure's label, or None."""
    rx = re.compile(r'^\s*(?:Figure|Fig\.)\s*%s\s*[:.]' % re.escape(str(number)))
    for block in page.get_text('dict').get('blocks', []):
        if block.get('type') != 0:
            continue
        lines = block.get('lines') or []
        if not lines:
            continue
        first = ''.join(s.get('text', '') for s in lines[0].get('spans', []))
        if rx.match(first):
            return block
    return None


def _drawing_rects(page):
    # A rule is a drawing with no height, and an axis tick one with no width;
    # both belong to a plot, so either extent is enough.
    rects = [path['rect'] for path in page.get_drawings()
             if path.get('rect') is not None
             and (path['rect'].width > 1 or path['rect'].height > 1)]
    # Ghostscript paints a TeX \rule as a one-pixel image stretched over the
    # rule. Shor's Figure 5.1, a gnuplot `picture`, is nothing but such
    # rules: no vector drawing at all, so the figure was never found.
    import pymupdf
    for info in page.get_image_info():
        if info.get('width') == 1 and info.get('height') == 1:
            r = pymupdf.Rect(info['bbox'])
            if r.width > 1 or r.height > 1:
                rects.append(r)
    return rects


def locate(doc, number):
    """(page index, clip rect) of the drawing that Figure `number` captions."""
    import pymupdf
    for pno in range(doc.page_count):
        page = doc[pno]
        block = _caption_block(page, number)
        if not block:
            continue
        cap = pymupdf.Rect(block['bbox'])
        # The caption's column, not its own width: a short caption sits under
        # a drawing wider than itself.
        mid = page.rect.width / 2
        if cap.x1 <= mid + 10:
            x0, x1 = 0, mid
        elif cap.x0 >= mid - 10:
            x0, x1 = mid, page.rect.width
        else:
            x0, x1 = 0, page.rect.width
        rects = [r for r in _drawing_rects(page)
                 if r.x1 > x0 and r.x0 < x1]
        for side in ('above', 'below'):
            if side == 'above':
                near = [r for r in rects if r.y1 <= cap.y0 + 2]
                near.sort(key=lambda r: -r.y1)
                edge = cap.y0
            else:
                near = [r for r in rects if r.y0 >= cap.y1 - 2]
                near.sort(key=lambda r: r.y0)
                edge = cap.y1
            if not near:
                continue
            first = near[0]
            gap = (edge - first.y1) if side == 'above' else (first.y0 - edge)
            if gap > 3 * _JOIN_GAP:
                continue
            region = pymupdf.Rect(first)
            for r in near[1:]:
                if (side == 'above' and r.y1 >= region.y0 - _JOIN_GAP) or \
                        (side == 'below' and r.y0 <= region.y1 + _JOIN_GAP):
                    region |= r
            region = _with_labels(page, region, cap, (x0, x1))
            region = (region + (-4, -4, 4, 4)) & page.rect
            if region.width > 20 and region.height > 20:
                return pno, region
    return None


def _with_labels(page, region, cap, columns):
    """Grow the region over the small text blocks that belong to it."""
    import pymupdf
    column = cap.width
    grown = pymupdf.Rect(region)
    for _ in range(3):
        before = pymupdf.Rect(grown)
        for block in page.get_text('dict').get('blocks', []):
            if block.get('type') != 0:
                continue
            b = pymupdf.Rect(block['bbox'])
            if b.intersects(cap) or b.width > _BODY_TEXT_SHARE * column:
                continue
            near = (grown + (-_JOIN_GAP / 2, -_JOIN_GAP / 2,
                             _JOIN_GAP / 2, _JOIN_GAP / 2))
            # An axis title stands farther off, level with the plot: Shor's
            # "P" sits 20pt left of its tick labels.
            beside = (grown.y0 <= (b.y0 + b.y1) / 2 <= grown.y1
                      and b.x0 >= columns[0] and b.x1 <= columns[1]
                      and b.intersects(grown + (-2 * _JOIN_GAP, 0, 2 * _JOIN_GAP, 0)))
            if b.intersects(near) or beside:
                grown |= b
        if grown == before:
            break
    return grown


def crop_drawn_figures(flat, pdf_path, out_dir):
    r"""Replace each drawn figure's drawing with a crop of the printed one.

    Returns (flat, [(number, file name)]). The drawing environments and any
    `\input` of a drawing file go; one `\includegraphics` takes the place of
    the first of them, so caption, label and panel structure stay.
    """
    if not pdf_path or not os.path.isfile(pdf_path):
        return flat, []
    units = drawn_figures(flat)
    if not units:
        return flat, []
    try:
        import pymupdf
    except ImportError:
        return flat, []
    done = []
    doc = pymupdf.open(pdf_path)
    try:
        replacements = []
        for number, start, stop in units:
            found = locate(doc, number)
            if not found:
                continue
            pno, clip = found
            name = 'tb_drawn_figure_%s.png' % str(number).replace('.', '_')
            pix = doc[pno].get_pixmap(matrix=pymupdf.Matrix(_ZOOM, _ZOOM),
                                      clip=clip, alpha=False)
            pix.save(os.path.join(out_dir, name))
            replacements.append((start, stop, name))
            done.append((number, name))
    finally:
        doc.close()
    for start, stop, name in reversed(replacements):
        flat = flat[:start] + _swap_drawing(flat[start:stop], name) + flat[stop:]
    return flat, done


def _swap_drawing(figure, name):
    """The figure with its drawing replaced by one image."""
    graphic = '\\includegraphics[width=\\linewidth]{%s}' % name
    out, cursor, placed = [], 0, False
    spans = []
    for m in _DRAWN_RE.finditer(figure):
        end = re.compile(r'\\end\s*\{%s\}' % m.group(1)).search(figure, m.end())
        if end:
            spans.append((m.start(), end.end()))
    spans += [(m.start(), m.end()) for m in _TIKZ_INPUT_RE.finditer(figure)]
    spans.sort()
    for s, e in spans:
        if s < cursor:
            continue
        out.append(figure[cursor:s])
        if not placed:
            out.append(graphic)
            placed = True
        cursor = e
    out.append(figure[cursor:])
    return _without_drawing_setup(''.join(out))


# What a drawing sets up before it starts, and what is left meaningless once
# the drawing is gone. gnuplot's LaTeX terminal writes all three above every
# `picture`; left behind, Shor's `\sbox{\plotpoint}{\rule..}` reached pandoc
# as raw LaTeX on the image's line, and the figure lost its caption.
_UNITLENGTH_RE = re.compile(r'\\setlength\s*\{?\\unitlength\}?\s*\{[^{}]*\}%?')
_NEWSAVEBOX_RE = re.compile(
    r'\\ifx\s*\\(\w+)\s*\\undefined\s*\\newsavebox\s*\{\\\1\}\s*\\fi%?')
_SBOX_RE = re.compile(r'\\sbox\s*\{\\\w+\}\s*\{')


def _without_drawing_setup(figure):
    figure = _UNITLENGTH_RE.sub('', figure)
    figure = _NEWSAVEBOX_RE.sub('', figure)
    while True:
        m = _SBOX_RE.search(figure)
        if not m:
            return figure
        end = _balanced_group(figure, m.end() - 1)
        if end < 0:
            return figure
        if figure[end:end + 1] == '%':
            end += 1
        figure = figure[:m.start()] + figure[end:]

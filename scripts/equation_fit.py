# -*- coding: utf-8 -*-
r"""Keep a display equation clear of its own number.

A numbered display equation is drawn as a centred formula with the number
absolutely positioned at the right margin, the way LaTeX sets it. When the
formula is nearly as wide as the text column the two occupy the same ink, and
the tail of the formula prints underneath the number: VLA-Adapter's equation
(3) ended `\sigma'_1(\mathcal{C}` with `(3)` stamped across it, unreadable,
and every automated check passed because both the formula and the number were
present and correct.

Nothing in CSS fixes this. MathML content does not shrink to fit its box --
`max-width` clamps the box and the glyphs simply overflow it -- so the only
lever is the font size, and the size that is needed cannot be known without
laying the formula out. The source's own `\small` is not the answer either:
measured, it leaves the formula 10pt into the number.

So measure. Each numbered equation is rendered alone on its own page, once
per candidate size, in a document that carries the book's own stylesheet.
One page holds one equation, so the number is whatever span reads as the
number and the formula is everything else -- no guessing which `(3)` on a
crowded page is the equation number and which is a superscript.

The largest size that leaves a real gap wins. An equation that already fits
is not touched, which is all of them in most papers.
"""
import os
import re

# Tried largest first. 1.0 means "leave it alone", and is always tried, so a
# paper whose equations all fit is measured once and patched not at all.
DEFAULT_SCALES = (1.0, 0.94, 0.88, 0.82, 0.76, 0.70)

# The formula has to stop this far short of the number. Two points reads as a
# collision to anyone looking at the page even though the boxes do not
# strictly overlap.
MIN_GAP_PT = 6.0

MM_PT = 72.0 / 25.4

_MATH_OPEN_RE = re.compile(r'<math\b[^>]*\bdata-eqno="([^"]*)"[^>]*>')
_ID_RE = re.compile(r'\bid="([^"]*)"')
_HEAD_RE = re.compile(r'<head\b.*?</head>', re.DOTALL | re.IGNORECASE)


def numbered_equations(html):
    r"""[(key, eqno, element)] for every numbered display equation.

    `key` is the element's id when it has one, which is what a patch is
    keyed on later; an equation with no id is measured but cannot be
    patched, and is reported rather than silently skipped.
    """
    found = []
    for m in _MATH_OPEN_RE.finditer(html):
        close = html.find('</math>', m.end())
        if close < 0:
            continue
        element = html[m.start():close + len('</math>')]
        ident = _ID_RE.search(m.group(0))
        found.append((ident.group(1) if ident else None, m.group(1), element))
    return found


_FONT_SIZE_DECL_RE = re.compile(r'\s*font-size\s*:[^;"]*;?')
_STYLE_ATTR_RE = re.compile(r'\s*style="([^"]*)"')


def _scale_attr(element, scale):
    r"""Return `element` with exactly this font-size forced on its <math> tag.

    Any font-size already on the element comes off first. Both halves of that
    matter, and both were once wrong here:

    A previous build's patch is still in the file when the next build starts,
    and a second declaration PREPENDED to the same style attribute loses to
    it -- last declaration wins inside one block. Every candidate size then
    measured identically, the pass reported the same collision at 1.0 and at
    0.7, and the size it chose had no effect on the page.

    Stripping also makes size 1.0 mean what it says. It is the baseline the
    other sizes are compared against, so it has to be the element as the
    stylesheet alone would render it, not as the last run left it.
    """
    open_end = element.index('>')
    head, rest = element[:open_end], element[open_end:]

    def clean(m):
        left = _FONT_SIZE_DECL_RE.sub('', m.group(1)).strip().strip(';')
        return ' style="%s"' % left if left else ''

    head = _STYLE_ATTR_RE.sub(clean, head)
    if scale >= 1.0:
        return head + rest

    style = 'font-size:%gem' % scale
    existing = _STYLE_ATTR_RE.search(head)
    if existing:
        head = _STYLE_ATTR_RE.sub(
            lambda m: ' style="%s;%s"' % (m.group(1).rstrip(';'), style),
            head, count=1)
    else:
        head += ' style="%s"' % style
    return head + rest


def build_probe_html(html, scales=DEFAULT_SCALES):
    r"""Each equation laid out alone, once per candidate size.

    NOT used to decide anything, and kept only because it is the quickest way
    to look at one equation in isolation while working on this.

    It cannot decide sizes, and that was learned the hard way. A probe
    carrying the book's own <head> still does not reproduce the book's
    layout: measured on VLA-Adapter's equation (3), the probe shrank
    obediently at 0.94em (410pt wide) while the book stayed pinned at 463pt
    until 0.86em, because in the book the formula is wider than its box and
    Chromium compresses the spacing to fit. The probe therefore certified a
    size that changed nothing, and the number went on printing across the
    formula while the build log said the equation had been reduced.

    Returns (probe_html, plan), plan being [(key, eqno, scale)] in page
    order.
    """
    head = _HEAD_RE.search(html)
    head_html = head.group(0) if head else '<head><meta charset="utf-8"></head>'
    lang = re.search(r'<html\b[^>]*\blang="([^"]*)"', html)
    lang_attr = ' lang="%s"' % lang.group(1) if lang else ''

    plan = []
    body = []
    for key, eqno, element in numbered_equations(html):
        for scale in scales:
            plan.append((key, eqno, scale))
            body.append('<p style="margin:0;break-after:page;'
                        'page-break-after:always;text-indent:0">%s</p>'
                        % _scale_attr(element, scale))
    if not body:
        return '', []
    doc = ('<!doctype html><html%s>%s<body>%s</body></html>'
           % (lang_attr, head_html, ''.join(body)))
    return doc, plan


def column_bounds(page_width_pt, print_cfg):
    """(left, right) of the text column, in points."""
    left = float(print_cfg.get('margin_left_mm', 18)) * MM_PT
    right = page_width_pt - float(print_cfg.get('margin_right_mm', 18)) * MM_PT
    return left, right


# How close to the margin a span has to end before it can be the equation
# number. Measured: numbers land at x1 = 544.5 against a column edge of
# 544.0. A superscript `(1)` inside a formula sits mid-line and is nowhere
# near, which is what separates the two -- both read as "(1)" in the text.
EDGE_TOLERANCE_PT = 4.0

# Substrings of the font names Chromium embeds for MathML. The equation
# number is set in the body serif, the formula in the math font, so a band
# with no math font on it is prose that happens to end in "(3)".
_MATH_FONT_HINTS = ('math', 'cambria', 'latinmodern', 'stix')


def _is_math_font(name):
    low = (name or '').lower()
    return any(hint in low for hint in _MATH_FONT_HINTS)


def measure_book(pdf_path, eqnos, print_cfg, min_gap_pt=MIN_GAP_PT):
    r"""[(eqno, fits, detail)] measured on the book itself.

    Measured on the finished book rather than on an isolated probe, because
    the two do not agree. Laid out alone, VLA-Adapter's equation (3) shrank
    with its font size exactly as expected. In the book the same element at
    the same size did not move at all: there the formula is wider than the
    box it is centred in, Chromium compresses the spacing to fit, and the
    painted width stays pinned at the box width through every size from 1.0
    down to 0.90. A probe therefore certifies sizes that change nothing.

    Finding the number on a full page needs care: `(1)` and `(2)` also
    appear as superscripts inside these very formulas. The number is the one
    that ends at the right margin, on a band that carries math type.
    """
    import fitz

    doc = fitz.open(pdf_path)
    wanted = {e.strip() for e in eqnos}
    seen = {}
    for page in doc:
        left, right = column_bounds(page.rect.width, print_cfg)
        lines = []
        for block in page.get_text('dict')['blocks']:
            for line in block.get('lines', []):
                spans = [s for s in line['spans'] if s['text'].strip()]
                if spans:
                    lines.append((line['bbox'], spans))
        for lbbox, spans in lines:
            for span in spans:
                text = span['text'].strip()
                if text not in wanted or text in seen:
                    continue
                if abs(span['bbox'][2] - right) > EDGE_TOLERANCE_PT:
                    continue
                band = [s for b, ss in lines for s in ss
                        if abs(b[1] - lbbox[1]) < 6]
                if not any(_is_math_font(s['font']) for s in band):
                    continue
                rest = [s for s in band if s is not span]
                if not rest:
                    seen[text] = (False, 'formula painted nothing')
                    continue
                f_x0 = min(s['bbox'][0] for s in rest)
                f_x1 = max(s['bbox'][2] for s in rest)
                gap = span['bbox'][0] - f_x1
                fits = (gap >= min_gap_pt and f_x0 >= left - 0.5
                        and f_x1 <= right + 0.5)
                seen[text] = (fits,
                              'formula x=[%.1f,%.1f] number x0=%.1f '
                              'gap %+.1fpt' % (f_x0, f_x1, span['bbox'][0],
                                               gap))
    out = []
    for eqno in eqnos:
        fits, detail = seen.get(eqno.strip(),
                                (True, 'no number found at the margin'))
        out.append((eqno, fits, detail))
    return out


def apply_scales(html, scales):
    r"""Set each numbered <math> to its chosen size. Returns (html, applied).

    Every numbered equation is rewritten, not only the ones being shrunk,
    because a size left over from a previous build is as wrong as a missing
    one: an equation that fits today would keep last week's reduction
    forever, and the reduction would not show up in this run's log.
    """
    applied = [0]

    def patch(m):
        ident = _ID_RE.search(m.group(0))
        scale = scales.get(ident.group(1)) if ident else None
        out = _scale_attr(m.group(0), scale if scale else 1.0)
        if scale:
            applied[0] += 1
        return out

    return _MATH_OPEN_RE.sub(patch, html), applied[0]


def pymupdf_available():
    """Can the finished PDF be measured on this machine?

    The renderer around this treats PyMuPDF as optional -- it warns and
    carries on when page numbers cannot be stamped -- and this pass has to
    match, or installing the pipeline without one Python package turns a
    cosmetic check into no PDF at all. `except Exception`, not ImportError:
    a half-installed build raises other things on import.
    """
    try:
        import fitz                                       # noqa: F401
    except Exception:                                     # noqa: BLE001
        return False
    return True


def _write_if_changed(path, text):
    with open(path, encoding='utf-8') as fh:
        if fh.read() == text:
            return False
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(text)
    return True


def fit_equations(html_path, pdf_path, render, print_cfg,
                  scales=DEFAULT_SCALES, min_gap_pt=MIN_GAP_PT, log=print,
                  measure=None):
    r"""Render the book, and shrink any equation printing under its number.

    Renders, measures the result, steps the offending equations down one
    size, and renders again, until every number is clear or the sizes run
    out. `pdf_path` is left holding the final render, so the caller does not
    render again -- an untouched book therefore costs exactly one render,
    which is what it cost before this existed.

    `render(src_html, out_pdf) -> bool` is passed in so this does not care
    which browser is driving and can be tested without one. `measure` is
    injectable for the same reason: `measure_book` needs a PDF reader, and
    the loop around it -- which is where the stepping and the giving-up live
    -- is worth testing on its own.

    Returns (rendered_ok, unfixable). `unfixable` names equations still
    colliding at the smallest size tried; they are reported rather than
    shipped quietly at a size that did not work.
    """
    with open(html_path, encoding='utf-8') as fh:
        html = fh.read()

    equations = numbered_equations(html)
    keys = {eqno: key for key, eqno, _el in equations if key}
    eqnos = [eqno for _key, eqno, _el in equations]

    if not eqnos:
        return render(html_path, pdf_path), []

    if measure is None and not pymupdf_available():
        # One render and no measuring, exactly as before this pass existed.
        # The alternative is to raise on the import and take the whole PDF
        # with it, which would make a formula's spacing a hard dependency.
        log('  equation fit: PyMuPDF is not installed, so equation numbers '
            'are not measured. `pip install pymupdf` to have a formula that '
            'is as wide as the text column fitted clear of its number.')
        return render(html_path, pdf_path), []

    level = {}
    stuck = []
    for _attempt in range(len(scales)):
        chosen = {keys[e]: scales[level[e]]
                  for e in level if e in keys and scales[level[e]] < 1.0}
        patched, applied = apply_scales(html, chosen)
        # Rewritten even when nothing shrinks, so a size left over from an
        # earlier build cannot survive into this one unmentioned.
        _write_if_changed(html_path, patched)

        if not render(html_path, pdf_path):
            log('  equation fit: render failed')
            return False, []

        results = (measure or measure_book)(pdf_path, eqnos, print_cfg,
                                            min_gap_pt)
        for eqno, _fits, detail in results:
            if 'no number found' in detail:
                log('  equation fit: %s has no number at the margin; '
                    'left alone (%s)' % (eqno, detail))

        failing = [e for e, fits, _d in results if not fits and e not in stuck]
        if not failing:
            if applied:
                log('  equation fit: %d equation(s) reduced to clear their '
                    'number (%s)'
                    % (applied, ', '.join('%s at %g' % (k, v)
                                          for k, v in sorted(chosen.items()))))
            return True, stuck

        for eqno in failing:
            nxt = level.get(eqno, 0) + 1
            if nxt >= len(scales) or eqno not in keys:
                stuck.append(eqno)
            else:
                level[eqno] = nxt
        if len(stuck) == len(failing) and not level:
            break

    return True, sorted(set(stuck))

#!/usr/bin/env python3
"""
layout_probe.py - Build the Korean layout fixture and measure the printed page.

Deliberately NOT named test_*.py: `unittest discover -p 'test_*.py'` must not
collect it, because it needs PyMuPDF, pandoc and a browser, and CI runs the
unit tests on the standard library alone.

    python tests/layout_probe.py                      # build + measure
    python tests/layout_probe.py --profile a4-large
    python tests/layout_probe.py --strict             # non-zero exit on drift
    python tests/layout_probe.py --measure-only x.pdf # just report on a PDF
    python tests/layout_probe.py --keep               # leave artifacts on disk

The point of this script is the loop: edit template_ebook.html or
layout.PRINT_PROFILES, re-run, read the numbers. It skips DOCX and EPUB
entirely, so a round trip is one pandoc call plus one Chrome launch.
"""

import argparse
import os
import re
import shutil
import statistics
import sys
import tempfile
from collections import Counter

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_DIR = os.path.join(REPO_ROOT, 'scripts')
FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures')
FIXTURE = os.path.join(FIXTURES_DIR, 'layout_ko.md')
STRESS_FIXTURE = os.path.join(FIXTURES_DIR, 'layout_stress_ko.md')
sys.path.insert(0, SCRIPT_DIR)

MM = 25.4 / 72.0
PT = 72.0 / 25.4


def _pymupdf():
    try:
        import pymupdf
        return pymupdf
    except ImportError:
        import fitz
        return fitz


# ---------------------------------------------------------------- measurement

def measure_pdf(pdf_path, body_size_tolerance=0.15, ignore_page_numbers=True,
                with_ink=True):
    """Return a dict of everything needed to prove the layout is right."""
    pymupdf = _pymupdf()
    doc = pymupdf.open(pdf_path)
    try:
        pages = []
        sizes = Counter()
        leads = Counter()
        fonts = {}

        for page in doc:
            rect = page.rect
            blocks = [b for b in page.get_text('blocks') if b[6] == 0]
            if ignore_page_numbers:
                # Both conditions, not either: a page whose body legitimately
                # ends in a bare number must not be discarded.
                blocks = [b for b in blocks
                          if not (re.fullmatch(r'\d+(\s*/\s*\d+)?', b[4].strip())
                                  and b[1] > rect.height * 0.90)]
            images = [b for b in page.get_text('blocks') if b[6] == 1]
            box = blocks + images
            info = {'w_mm': rect.width * MM, 'h_mm': rect.height * MM}
            if box:
                x0 = min(b[0] for b in box); x1 = max(b[2] for b in box)
                y0 = min(b[1] for b in box); y1 = max(b[3] for b in box)
                info.update(left_mm=x0 * MM, right_mm=(rect.x1 - x1) * MM,
                            top_mm=y0 * MM, bottom_mm=(rect.y1 - y1) * MM,
                            text_x1=x1)
            pages.append(info)

            # Font sizes, weighted by character count.
            d = page.get_text('dict')
            page_lines = []
            for blk in d['blocks']:
                if blk.get('type') != 0:
                    continue
                for ln in blk['lines']:
                    if not ln['spans']:
                        continue
                    text = ''.join(s['text'] for s in ln['spans'])
                    if not text.strip():
                        continue
                    dominant = max(ln['spans'], key=lambda s: len(s['text']))['size']
                    page_lines.append((ln['spans'][0]['origin'][1],
                                       round(dominant, 2), text))
                    for s in ln['spans']:
                        n = len(s['text'].strip())
                        if n:
                            sizes[round(s['size'], 2)] += n

            # Baseline-to-baseline, measured across the whole page in reading
            # order. Doing this per-block misses everything, because Chromium
            # emits most lines as their own block.
            page_lines.sort(key=lambda t: t[0])
            for prev, cur in zip(page_lines, page_lines[1:]):
                dy = round(cur[0] - prev[0], 1)
                if 5 < dy < 60 and abs(cur[1] - prev[1]) < 0.01:
                    leads[dy] += 1
            info['lines'] = page_lines

            for f in page.get_fonts(full=True):
                xref, ext, ftype, basefont = f[0], f[1], f[2], f[3]
                fonts.setdefault((basefont, ftype), ext != 'n/a')

        modal_size = sizes.most_common(1)[0][0] if sizes else 0.0
        body_lines = []
        for info in pages:
            body = [t for t in info.get('lines', [])
                    if abs(t[1] - modal_size) <= body_size_tolerance]
            info['body_line_count'] = len(body)
            body_lines.extend(body)

        overflow = []
        for pno, info in enumerate(pages, 1):
            if 'text_x1' not in info:
                continue
            limit = info['text_x1']
            for ln in info.get('lines', []):
                pass  # per-line x is not in this tuple; block-level check below
        # Block-level overflow: anything reaching past the widest body block.
        for pno, page in enumerate(doc, 1):
            rect = page.rect
            right_limit = rect.x1 - _profile_right_pt_hint(pages)
            for b in page.get_text('blocks'):
                if b[6] != 0:
                    continue
                if b[2] > right_limit + 1.0:
                    overflow.append((pno, round((rect.x1 - b[2]) * MM, 1),
                                     b[4].strip()[:60]))

        ink = measure_ink_margins(pdf_path) if with_ink else []

        return {
            'path': pdf_path,
            'ink': ink,
            'page_count': doc.page_count,
            'pages': pages,
            'sizes': sizes,
            'modal_size': modal_size,
            'leads': leads,
            'modal_lead': leads.most_common(1)[0][0] if leads else 0.0,
            'fonts': fonts,
            'body_line_counts': [p.get('body_line_count', 0) for p in pages],
            'chars_per_line': [len(t[2]) for t in body_lines],
            'overflow': overflow,
            'size_bytes': os.path.getsize(pdf_path),
        }
    finally:
        doc.close()


def _profile_right_pt_hint(pages):
    """Widest observed right margin is the honest text edge for overflow."""
    rights = [p['right_mm'] for p in pages if 'right_mm' in p]
    return (min(rights) if rights else 0.0) * PT


def measure_ink_margins(pdf_path, dpi=150, threshold=200):
    """Margins measured from actual ink, per page, in mm.

    The block-based numbers above come from PyMuPDF's line boxes, which are
    glyph EM boxes: a heading with a tight line-height reports a top margin
    ~1mm smaller than the ink really is, because the font's ascent overshoots
    its own line box. For "does this look right on paper" the ink is the
    honest measure, so the pass/fail check uses this.

    The bottom margin is deliberately NOT taken from here: the stamped page
    number lives in the bottom margin band by design, so ink would always
    report it. Use the block-based bottom, which filters the folio out.
    """
    pymupdf = _pymupdf()
    doc = pymupdf.open(pdf_path)
    px2mm = 25.4 / dpi
    out = []
    try:
        zoom = dpi / 72.0
        for page in doc:
            pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
            w, h, n, stride = pix.width, pix.height, pix.n, pix.stride
            buf = pix.samples
            top = bot = left = right = None
            for y in range(h):
                row = buf[y * stride: y * stride + w * n]
                if min(row) < threshold:
                    if top is None:
                        top = y
                    bot = y
            for x in range(w):
                col = bytes(buf[y * stride + x * n] for y in range(0, h, 2))
                if min(col) < threshold:
                    if left is None:
                        left = x
                    right = x
            if top is None:
                out.append({})
                continue
            out.append({'left_mm': left * px2mm,
                        'right_mm': (w - 1 - right) * px2mm,
                        'top_mm': top * px2mm,
                        'bottom_mm': (h - 1 - bot) * px2mm})
    finally:
        doc.close()
    return out


def report(m, profile=None):
    print(f"\n=== {m['path']} ===")
    print(f"pages {m['page_count']}   size {m['size_bytes']:,} bytes")
    p0 = m['pages'][0]
    print(f"page   {p0['w_mm']:.1f} x {p0['h_mm']:.1f} mm")

    def col(key):
        vals = [p[key] for p in m['pages'] if key in p]
        return min(vals) if vals else float('nan')

    print(f"margins, line boxes (min, mm)   "
          f"L={col('left_mm'):.1f}  R={col('right_mm'):.1f}  "
          f"T={col('top_mm'):.1f}  B={col('bottom_mm'):.1f}")
    if m.get('ink'):
        def inkcol(key):
            vals = [p[key] for p in m['ink'] if key in p]
            return min(vals) if vals else float('nan')
        print(f"margins, actual ink (min, mm)   "
              f"L={inkcol('left_mm'):.1f}  R={inkcol('right_mm'):.1f}  "
              f"T={inkcol('top_mm'):.1f}   <- authoritative; "
              f"bottom omitted (folio sits in that band by design)")
    print(f"body size  {m['modal_size']:.2f} pt      "
          f"measured leading  {m['modal_lead']:.1f} pt")
    print("size histogram: " + ', '.join(
        f"{s:g}pt x{c}" for s, c in m['sizes'].most_common(5)))
    counts = [c for c in m['body_line_counts'] if c]
    if counts:
        print(f"body lines/page  min {min(counts)}  max {max(counts)}  "
              f"median {int(statistics.median(counts))}")
    cpl = m['chars_per_line']
    if cpl:
        cpl_sorted = sorted(cpl)
        print(f"chars/line  mean {statistics.mean(cpl):.1f}  "
              f"median {cpl_sorted[len(cpl_sorted)//2]}  max {cpl_sorted[-1]}")
    print("fonts:")
    for (basefont, ftype), embedded in sorted(m['fonts'].items()):
        flag = 'embedded' if embedded else 'NOT EMBEDDED'
        warn = '   <-- Type3: variable font failed to subset' if ftype == 'Type3' else ''
        print(f"   {basefont or '(unnamed)':40s} {ftype:8s} {flag}{warn}")
    if m['overflow']:
        print(f"OVERFLOW: {len(m['overflow'])} block(s) past the right text edge")
        for pno, over, txt in m['overflow'][:5]:
            print(f"   p{pno}: {txt!r}")
    else:
        print("overflow: none")


def check(m, profile, body_metrics=True):
    """Return a list of failure strings; empty means the layout is on spec.

    body_metrics=False skips the modal-size and leading assertions. The
    stress fixture is deliberately dominated by a 45-row table (10pt) and a
    60-line code block (9.5pt), so its modal glyph size is NOT the body
    size and those two checks would report a failure that is not one.
    """
    fails = []
    p0 = m['pages'][0]
    expect_w, expect_h = (210.0, 297.0) if profile['page_size'] == 'A4' else (215.9, 279.4)
    if abs(p0['w_mm'] - expect_w) > 0.6 or abs(p0['h_mm'] - expect_h) > 0.6:
        fails.append(f"page is {p0['w_mm']:.1f}x{p0['h_mm']:.1f}mm, "
                     f"expected {expect_w}x{expect_h} - @page size did not take")
    # Ink, not line boxes: a tight-leading heading's EM box overshoots its own
    # line box and would report a ~1mm smaller top margin than really prints.
    margin_src = m['ink'] if m.get('ink') else m['pages']
    for side, key in (('left', 'left_mm'), ('right', 'right_mm'), ('top', 'top_mm')):
        vals = [p[key] for p in margin_src if key in p]
        want = profile[f'margin_{side}_mm']
        if vals and min(vals) < want - 0.6:
            fails.append(f"{side} margin {min(vals):.1f}mm < {want}mm")
    # Bottom always from line boxes; the stamped folio lives in the ink band.
    bvals = [p['bottom_mm'] for p in m['pages'] if 'bottom_mm' in p]
    if bvals and min(bvals) < profile['margin_bottom_mm'] - 0.6:
        fails.append(f"bottom margin {min(bvals):.1f}mm "
                     f"< {profile['margin_bottom_mm']}mm")
    if body_metrics:
        if abs(m['modal_size'] - profile['base_font_size_pt']) > 0.2:
            fails.append(f"body {m['modal_size']:.2f}pt, "
                         f"expected {profile['base_font_size_pt']}pt")
        want_lead = profile['base_font_size_pt'] * profile['line_height']
        if m['modal_lead'] and abs(m['modal_lead'] - want_lead) > 1.0:
            fails.append(f"leading {m['modal_lead']:.1f}pt, "
                         f"expected {want_lead:.1f}pt")
    if any(ftype == 'Type3' for (_, ftype) in m['fonts']):
        fails.append("Type3 fonts present - a variable font failed to subset-embed")
    if m['overflow']:
        fails.append(f"{len(m['overflow'])} block(s) overflow the right margin")
    return fails


# ---------------------------------------------------------------- stress mode

def stress_report(pdf_path):
    """Check the three things a one-page fixture can never exercise.

    Returns a list of failure strings; empty means all three behaved.
    """
    pymupdf = _pymupdf()
    doc = pymupdf.open(pdf_path)
    fails = []
    try:
        pages = [doc[i].get_text('text') for i in range(doc.page_count)]

        # 1. A 45-row table must span pages, and thead must repeat on each.
        header_cells = ('실험 번호', '모델 이름', '파라미터')
        header_pages = [i + 1 for i, t in enumerate(pages)
                        if all(c in t for c in header_cells)]
        row_pages = sorted({i + 1 for i, t in enumerate(pages)
                            if re.search(r'실험 \d\d', t)})
        print(f"  table spans pages   : {row_pages}")
        print(f"  header repeated on  : {header_pages}")
        if len(row_pages) < 2:
            fails.append('the 45-row table did not span pages; '
                         'the fixture no longer stresses pagination')
        elif len(header_pages) < len(row_pages):
            fails.append(f'thead repeated on {len(header_pages)} of '
                         f'{len(row_pages)} table pages '
                         f'(display: table-header-group is not taking effect)')
        rows_found = len(set(re.findall(r'실험 (\d\d)', ' '.join(pages))))
        print(f"  distinct table rows : {rows_found}/45")
        if rows_found < 45:
            fails.append(f'only {rows_found} of 45 table rows survived')

        # 2. A display equation must not be torn across a page break. Located
        #    by the integral/summation glyphs it is built from.
        math_pages = [i + 1 for i, t in enumerate(pages)
                      if any(g in t for g in ('∫', '∑', '\u03c3', '\u03bb'))]
        print(f"  display math on     : {math_pages}")
        if len(math_pages) > 1:
            fails.append(f'display equation glyphs appear on {len(math_pages)} '
                         f'pages ({math_pages}) -- it was split across a break')
        elif not math_pages:
            fails.append('display equation not found at all -- MathML did not render')

        # 3. Every line of an over-long code block must survive.
        code_found = len(set(re.findall(r'layer_(\d\d) = self', ' '.join(pages))))
        code_pages = [i + 1 for i, t in enumerate(pages) if 'self.block_' in t]
        print(f"  code block on pages : {code_pages}")
        print(f"  distinct code lines : {code_found}/60")
        if code_found < 60:
            fails.append(f'only {code_found} of 60 code lines survived '
                         f'(break-inside: avoid clipped the block)')
        return fails
    finally:
        doc.close()


# ------------------------------------------------------------------- building

CONFIG_TXT = """input_file=layout_ko.md
input_lang=en
output_lang={lang}
conversion_method=fixture
math_guard=off
original_title={title}
creator=translate-book
publisher=translate-book
source_language=en
"""


def make_figure(path, width=800, height=450):
    """Draw a labelled placeholder rather than checking a binary into git."""
    pymupdf = _pymupdf()
    doc = pymupdf.open()
    page = doc.new_page(width=width, height=height)
    page.draw_rect(pymupdf.Rect(2, 2, width - 2, height - 2),
                   color=(0.1, 0.1, 0.1), width=3)
    page.draw_rect(pymupdf.Rect(60, 60, 360, 260), color=(0.2, 0.2, 0.2), width=2)
    page.draw_circle(pymupdf.Point(560, 200), 90, color=(0.2, 0.2, 0.2), width=2)
    page.insert_text(pymupdf.Point(60, 380), "layout probe figure  800 x 450",
                     fontname='helv', fontsize=28)
    page.get_pixmap(matrix=pymupdf.Matrix(1, 1), alpha=False).save(path)
    doc.close()


def build(profile_name, lang, workdir, fixture=None):
    import layout
    import merge_and_build
    import chromium_pdf

    print_cfg = layout.get_print_profile(profile_name)
    lang_cfg = layout.get_lang_config(lang)
    title = '레이아웃 검증 문서'

    os.makedirs(os.path.join(workdir, 'images'), exist_ok=True)
    shutil.copy2(fixture or FIXTURE, os.path.join(workdir, 'output.md'))
    with open(os.path.join(workdir, 'config.txt'), 'w', encoding='utf-8') as f:
        f.write(CONFIG_TXT.format(lang=lang, title=title))
    make_figure(os.path.join(workdir, 'images', 'fig1.png'))

    print(f"=== building fixture: profile={profile_name} lang={lang} ===")
    ok = merge_and_build.convert_md_to_html(
        workdir, title, lang_cfg, 'translate-book',
        force=True, print_cfg=print_cfg)
    if not ok:
        print('ERROR: convert_md_to_html failed')
        return None, print_cfg

    pdf = os.path.join(workdir, 'book.pdf')
    if not chromium_pdf.html_to_pdf(os.path.join(workdir, 'book_doc.html'), pdf,
                                    lang=lang_cfg['lang_attr'], profile=print_cfg):
        return None, print_cfg
    return pdf, print_cfg


def main():
    ap = argparse.ArgumentParser(description='Measure the printed page layout')
    ap.add_argument('--profile', default=None, help='layout.PRINT_PROFILES key')
    ap.add_argument('--lang', default='ko')
    ap.add_argument('--keep', action='store_true',
                    help='write to tests/.artifacts/ instead of a temp dir')
    ap.add_argument('--strict', action='store_true',
                    help='exit non-zero if the layout drifts from the profile')
    ap.add_argument('--measure-only', metavar='PDF',
                    help='skip the build and just report on an existing PDF')
    ap.add_argument('--stress', action='store_true',
                    help='use the pagination stress fixture: a 45-row table, a '
                         'display equation at a page break, and a code block '
                         'longer than a page')
    args = ap.parse_args()

    import layout
    profile_name = args.profile or layout.DEFAULT_PRINT_PROFILE

    if args.measure_only:
        m = measure_pdf(args.measure_only)
        report(m, layout.get_print_profile(profile_name))
        fails = check(m, layout.get_print_profile(profile_name))
    else:
        if args.keep:
            workdir = os.path.join(REPO_ROOT, 'tests', '.artifacts',
                                   f'layout-{args.lang}_temp')
            shutil.rmtree(workdir, ignore_errors=True)
            os.makedirs(workdir, exist_ok=True)
            cleanup = False
        else:
            workdir = tempfile.mkdtemp(prefix='tb-layout-')
            cleanup = True
        try:
            pdf, print_cfg = build(profile_name, args.lang, workdir,
                                   fixture=STRESS_FIXTURE if args.stress else None)
            if not pdf:
                sys.exit(1)
            m = measure_pdf(pdf)
            report(m, print_cfg)
            fails = check(m, print_cfg, body_metrics=not args.stress)
            if args.stress:
                print('\npagination stress:')
                fails += stress_report(pdf)
            if args.keep:
                print(f"\nartifacts kept in {workdir}")
        finally:
            if cleanup:
                shutil.rmtree(workdir, ignore_errors=True)

    if fails:
        print('\nFAIL:')
        for f in fails:
            print(f'  - {f}')
        if args.strict:
            sys.exit(1)
    else:
        print('\nPASS: layout matches the profile')


if __name__ == '__main__':
    main()

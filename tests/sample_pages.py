# -*- coding: utf-8 -*-
r"""Render one printed page per language for the README.

    python tests/sample_pages.py            # build and render every language
    python tests/sample_pages.py ko zh      # just these

Why this exists rather than a screenshot of a real translated paper: a page of
somebody's arXiv paper is their work, and this repository has no licence to
republish it. `tests/fixtures/sample_page*.md` is written here instead, so the
sample can sit in a public README with nothing borrowed, and anyone who clones
the repository regenerates the exact same images and checks them.

The source page is `sample_page.md`; each translation is checked in beside it
as `sample_page.<lang>.md`, produced by the pipeline and reviewed. Rendering is
deterministic, so a reader is trusting the checked-in text, not a claim about
it.

The page reads like the middle of a paper -- numbered sections, a display
equation, citations, a results table and a figure -- because a thin one-page
summary shows the typography without showing what a reader is actually
judging. The results are invented; the papers it cites are real, since citing
work is not republishing it.

The figure is drawn by `draw_chart` rather than checked in as a binary, and
the page geometry is the shipped `a4-book` profile.
"""
import argparse
import io
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
FIXTURES = os.path.join(HERE, 'fixtures')
OUT_DIR = os.path.join(REPO, 'docs', 'samples')
sys.path.insert(0, os.path.join(REPO, 'scripts'))
sys.path.insert(0, HERE)

# The source page is English; every other entry is a translation of it.
LANGS = ['en', 'ko', 'ja', 'zh', 'fr', 'de', 'es']
PROFILE = 'a4-book'
# 595pt of A4 width at this scale is a little under 1000px: wide enough to read
# the body text in a browser, small enough for a repository.
SCALE = 1.6

CONFIG_TXT = """input_file=sample_page.md
input_lang=en
output_lang={lang}
conversion_method=fixture
math_guard=off
original_title={title}
creator=translate-book
publisher=translate-book
source_language=en
"""


def draw_chart(path, width=900, height=160):
    r"""A small line chart, drawn here rather than checked in as a binary.

    The first version of this reused `layout_probe.make_figure`, which draws a
    labelled rectangle: fine for measuring a page, and obviously a placeholder
    on one meant to show what the pipeline produces. A reader judging a sample
    should be looking at something a paper would actually print.
    """
    import pymupdf
    doc = pymupdf.open()
    page = doc.new_page(width=width, height=height)
    left, right = 96, width - 40
    top, bottom = 28, height - 46
    ink = (0.15, 0.15, 0.15)

    page.draw_line(pymupdf.Point(left, bottom), pymupdf.Point(right, bottom),
                   color=ink, width=1.4)
    page.draw_line(pymupdf.Point(left, bottom), pymupdf.Point(left, top),
                   color=ink, width=1.4)

    def at(fx, fy):
        return pymupdf.Point(left + (right - left) * fx,
                             bottom - (bottom - top) * fy)

    # Two curves: a fixed-depth baseline that falls away as the budget
    # tightens, and a budgeted rule that holds until it cannot.
    budgeted = [(0.00, 0.93), (0.18, 0.92), (0.36, 0.91), (0.54, 0.90),
                (0.72, 0.86), (0.86, 0.72), (1.00, 0.48)]
    fixed = [(0.00, 0.92), (0.18, 0.84), (0.36, 0.74), (0.54, 0.62),
             (0.72, 0.49), (0.86, 0.37), (1.00, 0.24)]
    for pts, dash in ((budgeted, None), (fixed, '[4 3] 0')):
        for a, b in zip(pts, pts[1:]):
            page.draw_line(at(*a), at(*b), color=ink, width=2.0, dashes=dash)
    for fx, fy in budgeted:
        page.draw_circle(at(fx, fy), 3.4, color=ink, fill=ink)

    page.insert_text(pymupdf.Point(left - 78, top + 46), 'success',
                     fontname='helv', fontsize=15, color=ink)
    page.insert_text(pymupdf.Point(left - 78, top + 66), 'rate',
                     fontname='helv', fontsize=15, color=ink)
    page.insert_text(pymupdf.Point(right - 150, bottom + 30),
                     'compute per step', fontname='helv', fontsize=15,
                     color=ink)
    page.insert_text(at(0.06, 0.30), 'budgeted', fontname='helv',
                     fontsize=15, color=ink)
    page.insert_text(at(0.06, 0.16), 'fixed depth', fontname='helv',
                     fontsize=15, color=ink)

    page.get_pixmap(matrix=pymupdf.Matrix(1, 1), alpha=False).save(path)
    doc.close()


def fixture_for(lang):
    name = 'sample_page.md' if lang == 'en' else 'sample_page.%s.md' % lang
    return os.path.join(FIXTURES, name)


def split_title(path):
    """(title, body). The H1 names the page; the build prints it itself.

    Keeping the title in the fixture means one file to edit per language. But
    leaving it in the body too printed it twice, once from `--title` and once
    as a heading -- which is why the real pipeline strips the paper's title
    block before merging. Do the same here.
    """
    with io.open(path, encoding='utf-8') as fh:
        lines = fh.read().split('\n')
    title, out, taken = 'sample page', [], False
    for line in lines:
        m = re.match(r'#\s+(.*)', line.strip())
        if m and not taken:
            title, taken = m.group(1).strip(), True
            continue
        out.append(line)
    return title, '\n'.join(out).lstrip('\n')


def render_content_page(pdf_path, png_path):
    r"""Render the page carrying the body. Returns (page_no, pages, w, h).

    The build opens with a title page, and neither it nor a printed contents
    page shows what a reader wants to judge. The first rule here was "the
    first page with 400 extracted characters", which picked the title page for
    Chinese: the same content needs far fewer characters in Han script, so the
    Chinese body page never reached the threshold and the fallback won. A
    count calibrated on one script does not carry to another -- take the page
    with the most text instead, which needs no number at all.
    """
    import pymupdf
    doc = pymupdf.open(pdf_path)
    try:
        lengths = [len(doc[n].get_text('text').strip())
                   for n in range(doc.page_count)]
        chosen = max(range(len(lengths)), key=lambda n: lengths[n])
        page = doc[chosen]
        pix = page.get_pixmap(matrix=pymupdf.Matrix(SCALE, SCALE), alpha=False)
        pix.save(png_path)
        return chosen + 1, doc.page_count, pix.width, pix.height
    finally:
        doc.close()


def build_one(lang, workdir):
    import layout
    import merge_and_build
    import chromium_pdf

    fixture = fixture_for(lang)
    if not os.path.isfile(fixture):
        return None, 'no fixture: %s' % os.path.basename(fixture)

    print_cfg = layout.get_print_profile(PROFILE)
    lang_cfg = layout.get_lang_config(lang)
    title, body = split_title(fixture)

    os.makedirs(os.path.join(workdir, 'images'), exist_ok=True)
    with io.open(os.path.join(workdir, 'output.md'), 'w',
                 encoding='utf-8', newline='\n') as fh:
        fh.write(body)
    with io.open(os.path.join(workdir, 'config.txt'), 'w',
                 encoding='utf-8') as fh:
        fh.write(CONFIG_TXT.format(lang=lang, title=title))
    # Short and wide, so the figure and its caption land on the same page as
    # the table. The caption is where the per-language float label shows.
    draw_chart(os.path.join(workdir, 'images', 'fig1.png'),
               width=900, height=160)

    ok = merge_and_build.convert_md_to_html(
        workdir, title, lang_cfg, 'translate-book',
        force=True, print_cfg=print_cfg)
    if not ok:
        return None, 'convert_md_to_html failed'

    pdf = os.path.join(workdir, 'book.pdf')
    if not chromium_pdf.html_to_pdf(os.path.join(workdir, 'book_doc.html'),
                                    pdf, lang=lang_cfg['lang_attr'],
                                    profile=print_cfg):
        return None, 'html_to_pdf failed'
    return pdf, title


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('langs', nargs='*', help='default: every language')
    ap.add_argument('--keep', action='store_true',
                    help='leave the build directories behind for inspection')
    args = ap.parse_args()

    wanted = args.langs or LANGS
    unknown = [l for l in wanted if l not in LANGS]
    if unknown:
        print('unknown language(s): %s' % ', '.join(unknown))
        return 2

    if not os.path.isdir(OUT_DIR):
        os.makedirs(OUT_DIR)

    failures = 0
    for lang in wanted:
        workdir = tempfile.mkdtemp(prefix='sample-%s-' % lang)
        try:
            pdf, note = build_one(lang, workdir)
            if not pdf:
                print('%-4s FAILED: %s' % (lang, note))
                failures += 1
                continue
            png = os.path.join(OUT_DIR, 'sample_%s.png' % lang)
            page_no, pages, pw, ph = render_content_page(pdf, png)
            print('%-4s %-38s page %d of %d -> %dx%dpx  %s bytes'
                  % (lang, note[:38], page_no, pages, pw, ph,
                     format(os.path.getsize(png), ',d')))
        finally:
            if not args.keep:
                shutil.rmtree(workdir, ignore_errors=True)
            else:
                print('     kept: %s' % workdir)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())

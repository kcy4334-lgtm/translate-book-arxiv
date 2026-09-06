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

The figure is drawn by `layout_probe.make_figure` rather than checked in as a
binary, and the page geometry is the shipped `a4-book` profile.
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
    import layout_probe

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
    layout_probe.make_figure(os.path.join(workdir, 'images', 'fig1.png'),
                             width=900, height=95)

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

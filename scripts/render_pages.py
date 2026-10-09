# -*- coding: utf-8 -*-
r"""Render the pages of a PDF to PNG files, for the page-by-page reading.

    python scripts/render_pages.py <pdf> <out_dir> --prefix <name>
    python scripts/render_pages.py <pdf> <out_dir> --prefix <name> --pages 7-9

Step 7.5 asks for the original and the translated pages read as images,
because a heading sitting on a figure extracts as clean text. It used to say
only "render them with PyMuPDF", so the reviewing agent wrote a script of its
own, and a script of its own is not one the skill pre-approves: on an
unattended plugin run on 2026-10-09 the render was refused and no page was
ever looked at. This is that render, shipped, so the step runs as the skill's
own command.

Prints one line per page written. Writes only into <out_dir>, which it
creates; put it inside the run's temp directory.
"""
import argparse
import os
import sys

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError, OSError):
        pass

try:
    import pymupdf
except ImportError:                                     # older PyMuPDF
    import fitz as pymupdf


def page_numbers(spec, count):
    """1-based page numbers from '3', '2-5' or '1,4,7-9'; every page if empty."""
    if not spec:
        return list(range(1, count + 1))
    pages = []
    for part in spec.split(','):
        part = part.strip()
        if '-' in part:
            a, b = part.split('-', 1)
            pages.extend(range(int(a), int(b) + 1))
        elif part:
            pages.append(int(part))
    bad = [p for p in pages if not 1 <= p <= count]
    if bad:
        raise SystemExit('page(s) %s outside 1-%d' % (bad, count))
    return pages


def render(pdf, out_dir, prefix, spec='', zoom=2.0):
    doc = pymupdf.open(pdf)
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for n in page_numbers(spec, doc.page_count):
        path = os.path.join(out_dir, '%s_p%03d.png' % (prefix, n))
        doc[n - 1].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom),
                              alpha=False).save(path)
        written.append(path)
    return written


def main(argv=None):
    ap = argparse.ArgumentParser(description='Render PDF pages to PNG')
    ap.add_argument('pdf')
    ap.add_argument('out_dir')
    ap.add_argument('--prefix', required=True,
                    help="start of each file name, e.g. '2609.11801_ko'; "
                         'agents share the directory')
    ap.add_argument('--pages', default='', help="e.g. '7' or '2-5,9'; default all")
    ap.add_argument('--zoom', type=float, default=2.0)
    args = ap.parse_args(argv)
    if not os.path.isfile(args.pdf):
        raise SystemExit('no such PDF: %s' % args.pdf)
    for path in render(args.pdf, args.out_dir, args.prefix, args.pages, args.zoom):
        print(path)
    return 0


if __name__ == '__main__':
    sys.exit(main())

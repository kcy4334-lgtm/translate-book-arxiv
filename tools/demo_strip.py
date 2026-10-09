# -*- coding: utf-8 -*-
r"""Put one page of the paper beside one page of the book, for assets/demo.

    python tools/demo_strip.py <paper.pdf> <page> <book.pdf> <page> <out.png>
        [--paper-label "arXiv:2609.11801v1 (CC BY 4.0)"] [--book-label "translate-book-arxiv ko"]

Both pages are drawn at the same height, so a letter page and an A4 page
come out the size a reader holding both would see them. Each gets its page
number and source written above it in small grey type, and a thin frame.
The three images in assets/demo were made this way; this script is here so
the next demo book can be shown the same way without guessing how.

Needs PyMuPDF and Pillow. Development only; the plugin does not ship tools/.
"""
import argparse
import io

import pymupdf
from PIL import Image, ImageDraw, ImageFont

HEIGHT = 1690          # pixels per page
MARGIN = 20
LABEL = 34             # band above each page for its label
GAP = 24
FRAME = (200, 200, 200)
INK = (90, 90, 90)


def page_image(path, number):
    doc = pymupdf.open(path)
    try:
        page = doc[number - 1]
        zoom = HEIGHT / page.rect.height
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
        return Image.open(io.BytesIO(pix.tobytes('png'))).convert('RGB')
    finally:
        doc.close()


def label_font():
    for name in ('arial.ttf', 'DejaVuSans.ttf', 'Helvetica.ttc'):
        try:
            return ImageFont.truetype(name, 18)
        except OSError:
            continue
    return ImageFont.load_default()


def strip(paper, paper_page, book, book_page, paper_label, book_label):
    left = page_image(paper, paper_page)
    right = page_image(book, book_page)
    width = MARGIN * 2 + left.width + GAP + right.width
    height = MARGIN * 2 + LABEL + HEIGHT
    out = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(out)
    font = label_font()
    x = MARGIN
    for image, text in ((left, '%s  p.%d' % (paper_label, paper_page)),
                        (right, '%s  p.%d' % (book_label, book_page))):
        draw.text((x, MARGIN), text, fill=INK, font=font)
        top = MARGIN + LABEL
        out.paste(image, (x, top))
        draw.rectangle([x - 1, top - 1, x + image.width, top + image.height],
                       outline=FRAME)
        x += image.width + GAP
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('paper')
    ap.add_argument('paper_page', type=int)
    ap.add_argument('book')
    ap.add_argument('book_page', type=int)
    ap.add_argument('out')
    ap.add_argument('--paper-label', default='arXiv:2609.11801v1 (CC BY 4.0)')
    ap.add_argument('--book-label', default='translate-book-arxiv  ko')
    args = ap.parse_args(argv)
    strip(args.paper, args.paper_page, args.book, args.book_page,
          args.paper_label, args.book_label).save(args.out, optimize=True)
    print(args.out)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

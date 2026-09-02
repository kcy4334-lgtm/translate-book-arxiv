#!/usr/bin/env python3
"""
chromium_pdf.py - Render HTML to PDF with headless Chromium.

Replaces the Calibre PDF path. Calibre never passed --paper-size or any of the
--pdf-page-margin-* options, so every PDF came out US Letter with 25.4mm on all
four sides, and Calibre honours neither `@page` nor most of a print stylesheet.
Chromium's --print-to-pdf does honour `@page { size / margin }`, which is what
makes the page geometry in layout.PRINT_PROFILES actually reach the paper.

Usage: chromium_pdf.py input.html -o output.pdf [--profile a4-book] [--lang ko]
"""

import os
import sys
import re
import glob
import shutil
import subprocess
import argparse
import tempfile
import unicodedata
from collections import Counter
from pathlib import Path

import layout

# Windows consoles default to a legacy codepage; force UTF-8 so non-ASCII
# progress output cannot crash the build.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError, OSError):
        pass

DEFAULT_TIMEOUT = 600
DEFAULT_VIRTUAL_TIME_MS = 15000

_MM_TO_PT = 72.0 / 25.4
# Helvetica cap height, used to sit the folio optically centred in its band.
_HELV_CAP_HEIGHT_EM = 0.717

# [] = unresolved, [None] = definitively absent
_CHROMIUM_CACHE = []


def _playwright_build_no(path):
    """Sort key for ms-playwright/chromium-<build> directories."""
    m = re.search(r'-(\d+)$', os.path.basename(path))
    return int(m.group(1)) if m else -1


def _chromium_candidates():
    """Ordered candidate paths for a Chromium-family browser.

    Real Chrome first, then Edge, then any Playwright-cached build. The
    standalone chrome-headless-shell is last: it is the OLD headless
    implementation kept alive as a separate binary, so it is a fallback rather
    than something to tune print CSS against.
    """
    local = os.environ.get('LOCALAPPDATA', '')
    pf = os.environ.get('PROGRAMFILES', r'C:\Program Files')
    pf86 = os.environ.get('PROGRAMFILES(X86)', r'C:\Program Files (x86)')

    cands = [
        os.environ.get('TRANSLATE_BOOK_CHROME'),
        shutil.which('chrome'),
        shutil.which('google-chrome'),
        shutil.which('google-chrome-stable'),
        shutil.which('chromium'),
        shutil.which('chromium-browser'),
        shutil.which('msedge'),
        # Windows
        os.path.join(pf, r'Google\Chrome\Application\chrome.exe'),
        os.path.join(pf86, r'Google\Chrome\Application\chrome.exe'),
        os.path.join(local, r'Google\Chrome\Application\chrome.exe'),
        os.path.join(pf86, r'Microsoft\Edge\Application\msedge.exe'),
        os.path.join(pf, r'Microsoft\Edge\Application\msedge.exe'),
    ]

    # Playwright browser cache, newest build first.
    if local:
        for pattern, leaf in (
            (os.path.join(local, 'ms-playwright', 'chromium-*'),
             os.path.join('chrome-win64', 'chrome.exe')),
            (os.path.join(local, 'ms-playwright', 'chromium_headless_shell-*'),
             os.path.join('chrome-headless-shell-win64', 'chrome-headless-shell.exe')),
        ):
            for d in sorted(glob.glob(pattern), key=_playwright_build_no, reverse=True):
                cands.append(os.path.join(d, leaf))

    cands += [
        # macOS
        '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
        '/Applications/Chromium.app/Contents/MacOS/Chromium',
        '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
        # Linux
        '/usr/bin/google-chrome',
        '/usr/bin/google-chrome-stable',
        '/usr/bin/chromium',
        '/usr/bin/chromium-browser',
        '/usr/bin/microsoft-edge',
        '/snap/bin/chromium',
    ]
    return [c for c in cands if c]


def find_chromium():
    """Locate a Chromium-family browser. Cached; returns None if absent.

    Deliberately NOT probed with `--version`, unlike find_calibre_convert().
    On Windows a already-running Chrome intercepts the command line, prints
    "opening in existing browser session" and exits 0 without printing a
    version -- so a version probe would validate binaries that cannot render
    and would reject nothing. os.path.isfile is the honest check.
    """
    if _CHROMIUM_CACHE:
        return _CHROMIUM_CACHE[0]

    for path in _chromium_candidates():
        if os.path.isfile(path):
            print(f"Found Chromium for PDF rendering: {path}")
            _CHROMIUM_CACHE.append(path)
            return path

    _CHROMIUM_CACHE.append(None)
    return None


# =============================================================================
# Print table of contents and PDF outline
# =============================================================================
#
# Chromium implements no `target-counter()`, so CSS cannot ask "which page does
# this link land on". merge_and_build stamps a sentinel into each TOC entry's
# page slot; we render once to find out where every heading actually fell,
# substitute the real numbers, and render again. Two Chrome launches, exact
# numbers, and no dependence on a paged-media engine we do not have.

_TOC_SENTINEL_RE = re.compile('\u00a7\u00a7(\\d+)\u00a7\u00a7')
_TOC_ENTRY_RE = re.compile(
    r'<a href="#(?P<id>[^"]+)">.*?data-toc="(?P<idx>\d+)"', re.DOTALL)
_HEADING_RE = re.compile(
    r'<(h[1-6])(?P<attrs>[^>]*\bid="(?P<id>[^"]+)"[^>]*)>(?P<text>.*?)</\1>',
    re.IGNORECASE | re.DOTALL)
# pandoc's document-title heading. Not a bookmark: it is the book itself.
_TITLE_CLASS_RE = re.compile(r'class="[^"]*\btitle\b', re.IGNORECASE)


# <annotation encoding="application/x-tex"> carries the TeX source of a
# rendered formula. Stripping tags without removing it first leaves the glyph
# AND its source in the text: "γ\gamma의 ...".
_ANNOTATION_RE = re.compile(r'<annotation\b[^>]*>.*?</annotation>', re.DOTALL)


def _plain_text(html_fragment):
    text = _ANNOTATION_RE.sub('', html_fragment)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'&nbsp;?', ' ', text)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&lt;', '<', text)
    text = re.sub(r'&gt;', '>', text)
    return re.sub(r'\s+', ' ', text).strip()


def parse_toc_entries(html):
    """[(entry_index, heading_id)] for each print-TOC row, in document order."""
    nav = re.search(r'<nav class="print-toc".*?</nav>', html, re.DOTALL)
    if not nav:
        return []
    return [(int(m.group('idx')), m.group('id'))
            for m in _TOC_ENTRY_RE.finditer(nav.group(0))]


def parse_headings(html):
    """{heading_id: (level, text)} for every heading carrying an id."""
    body = re.sub(r'<nav class="print-toc".*?</nav>', '', html, flags=re.DOTALL)
    out = {}
    for m in _HEADING_RE.finditer(body):
        if _TITLE_CLASS_RE.search(m.group('attrs') or ''):
            continue
        text = _plain_text(m.group('text'))
        if text:
            out[m.group('id')] = (int(m.group(1)[1]), text)
    return out


def _heading_index(doc):
    """{page_index: [heading-sized line texts]} plus the body size.

    Korean section names are routinely two characters ("서론", "결론"). Those
    are far too common to locate with a blind text search, and a length floor
    just drops them. Headings are set larger than body text, so matching only
    against over-sized lines identifies them reliably and cheaply.
    """
    sizes = Counter()
    lines = {}
    for pno in range(doc.page_count):
        try:
            data = doc[pno].get_text('dict')
        except Exception:
            lines[pno] = []
            continue
        page_lines = []
        for block in data.get('blocks', []):
            if block.get('type') != 0:
                continue
            for line in block.get('lines', []):
                spans = line.get('spans') or []
                if not spans:
                    continue
                text = ''.join(s.get('text', '') for s in spans).strip()
                if not text:
                    continue
                biggest = max(s.get('size', 0) for s in spans)
                for s in spans:
                    n = len(s.get('text', '').strip())
                    if n:
                        sizes[round(s.get('size', 0), 1)] += n
                page_lines.append((biggest, re.sub(r'\s+', ' ', text)))
        lines[pno] = page_lines
    body = sizes.most_common(1)[0][0] if sizes else 0.0
    threshold = body * 1.12 if body else 0.0
    return {p: [t for size, t in ls if size >= threshold] for p, ls in lines.items()}, body


def _fold_for_match(text):
    r"""Normalise a heading so its HTML form and its PDF form compare equal.

    A heading with inline maths is set by MathML from the Mathematical
    Alphanumeric Symbols block: `$y$` reaches the page as U+1D466 MATHEMATICAL
    ITALIC SMALL Y, while the same heading read out of the HTML is an ASCII `y`
    from `<mi>y</mi>`. Nothing matched, so `y의 매끄러운 선택` and its two
    siblings were the three TOC rows that printed with no page number and the
    three bookmarks the outline was missing — and every prefix probe began with
    the one character that differed, so shortening could not rescue it.

    NFKC maps that whole block back to plain letters, and takes the ligatures
    the PDF also carries (`di<ff>erent`) with it.
    """
    return unicodedata.normalize('NFKC', text)


def _find_text_page(doc, needle, first_page, heading_lines=None):
    """1-based page a heading lands on, searching from first_page onward.

    Tries the heading-sized line index first, then falls back to a plain text
    search on progressively shorter prefixes -- Chromium wraps long headings
    across lines and PyMuPDF cannot match across a line break.
    """
    target = re.sub(r'\s+', ' ', needle).strip()
    if not target:
        return None

    if heading_lines is not None:
        folded = _fold_for_match(target)
        for pno in range(first_page, doc.page_count):
            for text in heading_lines.get(pno, ()):
                if text == target or text.startswith(target) or target.startswith(text):
                    return pno + 1
                other = _fold_for_match(text)
                if other == folded or other.startswith(folded) \
                        or folded.startswith(other):
                    return pno + 1

    for probe in (target, target[:40], target[:24], target[:14]):
        probe = probe.strip()
        if len(probe) < 4:
            continue
        for pno in range(first_page, doc.page_count):
            try:
                if doc[pno].search_for(probe, quads=False):
                    return pno + 1
            except Exception:
                continue
    return None


def resolve_toc_pages(pdf_path, html):
    """Map TOC entry index -> printed page number. {} when nothing to do."""
    pymupdf = _import_pymupdf()
    if pymupdf is None:
        return {}
    entries = parse_toc_entries(html)
    if not entries:
        return {}
    headings = parse_headings(html)

    doc = pymupdf.open(pdf_path)
    try:
        # The TOC repeats every heading title, so body pages have to be
        # searched from after the last page carrying a sentinel.
        last_toc_page = 0
        for pno in range(doc.page_count):
            if _TOC_SENTINEL_RE.search(doc[pno].get_text('text')):
                last_toc_page = pno + 1
        heading_lines, _body = _heading_index(doc)
        mapping, cursor = {}, last_toc_page
        for idx, heading_id in entries:
            level_text = headings.get(heading_id)
            if not level_text:
                continue
            page = _find_text_page(doc, level_text[1], cursor, heading_lines)
            if page:
                mapping[idx] = page
                cursor = page - 1  # headings are monotonic; allow the same page
        return mapping
    finally:
        doc.close()


def apply_toc_pages(html, mapping):
    """Replace each sentinel with its page number (blank when unresolved)."""
    def repl(m):
        return str(mapping.get(int(m.group(1)), ''))
    return _TOC_SENTINEL_RE.sub(repl, html)


def build_pdf_outline(pdf_path, html):
    """Give the PDF real bookmarks. Returns the number of entries written."""
    pymupdf = _import_pymupdf()
    if pymupdf is None:
        return 0
    headings = parse_headings(html)
    if not headings:
        return 0
    doc = pymupdf.open(pdf_path)
    try:
        heading_lines, _body = _heading_index(doc)
        toc, cursor = [], 0
        for heading_id, (level, text) in headings.items():
            page = _find_text_page(doc, text, cursor, heading_lines)
            if not page:
                continue
            cursor = max(0, page - 1)
            # PyMuPDF rejects a level that jumps by more than one.
            level = min(level, (toc[-1][0] + 1) if toc else 1)
            toc.append([level, text[:120], page])
        if not toc:
            return 0
        doc.set_toc(toc)
        doc.saveIncr() if doc.can_save_incrementally() else doc.save(
            pdf_path + '.tmp', garbage=3, deflate=True)
        if not doc.can_save_incrementally():
            doc.close()
            os.replace(pdf_path + '.tmp', pdf_path)
            return len(toc)
        doc.close()
        return len(toc)
    except Exception as e:
        print(f'WARNING: could not write PDF bookmarks: {e}')
        try:
            doc.close()
        except Exception:
            pass
        return 0


def build_chrome_argv(chrome, html_file, pdf_file, profile_dir,
                      virtual_time_ms=DEFAULT_VIRTUAL_TIME_MS, no_sandbox=False):
    """Build the headless-Chromium argv for one HTML -> PDF render.

    Load-bearing arguments, do not drop any of these:

      --headless               Chrome >=132 removed old headless; plain
                               --headless IS new headless.
      --user-data-dir=<fresh>  Without a distinct profile, launching chrome.exe
                               while the user's Chrome is running hands the
                               command line to that browser and exits 0 having
                               produced nothing. This is the single most
                               important flag here.
      --print-to-pdf=<abs>     A relative path resolves against an
                               unpredictable cwd and fails silently.
      --no-pdf-header-footer   Otherwise every page carries the file:// URL and
                               a timestamp.
      --virtual-time-budget    Advances a virtual clock so layout, webfonts and
                               MathML shaping settle before the snapshot.
                               Chrome prints as soon as the page goes idle, so
                               this is a ceiling, not a fixed cost.
      file:///... LAST         Chrome silently ignores a bare Windows path; it
                               is not a URL. Path.as_uri() gives the forward
                               slashes and percent-encoding that Korean paths
                               and spaces need.
    """
    argv = [
        chrome,
        '--headless',
        f'--user-data-dir={os.path.abspath(profile_dir)}',
        '--no-first-run',
        '--no-default-browser-check',
        '--disable-extensions',
        '--disable-gpu',
        '--disable-features=Translate,OptimizationHints,MediaRouter,CalculateNativeWinOcclusion',
        '--allow-file-access-from-files',
        f'--virtual-time-budget={int(virtual_time_ms)}',
        '--no-pdf-header-footer',
        f'--print-to-pdf={os.path.abspath(pdf_file)}',
    ]
    if no_sandbox:
        argv.insert(2, '--no-sandbox')
    if os.name != 'nt':
        argv.append('--disable-dev-shm-usage')
    argv.append(Path(html_file).resolve().as_uri())
    return argv


def _want_no_sandbox():
    """Chrome refuses to start as root without --no-sandbox; otherwise skip it."""
    if os.environ.get('TRANSLATE_BOOK_CHROME_NO_SANDBOX'):
        return True
    return os.name != 'nt' and hasattr(os, 'geteuid') and os.geteuid() == 0


def verify_pdf(pdf_path, min_bytes=1024, require_text_in_first=3):
    """Return (ok, detail). detail is empty on success.

    --print-to-pdf returns 0 whether it wrote a book or nothing at all, so the
    exit code carries no information and these checks are the real contract.

    Layered so the stdlib checks run BEFORE the pymupdf import: CI runs the
    unit tests on stdlib only, and the interesting failure paths must stay
    reachable there.
    """
    if not os.path.isfile(pdf_path):
        return False, 'Chromium wrote no file at all'
    size = os.path.getsize(pdf_path)
    if size < min_bytes:
        return False, f'file is {size} bytes - too small to be a real PDF'
    with open(pdf_path, 'rb') as fh:
        if fh.read(5) != b'%PDF-':
            return False, 'file does not start with the %PDF- magic'

    pymupdf = _import_pymupdf()
    if pymupdf is None:
        print('WARNING: pymupdf unavailable - structural PDF checks skipped')
        return True, ''

    doc = None
    try:
        doc = pymupdf.open(pdf_path)
        if doc.page_count < 1:
            return False, 'PDF has zero pages'
        probe = min(require_text_in_first, doc.page_count)
        # Any of the first N pages, not page 1 specifically: a legitimate book
        # can open on a full-bleed cover image with no text.
        if not any(doc[i].get_text('text').strip() for i in range(probe)):
            return False, (f'no extractable text on the first {probe} page(s) - '
                           f'the page rendered blank, or every glyph fell back '
                           f'to a missing font')
    except Exception as e:
        return False, f'PDF will not open: {e}'
    finally:
        if doc is not None:
            doc.close()
    return True, ''


def _import_pymupdf():
    """Import pymupdf under either of its module names, or return None."""
    try:
        import pymupdf
        return pymupdf
    except ImportError:
        try:
            import fitz
            return fitz
        except ImportError:
            return None


def stamp_page_numbers(pdf_path, skip_first=1, start_at=None,
                       position='bottom-center', fontname='helv', fontsize=9.0,
                       bottom_margin_mm=22.0, side_margin_mm=18.0, fmt='{page}'):
    """Draw page numbers into the bottom margin band. Returns pages stamped.

    Chromium implements no `@page` margin boxes (@bottom-center { content:
    counter(page) }), and the --print-to-pdf command line exposes no
    header/footer template, so folios have to be stamped afterwards.

    `fmt` is a str.format template over {page} and {total} and MUST stay ASCII:
    'helv' is PDF base-14 Helvetica, which carries no Hangul, so a Korean label
    such as '3쪽' would silently lose its characters.

    bottom_margin_mm must be the SAME value that produced the CSS @page margin
    -- both come from one layout.PRINT_PROFILES entry, which is what makes a
    collision with the text block impossible rather than merely unlikely.
    """
    pymupdf = _import_pymupdf()
    if pymupdf is None:
        print('WARNING: pymupdf unavailable - page numbers not stamped')
        return 0

    doc = pymupdf.open(pdf_path)
    stamped = 0
    try:
        total = doc.page_count
        bottom_pt = bottom_margin_mm * _MM_TO_PT
        side_pt = side_margin_mm * _MM_TO_PT

        for idx, page in enumerate(doc):
            if idx < skip_first:
                continue
            number = (start_at + idx - skip_first) if start_at is not None else idx + 1
            label = fmt.format(page=number, total=total)

            rect = page.rect
            # Centre the digits vertically in the bottom margin band, then
            # shift down by half the cap height so the optical centre -- not
            # the baseline -- lands on the band's midline.
            band_mid_y = rect.y1 - bottom_pt / 2.0
            baseline_y = band_mid_y + fontsize * _HELV_CAP_HEIGHT_EM / 2.0
            width = pymupdf.get_text_length(label, fontname=fontname, fontsize=fontsize)

            if position == 'bottom-right':
                x = rect.x1 - side_pt - width
            elif position == 'bottom-left':
                x = rect.x0 + side_pt
            else:  # bottom-center
                x = (rect.x0 + rect.x1 - width) / 2.0

            # rect.x0/y1 rather than 0/height so a non-zero-origin MediaBox
            # stays correct for free.
            page.insert_text(pymupdf.Point(x, baseline_y), label,
                             fontname=fontname, fontsize=fontsize, color=(0, 0, 0))
            stamped += 1

        if doc.can_save_incrementally():
            doc.save(pdf_path, incremental=True, encryption=pymupdf.PDF_ENCRYPT_KEEP)
            doc.close()
        else:
            tmp = pdf_path + '.stamped'
            doc.save(tmp, garbage=3, deflate=True)
            doc.close()  # Windows will not replace a file that is still open
            os.replace(tmp, pdf_path)
    except Exception:
        try:
            doc.close()
        except Exception:
            pass
        raise
    return stamped


def html_to_pdf(html_file, output_file, lang='ko', profile=None,
                timeout=DEFAULT_TIMEOUT, virtual_time_ms=DEFAULT_VIRTUAL_TIME_MS,
                page_numbers=True):
    """Render one HTML file to PDF. Returns True on success.

    Prints 'ERROR: ...' and returns False on failure -- the same contract
    convert_html_with_calibre() already has, so callers need no new error
    vocabulary.

    The HTML is rendered IN PLACE. book_doc.html sits next to images/, so
    relative <img src="images/x.png"> resolves with no copying and no work.html.
    """
    cfg = profile or layout.get_print_profile()

    chrome = find_chromium()
    if not chrome:
        print('ERROR: Chromium/Chrome not found for PDF rendering.')
        print('  checked: TRANSLATE_BOOK_CHROME, PATH, Chrome/Edge install dirs, '
              'ms-playwright cache')
        print('  fix: install Google Chrome, or set TRANSLATE_BOOK_CHROME to a '
              'chrome.exe,')
        print('       or re-run merge_and_build.py with --pdf-engine calibre')
        return False

    print(f"Rendering PDF with Chromium ({cfg['page_size']}, "
          f"{layout.page_margin_css(cfg)}, {cfg['base_font_size_pt']:g}pt"
          + (', section breaks' if cfg.get('section_break') else '') + ')...')

    def _render(source_html):
        profile_dir = tempfile.mkdtemp(prefix='tb-chrome-')
        try:
            argv = build_chrome_argv(chrome, source_html, output_file, profile_dir,
                                     virtual_time_ms=virtual_time_ms,
                                     no_sandbox=_want_no_sandbox())
            try:
                subprocess.run(argv, capture_output=True, text=True,
                               encoding='utf-8', errors='replace', timeout=timeout)
            except subprocess.TimeoutExpired:
                print(f'ERROR: Chromium PDF rendering timed out after '
                      f'{timeout} seconds')
                print('  fix: the document may be pathologically large; '
                      'try --pdf-engine calibre.')
                return False
            except (FileNotFoundError, OSError) as e:
                print(f'ERROR: could not launch Chromium: {e}')
                return False
        finally:
            shutil.rmtree(profile_dir, ignore_errors=True)
        return True

    if not _render(html_file):
        return False

    ok, detail = verify_pdf(output_file)
    if not ok:
        print('ERROR: Chromium exited 0 but produced no usable PDF.')
        print(f'  cause: {detail}')
        print('  note: --print-to-pdf always exits 0; this check exists because '
              'the exit code carries no information.')
        print('  fix: raise the virtual time budget, or open the HTML in a '
              'browser and print it by hand to see what the renderer sees.')
        return False

    # Second pass: the print TOC's page numbers can only be known once the
    # document has been laid out, because Chromium has no target-counter().
    try:
        page_html = Path(html_file).read_text(encoding='utf-8')
    except OSError:
        page_html = ''
    if _TOC_SENTINEL_RE.search(page_html):
        mapping = resolve_toc_pages(output_file, page_html)
        resolved = len(mapping)
        total = len(parse_toc_entries(page_html))
        # Rendered beside the original so relative image paths still resolve.
        second = os.path.join(os.path.dirname(os.path.abspath(html_file)),
                              '_toc_pass2.html')
        try:
            with open(second, 'w', encoding='utf-8', newline='') as fh:
                fh.write(apply_toc_pages(page_html, mapping))
            if _render(second):
                ok, detail = verify_pdf(output_file)
                if not ok:
                    print(f'ERROR: TOC pass 2 produced no usable PDF ({detail})')
                    return False
            print(f'Print TOC: {resolved}/{total} page number(s) resolved')
        finally:
            try:
                os.remove(second)
            except OSError:
                pass
        n_marks = build_pdf_outline(output_file, page_html)
        if n_marks:
            print(f'PDF bookmarks: {n_marks} entries')

    if page_numbers and cfg.get('page_number', True):
        try:
            n = stamp_page_numbers(
                output_file,
                skip_first=cfg.get('page_number_skip_first', 1),
                position=cfg.get('page_number_position', 'bottom-center'),
                fontsize=cfg.get('page_number_font_size_pt', 9.0),
                bottom_margin_mm=cfg['margin_bottom_mm'],
                side_margin_mm=cfg['margin_right_mm'])
            print(f'Stamped page numbers on {n} page(s)')
        except Exception as e:
            # A missing folio is cosmetic; a lost PDF is not. Warn, keep going.
            print(f'WARNING: could not stamp page numbers: {e}')

    size = os.path.getsize(output_file)
    print(f'PDF conversion successful: {output_file} ({size:,} bytes)')
    return True


def main():
    parser = argparse.ArgumentParser(
        description='Render HTML to PDF using headless Chromium')
    parser.add_argument('input_html', help='Input HTML file')
    parser.add_argument('-o', '--output', required=True, help='Output .pdf file')
    parser.add_argument('-t', '--timeout', type=int, default=DEFAULT_TIMEOUT,
                        help=f'Render timeout in seconds (default: {DEFAULT_TIMEOUT})')
    parser.add_argument('--lang', default='ko',
                        help='Language code for output metadata (default: ko)')
    parser.add_argument('--profile', default=layout.DEFAULT_PRINT_PROFILE,
                        choices=sorted(layout.PRINT_PROFILES),
                        help=f'Print profile (default: {layout.DEFAULT_PRINT_PROFILE})')
    parser.add_argument('--no-page-numbers', action='store_true',
                        help='Skip stamping page numbers into the bottom margin')
    parser.add_argument('--virtual-time', type=int, default=DEFAULT_VIRTUAL_TIME_MS,
                        help='Virtual time budget in ms '
                             f'(default: {DEFAULT_VIRTUAL_TIME_MS})')
    args = parser.parse_args()

    if not os.path.exists(args.input_html):
        print(f'Error: Input file not found: {args.input_html}')
        sys.exit(1)
    if os.path.splitext(args.output)[1].lower() != '.pdf':
        print('Error: output must be a .pdf file')
        sys.exit(1)

    ok = html_to_pdf(args.input_html, args.output, lang=args.lang,
                     profile=layout.get_print_profile(args.profile),
                     timeout=args.timeout, virtual_time_ms=args.virtual_time,
                     page_numbers=not args.no_page_numbers)
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()

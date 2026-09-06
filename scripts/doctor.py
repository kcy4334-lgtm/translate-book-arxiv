# -*- coding: utf-8 -*-
"""Will this machine produce the same book as the machine that built it?

Copying the skill copies the code. It does not copy pandoc, Calibre, a
Chromium, PyMuPDF or the fonts, and the output depends on every one of them:
without a CJK serif face the Korean text falls back to whatever the system
offers and the page breaks land elsewhere, so the PDF is a different document
even though nothing failed.

    python scripts/doctor.py            # what is installed, what is missing
    python scripts/doctor.py --strict   # exit 1 if anything required is absent

This reports what is present. It does not prove the output matches: for that
run `python tests/layout_probe.py --strict`, which builds a real PDF and
measures the page, the margins, the type size and the embedded font names.
"""
from __future__ import unicode_literals

import argparse
import os
import shutil
import subprocess
import sys

# A CLI prints, and what it prints may carry the book's text. A Windows
# console under a non-UTF-8 locale then raises UnicodeEncodeError and the
# command dies -- which stayed hidden while every caller happened to set
# PYTHONIOENCODING for it.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError, OSError):
        pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

REQUIRED = 'required'
RECOMMENDED = 'recommended'
OPTIONAL = 'optional'


def _run(args):
    try:
        out = subprocess.run(args, capture_output=True, text=True, timeout=25)
    except (OSError, subprocess.SubprocessError):
        return None
    text = (out.stdout or out.returncode is not None and out.stderr) or ''
    return ' '.join(text.split()[:4]) if text.strip() else 'present'


def check_python():
    version = '%d.%d.%d' % sys.version_info[:3]
    ok = sys.version_info >= (3, 8)
    return ok, version, 'Python 3.8+ is needed for the scripts as written'


def check_pandoc():
    # merge_and_build.resolve_pandoc() knows the install locations that are
    # not on PATH -- which is how pandoc is installed on Windows by default.
    exe = None
    try:
        import merge_and_build
        exe = merge_and_build.resolve_pandoc()
    except Exception:
        exe = None
    exe = exe or shutil.which('pandoc')
    if not exe:
        return False, None, 'every markdown/HTML conversion goes through it'
    version = _run([exe, '--version']) or 'present'
    return True, version, exe


def check_calibre():
    try:
        import calibre_html_publish as chp
        exe = chp.find_calibre_convert()
    except Exception:
        exe = None
    exe = exe or shutil.which('ebook-convert')
    if not exe:
        return False, None, 'EPUB output and the calibre ingest backend'
    return True, os.path.basename(exe), exe


def check_chromium():
    try:
        import chromium_pdf
        exe = chromium_pdf.find_chromium()
    except Exception:
        exe = None
    if not exe:
        return False, None, ('the PDF is printed by headless Chromium; set '
                             'TRANSLATE_BOOK_CHROME to a browser binary if '
                             'yours is somewhere unusual')
    return True, os.path.basename(exe), exe


def check_pymupdf():
    try:
        import pymupdf                                          # noqa: F401
        return True, getattr(pymupdf, '__version__', 'present'), 'pymupdf'
    except ImportError:
        try:
            import fitz                                          # noqa: F401
            return True, getattr(fitz, 'version', ('?',))[0], 'fitz'
        except ImportError:
            return False, None, ('page numbers are stamped with it, and every '
                                 'probe that reads a PDF needs it')


def check_module(name, why):
    try:
        __import__(name)
        return True, 'present', why
    except ImportError:
        return False, None, why


def _font_files():
    """Every font filename this machine has, lowercased. Best effort."""
    names = set()
    dirs = []
    if os.name == 'nt':
        dirs = [os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts'),
                os.path.join(os.environ.get('LOCALAPPDATA', ''),
                             'Microsoft', 'Windows', 'Fonts')]
    elif sys.platform == 'darwin':
        dirs = ['/Library/Fonts', '/System/Library/Fonts',
                os.path.expanduser('~/Library/Fonts')]
    else:
        dirs = ['/usr/share/fonts', '/usr/local/share/fonts',
                os.path.expanduser('~/.fonts'),
                os.path.expanduser('~/.local/share/fonts')]
    for base in dirs:
        if not base or not os.path.isdir(base):
            continue
        for root, _dirs, files in os.walk(base):
            for name in files:
                names.add(name.lower())
    if not names:
        listing = shutil.which('fc-list')
        if listing:
            out = _run([listing])
            if out:
                names.add(out.lower())
    return names


def check_font(needles, why, fonts):
    hit = next((n for n in fonts
                if any(needle in n for needle in needles)), None)
    return bool(hit), hit, why


def check_advisors():
    r"""The four advisor definitions, where a runtime will actually find them.

    They ship at `<skill>/.claude/agents/`, and no runtime searches that path:
    sub-agents are discovered in `~/.claude/agents/` and in a project's own
    `.claude/agents/`. Left where they ship they cannot be called at all, and
    until now nothing said so — `install_advisors.py` records that ten papers
    were translated in exactly that state with no report anywhere.

    `SKILL.md` names these four sixteen times and tells the orchestrator when
    to call each. A skill whose instructions depend on something the install
    step can silently skip is the shape this whole log is about, so the tool
    whose job is "what is present" has to look here too.
    """
    why = ('the growth loop — old-man, question-monster, fast-finder and '
           'referee — cannot be called until `python '
           'scripts/install_advisors.py` copies them where the runtime looks')
    shipped = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), '.claude', 'agents')
    try:
        names = sorted(n for n in os.listdir(shipped) if n.endswith('.md'))
    except OSError:
        return False, 'none shipped', why
    if not names:
        return False, 'none shipped', why
    dest = os.path.join(os.path.expanduser('~'), '.claude', 'agents')
    found = [n for n in names if os.path.isfile(os.path.join(dest, n))]
    if len(found) == len(names):
        return True, '%d of %d installed' % (len(found), len(names)), why
    return False, '%d of %d installed' % (len(found), len(names)), why


def probe(strict=False):
    fonts = _font_files()
    checks = [
        (REQUIRED, 'Python', check_python()),
        (REQUIRED, 'pandoc', check_pandoc()),
        (REQUIRED, 'Chromium/Chrome/Edge', check_chromium()),
        (REQUIRED, 'Calibre ebook-convert', check_calibre()),
        (REQUIRED, 'PyMuPDF', check_pymupdf()),
        (RECOMMENDED, 'advisor sub-agents', check_advisors()),
        (RECOMMENDED, 'pypandoc',
         check_module('pypandoc', 'used by the conversion path')),
        (OPTIONAL, 'beautifulsoup4',
         check_module('bs4', 'better table-of-contents generation')),
        (RECOMMENDED, 'Noto Serif KR font',
         check_font(('notoserifkr', 'noto serif kr', 'notoserifcjk'),
                    'Korean body text; without it the fallback face changes '
                    'the line breaks and therefore the page count',
                    fonts)),
        (RECOMMENDED, 'Noto Sans KR font',
         check_font(('notosanskr', 'noto sans kr', 'notosanscjk'),
                    'Korean headings', fonts)),
        # Only Korean was checked here, so a run targeting Japanese or
        # Chinese got no word about its own body face. Measured on this
        # machine: with no Mincho installed the Japanese stack falls through
        # the generic `serif` keyword, and for that script the browser
        # answers with Yu GOTHIC -- the body sets in a sans and every check
        # passes. Source Han Serif JP is not accepted as a pass: it is CFF,
        # and this Chromium emits it as a Type3 font, which is the failure
        # the Korean rule ("static, 0 Type3") already exists to refuse.
        (RECOMMENDED, 'Japanese serif (Mincho)',
         check_font(('mincho', 'hiragino', 'notoserifjp'),
                    'Japanese body text; without one the stack reaches the '
                    'generic serif, which resolves to a GOTHIC face -- the '
                    'body prints in a sans where the design says serif',
                    fonts)),
        (RECOMMENDED, 'Chinese serif (FangSong/SimSun)',
         check_font(('simfang', 'fangsong', 'simsun', 'notoserifsc'),
                    'Chinese body text; FangSong is absent on a stock '
                    'Windows outside China and SimSun is the named fallback',
                    fonts)),
        (RECOMMENDED, 'a math font',
         check_font(('cambria', 'stix', 'latinmodern-math', 'lmmath',
                     'notosansmath', 'xits'),
                    'formulas need an OpenType MATH table; Cambria Math ships '
                    'with Office, STIX Two Math is the free alternative',
                    fonts)),
    ]

    width = max(len(name) for _s, name, _r in checks)
    missing_required, missing_other = [], []
    for severity, name, (ok, detail, why) in checks:
        mark = 'OK  ' if ok else ('MISSING' if severity == REQUIRED else 'absent')
        print('%-8s %-*s %s' % (mark, width, name, detail or ''))
        if not ok:
            print('%-8s %-*s   ^ %s' % ('', width, '', why))
            (missing_required if severity == REQUIRED
             else missing_other).append(name)

    print()
    if missing_required:
        print('%d required component(s) missing: %s'
              % (len(missing_required), ', '.join(missing_required)))
        print('This machine cannot build a book until they are installed.')
    elif missing_other:
        print('Everything required is present. Missing: %s'
              % ', '.join(missing_other))
        if any('font' in name for name in missing_other):
            print('A missing font is not cosmetic: the fallback face has '
                  'different metrics, so the lines break elsewhere and the '
                  'page count of the finished book will not match.')
        else:
            print('Nothing here changes the finished book.')
    else:
        print('Everything this pipeline uses is present.')

    print()
    print('This lists what is installed. To prove the output matches, build a '
          'real PDF and measure it:')
    print('    python tests/layout_probe.py --strict')
    print('    python -m unittest discover -s tests -p "test_*.py"')
    return 1 if (strict and missing_required) else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--strict', action='store_true',
                        help='exit 1 when a required component is missing')
    args = parser.parse_args()
    return probe(args.strict)


if __name__ == '__main__':
    sys.exit(main())

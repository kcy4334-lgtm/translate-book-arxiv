#!/usr/bin/env python3
"""
arxiv_backend.py - Build input.md + images/ from a paper's arXiv LaTeX source.

Why this exists
---------------
Calibre's PDF path runs pdftohtml, which turns every formula into positioned
text spans. There is no math object left to preserve, so no combination of
flags can recover an equation from the PDF. The LaTeX source, in contrast, still
has the math as math — converting it never round-trips through pixels.

Contract with convert.py
------------------------
build() must produce, inside temp_dir:
  - input.md   (markdown with $...$ / $$...$$ math intact)
  - images/    (raster images; PDF/EPS figures rasterized to PNG)
and return (ok, metadata_dict). Everything downstream (chunking, manifest,
translation, merge) is unchanged.
"""

import os
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.error
import urllib.request

import math_guard
import paper_macros

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError, OSError):
        pass


# arXiv rejects the default urllib User-Agent, so identify ourselves.
_UA = 'translate-book/1.0 (+https://arxiv.org/help/api/user-manual)'

_ID_RE = re.compile(r'ar\s?X\s?iv[:\s]*(\d{4}\.\d{4,5})(v\d+)?', re.I)
_OLD_ID_RE = re.compile(r'arXiv[:\s]*([a-z\-]+(?:\.[A-Z]{2})?/\d{7})(v\d+)?', re.I)


def normalize_arxiv_id(raw):
    """Normalize a user- or PDF-supplied arXiv id."""
    if not raw:
        return None
    text = str(raw).strip()
    text = re.sub(r'^(?:https?://)?(?:www\.)?arxiv\.org/(?:abs|pdf|e-print)/', '', text, flags=re.I)
    text = re.sub(r'\.pdf$', '', text, flags=re.I)
    text = re.sub(r'^arxiv:\s*', '', text, flags=re.I)
    return text.strip() or None


# =============================================================================
# Detection
# =============================================================================

def detect_arxiv_id(pdf_path):
    """Return (arxiv_id_or_None, signal_description).

    Two independent signals are used:
      1. The vertical stamp arXiv prints in the page-1 margin.
      2. metadata['creator'] == 'arXiv GenPDF (tex2pdf:...)', which proves the
         submission was LaTeX source — i.e. /e-print will return a tarball
         rather than a bare PDF.
    """
    try:
        import pymupdf
    except ImportError:
        try:
            import fitz as pymupdf  # noqa: N813
        except ImportError:
            return None, 'pymupdf unavailable'

    signals = []
    doc = None
    try:
        doc = pymupdf.open(pdf_path)
        meta = doc.metadata or {}
        creator = meta.get('creator') or ''
        if 'arxiv' in creator.lower():
            signals.append(f'creator={creator!r}')

        for pno in range(min(2, doc.page_count)):
            text = doc[pno].get_text("text")
            m = _ID_RE.search(text) or _OLD_ID_RE.search(text)
            if m:
                signals.append(f'page-{pno + 1} stamp {m.group(0)!r}')
                found = normalize_arxiv_id(m.group(1) + (m.group(2) or ''))
                return found, '; '.join(signals)

        # DOI form: 10.48550/arXiv.XXXX.XXXXX
        if doc.page_count:
            m = re.search(r'10\.48550/arXiv\.(\d{4}\.\d{4,5})',
                          doc[0].get_text("text"), re.I)
            if m:
                signals.append('DOI')
                return normalize_arxiv_id(m.group(1)), '; '.join(signals)
    except Exception as e:
        signals.append(f'pdf read error: {e}')
    finally:
        if doc is not None:
            try:
                doc.close()
            except Exception:
                pass

    # Filename fallback: 2606.04980v1.pdf
    base = os.path.basename(pdf_path)
    m = re.search(r'(?<!\d)(\d{4}\.\d{4,5})(v\d+)?(?!\d)', base)
    if m:
        signals.append('filename')
        return normalize_arxiv_id(m.group(0)), '; '.join(signals)

    return None, '; '.join(signals) or 'no arXiv signals'


# Commands whose whole call (including the argument) is dropped from a title.
_TITLE_DROP_CMDS = ('thanks', 'footnote', 'IEEEmembership', 'inst',
                    'institute', 'affiliation', 'orcid', 'email')


def _balanced_arg(text, brace_at):
    """Contents of the {...} group opening at brace_at, or None."""
    depth = 0
    for i in range(brace_at, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return text[brace_at + 1:i]
    return None


def clean_latex_title(raw):
    """Reduce a LaTeX title to plain text."""
    if not raw:
        return ''
    text = raw
    # Drop commands whose argument is not part of the title at all.
    for cmd in _TITLE_DROP_CMDS:
        while True:
            m = re.search(r'\\' + cmd + r'\s*(\[[^\]]*\])?\s*\{', text)
            if not m:
                break
            arg = _balanced_arg(text, text.index('{', m.end() - 1))
            if arg is None:
                text = text[:m.start()] + text[m.end():]
                break
            end = text.index('{', m.end() - 1) + len(arg) + 2
            text = text[:m.start()] + text[end:]
    text = re.sub(r'\$[^$]*\$', '', text)          # $^{1,2}$ affiliation marks
    text = re.sub(r'\\\\', ' ', text)               # forced line breaks
    text = re.sub(r'\\[a-zA-Z]+\s*\*?\s*\{([^{}]*)\}', r'\1', text)  # \textbf{x} -> x
    text = re.sub(r'\\[a-zA-Z]+\s*', ' ', text)     # bare commands
    text = text.replace('~', ' ').replace('{', '').replace('}', '')
    text = re.sub(r'\s+', ' ', text)
    return text.strip(' ,;:-')


_ABSTRACT_ENV_RE = re.compile(
    r'\\begin\{abstract\}(.*?)\\end\{abstract\}', re.DOTALL)
_KEYWORDS_ENV_RE = re.compile(
    r'\\begin\{IEEEkeywords\}(.*?)\\end\{IEEEkeywords\}', re.DOTALL)


def sectionize_front_matter(tex):
    """Rewrite abstract/keywords environments into starred sections.

    pandoc's LaTeX reader treats `abstract` as document METADATA. Converting to
    markdown without --standalone therefore DROPS it entirely -- the most-read
    part of a paper, gone with no warning. A `\\section*` keeps it in the body,
    and starred means it stays out of the section numbering.

    Returns (tex, count).
    """
    count = 0

    def to_section(title):
        def repl(m):
            nonlocal count
            count += 1
            return '\\section*{%s}\n%s\n' % (title, m.group(1).strip())
        return repl

    tex = _ABSTRACT_ENV_RE.sub(to_section('Abstract'), tex)
    tex = _KEYWORDS_ENV_RE.sub(to_section('Index Terms'), tex)
    return tex, count


def extract_latex_title(tex):
    """The paper's \\title{...}, cleaned. '' when there is none."""
    m = re.search(r'\\title\s*(\[[^\]]*\])?\s*\{', tex or '')
    if not m:
        return ''
    brace = tex.index('{', m.end() - 1)
    return clean_latex_title(_balanced_arg(tex, brace) or '')


_AUTHOR_SEP_RE = re.compile(
    r'\\(?:and|AND|And)\b|\\quad\b|\\qquad\b|\\hspace\*?\s*\{[^{}]*\}|,')
# Inside one author entry the NAME is the first line; `\\` starts the
# affiliation and the e-mail. Gluing the lines together produced
# "Ashish Vaswani Google Brain avaswani@google.com" as a person.
_AUTHOR_LINE_RE = re.compile(r'\\\\')
# Words that make a fragment an institution rather than a person. Short and
# specific on purpose: this decides only whether to REFUSE, and refusing means
# the title page keeps saying "Unknown Author" — which is what it says now.
_NOT_A_PERSON_RE = re.compile(
    r'@|\bhttps?:|\b(?:University|Universit|Institute|Institut|Laborator|Lab\b'
    r'|College|School|Department|Dept\b|Center|Centre|Academy|Research'
    r'|Corporation|Inc\b|Ltd\b|LLC\b|GmbH|Google|Microsoft|Meta\b|OpenAI'
    r'|DeepMind|Huawei|Amazon|Apple\b|Berkeley|Stanford|MIT\b|CMU\b)',
    re.IGNORECASE)
# A note that carries its own argument, removed FIRST so that a comma inside
# `\thanks{Room 2D-149, Murray Hill}` cannot split one author into two.
# Longest name first. Alternation is ordered, so `footnote` in front of
# `footnotemark` matched `\footnote` and left `mark[1]` glued to the name —
# which then carried a digit and the whole author was refused.
_AUTHOR_NOTE_RE = re.compile(
    r'\\(?:footnotemark|footnote|thanksref|thanks|textsuperscript'
    r'|altaffilmark|affmark|affaddr|sthanks|IEEEmembership|orcid|email'
    r'|inst|ead)\s*'
    r'(?:\[[^\]]*\]\s*)?(?:\{(?:[^{}]|\{[^{}]*\})*\})?')
# The rest of the decoration, removed LAST — after the entry has been split on
# `\\`, because `\\` is the line break this model depends on. Removing it first
# glued "Ashish Vaswani Google Brain avaswani@google.com" into one person.
_AUTHOR_MARKUP_RE = re.compile(
    r'\\(?:textbf|textit|texttt|textrm|emph|rm|bf|it|normalfont'
    r'|scriptsize|footnotesize|small|large|Large|quad|qquad|thanksmark'
    r'|enspace|enskip|hfill|hspace|vspace|centering|linebreak|newline'
    r'|samethanks|equalcontrib)\b'
    r'|\$[^$]*\$|\{|\}|~|\\,|\\ |\^\{[^{}]*\}|\^\S')


def extract_latex_authors(tex):
    r"""The paper's author names, from `\author{}` or `\icmlauthor{}`. '' if none.

    The title page falls back to "Unknown Author" whenever the source PDF has
    no author metadata, which arXiv's GenPDF routinely omits — eight finished
    books say it, and every one of them has the names sitting in its own
    flat.tex. This does not try to parse an author BLOCK, only to recover the
    names from it: affiliations, footnote marks and superscripts are markup and
    come off.
    """
    tex = tex or ''
    icml = re.findall(r'\\icmlauthor\s*\{((?:[^{}]|\{[^{}]*\})*)\}', tex)
    if icml:
        names = icml
    else:
        m = re.search(r'\\author\s*(?:\[[^\]]*\])?\s*\{', tex)
        if not m:
            return ''
        block = _balanced_arg(tex, tex.index('{', m.end() - 1)) or ''
        block = re.sub(r'(?m)^\s*%.*$', '', block)     # a commented-out author
        block = _AUTHOR_NOTE_RE.sub(' ', block)
        names = []
        for entry in _AUTHOR_SEP_RE.split(block):
            # The name is the first line of the entry; the rest is where they
            # work and how to reach them.
            names.append(_AUTHOR_LINE_RE.split(entry)[0])
    out = []
    for name in names:
        name = ' '.join(_AUTHOR_MARKUP_RE.sub(' ', name).split())
        name = name.strip(' .,;*†‡§')
        if _NOT_A_PERSON_RE.search(name):
            # An institution where a person should be. Refusing costs the
            # title page nothing it does not already lack; printing it would
            # put a false name on a book (K121's lesson in another costume).
            return ''
        # Nothing but punctuation or spacing: not a name, and not a failure.
        if not name or not re.search(r'[A-Za-zÀ-ɏ]', name):
            continue
        # It looked like a name and did not come out as one — a digit or a
        # backslash means markup survived the strip. Refuse the WHOLE list:
        # `Łukasz Kaiser` is written `{\L}ukasz Kaiser` and `Sherjil Ozair`
        # carries a dagger, and dropping just those two printed seven of
        # Attention's eight authors and seven of GAN's eight. A list missing
        # someone is as wrong as one naming the wrong person, and it is harder
        # to notice.
        if re.search(r'\d|\\', name) or len(name) > 60 \
                or len(name.split()) > 6:
            return ''
        if name not in out:
            out.append(name)
    return '; '.join(out)


def extract_pdf_metadata(pdf_path):
    """Title/author straight from the PDF metadata (cleaner than Calibre's OPF)."""
    out = {}
    try:
        try:
            import pymupdf
        except ImportError:
            import fitz as pymupdf  # noqa: N813
        doc = pymupdf.open(pdf_path)
        meta = doc.metadata or {}
        doc.close()
        if meta.get('title'):
            out['title'] = meta['title'].strip()
        if meta.get('author'):
            out['creator'] = meta['author'].strip()
    except Exception:
        pass
    return out


# =============================================================================
# Fetch + unpack
# =============================================================================

def fetch_eprint(arxiv_id, cache_dir):
    """Download https://arxiv.org/e-print/<id>, cached inside cache_dir.

    Caching means a retried or resumed run needs no network at all.
    """
    os.makedirs(cache_dir, exist_ok=True)
    cache = os.path.join(cache_dir, f'eprint_{arxiv_id.replace("/", "_")}.bin')
    if os.path.exists(cache) and os.path.getsize(cache) > 0:
        print(f"Using cached e-print: {os.path.basename(cache)} "
              f"({os.path.getsize(cache):,} bytes)")
        return cache

    url = f'https://arxiv.org/e-print/{arxiv_id}'
    print(f"Fetching LaTeX source: {url}")
    req = urllib.request.Request(url, headers={'User-Agent': _UA})
    try:
        with urllib.request.urlopen(req, timeout=180) as resp, open(cache, 'wb') as f:
            shutil.copyfileobj(resp, f)
    except urllib.error.HTTPError as e:
        if e.code in (403, 404):
            print(f"arXiv has no source for {arxiv_id} (HTTP {e.code}) — "
                  f"PDF-only submission or withdrawn.")
        else:
            print(f"arXiv fetch failed (HTTP {e.code}): {e.reason}")
        if os.path.exists(cache):
            os.remove(cache)
        return None
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        print(f"arXiv fetch failed: {e}")
        if os.path.exists(cache):
            os.remove(cache)
        return None

    print(f"Downloaded {os.path.getsize(cache):,} bytes")
    return cache


def _safe_extract(tf, dest):
    # filter='data' (Python 3.12) blocks absolute paths, ../ traversal, links,
    # devices and setuid bits. Non-negotiable for a downloaded tarball.
    try:
        tf.extractall(dest, filter='data')
    except TypeError:  # pragma: no cover - Python < 3.12
        tf.extractall(dest)


def unpack_eprint(blob_path, dest):
    """Unpack an arXiv e-print blob.

    Returns 'tree' | 'single' | 'pdf' | None. arXiv serves any of: a gzipped tar
    of the source tree, a plain tar, a bare gzipped .tex, or (for PDF-only
    submissions) a PDF.
    """
    os.makedirs(dest, exist_ok=True)
    with open(blob_path, 'rb') as f:
        head = f.read(8)

    if head[:4] == b'%PDF':
        return 'pdf'

    if head[:2] == b'\x1f\x8b':
        import gzip
        try:
            with tarfile.open(blob_path, 'r:gz') as tf:
                _safe_extract(tf, dest)
            return 'tree'
        except tarfile.ReadError:
            with open(blob_path, 'rb') as f:
                data = gzip.decompress(f.read())
            if data[:4] == b'%PDF':
                return 'pdf'
            with open(os.path.join(dest, 'main.tex'), 'wb') as f:
                f.write(data)
            return 'single'

    try:
        with tarfile.open(blob_path, 'r:') as tf:
            _safe_extract(tf, dest)
        return 'tree'
    except tarfile.ReadError:
        return None


# =============================================================================
# Locate and flatten the LaTeX source
# =============================================================================

# `\documentstyle` is the LaTeX 2.09 spelling that `\documentclass` replaced in
# 1994. Shor's 1995 paper still writes it, and requiring the modern spelling
# rejected a complete single-file 111 KB document — 47 equations and 75
# references — as "no top-level .tex found", then fell back to a backend that
# cannot recover equations at all.
#
# Neither pattern is anchored to the start of a line: `\makeatletter\document`
# `class{...}` is legal LaTeX and was missed too. What the old anchor was
# really guarding against is a commented-out line, so guard against that
# instead — no `%` between the line start and the command.
_DOC_DECL_RE = re.compile(r'^[^%\n]*\\document(?:class|style)\b', re.M)
# `\begin {document}` with space or a newline before the brace is accepted by
# TeX. The old test was a literal `in` substring check, which is not.
_DOC_BEGIN_RE = re.compile(r'^[^%\n]*\\begin\s*\{\s*document\s*\}', re.M)


def find_main_tex(root):
    """Locate the top-level .tex file, or None if the tree has no document."""
    # arXiv's own directive wins when present.
    for name in ('00README.XXX', '00README.json'):
        p = os.path.join(root, name)
        if os.path.exists(p):
            try:
                with open(p, encoding='utf-8', errors='replace') as f:
                    m = re.search(r'toplevelfile\s+(\S+)', f.read())
                if m:
                    cand = os.path.join(root, m.group(1))
                    if os.path.exists(cand):
                        return cand
            except OSError:
                pass

    best, best_score = None, -1
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            if not fn.lower().endswith('.tex'):
                continue
            path = os.path.join(dirpath, fn)
            try:
                with open(path, encoding='utf-8', errors='replace') as f:
                    src = f.read()
            except OSError:
                continue
            # A file qualifies or it does not; the score only RANKS the ones
            # that do. Expressing the requirement as "score >= 20" made the
            # two flags worth exactly the threshold, so any other adjustment
            # could veto a real document: a top-level file already paid -1 for
            # depth, and a LaTeX2e paper whose \title sits in an \input'd file
            # and whose name is not one of the four below scored 19 and was
            # rejected. Nothing said so; it fell back to calibre and lost its
            # equations.
            if not (_DOC_DECL_RE.search(src) and _DOC_BEGIN_RE.search(src)):
                continue
            score = 0
            if r'\title' in src:
                score += 2
            if r'\maketitle' in src:
                score += 2
            # Depth relative to the root, with the separator that joins them
            # not counted: `<root>/main.tex` is at depth 0, not 1.
            score -= path[len(root):].strip(os.sep).count(os.sep)
            if fn.lower() in ('main.tex', 'ms.tex', 'paper.tex', 'arxiv.tex'):
                score += 3
            if score > best_score:
                best, best_score = path, score

    return best


# \b after the command name is essential: without it `\includegraphics{fig.pdf}`
# matches the `\include` alternative and is treated as a missing source file.
_INPUT_RE = re.compile(r'(?<!\\)\\(?:input|include|subfile)\b\s*(?:\{([^}]*)\}|(\S+))')


def normalize_newlines(text):
    r"""Collapse CRLF/CR to LF.

    Required before writing on Windows: Python's text mode translates every
    `\n` to `\r\n`, so a `\r\n` already present in pandoc's output becomes
    `\r\r\n` on disk — which reads back as TWO newlines, i.e. a blank line that
    was never there. Inside `$$` display math that blank line terminates the
    formula and pandoc then swallows the following prose as math.
    """
    return text.replace('\r\n', '\n').replace('\r', '\n')
_VERBATIM_OPEN_RE = re.compile(r'\\begin\{(verbatim|lstlisting|minted|Verbatim|alltt)\*?\}')
_VERBATIM_CLOSE_RE = re.compile(r'\\end\{(verbatim|lstlisting|minted|Verbatim|alltt)\*?\}')


def _resolve_tex(target, cur_dir, root):
    cands = []
    for base in (cur_dir, root):
        cands.append(os.path.join(base, target))
        if not target.lower().endswith('.tex'):
            cands.append(os.path.join(base, target + '.tex'))
    for c in cands:
        if os.path.isfile(c):
            return c
    return None


def flatten_tex(path, root, seen=None, depth=0):
    r"""Inline \input/\include/\subfile recursively.

    Done here rather than left to pandoc: an unresolved \input silently deletes
    a whole section, and that failure is invisible in the output.
    """
    if depth > 12:
        print(f"Warning: \\input nesting deeper than 12 at {path}")
        return ''
    seen = set() if seen is None else seen
    real = os.path.realpath(path)
    if real in seen:
        return ''  # cycle guard
    seen.add(real)

    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            text = f.read()
    except OSError as e:
        print(f"Warning: cannot read {path}: {e}")
        return ''

    out = []
    verbatim_depth = 0
    for line in text.split('\n'):
        if verbatim_depth or _VERBATIM_OPEN_RE.search(line):
            verbatim_depth += len(_VERBATIM_OPEN_RE.findall(line))
            verbatim_depth -= len(_VERBATIM_CLOSE_RE.findall(line))
            verbatim_depth = max(0, verbatim_depth)
            out.append(line)
            continue

        # Never follow an \input that sits inside a comment.
        code = '' if re.match(r'^\s*%', line) else line.split('%')[0]
        m = _INPUT_RE.search(code) if code else None
        if not m:
            out.append(line)
            continue

        target = (m.group(1) or m.group(2) or '').strip()
        cand = _resolve_tex(target, os.path.dirname(path), root)
        if cand:
            out.append(line[:m.start()])
            out.append(flatten_tex(cand, root, seen, depth + 1))
            out.append(line[m.end():])
        else:
            print(f"Warning: unresolved \\input{{{target}}}")
            out.append(line)

    return '\n'.join(out)


def inline_bibliography(tex, root):
    r"""Replace \bibliography{...} with the compiled .bbl, when one shipped.

    pandoc reads a thebibliography environment into a real list, so this is what
    keeps the reference section from vanishing.
    """
    bbl = None
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            if fn.lower().endswith('.bbl'):
                bbl = os.path.join(dirpath, fn)
                break
        if bbl:
            break
    if not bbl:
        return tex

    try:
        with open(bbl, encoding='utf-8', errors='replace') as f:
            body = f.read()
    except OSError:
        return tex

    patched, n = re.subn(r'(?<!\\)\\bibliography\s*\{[^}]*\}', lambda _m: body, tex)
    if n == 0:
        patched, n = re.subn(r'(?<!\\)\\printbibliography(?:\[[^\]]*\])?',
                             lambda _m: body, tex)
    if n:
        print(f"Inlined bibliography from {os.path.basename(bbl)}")
    return patched


# natbib writes `\bibitem[Author et al.(2024)Full, Author, List]{citekey}`.
# The short label before the parenthesis plus the year is what a reader expects
# to see in the text.
_BIBITEM_RE = re.compile(
    r'\\bibitem\[([^\]]*)\]\{([^}]*)\}|\\bibitem\{([^}]*)\}')
_CITE_TOKEN_RE = re.compile(r'(?<!\\)\[@([^\]\n]{1,400})\]')
# A bare `@key`, which is how pandoc writes an author-in-text `\citet{}`.
# Not preceded by `[` (that is the bracketed form, handled above), by a word
# character or a dot (that would be an email address), or by a backslash.
# Ends on an alphanumeric so sentence punctuation is not eaten.
_BARE_CITE_RE = re.compile(
    r'(?<![\[\w@\\.])@([A-Za-z][A-Za-z0-9_:.\-]{1,120}[A-Za-z0-9])')
# `Adepu et al. (2024) (Ashkboos et al. 2024b)` -- one citation that arrived
# split. The second half must itself carry a year, so an ordinary
# parenthetical aside after a date is never swallowed.
_ADJACENT_CITE_RE = re.compile(
    r'([A-Z][A-Za-z.&\\ ]{1,40}?)[ ]*\(((?:19|20)\d{2}[a-z]?)\)'
    r'[ ]*\(([^()\n]{3,140}?(?:19|20)\d{2}[a-z]?)\)')


def _inside_parens(text, pos):
    """Is `pos` inside an unclosed `(` on its own line?"""
    start = text.rfind('\n', 0, pos) + 1
    depth = 0
    for ch in text[start:pos]:
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth = max(0, depth - 1)
    return depth > 0


def _clean_bib_label(raw):
    r"""`Ashkboos et~al.(2024{\natexlab{a}})Ashkboos, Croci, ...` -> `Ashkboos et al. 2024a`."""
    label = raw
    label = re.sub(r'\{\\natexlab\{([^}]*)\}\}', r'\1', label)
    label = label.replace('~', ' ')
    m = re.match(r'\s*(.*?)\(([^)]*)\)', label)
    if m:
        authors, year = m.group(1).strip().rstrip(','), m.group(2).strip()
        label = f'{authors} {year}'.strip()
    label = re.sub(r'\\[a-zA-Z]+\s*', '', label)
    label = re.sub(r'[{}]', '', label)
    return re.sub(r'\s+', ' ', label).strip()


def build_citation_map(root):
    """Map bibtex key -> human citation label, harvested from a .bbl."""
    mapping = {}
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            if not fn.lower().endswith('.bbl'):
                continue
            try:
                with open(os.path.join(dirpath, fn), encoding='utf-8', errors='replace') as f:
                    text = f.read()
            except OSError:
                continue
            for m in _BIBITEM_RE.finditer(text):
                label, key, bare_key = m.group(1), m.group(2), m.group(3)
                if bare_key:
                    continue  # no label to show; leave those alone
                cleaned = _clean_bib_label(label)
                if key and cleaned:
                    mapping[key] = cleaned
    return mapping


def resolve_citation_keys(text, citation_map):
    r"""Turn `[@key1; @key2]` into `(Author Year; Author Year)`.

    Without this, a paper whose arXiv source ships only a compiled `.bbl` (no
    `.bib`, so citeproc cannot run) leaves raw bibtex keys in the reader's face.
    Keys with no label found are left untouched rather than silently deleted.
    """
    if not citation_map:
        return text

    resolved = [0]

    def handle(m):
        keys = [k.strip().lstrip('@') for k in m.group(1).split(';')]
        labels = []
        for key in keys:
            label = citation_map.get(key)
            if not label:
                return m.group(0)  # unknown key: leave the whole group as-is
            labels.append(label)
        resolved[0] += 1
        return '(' + '; '.join(labels) + ')'

    out = _CITE_TOKEN_RE.sub(handle, text)

    # `\citet{key}` puts the author's name in the sentence, so pandoc writes
    # it WITHOUT brackets -- a bare `@key`. The pattern above only sees the
    # bracketed form, so those printed as raw bibtex keys in the reader's
    # face: CafeQ shipped five of them, one sitting right beside a citation
    # that had rendered correctly, in a build where all 61 labels had been
    # harvested and were sitting in this very map.
    def handle_bare(m):
        label = citation_map.get(m.group(1))
        if not label:
            return m.group(0)
        resolved_bare[0] += 1
        # Author-in-text form: the name carries the sentence, the year is
        # parenthesised -- `Adepu et al. (2024)`, not `(Adepu et al. 2024)`.
        # But inside a parenthesis the sentence is not carrying anything, and
        # `(예: Dettmers & Zettlemoyer (2023))` nests brackets for no reason,
        # so there the plain label is what a copy editor would leave.
        if _inside_parens(out_text[0], m.start()):
            return label
        year = re.match(r'^(.*?)[\s,]+((?:19|20)\d{2}[a-z]?)$', label)
        return f'{year.group(1)} ({year.group(2)})' if year else label

    resolved_bare = [0]
    out_text = [out]
    out = _BARE_CITE_RE.sub(handle_bare, out)

    # `\citep{A, B}` can reach us split into an in-text `@A` and a bracketed
    # `[@B]`, which resolves to two parentheses back to back:
    # `Adepu et al. (2024) (Ashkboos et al. 2024b)`. They are one citation.
    out, merged = _ADJACENT_CITE_RE.subn(
        lambda m: '(%s %s; %s)' % (m.group(1), m.group(2), m.group(3)), out)

    if resolved[0] or resolved_bare[0]:
        print(f"Resolved {resolved[0]} citation group(s) and "
              f"{resolved_bare[0]} in-text citation(s) from .bbl labels"
              + (f"; merged {merged} adjacent pair(s)" if merged else ""))
    return out


def extract_math_macros(tex):
    r"""Collect preamble macro definitions so a renderer can be taught them.

    NOT extended to the `.sty` files in the tarball, though that is where a
    collaboration keeps its macros and their absence costs real formulas
    (K121). Collecting them was tried and measured: it made the ATLAS paper
    WORSE, 256 refused formulas to 272. Two reasons, both needing real work
    rather than a wider pattern — this collector is line-anchored and a `.sty`
    definition wraps (`\def\GeV{\ifmmode {...}\else` continues on the next
    line, so the fragment collected does not balance), and the bodies that do
    parse are mode-dependent `\ifmmode` conditionals that texmath cannot read
    either. A half-collected package is worse than none: it turns a name the
    renderer cannot read into a different name it cannot read.
    """
    pattern = re.compile(
        r'^[ \t]*\\(?:newcommand|renewcommand|providecommand|DeclareMathOperator'
        r'|newoperator|def)\b.*$', re.M)
    preamble = tex.split(r'\begin{document}')[0]
    return [m.group(0).strip() for m in pattern.finditer(preamble)]


# =============================================================================
# LaTeX -> markdown
# =============================================================================

# +raw_tex on the READER is required: this pandoc build cannot parse tabular or
# longtable at all — it flattens them into `cc a & b  1 & 2`. With raw_tex the
# environment survives verbatim and can be preserved instead of mangled.
_READER = 'latex+raw_tex'

# -raw_html on the WRITER is required (measured): with raw_html enabled, figures
# come out as <embed src="x.pdf"> (invisible to the image validator) and math
# inside captions is destroyed into Unicode. Disabling it yields ![](x.pdf) and
# keeps caption math as $...$.
# -simple_tables-multiline_tables: both delimit their columns by CHARACTER
# POSITION in the ruler line, which a translator cannot preserve and keep the
# text readable once the cells hold CJK -- CafeQ's header row came out two
# columns out of step and its first cell rendered as "적함수". A pipe table
# marks every cell boundary with `|` and does not care how wide anything is.
# Simple and multiline tables are off because they mark columns by CHARACTER
# POSITION, which no translation survives (K49, K52). Grid tables have the
# same weakness and are deliberately LEFT ON anyway: they are the only format
# pandoc can use for a table with a spanning multi-deck header, and turning
# them off did not make such a table safe -- it made pandoc write the literal
# text `[TABLE]` in its place and CafeQ lost a whole results table. A grid
# table that reaches the merge is converted to a pipe table there, once the
# translator is done with it, which is the point at which nothing can drift
# any further.
_WRITER = ('markdown+tex_math_dollars-raw_html-bracketed_spans-native_spans'
           '-simple_tables-multiline_tables+pipe_tables+grid_tables'
           '-native_divs-link_attributes-header_attributes'
           '-inline_code_attributes-markdown_attribute-smart')


def find_bib_files(root):
    """Locate .bib files shipped in the arXiv source tree."""
    found = []
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            if fn.lower().endswith('.bib'):
                found.append(os.path.join(dirpath, fn))
    return sorted(found)


# Presentation-only markup that pandoc does not consume and that therefore
# reaches the markdown as literal text. \cellcolor is the one that does real
# damage: pandoc writes wide tables as *simple tables*, whose columns are
# defined by the position of the dashes in the ruler line. A cell carrying
# `\cellcolor{customblue!30}` overruns that ruler, and on the way back in the
# markdown reader splits the row at the ruler column instead -- landing inside
# the command and tearing it in half. The table survives, full of debris like
# `\cellcolor{cus` / `tomblue!30}` cells.
_TEX_NOISE = (
    # (pattern, replacement)
    # `appendices` (from the appendix package) has no pandoc reader, so the
    # WHOLE appendix becomes one raw block: its figures are never resolved into
    # images/, its lists and listings never convert, and the HTML writer drops
    # the lot. Neural ODE lost its entire appendix that way, and the loss was
    # invisible because a single raw block reports as a single finding. The
    # wrapper carries nothing — `\appendix` before it already switched the
    # numbering — so removing the two lines costs nothing and recovers
    # everything inside.
    (re.compile(r'(?m)^[ \t]*\\(?:begin|end)\{(?:appendices|subappendices)\}'
                r'[ \t]*$\n?'), ''),
    (re.compile(r'\\(?:cell|row|column)color\s*(?:\[[^\]]*\])?\s*\{[^{}]*\}'), ''),
    (re.compile(r'\\printAffiliationsAndNotice\s*\{[^{}]*\}'), ''),
    # \cmidrule draws a partial rule under a few columns. pandoc consumes the
    # command name but not its argument, so the row's first cell ends up
    # reading "2-2" and the next \cmidrule prints verbatim beside it.
    #
    # Handled per tabular by normalize_table_rules() below, which keeps the
    # ones that separate row GROUPS and drops the ones that only underline a
    # column group. Deleting all of them, as this used to, lost both.
    # Column padding, glue and struts: page geometry, no content.
    (re.compile(r'\\setlength\s*\{[^{}]*\}\s*\{[^{}]*\}'), ''),
    (re.compile(r'\\(?:hfill|vfill|hrulefill|dotfill)(?![a-zA-Z])'), ''),
    # \hbox{4-bit} exists to stop a line break; the words are the content.
    (re.compile(r'\\(?:hbox|mbox)\s*\{([^{}]*)\}'), r'\1'),
)

_TABLE_NOTE_RE = re.compile(r'\\tnote\s*\{([^{}]*)\}')


def unwrap_table_notes(tex):
    r"""`\tnote{$\dagger$}` -> `\textsuperscript{$\dagger$}`. (text, count).

    threeparttable's row marker. pandoc has no reader for `\tnote` and drops
    the call with its body, so the dagger tying a row to the footnote below
    the table goes with it -- SINQ's tables carry seventeen and four reached
    the page. Nothing counted them: the rows were all there, the numbers
    were all there, and the mark saying which rows the footnote spoke about
    was not. It is a superscript marker, so it becomes one.
    """
    return _TABLE_NOTE_RE.subn(r'\\textsuperscript{\1}', tex)


# Both take throwaway arguments and then the text that matters.
_BOXED_LABEL_RE = re.compile(
    r'\\rotatebox\s*(?:\[[^\]]*\])?\s*\{[^{}]*\}\s*(?=\{)'
    r'|\\multirow\s*\*?\s*(?:\[[^\]]*\])?\s*\{[^{}]*\}\s*\{[^{}]*\}\s*(?=\{)')


def unwrap_rotatebox(tex):
    """`\\rotatebox{90}{\\textsc{4-bit}}` -> `\\textsc{4-bit}`. (text, count).

    A rotated or row-spanning label is how a narrow column carries a group
    name. pandoc drops both calls whole, argument and all, so SINQ's
    bit-width column and its "Calibration free" column came out empty in
    every table that used one: the rows were there and nothing said which
    group they belonged to. The body is read with a balanced scan because it
    is usually `{\\textsc{...}}`, not a flat string. The span itself is lost,
    so the label sits in the first row of its group rather than beside all of
    them -- which is what a reader needs anyway.

    The two nest. SINQ writes every band label as
    `\\multirow{4}{*}{\\rotatebox[origin=c]{90}{\\scriptsize\\textsc{3-bit}}}`,
    and one pass takes the `\\multirow` and then steps the cursor over the
    whole group -- so the `\\rotatebox` inside starts behind the cursor, is
    skipped, and pandoc eats the label after all. Nine of SINQ's tables lost
    their band labels to that: table 1 printed the same four method rows
    twice with nothing saying which block was 3-bit and which was 4-bit.
    """
    count = 0
    while True:
        tex, n = _unwrap_boxed_once(tex)
        count += n
        if not n:                 # each pass removes one, so this terminates
            return tex, count


def _unwrap_boxed_once(tex):
    out, cursor, count = [], 0, 0
    for m in _BOXED_LABEL_RE.finditer(tex):
        if m.start() < cursor:
            continue
        close = _balanced_brace(tex, m.end())
        if close < 0:
            continue
        out.append(tex[cursor:m.start()])
        out.append(tex[m.end() + 1:close - 1])
        cursor = close
        count += 1
    out.append(tex[cursor:])
    return ''.join(out), count


_RESIZEBOX_RE = re.compile(r'\\(?:resize|scale)box\s*\*?\s*\{')


def _balanced_brace(text, open_at):
    """Index just past the `{...}` group starting at open_at, or -1."""
    depth = 0
    for i in range(open_at, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return i + 1
    return -1


def unwrap_resizebox(tex):
    """`\\resizebox{w}{h}{BODY}` -> `BODY`. Returns (text, count).

    Not cosmetic housekeeping: while the wrapper is there pandoc cannot parse
    the enclosing `\\begin{table}`, so it emits the bare tabular and throws the
    float's \\caption away. \\scalebox takes two arguments rather than three and
    is handled by the same scan.
    """
    count = 0
    guard = 0
    while guard < 200:
        guard += 1
        m = _RESIZEBOX_RE.search(tex)
        if not m:
            break
        wanted = 2 if 'scalebox' in m.group(0) else 3
        pos, args = m.end() - 1, []
        for _ in range(wanted):
            close = _balanced_brace(tex, pos)
            if close < 0:
                break
            args.append((pos, close))
            nxt = re.match(r'\s*\{', tex[close:])
            if not nxt:
                pos = close
                break
            pos = close + nxt.end() - 1
        if len(args) < wanted:
            # Malformed or unexpected shape: leave it alone rather than guess,
            # and rename it so the scan can move past it.
            tex = tex[:m.start()] + '\\KEEPBOX' + tex[m.start() + len(m.group(0)) - 1:]
            continue
        body_open, body_close = args[-1]
        tex = tex[:m.start()] + tex[body_open + 1:body_close - 1] + tex[body_close:]
        count += 1
    return tex.replace('\\KEEPBOX', '\\resizebox'), count


_SUBFLOAT_CMD_RE = re.compile(r'\\subfloat\b[ \t]*')


def _in_comment(tex, pos):
    """Is `pos` inside a % comment? A comment runs to the end of its line."""
    i = tex.rfind('\n', 0, pos) + 1
    while i < pos:
        if tex[i] == '\\':
            i += 2
            continue
        if tex[i] == '%':
            return True
        i += 1
    return False


def unwrap_subfloat(tex):
    """`\\subfloat[cap]{BODY}` -> `BODY` on its own paragraph. (text, count).

    pandoc has no reader for the subfig package, so a \\subfloat survives into
    the markdown verbatim -- and the \\includegraphics inside it is therefore
    never seen by resolve_images, which only rewrites images pandoc already
    emitted. SINQ builds its Figures 4 and 5 this way and both were simply
    absent from the translated book: caption printed, plot gone, no warning
    anywhere. Its other figures use \\begin{subfigure}, which pandoc does read,
    which is why the loss looked like a tikz limitation rather than a bug.

    The body is separated by blank lines so each panel lands in its own
    paragraph; format_figure_blocks matches an image alone on its line.
    """
    count, guard = 0, 0
    while guard < 400:
        guard += 1
        m = _SUBFLOAT_CMD_RE.search(tex)
        if not m:
            break
        if _in_comment(tex, m.start()):
            # Unwrapping lifts the body onto its own line, out from behind the
            # `%` that was hiding it. SINQ has a commented-out panel that came
            # back as a figure the paper does not print.
            tex = tex[:m.start()] + '\\KEEPSUBFLOAT' + tex[m.end():]
            continue
        pos = m.end()
        # subfig takes \subfloat[list entry][caption]{body}: up to two.
        while pos < len(tex) and tex[pos] == '[':
            close = tex.find(']', pos)
            if close < 0:
                break
            pos = close + 1
            while pos < len(tex) and tex[pos] in ' \t\r\n':
                pos += 1
        end = _balanced_brace(tex, pos) if pos < len(tex) and tex[pos] == '{' else -1
        if end < 0:
            # Unexpected shape: leave it alone rather than guess, and rename it
            # so the scan can move past it.
            tex = tex[:m.start()] + '\\KEEPSUBFLOAT' + tex[m.end():]
            continue
        tex = tex[:m.start()] + '\n\n' + tex[pos + 1:end - 1] + '\n\n' + tex[end:]
        count += 1
    return tex.replace('\\KEEPSUBFLOAT', '\\subfloat'), count


_GRAPHIC_OPT_RE = re.compile(
    r'(\\includegraphics\s*)\[([^\]]*)\]\s*\{([^}]*)\}')

# What each float environment pandoc does not know should be read as. The
# names stay untouched in flat.tex, so float_units still counts the original.
_FLOAT_ALIASES = {
    'SCfigure': 'figure', 'SCtable': 'table',
    'wrapfigure': 'figure', 'wraptable': 'table',
    'sidewaysfigure': 'figure', 'sidewaystable': 'table',
    'floatingfigure': 'figure', 'floatingtable': 'table',
}
_ALIAS_BEGIN_RE = re.compile(
    r'\\begin\{(%s)\}((?:\s*\[[^\]]*\])*)((?:\s*\{[^{}]*\})*)'
    % '|'.join(_FLOAT_ALIASES))
_ALIAS_END_RE = re.compile(r'\\end\{(%s)\}' % '|'.join(_FLOAT_ALIASES))

# paralist's compact lists. pandoc has no reader for them, so the whole
# environment becomes a raw block and the HTML path drops raw LaTeX WHOLE --
# the markup never prints, so nothing looks wrong, and the items inside it
# simply are not in the book. CafeQ lost the two challenges its method is
# built around this way: the introduction says "the key questions come down
# to the following two challenges" and then moves on to the next section.
_LIST_ALIASES = {
    'inparaenum': 'enumerate', 'asparaenum': 'enumerate',
    'compactenum': 'enumerate',
    'inparaitem': 'itemize', 'asparaitem': 'itemize',
    'compactitem': 'itemize',
    'inparadesc': 'description', 'asparadesc': 'description',
    'compactdesc': 'description',
}
_LIST_BEGIN_RE = re.compile(
    r'\\begin\{(%s)\}((?:\s*\[[^\]]*\])*)' % '|'.join(_LIST_ALIASES))
_LIST_END_RE = re.compile(r'\\end\{(%s)\}' % '|'.join(_LIST_ALIASES))


def normalize_list_envs(tex):
    """`inparaenum`/`asparaitem`/... -> `enumerate`/`itemize`. (text, count).

    The optional argument is a label format (`[(1)]`, `[\\bfseries (a)]`) that
    pandoc's list readers do not take, so it goes with the rename.
    """
    tex, n = _LIST_BEGIN_RE.subn(
        lambda m: '\\begin{%s}' % _LIST_ALIASES[m.group(1)], tex)
    tex = _LIST_END_RE.sub(
        lambda m: '\\end{%s}' % _LIST_ALIASES[m.group(1)], tex)
    return tex, n


def encode_graphic_pages(tex):
    """`\\includegraphics[page=4]{x.pdf}` -> `{x--page4.pdf}`. (text, count).

    pandoc drops the option list, so by the time resolve_images sees a figure
    the page number is gone and every panel of a multi-page figure PDF
    rasterizes to page 1. Carrying it in the filename is the only place it
    survives the LaTeX reader.
    """
    count = 0

    def swap(m):
        nonlocal count
        page = re.search(r'\bpage\s*=\s*(\d+)', m.group(2))
        path = m.group(3).strip()
        if not page or page.group(1) == '1' or '--page' in path:
            return m.group(0)
        count += 1
        stem, ext = os.path.splitext(path)
        return '%s[%s]{%s--page%s%s}' % (m.group(1), m.group(2), stem,
                                         page.group(1), ext)

    return _GRAPHIC_OPT_RE.sub(swap, tex), count


def normalize_float_envs(tex):
    """`SCfigure`/`wrapfigure`/... -> `figure`. Returns (text, count).

    pandoc has no reader for these, so the whole environment -- caption,
    \\includegraphics and all -- passes through as raw LaTeX and the figure
    never reaches the book. CafeQ's Figure 1 lives in an SCfigure and was
    missing outright, which looked like the paper simply had no such image.
    """
    tex, n = _ALIAS_BEGIN_RE.subn(
        lambda m: '\\begin{%s}' % _FLOAT_ALIASES[m.group(1)], tex)
    tex = _ALIAS_END_RE.sub(
        lambda m: '\\end{%s}' % _FLOAT_ALIASES[m.group(1)], tex)
    return tex, n


_FLOAT_SPAN_RE = re.compile(
    r'\\begin\{(figure|table)(\*?)\}.*?\\end\{\1\2\}', re.DOTALL)
_CAPTIONOF_RE = re.compile(r'\\captionof\s*\{\s*(?:figure|table)\s*\}\s*')


# A paper shorter than this in markdown is not a paper. The real ones in the
# corpus run from 34 KB up; the wrapper that prompted this produced 43 bytes.
_MIN_BODY_CHARS = 600


def no_latex_body(flat, md):
    r"""Why this source has no document in it, or '' if it has one.

    Not every arXiv "source" contains LaTeX. Adam's is 298 bytes whose whole
    body is `\includepdf[pages=1-last]{0_adam_main.pdf}` — the authors
    submitted a finished PDF in a LaTeX envelope, which is a perfectly normal
    thing to do and leaves this backend nothing whatsoever to convert.

    Caught here rather than downstream because the pipeline REUSES `input.md`:
    written once, a 43-character document is picked up by every later run as
    already converted, and the book is built from it in silence. The failure
    to avoid is not the empty conversion, it is the cheerful "Conversion
    completed successfully!" that followed it.
    """
    body = re.search(r'\\begin\{document\}(.*?)\\end\{document\}', flat,
                     re.DOTALL)
    inner = body.group(1) if body else flat
    if re.search(r'\\includepdf\b', inner):
        return ('the body is \\includepdf — a finished PDF in a LaTeX '
                'envelope, with no source to translate')
    visible = ' '.join(md.split())
    if len(visible) < _MIN_BODY_CHARS:
        return ('the conversion produced %d visible character(s), which is '
                'not a paper' % len(visible))
    return ''


# \def, and the ways a preamble spells it. `\long\def` and friends are matched
# by letting the prefix be optional.
# The name may be a control WORD (`\tablenote`) or a control SYMBOL (`\<`).
# Maths papers shorten their notation with the second kind constantly —
# `\def \< {\langle}` — and a pattern that only knew the first left pandoc to
# die on it exactly as before.
_TEX_DEF_RE = re.compile(
    r'\\(?:long|global|outer|protected)?\s*\\?(?:def|gdef|edef|xdef)'
    r'\s*\\([A-Za-z@]+|[^A-Za-z\s])([^{]*)(?=\{)')
_PLAIN_PARAMS_RE = re.compile(r'^(?:\s*#\d)*\s*$')


# Front matter. pandoc has no reader for any of these, and the two halves fail
# in opposite directions, so they cannot share one rule.
#
# `\address` and `\institute` carry the author's affiliation — real prose. It
# is dropped WITH the command and nothing anywhere reports the loss: Maynard's
# five-line address at Centre de recherches mathematiques appears once in
# flat.tex and zero times in input.md, the chunks and output.md. No count
# disagreed, because a count of what arrived cannot see what did not (K110).
# `\email` is the same shape and nests INSIDE `\institute` in U-Net, so
# deleting it there would strand the `,\\ WWW home page:` that follows.
# Unwrapping all three keeps the text and makes the nesting harmless.
#
# The rest are directives with nothing to read. `\bibliographystyle{plain}`
# is not dropped but PASSED THROUGH, and stood at the end of Maynard's
# acknowledgements as literal text for a translator to puzzle over.
#
# Deliberately absent: `\bibliography{...}`, which citeproc still needs to
# find the .bib, and `\parhead{...}`, which is spectre's own `\newcommand` for
# a run-in heading — twelve real headings that a drop-with-argument rule would
# delete outright.
_FRONT_MATTER_UNWRAP = ('address', 'institute', 'email')
_FRONT_MATTER_DROP = ('bibliographystyle', 'titlerunning', 'authorrunning',
                      'tocauthor', 'icmlkeywords', 'icmlsetsymbol')
# ICML's author block, where the content is in a DIFFERENT argument for each
# command — read out of `icml2026.sty`, not recalled: `\icmlauthor{#1}{#2}`
# sets `\mbox{\bf #1}` and treats #2 as affiliation KEYS, while
# `\icmlaffiliation{#1}{#2}` keys on #1 and stores #2. Get it backwards and an
# affiliation key prints where a name belongs.
#
# Nothing read either, so SINQ's six authors and its one affiliation appear
# zero times in its book — K123's swallow in a second costume, and this one
# reached a shipped v1.
_FRONT_MATTER_TWO_ARG = {
    'icmlauthor': (1,),
    'icmlaffiliation': (2,),
    'icmlcorrespondingauthor': (1, 2),
}
# ...and the environment that holds them. pandoc has no reader for it, so
# rescuing the names into it would only move the loss one level out: the
# wrapper survives as raw LaTeX and takes its contents with it (K110).
_FRONT_MATTER_ENVS = ('icmlauthorlist',)


def _brace_end(text, open_at):
    """Index just past the `}` matching the `{` at open_at, or -1."""
    depth = 0
    i = open_at
    while i < len(text):
        ch = text[i]
        if ch == '\\':
            i += 2
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return -1


def _starts_in_comment(text, pos):
    r"""Is `pos` after an unescaped `%` on its own line?

    planck writes `%\institute{L2 \and Earth}` and U-Net `%\authorrunning{*}`.
    Rewriting those changes nothing a reader sees — but the brace scan does not
    stop at end of line, so a commented-out `\address{` whose `}` never comes
    would run into live text below and take it. Six such matches exist across
    the corpus, so this is measured, not hypothetical.
    """
    i = text.rfind('\n', 0, pos) + 1
    while i < pos:
        if text[i] == '\\':
            i += 2
            continue
        if text[i] == '%':
            return True
        i += 1
    return False


def _rewrite_braced_command(tex, name, keep_body):
    """`\\name[opt]{body}` -> body, or nothing. Returns (text, count)."""
    # The optional argument has to be consumed with the command: `\address[a]`
    # and `\ead[url]` put a label between the two, and a pattern that steps
    # straight from the name to `{` leaves `[a]` printing on the page.
    head = re.compile(r'\\' + name + r'\b\*?\s*(?:\[[^\]]*\]\s*)*')
    count = 0
    at = 0
    while True:
        m = head.search(tex, at)
        if not m:
            return tex, count
        if _starts_in_comment(tex, m.start()):
            at = m.end()
            continue
        if m.end() >= len(tex) or tex[m.end()] != '{':
            # No argument to take: a bare `\maketitle`-shaped use. Leave it;
            # something downstream owns that shape.
            at = m.end()
            continue
        close = _brace_end(tex, m.end())
        if close < 0:
            at = m.end()
            continue
        body = tex[m.end() + 1:close - 1] if keep_body else ''
        tex = tex[:m.start()] + body + tex[close:]
        at = m.start() + len(body)
        count += 1


def _rewrite_two_arg(tex, name, keep):
    r"""`\name{a}{b}` -> the kept arguments, comma-joined. (text, count)."""
    head = re.compile(r'\\' + name + r'\b\*?\s*')
    count = 0
    at = 0
    while True:
        m = head.search(tex, at)
        if not m:
            return tex, count
        if _starts_in_comment(tex, m.start()):
            at = m.end()
            continue
        args, pos = [], m.end()
        while len(args) < 2 and pos < len(tex) and tex[pos] == '{':
            close = _brace_end(tex, pos)
            if close < 0:
                break
            args.append(tex[pos + 1:close - 1])
            pos = close
        if len(args) != 2:
            # All three take exactly two. Anything else is not the shape this
            # models, and reading one argument as the other is how an
            # affiliation key ends up printed as an author's name.
            at = m.end()
            continue
        body = ', '.join(args[i - 1].strip() for i in keep
                         if args[i - 1].strip())
        tex = tex[:m.start()] + body + tex[pos:]
        at = m.start() + len(body)
        count += 1


def unwrap_front_matter(tex):
    r"""Keep the affiliation, drop the directives. Returns (text, count).

    Runs before pandoc so the affiliation arrives as ordinary prose and the
    directives never reach a translator. Unwrapping happens outermost-first,
    which is what makes U-Net's `\institute{... \email{...} ...}` safe: the
    institute goes first, the email it contained is then a top-level command
    and unwraps to its own address, and no punctuation is left dangling.
    """
    count = 0
    for name in _FRONT_MATTER_UNWRAP:
        tex, n = _rewrite_braced_command(tex, name, True)
        count += n
    for name, keep in _FRONT_MATTER_TWO_ARG.items():
        tex, n = _rewrite_two_arg(tex, name, keep)
        count += n
    for name in _FRONT_MATTER_DROP:
        tex, n = _rewrite_braced_command(tex, name, False)
        count += n
    for env in _FRONT_MATTER_ENVS:
        pattern = re.compile(r'\\(?:begin|end)\s*\{%s\}' % re.escape(env))
        tex, n = pattern.subn('', tex)
        count += n // 2
    return tex, count


# Inside `tabbing`, LaTeX rebinds `\>`, `\=`, `\<`, `` \` `` and `\'` to tab
# commands for the length of the environment. pandoc expands the document's own
# macros without knowing that, and Shor wrote the two definitions that turn the
# gap into damage:
#
#     \newcommand{\tab}{\>}              % to keep tabbing usable ...
#     \renewcommand{\>}{\right\rangle}   % ... despite ket notation
#
# so all 29 `\tab`s in his three algorithm listings arrived as `\right\rangle`.
# The pseudocode is the centre of that paper and it read
# `\right\rangle for {\it i} = 0 to {\it l}`.
#
# Only a tab command REDEFINED in the preamble can be damaged this way, and the
# whole corpus has exactly one paper that does it — so this touches nothing
# else. Four spaces is what `merge_and_build.unwrap_tabbing` would have made of
# the stop anyway.
_TABBING_BLOCK_RE = re.compile(r'\\begin\{tabbing\}.*?\\end\{tabbing\}',
                               re.DOTALL)
_TAB_CMDS = ('>', '=', '<', "'", '`')
_TAB_REDEF_RE = re.compile(
    r'\\(?:re)?newcommand\s*\{?\s*\\([>=<\'`])\s*\}?\s*\{')
_TAB_ALIAS_RE = re.compile(
    r'\\(?:re)?newcommand\s*\{\s*\\([A-Za-z]+)\s*\}\s*\{\s*\\([>=<\'`])\s*\}')


def neutralize_tabbing_tabs(tex):
    r"""Turn redefined tab commands back into indentation. (text, count)."""
    at = tex.find(r'\begin{document}')
    preamble = tex[:at] if at >= 0 else tex
    redefined = {m.group(1) for m in _TAB_REDEF_RE.finditer(preamble)}
    if not redefined:
        return tex, 0
    aliases = {name for name, target in _TAB_ALIAS_RE.findall(preamble)
               if target in redefined}
    names = sorted(aliases, key=len, reverse=True)
    total = [0]

    def fix(m):
        body = m.group(0)
        for name in names:
            body, n = re.subn(r'\\%s(?![A-Za-z])\s?' % re.escape(name),
                              '    ', body)
            total[0] += n
        for sym in sorted(redefined):
            body, n = re.subn(r'\\%s' % re.escape(sym), '    ', body)
            total[0] += n
        return body

    return _TABBING_BLOCK_RE.sub(fix, tex), total[0]


def neutralize_tex_defs(tex):
    r"""Drop `\def`s whose parameters are delimited. Returns (text, count).

    pandoc reads `\def\foo{bar}` and even `\def\foo#1{bar}`. What it cannot
    read is TeX's DELIMITED parameter text — `\def\tablenote#1 #2\par{...}`,
    where the space and the `\par` are part of the calling pattern. LaTeX has
    no equivalent, so a macro written that way is plain TeX, and pandoc stops
    the entire conversion at it: Planck 2015 XIII died on one such line, 233
    pages of astrophysics lost to a footnote macro.

    Only the definition goes. Uses survive as raw commands, which pandoc
    already knows how to leave alone, and a macro of this shape is layout —
    it has never been the content. Definitions with plain `#1#2` parameters
    are left exactly as they are: pandoc expands those, and expanding them is
    how a paper's own shorthands reach the page at all.
    """
    # One more shape has to go: a `\def` that redefines an ENVIRONMENT the
    # document then uses. pandoc reads `\begin{thebibliography}` with its own
    # reader, and Shor 1995 redefines `\thebibliography` in the 2.09 way — the
    # two collide and pandoc abandons the file at the closing `\end`, 2400
    # lines in, reporting only "unexpected \end". Measured: removing that one
    # definition converts the paper; removing the `\@biblabel` beside it
    # changes nothing.
    #
    # Which names count is read from the document rather than listed here. A
    # fixed list is a guess about the author, and this pipeline has paid for
    # that guess before (K113).
    used_envs = set(re.findall(r'\\begin\s*\{\s*([A-Za-z@]+\*?)\s*\}', tex))

    out, cursor, count = [], 0, 0
    for m in _TEX_DEF_RE.finditer(tex):
        if m.start() < cursor:
            continue
        name, params = m.group(1), m.group(2)
        # A control SYMBOL always goes. `\def \< {\langle}` is how a maths
        # paper shortens its notation, and pandoc cannot read the definition
        # whatever follows the name — the space after `\<` is parameter text
        # to TeX, and treating it as "no parameters" is what let this one
        # through the first time.
        if (name.isalpha() and _PLAIN_PARAMS_RE.match(params)
                and name not in used_envs):
            continue                       # pandoc handles this one
        brace = tex.index('{', m.end() - 1)
        close = _balanced_brace(tex, brace)
        if close < 0:
            continue
        out.append(tex[cursor:m.start()])
        cursor = close
        count += 1
    out.append(tex[cursor:])
    return ''.join(out), count


_NEWCOLUMNTYPE_RE = re.compile(
    r'\\newcolumntype\s*\{\s*([A-Za-z])\s*\}\s*(?:\[\s*(\d+)\s*\])?\s*(?=\{)')


def _rewrite_spec(spec, types):
    """Replace uses of a custom column type with a plain centred column."""
    out, i = [], 0
    while i < len(spec):
        ch = spec[i]
        arity = types.get(ch)
        if arity is None:
            out.append(ch)
            i += 1
            continue
        i += 1
        for _ in range(arity):                    # eat its brace arguments
            j = i
            while j < len(spec) and spec[j] in ' \t':
                j += 1
            if j < len(spec) and spec[j] == '{':
                close = _balanced_brace(spec, j)
                if close < 0:
                    break
                i = close
            else:
                break
        out.append('c')
    return ''.join(out)


def neutralize_newcolumntype(tex):
    r"""Drop `\newcolumntype` definitions and plain-ify their uses.

    `\newcolumntype{x}[1]{>{\centering}p{#1pt}}` is ordinary array-package
    LaTeX and pandoc has no reader for the parameter: it stops at `unexpected
    #1` and the WHOLE conversion dies. ResNet was asked for on the arXiv path,
    failed on this one line, came back through calibre with every equation
    gone, and reported success.

    The definitions go, because this pipeline renders raw tables itself and
    never needed the column formatting. The USES have to go with them: left
    behind, `x{20}` is an unknown letter followed by a stray brace group, and
    the column count stops matching the rows. `c` is the honest stand-in — a
    custom type here is nearly always a width, which the renderer decides
    anyway. Returns (text, count).
    """
    types, out, cursor = {}, [], 0
    for m in _NEWCOLUMNTYPE_RE.finditer(tex):
        if m.start() < cursor:
            continue
        brace = tex.index('{', m.end() - 1)
        close = _balanced_brace(tex, brace)
        if close < 0:
            continue
        types[m.group(1)] = int(m.group(2) or 0)
        out.append(tex[cursor:m.start()])
        cursor = close
    out.append(tex[cursor:])
    tex = ''.join(out)
    if not types:
        return tex, 0

    pieces, cursor = [], 0
    for m in _TABULAR_OPEN_RE.finditer(tex):
        if m.start() < cursor:
            continue
        start = m.end() - 1
        close = _balanced_brace(tex, start)
        if close < 0:
            continue
        spec = tex[start + 1:close - 1]
        pieces.append(tex[cursor:start + 1])
        pieces.append(_rewrite_spec(spec, types))
        cursor = close - 1
    pieces.append(tex[cursor:])
    return ''.join(pieces), len(types)


def normalize_captionof(tex):
    r"""`\captionof{figure}{...}` -> `\caption{...}`, inside floats only.

    pandoc has no reader for \captionof, so the call survives as a raw inline
    and the HTML path drops it whole -- DeeR-VLA's first two figures reached
    the page with no caption at all. Inside a float the two spellings produce
    the same numbered caption, so this is a rename and not a change of
    meaning.

    It has to happen HERE rather than at merge time. Left as a raw inline the
    caption text sits in a code span, and a code span is the one thing a
    translator is told not to touch: repairing it later would put the caption
    on the page in the original language. Run after normalize_float_envs, so
    the floats pandoc has no reader for are already plain `figure`/`table`.

    Outside a float \captionof is the only correct spelling and there is no
    caption for it to become, so those are left alone. Returns (text, count).
    """
    out, cursor, count = [], 0, 0
    for span in _FLOAT_SPAN_RE.finditer(tex):
        if span.start() < cursor:
            continue
        body, n = _CAPTIONOF_RE.subn(lambda _m: '\\caption', span.group(0))
        if not n:
            continue
        out.append(tex[cursor:span.start()])
        out.append(body)
        cursor = span.end()
        count += n
    out.append(tex[cursor:])
    return ''.join(out), count


_TABULAR_OPEN_RE = re.compile(
    r'(\\begin\{(?:tabular|tabularx|longtable|array)\*?\}'
    r'(?:\s*\[[^\]]*\])?(?:\s*\{[^{}]*\})?\s*)\{')
_STAR_SPEC_RE = re.compile(r'\*\s*\{\s*(\d+)\s*\}\s*\{([^{}]*)\}')


def expand_tabular_stars(tex):
    """`{l l l*{9}{r}}` -> `{l l l rrrrrrrrr}`. Returns (text, count).

    pandoc understands the repeat form perfectly well, and that is the
    problem: reading the tabular it expands `*{9}{r}` to nine `r`s, and
    writing the raw block back out it emits the ORIGINAL spec followed by the
    expansion -- `{l l l*{9}{r}rrrrrrrrr}`, twenty-one columns where the paper
    has twelve. SINQ's main results table rendered with nine empty columns
    after every row, squeezing the numbers into half the page. Expanding it
    here leaves pandoc nothing to expand, so it cannot double it.
    """
    # Not re.sub: the column spec is a balanced group, so the text to replace
    # runs past the end of the match and only an explicit scan can consume it.
    out, cursor, count = [], 0, 0
    for m in _TABULAR_OPEN_RE.finditer(tex):
        if m.start() < cursor:
            continue
        start = m.end() - 1
        close = _balanced_brace(tex, start)
        if close < 0:
            continue
        spec = tex[start + 1:close - 1]
        if not _STAR_SPEC_RE.search(spec):
            continue
        for _ in range(8):                    # nested repeats are legal
            spec, n = _STAR_SPEC_RE.subn(
                lambda s: s.group(2) * int(s.group(1)), spec)
            if not n:
                break
        out.append(tex[cursor:m.start()])
        out.append(m.group(1) + '{' + spec + '}')
        cursor = close
        count += 1
    out.append(tex[cursor:])
    return ''.join(out), count


_TWOCOLUMN_RE = re.compile(r'\\twocolumn\s*\[')


def strip_title_block(tex):
    """Drop the `\\twocolumn[ ... ]` title block. Returns (text, count).

    ICML-style classes put the title, authors, affiliations and keywords
    inside `\\twocolumn[...]`. pandoc has no reader for it, so the whole block
    -- template comments and all -- came through as raw LaTeX and sat at the
    top of the exported markdown: thirty-seven lines of "It is OKAY to include
    author information" before the paper began. The title and authors are read
    from the PDF metadata, so nothing here is lost.

    A class that puts the abstract inside the block is left alone rather than
    guessed at; losing an abstract would be far worse than keeping the noise.
    """
    out, cursor, count = [], 0, 0
    for m in _TWOCOLUMN_RE.finditer(tex):
        if m.start() < cursor:
            continue
        depth, close = 0, -1
        for i in range(m.end() - 1, len(tex)):
            if tex[i] == '[':
                depth += 1
            elif tex[i] == ']':
                depth -= 1
                if depth == 0:
                    close = i
                    break
        if close < 0:
            continue
        inner = tex[m.end():close]
        if re.search(r'\\begin\{abstract\}|\\section', inner):
            continue
        out.append(tex[cursor:m.start()])
        cursor = close + 1
        count += 1
    out.append(tex[cursor:])
    return ''.join(out), count


_TABULAR_ENV_RE = re.compile(
    r'\\begin\{(tabular\*?|tabularx|longtable|array)\}(.*?)\\end\{\1\}',
    re.DOTALL)
_CMIDRULE_RE = re.compile(
    r'\\cmidrule\s*(?:\[[^\]]*\])?\s*(?:\([lr]{1,2}\))?\s*\{[^{}]*\}'
    r'|\\cline\s*\{[^{}]*\}')
_HEADER_RULE_RE = re.compile(r'\\(?:midrule|hline)\b')


def normalize_table_rules(tex):
    """Keep the \\cmidrule that separates row groups; drop the decorative one.

    pandoc consumes the command name but not its argument, so a surviving
    `\\cmidrule(lr){4-6}` puts "4-6" in a cell. Deleting all of them was the
    old answer and it lost the rule between a table's row groups -- SINQ's
    3-bit and 4-bit blocks ran together with nothing between them.

    Inside a tabular the first `\\midrule` ends the header. Before it a
    `\\cmidrule` only underlines a column group, which CSS now does from the
    `colspan` instead; after it, the rule separates row groups and becomes a
    plain `\\midrule`, which carries no argument to leak.
    """
    count = [0]

    def fix(m):
        body = m.group(2)
        end = _HEADER_RULE_RE.search(body)
        cut = end.end() if end else len(body)
        head = _CMIDRULE_RE.sub('', body[:cut])
        rest, n = _CMIDRULE_RE.subn(r'\\midrule', body[cut:])
        count[0] += n
        # `\addlinespace` STAYS. It marks a booktabs row group, and
        # merge_and_build turns it into the soft row rule. It was stripped
        # here for a while because pandoc, having no reader for it, emitted
        # it as CELL CONTENT and stranded CafeQ's RANDOM and CafeQ (ours)
        # labels on rows of their own. That was the wrong place to fix it:
        # `table` floats now bypass pandoc's table writer entirely, so the
        # command never reaches a reader that would mangle it, and removing
        # it here would throw away the row grouping for nothing.
        return '\\begin{%s}%s%s\\end{%s}' % (m.group(1), head, rest,
                                             m.group(1))

    return _TABULAR_ENV_RE.sub(fix, tex), count[0]


def sanitize_tex(tex):
    """Drop markup that only styles the page, before pandoc reads it."""
    total = 0
    for pattern, repl in _TEX_NOISE:
        tex, n = pattern.subn(repl, tex)
        total += n
    tex, boxes = unwrap_resizebox(tex)
    if boxes:
        print(f"Unwrapped {boxes} \\resizebox/\\scalebox wrapper(s) so pandoc can "
              f"read the enclosing float and keep its caption")
    tex, panels = unwrap_subfloat(tex)
    if panels:
        print(f"Unwrapped {panels} \\subfloat panel(s) so pandoc can see the "
              f"figures inside them")
    tex, floats = normalize_float_envs(tex)
    if floats:
        print(f"Rewrote {floats} float environment(s) pandoc has no reader for "
              f"(SCfigure/wrapfigure/...) so their figures survive")
    tex, tabs = neutralize_tabbing_tabs(tex)
    if tabs:
        print(f"Turned {tabs} redefined tab command(s) back into indentation; "
              f"inside tabbing they are tab stops, not the author's macro")
    tex, front = unwrap_front_matter(tex)
    if front:
        print(f"Unwrapped {front} front-matter command(s); the affiliation "
              f"inside them is dropped with the command and nothing reports it")
    tex, defs = neutralize_tex_defs(tex)
    if defs:
        print(f"Dropped {defs} \\def with delimited parameters; pandoc stops "
              f"the whole conversion at them")
    tex, coltypes = neutralize_newcolumntype(tex)
    if coltypes:
        print(f"Neutralised {coltypes} \\newcolumntype definition(s); pandoc "
              f"stops the whole conversion at their parameters")
    tex, captionofs = normalize_captionof(tex)
    if captionofs:
        print(f"Renamed {captionofs} \\captionof call(s) to \\caption so the "
              f"caption reaches the page and the translator")
    tex, group_rules = normalize_table_rules(tex)
    if group_rules:
        print(f"Kept {group_rules} row-group rule(s) inside tables that would "
              f"otherwise have been deleted with the column rules")
    tex, lists = normalize_list_envs(tex)
    if lists:
        print(f"Rewrote {lists} compact list environment(s) pandoc has no "
              f"reader for (inparaenum/...); their items would be dropped")
    tex, pages = encode_graphic_pages(tex)
    if pages:
        print(f"Carried the requested page through for {pages} multi-page "
              f"figure PDF(s)")
    tex, titles = strip_title_block(tex)
    if titles:
        print(f"Dropped {titles} \\twocolumn[...] title block(s); the title and "
              f"authors come from the metadata")
    tex, turned = unwrap_rotatebox(tex)
    if turned:
        print(f"Unwrapped {turned} rotated label(s) pandoc would have dropped")
    tex, stars = expand_tabular_stars(tex)
    if stars:
        print(f"Expanded the repeat form in {stars} tabular column spec(s), "
              f"which pandoc would otherwise emit twice")
    if total:
        print(f"Stripped {total} presentation-only command(s) before conversion")
    return tex


# pandoc has no reader for `table*`, so with `+raw_tex` a starred float
# passes through VERBATIM and the pipeline converts it itself, keeping every
# `\multicolumn` span. `table` it does read -- and its markdown writer cannot
# express a span in a grid table, so it emits one whose top border declares
# four columns while the rows carry seven. pandoc's own reader then locks
# onto the border and DISCARDS the overflow: twelve of CafeQ's table 1 values
# and six of table 5's left the book that way, while the prose went on citing
# them. Renaming the environment for the duration of the conversion puts the
# unstarred float on the path that already works.
_PROTECTED_TABLE_ENV = 'tbfloatprotected'
_UNSTARRED_TABLE_RE = re.compile(r'\\(begin|end)\{table\}')


def protect_table_floats(tex):
    """Give `table` the same passthrough `table*` already gets. (tex, n)."""
    tex, n = _UNSTARRED_TABLE_RE.subn(
        lambda m: '\\%s{%s}' % (m.group(1), _PROTECTED_TABLE_ENV), tex)
    return tex, n // 2


def restore_table_floats(md):
    """Put the environment name back once pandoc is done with the document."""
    for edge in ('begin', 'end'):
        md = md.replace('\\%s{%s}' % (edge, _PROTECTED_TABLE_ENV),
                        '\\%s{table}' % edge)
    return md


def latex_to_markdown(flat_tex, tex_dir, root, bib_files=None):
    """Convert flattened LaTeX to markdown via pandoc (through pypandoc)."""
    try:
        import pypandoc
    except ImportError:
        print("pypandoc not found. Install with: pip install pypandoc")
        return None

    extra = ['--wrap=none', f'--resource-path={tex_dir}{os.pathsep}{root}']
    if bib_files:
        # Without citeproc every \cite lands in the output as a literal
        # `[@bibtexkey]`, so the reader sees raw keys instead of citations.
        # With the .bib supplied, pandoc renders real author-year citations
        # and builds the reference list itself.
        extra.append('--citeproc')
        for bib in bib_files:
            extra.append(f'--bibliography={bib}')
        print(f"Using citeproc with {len(bib_files)} bibliography file(s)")

    tex, protected = protect_table_floats(sanitize_tex(flat_tex))
    if protected:
        print(f"Protected {protected} `table` float(s) from pandoc's grid-table "
              f"writer, which cannot express a \\multicolumn span")

    try:
        out = restore_table_floats(pypandoc.convert_text(
            tex, _WRITER, format=_READER, extra_args=extra
        ))
        # pandoc emits CRLF here; normalize before any newline-sensitive
        # processing or writing. See normalize_newlines().
        return normalize_newlines(out)
    except Exception as e:
        print(f"LaTeX to markdown conversion failed: {e}")
        return None


# --- post-processing --------------------------------------------------------

_DISPLAY_MATH_RE = re.compile(r'(\$\$.*?\$\$|(?<!\\)\\\[.*?(?<!\\)\\\])', re.S)
_RAW_TABULAR_RE = re.compile(
    r'\\begin\{(tabular|longtable|tabularx|array)\*?\}.*?\\end\{\1\*?\}', re.S)


def repair_display_math(text):
    r"""Repair every display-math and raw-tabular span in the document.

    The per-span repair (row separators eaten by pandoc's LaTeX reader, and
    blank lines that would terminate `$$` math in pandoc's markdown reader)
    lives in math_guard so there is exactly one implementation.
    """
    def fix(m):
        return math_guard.repair_display_math(m.group(0))

    text = _DISPLAY_MATH_RE.sub(fix, text)
    text = _RAW_TABULAR_RE.sub(fix, text)
    return text


def strip_pandoc_divs(text):
    """Drop `:::` fenced-div wrapper lines while keeping their contents."""
    return '\n'.join(
        line for line in text.split('\n')
        if not re.match(r'^\s*:{3,}\s*(\{[^}]*\}|[A-Za-z][\w-]*)?\s*$', line)
    )


def clean_cross_references(text):
    r"""Turn pandoc's `[1](#fig:x){reference-type=...}` into plain text.

    The link target is meaningless in a translated markdown/EPUB context; the
    resolved number pandoc computed is the useful part.
    """
    text = re.sub(r'\{reference-type="[^"]*"\s+reference="[^"]*"\}', '', text)
    # [\[eq:a\]](#eq:a) or [1](#fig:one) -> the visible label
    text = re.sub(r'\[\\?\[?([^\]\n]{1,80}?)\\?\]?\]\(#[^)\s]+\)', r'\1', text)
    return text


# Inline raw LaTeX pandoc could not translate, emitted as `` `\cmd{...}`{=latex} ``.
# Left alone these reach the reader as literal backslash commands, and a stray
# one inside a formula makes pandoc fail to parse the whole span.
_RAW_INLINE_RE = re.compile(r'`(\\[a-zA-Z@]+(?:\s*(?:\{[^{}]*\}|\[[^\[\]]*\]|=[-\d.]+))*)`\{=latex\}')
_LAYOUT_ONLY = re.compile(
    r'^\\(?:looseness|vspace|hspace|noindent|centering|small|footnotesize'
    r'|scriptsize|normalsize|bigskip|medskip|smallskip|clearpage|newpage'
    r'|linebreak|nolinebreak|allowbreak|raggedright|raggedleft|par'
    # \label carries nothing a reader sees, and cross-references resolve from
    # flat.tex rather than from here. Backticking it and letting
    # strip_latex_cruft empty the span left a bare `` glued to the image line,
    # which stopped format_figure_blocks from recognising the image at all.
    r'|label)\b')
_REF_CMD = re.compile(r'^\\(?:ref|eqref|autoref|cref|Cref)\s*\{([^{}]*)\}$')


def clean_raw_inline_latex(text):
    r"""Resolve or drop inline raw-LaTeX escapes left by pandoc.

    - layout-only commands (\looseness, \vspace, ...) are dropped outright
    - \ref{label}/\eqref{label} keep the label so the reader can still tell
      which equation or figure is meant
    - anything else keeps its literal LaTeX but loses the `{=latex}` wrapper,
      so it can no longer break a surrounding math span
    """
    def handle(m):
        cmd = m.group(1).strip()
        if _LAYOUT_ONLY.match(cmd):
            return ''
        ref = _REF_CMD.match(cmd)
        if ref:
            return f'({ref.group(1)})'
        return f'`{cmd}`'

    return _RAW_INLINE_RE.sub(handle, text)


# `\*?` then the argument, NOT one or the other: `(?:\{...\}|\*)?` consumed the
# star and stopped, so `\vspace*{-2.5mm}` lost its head and left `{-2.5mm}`
# standing on the page — twelve times in Neural ODE, above every CNF figure.
# The starred form is a different string, not a special case (K111).
_LATEX_CRUFT_RE = re.compile(
    r'\\(?:label|vspace|hspace|centering|noindent|clearpage|newpage|FloatBarrier'
    r'|acks|small|footnotesize|scriptsize|normalsize|bigskip|medskip|smallskip)'
    r'\*?\s*(?:\{[^{}]*\})?'
)


_EMPTY_CODE_RE = re.compile(r'`[ \t]*`')


def strip_latex_cruft(text):
    """Remove layout-only LaTeX commands pandoc passed through as raw."""
    text = _LATEX_CRUFT_RE.sub('', text)
    # Stripping the command out of a code span leaves the span behind. An
    # empty one renders as nothing but still counts as content, so it can
    # push an image off the end of its own line.
    return _EMPTY_CODE_RE.sub('', text)


_IMG_REF_RE = re.compile(r'!\[([^\]]*)\]\(([^)\s]+)(\s+"[^"]*")?\)')
_EXT_PROBE = ['', '.pdf', '.png', '.jpg', '.jpeg', '.PNG', '.JPG', '.PDF',
              '.eps', '.ps', '.svg', '.gif']


_PAGE_TAG_RE = re.compile(r'--page(\d+)(?=\.[A-Za-z0-9]+$|$)')


def split_page_tag(ref):
    """('figures/x.pdf', 4) from 'figures/x--page4.pdf'; page 1 by default."""
    m = _PAGE_TAG_RE.search(ref)
    if not m:
        return ref, 1
    return ref[:m.start()] + ref[m.end():], int(m.group(1))


def _resolve_figure(ref, search_dirs):
    """Find the real file behind an \\includegraphics reference.

    LaTeX omits the extension (`\\includegraphics{figs/plot}`), which is exactly
    why pandoc's --extract-media silently misses these files.
    """
    ref = ref.replace('\\', '/')
    stem_variants = [ref, os.path.splitext(ref)[0]]
    for base in search_dirs:
        for stem in stem_variants:
            for ext in _EXT_PROBE:
                cand = os.path.normpath(os.path.join(base, stem + ext))
                if os.path.isfile(cand):
                    return cand
    return None


def _rasterize_pdf(src, dest, page_no=1):
    """PDF/EPS figure -> PNG via pymupdf (no ghostscript/ImageMagick needed).

    `page_no` is the 1-based page an \\includegraphics asked for. A figure PDF
    is often a multi-page sheet with one panel per page: CafeQ draws its
    Figure 3 from page 4 and page 1 of the same file, so taking page 1 twice
    showed the same plot twice and one of them was the wrong panel.
    """
    try:
        try:
            import pymupdf
        except ImportError:
            import fitz as pymupdf  # noqa: N813
        doc = pymupdf.open(src)
        if doc.page_count == 0:
            doc.close()
            return False
        index = min(max(page_no, 1), doc.page_count) - 1
        page = doc[index]
        longest = max(page.rect.width, page.rect.height) or 1
        zoom = max(1.0, min(4.0, 1600.0 / longest))
        page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False).save(dest)
        doc.close()
        return True
    except Exception as e:
        print(f"  Warning: could not rasterize {os.path.basename(src)}: {e}")
        return False


def _eps_to_pdf(src, work_dir):
    """Convert EPS via epstopdf (shipped with MiKTeX/TeX Live), if available."""
    tool = shutil.which('epstopdf')
    if not tool:
        return None
    out = os.path.join(work_dir, os.path.basename(os.path.splitext(src)[0]) + '.pdf')
    try:
        result = subprocess.run([tool, f'--outfile={out}', src],
                                capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=120)
        if result.returncode == 0 and os.path.isfile(out):
            return out
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


_RESOLVED_REF_RE = re.compile(r'^images/fig\d{4}_')


def resolve_images(text, tex_dir, root, temp_dir, work_dir):
    """Copy/convert every referenced figure into temp_dir/images and rewrite refs."""
    images_dir = os.path.join(temp_dir, 'images')
    os.makedirs(images_dir, exist_ok=True)
    search_dirs = [tex_dir, root]
    counter = [0]
    unconverted = []
    resolved_cache = {}

    def handle(m):
        alt, ref = m.group(1), m.group(2)
        # "Already ours" is the `figNNNN_` name this function writes, not any
        # path under `images/`. DeeR-VLA keeps its own figures in a folder of
        # that name, so every one of its seven was taken for a finished job:
        # nothing was extracted, the refs kept pointing at `.pdf` files that
        # exist only in `arxiv_src`, and the build stopped.
        if ref.startswith(('http://', 'https://', 'data:')) \
                or _RESOLVED_REF_RE.match(ref):
            return m.group(0)
        if ref in resolved_cache:
            return f'![{alt}]({resolved_cache[ref]})'
        # The page a multi-page figure PDF was asked for rides along in the
        # name, because pandoc drops \includegraphics options long before now.
        bare, page_no = split_page_tag(ref)

        src = _resolve_figure(bare, search_dirs)
        if not src:
            print(f"  Warning: figure not found: {bare}")
            unconverted.append(bare)
            # Keep the caption from being orphaned.
            return f'<!-- figure not found: {bare} -->\n\n> [Figure: {bare}]'

        counter[0] += 1
        stem = re.sub(r'[^A-Za-z0-9_.-]', '_', os.path.splitext(os.path.basename(src))[0])
        if page_no > 1:
            stem += f'_p{page_no}'
        ext = os.path.splitext(src)[1].lower()

        if ext in ('.png', '.jpg', '.jpeg', '.gif'):
            dest_name = f'fig{counter[0]:04d}_{stem}{ext}'
            shutil.copy2(src, os.path.join(images_dir, dest_name))
        elif ext in ('.pdf', '.eps', '.ps'):
            pdf_src = src
            if ext in ('.eps', '.ps'):
                pdf_src = _eps_to_pdf(src, work_dir)
                if not pdf_src:
                    print(f"  Warning: cannot convert {bare} (no epstopdf)")
                    unconverted.append(bare)
                    return f'<!-- figure not converted: {bare} -->\n\n> [Figure: {bare}]'
            dest_name = f'fig{counter[0]:04d}_{stem}.png'
            if not _rasterize_pdf(pdf_src, os.path.join(images_dir, dest_name),
                                  page_no):
                unconverted.append(bare)
                return f'<!-- figure not converted: {bare} -->\n\n> [Figure: {bare}]'
        else:
            print(f"  Warning: unsupported figure type {ext} for {bare}")
            unconverted.append(bare)
            return f'<!-- figure unsupported: {bare} -->\n\n> [Figure: {bare}]'

        rel = f'images/{dest_name}'
        resolved_cache[ref] = rel
        return f'![{alt}]({rel})'

    text = _IMG_REF_RE.sub(handle, text)

    if unconverted:
        with open(os.path.join(temp_dir, 'unconverted_figures.txt'), 'w',
                  encoding='utf-8') as f:
            f.write('\n'.join(unconverted))
        print(f"  {len(unconverted)} figure(s) could not be converted "
              f"(see unconverted_figures.txt)")
    print(f"Resolved {counter[0]} figure(s) into images/")
    return text


def postprocess_markdown(text, tex_dir, root, temp_dir, work_dir,
                         citation_map=None):
    """Repair and normalize pandoc's LaTeX output. Order matters."""
    text = strip_pandoc_divs(text)
    text = clean_cross_references(text)
    text = resolve_citation_keys(text, citation_map)
    text = clean_raw_inline_latex(text)
    text = strip_latex_cruft(text)
    # AFTER cruft removal, not before: deleting a `\label{...}` that sat on its
    # own line inside a formula leaves a blank line behind, and a blank line
    # terminates `$$` math in pandoc's markdown reader. Repairing first would
    # therefore miss every equation that carried a label.
    text = repair_display_math(text)
    text = resolve_images(text, tex_dir, root, temp_dir, work_dir)
    text = re.sub(r'\n{4,}', '\n\n\n', text)
    return text.strip() + '\n'


# =============================================================================
# Entry point
# =============================================================================

def build(input_file, temp_dir, arxiv_id, allow_network=True):
    """Produce input.md + images/ in temp_dir from arXiv LaTeX source.

    Returns (ok, metadata). On any failure returns (False, {}) so convert.py can
    fall back to the calibre backend.
    """
    print(f"=== arXiv backend: {arxiv_id} ===")
    os.makedirs(temp_dir, exist_ok=True)
    work_dir = os.path.join(temp_dir, 'arxiv_src')

    if not allow_network and not os.path.isdir(work_dir):
        print("arXiv backend needs the network but --allow-network was not given.")
        return False, {}

    blob = fetch_eprint(arxiv_id, temp_dir)
    if not blob:
        return False, {}

    shutil.rmtree(work_dir, ignore_errors=True)
    kind = unpack_eprint(blob, work_dir)
    if kind is None:
        print("Could not unpack the arXiv e-print (unknown archive format).")
        return False, {}
    if kind == 'pdf':
        print("arXiv returned a PDF (no LaTeX source available).")
        return False, {}
    print(f"Unpacked arXiv source ({kind})")

    main_tex = find_main_tex(work_dir)
    if not main_tex:
        # Say what was actually required. The old wording named a condition
        # the code did not test, and blamed a missing `\begin{document}` that
        # was present on line 58 of the file it rejected.
        print("No top-level .tex found: no file carries both a document "
              "declaration (\\documentclass or \\documentstyle) and "
              "\\begin{document}.")
        return False, {}
    print(f"Main LaTeX file: {os.path.relpath(main_tex, work_dir)}")

    flat = flatten_tex(main_tex, work_dir)
    if not flat.strip():
        print("Flattened LaTeX source is empty.")
        return False, {}

    # Prefer citeproc over inlining a .bbl: citeproc renders real author-year
    # citations AND the reference list, whereas an inlined thebibliography
    # leaves every in-text \cite as a bare `[@key]`.
    bib_files = find_bib_files(work_dir)
    if not bib_files:
        flat = inline_bibliography(flat, work_dir)

    flat, front_sections = sectionize_front_matter(flat)
    if front_sections:
        print(f"Front matter: {front_sections} environment(s) kept as sections "
              f"(pandoc drops abstract/keywords as metadata otherwise)")

    # The paper's own shorthand, before pandoc reads the source. A `.sty` is
    # never `\input`, so `flatten_tex` does not inline it and pandoc never sees
    # the definition -- the name then survives `+raw_tex` verbatim and prints
    # at the reader. resnet's finished book had `\ie` mid-sentence five times.
    # Done here rather than inside latex_to_markdown so flat.tex, the markdown
    # and everything downstream that re-reads flat.tex agree on one source.
    flat, macro_report = paper_macros.expand_in_source(
        flat, paper_macros.shipped_sources(flat, work_dir))
    if macro_report['expanded']:
        top = sorted(macro_report['expanded'].items(), key=lambda kv: -kv[1])
        print(f"Expanded {sum(macro_report['expanded'].values())} call(s) of "
              f"the paper's own macros: "
              + ', '.join(f'\\{k} x{v}' for k, v in top[:6]))
    # Reported, not swallowed. A refusal leaves the name printing verbatim in
    # the book, and the silent version of that is how it went unnoticed until
    # a reader found `\ie` in the middle of a Korean sentence (K110).
    used_refusals = {k: v for k, v in macro_report['refused'].items()
                     if re.search(r'\\%s(?![A-Za-z])' % re.escape(k), flat)}
    if used_refusals:
        print(f"{len(used_refusals)} macro(s) used in the body could not be "
              f"resolved and will appear verbatim:")
        for name, why in sorted(used_refusals.items())[:8]:
            print(f"  \\{name}: {why}")

    # Written out so a verification step can count equations in the source and
    # compare against the produced markdown.
    with open(os.path.join(temp_dir, 'flat.tex'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(flat)

    macros = extract_math_macros(flat)
    if macros:
        with open(os.path.join(temp_dir, 'math_macros.tex'), 'w', encoding='utf-8', newline='\n') as f:
            f.write('\n'.join(macros) + '\n')
        print(f"Extracted {len(macros)} math macro definition(s)")

    md = latex_to_markdown(flat, os.path.dirname(main_tex), work_dir,
                           bib_files=bib_files)
    if md is None:
        return False, {}

    # Only needed when citeproc could not run (no .bib in the source).
    citation_map = {} if bib_files else build_citation_map(work_dir)
    md = postprocess_markdown(md, os.path.dirname(main_tex), work_dir,
                              temp_dir, work_dir, citation_map=citation_map)

    empty_reason = no_latex_body(flat, md)
    if empty_reason:
        print(f"arXiv source carries no LaTeX body: {empty_reason}")
        return False, {}

    input_md = os.path.join(temp_dir, 'input.md')
    with open(input_md, 'w', encoding='utf-8', newline='\n') as f:
        f.write(md)
    print(f"Wrote input.md ({len(md):,} characters)")

    metadata = extract_pdf_metadata(input_file)
    # The LaTeX \title{} beats everything: arXiv PDFs routinely ship an empty
    # /Title, and the first-heading fallback then names every paper after its
    # own Introduction.
    latex_title = extract_latex_title(flat)
    if latex_title:
        metadata['title'] = latex_title
    # The PDF's /Author is empty on most arXiv submissions, and the title page
    # then reads "Unknown Author" about a paper whose flat.tex names everybody.
    # Only when the metadata has nothing, and only when the block parses
    # cleanly — a wrong name on a title page is worse than none (K139).
    if not metadata.get('creator'):
        latex_authors = extract_latex_authors(flat)
        if latex_authors:
            metadata['creator'] = latex_authors
            print(f"Authors: read {latex_authors.count(';') + 1} name(s) from "
                  f"the LaTeX; the PDF metadata carried none")
    if 'title' not in metadata:
        title_match = re.search(r'^#\s+(.+)$', md, re.M)
        if title_match:
            metadata['title'] = title_match.group(1).strip()
    metadata.setdefault('arxiv_id', arxiv_id)
    return True, metadata

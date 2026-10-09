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

import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request

import latex_rows
import math_guard
import paper_macros
from build_common import _balanced_group as _balanced_brace, _in_latex_comment

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
    """Contents of the {...} group opening at brace_at, or None. Escaped
    braces are characters (`build_common._balanced_group`)."""
    end = _balanced_brace(text, brace_at)
    return text[brace_at + 1:end - 1] if end > 0 else None


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
    had_environment = count > 0
    tex = _KEYWORDS_ENV_RE.sub(to_section('Index Terms'), tex)
    if not had_environment:
        tex, moved = _abstract_command_to_section(tex)
        count += moved
    return tex, count


_ABSTRACT_CMD_RE = re.compile(r'\\abstract\s*\{')
# What may stand in front of `\abstract{` when the line DEFINES the command
# rather than uses it: `\newcommand\abstract{...}` must stay where it is.
_DEFINES_RE = re.compile(r'\\(?:(?:re)?newcommand|providecommand|def|let)\*?\s*\{?\s*$')
_MAKETITLE_RE = re.compile(r'\\maketitle\b')


def _abstract_command_to_section(tex):
    r"""Move an abstract given as `\abstract{...}` into the body as a section.

    Some classes take the abstract as a command in the preamble and print it
    from `\maketitle`: muxlab.cls defines `\renewcommand{\abstract}[1]{\def
    \abstracttext{#1}}`. pandoc reads no class file, so the text never reached
    the body, and the finished book of 2609.11801, shipped as the repository's
    demo, opened at the authors and went straight to Figure 1. The section
    goes right after `\maketitle`, where the class would have printed it, or
    at the start of the body when there is none. Returns (tex, moved).
    """
    for m in _ABSTRACT_CMD_RE.finditer(tex):
        line_start = tex.rfind('\n', 0, m.start()) + 1
        before = tex[line_start:m.start()]
        if re.search(r'(?<!\\)%', before) or _DEFINES_RE.search(before):
            continue
        brace = m.end() - 1
        body = _balanced_arg(tex, brace)
        if body is None or not body.strip():
            continue
        end = brace + len(body) + 2
        section = '\\section*{Abstract}\n%s\n' % body.strip()
        begin = tex.find('\\begin{document}')
        if begin == -1 or m.start() > begin:
            return tex[:m.start()] + section + tex[end:], 1
        tex = tex[:m.start()] + tex[end:]
        begin = tex.find('\\begin{document}')
        title = _MAKETITLE_RE.search(tex, begin)
        at = title.end() if title else begin + len('\\begin{document}')
        return tex[:at] + '\n' + section + tex[at:], 1
    return tex, 0


def extract_latex_title(tex):
    """The paper's \\title{...}, cleaned. '' when there is none."""
    m = re.search(r'\\title\s*(\[[^\]]*\])?\s*\{', tex or '')
    if not m:
        return ''
    brace = tex.index('{', m.end() - 1)
    return clean_latex_title(_balanced_arg(tex, brace) or '')


_AUTHOR_SEP_RE = re.compile(
    r'\\(?:and|AND|And)\b|\\quad\b|\\qquad\b|\\hspace\*?\s*\{[^{}]*\}')
# Names within one line of an entry. Split per LINE, not over the whole
# block: a comma in the affiliation line below the names made
# "Technische Universität Darmstadt" an author, and Sentence-BERT's whole
# list was refused for it. The word `and` joins two names as often as
# `\and` does: "Nils Reimers and Iryna Gurevych".
# Spacing between names is a separator too: DeeR-VLA writes `~~~`, AlphaQ
# `\enspace`, 2609.11801 `,\;\;`. Unsplit, four names read as one person of
# eight words and the whole list was refused.
_AUTHOR_NAME_SEP_RE = re.compile(
    r',|\s+and\s+|~{2,}|\\(?:enspace|enskip)\b|\\;')
# Spacing and marks that carry no name, gone before anything is split: the
# comma in ViT's `$^{*,\dagger}$` cut a mark in half, and `\vspace{1mm}`
# left "1mm" behind as a name with a digit in it. A colour or a font switch
# names nothing either: `\color{muxfg}` left "muxfg" in front of a name.
_AUTHOR_SPACING_RE = re.compile(
    r'\$[^$]*\$|\\vspace\*?\s*\{[^{}]*\}|\\centerline\b'
    r'|\\color\s*(?:\[[^\]]*\])?\s*\{[^{}]*\}'
    r'|\\(?:sffamily|rmfamily|ttfamily|bfseries|mdseries|itshape|upshape'
    r'|normalsize|small|large|Large)\b')
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
# Words that end a line of names further down the block. Not refused on the
# first line, where "The Planck team" is the author the paper names.
_NOT_A_NAME_LINE_RE = re.compile(r'\b(?:Team|Group|Labs|AI)\b')
# Lower-case words a family name may start with.
_NAME_PARTICLES = {'van', 'von', 'der', 'den', 'de', 'del', 'della', 'da',
                   'di', 'du', 'la', 'le', 'bin', 'al', 'el', 'dos', 'das',
                   'ter', 'zu'}


def _bare_author(part):
    """One name fragment with its markup and stray marks gone."""
    part = re.sub('[^]*', ' ', part)    # `_encode_marks`
    return ' '.join(_AUTHOR_MARKUP_RE.sub(' ', part).split()).strip(' .,;*†‡§:')


def _reads_as_a_name(part):
    """Does this fragment, alone, read as a person's name?

    Only used to decide whether a LATER line of an author block is still
    names. Strict on purpose: a line that fails ends the list there.
    """
    bare = _bare_author(part)
    words = bare.split()
    if not 2 <= len(words) <= 6 or _NOT_A_PERSON_RE.search(bare) \
            or _NOT_A_NAME_LINE_RE.search(bare):
        return False
    if re.search(r'[\d@\\:()]', bare):
        return False
    return all(w[0].isupper() or w.lower() in _NAME_PARTICLES for w in words)
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


# Marks are kept through the parse, so a name can be matched to the
# affiliation that carries the same mark. Encoded in private-use characters,
# commas included, so no separator and no markup pattern below touches them.
_MARK_OPEN, _MARK_CLOSE, _MARK_COMMA = '\ue010', '\ue011', '\ue012'
_MARK_IN_TEXT_RE = re.compile('%s([^%s]*)%s' % (_MARK_OPEN, _MARK_CLOSE,
                                                _MARK_CLOSE))
_MARK_SYMBOLS = (('ddagger', '‡'), ('ddag', '‡'), ('dagger', '†'),
                 ('dag', '†'), ('circ', '∘'), ('ast', '*'), ('star', '⋆'),
                 ('S', '§'), ('P', '¶'), ('sharp', '♯'), ('natural', '♮'),
                 ('flat', '♭'), ('diamondsuit', '♢'), ('diamond', '◇'),
                 ('heartsuit', '♡'), ('spadesuit', '♠'), ('clubsuit', '♣'),
                 ('Letter', '✉'))
_MARK_CMD_RE = re.compile(
    r'\\textsuperscript\s*\{((?:[^{}]|\{[^{}]*\})*)\}'
    r'|\\inst\s*\{([^{}]*)\}'
    r'|\$\s*((?:[^$\\]|\\.)*?)\s*\$')
_IS_MARK_RE = re.compile(r'[0-9a-z*†‡∘⋆§¶♯♮♭♢◇♡♠♣✉,]+')


def _mark_text(raw):
    r"""`\normalfont 1,2,3` -> `1,2,3`; `^{*,\dagger}` -> `*,†`."""
    text = raw
    for cmd, char in _MARK_SYMBOLS:
        text = re.sub(r'\\%s(?![A-Za-z])' % cmd, char, text)
    # `$` too: 2609.11801 marks its first author `\textsuperscript{1,$*$}`.
    text = re.sub(r'\\[A-Za-z]+|\\[,;:! ]|[{}^\s~$]', '', text)
    return text


def _encode_marks(block):
    """Each author or affiliation mark in `block` as a placeholder."""
    def swap(m):
        raw = m.group(1) if m.group(1) is not None else (
            m.group(2) if m.group(2) is not None else m.group(3))
        mark = _mark_text(raw)
        if not _IS_MARK_RE.fullmatch(mark or ''):
            return m.group(0)
        return _MARK_OPEN + mark.replace(',', _MARK_COMMA) + _MARK_CLOSE
    return _MARK_CMD_RE.sub(swap, block)


def _split_marks(text):
    """(text without marks, [mark, ...])."""
    marks = [m.replace(_MARK_COMMA, ',').strip(',')
             for m in _MARK_IN_TEXT_RE.findall(text)]
    marks = [m for m in marks if m]
    return _MARK_IN_TEXT_RE.sub(' ', text), marks


# TeX's spellings of letters a name needs: `{\L}ukasz`, `\.{I}smail`,
# `Schr\"odinger`. Left as they were, the backslash refused Attention's whole
# author list over Łukasz Kaiser.
_TEX_LETTERS = {'L': 'Ł', 'l': 'ł', 'O': 'Ø', 'o': 'ø', 'ss': 'ß',
                'AA': 'Å', 'aa': 'å', 'AE': 'Æ', 'ae': 'æ', 'OE': 'Œ',
                'oe': 'œ', 'i': 'ı', 'j': 'ȷ'}
_TEX_ACCENTS = {"'": '\u0301', '`': '\u0300', '^': '\u0302', '"': '\u0308',
                '~': '\u0303', '=': '\u0304', '.': '\u0307', 'u': '\u0306',
                'v': '\u030c', 'H': '\u030b', 'c': '\u0327', 'k': '\u0328',
                'r': '\u030a'}
_TEX_LETTER_RE = re.compile(
    r'\{\\(%s)\}|\\(%s)(?:\{\}|(?![A-Za-z]))'
    % (('|'.join(sorted(_TEX_LETTERS, key=len, reverse=True)),) * 2))
# Each spelling with its own braces, never an optional brace on either side:
# `\{?` took the brace of the `\textbf{` in front, and `\textbf{\.{I}smail}`
# came out `\textbfİsmail}`.
_TEX_ACCENT_RE = re.compile(
    r'\{\\([\'`^"~=.])\s*([A-Za-zıȷ])\}'            # {\'e}
    r'|\\([\'`^"~=.])\s*\{([A-Za-zıȷ])\}'           # \'{e}
    r'|\\([\'`^"~=.])([A-Za-zıȷ])'                  # \'e
    r'|\{\\([uvHckr])\s+([A-Za-zıȷ])\}'             # {\v s}
    r'|\\([uvHckr])\s*\{([A-Za-zıȷ])\}'             # \v{s}
    r'|\\([uvHckr])\s([A-Za-zıȷ])')                 # \v s


def tex_letters_to_unicode(text):
    r"""`{\L}ukasz \.{I}lkan Schr\"odinger` -> `Łukasz İlkan Schrödinger`."""
    import unicodedata
    text = _TEX_LETTER_RE.sub(
        lambda m: _TEX_LETTERS[m.group(1) or m.group(2)], text)

    def accent(m):
        groups = m.groups()
        at = next(i for i in range(0, len(groups), 2) if groups[i])
        mark, base = groups[at], groups[at + 1]
        base = {'ı': 'i', 'ȷ': 'j'}.get(base, base)
        return unicodedata.normalize('NFC', base + _TEX_ACCENTS[mark])
    return _TEX_ACCENT_RE.sub(accent, text)


# An affiliation line that is something else: an e-mail, a note on equal
# contribution, a link.
_NOT_AN_AFFILIATION_RE = re.compile(
    r'(?i)equal(?:ly)?\s+(?:contribut|advis)|corresponding|work\s+(?:done|'
    r'performed)|^\s*$')
_EMAIL_GROUP_RE = re.compile(
    r'\\(?:texttt|url|href|textsf|tt)\s*\{(?:[^{}]|\{[^{}]*\})*@'
    r'(?:[^{}]|\{[^{}]*\})*\}(?:\s*\{(?:[^{}]|\{[^{}]*\})*\})?'
    r'|\{\\tt\b(?:[^{}]|\{[^{}]*\})*@(?:[^{}]|\{[^{}]*\})*\}'
    r'|\\?\{?[\w.,~\s\\-]*\\?\}?@[\w.-]+')
_AFFIL_NOISE_RE = re.compile(
    r'\\color\s*\{[^{}]*\}|\\(?:vspace|hspace)\*?\s*\{[^{}]*\}'
    r'|^\s*\[[^\]]*\]|\\[A-Za-z]+\*?|[{}$~]')


def _tex_group(tex, open_at):
    r"""The body of the `{...}` at `open_at`, read as TeX reads it, or None.

    Comments do not count and neither does an escaped brace. A brace count
    that took both ran spectre's `\author{}` on through `\title{}` and the
    whole abstract: a commented-out line in it holds `\{\href{...}`.
    `tex` must be comment-stripped (`paper_macros.strip_comments`).
    """
    close = paper_macros._group_end(tex, open_at)
    return tex[open_at + 1:close - 1] if close > 0 else None


def _renewed_body(tex, name):
    r"""The body of `\renewcommand{\name}{...}`, or None."""
    m = re.search(r'\\(?:re)?newcommand\s*\{?\\%s\}?\s*\{' % name, tex)
    return _tex_group(tex, m.end() - 1) if m else None


def _title_entries(tex):
    r"""[(name parts, affiliation lines)] per author entry, or None.

    The one parse both `extract_latex_authors` and `read_title_block` read,
    so the names on the title page and in the metadata cannot disagree.
    Marks are placeholders here (`_encode_marks`).

    Two places a paper writes its author block: `\author{}` and a class's own
    list macros (muxlab's `\authorlist` and `\affiliationlist`, which
    2609.11801 fills with `\renewcommand`).
    """
    tex = paper_macros.strip_comments(tex)
    listed = _renewed_body(tex, 'authorlist')
    if listed is not None:
        block, extra = listed, _renewed_body(tex, 'affiliationlist') or ''
    else:
        m = re.search(r'\\author\s*(?:\[[^\]]*\])?\s*\{', tex)
        if not m:
            return None
        block = _tex_group(tex, tex.index('{', m.end() - 1)) or ''
        extra = ''
    entries = []
    for part, is_affiliations in ((block, False), (extra, True)):
        part = re.sub(r'(?m)^\s*%.*$', '', part)          # a commented-out line
        part = re.sub(r'(?m)(?<!\\)%.*$', '', part)       # a line-end comment
        part = tex_letters_to_unicode(_encode_marks(part))
        part = _AUTHOR_NOTE_RE.sub(' ', part)
        part = _AUTHOR_SPACING_RE.sub(' ', part)
        if is_affiliations:
            entries.append(([], _AUTHOR_LINE_RE.split(part)))
            continue
        for entry in _AUTHOR_SEP_RE.split(part):
            names, affiliations = [], []
            # The names come first in the entry; then where they work and
            # how to reach them. The first line is always names (and is
            # refused below if it is not). A later line is names only if
            # every part of it reads as one: ViT sets twelve names over
            # three centred lines and CafeQ seven over two, and stopping
            # after the first line printed four of each -- a list missing
            # someone, which is as wrong as a false name. The first line
            # that is anything else -- an affiliation, an address, a note
            # on equal contribution -- ends the names.
            lines = _AUTHOR_LINE_RE.split(entry)
            for index, line in enumerate(lines):
                line = re.sub(r'^\s*\[[^\]]*\]', '', line)   # `\\[2pt]`
                # A name carries its mark after it, an affiliation before it.
                # VLA-Adapter spaces its affiliations with `\quad` as it does
                # its names, so `$^{5}$State Key Laboratory` arrived as an
                # entry of its own and refused the whole list as a name.
                if not index and _LEADING_MARK_RE.match(line):
                    affiliations = lines
                    break
                parts = _AUTHOR_NAME_SEP_RE.split(line)
                if index and not all(_reads_as_a_name(p) for p in parts
                                     if _bare_author(p)):
                    affiliations = lines[index:]
                    break
                names.extend(parts)
            entries.append((names, affiliations))
    return entries


_LEADING_MARK_RE = re.compile(r'[\s{}]*(?:\\[A-Za-z]+\*?\s*)*')


def _clean_name(part):
    """(name, marks) for one name fragment."""
    text, marks = _split_marks(part)
    name = ' '.join(_AUTHOR_MARKUP_RE.sub(' ', text).split())
    return name.strip(' .,;*†‡§'), marks


def _checked_names(parts):
    r"""[(name, marks)], or None when any fragment is not a name.

    It looked like a name and did not come out as one -- a digit or a
    backslash means markup survived the strip. Refuse the WHOLE list:
    `Sherjil Ozair` carries a dagger, and dropping just that one printed
    seven of GAN's eight authors. A list missing someone is as wrong as one
    naming the wrong person, and it is harder to notice.
    """
    out, seen = [], set()
    for part in parts:
        name, marks = _clean_name(part)
        if _NOT_A_PERSON_RE.search(name):
            # An institution where a person should be. Refusing costs the
            # title page nothing it does not already lack; printing it would
            # put a false name on a book (K121's lesson in another costume).
            return None
        # Nothing but punctuation or spacing: not a name, and not a failure.
        if not name or not re.search(r'[A-Za-zÀ-ɏ]', name):
            continue
        if re.search(r'\d|\\', name) or len(name) > 60 \
                or len(name.split()) > 6:
            return None
        if name not in seen:
            seen.add(name)
            out.append((name, marks))
    return out


def extract_latex_authors(tex):
    r"""The paper's author names, from `\author{}` or `\icmlauthor{}`. '' if none.

    The title page falls back to "Unknown Author" whenever the source PDF has
    no author metadata, which arXiv's GenPDF routinely omits — eight finished
    books say it, and every one of them has the names sitting in its own
    flat.tex. Marks and affiliations come off here; `read_title_block` keeps
    them.
    """
    tex = tex or ''
    icml = re.findall(r'\\icmlauthor\s*\{((?:[^{}]|\{[^{}]*\})*)\}', tex)
    if icml:
        parts = icml
    else:
        entries = _title_entries(tex)
        if entries is None:
            return ''
        parts = [p for names, _aff in entries for p in names]
    names = _checked_names(parts)
    return '; '.join(name for name, _marks in names) if names else ''


# What follows the names and is not an affiliation: a project page, a
# dedication (higgs_atlas), IEEE's "X and Y are with Z" note (TinyVLA).
_NOT_AN_AFFILIATION_TEXT_RE = re.compile(
    r'(?i)^(?:https?://|www\.)|^\S+\.(?:com|org|net|edu|io|de)\S*$'
    r'|\b(?:is|are)\s+with\b|\bdedicated\b')


def _note_of(line):
    """A note line (`$^*$equal technical contribution`) as text, marks inline."""
    text = _MARK_IN_TEXT_RE.sub(
        lambda m: m.group(1).replace(_MARK_COMMA, ','), line)
    return ' '.join(_AFFIL_NOISE_RE.sub(' ', text).split()).strip(' ,;:')


def _affiliations_of(lines, notes=None):
    """[(marks, text)] from the lines after an entry's names.

    A line that is a note on the authors (equal contribution, corresponding
    author) goes to `notes` instead, when given: ViT marks authors `*` and
    a dagger and says what they mean on a line of its own.

    A marked affiliation runs until the next mark, over several lines if the
    paper wraps it (2609.11716's first). Unmarked lines are one affiliation
    together: VAE's `Machine Learning Group \\ Universiteit van Amsterdam`
    is one place, not two.
    """
    out = []
    for line in lines:
        line = _EMAIL_GROUP_RE.sub(' ', line)
        if _NOT_AN_AFFILIATION_RE.search(_MARK_IN_TEXT_RE.sub('', line)):
            note = _note_of(line)
            if notes is not None and note and note not in notes:
                notes.append(note)
            continue
        # A line can carry several, each opened by its mark:
        # `^1 Department of Automation ~~~ ^2 ByteDance`.
        pieces = re.split('(%s[^%s]*%s)' % (_MARK_OPEN, _MARK_CLOSE,
                                             _MARK_CLOSE), line)
        mark = None
        for piece in pieces:
            if piece.startswith(_MARK_OPEN):
                mark = piece[1:-1].replace(_MARK_COMMA, ',').strip(',')
                continue
            text = ' '.join(_AFFIL_NOISE_RE.sub(' ', piece).split())
            text = text.strip(' ,;:·')
            if not re.search(r'[A-Za-zÀ-ɏ]{2}', text) \
                    or _NOT_AN_AFFILIATION_TEXT_RE.search(text) \
                    or len(text.split()) > 20:
                continue
            if mark is None and out:
                # No mark of its own: it continues the one before it.
                out[-1] = (out[-1][0], out[-1][1] + ', ' + text)
            else:
                out.append((mark or '', text))
            mark = None
    return out


def read_title_block(tex):
    r"""{'authors': [(name, marks)], 'affiliations': [(mark, text)],
    'notes': [text]}, or None.

    The affiliations reached no page: pandoc reads `\author{}` as metadata
    and drops it, and the title page was built from the names alone. Seven
    of the corpus papers lost every affiliation that way, among them
    2609.11801, whose seven institutions an agent then typed in by hand.

    Marks are the paper's own (`\textsuperscript{1}`, `$^{*,\dagger}$`,
    `\inst{1}`). A paper that writes each author's affiliation under their
    name with no marks (Attention, VAE) gets numbers, one per distinct
    affiliation, and none at all when every author shares one. None when the
    names cannot be read, as `extract_latex_authors` refuses them.
    """
    entries = _title_entries(tex or '')
    if not entries:
        return None
    authors, affiliations, owners, notes = [], [], [], []
    for names, lines in entries:
        checked = _checked_names(names)
        if checked is None:
            return None
        found = _affiliations_of(lines, notes)
        if checked:
            authors.extend(checked)
            owners.append((len(authors) - len(checked), len(authors), found))
        elif found and owners:
            # An entry split by spacing before its affiliation, as Attention
            # writes `Aidan N. Gomez\hspace{1.7mm}\thanks{..}\\ University of
            # Toronto`: the affiliation is the previous name's.
            start, stop, before = owners[-1]
            owners[-1] = (start, stop, before + found)
        else:
            owners.append((len(authors), len(authors), found))
        affiliations.extend(found)
    if not authors:
        return None
    marked = any(mark for mark, _text in affiliations)
    distinct = []
    for _mark, text in affiliations:
        if text not in distinct:
            distinct.append(text)
    if marked or len(distinct) <= 1:
        unique = []
        for item in affiliations:
            if item not in unique:
                unique.append(item)
        return {'authors': authors, 'affiliations': unique, 'notes': notes}
    # Unmarked and not shared: number each distinct affiliation, and give
    # each author the numbers of the affiliations written under them.
    numbered = [(str(i), text) for i, text in enumerate(distinct, 1)]
    number = {text: str(i) for i, text in enumerate(distinct, 1)}
    authors = [list(a) for a in authors]
    for start, stop, found in owners:
        marks = []
        for _m, text in found:
            if number[text] not in marks:
                marks.append(number[text])
        for author in authors[start:stop]:
            author[1] = marks + author[1]
    return {'authors': [tuple(a) for a in authors],
            'affiliations': numbered, 'notes': notes}


def read_pdf_text(pdf_path):
    r"""The text the PRINTED paper shows, or '' when it cannot be read.

    Used to settle a question the source cannot: a macro defined once in each
    branch of a conditional. spectre's `\dtcolornote` prints an author's margin
    note in one branch and nothing in the other, and dtrt.sty's default is the
    first -- but the paper is built `camera` and its PDF contains
    "NeedReference" zero times. The artefact decides (K138).
    """
    try:
        try:
            import pymupdf
        except ImportError:
            import fitz as pymupdf  # noqa: N813
        doc = pymupdf.open(pdf_path)
        try:
            return '\n'.join(page.get_text('text') for page in doc)
        finally:
            doc.close()
    except Exception:
        return ''


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


def pick_bbl(root, main_tex=None):
    r"""The `.bbl` LaTeX reads for this paper, or None.

    LaTeX reads `\jobname.bbl`: the main file's name with `.bbl`. The first
    `.bbl` an os.walk met was taken instead; bert ships `lumiere.bbl` beside
    `main.bbl` and got `lumiere.bbl` (identical content, by luck). Several
    with none named after the main file: sorted first, with a warning.
    """
    found = []
    for dirpath, _dirs, files in os.walk(root):
        found.extend(os.path.join(dirpath, fn) for fn in files
                     if fn.lower().endswith('.bbl'))
    if not found:
        return None
    if main_tex:
        stem = os.path.splitext(os.path.basename(main_tex))[0].lower()
        named = sorted(p for p in found
                       if os.path.splitext(os.path.basename(p))[0].lower() == stem)
        if named:
            return named[0]
    found.sort()
    if len(found) > 1:
        print("Warning: %d .bbl files and none named after %s; using %s"
              % (len(found), os.path.basename(main_tex or 'the main file'),
                 os.path.basename(found[0])))
    return found[0]


def inline_bibliography(tex, root, main_tex=None):
    r"""Replace \bibliography{...} with the compiled .bbl, when one shipped.

    pandoc reads a thebibliography environment into a real list, so this is what
    keeps the reference section from vanishing.
    """
    bbl = pick_bbl(root, main_tex)
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
# `\citet{a, b, c}`: pandoc writes the first key bare and the rest bracketed,
# `@a [@b; @c]`. It is one author-in-text list, which natbib prints
# "A (2024); B (2024b)". Resolved as two separate citations and then glued,
# CafeQ read "(Adepu et al. 2024; Ashkboos et al. 2024b)", ViT read
# "Kolesnikov et al. (2020; Djolonga et al. 2020)" and Sentence-BERT nested
# one citation inside another.
_CITET_LIST_RE = re.compile(
    r'(?<![\[\w@\\.])@([A-Za-z][A-Za-z0-9_:.\-]{1,120}[A-Za-z0-9])'
    r'[ ]\[((?:@[^\]\s;]+;[ ]*)*@[^\]\s;]+)\]')


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
    # `alpha` marks a fourth author with a raised plus: `VLL$^+$10`. The
    # label prints wherever it is cited and on the list, and its dollars
    # reached VAE's page as TeX.
    label = re.sub(r'\$\^\{?\+\}?\$', '+', label)
    label = label.replace('$', '')
    label = re.sub(r'\\[a-zA-Z]+\s*', '', label)
    label = re.sub(r'[{}]', '', label)
    return re.sub(r'\s+', ' ', label).strip()


def build_citation_map(root, main_tex=None):
    """Map bibtex key -> human citation label, from the `.bbl` that was
    inlined (`pick_bbl`), not every `.bbl` in the tree."""
    mapping = {}
    bbl = pick_bbl(root, main_tex)
    if not bbl:
        return mapping
    try:
        with open(bbl, encoding='utf-8', errors='replace') as f:
            text = f.read()
    except OSError:
        return mapping
    for m in _BIBITEM_RE.finditer(text):
        label, key, bare_key = m.group(1), m.group(2), m.group(3)
        if bare_key:
            continue  # no label to show; leave those alone
        cleaned = _clean_bib_label(label)
        if key and cleaned:
            mapping[key] = cleaned
    return mapping


def cite_group(labels):
    """One citation group as the paper prints it.

    Author-year labels go in parentheses, `(Kingma et al. 2014; ...)`. An
    alphabetic label, `BJP12`, goes in square brackets, `[BJP12, DHS10]`,
    as the `alpha` style prints it, and as the reference list now labels its
    entries; in parentheses VAE's citations matched nothing in its list.
    """
    if labels and not any(re.search(r'\s', label) for label in labels):
        return '[' + ', '.join(labels) + ']'
    return '(' + '; '.join(labels) + ')'


def resolve_citation_keys(text, citation_map):
    r"""Turn `[@key1; @key2]` into `(Author Year; Author Year)`.

    Without this, a paper whose arXiv source ships only a compiled `.bbl` (no
    `.bib`, so citeproc cannot run) leaves raw bibtex keys in the reader's face.
    Keys with no label found are left untouched rather than silently deleted.
    """
    if not citation_map:
        return text

    resolved = [0]
    resolved_bare = [0]

    def in_text(label, enclosed):
        # Author-in-text form: the name carries the sentence, the year is
        # parenthesised -- `Adepu et al. (2024)`, not `(Adepu et al. 2024)`.
        # But inside a parenthesis the sentence is not carrying anything, and
        # `(예: Dettmers & Zettlemoyer (2023))` nests brackets for no reason,
        # so there the plain label is what a copy editor would leave.
        if enclosed:
            return label
        year = re.match(r'^(.*?)[\s,]+((?:19|20)\d{2}[a-z]?)$', label)
        return f'{year.group(1)} ({year.group(2)})' if year else label

    def handle_list(m):
        keys = [m.group(1)] + [k.strip().lstrip('@')
                               for k in m.group(2).split(';')]
        labels = [citation_map.get(k) for k in keys]
        if not all(labels):
            return m.group(0)
        resolved_bare[0] += 1
        enclosed = _inside_parens(text, m.start())
        return '; '.join(in_text(label, enclosed) for label in labels)

    text = _CITET_LIST_RE.sub(handle_list, text)

    def handle(m):
        keys = [k.strip().lstrip('@') for k in m.group(1).split(';')]
        labels = []
        for key in keys:
            label = citation_map.get(key)
            if not label:
                return m.group(0)  # unknown key: leave the whole group as-is
            labels.append(label)
        resolved[0] += 1
        return cite_group(labels)

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
        return in_text(label, _inside_parens(out_text[0], m.start()))

    out_text = [out]
    out = _BARE_CITE_RE.sub(handle_bare, out)

    if resolved[0] or resolved_bare[0]:
        print(f"Resolved {resolved[0]} citation group(s) and "
              f"{resolved_bare[0]} in-text citation(s) from .bbl labels")
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


_BIB_ENTRY_RE = re.compile(r'(?m)^[ \t]*@[A-Za-z]+[ \t]*\{')


def _closes_at(text, start, escaped):
    r"""Where the brace opened at `start` closes, or -1.

    `escaped=True` reads a backslash as escaping the next character, which is
    what pandoc does. `escaped=False` counts every brace, which is what BibTeX
    does. Two readings of one file are the whole of this problem.
    """
    depth, i = 0, start
    while i < len(text):
        ch = text[i]
        if escaped and ch == '\\':
            i += 2
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def repair_bib_braces(path):
    r"""Make one `.bib` readable by pandoc without changing what it says.

    BibTeX does not treat a backslash as escaping a brace: it counts `{` and
    `}` and nothing else. pandoc's reader follows the LaTeX convention, where
    `\}` is a literal brace. A file can therefore be valid to BibTeX, the
    program a `.bib` is written for, and unreadable to pandoc.

    One paper ends a field with an escaped brace where the closer belonged.
    BibTeX closes the field there and is content, which is why the paper
    builds on arXiv. pandoc reads that brace as text, never closes the entry,
    meets the next `@` and exits 25 -- taking the whole conversion with it,
    for a paper whose body cites 22 keys that live only in that file
    (KNOWLEDGE.md K145).

    Repairing it by hand does not survive, because the work directory is
    re-unpacked before every run. So repair it here, after unpacking and
    before pandoc reads it.

    Only an entry pandoc cannot close is touched, and only by dropping a
    backslash BibTeX was already ignoring, so the file still says the same
    thing to the program it was written for. An entry that will not close even
    then is left exactly as it was: a file this cannot fix is one to report,
    not to guess at.

    Returns the number of entries repaired.
    """
    try:
        with open(path, encoding='utf-8', errors='replace') as fh:
            text = fh.read()
    except (IOError, OSError):
        return 0

    starts = [m.end() - 1 for m in _BIB_ENTRY_RE.finditer(text)]
    if not starts:
        return 0

    repaired, pieces, cursor = 0, [], 0
    for n, start in enumerate(starts):
        nxt = starts[n + 1] if n + 1 < len(starts) else len(text)
        closes = _closes_at(text, start, escaped=True)
        if 0 <= closes < nxt:
            continue                      # pandoc closes it: nothing to do
        bibtex_closes = _closes_at(text, start, escaped=False)
        if not 0 <= bibtex_closes < nxt:
            continue                      # BibTeX cannot close it either
        entry = text[start:nxt]
        fixed = entry.replace('\\}', '}').replace('\\{', '{')
        if _closes_at(fixed, 0, escaped=True) < 0:
            continue                      # still broken; leave it alone
        pieces.append(text[cursor:start])
        pieces.append(fixed)
        cursor = nxt
        repaired += 1

    if not repaired:
        return 0
    pieces.append(text[cursor:])
    try:
        with open(path, 'w', encoding='utf-8', newline='') as fh:
            fh.write(''.join(pieces))
    except (IOError, OSError):
        return 0
    return repaired


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
    # wrapper carries nothing that pandoc needs, so removing the two lines
    # costs nothing and recovers everything inside.
    #
    # The SINGULAR `appendix` was missing from this list and is the spelling
    # 2609.05354 uses, with no `\appendix` command anywhere. Its whole
    # appendix reached the markdown as one raw block and the HTML writer
    # dropped it, reported as a single finding exactly as the paragraph
    # above predicts.
    #
    # Stripping it does NOT cost the numbering, and that is worth stating
    # because for this paper the wrapper IS the switch. `flat.tex` is
    # written from the text BEFORE `sanitize_tex` runs, and every reader
    # that letters an appendix -- `build_label_index`, `flat_equation_numbers`,
    # `float_units` -- reads `flat.tex`. Only the markdown path sees this.
    (re.compile(r'(?m)^[ \t]*\\(?:begin|end)'
                r'\{(?:subappendices|appendices|appendix)\}'
                r'[ \t]*$\n?'), ''),
    # `\rowcolor` is deliberately NOT in here. The damage described above is
    # `\cellcolor`'s: it sits inside a row, between two `&`, where it overruns
    # a simple table's ruler. `\rowcolor` sits in front of the first cell, and
    # measured against pandoc 3.10.2 it is dropped silently on both the html
    # and the markdown path, so nothing of it reaches a reader either way.
    #
    # Keeping it costs nothing and buys the one thing a results table cannot
    # say without it: which rows are the authors' own. VLA-Adapter shades five,
    # they were stripped here, and the book presented the paper's own numbers
    # looking exactly like the twenty baselines above them. `mark_shaded_rows`
    # reads the command out of the protected float and puts the band back.
    (re.compile(r'\\(?:cell|column)color\s*(?:\[[^\]]*\])?\s*\{[^{}]*\}'), ''),
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
    # `\citet{a, b}` is natbib's "A (2020); B (2020)", one author-in-text
    # citation per key. pandoc writes it `@a [@b]`, which citeproc reads as
    # one citation with the second as a note: ViT printed "Kolesnikov et al.
    # (2020; Djolonga et al. 2020)". Spelled out per key, both the citeproc
    # and the `.bbl` path print it as the paper does. Only without notes.
    (re.compile(r'\\(citet|citeauthor|Citet)\s*\{([^{}]*,[^{}]*)\}'),
     lambda m: '; '.join('\\%s{%s}' % (m.group(1), key.strip())
                         for key in m.group(2).split(',') if key.strip())),
    # textcomp's `\texttildelow` is not a command pandoc knows. It kept it as
    # raw LaTeX together with the NUMBER after it, and the HTML writer drops
    # raw LaTeX: Sentence-BERT's "(~65 hours)" printed as "( hours)", the
    # figure its whole argument rests on. `\textasciitilde{}` it reads.
    (re.compile(r'\\texttildelow(?![A-Za-z])\s*(?:\{\})?'), r'\\textasciitilde{}'),
    # scrextend's `addmargin` indents a block, which is what `quote` is, and
    # `quote` pandoc reads. Kept, PaLM's worked examples -- the input, the
    # scoring, the model's answer -- reached the HTML as raw LaTeX and were
    # dropped, and the build refused the book.
    (re.compile(r'\\begin\{addmargin\*?\}\s*(?:\[[^\]]*\])?\s*\{[^{}]*\}'),
     r'\\begin{quote}'),
    (re.compile(r'\\end\{addmargin\*?\}'), r'\\end{quote}'),
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


_RAISEBOX_RE = re.compile(
    r'\\raisebox\s*\{[^{}]*\}\s*(?:\[[^\]]*\]\s*){0,2}(?=\{)')


def unwrap_raised_graphics(tex):
    r"""`\raisebox{-0.15in}{\includegraphics{x}}` -> the graphic. (text, count).

    The shift only lines a panel up with its neighbours. pandoc keeps the
    wrapper as raw LaTeX, so the graphic inside is never resolved to an image
    and the panel is gone: ViT's figure 7 printed one of its three panels.
    Only a box holding a graphic is unwrapped; one round a table's coloured
    dot or a symbol is left to whatever handles that.
    """
    out, cursor, count = [], 0, 0
    for m in _RAISEBOX_RE.finditer(tex):
        if m.start() < cursor:
            continue
        close = _balanced_brace(tex, m.end())
        body = tex[m.end() + 1:close - 1] if close > 0 else ''
        if '\\includegraphics' not in body:
            continue
        out.append(tex[cursor:m.start()])
        out.append(body)
        cursor = close
        count += 1
    out.append(tex[cursor:])
    return ''.join(out), count


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


_SUBFIGURE_ENV_RE = re.compile(
    r'\\begin\{subfigure\}.*?\\end\{subfigure\}', re.DOTALL)
_SUBCAPTION_CMD_RE = re.compile(r'\\(?:sub)?caption\s*(?:\[[^\]]*\])?\s*(?=\{)')


def bold_subfigure_captions(tex):
    r"""A subfigure's `\caption{X}` becomes a bold paragraph of its own.

    pandoc writes a subfigure caption as a plain paragraph under its panel,
    and `format_figure_blocks` knows a panel's caption by its bold. Plain, it
    was taken for the figure's caption: VAE's figure 4 printed "Learned MNIST
    manifold" -- panel (b)'s label -- as the figure's caption, and the real
    caption below it as a paragraph of body text. Returns (tex, n).
    """
    count = 0

    def in_subfigure(m):
        nonlocal count
        block = m.group(0)
        out, cursor = [], 0
        for c in _SUBCAPTION_CMD_RE.finditer(block):
            if c.start() < cursor:
                continue
            close = _balanced_brace(block, c.end())
            if close < 0:
                continue
            out.append(block[cursor:c.start()])
            out.append('\n\\par\\textbf{%s}\n' % block[c.end() + 1:close - 1].strip())
            cursor = close
            count += 1
        out.append(block[cursor:])
        return ''.join(out)

    return _SUBFIGURE_ENV_RE.sub(in_subfigure, tex), count


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
        # planck writes `%\institute{L2 \and Earth}` and U-Net
        # `%\authorrunning{*}`. The brace scan does not stop at the end of a
        # line, so a commented-out `\address{` whose `}` never comes would
        # run into live text below and take it. The corpus has six.
        if _in_comment(tex, m.start()):
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
        if _in_comment(tex, m.start()):
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
# `\renewcommand\twocolumn[1][]{#1}` is a DEFINITION of the command, and the
# `[1]` after it is its argument count, not a title block. An ICCV paper
# writes exactly that INSIDE its own `\twocolumn[...]`, so the outer block is
# skipped for holding the abstract and the loop walks straight into the
# redefinition.
_DEFINING_RE = re.compile(
    r'\\(?:new|renew|provide)command\s*\*?\s*$'
    r'|\\DeclareRobustCommand\s*\*?\s*$')


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

    And a REDEFINITION of `\\twocolumn` is not a use of it. The ICCV template
    writes `\\renewcommand\\twocolumn[1][]{#1}` inside its own title block, so
    the outer block is skipped for holding the abstract and the walk arrives
    at the redefinition, where `[1]` is an argument count. Cutting it mangles
    the definition, pandoc then dies on the whole document with exit 64, and
    `--backend auto` falls back to calibre without a word: a book with no
    recoverable equations, reported as a successful conversion. That idiom is
    in the CVPR, ICCV and NeurIPS templates, so it is not one paper's problem.
    """
    out, cursor, count = [], 0, 0
    for m in _TWOCOLUMN_RE.finditer(tex):
        if m.start() < cursor:
            continue
        if _DEFINING_RE.search(tex[max(0, m.start() - 48):m.start()]):
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


_FIGURE_ENV_RE = re.compile(
    r'\\begin\{(figure\*?)\}(?:\[[^\]]*\])?(.*?)\\end\{\1\}', re.DOTALL)
_ALGORITHM_FLOAT_RE = re.compile(
    r'\\begin\{(algorithm\*?)\}.*?\\end\{\1\}', re.DOTALL)
# What a figure may hold besides its algorithms and still be only a holder.
_HOLDER_NOISE_RE = re.compile(
    r'\\(?:begin|end)\{minipage\}(?:\[[^\]]*\])?(?:\{[^{}]*\})?'
    r'|\\(?:hfill|centering|small|footnotesize|vspace\*?\{[^{}]*\}|hspace\*?\{[^{}]*\})'
    r'|\\algrenewcommand\{[^{}]*\}\{[^{}]*\}|%[^\n]*|\s')


def unwrap_algorithm_figures(tex):
    r"""A figure that only holds algorithm floats, side by side, becomes them.

    2609.11801 sets its two algorithms in two minipages inside one `figure`.
    pandoc gives that figure the LAST caption and label it finds inside it, so
    the book printed the second algorithm's caption, "Inference", once more as
    a stray line under both, and `alg:b` named the figure as well as the
    algorithm. The algorithms are floats of their own; the figure added only
    the side-by-side layout, which a book page in one column does not keep.
    Returns (tex, n).
    """
    count = 0

    def repl(m):
        nonlocal count
        body = m.group(2)
        algorithms = [a.group(0) for a in _ALGORITHM_FLOAT_RE.finditer(body)]
        if not algorithms:
            return m.group(0)
        rest = _ALGORITHM_FLOAT_RE.sub('', body)
        if _HOLDER_NOISE_RE.sub('', rest):
            return m.group(0)          # a caption, an image, text: a real figure
        count += 1
        return '\n\n'.join(algorithms)

    return _FIGURE_ENV_RE.sub(repl, tex), count


# Numbering a row by hand: step the equation counter and tag the row with it.
# LaTeX prints exactly what an unstarred environment would.
_MANUAL_TAG = (r'\\(?:addtocounter\s*\{equation\}\s*\{1\}|(?:ref)?stepcounter'
               r'\s*\{equation\})\s*\\tag\s*\{\\theequation\}')
_MANUAL_TAG_DEF_RE = re.compile(
    r'\\(?:(?:re)?newcommand\*?\s*\{?\\([A-Za-z]+)\}?|def\s*\\([A-Za-z]+))'
    r'\s*\{\s*' + _MANUAL_TAG + r'\s*\}')
_STARRED_DISPLAY_RE = re.compile(
    r'\\begin\{(align|gather|equation|multline|flalign|eqnarray)\*\}'
    r'(.*?)\\end\{\1\*\}', re.DOTALL)


# What llncs.cls defines itself, so a paper never declares it: name -> title.
_LLNCS_THEOREMS = {
    'theorem': 'Theorem', 'lemma': 'Lemma', 'corollary': 'Corollary',
    'proposition': 'Proposition', 'definition': 'Definition',
    'example': 'Example', 'exercise': 'Exercise', 'note': 'Note',
    'problem': 'Problem', 'property': 'Property', 'question': 'Question',
    'solution': 'Solution', 'remark': 'Remark', 'conjecture': 'Conjecture',
    'claim': 'Claim', 'case': 'Case'}


def declare_class_theorems(tex):
    r"""Declare the theorem-likes llncs defines in the class. (tex, n).

    pandoc reads a `\begin{lemma}` only when the document says
    `\newtheorem{lemma}`, and an LNCS paper never does: the class has them.
    AdamX's lemmas, theorem, remark and proposition reached the book as raw
    LaTeX, which the HTML writer drops, and the build refused it. The
    declarations follow the class options: each its own counter by default,
    one shared counter under `envcountsame`, per section under
    `envcountsect`. Its `credits` block, the acknowledgement, comes out of
    its wrapper with `\ackname` spelled out.
    """
    cls = re.search(r'\\documentclass\s*(\[[^\]]*\])?\s*\{llncs\}', tex)
    if not cls:
        return tex, 0
    options = cls.group(1) or ''
    declared = set(re.findall(
        r'\\(?:sp)?newtheorem\*?\s*\{([^{}]+)\}', tex))
    used = [env for env in _LLNCS_THEOREMS
            if env not in declared and re.search(
                r'\\begin\{%s\}' % env, tex[cls.end():])]
    lines = []
    for env in used:
        if 'envcountsame' in options and env != 'theorem':
            lines.append('\\newtheorem{%s}[theorem]{%s}' % (env, _LLNCS_THEOREMS[env]))
        elif 'envcountsect' in options:
            lines.append('\\newtheorem{%s}{%s}[section]' % (env, _LLNCS_THEOREMS[env]))
        else:
            lines.append('\\newtheorem{%s}{%s}' % (env, _LLNCS_THEOREMS[env]))
    if 'envcountsame' in options and lines and 'theorem' not in used \
            and 'theorem' not in declared:
        lines.insert(0, '\\newtheorem{theorem}{Theorem}')
    tex = re.sub(r'\\(?:begin|end)\{credits\}', '', tex)
    # Uses only. `\renewcommand{\ackname}{Thanks}` spelled out became
    # `\renewcommand{Acknowledgements}{Thanks}`, which pandoc cannot read.
    tex = re.sub(r'\\ackname\b',
                 lambda m: m.group(0) if _DEFINES_RE.search(
                     tex[max(0, m.start() - 40):m.start()])
                 else 'Acknowledgements', tex)
    if lines:
        tex = tex[:cls.end()] + '\n' + '\n'.join(lines) + tex[cls.end():]
    return tex, len(lines)


def number_manually_tagged_rows(tex):
    r"""A starred display numbered by hand becomes an ordinary numbered one.

    VAE defines `\eqnr` as `\addtocounter{equation}{1}\tag{\theequation}` and
    ends 22 `align*` rows with it. Every counter here reads a starred block as
    unnumbered, so the book counted 2 equations where the paper prints 24,
    and texmath, which cannot render `\addtocounter`, printed the 22 formulas
    as raw TeX. The unstarred environment with `\nonumber` on the untagged
    rows numbers exactly the same rows with the same numbers, in LaTeX every
    reader here understands. Returns (tex, blocks rewritten).
    """
    names = {a or b for a, b in _MANUAL_TAG_DEF_RE.findall(tex)}
    marker = _MANUAL_TAG
    if names:
        marker += r'|\\(?:%s)(?![A-Za-z])(?:\{\})?' % '|'.join(
            re.escape(n) for n in sorted(names, key=len, reverse=True))
    marker_re = re.compile(marker)
    count = 0

    def repl(m):
        nonlocal count
        env, body = m.group(1), m.group(2)
        if not marker_re.search(body):
            return m.group(0)
        if env in ('equation', 'multline'):
            new = marker_re.sub('', body)
        else:
            rows = []
            for row in latex_rows.split_rows(body):
                if marker_re.search(row):
                    rows.append(marker_re.sub('', row))
                else:
                    # An empty last row too: unstarred, a trailing `\\`
                    # would number a row that prints nothing.
                    rows.append(row.rstrip() + ' \\nonumber'
                                + row[len(row.rstrip()):])
            new = '\\\\'.join(rows)
        count += 1
        return '\\begin{%s}%s\\end{%s}' % (env, new, env)

    return _STARRED_DISPLAY_RE.sub(repl, tex), count


_GRAPHIC_CALL_RE = re.compile(
    r'\\includegraphics\s*(?:\[[^\]]*\])?\s*\{[^{}]*\}')
# `tabular*` takes its width before the column spec.
_LAYOUT_TABULAR_RE = re.compile(
    r'\\begin\{(tabular\*?)\}\s*(?:\[[^\]]*\])?\s*'
    r'(?:\{[^{}]*\}\s*(?=\{))?\{(?:[^{}]|\{[^{}]*\})*\}'
    r'(.*?)\\end\{\1\}', re.DOTALL)
# What a layout cell may hold besides its graphic.
_LAYOUT_NOISE_RE = re.compile(
    r'\\\\(?:\[[^\]]*\])?|&|\\(?:hfill|centering|quad|qquad'
    r'|vspace\*?\{[^{}]*\}|hspace\*?\{[^{}]*\})|%[^\n]*|\s')


def unwrap_graphics_tabulars(tex):
    r"""A tabular inside a figure that only lays out graphics becomes them.

    ViT centres its model diagram in a one-cell `tabular`. pandoc reads that
    as a table: the figure became a table holding an image, its caption a
    plain paragraph with no number, and the book counted one table more than
    the paper has. Only a tabular whose cells hold nothing but graphics is
    unwrapped; a grid with labels or numbers in it is a real table.
    Returns (tex, n).
    """
    count = 0

    def in_figure(m):
        body = m.group(2)

        def tabular(t):
            nonlocal count
            cells = t.group(2)
            graphics = _GRAPHIC_CALL_RE.findall(cells)
            if not graphics or _LAYOUT_NOISE_RE.sub(
                    '', _GRAPHIC_CALL_RE.sub('', cells)):
                return t.group(0)
            count += 1
            return '\n'.join(graphics)

        new = _LAYOUT_TABULAR_RE.sub(tabular, body)
        return m.group(0) if new == body else m.group(0).replace(body, new, 1)

    return _FIGURE_ENV_RE.sub(in_figure, tex), count


_MINIPAGE_RE = re.compile(
    r'\\begin\{minipage\}(?:\[[^\]]*\])*\{[^{}]*\}(.*?)\\end\{minipage\}',
    re.DOTALL)


def split_captioned_minipages(tex):
    r"""A figure of side-by-side minipages, each with its own caption, becomes
    one figure per minipage. Returns (tex, n).

    LaTeX numbers each caption; pandoc gives the float only its LAST one. ViT
    sets figures 3 and 4 that way: the book printed one figure with both
    images, figure 3's caption was gone, and the `\;` spacing between the
    minipages reached the page. Side by side is a layout a one-column book
    page does not keep, and two floats is what the paper numbers.
    """
    count = 0

    def repl(m):
        nonlocal count
        env, body = m.group(1), m.group(2)
        pages = list(_MINIPAGE_RE.finditer(body))
        if len(pages) < 2 or '\\captionof' in body:
            return m.group(0)
        if not all('\\caption' in p.group(1) for p in pages):
            return m.group(0)
        outside = _MINIPAGE_RE.sub('', body)
        if '\\caption' in outside or '\\includegraphics' in outside:
            return m.group(0)        # a float caption over panels: one figure
        count += 1
        return '\n\n'.join('\\begin{%s}\n%s\n\\end{%s}' % (env, p.group(1).strip(), env)
                           for p in pages)

    return _FIGURE_ENV_RE.sub(repl, tex), count


_ENUM_LABEL_RE = re.compile(r'\\begin\{enumerate\}\s*\[')
_ENUM_COUNTERS = {
    'arabic': lambda n: str(n),
    'alph': lambda n: 'abcdefghijklmnopqrstuvwxyz'[n - 1],
    'Alph': lambda n: 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'[n - 1],
    'roman': lambda n: ['i', 'ii', 'iii', 'iv', 'v', 'vi', 'vii', 'viii',
                        'ix', 'x', 'xi', 'xii'][n - 1],
    'Roman': lambda n: ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII',
                        'IX', 'X', 'XI', 'XII'][n - 1],
}


def _label_option(options):
    """The value of `label=` in an enumitem option list, braces balanced."""
    m = re.search(r'(?:^|,)\s*label\s*=\s*', options)
    if not m:
        return None
    i, depth, out = m.end(), 0, []
    while i < len(options):
        c = options[i]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
        elif c == ',' and depth == 0:
            break
        out.append(c)
        i += 1
    return ''.join(out).strip()


def relabel_enumerate(tex):
    r"""A numbered list with its own label prints that label.

    pandoc ignores enumitem's `label=`: `\begin{enumerate}[label={\bf
    Q\arabic*}.]` became a plain 1., 2., 3. list, so 2609.11801's three
    research questions lost the "Q1", "Q2", "Q3" its later section titles
    refer back to, and `label=(\alph*)` prints 1., 2. as well. Each item
    becomes a paragraph opening with the label the paper prints, set the way
    the paper sets it. A plain `\arabic*.` is left to pandoc. Returns (tex, n).
    """
    count = 0
    out, pos = [], 0
    for m in _ENUM_LABEL_RE.finditer(tex):
        if m.start() < pos:
            continue
        close = tex.find(']', m.end())
        # The option list may hold braces with `]` inside; find the real end.
        depth, i = 0, m.end()
        while i < len(tex):
            if tex[i] == '{':
                depth += 1
            elif tex[i] == '}':
                depth -= 1
            elif tex[i] == ']' and depth == 0:
                close = i
                break
            i += 1
        label = _label_option(tex[m.end():close])
        end = tex.find('\\end{enumerate}', close)
        if not label or end == -1:
            continue
        body = tex[close + 1:end]
        if '\\begin{enumerate}' in body or '\\begin{itemize}' in body:
            continue
        counter = re.search(r'\\(arabic|alph|Alph|roman|Roman)\*', label)
        if not counter:
            continue
        if re.sub(r'\s', '', label) in ('\\arabic*.', '{\\arabic*.}'):
            continue                      # 1., 2., 3. is what pandoc prints
        items = re.split(r'\\item\b\s*', body)
        if len(items) < 2 or len(items) > 13:
            continue
        paragraphs = []
        for n, item in enumerate(items[1:], 1):
            text = re.sub(r'\\vspace\*?\{[^{}]*\}', '', item).strip()
            # The label as the paper wrote it, number put in: `{\bf Q1}.`
            # keeps exactly the bold the original prints.
            mark = re.sub(r'\\(arabic|alph|Alph|roman|Roman)\*',
                          lambda c: _ENUM_COUNTERS[c.group(1)](n), label)
            # No `\noindent` in front: pandoc took the `{\bf Q1}` after it as
            # the command's argument and dropped both.
            paragraphs.append('%s %s' % (mark, text))
        out.append(tex[pos:m.start()])
        out.append('\n\n' + '\n\n'.join(paragraphs) + '\n\n')
        pos = end + len('\\end{enumerate}')
        count += 1
    out.append(tex[pos:])
    return ''.join(out), count


_FOOTNOTE_PIECE_RE = re.compile(r'\\footnote(mark|text)\b\s*(?:\[[^\]]*\])?')


def keep_unmarked_footnotetext(tex):
    r"""A `\footnotetext` with no `\footnotemark` waiting for it stays as text.

    pandoc pairs each `\footnotetext` with the `\footnotemark` before it and
    drops one that has none. Papers write unmarked notes exactly that way:
    2609.11801 puts its "Work done while a visiting researcher" and "Equal
    advising" note under the title with `\renewcommand{\thefootnote}{}`, and
    BERT adds "See (10) in gluebenchmark.com/faq" after a table. Both books
    lost the note. It becomes a paragraph where it stood, which is what a
    reader of the original sees at the foot of that page. Returns (tex, n).
    """
    out, pending, count, i = [], 0, 0, 0
    for m in _FOOTNOTE_PIECE_RE.finditer(tex):
        if m.start() < i or _in_latex_comment(tex, m.start()):
            continue
        if m.group(1) == 'mark':
            pending += 1
            continue
        if pending:
            pending -= 1
            continue
        brace = m.end()
        if brace >= len(tex) or tex[brace] != '{':
            continue
        body = _balanced_arg(tex, brace)
        if body is None:
            continue
        end = brace + len(body) + 2
        # Note marks set in text, which pandoc keeps as raw LaTeX and the
        # HTML then drops: "†Equal advising" printed as "Equal advising".
        body = re.sub(r'\\q?quad\b\s*', ' ', body)
        body = re.sub(r'\\ddag\b\s*', '‡', body)
        body = re.sub(r'\\dag\b\s*', '†', body)
        out.append(tex[i:m.start()])
        out.append('\n\n%s\n\n' % body.strip())
        i = end
        count += 1
    out.append(tex[i:])
    return ''.join(out), count


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
    tex, raised = unwrap_raised_graphics(tex)
    if raised:
        print(f"Unwrapped {raised} \\raisebox wrapper(s) round a graphic so the "
              f"panel is extracted")
    tex, subcaps = bold_subfigure_captions(tex)
    if subcaps:
        print(f"Set {subcaps} subfigure caption(s) as their panel's bold label; "
              f"plain, they read as the figure's own caption")
    tex, panels = unwrap_subfloat(tex)
    if panels:
        print(f"Unwrapped {panels} \\subfloat panel(s) so pandoc can see the "
              f"figures inside them")
    tex, lists = relabel_enumerate(tex)
    if lists:
        print(f"Kept the printed labels of {lists} numbered list(s) whose "
              f"label carries words (Q1, Q2, ...); pandoc numbers them 1, 2, ...")
    tex, notes = keep_unmarked_footnotetext(tex)
    if notes:
        print(f"Kept {notes} \\footnotetext with no \\footnotemark as text; "
              f"pandoc drops an unpaired one")
    tex, holders = unwrap_algorithm_figures(tex)
    if holders:
        print(f"Unwrapped {holders} figure(s) that only held algorithms; "
              f"pandoc would print their last caption a second time")
    tex, split = split_captioned_minipages(tex)
    if split:
        print(f"Split {split} figure(s) of captioned minipages into one figure "
              f"each; pandoc keeps only the last caption of a float")
    tex, layouts = unwrap_graphics_tabulars(tex)
    if layouts:
        print(f"Unwrapped {layouts} tabular(s) that only laid out a figure's "
              f"graphics; pandoc would make the figure a table")
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


_CITE_KEYS_RE = re.compile(
    r'\\(?:no)?cite[a-zA-Z]*\*?\s*(?:\[[^\]]*\]\s*){0,2}\{([^{}]+)\}')


def nocite_every_cited_key(tex):
    r"""`\nocite` every key the document cites, so citeproc lists them all.

    LaTeX lists every cited work. citeproc lists only the citations pandoc
    read, and a table float passes through as raw LaTeX: Touvron et al.
    (2020), cited only in ViT's Table 2 caption, was missing from its
    reference list. Declaring the cited keys is exactly LaTeX's own rule,
    so a key cited nowhere is still not listed.
    """
    keys = []
    for m in _CITE_KEYS_RE.finditer(tex):
        if _in_latex_comment(tex, m.start()):
            continue                   # LaTeX does not list that one either
        for key in m.group(1).split(','):
            key = key.strip()
            if key and key != '*' and key not in keys:
                keys.append(key)
    if not keys:
        return tex
    line = '\n\\nocite{%s}\n' % ','.join(keys)
    # Before `\end{document}`: pandoc reads nothing after it.
    end = tex.rfind('\\end{document}')
    return tex[:end] + line + tex[end:] if end >= 0 else tex + line


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


# pandoc names the file it could not read, and that name decides who can act.
# Everything else this converter reports is ours to fix; a bibliography that
# will not parse belongs to the paper (K145).
_BIB_READ_ERROR_RE = re.compile(r"Error reading bibliography file '([^']+)'")


# Where the paper's `\bibliography{...}` stood. pandoc reads the command and
# leaves nothing in its place, then appends the reference list after the last
# block, so 2609.11801's references came after its appendix while the paper
# prints them before it. A word pandoc keeps as an ordinary paragraph marks
# the spot; the list is moved there in pandoc's tree and the word removed.
_BIB_ANCHOR = 'TBREFERENCELISTANCHOR'
_BIBLIOGRAPHY_CMD_RE = re.compile(r'\\bibliography\s*\{[^{}]*\}')


_REFS_END_RE = re.compile(
    r'\\end\s*\{thebibliography\}|\\bibliography\s*\{[^{}]*\}'
    r'|\\printbibliography(?:\[[^\]]*\])?')
_NEXT_SECTION_RE = re.compile(
    r'\\(?:part|chapter|section|subsection)\*?\s*(?:\[[^\]]*\]\s*)?\{')
_FLOAT_OPEN_RE = re.compile(r'\\begin\s*\{(figure|table|SCfigure)(\*?)\}')
# What may stand between the list and the next section beside the floats.
_BETWEEN_RE = re.compile(
    r'\\appendix\b|\\clearpage\b|\\newpage\b|\\cleardoublepage\b'
    r'|\\bibliographystyle\s*\{[^{}]*\}|\s+')


def floats_out_of_references(tex):
    r"""Move floats written between the reference list and the next section
    into that section, after its first paragraph. Returns (tex, n).

    VAE writes Figures 4 and 5 after `\appendix` and before
    `\section{Visualisations}`; LaTeX could not fit them on the references'
    last page and set them after the section's opening paragraph. pandoc
    keeps source order, so the book printed both figures between the last
    reference and appendix A, belonging to neither. Only when nothing but
    floats, `\appendix`, page breaks and comments stand in that gap.
    """
    ends = list(_REFS_END_RE.finditer(tex))
    if not ends:
        return tex, 0
    start = ends[-1].end()
    section = _NEXT_SECTION_RE.search(tex, start)
    if not section:
        return tex, 0
    gap = tex[start:section.start()]
    floats, rest, at = [], [], 0
    for m in _FLOAT_OPEN_RE.finditer(gap):
        if m.start() < at:
            continue
        close = re.compile(r'\\end\s*\{%s%s\}' % (m.group(1), re.escape(m.group(2))))
        c = close.search(gap, m.end())
        if not c:
            return tex, 0
        rest.append(gap[at:m.start()])
        floats.append(gap[m.start():c.end()])
        at = c.end()
    rest.append(gap[at:])
    residue = re.sub(r'(?<!\\)%[^\n]*', '', ''.join(rest))
    if not floats or _BETWEEN_RE.sub('', residue):
        return tex, 0
    head_end = _balanced_brace(tex, section.end() - 1)
    if head_end < 0:
        return tex, 0
    # The end of the section's first paragraph, unless something structural
    # comes first; then straight after the heading.
    insert = head_end
    body = re.match(r'(?:\s*\\label\s*\{[^{}]*\})?\s*', tex[head_end:])
    first = head_end + body.end()
    blank = re.compile(r'\n[ \t]*\n').search(tex, first)
    stop = blank.start() if blank else len(tex)
    if first < stop and not re.match(r'\\(?:begin|section|subsection|part|chapter)\b',
                                     tex[first:]):
        insert = stop
    moved = '\n\n' + '\n\n'.join(floats) + '\n'
    out = (tex[:start] + ''.join(rest) + tex[section.start():insert] + moved
           + tex[insert:])
    return out, len(floats)


def _anchor_bibliography(tex):
    for m in _BIBLIOGRAPHY_CMD_RE.finditer(tex):
        line_start = tex.rfind('\n', 0, m.start()) + 1
        if re.search(r'(?<!\\)%', tex[line_start:m.start()]):
            continue
        return tex[:m.end()] + '\n\n%s\n\n' % _BIB_ANCHOR + tex[m.end():], True
    return tex, False


def _is_anchor(block):
    return (block.get('t') == 'Para' and len(block.get('c', [])) == 1
            and block['c'][0].get('t') == 'Str'
            and block['c'][0].get('c') == _BIB_ANCHOR)


def _move_refs_to_anchor(tree):
    """Put the `refs` Div where the anchor paragraph is. True if moved."""
    blocks = tree.get('blocks', [])
    refs = [i for i, b in enumerate(blocks)
            if b.get('t') == 'Div' and b['c'][0][0] == 'refs']
    anchors = [i for i, b in enumerate(blocks) if _is_anchor(b)]
    if len(refs) != 1 or len(anchors) != 1 or refs[0] < anchors[0]:
        return False
    div = blocks.pop(refs[0])
    blocks[anchors[0]] = div
    return True


def _drop_anchor(tree):
    tree['blocks'] = [b for b in tree.get('blocks', []) if not _is_anchor(b)]


# The year letter of an author-year label: `Wang et al. 2020a`.
_LABEL_LETTER_RE = re.compile(r'^(.*\S)\s+(\d{4})([a-z])$')
# A citeproc year token: `2020a`, `(2020a,`, `2020b).`
_YEAR_TOKEN_RE = re.compile(r'^(\W*)(\d{4})([a-z])(\W*)$')


def bbl_year_letters(citation_map):
    """{key: (authors, year, letter)} for each `.bbl` label carrying a letter."""
    out = {}
    for key, label in (citation_map or {}).items():
        m = _LABEL_LETTER_RE.match(label)
        if m:
            out[key] = (m.group(1), m.group(2), m.group(3))
    return out


def _walk_inlines(node, fn):
    """Call fn(list) on every inline list under node, depth first."""
    if isinstance(node, dict):
        for value in node.values():
            _walk_inlines(value, fn)
    elif isinstance(node, list):
        if node and all(isinstance(x, dict) and 't' in x for x in node):
            fn(node)
        for value in node:
            _walk_inlines(value, fn)


def _inline_text(node):
    if isinstance(node, dict):
        if node.get('t') == 'Str':
            return node['c']
        if node.get('t') in ('Space', 'SoftBreak', 'LineBreak'):
            return ' '
        return _inline_text(node.get('c'))
    if isinstance(node, list):
        return ''.join(_inline_text(x) for x in node)
    return ''


def align_year_letters(tree, letters):
    r"""Give citeproc's year letters the `.bbl`'s order. Returns the count.

    citeproc letters two works by the same authors in the same year by its own
    sort, BibTeX by its own; ViT cites Axial-DeepLab twice (ECCV and arXiv,
    same title) and the book's 2020a/2020b were the original's 2020b/2020a.
    A table citation is rendered from the `.bbl` (`latex_tables`), so the two
    disagreed inside one book. citeproc takes no letter from the `.bib`, so
    its output is relabelled: per group (authors, year) whose letters are a
    permutation of the `.bbl`'s, in the reference entries (`ref-<key>`) and in
    every Cite whose text names that group's authors before the year.
    """
    entries = {}

    def find_entries(node):
        if isinstance(node, dict):
            if node.get('t') == 'Div':
                ident = node['c'][0][0]
                if ident.startswith('ref-'):
                    entries[ident[4:]] = node
            for value in node.values():
                find_entries(value)
        elif isinstance(node, list):
            for value in node:
                find_entries(value)

    find_entries(tree.get('blocks', []))

    def year_tokens(node, year):
        found = []

        def visit(inlines):
            for item in inlines:
                if item.get('t') == 'Str':
                    m = _YEAR_TOKEN_RE.match(item['c'])
                    if m and m.group(2) == year:
                        found.append(item)

        _walk_inlines(node, visit)
        return found

    groups = {}
    for key, (authors, year, letter) in letters.items():
        groups.setdefault((authors, year), []).append(key)
    swaps = {}
    for (authors, year), keys in groups.items():
        given = {}
        for key in keys:
            tokens = year_tokens(entries.get(key, {}), year)
            if not tokens:
                break
            given[key] = _YEAR_TOKEN_RE.match(tokens[0]['c']).group(3)
        else:
            want = {k: letters[k][2] for k in keys}
            if sorted(given.values()) == sorted(want.values()) \
                    and given != want:
                swaps[(authors, year)] = {given[k]: want[k] for k in keys}
    if not swaps:
        return 0
    count = 0

    def relabel(item, table):
        m = _YEAR_TOKEN_RE.match(item['c'])
        new = table.get(m.group(3))
        if new and new != m.group(3):
            item['c'] = m.group(1) + m.group(2) + new + m.group(4)
            return True
        return False

    for (authors, year), table in swaps.items():
        for key in groups[(authors, year)]:
            for item in year_tokens(entries[key], year)[:1]:
                count += relabel(item, table)
        # The list then reads 2020b before 2020a; put the group's entries
        # back in letter order, in the slots they already hold.
        mine = {id(entries[k]): letters[k][2] for k in groups[(authors, year)]}

        def reorder(node):
            if isinstance(node, list):
                slots = [i for i, x in enumerate(node) if id(x) in mine]
                if len(slots) > 1:
                    ordered = sorted((node[i] for i in slots),
                                     key=lambda x: mine[id(x)])
                    for i, x in zip(slots, ordered):
                        node[i] = x
                    return
                for x in node:
                    reorder(x)
            elif isinstance(node, dict):
                for x in node.values():
                    reorder(x)

        reorder(tree.get('blocks', []))

    def visit_cite(inlines):
        nonlocal count
        for cite in inlines:
            if cite.get('t') != 'Cite':
                continue
            # The authors stand between the last `;` and the year.
            segment = ''
            for item in cite['c'][1]:
                text = _inline_text(item).replace('\xa0', ' ')
                if item.get('t') == 'Str':
                    m = _YEAR_TOKEN_RE.match(text)
                    if m:
                        hits = [table for (authors, year), table in swaps.items()
                                if year == m.group(2) and authors in segment]
                        if len(hits) == 1:
                            count += relabel(item, hits[0])
                segment += text
                if ';' in text:
                    segment = text.rsplit(';', 1)[1]

    _walk_inlines(tree.get('blocks', []), visit_cite)
    return count


def _full_author_csl(pypandoc):
    r"""pandoc's own default style, listing every author in the reference list.

    The default (Chicago author-date) cuts a reference to three names and
    "et al." from seven authors on. The papers this reads print them all --
    natbib's plainnat, the style of 2609.11801, names every author -- and a
    reader of the translation had 44 entries shortened that the original
    gives in full. In-text citations keep the default's "et al.". Returns a
    temporary file's path, or None to fall back to the default.
    """
    try:
        exe = pypandoc.get_pandoc_path()
        style = subprocess.run([exe, '--print-default-data-file', 'default.csl'],
                               capture_output=True, timeout=30).stdout.decode('utf-8')
    except Exception:          # no style to adjust: the default one still works
        return None
    patched, n = re.subn(
        r'(<bibliography\b[^>]*?)\s+et-al-min="\d+"\s+et-al-use-first="\d+"',
        r'\1', style, count=1)
    if not n:
        return None
    fd, path = tempfile.mkstemp(suffix='.csl', prefix='translate_book_')
    with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as f:
        f.write(patched)
    return path


def latex_to_markdown(flat_tex, tex_dir, root, bib_files=None,
                      year_letters=None):
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

    csl = None
    try:
        if bib_files:
            csl = _full_author_csl(pypandoc)
            if csl:
                extra.append(f'--csl={csl}')
            tex = nocite_every_cited_key(tex)
            tex, anchored = _anchor_bibliography(tex)
            # Two passes, so the reference list can be moved in pandoc's own
            # document tree before the markdown writer flattens it: the writer
            # runs with -native_divs, which leaves nothing to find it by.
            tree = json.loads(pypandoc.convert_text(
                tex, 'json', format=_READER, extra_args=extra))
            if anchored and _move_refs_to_anchor(tree):
                print("Bibliography: the reference list stays where the paper "
                      "put it, ahead of the appendix")
            _drop_anchor(tree)
            if year_letters:
                n = align_year_letters(tree, year_letters)
                if n:
                    print(f"Year letters: {n} label(s) relabelled to the "
                          f".bbl's order")
            # `-citations`: in one pass the writer prints what citeproc
            # rendered; reading the tree back in a second pass it would
            # print every citation as its `[@key]` instead.
            md = pypandoc.convert_text(json.dumps(tree), _WRITER + '-citations',
                                       format='json', extra_args=['--wrap=none'])
        else:
            md = pypandoc.convert_text(tex, _WRITER, format=_READER,
                                       extra_args=extra)
        out = restore_table_floats(md)
        # pandoc emits CRLF here; normalize before any newline-sensitive
        # processing or writing. See normalize_newlines().
        return normalize_newlines(out)
    except Exception as e:
        print(f"LaTeX to markdown conversion failed: {e}")
        bad = _BIB_READ_ERROR_RE.search(str(e))
        if bad:
            # The generic advice below this ("fix the cause reported above")
            # sends the reader at something they did not write and cannot
            # change upstream, so say whose file it is and what actually
            # works on it.
            print(f"  That file came out of the paper's own tarball, not out "
                  f"of this pipeline. BibTeX tolerates brace faults that "
                  f"pandoc's reader stops at, which is why the paper builds "
                  f"on arXiv and this conversion does not (K145).")
            print(f"  Editing it in place will not help: the source tree is "
                  f"deleted and re-unpacked on every run, so the repair is "
                  f"gone before pandoc reads it.")
            print(f"  `--backend auto` finishes through calibre instead, "
                  f"without equations. There is no path today that keeps both "
                  f"the equations and the citations of a paper whose own "
                  f"bibliography will not parse.")
        return None
    finally:
        if csl:
            try:
                os.remove(csl)
            except OSError:
                pass


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
# One or more commands, not exactly one. TeX writes several directives in a
# single escape -- `\begingroup\postdisplaypenalty=10000` is two -- and a
# pattern that stopped after the first never matched such a span at all, so
# it was not cleaned, not dropped, and printed to the reader in monospace.
_RAW_INLINE_RE = re.compile(
    r'`((?:\\[a-zA-Z@]+(?:\s*(?:\{[^{}]*\}|\[[^\[\]]*\]|=[-\d.]+[a-z]*))*)+)'
    r'`\{=latex\}')
_LAYOUT_ONLY = re.compile(
    r'^\\(?:looseness|vspace|hspace|noindent|centering|small|footnotesize'
    r'|scriptsize|normalsize|bigskip|medskip|smallskip|clearpage|newpage'
    r'|linebreak|nolinebreak|allowbreak|raggedright|raggedleft|par'
    # \label carries nothing a reader sees, and cross-references resolve from
    # flat.tex rather than from here. Backticking it and letting
    # strip_latex_cruft empty the span left a bare `` glued to the image line,
    # which stopped format_figure_blocks from recognising the image at all.
    # Grouping and penalty directives. They control where TeX may break a
    # page and nothing a reader sees, but they arrive as an ordinary inline
    # escape, so they fell through to the branch that keeps the literal and
    # printed as `\endgroup` in monospace in the middle of a Korean page.
    r'|begingroup|endgroup|penalty|postdisplaypenalty|predisplaypenalty'
    r'|interlinepenalty|widowpenalty|clubpenalty|displaybreak|nobreak'
    r'|goodbreak|phantomsection|leavevmode|protect|relax'
    r'|label)\b')
# The same alternation, unanchored, to ask a different question: is there
# anything left once every layout directive is removed? One escape can hold
# several -- `\begingroup\postdisplaypenalty=10000` is two -- and matching
# only the head would be right by luck here and wrong on a span whose layout
# command is followed by text the reader needs.
_LAYOUT_ONLY_ANY = re.compile(
    _LAYOUT_ONLY.pattern.replace(r'^\\', r'\\', 1)
    + r'\s*(?:\*?\s*=\s*[-\d.]+[a-z]*|\*?\s*\{[^{}]*\})?')
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
        # Ask what is LEFT, not what it starts with. An escape can hold
        # several directives, and a span whose layout command is followed by
        # text the reader needs must keep that text.
        if not _LAYOUT_ONLY_ANY.sub('', cmd).strip():
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
# The whitespace run is deliberately NOT `\s*`. `\s` matches newlines, so a
# command with no argument ate everything up to the next word -- including the
# indentation of the line below it. VLA-Adapter puts `{\small` in front of a
# `verbatim` listing; pandoc leaves `\small` on its own line above an indented
# code block, and the match came out as `'\\small\n\n    '`, twelve characters
# ending in the four spaces that made the next line code. At column zero
# `class MLPResNetBlock_Pro(nn.Module):` is a paragraph, so the listing broke
# in two and its first line was typeset as prose.
#
# An argument may still sit on the following line, which is why the first
# branch allows one newline before a brace; without an argument nothing but
# spaces and tabs comes off. Blank lines left behind are expected -- that is
# what `repair_display_math` and the `\n{4,}` collapse downstream are for.
_LATEX_CRUFT_RE = re.compile(
    r'\\(?:label|vspace|hspace|centering|noindent|clearpage|newpage|FloatBarrier'
    r'|acks|small|footnotesize|scriptsize|normalsize|bigskip|medskip|smallskip)'
    r'\*?(?:[ \t]*\r?\n?[ \t]*\{[^{}]*\}|[ \t]*)'
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


_GRAPHICSPATH_RE = re.compile(r'\\graphicspath\s*\{((?:\s*\{[^{}]*\}\s*)+)\}')


def _read_flat_source(temp_dir):
    """The flattened LaTeX, or '' when there is none to read."""
    path = os.path.join(temp_dir or '', 'flat.tex')
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as fh:
            return fh.read()
    except OSError:
        return ''


def graphics_search_dirs(text, bases):
    r"""The directories `\graphicspath` adds, resolved against each base.

    `\graphicspath{{figures/}}` is how a paper says that a bare
    `\includegraphics{plot.pdf}` means `figures/plot.pdf`. Not reading it
    reports the figure missing while the file sits in the tarball: on the
    paper that found this, the five calls written `figures/x.pdf` resolved
    and the two written `x.pdf` did not, so two figures were dropped with
    nothing but a warning, their captions left orphaned on the page.
    """
    out = []
    for m in _GRAPHICSPATH_RE.finditer(text or ''):
        for piece in re.findall(r'\{([^{}]*)\}', m.group(1)):
            piece = piece.strip()
            if not piece:
                continue
            for base in bases:
                if not base:
                    continue
                candidate = os.path.normpath(os.path.join(base, piece))
                if os.path.isdir(candidate) and candidate not in out:
                    out.append(candidate)
    return out


def resolve_images(text, tex_dir, root, temp_dir, work_dir):
    """Copy/convert every referenced figure into temp_dir/images and rewrite refs."""
    images_dir = os.path.join(temp_dir, 'images')
    os.makedirs(images_dir, exist_ok=True)
    # `\graphicspath` is a PREAMBLE declaration, and `text` here is the
    # markdown pandoc already produced, so the declaration is long gone from
    # it. Read it from `flat.tex`, which the backend writes before conversion
    # precisely so that later steps can ask the source a question.
    search_dirs = [tex_dir, root] + graphics_search_dirs(
        _read_flat_source(temp_dir), [tex_dir, root])
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
    # Before pandoc reads them, and after the unpack that would have thrown
    # away any hand repair (K145).
    mended = sum(repair_bib_braces(p) for p in bib_files)
    if mended:
        print(f"Bibliography: {mended} entry(ies) closed with a brace pandoc "
              f"read as literal text; BibTeX had already closed them")
    if not bib_files:
        flat = inline_bibliography(flat, work_dir, main_tex)

    flat, front_sections = sectionize_front_matter(flat)
    if front_sections:
        print(f"Front matter: {front_sections} abstract/keywords block(s) kept "
              f"as sections (pandoc drops them as metadata otherwise)")

    # The paper's own shorthand, before pandoc reads the source. A `.sty` is
    # never `\input`, so `flatten_tex` does not inline it and pandoc never sees
    # the definition -- the name then survives `+raw_tex` verbatim and prints
    # at the reader. resnet's finished book had `\ie` mid-sentence five times.
    # Done here rather than inside latex_to_markdown so flat.tex, the markdown
    # and everything downstream that re-reads flat.tex agree on one source.
    flat, macro_report = paper_macros.expand_in_source(
        flat, paper_macros.shipped_sources(flat, work_dir),
        paper_text=read_pdf_text(input_file))
    for name, source in sorted(macro_report.get('decided', {}).items()):
        print(f"\\{name} has competing definitions; the printed paper picks "
              f"the one in {source}")
    if macro_report['expanded']:
        top = sorted(macro_report['expanded'].items(), key=lambda kv: -kv[1])
        print(f"Expanded {sum(macro_report['expanded'].values())} call(s) of "
              f"the paper's own macros: "
              + ', '.join(f'\\{k} x{v}' for k, v in top[:6]))
    flat, declared = declare_class_theorems(flat)
    if declared:
        print(f"Declared {declared} theorem-like environment(s) the document "
              f"class defines; pandoc reads only declared ones")
    flat, tagged = number_manually_tagged_rows(flat)
    if tagged:
        print(f"Rewrote {tagged} starred display(s) the paper numbers by hand "
              f"(\\addtocounter + \\tag) as ordinary numbered ones")
    flat, moved = floats_out_of_references(flat)
    if moved:
        print(f"Moved {moved} float(s) from between the reference list and the "
              f"next section into that section, where the paper prints them")
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

    md = latex_to_markdown(
        flat, os.path.dirname(main_tex), work_dir, bib_files=bib_files,
        year_letters=bbl_year_letters(build_citation_map(work_dir, main_tex))
        if bib_files else None)
    if md is None:
        return False, {}

    # Only needed when citeproc could not run (no .bib in the source).
    citation_map = {} if bib_files else build_citation_map(work_dir, main_tex)
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

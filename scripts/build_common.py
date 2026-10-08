# -*- coding: utf-8 -*-
"""Small helpers more than one part of the build leans on.

Split out of merge_and_build.py with latex_cleanup.py, numbering.py and
latex_tables.py, to keep every file under the 256 KiB that Anthropic's plugin
directory reads before it will publish a release. What is here is what those
modules share, so none of them has to import another sideways.
"""

import os
import re
import shutil
import subprocess
from collections import Counter
from html.parser import HTMLParser


# =============================================================================
# Image structure validation helpers
# =============================================================================

# Markdown image: `![alt](url)` or `![alt](url "title")`.
# - Negative lookbehind on `\` skips escaped `\![...]` (renders as literal text).
# - Closing `)` is required — a missing `)` means the image won't render, so
#   such a fragment must NOT count as a preserved image reference.
_MD_IMG_RE = re.compile(r'(?<!\\)!\[[^\]]*\]\(\s*([^)\s]+)[^)]*\)')
_VALID_ATTR_NAME_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_:.\-]*$')


class _ImgTagCollector(HTMLParser):
    """Collects every <img> tag found in fed text. Uses stdlib HTMLParser, which
    correctly handles `>` inside quoted attribute values — unlike a plain
    `<img\\b[^>]*>` regex, which would truncate at the first `>`."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.records = []  # list of (raw_tag_text, attrs_list)

    def handle_starttag(self, tag, attrs):
        if tag == 'img':
            self.records.append((self.get_starttag_text(), list(attrs)))

    handle_startendtag = handle_starttag


def _scan_img_tags(text):
    """Return (Counter of <img> srcs, list of (raw_tag, bad_attr_name) tuples).

    Feeds the entire text to HTMLParser rather than pre-extracting tags via regex,
    so quoted attribute values containing `>` are handled correctly."""
    src_counts = Counter()
    bad_attrs = []
    parser = _ImgTagCollector()
    try:
        parser.feed(text)
        parser.close()
    except Exception as e:
        bad_attrs.append(('<unparseable input>', f'<parser error: {e}>'))
        return src_counts, bad_attrs
    for raw_tag, attrs in parser.records:
        for name, _ in attrs:
            if not _VALID_ATTR_NAME_RE.match(name):
                bad_attrs.append((raw_tag, name))
        for name, val in attrs:
            if name == 'src' and val:
                src_counts[val] += 1
    return src_counts, bad_attrs


def _scan_image_refs(text):
    """Return (Counter html_srcs, Counter md_srcs, list bad_attrs)."""
    html_srcs, bad_attrs = _scan_img_tags(text)
    md_srcs = Counter(_MD_IMG_RE.findall(text))
    return html_srcs, md_srcs, bad_attrs

# [] = not yet resolved, [None] = definitively absent
_PANDOC_PATH = []


def resolve_pandoc():
    """Return an absolute pandoc path, or None. Cached after the first call.

    A bare `pandoc` lookup is not enough: on Windows the official installer
    drops pandoc in %LOCALAPPDATA%\\Pandoc without touching PATH, so probing
    only PATH silently downgrades the whole build to a table-less fallback.
    """
    if _PANDOC_PATH:
        return _PANDOC_PATH[0]

    found = None
    # pypandoc knows how to locate pandoc without PATH
    try:
        import pypandoc
        found = pypandoc.get_pandoc_path()
    except Exception:
        found = None

    if not found:
        found = shutil.which('pandoc')

    if not found:
        exe = 'pandoc.exe' if os.name == 'nt' else 'pandoc'
        for cand in [
            os.environ.get('PANDOC_PATH'),
            os.environ.get('PYPANDOC_PANDOC'),
            os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Pandoc', exe),
            r"C:\Program Files\Pandoc\pandoc.exe",
            r"C:\Program Files (x86)\Pandoc\pandoc.exe",
            "/usr/local/bin/pandoc", "/usr/bin/pandoc", "/opt/homebrew/bin/pandoc",
        ]:
            if cand and os.path.isfile(cand):
                found = cand
                break

    if found:
        try:
            result = subprocess.run(
                [found, '--version'], capture_output=True, text=True,
                encoding='utf-8', errors='replace', timeout=30
            )
            if result.returncode != 0:
                found = None
            else:
                first = result.stdout.splitlines()[0] if result.stdout else '?'
                print(f"Found pandoc: {found} ({first})")
        except (OSError, subprocess.TimeoutExpired):
            found = None

    _PANDOC_PATH.append(found)
    return found


# `\begin{comment}...\end{comment}` (comment.sty, verbatim.sty) hides its
# contents as completely as a `%` does — LaTeX typesets none of it, and pandoc
# correctly drops it. What reads flat.tex afterwards did not: Maynard leaves a
# 54-line block containing `\section{Motivation}`, so the heading list came
# back with eleven entries against the translation's ten and the build gave up
# on section numbering entirely — "refusing to guess" about a section the
# author had already deleted. The same block also hides two theorems and their
# labels, which would have numbered every theorem after them one too high.
_COMMENT_ENV_RE = re.compile(
    r'\\begin\s*\{comment\}.*?\\end\s*\{comment\}', re.DOTALL)


# A definition is not an occurrence. `\renewcommand{\beginappendix}{%
# \clearpage\appendix\section{Appendix}}` puts a `\appendix` in the preamble,
# and the walks that letter an appendix read it as the start of one: a paper
# whose appendix begins two thirds of the way down had everything after the
# definition lettered, so its BODY sections 4, 5.1 and 5.3 printed D, E.1 and
# E.3 and seven cross-references disagreed with the printed paper.
#
# The same trap is open to every other structural walk -- a `\begin{figure}`
# or `\begin{table}` in a definition counts once per definition, not once per
# use -- which is why this is masked for all of them rather than patched into
# the appendix readers one at a time. `theorem_declarations` and
# `read_one_argument_macros` exist to READ definitions, and say so by asking
# for them.
_DEF_HEAD_RE = re.compile(
    r'\\(?:new|renew|provide)command\*?(?![A-Za-z])'
    r'|\\DeclareRobustCommand\*?(?![A-Za-z])'
    r'|\\(?:new|renew)environment\*?(?![A-Za-z])'
    r'|\\[gex]?def(?![A-Za-z])')
_DEF_BODIES = 2         # \newenvironment has a begin AND an end body
_DEF_SCAN_LIMIT = 400   # a definition head is short; do not run off the file


def _blank_span(text):
    """The same text with nothing in it: length and line breaks preserved, so
    anything downstream that reports a position still reports the right one."""
    return ''.join('\n' if ch == '\n' else ' ' for ch in text)


_COUNTER_FORMAT_RE = re.compile(r'\\?the[a-zA-Z@]*\Z')


def mask_macro_definitions(tex):
    r"""Blank the body of every macro and environment definition.

    Except a counter format. `\def\theequation{\thesection.\arabic{equation}}`
    is not a wrapper holding content for later use; it is how a paper DECLARES
    that its equations are numbered within sections, and `read_counter_parents`
    exists to read exactly that. Blanking it numbered equations 1, 2, 3 in a
    paper that prints 1.1, 1.2, 2.1.
    """
    cursor, pieces = 0, []
    for m in _DEF_HEAD_RE.finditer(tex):
        if m.start() < cursor:
            continue
        head = m.group(0)
        i = m.end()
        limit = min(len(tex), i + _DEF_SCAN_LIMIT)
        # The name: `{\foo}`, `{foo}` or a bare `\foo`, then any [n] or
        # [default] arguments, then `\def`'s delimited parameters.
        name_start = i
        while i < limit and tex[i] not in '{':
            if tex[i] == '[':
                close = tex.find(']', i, limit)
                if close < 0:
                    break
                i = close + 1
                continue
            i += 1
        if i >= limit or tex[i] != '{':
            continue
        # `\def\theequation{...}` names itself before the brace, so the first
        # group IS the body. `\newcommand{\foo}{...}` puts the name in that
        # group, and it has to be CONSUMED -- peeking at it and then blanking
        # one group from here blanks the name and leaves the body standing,
        # which is a mask that does nothing and corrupts the definition.
        name = tex[name_start:i].strip()
        if not name:
            name, i = _brace_group(tex, i)
            name = (name or '').strip()
        if _COUNTER_FORMAT_RE.match(name):
            continue
        while True:                              # [n] and [default]
            j = i
            while j < len(tex) and tex[j] in ' \t\n':
                j += 1
            if j < len(tex) and tex[j] == '[':
                close = tex.find(']', j)
                if close < 0:
                    break
                i = close + 1
                continue
            break
        bodies = _DEF_BODIES if 'environment' in head else 1
        start = i
        for _ in range(bodies):
            while i < len(tex) and tex[i] in ' \t\n':
                i += 1
            if i >= len(tex) or tex[i] != '{':
                break
            _, i = _brace_group(tex, i)
        if i <= start:
            continue
        pieces.append(tex[cursor:start])
        pieces.append(_blank_span(tex[start:i]))
        cursor = i
    pieces.append(tex[cursor:])
    return ''.join(pieces) if pieces else tex


def strip_tex_comments(text, keep_definitions=False):
    r"""Remove % comments and `comment` environments, honouring \\% escapes.

    Macro definition BODIES are blanked too, for the reason above. Pass
    `keep_definitions=True` when the definitions are what you came to read.
    """
    text = _COMMENT_ENV_RE.sub('', text)
    if not keep_definitions:
        text = mask_macro_definitions(text)
    out = []
    for line in text.split('\n'):
        i, n = 0, len(line)
        while i < n:
            if line[i] == '\\' and i + 1 < n:
                i += 2
                continue
            if line[i] == '%':
                line = line[:i]
                break
            i += 1
        out.append(line)
    return drop_false_conditionals('\n'.join(out))


# `\iffalse ... \fi` is the other way an author deletes a passage without
# deleting it, and TeX skips it as surely as a `comment` environment. pandoc
# honours it, so the translated text never carried AdamX's disabled
# "Strongly Convex Losses" subsection -- but every reader that counts from
# flat.tex did: the heading list gained a section the paper does not print,
# and the figures inside two such blocks pushed the next figure to 3 where
# the paper prints 1. Those counts are the numbers the book prints.
#
# Skipping follows TeX: every `\if...` met inside the block opens a level
# that its own `\fi` closes, and an `\else` at the outer level ends the
# skipped part, so what follows it is kept. Three names look like
# conditionals and are not: `\iff` is the maths arrow, `\ifthenelse` is a
# LaTeX command with brace arguments, and `\newif\ifdraft` DEFINES a
# conditional rather than opening one. A block with no closing `\fi` is left
# as it was: deleting from an unmatched `\iffalse` to the end of the paper is
# the one mistake worse than keeping it. Newlines inside a dropped block are
# kept, so line positions downstream do not move.
_COND_TOKEN_RE = re.compile(r'\\(iffalse|if[a-zA-Z@]*|fi|else)(?![a-zA-Z@])')
_NOT_A_CONDITIONAL = frozenset(('iff', 'ifthenelse'))


def _opens_a_conditional(text, token):
    name = token.group(1)
    if name in _NOT_A_CONDITIONAL:
        return False
    return not text[max(0, token.start() - 16):token.start()].rstrip().endswith(
        '\\newif')


def drop_false_conditionals(text):
    r"""Remove what `\iffalse ... [\else] ... \fi` tells TeX to skip."""
    out, pos = [], 0
    while True:
        start = None
        for token in _COND_TOKEN_RE.finditer(text, pos):
            if token.group(1) == 'iffalse':
                start = token
                break
        if start is None:
            out.append(text[pos:])
            return ''.join(out)
        depth, else_at, end = 0, None, None
        for token in _COND_TOKEN_RE.finditer(text, start.end()):
            name = token.group(1)
            if name == 'fi':
                if depth == 0:
                    end = token
                    break
                depth -= 1
            elif name == 'else':
                if depth == 0 and else_at is None:
                    else_at = token
            elif _opens_a_conditional(text, token):
                depth += 1
        if end is None:
            out.append(text[pos:])
            return ''.join(out)
        out.append(text[pos:start.start()])
        if else_at is None:
            out.append('\n' * text.count('\n', start.start(), end.end()))
        else:
            out.append('\n' * text.count('\n', start.start(), else_at.end()))
            out.append(text[else_at.end():end.start()])
        pos = end.end()
# \caption, plus \captionof{figure} for a float built out of a plain box.
_CAPTION_CMD_RE = re.compile(
    r'\\caption(?:of)?\s*(?:\{(?:figure|table)\}\s*)?(?:\[[^\]]*\])?\s*\{')


# The commented tail of a line, for counting braces that TeX never sees.
_COMMENT_LINE_RE = re.compile(r'(?<!\\)%[^\n]*')

# `\fontsize{6pt}{1pt}\selectfont{system}` — a size switch with its argument.
# It sets type and shows nothing of its own, but pandoc's tabular reader loses
# the ROW it opens: ResNet's per-class detection table converted "successfully"
# and reached the page with its header and every class column gone. Keep the
# argument, drop the switch. The trailing group is optional because the switch
# is as often used bare, to change size for the rest of the cell.
# pandoc hands it over as a backticked raw inline, so the BACKTICKS have to go
# with it. Removing the command alone left `` on the page — two stray marks
# the empty-span cleanup could not take, because it only lifts a pair standing
# alone between spaces and this one had text hard against it.
_FONTSIZE_RE = re.compile(
    r'[ \t]*`?\\fontsize\s*\{[^{}]*\}\s*\{[^{}]*\}\s*\\selectfont\s*'
    r'(?:\{((?:[^{}]|\{[^{}]*\})*)\})?[ \t]*`?(?:\{=[a-z]+\})?')


def _in_latex_comment(text, pos):
    """Is `pos` on the commented-out part of its line?

    `float_units` takes comment-stripped text and so never had to ask. The
    passes that read the MERGED MARKDOWN cannot strip: the raw floats have to
    reach pandoc byte for byte. They need the question answered in place.

    A `%` opens a comment unless it is escaped, and a backslash escapes only
    when it is not itself escaped -- so what decides is whether the run of
    backslashes in front of the `%` is even.
    """
    line_start = text.rfind('\n', 0, pos) + 1
    scan = line_start
    while True:
        at = text.find('%', scan, pos)
        if at < 0:
            return False
        back = at
        while back > line_start and text[back - 1] == '\\':
            back -= 1
        if (at - back) % 2 == 0:
            return True
        scan = at + 1


def _balanced_group(text, open_at):
    """Index just past the `{...}` group that starts at open_at, or -1."""
    depth = 0
    for i in range(open_at, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return i + 1
    return -1


def _brace_group(text, start):
    """(content, index after the group) for the `{...}` at `text[start]`."""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return text[start + 1:i], i + 1
    return None, start

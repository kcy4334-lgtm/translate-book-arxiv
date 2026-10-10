# -*- coding: utf-8 -*-
r"""A plain-TeX `\halign` table, rewritten as the `tabular` pandoc reads.

The A&A and Planck templates build every table this way:

    \setbox\tablebox=\vbox{
       \newdimen\digitwidth \setbox0=\hbox{\rm 0} \digitwidth=\wd0
       \catcode`*=\active \def*{\kern\digitwidth}
       \halign{\hbox to 1.0in{#\leaderfil}\tabskip 1.2em&
       \hfil#\hfil\tabskip 0pt\cr
       \noalign{\doubleline}
       \omit\hfil Parameter\hfil& Value\cr
       \noalign{\vskip 3pt\hrule\vskip 5pt}
       $H_0$& $67.3 \pm 1.2*$\cr
       ...}}
    \endPlancktablewide

pandoc reads none of it. planck has eight such tables, and with them in the
source pandoc stopped the whole conversion; with the conversion repaired,
the book would have had none of the eight.

The template line says how many columns there are and how each is set:
`\hfil#\hfil` centred, `#\hfil` left, `\hfil#` right, `$#$` a formula.
`\cr` ends a row, `\noalign{...\hrule...}` draws a rule, `\omit` drops the
template for one cell, `\multispan{n}` joins n of them. Characters made
active for alignment (`*` and `!` above, each a fixed-width kern) are
spacing and go.
"""
import re

from build_common import _balanced_group

_HALIGN_RE = re.compile(r'\\halign\s*(?:to\s*[^{]*)?\{')
_VBOX_RE = re.compile(r'\\setbox\s*\\[A-Za-z@]+\s*=?\s*\\vbox\s*\{')
_ACTIVE_RE = re.compile(r'\\catcode\s*`\\?(.)\s*=\s*\\active')
_COMMENT_RE = re.compile(r'(?<!\\)%[^\n]*')
_ENDTABLE_RE = re.compile(
    r'(?:\s|(?<!\\)%[^\n]*)*\\endPlancktable(?:wide)?(?![A-Za-z])')
_CR_RE = re.compile(r'\\cr(?![A-Za-z])')
_NOALIGN_RE = re.compile(r'\s*\\noalign\s*\{')
_OMIT_RE = re.compile(r'^\s*\\omit(?![A-Za-z])')
_MULTISPAN_RE = re.compile(r'^\s*\\multispan\s*\{?\s*(\d+)\s*\}?')
_SPACING_RE = re.compile(
    r'\\(?:hfil{1,3}|hss|leaderfil|strut|relax|hidewidth)(?![A-Za-z])'
    r'|\\(?:hskip|kern)\s*-?[\d.]+\s*(?:pt|em|ex|mm|cm|in)')


def halign_tables(tex):
    """Every `\\halign` table as a tabular. (tex, count)."""
    count = 0
    while True:
        found = _next_table(tex)
        if not found:
            return tex, count
        start, stop, tabular = found
        tex = tex[:start] + tabular + tex[stop:]
        count += 1


def _next_table(tex, at=0):
    """(start, stop, tabular) for the next convertible table, or None."""
    for m in _HALIGN_RE.finditer(tex, at):
        close = _balanced_group(tex, m.end() - 1)
        if close < 0:
            continue
        inner = tex[m.end():close - 1]
        first = _CR_RE.search(inner)
        # `##` is a template inside a macro DEFINITION (planck's `\ga`
        # stacks `>` over `\sim` with one); that is a symbol, not a table.
        if not first or '##' in inner[:first.start()]:
            continue
        start, stop, active = m.start(), close, set()
        box = _enclosing_vbox(tex, m.start())
        if box:
            box_start, box_stop = box
            setup = tex[box_start:m.start()]
            active = set(_ACTIVE_RE.findall(setup))
            # The box holds the table and nothing else (a `% close halign`
            # comment aside): the box, and the macro that prints it, go too.
            if not _COMMENT_RE.sub('', tex[close:box_stop - 1]).strip():
                start, stop = box_start, box_stop
                end = _ENDTABLE_RE.match(tex, stop)
                if end:
                    stop = end.end()
        tabular = _as_tabular(inner, active)
        if tabular:
            return start, stop, tabular
    return None


def _enclosing_vbox(tex, at):
    """(start, end) of the `\\setbox..=\\vbox{` group holding `at`, or None."""
    best = None
    for m in _VBOX_RE.finditer(tex, 0, at):
        close = _balanced_group(tex, m.end() - 1)
        if close > at:
            best = (m.start(), close)
    return best


def _split_top(text, pattern):
    """`text` cut at each match of `pattern` outside braces."""
    pieces, depth, start, i = [], 0, 0, 0
    while i < len(text):
        ch = text[i]
        if ch == '\\':
            m = pattern.match(text, i)
            if m and depth == 0:
                pieces.append(text[start:i])
                start = i = m.end()
                continue
            i += 2
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth = max(0, depth - 1)
        elif ch == '&' and depth == 0 and pattern is _AMP:
            pieces.append(text[start:i])
            start = i + 1
        i += 1
    pieces.append(text[start:])
    return pieces


_AMP = re.compile(r'(?!)')        # a marker: split on top-level `&`


def _columns(template):
    """[(align, math)] per template column."""
    out = []
    for col in _split_top(template, _AMP):
        col = re.sub(r'\\tabskip\s*=?\s*-?[\d.]+\s*(?:pt|em|ex|mm|cm|in)', '', col)
        math = bool(re.search(r'\$\s*#\s*\$', col))
        hole = col.find('#')
        before, after = col[:hole], col[hole + 1:]
        left = bool(re.search(r'\\hfil|\\hss', before))
        right = bool(re.search(r'\\hfil|\\hss|\\leaderfil', after))
        if left and right:
            align = 'c'
        elif left:
            align = 'r'
        else:
            align = 'l'
        out.append((align, math))
    return out


def _as_tabular(inner, active):
    # A row is written out on one line, so a `% Template goes here.` left in
    # it would comment out the rest of the row.
    inner = _COMMENT_RE.sub('', inner)
    rows_raw = _split_top(inner, _CR_RE)
    template, rows_raw = rows_raw[0], rows_raw[1:]
    columns = _columns(template)
    if not columns:
        return None
    lines = []
    for raw in rows_raw:
        rules, raw = _take_noaligns(raw)
        lines.extend(rules)
        if not raw.strip():
            continue
        cells, used = [], 0
        for cell in _split_top(raw, _AMP):
            span = _MULTISPAN_RE.match(cell)
            if span:
                n = int(span.group(1))
                text = _clean(cell[span.end():], active)
                cells.append(text if n == 1 else
                             '\\multicolumn{%d}{c}{%s}' % (n, text))
                used += n
                continue
            omit = _OMIT_RE.match(cell)
            if omit:
                cell = cell[omit.end():]
            text = _clean(cell, active)
            if used < len(columns) and columns[used][1] and not omit \
                    and text:
                text = '$%s$' % text
            cells.append(text)
            used += 1
        lines.append(' & '.join(cells) + ' \\\\')
    spec = ''.join(align for align, _math in columns)
    return ('\\begin{tabular}{%s}\n%s\n\\end{tabular}'
            % (spec, '\n'.join(lines)))


def _take_noaligns(raw):
    """(rule lines, rest) for the `\\noalign{...}`s that open a row."""
    rules = []
    while True:
        m = _NOALIGN_RE.match(raw)
        if not m:
            return rules, raw
        close = _balanced_group(raw, m.end() - 1)
        if close < 0:
            return rules, raw
        body = raw[m.end():close - 1]
        n = len(re.findall(r'\\hrule(?![A-Za-z])', body))
        n += 2 * len(re.findall(r'\\doubleline(?![A-Za-z])', body))
        rules.extend(['\\hline'] * n)
        raw = raw[close:]


def _clean(cell, active):
    cell = _SPACING_RE.sub('', cell)
    cell = re.sub(r'\\quad(?![A-Za-z])|\\qquad(?![A-Za-z])', ' ', cell)
    for ch in active:
        cell = re.sub(r'(?<!\\)' + re.escape(ch), '', cell)
    cell = re.sub(r'\$\s*\$', '', cell)
    return ' '.join(cell.split())

# -*- coding: utf-8 -*-
r"""A `tabular` inside a formula, rewritten as the `array` a formula can hold.

planck lists each result as a brace over a two-column list:

    \begin{equation}
    \omega_\mathrm{b} = \left\{ \mathrm{\begin{tabular}{ll}
    $0.02222^{+0.00045}_{-0.00043}$ & \textit{Planck}\ {\rm TT}{+}{\rm lowP}, \\
    ...
    \end{tabular}} \right.
    \end{equation}

LaTeX typesets that: the tabular is a box, and its cells switch back to
text. texmath has no tabular in a formula. Worse, the table expander found
all seven of these, turned each into an HTML `<table>` in the middle of a
`$$...$$`, and the HTML writer dropped them: planck's build stopped with
"7 table(s) ... but the HTML has only 0".

An `array` is the formula's own table. Each cell's formula parts go in as
they are; its text parts become `\text{...}`, and the italic and upright
switches become `\textit{...}` and `\text{...}` -- texmath reads those in a
formula, but not `\textit` nested inside `\text`, so the runs are kept
side by side rather than nested.
"""
import re

import latex_rows
from build_common import _balanced_group

# Where a tabular counts as inside a formula.
# `\[` only where it opens a display: in `\\[2pt]` it is the spacing argument
# of a line break, and 2609.11801's author block, read as a display holding
# its results table, had that table rewritten as an array.
_MATH_BLOCK_RE = re.compile(
    r'\\begin\{(equation|align|gather|multline|eqnarray|displaymath)(\*?)\}'
    r'.*?\\end\{\1\2\}'
    r'|(?<!\\)\$\$.*?(?<!\\)\$\$|(?<!\\)\\\[.*?(?<!\\)\\\]', re.DOTALL)
# `tabular*` takes its width first; the width goes, the columns stay.
_TABULAR_RE = re.compile(
    r'\\begin\{tabular(?:\*\}\s*\{[^{}]*\}|\})\s*(?:\[[^\]]*\]\s*)?(?=\{)')
# A box around the tabular, there only to leave math mode.
_WRAPPER_RE = re.compile(r'\\(?:mathrm|mbox|hbox|text|textrm)\s*\{\s*$')
_FONT_COMMANDS = {'textit': 'textit', 'emph': 'textit', 'textbf': 'textbf',
                  'textrm': 'text', 'textsf': 'text', 'texttt': 'texttt',
                  'text': 'text', 'mbox': 'text'}
_FONT_SWITCHES = {'rm': 'text', 'it': 'textit', 'bf': 'textbf',
                  'sl': 'textit', 'em': 'textit', 'tt': 'texttt',
                  'sf': 'text'}
_MATH_SPACES = (',', '!', ';', ':', ' ')


def tabulars_in_math_as_arrays(tex):
    """Every tabular inside a display formula, as an array. (tex, count)."""
    count = 0
    pieces, cursor = [], 0
    for block in _MATH_BLOCK_RE.finditer(tex):
        text = block.group(0)
        if '\\begin{tabular' not in text:
            continue
        rewritten, n = _rewrite_block(text)
        if not n:
            continue
        pieces.append(tex[cursor:block.start()])
        pieces.append(rewritten)
        cursor = block.end()
        count += n
    pieces.append(tex[cursor:])
    return ''.join(pieces), count


def _rewrite_block(text):
    count = 0
    while True:
        m = _TABULAR_RE.search(text)
        if not m:
            return text, count
        spec_end = _balanced_group(text, m.end())
        if spec_end < 0:
            return text, count
        spec = text[m.end() + 1:spec_end - 1]
        body = latex_rows.env_body(text, spec_end, 'tabular')
        end = spec_end + len(body)
        close = re.compile(r'\\end\s*\{tabular\*?\}').match(text, end)
        if not close:
            return text, count
        array = '\\begin{array}{%s}%s\\end{array}' % (
            _array_spec(spec), _array_body(body))
        start, stop = m.start(), close.end()
        wrapper = _WRAPPER_RE.search(text, 0, start)
        after = re.match(r'\s*\}', text[stop:])
        if wrapper and after:
            start, stop = wrapper.start(), stop + after.end()
        text = text[:start] + array + text[stop:]
        count += 1


def _array_spec(spec):
    """The column letters and rules an array takes; widths become `l`."""
    out, i = [], 0
    while i < len(spec):
        ch = spec[i]
        if ch in '@!>< ':
            # `@{...}` and friends carry an argument; the array does not
            # need the spacing they set.
            j = spec.find('{', i)
            if ch in '@!><' and j == i + 1:
                end = _balanced_group(spec, j)
                i = end if end > 0 else len(spec)
                continue
            i += 1
            continue
        if ch in 'pmbwX':
            j = i + 1
            if j < len(spec) and spec[j] == '{':
                end = _balanced_group(spec, j)
                i = end if end > 0 else len(spec)
            else:
                i += 1
            out.append('l')
            continue
        if ch in 'lcr|':
            out.append(ch)
        i += 1
    return ''.join(out) or 'l'


def _array_body(body):
    rows = []
    for row in latex_rows.split_rows(body):
        if not row.strip():
            continue
        rows.append(' & '.join(_cell_as_math(c) for c in _split_cells(row)))
    return ' \\\\ '.join(rows)


def _split_cells(row):
    cells, depth, start, i = [], 0, 0, 0
    while i < len(row):
        ch = row[i]
        if ch == '\\':
            i += 2
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth = max(0, depth - 1)
        elif ch == '&' and depth == 0:
            cells.append(row[start:i])
            start = i + 1
        i += 1
    cells.append(row[start:])
    return cells


def _cell_as_math(cell):
    """One tabular cell, written for an array."""
    out, run = [], []

    def flush():
        text = ''.join(run)
        run.clear()
        if text.strip():
            out.append('\\text{%s}' % text)
        elif text:
            out.append('\\ ')

    cell = cell.strip()
    i = 0
    while i < len(cell):
        ch = cell[i]
        if ch == '$':
            end = cell.find('$', i + 1)
            if end < 0:
                run.append(cell[i:])
                break
            flush()
            out.append(cell[i + 1:end])
            i = end + 1
            continue
        if ch == '\\':
            m = re.match(r'\\([A-Za-z]+)\s*', cell[i:])
            if m and m.group(1) in _FONT_COMMANDS \
                    and cell[i + m.end():i + m.end() + 1] == '{':
                close = _balanced_group(cell, i + m.end())
                if close > 0:
                    flush()
                    inner = cell[i + m.end() + 1:close - 1]
                    out.append('\\%s{%s}' % (_FONT_COMMANDS[m.group(1)],
                                             _plain(inner)))
                    i = close
                    continue
            if cell[i + 1:i + 2] in _MATH_SPACES:
                flush()
                out.append(cell[i:i + 2])
                i += 2
                continue
            if cell[i + 1:i + 2] in '%&#_{}':
                run.append(cell[i:i + 2])        # still escaped in \text
                i += 2
                continue
            if m:
                # Anything else is the formula's to read, with its brace
                # arguments: planck's `\datalabel{\planckTT}` is the paper's
                # own macro, and pandoc expands it inside the formula.
                flush()
                j = i + len(m.group(0))
                while j < len(cell) and cell[j] == '{':
                    end = _balanced_group(cell, j)
                    if end < 0:
                        break
                    j = end
                out.append(cell[i:j].rstrip() + ' ')
                i = j
                continue
            run.append(ch)
            i += 1
            continue
        if ch == '{':
            close = _balanced_group(cell, i)
            if close < 0:
                run.append(ch)
                i += 1
                continue
            inner = cell[i + 1:close - 1]
            switch = re.match(r'\\([A-Za-z]+)(?![A-Za-z])\s*', inner)
            if switch and switch.group(1) in _FONT_SWITCHES:
                flush()
                out.append('\\%s{%s}' % (_FONT_SWITCHES[switch.group(1)],
                                         _plain(inner[switch.end():])))
            else:
                flush()
                out.append(_cell_as_math(inner))
            i = close
            continue
        if ch == '~':
            flush()
            out.append('\\ ')
            i += 1
            continue
        run.append(ch)
        i += 1
    flush()
    return ''.join(out)


def _plain(text):
    """The words of a run inside a font command, its own markup removed."""
    text = re.sub(r'\\[A-Za-z]+\s*', '', text.replace('\\ ', ' ').replace('~', ' '))
    return re.sub(r'(?<!\\)[{}]', '', text)

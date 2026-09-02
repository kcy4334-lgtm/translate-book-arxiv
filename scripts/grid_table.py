# -*- coding: utf-8 -*-
r"""Keep a pandoc grid table's column spans through later text edits.

A grid table carries its spans in GEOMETRY, not in markup. A cell spans two
columns when the boundary between them carries no `|` in that row -- and no
`+` in the rules that close it:

    +------+------+------+
    | A    | BC          |
    +------+------+-------+

The build edits cell text after the table is written: numbering captions,
substituting `표 5` for `(tab:x)`, translating a header. Every edit moves the
`|` characters, the rules stop describing the cells, and pandoc -- without
complaining -- reads a table with no spans at all. Three books printed
`\multicolumn{6}{c}{Gemma 2 2B}` sitting over ONE column, and AlphaQ's
table 4 put `DeepSeekV2-Lite` over Mixtral's own accuracy column, a header
that mislabels the numbers beneath it.

So the geometry is CAPTURED while it is still true and RE-APPLIED after the
edits. Two earlier attempts failed and are worth remembering: reconstructing
the spans by matching each drifted `|` to its nearest boundary recovered four
of CafeQ's and destroyed three of AlphaQ's -- a guess that silently drops a
span is the same defect in a new coat. And measuring in display width found
nothing to capture at all: pandoc lays these tables out by CHARACTER index,
so a Hangul cell is padded to a count `len()` agrees with and East-Asian
width does not.

The only fact used here is that an edit changes cell TEXT, never the number
of dividers: the k-th cell of a row is still the k-th cell.

NOT WIRED IN, on purpose. `table` floats now bypass pandoc's table writer
entirely and are rendered by merge_and_build, so the pipeline no longer
produces a grid table whose spans could drift: measured across the four books,
`grid_tables_to_pipe` rewrote none. This module is kept, unimported, against
the paper that does produce one — a grid table with spans is a shape the
corpus simply has not shown yet. Wire it in at that point; do not read the
absence of callers as dead code.
"""
import re

_BLOCK_LINE_RE = re.compile(r'^[+|]')
_RULE_RE = re.compile(r'^\+[-=+:]*\+[ \t]*$')


def _marks(line, ch):
    return [i for i, c in enumerate(line) if c == ch]


def _blocks(lines):
    """(start, end) of each run of grid lines, 3 lines or longer."""
    out, i = [], 0
    while i < len(lines):
        if not _BLOCK_LINE_RE.match(lines[i]):
            i += 1
            continue
        j = i
        while j < len(lines) and _BLOCK_LINE_RE.match(lines[j]):
            j += 1
        if j - i >= 3:
            out.append((i, j))
        i = j
    return out


def capture(md_text):
    """Geometry of every grid table, in document order.

    Per table: (n_columns, [(is_rule, [boundary indices this line marks])]).
    `None` for a table whose geometry does not parse, so re-apply leaves it
    exactly as it is rather than improvising.
    """
    lines = md_text.split('\n')
    out = []
    for start, end in _blocks(lines):
        block = lines[start:end]
        bounds = sorted({m for l in block if _RULE_RE.match(l)
                         for m in _marks(l, '+')})
        if len(bounds) < 2:
            out.append(None)
            continue
        index = {b: k for k, b in enumerate(bounds)}
        layout, ok = [], True
        for line in block:
            rule = bool(_RULE_RE.match(line))
            marks = _marks(line, '+' if rule else '|')
            if len(marks) < 2 or marks[0] != 0 or marks[-1] != bounds[-1]:
                ok = False
                break
            try:
                layout.append((rule, [index[m] for m in marks]))
            except KeyError:
                ok = False
                break
        out.append((len(bounds) - 1, layout) if ok else None)
    return out


def _cells(line):
    parts = line.split('|')
    return [p for p in parts[1:-1]] if len(parts) >= 3 else []


def _rebuild(block, geometry):
    ncol, layout = geometry
    if len(layout) != len(block):
        return None
    parsed = []
    for line, (rule, marks) in zip(block, layout):
        if rule != bool(_RULE_RE.match(line)):
            return None
        if rule:
            parsed.append((True, None, marks))
            continue
        cells = _cells(line)
        if len(cells) != len(marks) - 1:
            return None                 # an edit changed the divider count
        parsed.append((False, [c.strip() for c in cells], marks))

    widths = [3] * ncol
    for is_rule, cells, marks in parsed:                 # single columns win
        if is_rule:
            continue
        for k, text in enumerate(cells):
            if marks[k + 1] - marks[k] == 1:
                widths[marks[k]] = max(widths[marks[k]], len(text) + 2)
    for is_rule, cells, marks in parsed:                 # then the spans
        if is_rule:
            continue
        for k, text in enumerate(cells):
            a, b = marks[k], marks[k + 1]
            if b - a == 1:
                continue
            need, have = len(text) + 2, sum(widths[a:b]) + (b - a - 1)
            if need > have:
                share, rest = divmod(need - have, b - a)
                for j in range(a, b):
                    widths[j] += share + (1 if j - a < rest else 0)

    out = []
    for (is_rule, cells, marks), line in zip(parsed, block):
        width_of = lambda a, b: sum(widths[a:b]) + (b - a - 1)
        if is_rule:
            fill = '=' if '=' in line else '-'
            aligned = ':' in line
            seg = ['+']
            for k in range(len(marks) - 1):
                w = width_of(marks[k], marks[k + 1])
                seg.append((':' + fill * (w - 1) if aligned and w > 1
                            else fill * w) + '+')
            out.append(''.join(seg))
            continue
        seg = ['|']
        for k, text in enumerate(cells):
            w = width_of(marks[k], marks[k + 1])
            body = ' ' + text
            seg.append(body + ' ' * max(0, w - len(body)) + '|')
        out.append(''.join(seg))
    return out


def reapply(md_text, geometries):
    """Re-emit each grid table with its captured spans. (text, fixed)."""
    lines = md_text.split('\n')
    blocks = _blocks(lines)
    if len(blocks) != len(geometries):
        return md_text, 0          # the document changed shape; do nothing
    out, cursor, fixed = [], 0, 0
    for (start, end), geometry in zip(blocks, geometries):
        out.extend(lines[cursor:start])
        cursor = end
        block = lines[start:end]
        rebuilt = _rebuild(block, geometry) if geometry else None
        if rebuilt is None or rebuilt == block:
            out.extend(block)
        else:
            out.extend(rebuilt)
            fixed += 1
    out.extend(lines[cursor:])
    return '\n'.join(out), fixed


def normalize_grid_tables(md_text, geometries=None):
    """Capture from this text and re-apply to it."""
    return reapply(md_text, geometries if geometries is not None
                   else capture(md_text))

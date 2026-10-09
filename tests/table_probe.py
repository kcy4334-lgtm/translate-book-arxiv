#!/usr/bin/env python3
r"""
table_probe.py - Every table in the built book, against the ORIGINAL LaTeX.

    python tests/table_probe.py <temp_dir> --lang ko [--strict]

Not named test_*.py: it needs a built temp dir, so `unittest discover` must
not collect it.

Nothing in this pipeline compared a table's CONTENT to the source. The two
checks that existed both look elsewhere:

  * `source_probe.py` does read the original PDF -- and counts numbers.
    Section numbers, equation numbers, float numbers, reference numbers. Not
    one cell.
  * `verify_tables.py` compares each table against a SNAPSHOT of our own
    files. If the conversion already dropped a value before the snapshot was
    taken, the snapshot records the damage and the check passes forever.

CafeQ shipped with twelve values missing from table 1 and six from table 5,
while the prose went on citing them, and both checks stayed green. Every
table defect in this project was found by a person reading the page.

This one asks the question those two do not: does the built table still say
what `flat.tex` says?

  columns      the colspec's column count against the widest rendered row,
               counting colspan
  rows         `\\` row terminators against <tr>
  values       the ordered multiset of numeric cells, both directions
  group spans  each `\multicolumn{N}` against a <th colspan="N">
  row labels   the first cell of each body row, present and non-empty

A raw-LaTeX table is built from the same LaTeX this probe reads, so agreement
is expected there. The point is the case where it does NOT agree.
"""
import argparse
import io
import os
import re
import sys
import unicodedata
from collections import Counter

SCRIPT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          'scripts')
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import latex_rows                                                # noqa: E402


# A CLI prints, and what it prints may carry the book's text. A Windows
# console under a non-UTF-8 locale then raises UnicodeEncodeError and the
# command dies -- which stayed hidden while every caller happened to set
# PYTHONIOENCODING for it.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError, OSError):
        pass

# Not `array`: that is a matrix inside a formula. Shor's three were counted
# as tables the book had lost.
TABULAR_RE = re.compile(
    r'\\begin\{(tabular\*?|tabularx|tabulary|longtable)\}(.*?)\\end\{\1\}',
    re.DOTALL)
TABLE_EL_RE = re.compile(r'(?s)<table\b.*?</table>')
ROW_RE = re.compile(r'(?s)<tr\b.*?</tr>')
CELL_RE = re.compile(r'(?s)<(t[hd])\b([^>]*)>(.*?)</\1>')
COLSPAN_RE = re.compile(r'colspan="(\d+)"')
MULTICOL_RE = re.compile(r'\\multicolumn\s*\{\s*(\d+)\s*\}')
NUMBER_RE = re.compile(r'\d+(?:\.\d+)?')
# A rule's trim, widths included: PaLM's `\cmidrule(l{3pt}r{3pt}){2-3}`.
_TRIM = r'(?:\((?:[^(){}]|\{[^{}]*\})*\))?'
# Comment out to the end of line, but `\%` is a printed percent sign.
COMMENT_RE = re.compile(r'(?<!\\)%[^\n]*')


def read(path):
    return io.open(path, encoding='utf-8', errors='replace').read()


def colspec_columns(spec):
    r"""Column count of `{l cc |r p{2cm} *{3}{c}}`."""
    # Braces nest in here: ViT's `!{\color{lightgray}\vline}` stopped at the
    # first `}` and left `lightgray` behind to be counted as columns.
    spec = re.sub(r'[@!<>]\{(?:[^{}]|\{[^{}]*\})*\}', '', spec)

    def expand(m):
        return m.group(2) * int(m.group(1))

    prev = None
    while prev != spec:
        prev = spec
        spec = re.sub(r'\*\s*\{\s*(\d+)\s*\}\s*\{([^{}]*)\}', expand, spec)
    # A defined type takes a width too: GAN's `L{1in}` counted its `in` as
    # two more columns, 13 for a five-column table.
    spec = re.sub(r'[A-Za-z]\{[^{}]*\}', 'p', spec)   # p{..} m{..} L{..}
    # Every letter left is a column, the paper's own types included: ViT
    # declares `\newcolumntype{C}` and its 22-column table counted 2.
    spec = re.sub(r'\\[A-Za-z]+', '', spec)
    return len(re.findall(r'[A-Za-z]', spec))


def _matching_brace(text, start):
    r"""Index of the `}` closing the `{` at `start`, or -1."""
    depth, i = 0, start
    while i < len(text):
        if text[i] == '\\':
            i += 2                  # an escaped brace is a character
            continue
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def tabular_units(tex):
    r"""(colspec_columns, body) for each tabular, in document order.

    The colspec has to be read to its matching brace, not to the first one:
    `{l*{11}{c}}` stops at the `}` of `{11}` and counts three columns for a
    table that renders twelve. Ten of SINQ's nineteen tables reported a
    column-count mismatch that way, which is ten reasons to stop reading a
    check that had nothing wrong to say.
    """
    out = []
    for kind, body in _outer_tabulars(tex):
        # A macro's template, not a table: ResNet's `\tabincell` is
        # `\begin{tabular}{@{}#1@{}}#2\end{tabular}`. Counted, it was table 1,
        # and every one of the book's 19 tables was compared with the source
        # table before it -- 40 findings on a correct book.
        # Unescaped: BERT's leaderboard prints `\#1 Ensemble`.
        if re.search(r'(?<!\\)#\d', body):
            continue
        pos = re.match(r'\s*(?:\[[^\]]*\])?\s*', body).end()
        # `tabular*` and `tabularx` take a width argument before the colspec.
        if kind in ('tabular*', 'tabularx'):
            if pos < len(body) and body[pos] == '{':
                close = _matching_brace(body, pos)
                if close < 0:
                    continue
                pos = close + 1
                pos += re.match(r'\s*(?:\[[^\]]*\])?\s*', body[pos:]).end()
        if pos >= len(body) or body[pos] != '{':
            continue
        close = _matching_brace(body, pos)
        if close < 0:
            continue
        cells = body[close + 1:]
        # A tabular that only lays out graphics is a figure, and the build
        # unwraps it (`unwrap_graphics_tabulars`). ViT's Figure 1 is one; left
        # in, every table after it was compared with the tabular before it,
        # and a correct book drew 29 findings.
        if '\\includegraphics' in cells and not _LAYOUT_LEFTOVER_RE.sub(
                '', _GRAPHIC_RE.sub('', cells)):
            continue
        out.append((colspec_columns(body[pos + 1:close]), cells))
    return out


# Source LaTeX never typesets. 2609.11867 keeps an older version of its table
# inside `\begin{comment}`, and it was counted as a table the book had lost.
_SKIPPED_RE = re.compile(
    r'(?s)\\begin\{comment\}.*?\\end\{comment\}|\\iffalse\b.*?\\fi\b')

_TABLE_TAG_RE = re.compile(r'<(/?)table\b[^>]*>')


def outer_tables(html):
    """Each <table> not inside another, whole: a cell's own table is its text."""
    out, depth, start = [], 0, 0
    for m in _TABLE_TAG_RE.finditer(html):
        if not m.group(1):
            if depth == 0:
                start = m.start()
            depth += 1
        elif depth:
            depth -= 1
            if depth == 0:
                out.append(_inner_as_text(html[start:m.end()]))
    return out


def _inner_as_text(block):
    """The outer table with every table inside it reduced to its words."""
    head = block.find('>') + 1
    tail = block.rfind('<')
    inner = block[head:tail]
    for _ in range(8):
        m = re.search(r'(?s)<table\b(?:(?!<table\b).)*?</table>', inner)
        if not m:
            break
        words = ' '.join(re.sub(r'<[^>]+>', ' ', m.group(0)).split())
        inner = inner[:m.start()] + words + inner[m.end():]
    return block[:head] + inner + block[tail:]


_TABULAR_TAG_RE = re.compile(
    r'\\(begin|end)\{(tabular\*?|tabularx|tabulary|longtable)\}')


def _outer_tabulars(tex):
    r"""(kind, body) for each tabular not inside another one.

    A tabular inside a cell is that cell's text. ResNet's \tabincell expands
    to one in four header cells of a table, and a non-greedy match ended the
    table at the first inner `\end{tabular}`.
    """
    out, depth, start, kind = [], 0, 0, None
    for m in _TABULAR_TAG_RE.finditer(tex):
        if m.group(1) == 'begin':
            if depth == 0:
                start, kind = m.end(), m.group(2)
            depth += 1
        elif depth:
            depth -= 1
            if depth == 0:
                out.append((kind, tex[start:m.start()]))
    return out


_GRAPHIC_RE = re.compile(r'\\includegraphics\s*(?:\[[^\]]*\])?\s*\{[^{}]*\}')
# The same allowance as the build's: breaks, cell separators, spacing.
_LAYOUT_LEFTOVER_RE = re.compile(
    r'\\\\(?:\[[^\]]*\])?|&|\\(?:hfill|centering|quad|qquad'
    r'|vspace\*?\{[^{}]*\}|hspace\*?\{[^{}]*\})|%[^\n]*|\s')


def source_rows(body):
    r"""Body cut at every `\\` that ends a row, comments and rules removed.

    Not every `\\` does. `\thead{Total \\ Time}` is one cell holding a line
    break, and a `cases` inside a cell spells its break the same way, so
    the depth that matters is both brace and environment. `latex_rows`
    counts them; splitting on the token alone read one row as two.
    """
    body = COMMENT_RE.sub('', body)
    # The same row end, spelled out: GAN's table 4 ends every row with
    # `\tabularnewline` and read as one row.
    body = re.sub(r'\\tabularnewline(?![a-zA-Z])', r'\\\\', body)
    body = re.sub(r'\\(?:top|mid|bottom)rule(?:\[[^\]]*\])?', '', body)
    # `\cline{2-3}` too: left in, its `2-3` was the first cell of ResNet's
    # `& val & test`, so a correctly blank cell under a `\multirow` read as
    # a stranded row label.
    body = re.sub(r'\\(?:cmidrule|cline)\s*' + _TRIM + r'\s*\{[^}]*\}',
                  '', body)
    # The optional argument has to go with the command. `\addlinespace[2pt]`
    # left its `[2pt]` behind in the next row's first cell, so seven of
    # AlphaQ's `\multirow` continuations counted as labelled and the probe
    # reported the seven real continuations as stranded rows.
    body = re.sub(r'\\(?:hline|addlinespace|toprule)\s*(?:\[[^\]]*\])?'
                  r'|\\noalign\{[^}]*\}', '', body)
    return latex_rows.nonempty_rows(body)


# A row colour carries no text but plenty of characters. Stripped by the
# generic rule below, `\rowcolor[rgb]{ .900, .900, .900}` left `.900, .900,
# .900` behind and the cell read as labelled -- so a blank row in the source
# counted as a labelled one, the source total came out short, and the page's
# genuinely blank rows were reported as stranded. Its whole argument goes,
# unlike `\multirow{4}{*}{Method}`, whose last argument is the label itself.
_CELL_DECOR_RE = re.compile(
    r'\\(?:row|cell|column)color\s*(?:\[[^\]]*\])?\s*\{[^{}]*\}')

# A brace group that may hold one more level of braces. A column format
# often does: `\multicolumn{7}{@{}l}{...}`, `\begin{tabular}{@{}l p{2cm}@{}}`.
# With a flat `\{[^{}]*\}` the format never matched, the command's numbers
# stayed in the cell, and 2609.11801's table 6 was reported missing a value
# 7 on every run: the span of its `\multicolumn{7}{@{}l}{\emph{Training}}`.
_GROUP = r'\{(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*\}'
# Two levels deep: Shor's `\multicolumn{3}{|c|@{\hspace{1em}}}{INPUT}` holds
# a brace inside a brace inside the format, and its span `3` was read as two
# values the page had lost.

# `\multicolumn` and `\multirow` put a span and a format in front of the text.
# The generic rule below strips the command and then unwraps every brace, so
# `\multicolumn{3}{c|}{}` -- an empty spanning cell -- came out as `3 c|` and
# read as a labelled row. VLA-Adapter's table 6 lost one blank row that way,
# and the page's genuinely blank rows were reported as stranded instead.
# Only the leading arguments go; the last brace group is the visible text and
# is what tells `\multirow{8}{*}{\textit{Large}}` from a continuation row.
_SPAN_ARGS_RE = re.compile(
    r'\\multicolumn\s*\{[^{}]*\}\s*' + _GROUP +
    r'|\\multirow\s*\{[^{}]*\}\s*(?:\[[^\]]*\])?\s*' + _GROUP)


def _blank_first_cell(row):
    r"""Does this source row start with an empty cell?

    Empty means nothing a reader would see: a `\multirow` continuation, an
    empty spanning cell, or a cell holding only spacing, colour and rules.
    """
    first = row.split('&')[0]
    first = _CELL_DECOR_RE.sub(' ', first)
    first = _SPAN_ARGS_RE.sub(' ', first)
    first = re.sub(r'\\[a-zA-Z]+\*?\s*(?:\[[^\]]*\])?', ' ', first)
    first = re.sub(r'[{}~$\\]', ' ', first)
    return not first.strip()


_NON_PAGE_RE = re.compile(r'(?s)<(style|script)\b.*?</\1>')


def _page_markup(html):
    r"""The document without its stylesheet and scripts.

    The print sheet carries a CSS comment naming `<table>`, and the table
    scan matched it: block 0 began inside `<style>` and ran to the end of the
    first real table. The counts still agreed by luck, so every table would
    have been silently compared against the wrong source tabular the moment a
    second such comment appeared.
    """
    return _NON_PAGE_RE.sub(' ', html)


_ANNOTATION_RE = re.compile(r'(?s)<annotation\b.*?</annotation>')


def strip_tags(html):
    # `<annotation encoding="application/x-tex">` carries the TeX a browser
    # never renders. Counting it as page text put a phantom `92` (from
    # `&#92;downarrow`) into every math cell, which would mask a real missing
    # 92 -- a check reading text the reader cannot see is measuring nothing.
    return ' '.join(re.sub(r'<[^>]+>', ' ', _ANNOTATION_RE.sub(' ', html))
                    .split())


def html_rows(block):
    out = []
    for row in ROW_RE.findall(block):
        cells = []
        for _tag, attrs, inner in CELL_RE.findall(row):
            span = COLSPAN_RE.search(attrs)
            cells.append((strip_tags(inner), int(span.group(1)) if span else 1))
        if cells:
            out.append(cells)
    return out


def numbers_of(text):
    # NFKC first: pandoc writes `\mathbf{88.55}` in MathML as the
    # mathematical bold digits `𝟖𝟖.𝟓𝟓`, which are digits to `\d` but not the
    # string "88.55". ViT's table 2 lost its seven bold best results that
    # way, on a page that shows every one of them.
    return Counter(NUMBER_RE.findall(unicodedata.normalize('NFKC', text)))


# The numbers inside a command's arguments are not table values: the `3` in
# `\multicolumn{3}{c}{...}`, the `2-7` in `\cmidrule{2-7}`, the `90` in a
# rotation. Counting them reported twenty-one "missing values" for a table
# that was missing none, and a check that cries about numbers nobody printed
# is one people stop reading.
_ARG_NUM_RE = re.compile(
    # A strut or a rule is all lengths: attention's `\rule{0pt}{2.0ex}` and
    # `\specialrule{1pt}{-1pt}{0pt}` were four missing values. First, so the
    # one-length rule below does not take `\rule{0pt}` and leave `{2.0ex}`.
    # A graphic's options are lengths and crops: Neural ODE's
    # `trim=4mm 4mm 4mm 4mm` read as twelve values.
    r'\\includegraphics\s*(?:\[[^\]]*\])?\s*\{[^{}]*\}|'
    r'\\(?:rule|specialrule)(?![a-zA-Z])(?:\s*\[[^\]]*\])?(?:\s*\{[^{}]*\})+|'
    # A citation key is not a value either. `\cite{adepu2024framequant}`
    # carries a 2024 the reader never sees as a table entry, and CafeQ's
    # table 6 was reported as missing six values it never had.
    r'\\cite[a-zA-Z]*\s*(?:\[[^\]]*\])*\s*\{[^{}]*\}'
    # A drawing, not a value: ViT marks each task's group with
    # `\tikz\fill[natural] (0,0) circle (.5ex);`, and its 20 coordinates
    # were reported as 60 missing numbers.
    r'|\\tikz\b[^;]*;'
    r'|\\(?:ref|autoref|eqref|cref|Cref|label)\s*\{[^{}]*\}'
    r'|\\(?:multicolumn|multirow)\s*\{[^{}]*\}\s*(?:\[[^\]]*\])?\s*' + _GROUP +
    r'|\\(?:cmidrule|cline)\s*' + _TRIM + r'\s*\{[^{}]*\}'
    # A footnote in a cell is printed under the table, not in it.
    r'|\\(?:tablefootnote|footnote)\s*' + _GROUP +
    r'|\\phantom\s*' + _GROUP +
    r'|\\rotatebox\s*(?:\[[^\]]*\])?\s*\{[^{}]*\}'
    r'|\\(?:resizebox|scalebox)\s*\{[^{}]*\}\s*\{[^{}]*\}'
    # A colour, not a value. `\rowcolor[rgb]{ .900, .900, .900}` shades the
    # paper's own rows, and its three `.900`s read as a value `900` that the
    # page had supposedly lost -- six of them across VLA-Adapter's tables 5,
    # 6 and 7, on a book whose fifteen tables were all correct.
    r'|\\(?:row|cell|column)color\s*(?:\[[^\]]*\])?\s*\{[^{}]*\}'
    # A dingbat's argument is a glyph id. `\ding{51}` prints a tick and
    # `\ding{55}` a cross; counted as values they were two more numbers
    # nobody had lost.
    r'|\\ding\s*\{[^{}]*\}'
    r'|\\setlength\s*\{[^{}]*\}\s*\{[^{}]*\}'
    r'|\\begin\{[^{}]*\}\s*(?:\[[^\]]*\])?\s*' + _GROUP +
    r'|\\[a-zA-Z]+\s*\{\s*[-\d.]+\s*(?:em|ex|pt|cm|mm|in|bp)\s*\}'
    # The same length in an optional argument: `\addlinespace[2pt]`. Seven of
    # those in AlphaQ's table 1 read as seven values the page had lost.
    r'|\\[a-zA-Z]+\s*\[\s*[-\d.]+\s*(?:em|ex|pt|cm|mm|in|bp)\s*\]'
    # And after a row break: U-Net's `\\[-0.8cm]` was a missing value 0.8.
    r'|\\\\\s*\[\s*[-\d.]+\s*(?:em|ex|pt|cm|mm|in|bp)\s*\]')


def printed_numbers(body):
    """The numbers a reader sees, with command arguments taken out."""
    return numbers_of(_ARG_NUM_RE.sub(' ', COMMENT_RE.sub('', body)))


def check_table(index, columns, body, block):
    """Findings for one table. Empty list means it matches the source."""
    findings = []
    rows = html_rows(block)
    if not rows:
        return ['table %d: no <tr> at all in the built HTML' % index]

    widest = max(sum(span for _t, span in r) for r in rows)
    if columns and widest != columns:
        findings.append('table %d: %d column(s) in the source colspec, %d '
                        'rendered' % (index, columns, widest))

    src_rows = source_rows(body)
    # Rows with something in them, on both sides. GPT-3's poem table spaces
    # its stanzas with `\\ \\` and `& \\`; the page keeps those blank rows and
    # the source count did not, five apart on a faithful table.
    src_full = [r for r in src_rows if re.sub(r'[&\s~{}]', '', r)]
    # A row of graphics has no text and is still a row: GPT-3's plot grids.
    page_full = [r for r in ROW_RE.findall(block)
                 if CELL_RE.search(r) and (strip_tags(r) or '<img' in r)]
    if src_rows and abs(len(src_full) - len(page_full)) > 1:
        findings.append('table %d: %d row(s) in the source, %d rendered'
                        % (index, len(src_full), len(page_full)))

    src_nums = printed_numbers(body)
    out_nums = numbers_of(' '.join(t for r in rows for t, _s in r))
    missing = src_nums - out_nums
    if missing:
        findings.append('table %d: %d value(s) in the source are not on the '
                        'page: %s' % (index, sum(missing.values()),
                                      ', '.join(sorted(missing)[:8])))

    src_spans = Counter(int(n) for n in MULTICOL_RE.findall(
        COMMENT_RE.sub('', body)) if int(n) > 1)
    out_spans = Counter(span for r in rows for _t, span in r if span > 1)
    lost = src_spans - out_spans
    if lost:
        findings.append('table %d: %d column-group span(s) lost — the source '
                        'has %s, the page has %s'
                        % (index, sum(lost.values()),
                           dict(sorted(src_spans.items())),
                           dict(sorted(out_spans.items())) or '{}'))

    blank_label = sum(1 for r in rows[1:]
                      if r and not r[0][0].strip()
                      and any(t.strip() for t, _s in r[1:]))
    # A `\multirow{4}{*}{Method}` leaves the next three source rows with an
    # empty first cell, and the page is right to render them empty. Only an
    # excess over the source is a stranded label -- the same ours-vs-source
    # rule the rest of this probe is built on.
    src_blank = sum(1 for r in src_rows[1:] if _blank_first_cell(r))
    if blank_label - src_blank > 0:
        findings.append('table %d: %d body row(s) carry numbers with no row '
                        'label (the source leaves %d such row(s) empty)'
                        % (index, blank_label - src_blank, src_blank))
    return findings


def probe(temp_dir, lang='ko', strict=False):
    flat = os.path.join(temp_dir, 'flat.tex')
    html_path = os.path.join(temp_dir, 'book_doc.html')
    if not os.path.isfile(flat):
        print('SKIP: no flat.tex in %s — this check needs the LaTeX source'
              % temp_dir)
        return 0
    if not os.path.isfile(html_path):
        print('ERROR: no book_doc.html in %s — build first' % temp_dir)
        return 1

    # Without the comments: Sentence-BERT has a whole table commented out,
    # and it was counted as an eighth table missing from a correct book.
    units = tabular_units(_SKIPPED_RE.sub('', COMMENT_RE.sub('', read(flat))))
    blocks = outer_tables(_page_markup(read(html_path)))
    print('source tabulars: %d      tables in the book: %d'
          % (len(units), len(blocks)))

    findings = []
    if len(units) != len(blocks):
        findings.append('%d tabular(s) in the source, %d table(s) in the book'
                        % (len(units), len(blocks)))
    for i, ((columns, body), block) in enumerate(zip(units, blocks), 1):
        findings.extend(check_table(i, columns, body, block))

    matched = min(len(units), len(blocks))
    print('tables compared : %d, %d finding(s)' % (matched, len(findings)))
    for line in findings[:24]:
        print('   ' + line)
    if len(findings) > 24:
        print('   ... and %d more' % (len(findings) - 24))

    if findings:
        print('\nFAIL: %d table finding(s) against the source LaTeX'
              % len(findings))
        return 1 if strict else 0
    print('\nPASS: every table matches the source LaTeX')
    return 0


def main():
    ap = argparse.ArgumentParser(
        description='Compare every built table against the source LaTeX')
    ap.add_argument('temp_dir')
    ap.add_argument('--lang', default='ko')
    ap.add_argument('--strict', action='store_true')
    args = ap.parse_args()
    sys.exit(probe(args.temp_dir, args.lang, args.strict))


if __name__ == '__main__':
    main()

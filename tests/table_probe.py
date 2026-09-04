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
from collections import Counter

TABULAR_RE = re.compile(
    r'\\begin\{(tabular\*?|tabularx|longtable|array)\}(.*?)\\end\{\1\}',
    re.DOTALL)
TABLE_EL_RE = re.compile(r'(?s)<table\b.*?</table>')
ROW_RE = re.compile(r'(?s)<tr\b.*?</tr>')
CELL_RE = re.compile(r'(?s)<(t[hd])\b([^>]*)>(.*?)</\1>')
COLSPAN_RE = re.compile(r'colspan="(\d+)"')
MULTICOL_RE = re.compile(r'\\multicolumn\s*\{\s*(\d+)\s*\}')
NUMBER_RE = re.compile(r'\d+(?:\.\d+)?')
# Comment out to the end of line, but `\%` is a printed percent sign.
COMMENT_RE = re.compile(r'(?<!\\)%[^\n]*')


def read(path):
    return io.open(path, encoding='utf-8', errors='replace').read()


def colspec_columns(spec):
    r"""Column count of `{l cc |r p{2cm} *{3}{c}}`."""
    spec = re.sub(r'@\{[^}]*\}|!\{[^}]*\}|>\{[^}]*\}|<\{[^}]*\}', '', spec)

    def expand(m):
        return m.group(2) * int(m.group(1))

    prev = None
    while prev != spec:
        prev = spec
        spec = re.sub(r'\*\s*\{\s*(\d+)\s*\}\s*\{([^{}]*)\}', expand, spec)
    spec = re.sub(r'[a-z]\{[^{}]*\}', 'p', spec)      # p{..} m{..} b{..}
    return len(re.findall(r'[lcrpXY]', spec))


def _matching_brace(text, start):
    r"""Index of the `}` closing the `{` at `start`, or -1."""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return i
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
    for m in TABULAR_RE.finditer(tex):
        body = m.group(2)
        pos = re.match(r'\s*(?:\[[^\]]*\])?\s*', body).end()
        # `tabular*` and `tabularx` take a width argument before the colspec.
        if m.group(1) in ('tabular*', 'tabularx'):
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
        out.append((colspec_columns(body[pos + 1:close]), body[close + 1:]))
    return out


def source_rows(body):
    r"""Body split on `\\`, comments and rules removed."""
    body = COMMENT_RE.sub('', body)
    body = re.sub(r'\\(?:top|mid|bottom)rule(?:\[[^\]]*\])?', '', body)
    body = re.sub(r'\\cmidrule\s*(?:\([lr]{1,2}\))?\s*\{[^}]*\}', '', body)
    # The optional argument has to go with the command. `\addlinespace[2pt]`
    # left its `[2pt]` behind in the next row's first cell, so seven of
    # AlphaQ's `\multirow` continuations counted as labelled and the probe
    # reported the seven real continuations as stranded rows.
    body = re.sub(r'\\(?:hline|addlinespace|toprule)\s*(?:\[[^\]]*\])?'
                  r'|\\noalign\{[^}]*\}', '', body)
    rows = [r for r in re.split(r'\\\\', body) if r.strip()]
    return rows


# A row colour carries no text but plenty of characters. Stripped by the
# generic rule below, `\rowcolor[rgb]{ .900, .900, .900}` left `.900, .900,
# .900` behind and the cell read as labelled -- so a blank row in the source
# counted as a labelled one, the source total came out short, and the page's
# genuinely blank rows were reported as stranded. Its whole argument goes,
# unlike `\multirow{4}{*}{Method}`, whose last argument is the label itself.
_CELL_DECOR_RE = re.compile(
    r'\\(?:row|cell|column)color\s*(?:\[[^\]]*\])?\s*\{[^{}]*\}')

# `\multicolumn` and `\multirow` put a span and a format in front of the text.
# The generic rule below strips the command and then unwraps every brace, so
# `\multicolumn{3}{c|}{}` -- an empty spanning cell -- came out as `3 c|` and
# read as a labelled row. VLA-Adapter's table 6 lost one blank row that way,
# and the page's genuinely blank rows were reported as stranded instead.
# Only the leading arguments go; the last brace group is the visible text and
# is what tells `\multirow{8}{*}{\textit{Large}}` from a continuation row.
_SPAN_ARGS_RE = re.compile(
    r'\\multicolumn\s*\{[^{}]*\}\s*\{[^{}]*\}'
    r'|\\multirow\s*\{[^{}]*\}\s*(?:\[[^\]]*\])?\s*\{[^{}]*\}')


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
    return Counter(NUMBER_RE.findall(text))


# The numbers inside a command's arguments are not table values: the `3` in
# `\multicolumn{3}{c}{...}`, the `2-7` in `\cmidrule{2-7}`, the `90` in a
# rotation. Counting them reported twenty-one "missing values" for a table
# that was missing none, and a check that cries about numbers nobody printed
# is one people stop reading.
_ARG_NUM_RE = re.compile(
    # A citation key is not a value either. `\cite{adepu2024framequant}`
    # carries a 2024 the reader never sees as a table entry, and CafeQ's
    # table 6 was reported as missing six values it never had.
    r'\\cite[a-zA-Z]*\s*(?:\[[^\]]*\])*\s*\{[^{}]*\}'
    r'|\\(?:ref|autoref|eqref|cref|Cref|label)\s*\{[^{}]*\}'
    r'|\\(?:multicolumn|multirow)\s*\{[^{}]*\}\s*(?:\[[^\]]*\])?\s*\{[^{}]*\}'
    r'|\\(?:cmidrule|cline)\s*(?:\([lr]{1,2}\))?\s*\{[^{}]*\}'
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
    r'|\\begin\{[^{}]*\}\s*(?:\[[^\]]*\])?\s*\{[^{}]*\}'
    r'|\\[a-zA-Z]+\s*\{\s*[-\d.]+\s*(?:em|ex|pt|cm|mm|in|bp)\s*\}'
    # The same length in an optional argument: `\addlinespace[2pt]`. Seven of
    # those in AlphaQ's table 1 read as seven values the page had lost.
    r'|\\[a-zA-Z]+\s*\[\s*[-\d.]+\s*(?:em|ex|pt|cm|mm|in|bp)\s*\]')


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
    if src_rows and abs(len(src_rows) - len(rows)) > 1:
        findings.append('table %d: %d row(s) in the source, %d rendered'
                        % (index, len(src_rows), len(rows)))

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

    units = tabular_units(read(flat))
    blocks = TABLE_EL_RE.findall(_page_markup(read(html_path)))
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

# -*- coding: utf-8 -*-
"""The paper's tables, from raw LaTeX to HTML the book can print.

The arXiv backend keeps tables as raw LaTeX; pandoc would drop them on the
HTML path. Each one is converted on its own, its caption, notes, header rows,
rules and shading carried across, and spliced back in.

Moved out of merge_and_build.py, which re-exports every name here that the
build or a test reaches for.
"""

import os
import re
import subprocess
import tempfile

import arxiv_backend

from build_common import (
    _CAPTION_CMD_RE, _COMMENT_LINE_RE, _balanced_group, _brace_group,
    _in_latex_comment, resolve_pandoc, strip_tex_comments,
)

from numbering import (
    build_float_numbers, build_label_index, read_float_units,
)


# =============================================================================
# Raw LaTeX tables
# =============================================================================
#
# The arXiv backend keeps the paper's tables as raw LaTeX
# (`\resizebox{..}{..}{\begin{tabular}...\end{tabular}}`, often inside a
# `\begin{table*}` float) rather than converting them to markdown. pandoc's
# markdown reader parses that as a raw LaTeX block, and a raw block only
# survives into its OWN output format -- so on the HTML path every one of those
# tables was silently DROPPED. Not rendered as literal text, which would at
# least be visible: simply gone, taking the paper's results section with it.
#
# pandoc CAN read a bare tabular when told the input is LaTeX, so each one is
# converted on its own and spliced back as raw HTML (`raw_html` is in
# PANDOC_FROM, so it passes straight through).
#
# The float wrapper has to be consumed too. pandoc drops a `\begin{table*}`
# float wholesale -- converting one yields an empty document -- and worse, if
# the `\begin{table*}` marker is left in place it starts a raw LaTeX block that
# swallows the HTML table injected inside it. So the whole float is replaced,
# and its `\caption{...}` is rendered separately into a real <caption>.

_TABULAR_BEGIN = r'\begin{tabular}'
_TABULAR_END = r'\end{tabular}'
# `tabular*` is the width-setting variant, and searching for the plain spelling
# misses it completely — the string `\begin{tabular}` is not a substring of
# `\begin{tabular*}`. BERT's GLUE results table is written that way: the float
# was found by no scan, converted by nothing, and reached the page as nothing.
_TABULAR_BEGIN_RE = re.compile(r'\\begin\{tabular\*?\}')
_TABULAR_END_RE = re.compile(r'\\end\{tabular\*?\}')
# Wrappers that take the tabular as their last braced argument.
_TABLE_WRAPPERS = (r'\resizebox', r'\scalebox', r'\colorbox', r'\fbox', r'\makebox')
# Float environments a tabular is commonly parked in.
_FLOAT_ENVS = ('table*', 'table', 'figure*', 'figure')


def _widen_to_wrapper(text, start, stop):
    """Widen a tabular span over a `\\resizebox{..}{..}{ ... }` wrapper.

    Counts the braces left open between the wrapper command and the tabular,
    then consumes that many closing braces after it.
    """
    # A wrapper the author commented out is not wrapping anything. The
    # Transformer's parsing table carries `%\resizebox{1.0}{` on the line above
    # its tabular: one unbalanced brace, on a line TeX never reads. Counted, it
    # consumed a closing brace belonging to the float; `_widen_to_float` then
    # found no float, the table reached pandoc as raw LaTeX, and pandoc dropped
    # it — the whole constituency-parsing table, gone without a word.
    head = -1
    for cmd in _TABLE_WRAPPERS:
        found = start
        while found > 0:
            found = text.rfind(cmd, max(0, start - 400), found)
            if found < 0:
                break
            if not _in_latex_comment(text, found):
                break
        if found > head:
            head = found
    if head < 0:
        return start, stop
    between = _COMMENT_LINE_RE.sub('', text[head:start])
    depth = between.count('{') - between.count('}')
    if depth <= 0:
        return start, stop
    tail = stop
    while depth > 0 and tail < len(text):
        if text[tail] == '}':
            depth -= 1
        elif text[tail] == '{':
            depth += 1
        tail += 1
    return head, tail


def _widen_to_float(text, start, stop):
    r"""Widen to an enclosing float environment. Returns (start, stop, env).

    The `\begin` found behind the tabular only encloses it if it has not
    already closed. Without that test the search walks back into the
    PREVIOUS float, then forward to the NEXT float's `\end`, and returns a
    span covering everything in between -- 22,000 characters in SINQ's case.
    The expander replaces that span with one rendered table and advances its
    cursor past it, so the prose inside is skipped: 316 Korean words in SINQ
    and 194 in AlphaQ, with every table still counted and every check quiet.
    """
    for env in _FLOAT_ENVS:
        opening, closing = '\\begin{%s}' % env, '\\end{%s}' % env
        begin = text.rfind(opening, max(0, start - 4000), start)
        if begin < 0:
            continue
        if text.find(closing, begin, start) >= 0:
            continue                     # that float closed before this table
        end = text.find(closing, stop)
        if end < 0:
            continue
        return begin, end + len(closing), env
    return start, stop, None


def _extract_caption(float_text, tabular_at=None):
    """The LaTeX inside the `\\caption{...}` that belongs to this tabular.

    Taking the float's FIRST caption is wrong whenever a float holds more
    than one: AlphaQ puts two minipages, each with its own caption and its own
    tabular, inside one `table*`. Both rendered tables carried the first
    caption and the second one's text -- "Component ablation on OLMoE-1B-7B"
    -- was nowhere in the book.

    A caption precedes its tabular inside the minipage, so the nearest one
    ABOVE wins; a float that captions below still resolves by falling forward.
    """
    starts = [m.start() for m in _CAPTION_CMD_RE.finditer(float_text)
              if not _in_latex_comment(float_text, m.start())]
    if not starts:
        return None
    if tabular_at is None:
        at = starts[0]
    else:
        above = [s for s in starts if s < tabular_at]
        at = above[-1] if above else starts[0]
    brace = float_text.find('{', at)
    if brace < 0:
        return None
    end = _balanced_group(float_text, brace)
    return float_text[brace + 1:end - 1] if end > 0 else None


_TABLENOTES_RE = re.compile(
    r'\\begin\{tablenotes\}(?:\s*\[[^\]]*\])?(.*?)\\end\{tablenotes\}',
    re.DOTALL)
_NOTE_ITEM_RE = re.compile(r'\\item\s*(?:\[([^\]]*)\])?\s*')


def extract_table_notes(float_text):
    r"""The `threeparttable` note under a table, as LaTeX pandoc can read.

    pandoc has no reader for `tablenotes` and drops the environment whole.
    SINQ has four, and each one defines the dagger its rows carry: with the
    note gone, four tables printed a marker that nothing on the page
    explained. Nothing counted it either -- the rows were complete, the
    numbers were complete, and the sentence saying which baselines were
    re-run rather than quoted was not there at all.
    """
    m = _TABLENOTES_RE.search(float_text)
    if not m:
        return None
    parts = []
    for chunk in re.split(r'(?=\\item\b)', m.group(1)):
        chunk = chunk.strip()
        item = _NOTE_ITEM_RE.match(chunk) if chunk else None
        if not item:
            continue
        marker, body = (item.group(1) or '').strip(), chunk[item.end():].strip()
        if not body:
            continue
        parts.append('\\textsuperscript{%s} %s' % (marker, body)
                     if marker else body)
    return '\n\n'.join(parts) or None


def _matching_tabular_end(text, start):
    r"""Index just past the `\end{tabular}` that closes the one at `start`.

    A cell holding a multi-line header is written as a `tabular` of its own --
    `\begin{tabular}[c]{@{}c@{}}Only RGB\\ Input\end{tabular}` -- and taking
    the FIRST `\end{tabular}` cuts the outer table off inside that cell.
    Three of DeeR-VLA's tables came out as fragments pandoc could not read,
    a fourth table went missing, and the paper's eleven tables were counted
    as fourteen.
    """
    depth, i = 0, start
    while i < len(text):
        open_m = _TABULAR_BEGIN_RE.search(text, i)
        close_m = _TABULAR_END_RE.search(text, i)
        if close_m is None:
            return -1
        if open_m is not None and open_m.start() < close_m.start():
            depth += 1
            i = open_m.end()
            continue
        depth -= 1
        i = close_m.end()
        if depth == 0:
            return i
    return -1


def find_raw_latex_tables(text):
    """Locate every raw LaTeX tabular, with its wrapper, float and caption."""
    out, i = [], 0
    while True:
        open_m = _TABULAR_BEGIN_RE.search(text, i)
        if open_m is None:
            break
        a = open_m.start()
        b = _matching_tabular_end(text, a)
        if b < 0:
            break
        i = b
        wa, wb = _widen_to_wrapper(text, a, b)
        fa, fb, env = _widen_to_float(text, wa, wb)
        out.append({
            'bare': text[a:b],
            'start': fa,
            'stop': fb,
            'float': env,
            'caption': _extract_caption(text[fa:fb], a - fa) if env else None,
            'notes': extract_table_notes(text[fa:fb]),
        })
    # One float can hold two tabulars, and the note under it belongs to the
    # float, not to each of them. Attached to both it prints twice.
    seen = {}
    for entry in out:
        seen[(entry['start'], entry['stop'])] = entry
    for entry in out:
        if seen.get((entry['start'], entry['stop'])) is not entry:
            entry['notes'] = None
    return out


def count_raw_latex_tables(md_text):
    """How many raw LaTeX tables the merged markdown carries."""
    return len(find_raw_latex_tables(md_text))


# A pandoc table caption is a line of its own opening with `: `.
_MD_TABLE_CAPTION_RE = re.compile(r'(?m)^([ \t]*:[ \t]+)(?=\S)')
# So is a pandoc DEFINITION LIST item, which is why the shape alone cannot
# tell them apart. A caption abuts its table; a definition abuts its term.
_MD_TABLE_ROW_RE = re.compile(r'^\s*(?:\|.*\||\+[-=+:]{2,}\+)\s*$')


def markdown_table_captions(md_text):
    r"""[(line start, offset just past the `: `)] for real table captions.

    Matching `^: ` alone counts every definition list item as a caption.
    VLA-Adapter carries fourteen of them, holding its Question, Key Finding
    and Conclusion items, and not one markdown table. Ten of its fifteen
    table numbers landed on that prose and ten real tables were left with no
    number at all, so the book printed `표 1` over a question and nothing
    over the table a reader was sent to.

    A caption is adjacent to its table, above it or below it, blank lines
    aside. A definition list item is adjacent to its term. That is the one
    difference the text carries, so it is what this asks about.
    """
    lines = md_text.split('\n')
    starts, pos = [], 0
    for line in lines:
        starts.append(pos)
        pos += len(line) + 1

    def is_row(i):
        return 0 <= i < len(lines) and bool(_MD_TABLE_ROW_RE.match(lines[i]))

    def nearest(i, step):
        i += step
        while 0 <= i < len(lines) and not lines[i].strip():
            i += step
        return i

    out = []
    for i, line in enumerate(lines):
        m = _MD_TABLE_CAPTION_RE.match(line)
        if not m:
            continue
        if is_row(nearest(i, -1)) or is_row(nearest(i, 1)):
            out.append((starts[i], starts[i] + m.end()))
    return out


_ALREADY_NUMBERED_RE = re.compile(
    r'\s*(?:\\textbf\{|\*\*)?\s*[^\s\\*{}]{1,12}\s*\d+\s*'
    r'(?:\(\s*Table\s*\d+\s*\))?\s*(?:\}|\*\*)')


def number_table_captions(md_text, temp_dir, lang_cfg=None):
    """Put "표 5 (Table 5)" in front of every table caption. (text, count).

    Figures carried their number and tables did not, so the body said "표 5에서
    보듯이" and the caption above the table said nothing a reader could match
    it against -- the same gap the equations had before they were numbered.

    Done here, on the merged markdown, because this is the last point where
    both kinds of table are still visible as text: the raw LaTeX ones keep
    their `\\caption{}` and pandoc's own tables keep their `: ` line. After
    this the two output paths render captions separately and would each need
    their own version of this.

    Only a captioned table takes a number, which is exactly LaTeX's rule.
    """
    lang_cfg = lang_cfg or {}
    label = lang_cfg.get('table_label', 'Table')
    numbers = [u['number'] for u in read_float_units(temp_dir)
               if u['kind'] == 'table' and u['number'] is not None]
    if not numbers:
        return md_text, 0

    def badge(number):
        # `%s`, not `%d`: a float counter scoped to the section carries a
        # number like `3.1`. This was the fourth site to follow from that and
        # the one that got missed — the equation taggers and the link regexes
        # were changed together, and the caption badge was not, so the build
        # died on `%d format: a real number is required, not str`.
        text = '%s %s' % (label, number)
        if label != 'Table':
            text += ' (Table %s)' % number
        return text

    # Every caption in the document, in the order a reader meets them.
    #
    # Iterate CAPTIONS, not tables: AlphaQ puts two minipages with their own
    # \caption inside one table* float, which LaTeX numbers as two tables
    # (K47). Walking tables gave both of them the float's first caption and
    # stamped two badges onto it.
    inside = sorted({(t['start'], t['stop'])
                     for t in find_raw_latex_tables(md_text)})
    events = []
    for start, stop in inside:
        for m in _CAPTION_CMD_RE.finditer(md_text, start, stop):
            # An author who keeps an old caption commented out above the live
            # one leaves two \caption commands in the float. DeeR-VLA does,
            # and counting the dead one gave its first table two numbers,
            # pushed every later table one on, and left the last with none.
            if _in_latex_comment(md_text, m.start()):
                continue
            brace = md_text.find('{', m.end() - 1)
            if 0 <= brace < stop:
                events.append((brace + 1, 'latex'))
    for line_start, at in markdown_table_captions(md_text):
        if any(a <= line_start < b for a, b in inside):
            continue                      # a stray `: ` within a raw float
        events.append((at, 'markdown'))
    events = sorted(set(events))

    pieces, cursor, used = [], 0, 0
    for at, kind in events:
        if used >= len(numbers):
            break
        pieces.append(md_text[cursor:at])
        text = badge(numbers[used])
        cursor = at
        used += 1
        # Already numbered: this text has been through here before. Skipping
        # keeps the pass idempotent, so a repair that feeds the numbered
        # markdown back does not give every caption a second badge.
        if _ALREADY_NUMBERED_RE.match(md_text, at):
            continue
        pieces.append('\\textbf{%s} ' % text if kind == 'latex'
                      else '**%s** ' % text)
    pieces.append(md_text[cursor:])
    return ''.join(pieces), used


def check_badge_placement(md_text, lang_cfg=None):
    r"""Did every table badge land on a table? Returns (ok, detail).

    Counting is what let this ship. `number_table_captions` issued fifteen
    numbers, wrote fifteen badges and reported fifteen, and ten of them were
    sitting on prose: pandoc's definition list opens with `: ` and so does a
    table caption, so the Question and Key Finding items took the numbers
    while ten real tables got none. Every count agreed. The page printed
    `표 1` over a question, and the sentence that said "see 표 1" pointed at
    it.

    So this asks where each badge IS, not how many were written. A badge
    belongs to a `\caption{}` inside a raw float, or to a `: ` line that
    abuts a markdown table. Anywhere else it is on prose.
    """
    lang_cfg = lang_cfg or {}
    label = lang_cfg.get('table_label', 'Table')
    inside = sorted({(t['start'], t['stop'])
                     for t in find_raw_latex_tables(md_text)})
    captions = {at for _start, at in markdown_table_captions(md_text)}

    # `표 1 (Table 1)` and `표 B1 (Table B1)`. A length cap was the first
    # attempt and it silently matched only the body tables: the appendix
    # badges are two characters longer, so the check validated 8 of 15 and
    # reported every one of them fine. A check that sees half the population
    # is worse than none, so the shape is spelled out instead of bounded.
    badge = re.compile(
        r'(?:\\textbf\{|\*\*)\s*' + re.escape(label)
        + r'\s+[A-Za-z]?[\d.]+(?:\s*\(Table\s+[A-Za-z]?[\d.]+\))?\s*'
          r'(?:\}|\*\*)')
    stray = []
    total = 0
    for m in badge.finditer(md_text):
        total += 1
        at = m.start()
        if any(a <= at < b for a, b in inside):
            continue                       # inside a raw float: a caption
        if any(abs(at - c) <= 2 for c in captions):
            continue                       # on a real markdown table caption
        line_start = md_text.rfind('\n', 0, at) + 1
        line_end = md_text.find('\n', at)
        stray.append(' '.join(
            md_text[line_start:line_end if line_end > 0 else at + 60].split()))

    if not stray:
        return True, '%d table badge(s), every one on a table caption' % total
    return False, ('%d of %d table badge(s) sit on prose, not on a table:\n  %s'
                   % (len(stray), total,
                      '\n  '.join(s[:96] for s in stray[:6])))


# pifont's tick and cross, which pandoc has no reader for: it drops the
# command and emits NOTHING, so a column of them comes out blank. VLA-Adapter
# lost all twelve marks in its table 7, whose entire content is which
# condition each method uses; the six success rates were left attached to
# nothing and two rows became indistinguishable. Every count agreed, because
# a mark is not a value and no probe was counting marks.
#
# Only the codes whose glyph is settled are mapped. An unknown \ding is left
# exactly as written, so it prints and can be seen, rather than being guessed
# at and quietly turned into the wrong symbol.
_DING_GLYPHS = {
    '51': '\u2713',      # check mark
    '52': '\u2714',      # heavy check mark
    '53': '\u2715',      # multiplication x
    '54': '\u2716',      # heavy multiplication x
    '55': '\u2717',      # ballot x
    '56': '\u2718',      # heavy ballot x
}
_DING_RE = re.compile(r'\\ding\s*\{\s*(\d+)\s*\}')


def substitute_dings(latex):
    """`\\ding{51}` -> the character. Returns (text, replaced, unknown)."""
    unknown = []

    def swap(m):
        glyph = _DING_GLYPHS.get(m.group(1))
        if glyph is None:
            unknown.append(m.group(1))
            return m.group(0)
        return glyph

    out, total = _DING_RE.subn(swap, latex)
    return out, total - len(unknown), sorted(set(unknown))


def _clean_colspec(spec):
    r"""Keep the alignment of a tabular preamble and drop the presentation.

    `@{}` and `!{...}` set inter-column spacing, `>{...}` and `<{...}` inject
    material either side of a cell, and `p{0.30\textwidth}` fixes a width. An
    HTML table uses none of it; alignment is the part that carries meaning.
    """
    out, i = [], 0
    while i < len(spec):
        ch = spec[i]
        if ch in '@!><' and i + 1 < len(spec) and spec[i + 1] == '{':
            _, i = _brace_group(spec, i + 1)
        elif ch in 'pmbPC' and i + 1 < len(spec) and spec[i + 1] == '{':
            _, i = _brace_group(spec, i + 1)
            out.append('l')                # a paragraph column reads left
        elif ch in 'lcr':
            out.append(ch)
            i += 1
        elif ch in 'XY':
            out.append('l')                # tabularx stretch columns
            i += 1
        elif ch == '|':
            out.append('|')
            i += 1
        else:
            i += 1                         # whitespace, widths, anything else
    return ''.join(out) or 'l'


# How many brace groups sit between the environment name and the preamble.
_TABULAR_ENVS = {'tabular': 0, 'array': 0, 'longtable': 0,
                 'tabular*': 1, 'tabularx': 1, 'tabulary': 1}
_TABULAR_BEGIN_RE = re.compile(
    r'\\begin\{(tabular\*?|array|longtable|tabularx|tabulary)\}')


def normalise_tabular_preambles(latex):
    r"""Rewrite every tabular preamble down to alignment letters.

    pandoc 3.10.2 cannot read a preamble mixing `@{}` spacing with `p{width}`
    columns. It abandons the tabular and emits a `<div class="tabular">` with
    the preamble printed as PROSE: the paper that found this shows
    `@p 0.30 p 0.64 @` where its notation table should be. Nothing downstream
    sees a table, so the table is absent from the book and the only report is
    a count of failures.

    Returns (latex, number of preambles rewritten).
    """
    out, cursor, changed = [], 0, 0
    for m in _TABULAR_BEGIN_RE.finditer(latex):
        if m.start() < cursor:
            continue
        skip = _TABULAR_ENVS.get(m.group(1), 0)
        i = m.end()
        while i < len(latex) and latex[i] in ' \t\n':
            i += 1
        if i < len(latex) and latex[i] == '[':          # \begin{tabular}[t]
            close = latex.find(']', i)
            if close < 0:
                continue
            i = close + 1
            while i < len(latex) and latex[i] in ' \t\n':
                i += 1
        for _ in range(skip):                           # tabularx width arg
            if i >= len(latex) or latex[i] != '{':
                break
            _, i = _brace_group(latex, i)
            while i < len(latex) and latex[i] in ' \t\n':
                i += 1
        if i >= len(latex) or latex[i] != '{':
            continue
        spec, end = _brace_group(latex, i)
        if spec is None:
            continue
        cleaned = _clean_colspec(spec)
        if cleaned == spec.strip():
            continue
        out.append(latex[cursor:i])
        out.append('{%s}' % cleaned)
        cursor = end
        changed += 1
    out.append(latex[cursor:])
    latex = ''.join(out)

    # And every `\multicolumn{2}{@{}l@{}}{...}`, which is the one that
    # actually mattered. Normalising the tabular preamble alone left the
    # notation table still absent: pandoc parses `{ll}` happily, then meets a
    # multicolumn span whose own spec it cannot read and abandons the whole
    # tabular, falling back to the unknown-environment rendering. `\multirow`
    # takes a width in the same position and is left alone; it is not a
    # column spec.
    out, cursor = [], 0
    for m in re.finditer(r'\\multicolumn\s*\{', latex):
        if m.start() < cursor:
            continue
        _n, i = _brace_group(latex, m.end() - 1)
        while i < len(latex) and latex[i] in ' \t\n':
            i += 1
        if i >= len(latex) or latex[i] != '{':
            continue
        spec, end = _brace_group(latex, i)
        if spec is None:
            continue
        cleaned = _clean_colspec(spec)
        if cleaned == spec.strip():
            continue
        out.append(latex[cursor:i])
        out.append('{%s}' % cleaned)
        cursor = end
        changed += 1
    out.append(latex[cursor:])
    return ''.join(out), changed


def _latex_fragment_to_html(latex, pandoc, work, name, inline=False,
                            math_mode='mathml'):
    """Render one LaTeX fragment to HTML. Returns '' when pandoc cannot.

    --mathml matters: without it pandoc emits `<span class="math inline">` with
    raw TeX inside, and a bare backslash there escapes the following '<' when
    the markdown reader re-reads the block, leaving a literal `</span>` printed
    in the cell. --wrap=none keeps pandoc from breaking lines inside tags.
    """
    latex, _swapped, _unknown = substitute_dings(latex)
    latex, _specs = normalise_tabular_preambles(latex)
    path = os.path.join(work, name)
    with open(path, 'w', encoding='utf-8', newline='') as fh:
        fh.write(latex + '\n')
    cmd = [pandoc, '-f', 'latex', '-t', 'html', '--wrap=none', path]
    if math_mode == 'mathml':
        cmd.insert(-1, '--mathml')
    # A fragment that will not convert is a table missing from the book, and
    # for a long time the only report was a count. Say what happened: the
    # first diagnosis of this cost an afternoon because the reason was thrown
    # away here.
    try:
        result = subprocess.run(cmd,
                                capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        print("  %s: pandoc could not run (%s)" % (name, str(exc)[:120]))
        return ''
    if result.returncode != 0:
        detail = ' '.join((result.stderr or '').split())[:200]
        print("  %s: pandoc exited %d%s"
              % (name, result.returncode, ' -- ' + detail if detail else ''))
        return ''
    html = (result.stdout or '').strip()
    if inline:
        html = re.sub(r'^<p>|</p>$', '', html).strip()
    return html


# Plain `-t markdown` writes a table however it likes. For anything wider or
# more spanned than a few columns it chooses a SIMPLE table -- columns marked
# by character position, no `|` anywhere -- which _is_markdown_table does not
# recognise, so nine of AlphaQ's twelve tables were dropped to plain text in
# the Word file while the HTML had all twelve. It also wraps the table in a
# `::: table*` div that prints literally. Pipe tables and nothing else.
# Grid is allowed; simple and multiline are not. The rule that matters is
# that the table pandoc writes must be one `_is_markdown_table` can see and
# pandoc can read back, and a simple table satisfies neither: it marks columns
# by character position with no `|` anywhere, which is how nine of AlphaQ's
# twelve tables fell to plain text in the Word file while the HTML had all
# twelve. A grid table opens with `+---+`, which that check has always
# recognised.
#
# Turning grid off as well went further than the reason required, and it cost
# four tables per book: a table needing more than a pipe table can say -- a
# multi-line cell, a spanned column -- came back as prose and was left as raw
# LaTeX, so DeeR-VLA's DOCX carried 7 of its 11 tables. The hazard recorded
# for grid tables in `grid_tables_to_pipe` is a different one: it belongs to
# markdown a translator edits, where a widened CJK cell no longer lines up.
# Nothing edits this markdown between pandoc writing it and pandoc reading it.
_FRAGMENT_WRITER = ('markdown-simple_tables-multiline_tables+grid_tables'
                    '+pipe_tables-fenced_divs-native_divs-raw_html')


def _latex_fragment_to_markdown(latex, pandoc, work, name):
    """Render one LaTeX fragment to markdown. '' when pandoc cannot."""
    latex, _specs = normalise_tabular_preambles(latex)
    path = os.path.join(work, name)
    with open(path, 'w', encoding='utf-8', newline='') as fh:
        fh.write(latex + '\n')
    try:
        result = subprocess.run(
            [pandoc, '-f', 'latex', '-t', _FRAGMENT_WRITER, '--wrap=none',
             path],
            capture_output=True, text=True,
            encoding='utf-8', errors='replace', timeout=120)
    except (OSError, subprocess.SubprocessError):
        return ''
    return (result.stdout or '').strip() if result.returncode == 0 else ''


def _is_markdown_table(text):
    """Did pandoc actually produce a table, or just prose?"""
    return '|' in text or '+--' in text or '+==' in text


# A border may carry en/em dashes: a chunk that went through a smart-quotes
# pass has them, and a border this pattern does not recognise gets read as a
# content row -- which cut CafeQ's widest table in half.
_GRID_BORDER_RE = re.compile(r'^\+[-=:+‐-―]{3,}\+[ \t]*$')
# `|          +--------+--------+` -- the continuation border of a cell that
# spans rows. A pipe table has no way to say that, so a table containing one
# is left as it is rather than half-converted.
_INTERIOR_BORDER_RE = re.compile(r'\+[-=:‐-―]{3,}')


def grid_tables_to_pipe(md_text):
    """Rewrite any grid table as a pipe table. Returns (text, count).

    A grid table marks its columns by CHARACTER POSITION and pandoc lays one
    out by DISPLAY width, counting a Hangul syllable as two columns. Translate
    a cell and pad it to the same character count -- the obvious thing to do,
    and what a sub-agent does -- and the `|` no longer meet the `+`, so pandoc
    abandons the table and prints one cell per line with the pipes still in
    it. CafeQ shipped three that way.

    The format cannot be turned off at ingest: it is the only one pandoc can
    use for a spanning multi-deck header, and without it pandoc writes the
    literal text `[TABLE]` instead and the table is gone. So the conversion
    happens here, after translation, when nothing can drift any further.

    Cells are read from the `|` separators, never from column positions --
    the positions are exactly what has gone wrong by this point. A spanning
    cell keeps its text and the columns it covered are left empty.
    """
    lines = md_text.split('\n')
    out, i, count = [], 0, 0
    while i < len(lines):
        if not _GRID_BORDER_RE.match(lines[i]):
            out.append(lines[i])
            i += 1
            continue
        # The whole block first, so a table this cannot convert is copied
        # verbatim in one piece. Bailing out line by line let the scan
        # re-enter halfway down and eat the interior borders of a table it
        # had just decided to leave alone.
        stop = i
        while stop < len(lines) and lines[stop].strip():
            stop += 1
        ncols = len(re.findall(r'[-=:‐-―]{3,}', lines[i]))
        rows, clean = [], True
        for line in lines[i + 1:stop]:
            if _GRID_BORDER_RE.match(line):
                continue
            if '|' not in line or _INTERIOR_BORDER_RE.search(line):
                # Either not a row at all, or a row-spanning cell's
                # continuation border (`|      +-----+-----+`), a shape a
                # pipe table cannot express.
                clean = False
                break
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            rows.append((cells + [''] * ncols)[:ncols])
        j = stop
        if not clean or len(rows) < 2 or ncols < 2:
            out.extend(lines[i:stop])
            i = stop
            continue
        out.append('| ' + ' | '.join(rows[0]) + ' |')
        out.append('|' + '|'.join(['---'] * ncols) + '|')
        for row in rows[1:]:
            out.append('| ' + ' | '.join(row) + ' |')
        count += 1
        i = j
    return '\n'.join(out), count


_HEADER_END_RE = re.compile(r'\\(?:midrule|hline)\b')
_ROW_BREAK_RE = re.compile(r'\\\\')
_TR_RE = re.compile(r'<tr[^>]*>.*?</tr>', re.DOTALL)


def header_row_count(latex):
    """How many rows of this tabular are its header, per the LaTeX itself.

    pandoc finds a header by looking for a rule, and the answer it gives
    depends on which rules a paper happens to use: SINQ's main results table
    and three of AlphaQ's produced no <thead> at all, so the header rule never
    drew, the header never repeated across a page break, and not one cell was
    a <th>. Nine columns of numbers sat under nothing.

    Counting is not a heuristic: the header is whatever precedes the first
    \\midrule or \\hline that is not the top rule.
    """
    body = _header_body(latex)
    end = _first_body_rule(body)
    if end is None:
        return 0
    rows = len(_ROW_BREAK_RE.findall(body[:end]))
    total = len(_ROW_BREAK_RE.findall(body))
    return rows if 0 < rows < total else 0


def _header_body(latex):
    """The tabular's rows, with comments and the top rule out of the way."""
    body = latex[latex.find('}', latex.find('{')) + 1:]
    return re.sub(r'(?m)%.*$', '', body).replace('\\toprule', '', 1)


def _first_body_rule(body):
    """Where the header ends, skipping a rule that sits above every row.

    A booktabs table opens with \\toprule, which is removed above. An
    \\hline-ruled table opens with \\hline instead, and taking that one as the
    header's end would say the table has no header at all.
    """
    for m in _HEADER_END_RE.finditer(body):
        if _ROW_BREAK_RE.search(body[:m.start()]):
            return m.start()
    return None


_TBODY_RE = re.compile(r'<tbody[^>]*>(.*?)</tbody>', re.DOTALL)


_SOFT_RULE_RE = re.compile(r'\\addlinespace\b|\\\\\s*\[\s*\d')


def body_rule_rows(latex):
    """{row index: 'hard'|'soft'} for body rows that open a group.

    A paper marks its row groups two ways and pandoc renders neither. SINQ
    separates bit-widths with a rule; AlphaQ's Table 1 nests them -- a
    `\\midrule` between models and an `\\addlinespace` between the bit budgets
    inside each model -- so nine rows of numbers ran together with only the
    span label in the margin to break them up.

    Space is not reproducible here (the cells are one row tall either way), so
    the softer boundary becomes a lighter rule: solid between models, hairline
    between bit groups. The hierarchy survives, which is the part that was
    lost.
    """
    body = _header_body(latex)
    end = _first_body_rule(body)
    if end is None:
        return {}
    after = body[end:]
    after = after[_HEADER_END_RE.match(after).end():] \
        if _HEADER_END_RE.match(after) else after
    marked = {}
    for index, piece in enumerate(_ROW_BREAK_RE.split(after)[:-1]):
        if not index:
            continue
        if _HEADER_END_RE.search(piece):
            marked[index] = 'hard'
        elif _SOFT_RULE_RE.search(piece):
            marked[index] = 'soft'
    return marked


def mark_body_rules(html, latex):
    """Give each row that opens a group the class the print sheet draws."""
    marked = body_rule_rows(latex)
    if not marked:
        return html
    body = _TBODY_RE.search(html)
    if not body:
        return html
    rows = _TR_RE.findall(body.group(1))
    out = []
    for i, row in enumerate(rows):
        kind = marked.get(i)
        if kind:
            css = 'rule-above' if kind == 'hard' else 'rule-above-soft'
            row = re.sub(r'<tr\b', '<tr class="%s"' % css, row, count=1)
        out.append(row)
    return (html[:body.start()] + '<tbody>\n' + '\n'.join(out) + '\n</tbody>'
            + html[body.end():])


_ROWCOLOR_RE = re.compile(r'\\rowcolor\s*(?:\[[^\]]*\])?\s*\{[^{}]*\}')


def shaded_body_rows(latex):
    r"""({row index}, row count) for the body rows the paper shades.

    `\rowcolor[rgb]{ .900, .900, .900}` is how a results table says which
    rows are the authors' own. pandoc drops it, so VLA-Adapter's five
    `(Ours)` rows sat in the book looking like every competitor's. Indexed
    the way `body_rule_rows` indexes, because the same `<tbody>` rows are
    what both of them mark.

    The count comes back too: shading the wrong row would credit somebody
    else's numbers to the authors, so the caller can refuse when the source
    and the rendered table disagree about how many rows there are.
    """
    body = _header_body(latex)
    end = _first_body_rule(body)
    if end is None:
        return set(), 0
    after = body[end:]
    after = after[_HEADER_END_RE.match(after).end():] \
        if _HEADER_END_RE.match(after) else after
    pieces = _ROW_BREAK_RE.split(after)[:-1]
    return ({i for i, piece in enumerate(pieces) if _ROWCOLOR_RE.search(piece)},
            len(pieces))


def _add_row_class(row, name):
    """Add a class to a `<tr>`, keeping any it already carries."""
    m = re.match(r'<tr\b([^>]*)>', row)
    if not m:
        return row
    attrs = m.group(1)
    if 'class="' in attrs:
        attrs = re.sub(r'class="([^"]*)"',
                       lambda x: 'class="%s %s"' % (x.group(1), name),
                       attrs, count=1)
    else:
        attrs += ' class="%s"' % name
    return '<tr' + attrs + '>' + row[m.end():]


def mark_shaded_rows(html, latex):
    """Give the paper's own rows back the shading it marked them with.

    Returns (html, count). Runs before `split_row_groups`, which turns the
    single `<tbody>` into several and would leave the indices meaning
    something else.
    """
    marked, total = shaded_body_rows(latex)
    if not marked:
        return html, 0
    body = _TBODY_RE.search(html)
    if not body:
        return html, 0
    rows = _TR_RE.findall(body.group(1))
    if len(rows) != total:
        # Refuse rather than guess. A band on the wrong row is a claim about
        # whose result is whose, and it is not one this can make on a count
        # it already knows to be wrong.
        return html, 0
    out = [_add_row_class(row, 'row-shaded') if i in marked else row
           for i, row in enumerate(rows)]
    return (html[:body.start()] + '<tbody>\n' + '\n'.join(out) + '\n</tbody>'
            + html[body.end():]), len(marked)


def labelled_group_starts(latex):
    r"""Body row indices where a group carrying a label begins.

    `\multirow{10}{*}{Mixtral-8x7B}` labels ten rows and prints once, so the
    other nine carry no model name -- fine on one page, not fine across two.
    AlphaQ's table 1 broke inside such a group and the next page opened with
    `PMQ 7.42 ...` under an empty model and an empty bit budget: every row
    present, and nothing on the page saying what they are of.

    The `\multirow` itself is long gone by the time the book is built --
    conversion unwraps it to the plain label in the group's first row. What
    survives is the rule the paper drew between groups, which is the same
    boundary read a different way.
    """
    return sorted(i for i, kind in body_rule_rows(latex).items()
                  if kind == 'hard')


def split_row_groups(html, latex):
    """One <tbody> per labelled group, so a break lands between them.

    Returns (html, groups). The browser is told not to break inside a group
    and moves the page boundary to the next one; where a group is taller
    than the page it breaks anyway, which is all anything could do.
    """
    starts = labelled_group_starts(latex)
    if not starts:
        return html, 0
    body = _TBODY_RE.search(html)
    if not body:
        return html, 0
    rows = _TR_RE.findall(body.group(1))
    bounds = [s for s in starts if 0 < s < len(rows)]
    if not bounds:
        return html, 0
    bounds = [0] + bounds
    chunks = []
    for i, start in enumerate(bounds):
        stop = bounds[i + 1] if i + 1 < len(bounds) else len(rows)
        chunks.append('<tbody class="rowgroup">\n'
                      + '\n'.join(rows[start:stop]) + '\n</tbody>')
    return (html[:body.start()] + '\n'.join(chunks) + html[body.end():],
            len(chunks))


def promote_header_rows(html, latex):
    """Wrap the header rows in <thead> and make their cells <th>.

    Rebuilds the whole body region rather than splicing tags in: pandoc has
    already wrapped every row in one <tbody>, and opening a <thead> in front
    of it would leave that wrapper unbalanced.
    """
    if '<thead' in html:
        return html
    wanted = header_row_count(latex)
    if not wanted:
        return html
    body = _TBODY_RE.search(html)
    if not body:
        return html
    rows = _TR_RE.findall(body.group(1))
    if wanted >= len(rows):
        return html
    head = '\n'.join(re.sub(r'<(/?)td\b', r'<\1th', r) for r in rows[:wanted])
    rest = '\n'.join(rows[wanted:])
    return (html[:body.start()]
            + '<thead>\n%s\n</thead>\n<tbody>\n%s\n</tbody>' % (head, rest)
            + html[body.end():])


_SYMBOL_MATH_RE = re.compile(
    r'<math\b[^>]*>\s*<semantics>\s*<m[iox]>(&#?\w+;|[^<>&])</m[iox]>\s*'
    r'(?:<annotation\b[^>]*>.*?</annotation>\s*)?</semantics>\s*</math>',
    re.DOTALL)


def simplify_symbol_math(html):
    """A formula that is one symbol is a character. Returns (html, n).

    Chromium repeats a `<thead>` on every page its table runs onto, and out
    of a two-row header it drops the inline `<math>` when it does. AlphaQ's
    table 1 said `WikiText2 ↓` and `정확도 ↑` on the first page and neither on
    the second, so the continuation never said which direction was better --
    and every count still balanced, because the header was there.

    `<mo>↓</mo>` inside `<semantics>` draws exactly what the bare character
    draws. The bare character also survives the repeat.

    Only the header. A body cell is never repeated, so it never hits this.

    The character keeps a `math` class rather than standing bare, because
    the math check counts formulas asked for against formulas delivered and
    a symbol dropped out of that total is a hole the check would stop being
    able to see.
    """
    total = [0]

    def in_head(m):
        head, n = _SYMBOL_MATH_RE.subn(
            lambda s: '<span class="math-symbol">%s</span>' % s.group(1),
            m.group(0))
        total[0] += n
        return head

    return re.sub(r'(?s)<thead\b.*?</thead>', in_head, html), total[0]


_BIBITEM_LABEL_RE = re.compile(r'\\bibitem\s*\[([^\]]*)\]\s*\{([^{}]*)\}')
_LABEL_YEAR_RE = re.compile(r'^(.*?)\(\s*([^()]*?)\s*\)')
_FRAGMENT_CITE_RE = re.compile(
    r'\\cite([a-zA-Z]*)\s*(?:\[[^\]]*\])*\s*\{([^{}]*)\}')
# `\text{PQE}` is amsmath's, and outside math pandoc drops it with its body.
# CafeQ's table 7 printed no header at all over the column it is sorted by.
# `\textrm` says the same thing in both modes.
_TEXT_MACRO_RE = re.compile(r'\\text(?=\s*\{)')


_COLOR_DECL_RE = re.compile(r'\\color\s*(?:\[[^\]]*\])?\s*\{([^{}]*)\}')


def _cell_end(tex, pos):
    r"""Where a bare `\color` stops: the end of its table cell."""
    depth = 0
    i = pos
    while i < len(tex):
        ch = tex[i]
        if ch == '{':
            depth += 1
        elif ch == '}':
            if depth == 0:
                return i
            depth -= 1
        elif depth == 0:
            if ch == '&':
                return i
            if ch == '\\' and tex[i:i + 2] == '\\\\':
                return i
        i += 1
    return len(tex)


def rewrite_color_declarations(tex):
    r"""`{\color{red} 17.14}` -> `{\textcolor{red}{17.14}}`. (text, count).

    The declaration form colours everything to the end of its group and
    pandoc's reader drops it; the command form survives, which is why the
    word `빨간색` in SINQ's captions prints red while the values it points at
    do not. Twelve marked results in tables 3 and 4 came out black, and both
    captions tell the reader to look for red — so the caption promises
    something the page cannot deliver, and no count noticed because every
    number was present.
    """
    out, cursor, count = [], 0, 0
    for m in _COLOR_DECL_RE.finditer(tex):
        if m.start() < cursor:
            continue
        # `{\color{red} X}` scopes to its brace; a bare `\color{red} X` in a
        # cell scopes to the `&`. SINQ writes both, and a third: the
        # declaration inside `\textbf{...}`. The braces are always left in
        # place, or `\textbf` loses the argument it was holding.
        opening = tex.rfind('{', cursor, m.start())
        if opening >= 0 and not tex[opening + 1:m.start()].strip():
            close = _balanced_group(tex, opening)
            stop = close - 1 if close > 0 else -1
        else:
            stop = _cell_end(tex, m.end())
        if stop < 0:
            continue
        # A declaration that opens inside math must not be closed outside it.
        # `_cell_end` stops at the `&`, which on this paper's notation table
        # is past the closing `$`, so the rewrite swallowed that `$` into
        # `\textcolor{...}{...}` and left the maths unbalanced. pandoc then
        # abandoned the whole tabular, emitted no `<table>`, and the table was
        # simply absent from the book -- reported as "1 FAILED" and nothing
        # more. Clamp the scope to the maths it started in.
        run = tex[m.end():stop]
        marks = [i for i, ch in enumerate(run)
                 if ch == '$' and (i == 0 or run[i - 1] != '\\')]
        if len(marks) % 2:
            stop = m.end() + marks[0]
        body = tex[m.end():stop].strip()
        if not body:
            continue
        out.append(tex[cursor:m.start()])
        out.append('\\textcolor{%s}{%s}' % (m.group(1), body))
        cursor = stop
        count += 1
    out.append(tex[cursor:])
    return ''.join(out), count


def build_citation_labels(md_text):
    r"""{key: 'Hendrycks et al. 2021a'} from the inlined natbib bibliography.

    A citation inside a raw table never reaches the resolver: the float is
    kept verbatim from flat.tex, so `\citep{...}` arrives at pandoc, which
    has no bibliography here and drops the call together with its key. CafeQ's
    table 6 exists to say which benchmark came from which paper, and all
    sixteen sources were deleted out of it.
    """
    labels = {}
    for m in _BIBITEM_LABEL_RE.finditer(md_text):
        split = _LABEL_YEAR_RE.match(m.group(1))
        if not split:
            continue
        authors = split.group(1).replace('~', ' ').strip()
        year = re.sub(r'[{}]', '', split.group(2)).strip()
        if authors and year:
            labels[m.group(2).strip()] = '%s %s' % (authors, year)
    return labels


_BIB_ENTRY_RE = re.compile(r'@[A-Za-z]+\s*\{\s*([^,\s]+)\s*,(.*?)(?=\n@|\Z)',
                           re.DOTALL)
_BIB_FIELD_RE = re.compile(r'(?im)^\s*(author|year|date)\s*=\s*'
                           r'(\{(?:[^{}]|\{[^{}]*\})*\}|"[^"]*"|\d+)')


def _bib_surname(chunk):
    """The family name out of one BibTeX author entry."""
    chunk = re.sub(r'[{}\\]', '', chunk).strip()
    if ',' in chunk:                       # `Last, First`
        return chunk.split(',')[0].strip()
    parts = chunk.split()                  # `First Last`
    return parts[-1] if parts else ''


def build_citation_labels_from_bib(temp_dir):
    r"""{key: 'Authors Year'} from the `.bib` the paper shipped.

    `build_citation_labels` reads an INLINED `\bibitem` list, which is one of
    the two shapes a paper arrives in. VLA-Adapter ships a `.bib` and lets
    citeproc render it, so that map came back empty, `resolve_fragment_
    citations` had nothing to resolve with, and pandoc dropped all 51 `\citep`
    calls inside its tables: a 22-baseline comparison in which no number could
    be traced to the paper it came from. The mechanism was there and called;
    it was built from the one bibliography this paper does not use.

    Returns {} when there is no tarball or no `.bib`, so the inlined path is
    unaffected.
    """
    src = os.path.join(temp_dir or '', 'arxiv_src')
    if not temp_dir or not os.path.isdir(src):
        return {}
    labels = {}
    for root, _dirs, names in os.walk(src):
        for name in sorted(names):
            if not name.endswith('.bib'):
                continue
            try:
                with open(os.path.join(root, name), encoding='utf-8',
                          errors='replace') as fh:
                    text = fh.read()
            except OSError:
                continue
            for key, body in _BIB_ENTRY_RE.findall(text):
                fields = {}
                for field, raw in _BIB_FIELD_RE.findall(body):
                    fields[field.lower()] = raw.strip('{}" ')
                year = fields.get('year') or ''
                if not year:
                    year = (re.search(r'\b(1[89]|20)\d{2}\b',
                                      fields.get('date', '')) or [''])
                    year = year.group(0) if hasattr(year, 'group') else ''
                names_ = [a for a in re.split(r'\s+and\s+',
                                              fields.get('author', ''))
                          if a.strip()]
                surnames = [_bib_surname(a) for a in names_]
                surnames = [s for s in surnames if s]
                if not surnames or not year:
                    continue
                if len(surnames) == 1:
                    who = surnames[0]
                elif len(surnames) == 2:
                    who = '%s and %s' % (surnames[0], surnames[1])
                else:
                    who = '%s et al.' % surnames[0]
                labels.setdefault(key.strip(), '%s %s' % (who, year))
    return labels


_FRAGMENT_REF_RE = re.compile(r'\\ref\s*\{([^{}]+)\}')


def resolve_fragment_references(tex, numbers):
    r"""`\ref{TableD1}` inside a raw table -> `D1`. (text, done, missed).

    A protected float never meets `resolve_references`, so its `\ref` calls
    reach pandoc, which prints the key. VLA-Adapter's captions carried twenty
    of them, `[TableD1]` and `[AppendixG]` among others, each a pointer the
    reader cannot follow.

    Only the NUMBER is substituted, never the word. All twenty already had a
    Korean label in front of them, written by the translator, so supplying
    another would print it twice, and choosing between 부록 and 절 for a
    section key would be a guess this does not need to make.

    The number comes from the index, not from the key, because the two
    disagree: this paper labels its appendix H `AppendixG` and LaTeX prints
    H. A key that resolves to nothing is left exactly as written, so it stays
    visible rather than becoming a confident wrong letter.
    """
    missed = []

    def swap(m):
        value = numbers.get(m.group(1).strip())
        if value is None:
            missed.append(m.group(1).strip())
            return m.group(0)
        return str(value)

    out, total = _FRAGMENT_REF_RE.subn(swap, tex)
    return out, total - len(missed), sorted(set(missed))


def fragment_reference_numbers(temp_dir):
    r"""{label: printed number} for anything a `\ref` inside a float names.

    Empty without a temp dir. `expand_raw_latex_tables` is called with none
    in four existing tests and by any caller that only has markdown, and
    `build_label_index` joins the path unguarded.
    """
    if not temp_dir or not os.path.isdir(temp_dir):
        return {}
    numbers = {}
    for label, number in build_float_numbers(temp_dir).items():
        numbers.setdefault(label, str(number))
    for key, entry in build_label_index(temp_dir).items():
        # Keyed by the label exactly as written. The colon in `eq:pqe` is
        # part of the name, not a kind prefix -- an earlier version here
        # also registered the tail, which buys nothing (`\ref` always writes
        # the full label) and silently collides `eq:main` with `tab:main`.
        numbers.setdefault(key, str(entry[0]))
    return numbers


def resolve_fragment_citations(tex, labels):
    """Render a raw table's `\\citep{key}` the way the body renders it.

    Returns (text, count). A key with no entry leaves the whole call alone:
    a citation that is visibly unresolved can be fixed, and one silently
    attributed to the wrong paper cannot be noticed at all.
    """
    if not labels:
        return tex, 0
    count = [0]

    def sub(m):
        keys = [k.strip() for k in m.group(2).split(',') if k.strip()]
        shown = [labels[k] for k in keys if k in labels]
        if not keys or len(shown) != len(keys):
            return m.group(0)
        count[0] += 1
        joined = '; '.join(shown)
        if m.group(1) in ('t', 'author', 'alt'):
            head, _sep, year = joined.rpartition(' ')
            return '%s (%s)' % (head, year) if head else joined
        return '(%s)' % joined

    return _FRAGMENT_CITE_RE.sub(sub, tex), count[0]


_CELL_WRAPPER_HEAD_RE = re.compile(
    r'\\(?:makecell|thead)\s*(?:\[[^\]\n]*\])?\s*(?=\{)')
# The row break INSIDE such a cell. It separates two lines of one cell, not
# two table rows, so it becomes a space rather than a break.
_CELL_ROW_BREAK_RE = re.compile(r'\s*\\\\\s*')


def unwrap_table_cell_wrappers(md_text):
    r"""`\makecell{a\\b}` -> `a b`. Returns (text, count).

    makecell's job is a line break inside one cell, and pandoc has no reader
    for it — so the command AND its argument are dropped and the cell arrives
    EMPTY. Measured: a cell holding `\makecell{one\\two}` renders as `<td></td>`
    with nothing said, the same silent swallow as K110's wrappers but one cell
    at a time. PaLM has 92 of them and `\thead` behaves identically.

    Joining the lines with a space keeps every word; only the line break is
    lost, which is typesetting rather than content.
    """
    count = 0
    while True:
        m = _CELL_WRAPPER_HEAD_RE.search(md_text)
        if not m:
            return md_text, count
        open_at = md_text.index('{', m.end() - 1)
        close = _balanced_group(md_text, open_at)
        if close < 0:
            return md_text, count
        inner = md_text[open_at + 1:close - 1]
        md_text = (md_text[:m.start()]
                   + _CELL_ROW_BREAK_RE.sub(' ', inner).strip()
                   + md_text[close:])
        count += 1


_TABBING_RE = re.compile(r'\\begin\{tabbing\}(.*?)\\end\{tabbing\}', re.S)
# The tab-stop template line: escaped spaces and `\=` marks ending in `\kill`.
# It positions the columns and prints nothing at all.
_TABBING_KILL_RE = re.compile(r'^[^\n]*\\kill[ \t]*$\n?', re.M)
_TABBING_STOP_RE = re.compile(r'\\[=>]')
# A code fence renders nothing, so `$\,-$` prints as five characters where the
# paper prints a minus sign. Shor's three listings hold nineteen of these, and
# the whole set is eleven fragments using two commands — `\,` and his own
# `\mod{n}`. The delimiters and the spacing come off; anything else is left
# standing rather than guessed at, so a macro the fence cannot render stays
# visible instead of quietly becoming something wrong.
_TABBING_MATH_RE = re.compile(r'\$([^$\n]*)\$')
# No letter boundary: `\,` is a control SYMBOL, complete in two characters, so
# the next character is never part of its name. Requiring a non-letter after it
# left `result_{\,i}` standing in the third listing.
_MATH_SPACING_RE = re.compile(r'\\[,;:!]')


def _tabbing_math(m):
    return _MATH_SPACING_RE.sub('', m.group(1))
_TABBING_FONT_RE = re.compile(r'\{\s*\\(?:it|rm|bf|tt|sf|sc)\s+([^{}]*)\}')


_ONE_ARG_DEF_RE = re.compile(
    r'\\(?:new|renew|provide)command\s*\{?\s*\\([A-Za-z]+)\s*\}?\s*\[1\]\s*\{')


def read_one_argument_macros(temp_dir):
    r"""{name: body-with-#1} for the paper's own single-argument shorthand.

    `read_math_macros` refuses these on purpose — expanding a macro properly
    needs a real expander and guessing corrupts formulas that render today
    (K121). This is a much smaller claim, used only inside a `tabbing` fence,
    where nothing renders at all and the alternative is printing `\mod{n}` at
    the reader. One argument, one body, and anything carrying a conditional is
    left alone.
    """
    macros = {}
    flat = os.path.join(temp_dir or '', 'flat.tex')
    if not os.path.isfile(flat):
        return macros
    try:
        with open(flat, 'r', encoding='utf-8', errors='replace') as fh:
            tex = strip_tex_comments(fh.read(), keep_definitions=True)
    except OSError:
        return macros
    tex = tex.split(r'\begin{document}')[0]
    for m in _ONE_ARG_DEF_RE.finditer(tex):
        close = _balanced_group(tex, m.end() - 1)
        if close < 0:
            continue
        body = tex[m.end():close - 1]
        if body.count('#1') != 1 or '#2' in body or r'\if' in body:
            continue
        macros[m.group(1)] = body
    return macros


def _expand_one_arg(text, macros):
    r"""`\mod{n}` -> ` (mod n)` for the macros this paper defines."""
    for name, body in macros.items():
        head = re.compile(r'\\%s(?![A-Za-z])\s*\{' % re.escape(name))
        while True:
            m = head.search(text)
            if not m:
                break
            close = _balanced_group(text, m.end() - 1)
            if close < 0:
                break
            arg = text[m.end():close - 1]
            text = text[:m.start()] + body.replace('#1', arg) + text[close:]
    return text


def unwrap_tabbing(md_text, macros=None):
    r"""Turn a `tabbing` environment into a code block. Returns (text, count).

    `tabbing` is how a 1990s paper sets aligned pseudocode, and pandoc has no
    reader for it — so on the HTML path the whole environment is dropped
    without a word, exactly as K110's wrappers were. Shor's three algorithm
    listings vanished that way, and only the raw-block fidelity count saw it.

    A code fence is the honest target: the environment's whole purpose here is
    preformatted alignment, which is what a fence preserves. The tab stops
    become indentation, the `\kill` template line goes (it prints nothing),
    and the old font switches around variable names are unwrapped.
    """
    count = [0]

    def convert(m):
        body = _TABBING_KILL_RE.sub('', m.group(1))
        # Before the font unwrap, deliberately: `\mod{n}` expands to
        # `{\rm \ (mod\ }n)`, and it is that unwrap which turns it into text.
        if macros:
            body = _expand_one_arg(body, macros)
        body = _TABBING_FONT_RE.sub(r'\1', body)
        body = _TABBING_STOP_RE.sub('    ', body)
        body = _TABBING_MATH_RE.sub(_tabbing_math, body)
        # `\\` ends a row; `\ ` is an escaped space holding indentation.
        # The source usually breaks the line after `\\` as well, so replacing
        # it with a newline doubles every gap and the listing prints
        # double-spaced. Take the newline that follows with it.
        body = re.sub(r'\\\\[ \t]*\n?', '\n', body).replace('\\ ', ' ')
        lines = [line.rstrip() for line in body.split('\n')]
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        if not lines:
            return ''
        count[0] += 1
        return '\n```\n%s\n```\n' % '\n'.join(lines)

    return _TABBING_RE.sub(convert, md_text), count[0]


_AT_SPACING_RE = re.compile(r'@\{[^{}]*\}')
# Brace-aware: a spec like `{|c|@{}}` contains braces, and a flat
# `\{[^{}]*\}` cannot match it. A flat pattern reported these specs as plain
# `{c}` and sent three hypotheses down the wrong path before the real shape
# turned up.
_MULTICOLUMN_SPEC_RE = re.compile(
    r'(\\multicolumn\s*\{[^{}]*\}\s*\{)((?:[^{}]|\{[^{}]*\})*)(\})')


def drop_multicolumn_spacing(tex):
    r"""Remove `@{}` from `\multicolumn` column specs. Returns (text, count).

    `@{}` suppresses inter-column padding and says nothing about content, but
    pandoc refuses a `\multicolumn{3}{|c|@{}}` outright — measured: the same
    table converts with `{|c|}` and not with `{|c|@{}}`, while `@{}` in the
    TABULAR spec is read without complaint. Shor's two truth-table floats were
    dropped whole on the HTML path over it, and pandoc's markdown reader drops
    a raw block without a word (K57), so only the table-fidelity count noticed.
    """
    return _MULTICOLUMN_SPEC_RE.subn(
        lambda m: m.group(1) + _AT_SPACING_RE.sub('', m.group(2))
        + m.group(3), tex)


def expand_raw_latex_tables(md_text, pandoc=None, math_mode='mathml',
                            output='html', temp_dir=None):
    """Convert raw LaTeX tables into real tables.

    `output='html'` gives HTML tables carrying the sizing classes the print
    sheet needs. `output='markdown'` gives markdown tables instead, which is
    what the DOCX path requires: raw HTML survives ONLY the HTML path, and
    injecting `<table>` left book.docx with zero tables and no complaint from
    any check. pandoc cannot express every LaTeX table as markdown, so the two
    are produced separately rather than one being derived from the other.

    Returns (new_text, converted, failed). A table pandoc cannot read is left
    exactly as it was, so check_table_fidelity reports the shortfall instead of
    the build quietly shipping a book with a hole in it.
    """
    tables = find_raw_latex_tables(md_text)
    if not tables:
        return md_text, 0, 0

    pandoc = pandoc or resolve_pandoc()
    if not pandoc:
        print("WARNING: %d raw LaTeX table(s) need pandoc to be expanded; "
              "they will be missing from the output" % len(tables))
        return md_text, 0, len(tables)

    converted = failed = 0
    cite_labels = build_citation_labels(md_text)
    if not cite_labels:
        # No inlined `\bibitem` list. The paper shipped a `.bib` and let
        # citeproc render it, so the keys live there instead (K152).
        cite_labels = build_citation_labels_from_bib(temp_dir)
    ref_numbers = fragment_reference_numbers(temp_dir)
    refs_done, refs_missed = 0, []
    shaded_rows = 0
    pieces, cursor = [], 0
    with tempfile.TemporaryDirectory(prefix='tb-tex-') as work:
        for n, t in enumerate(tables):
            # A band label is written `\multirow{4}{*}{\rotatebox{90}{...}}`
            # and reaches here whole, because a protected table float is kept
            # verbatim all the way from flat.tex. pandoc drops both calls with
            # their bodies, so nine of SINQ's tables rendered their group
            # column empty: the same four method rows twice, with nothing
            # saying which block was 3-bit and which was 4-bit.
            t['bare'], _labels = arxiv_backend.unwrap_rotatebox(t['bare'])
            t['bare'], _notes = arxiv_backend.unwrap_table_notes(t['bare'])
            t['bare'], _at = drop_multicolumn_spacing(t['bare'])
            # A protected float never met the citation resolver or the
            # leftover-command pass, so both have to happen here or the
            # reader loses the source beside a benchmark and the header
            # above a column.
            for part in ('bare', 'caption', 'notes'):
                if not t.get(part):
                    continue
                fixed, _n = resolve_fragment_citations(t[part], cite_labels)
                fixed, done, missed = resolve_fragment_references(
                    fixed, ref_numbers)
                refs_done += done
                refs_missed.extend(missed)
                fixed, _c = rewrite_color_declarations(fixed)
                t[part] = _TEXT_MACRO_RE.sub(r'\\textrm', fixed)
            if output == 'markdown':
                body = _latex_fragment_to_markdown(t['bare'], pandoc, work,
                                                   'table%d.tex' % n)
                if not _is_markdown_table(body):
                    failed += 1
                    continue
                if t['caption']:
                    cap = _latex_fragment_to_markdown(t['caption'], pandoc, work,
                                                      'cap%d.tex' % n)
                    if cap:
                        body = '**%s**\n\n%s' % (cap.replace('\n', ' ').strip(), body)
                if t.get('notes'):
                    note = _latex_fragment_to_markdown(t['notes'], pandoc, work,
                                                       'note%d.tex' % n)
                    if note:
                        body = '%s\n\n%s' % (body, note.strip())
                pieces.append(md_text[cursor:t['start']])
                pieces.append('\n\n' + body + '\n\n')
                cursor = t['stop']
                converted += 1
                continue

            html = _latex_fragment_to_html(t['bare'], pandoc, work,
                                           'table%d.tex' % n, math_mode=math_mode)
            if '<table' not in html:
                failed += 1
                continue
            html = promote_header_rows(html, t['bare'])
            html = mark_body_rules(html, t['bare'])
            html, _shaded = mark_shaded_rows(html, t['bare'])
            shaded_rows += _shaded
            html, _groups = split_row_groups(html, t['bare'])
            html, _symbols = simplify_symbol_math(html)
            # A paper table can carry ten columns; at body size that wraps every
            # header mid-word. Tag it so the print sheet can step the size down.
            rows = re.findall(r'<tr>.*?</tr>', html, re.DOTALL)
            columns = max((r.count('<td') + r.count('<th')) for r in rows) if rows else 0
            if columns > 6:
                html = html.replace('<table>', '<table class="cols-many">', 1)
            elif columns > 4:
                html = html.replace('<table>', '<table class="cols-wide">', 1)
            if t['caption']:
                cap = _latex_fragment_to_html(t['caption'], pandoc, work,
                                              'cap%d.tex' % n, inline=True,
                                              math_mode=math_mode)
                if cap:
                    html = re.sub(r'<table[^>]*>',
                                  lambda m: m.group(0) + '\n<caption>%s</caption>' % cap,
                                  html, count=1)
            if t.get('notes'):
                note = _latex_fragment_to_html(t['notes'], pandoc, work,
                                               'note%d.tex' % n,
                                               math_mode=math_mode)
                if note:
                    html += '\n<div class="table-notes">%s</div>' % note.strip()
            # --mathml keeps the original TeX in <annotation>, so the block
            # is full of backslashes -- and the markdown reader still applies
            # backslash escapes inside a raw HTML block. That is what ate the
            # '<' in <mi>\</mi> and printed a literal </mi> in the cell.
            # Numeric entities are inert to markdown and decode back to a
            # backslash in the HTML parser, so the TeX annotation stays intact.
            html = html.replace('\\', '&#92;')
            pieces.append(md_text[cursor:t['start']])
            # Blank lines both sides so the markdown reader sees one raw HTML
            # block rather than an inline run inside a paragraph.
            pieces.append('\n\n' + html + '\n\n')
            cursor = t['stop']
            converted += 1
    pieces.append(md_text[cursor:])
    if refs_done or refs_missed:
        print("Raw LaTeX tables: %d cross-reference(s) in captions resolved"
              % refs_done)
    if refs_missed:
        # Named, not swallowed: a key nobody can resolve prints as itself and
        # the reader meets `[TableD1]` where a number belongs.
        print("  %d key(s) had no number and will print raw: %s"
              % (len(set(refs_missed)), ', '.join(sorted(set(refs_missed)))))
    if shaded_rows:
        print("Raw LaTeX tables: %d row(s) the paper shades marked as its own"
              % shaded_rows)
    return ''.join(pieces), converted, failed

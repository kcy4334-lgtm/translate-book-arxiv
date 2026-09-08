# -*- coding: utf-8 -*-
r"""Words inside a table that step 4.6 was supposed to translate.

`untranslated_captions` in `merge_and_build` already stops a build whose
table CAPTIONS are still in the source language. It works because a caption
is a sentence: "the longest run of source prose words this shares with the
original" separates a translation from a copy in any target language.

A header cell is one to three words, so a run of four never occurs in one
and that test is blind to it by construction. Step 4.6 asks for three more
things besides the caption -- column headers, rotated row-group labels, and
the prose inside `\begin{tablenotes}` -- and until this module nothing
checked any of them. The build stopped on the caption and shipped the
header, which is the same defect one row lower and just as visible: a
results table in a Korean book with `Method` and `Params` across the top.

Two different problems, so two different tests:

  * `tablenotes` is prose. It is handed back to the caller and goes through
    the same three caption tests, because it is the same kind of thing.
  * a header cell is a word, and what separates `Method` (must be
    translated) from `OpenVLA` (must not) is neither case -- both are
    capitalised -- nor length. It is that one is common table vocabulary
    with a translation in every language and the other is a name.

That is a closed vocabulary, and inventing it would put false positives
into a gate that stops builds. It was read off the corpus instead: every
cell between `\toprule` and `\midrule` in the five papers on this machine,
counted by how many papers carry it. The split was clean. `Method` (3
papers), `Avg` (4), `Params` (2), `Bits`, `Model`, `Mem`, `Tok`, `Prefill`,
`Decode` are generic; `PIQA`, `MMLU`, `C4`, `WinoGrande`, `Qwen3-14B` are
names. Frequency alone does not separate them -- `PIQA` appears in two
papers, exactly like `Params` -- so the list is curated, with the observed
words as its spine.

The list is the COMMON CASE and is not exhaustive, deliberately. A gate
that stops a build has to be right when it fires, so a word earns its place
by being one that, standing alone in a cell of a book translated out of
English, is a defect with no second reading. Ambiguous ones are left out on
purpose: `Ours` and `Top-1` are routinely kept as they are in a correct
translation. Adding a word later costs one line.
"""
from __future__ import unicode_literals

import re

import latex_rows

# Read off the corpus, then extended with the siblings any results table
# uses. Lowercased; `header_word` does the folding.
HEADER_WORDS = frozenset([
    # observed in the five papers on this machine
    'method', 'model', 'models', 'avg', 'average', 'params', 'bits',
    'mem', 'memory', 'tok', 'tokens', 'prefill', 'decode', 'tasks', 'task',
    # the ordinary vocabulary of a results table
    'accuracy', 'acc', 'baseline', 'batch', 'cost', 'count', 'dataset',
    'datasets', 'depth', 'epoch', 'epochs', 'error', 'input', 'latency',
    'layer', 'layers', 'length', 'loss', 'mean', 'median', 'metric',
    'metrics', 'name', 'notes', 'output', 'overall', 'precision', 'rank',
    'rate', 'ratio', 'recall', 'result', 'results', 'score', 'setting',
    'settings', 'size', 'speed', 'stage', 'steps', 'test', 'throughput',
    'time', 'total', 'train', 'type', 'value', 'variant', 'width',
])

# `\rotatebox{90}{Method}` is a row-group label, which step 4.6 also asks
# for. The brace content is the word; the command and its angle are not.
_WRAPPED_RE = re.compile(
    r'\\(?:rotatebox|multicolumn|multirow)\s*(?:\[[^\]]*\])?'
    r'\s*\{[^{}]*\}(?:\s*\{[^{}]*\})?\s*\{([^{}]*)\}')
_COMMENT_RE = re.compile(r'(?<!\\)%.*')
_MATH_RE = re.compile(r'\$[^$]*\$')
_COMMAND_RE = re.compile(r'\\[A-Za-z@]+\*?')
# A unit or a direction marker rides along with the word and is not part of
# it: `Acc. (%)`, `WikiText2` with a down arrow, `Time (s)`.
_UNIT_RE = re.compile(r'\([^()]*\)|[\u2191\u2193\u2190\u2192]')

_TABULAR_RE = re.compile(
    r'\\begin\{(tabular[x*]?|longtable|tabu)\}'
    r'\s*(?:\[[^\]]*\])?\s*(?:\{[^{}]*\})?(.*?)\\end\{\1\}', re.DOTALL)


def cell_surface(cell):
    r"""The words of a cell with its LaTeX taken off.

    Rules ride along at the front of the first cell of a row -- `\toprule
    \textbf{Bits}` is one cell, not two -- and a header is commonly wrapped:
    `\multirow{2}{*}{Avg.}`. Both have to come off before the text can be
    compared with anything, and both have to come off the REPORTED string
    too. Printing `\multirow{2}{*}{Avg.}` at somebody whose build just
    stopped tells them about LaTeX when the answer is the word `Avg.`
    """
    text = _WRAPPED_RE.sub(r' \1 ', cell or '')
    text = _COMMENT_RE.sub(' ', text)
    text = _MATH_RE.sub(' ', text)
    text = _COMMAND_RE.sub(' ', text)
    text = text.replace('{', ' ').replace('}', ' ')
    text = _UNIT_RE.sub(' ', text)
    return ' '.join(text.split()).strip(' .,:;-')


def header_word(cell):
    r"""The common table word this cell IS, or None.

    `Acc. (%)` is `acc`; `HellaSwag` with an up arrow is not a word on the
    list and comes back None; `Total Time (s)` is two words and is not a
    single vocabulary entry, so it comes back None as well. Matching only a
    whole cell is what keeps the gate quiet: a cell that merely CONTAINS
    `time` is prose, and prose is the caption test's job.
    """
    text = cell_surface(cell)
    if not text or ' ' in text:
        return None
    folded = text.lower()
    return folded if folded in HEADER_WORDS else None


def table_cells(latex):
    r"""Every cell of every tabular in this float, in document order.

    Rows are cut by `latex_rows`, not by `re.split(r'\\\\')`: `\thead{Total
    \\ Time}` is ONE cell holding a line break, and splitting on every `\\`
    read it as two, which put `Total` and `Time` in front of the gate as
    separate untranslated headers.
    """
    for _env, body in _TABULAR_RE.findall(latex or ''):
        for row in latex_rows.split_rows(body):
            for cell in row.split('&'):
                yield cell


def untranslated_header_cells(latex):
    r"""The common table words this float still spells in English.

    Deduplicated, in first-seen order: a header repeated down a long table
    is one defect, not thirty, and a gate that prints thirty lines for it
    buries the second table.
    """
    seen, out = set(), []
    for cell in table_cells(latex):
        word = header_word(cell)
        if word and word not in seen:
            seen.add(word)
            out.append(cell_surface(cell))
    return out


# `tablenotes` is deliberately NOT extracted here. `extract_table_notes` in
# `merge_and_build` already does it, and `find_raw_latex_tables` hands the
# result back on every table as `entry['notes']`. A second extractor would
# be a second thing to keep true, and the two would drift on the first
# paper that spells `\item[$\dagger$]` in a way only one of them reads.

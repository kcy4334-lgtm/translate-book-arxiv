#!/usr/bin/env python3
"""
math_guard.py - Keep formulas, citations and raw LaTeX tables out of reach of
the translator.

The problem
-----------
A sub-agent translating a chunk sees LaTeX as text. Given `$\\alpha_i$` it may
translate a variable name, reflow the span, "fix" a backslash, or drop the
formula entirely — and the damage is invisible until someone reads the final
PDF. Instructing it not to is necessary but not sufficient.

The mechanism
-------------
Before chunking, every math span is replaced with an opaque token
(`⟦M0042⟧`). The token is stored in a per-chunk sidecar and substituted back
during the merge, so the translator never sees LaTeX at all and cannot corrupt
it. A validation gate then proves every token came back exactly once.

Token choice: U+27E6/U+27E7 MATHEMATICAL WHITE SQUARE BRACKETS. Absent from real
prose, carry no markdown meaning, contain no spaces (so a translator cannot
reflow inside one), survive markdown->HTML unchanged, and are visibly distinct
from CJK brackets so a CJK translator will not "localize" them.

Prefixes: M = math, C = citation, T = raw LaTeX table/float.
"""

import io
import json
import os
import re
import sys

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError, OSError):
        pass


TOKEN_RE = re.compile(r'\u27e6([MCT])(\d{4,})\u27e7')
SIDECAR_SUFFIX = '.math.json'
SIDECAR_VERSION = 1

_MATH_ENV = (r'equation|align|gather|multline|split|eqnarray|displaymath'
             r'|alignat|flalign|cases|array|CD|aligned|gathered')
_LATEX_FLOAT = (r'table|figure|tabular|longtable|tabularx|wraptable|wrapfigure'
                r'|algorithm|algorithmic')

# Ordered: longest / most specific first. Display before inline so `$$` is never
# matched as two `$`.
_SPANS = [
    ('T', 'float', re.compile(
        r'\\begin\{(' + _LATEX_FLOAT + r')\*?\}.*?\\end\{\1\*?\}', re.S)),
    # Note: pandoc's LaTeX reader emits `$$\begin{align}...\end{align}$$`, so
    # this rule fires first and the `$$...$$` rule below then wraps the
    # resulting token — a token nested inside another token's stored LaTeX.
    # That nesting is handled by spans_for_chunk() and restore(); do NOT try to
    # absorb the surrounding `$$` here, because a `$$` that turns out to belong
    # to a neighbouring span leaves the delimiters unbalanced and pandoc then
    # reads the prose between two formulas as math.
    ('M', 'display', re.compile(
        r'\\begin\{(' + _MATH_ENV + r')\*?\}.*?\\end\{\1\*?\}', re.S)),
    ('M', 'display', re.compile(r'(?<!\\)\$\$.*?(?<!\\)\$\$', re.S)),
    ('M', 'display', re.compile(r'(?<!\\)\\\[.*?(?<!\\)\\\]', re.S)),
    ('M', 'inline', re.compile(r'(?<!\\)\\\(.*?(?<!\\)\\\)', re.S)),
    # Inline $...$: no newline, no nested $. `(?!\s)` and `(?!\d)` keep prose
    # like "$5 and $6 each" from being read as a formula.
    # A subscript hung on a word: `BERT$_{\textsc{BASE}}$`, `ResNet$_{50}$`.
    # The general rule below refuses a `$` preceded by a word character — that
    # is what keeps "costs $5 and $6" out of maths — so this span is never
    # opened, and the dollars then pair off BY ONE: BERT's two model sizes
    # became `BERT$_{\textsc{BASE}}⟦M⟧_{\textsc{LARGE}}$`, with the whole BASE
    # specification swallowed into a token nobody could see was wrong. Three
    # papers reported the same shape independently.
    #
    # Placed first, and requiring `_` or `^` immediately after the `$`, which
    # a price never has.
    ('M', 'inline', re.compile(
        r'(?<=\w)\$[_^](?:[^$\n\\]|\\.)+?(?<!\\)\$(?!\d)')),
    # A `$` pair nested inside a braced argument. `\text{}` and `\mathrm{}`
    # switch to TEXT mode, so an author who wants a symbol back inside one
    # writes `$...$` again -- Neural ODE has
    # `$p(\mathrm{event at time $t$} \mid \dots)$`, which is ordinary LaTeX.
    #
    # Every rule below forbids `$` inside a span, so that formula is closed at
    # the inner `$` and the dollars pair off BY ONE from there -- the same
    # desynchronisation the subscript rule above was written for, in a
    # different shape. It cost this paper a whole passage: the chunk agent was
    # handed half a formula welded to the prose after it, and the region came
    # back part translated, part raw.
    #
    # Placed before the general rule, and it only matches when a brace group is
    # actually present, so a span without one is still handled below.
    ('M', 'inline', re.compile(
        r'(?<![\\$\w])\$(?!\s)'
        r'(?:[^$\n\\{]|\\[^\n])*'
        r'\{(?:[^{}$\\]|\\[^\n]|\$(?:[^$\n\\]|\\[^\n])+\$'
        r'|\{(?:[^{}$\\]|\\[^\n])*\})*\}'
        r'(?:[^$\n\\]|\\[^\n])*'
        r'(?<!\\)\$(?!\d)')),
    ('M', 'inline', re.compile(r'(?<![\\$\w])\$(?!\s)(?:[^$\n\\]|\\.)+?(?<!\\)\$(?!\d)')),
    # The same span, wrapped across lines. An author who writes a `\frac`
    # inline lays it out over several lines, and the rule above — which forbids
    # a newline on purpose — walks straight past it: the GAN paper's
    # `$D^*(x) = \frac{...}{...}$` reached a chunk as raw LaTeX with a
    # placeholder embedded in it, which is exactly what the guard exists to
    # prevent a translator from ever seeing.
    #
    # A NEWLINE is allowed; a BLANK line is not. A `$` pair reaching across a
    # paragraph break is nearly always two stray dollars rather than one
    # formula, and that is the desynchronisation the single-line rule was
    # written to avoid. Bounded in length for the same reason.
    ('M', 'inline', re.compile(
        r'(?<![\\$\w])\$(?!\s)'
        r'(?:[^$\n\\]|\\.|\n(?![ \t]*\r?\n)){1,800}?'
        r'(?<!\\)\$(?!\d)')),
    ('C', 'cite', re.compile(r'(?<!\\)\[@[^\]\n]{1,400}\]')),
]

_CODE_FENCE_RE = re.compile(r'^```.*?^```', re.S | re.M)
_INLINE_CODE_RE = re.compile(r'(?<!`)(`+)(?!`).*?(?<!`)\1(?!`)', re.S)

# NOTHING may stand between the backslash and the newline. The pattern used to
# allow spaces, on the stated grounds that "a lone trailing backslash before a
# newline is never valid LaTeX" — and that is false. `\ ` is the control space,
# TeX's explicit thin space, and Shor writes `R_j \ = \ ` for exactly that.
# Allowing the whitespace rewrote it as a row separator inside an `equation`,
# which texmath refuses, so both his gate tables printed as source in a shipped
# book. Across the corpus the loose form matched two spans and both were this.
# A truncated separator has nothing after the backslash, so the narrow form
# still repairs every case the loose one was written for.
_ROW_SEP_RE = re.compile(r'(?<!\\)\\(?=\r?\n)')
_BLANK_LINE_RE = re.compile(r'\r?\n[ \t]*(?:\r?\n[ \t]*)+')


def _mask_code(text):
    """Hide code so a `$` in a shell snippet is not mistaken for math."""
    store = []

    def take(m):
        store.append(m.group(0))
        return f'\x00C{len(store) - 1}\x00'

    text = _CODE_FENCE_RE.sub(take, text)
    text = _INLINE_CODE_RE.sub(take, text)
    return text, store


def _unmask_code(text, store):
    return re.sub(r'\x00C(\d+)\x00', lambda m: store[int(m.group(1))], text)


def repair_display_math(latex):
    r"""Repair two defects pandoc's LaTeX reader introduces into display math.

    1. Row separators. Measured: `a &= b \\` inside an align arrives as
       `a &= b \` — one backslash — so every multi-row
       align/split/gather/cases/matrix silently fails to render.
       ~~A lone trailing backslash before a newline is never valid LaTeX, which
       makes this repair provably safe.~~ It is: `\ ` is the control space.
       The repair is safe only for a backslash with NOTHING after it, which is
       the shape the truncation produces; see `_ROW_SEP_RE` (K136).

    2. Blank lines. pandoc preserves the source's blank lines inside the
       formula, but a blank line is a paragraph break to pandoc's *markdown*
       reader, so `$$` display math terminates there — the opening `$$` loses
       its partner and the following prose is swallowed as math. A blank line is
       not valid inside a LaTeX math environment either, so collapsing it is
       also safe.
    """
    latex = _ROW_SEP_RE.sub(r'\\\\', latex)
    return _BLANK_LINE_RE.sub('\n', latex)


# Anything a formula needs and ordinary bracketed text does not.
_MATHY_RE = re.compile(r'[\\^_=<>+*/|]|\d\s*[.,]?\s*\d|[Ͱ-Ͽ]')


def looks_like_math(body):
    r"""Could `\[body\]` be a formula, or is it a bracket someone escaped?

    pandoc's markdown writer escapes a literal `[` as `\[`, and our reader has
    tex_math_single_backslash on, so it reads that straight back as display
    maths. SINQ's `\textbf{Overhead [\%]}` -- the units of a column -- became
    a display formula holding one `%`, which renders as nothing at all: the
    header read "오버헤드" and then stopped.

    A formula carries a command, an operator, a relation, a subscript or a
    Greek letter. A unit in brackets carries none of those.
    """
    return bool(_MATHY_RE.search(body))


def protect(text, start=1):
    """Replace every math/citation/float span with an opaque token.

    Returns (protected_text, spans) where spans is a list of
    {token, kind, prefix, latex} in document order.
    """
    text, code_store = _mask_code(text)
    spans = []
    counter = [start - 1]

    for prefix, kind, pattern in _SPANS:
        def take(m, _prefix=prefix, _kind=kind):
            if (_kind == 'display' and m.group(0).startswith('\\[')
                    and not looks_like_math(m.group(0)[2:-2])):
                return m.group(0)          # an escaped bracket, not a formula
            counter[0] += 1
            latex = m.group(0)
            if _kind in ('display', 'float'):
                latex = repair_display_math(latex)
            token = f'\u27e6{_prefix}{counter[0]:04d}\u27e7'
            spans.append({'token': token, 'kind': _kind,
                          'prefix': _prefix, 'latex': latex})
            return token

        text = pattern.sub(take, text)

    text = _unmask_code(text, code_store)
    return text, spans


def restore(text, spans):
    """Substitute tokens back to their original LaTeX.

    Loops to a fixpoint so a token stored inside another token's LaTeX is also
    resolved. Idempotent: text containing no tokens is returned unchanged.
    """
    by_token = {s['token']: s['latex'] for s in spans}
    for _ in range(8):
        before = text
        for token, latex in by_token.items():
            if token in text:
                text = text.replace(token, latex)
        if text == before:
            break
    return text


def verify(source_text, output_text, spans=None):
    """Compare token usage between a source chunk and its translation.

    Returns {'missing': [...], 'duplicated': [...], 'foreign': [...]}.
      missing    - token in the source but absent from the translation
                   (a formula vanished from the book)
      duplicated - token appears more than once in the translation
      foreign    - token in the translation that is not in the source
                   (the translator invented one)
    """
    src_tokens = [m.group(0) for m in TOKEN_RE.finditer(source_text)]
    if spans:
        known = {s['token'] for s in spans}
        src_tokens = [t for t in src_tokens if t in known] or src_tokens

    out_counts = {}
    for m in TOKEN_RE.finditer(output_text):
        out_counts[m.group(0)] = out_counts.get(m.group(0), 0) + 1

    missing = [t for t in src_tokens if out_counts.get(t, 0) == 0]
    duplicated = [t for t in src_tokens if out_counts.get(t, 0) > 1]
    foreign = [t for t in out_counts if t not in set(src_tokens)]
    return {'missing': sorted(set(missing)),
            'duplicated': sorted(set(duplicated)),
            'foreign': sorted(foreign)}


# --- sidecar I/O -----------------------------------------------------------

def sidecar_path(temp_dir, chunk_name):
    """chunk0001.md -> <temp_dir>/chunk0001.math.json"""
    stem = chunk_name[:-3] if chunk_name.endswith('.md') else chunk_name
    return os.path.join(temp_dir, stem + SIDECAR_SUFFIX)


def write_sidecar(temp_dir, chunk_name, spans):
    path = sidecar_path(temp_dir, chunk_name)
    payload = {'version': SIDECAR_VERSION, 'chunk': chunk_name, 'spans': spans}
    with io.open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def load_sidecar(temp_dir, chunk_name):
    """Return the span list, or None when no sidecar exists.

    None is the signal for "pre-upgrade temp dir" — callers must treat it as a
    no-op so old temp dirs keep merging.
    """
    path = sidecar_path(temp_dir, chunk_name)
    if not os.path.exists(path):
        return None
    with io.open(path, encoding='utf-8') as f:
        data = json.load(f)
    if data.get('version') != SIDECAR_VERSION or not isinstance(data.get('spans'), list):
        raise ValueError(f'{os.path.basename(path)}: unsupported sidecar schema')
    return data['spans']


def spans_for_chunk(chunk_text, all_spans):
    """Select, in document order, the spans this chunk needs to be restored.

    Includes tokens nested inside another selected span's LaTeX — otherwise
    restoring the outer token would reintroduce an inner token that the sidecar
    cannot resolve, and the placeholder would leak into the final document.
    """
    by_token = {s['token']: s for s in all_spans}
    order = {s['token']: i for i, s in enumerate(all_spans)}

    needed = []
    seen = set()
    queue = [m.group(0) for m in TOKEN_RE.finditer(chunk_text)]
    while queue:
        tok = queue.pop(0)
        if tok in seen or tok not in by_token:
            continue
        seen.add(tok)
        needed.append(tok)
        # follow tokens hiding inside this span's stored LaTeX
        queue.extend(m.group(0) for m in TOKEN_RE.finditer(by_token[tok]['latex']))

    needed.sort(key=lambda t: order[t])
    return [by_token[t] for t in needed]

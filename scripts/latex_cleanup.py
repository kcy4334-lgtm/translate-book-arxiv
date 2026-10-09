# -*- coding: utf-8 -*-
"""LaTeX left in the merged markdown: commands, macros, math, headings.

The arXiv path hands pandoc markdown that still carries the paper's LaTeX.
These passes drop what prints as literal text, expand the paper's own macros,
rewrite math that MathJax and pandoc read differently, and number the
sections and theorem-like statements the way the original PDF does.

Moved out of merge_and_build.py, which re-exports every name here that the
build or a test reaches for.
"""

import os
import re
import subprocess

from build_common import (
    _FONTSIZE_RE, _balanced_group, resolve_pandoc, strip_tex_comments,
)

from numbering import (
    _NEWTHEOREM_RE, _counter_label, build_label_numbers,
    read_class_conventions, read_counter_parents, read_fixed_counter_prefix,
    read_theorem_environments,
)


# Commands that reach the markdown intact and then print as literal text.
# \IEEEPARstart{T}{raining} is IEEE's drop-cap macro: the two arguments are the
# first letter and the rest of the word, so dropping it loses a real word.
# Brace-balanced, not line-anchored: \markboth{...} routinely wraps across
# two lines, and dropping only its first line left a stranded "FEB 2025}" in
# the middle of the page.
# \captionsetup{font={footnotesize}} chooses how a caption is TYPESET and puts
# nothing on the page, but pandoc keeps it as a raw inline. DeeR-VLA writes one
# in front of every caption, and that is enough: the figure formatter looks for
# a caption in the paragraph after the image, finds this instead, and gives up.
# Six of its seven figures reached the page with the caption loose in the prose
# — no number, no figcaption, and every "그림 N" in the text pointing at nothing.
# `\index{sub-gaussian}` marks a term for an index this pipeline does not
# build. randmat writes 79 of them and every one printed as literal text in the
# body; `\printindex` printed itself too. Dropping them is a real reduction —
# the paper has an index and the book will not — so `report_index_terms` says
# so at build time rather than letting it pass unremarked (K110).
_LEFTOVER_CMDS = ('maketitle', 'providecommand', 'newcommand', 'renewcommand',
                  'markboth', 'captionsetup', 'IEEEpeerreviewmaketitle',
                  'IEEEdisplaynontitleabstractindextext',
                  'IEEEtitleabstractindextext')
_INDEX_HEAD_RE = re.compile(r'\\(?:index|printindex|makeindex)\b')
# Directives with nothing in them for a reader, which pandoc hands through as
# raw inlines exactly the way `\index` is — so they need the same removal, span
# and all (K133). Everything here either takes no argument or takes one that is
# a declaration: a page style, a counter name, a length. Deliberately absent
# are the commands whose argument is CONTENT and which therefore need
# resolving rather than dropping — `\parhead` (a run-in heading), `\subref`
# and `\cref` (references), `\newcite` (a citation), `\answerYes` (a checklist
# answer), `\etal`, `\caption`, `\emph`. See K135 for that inventory.
_DIRECTIVE_HEAD_RE = re.compile(
    r'\\(?:pagestyle|thispagestyle|@addtoreset|allowdisplaybreaks'
    r'|algorithmicindent|algrenewcommand|titlerunning|authorrunning'
    r'|large|Large|normalsize)\b')


def drop_directive_spans(md_text):
    r"""Remove content-free directives and the raw inline around them."""
    return _drop_head_and_span(md_text, _DIRECTIVE_HEAD_RE)


def drop_index_terms(md_text):
    r"""Remove `\index{...}` AND the code span it sits in. (text, count).

    Not a member of `_LEFTOVER_CMDS`, and that is the whole point. pandoc hands
    these through as raw inlines, so the markdown says
    `` `\index{Condition number}` ``; dropping only the command leaves an empty
    pair of backticks, and an empty pair is a code-span DELIMITER that swallows
    everything to the next one — including the `$` on either side. Doing it the
    ordinary way took randmat from 0 unrendered formulas to 29 while fixing
    the 79 markers. `arxiv_backend.strip_latex_cruft` learned the same thing
    (`_EMPTY_CODE_RE`); the span has to go with the command.
    """
    return _drop_head_and_span(md_text, _INDEX_HEAD_RE)


def _drop_head_and_span(md_text, head_re):
    r"""Drop each match, its braced arguments, and the raw inline around it."""
    count = 0
    out = []
    at = 0
    while True:
        m = head_re.search(md_text, at)
        if not m:
            out.append(md_text[at:])
            return ''.join(out), count
        stop = m.end()
        # `\algrenewcommand{\algorithmicindent}{...}` takes two; take every
        # brace group that follows, not only the first.
        while stop < len(md_text) and md_text[stop:stop + 1] == '{':
            close = _balanced_group(md_text, stop)
            if close < 0:
                break
            stop = close
        if stop < len(md_text) and md_text[stop:stop + 1] == '{':
            out.append(md_text[at:m.end()])       # unbalanced: leave it alone
            at = m.end()
            continue
        start = m.start()
        # Take the wrapping raw-inline with it when nothing else is inside.
        tail = re.match(r'`(?:\{=[a-z]+\})?', md_text[stop:])
        if start and md_text[start - 1] == '`' and tail:
            start -= 1
            stop += tail.end()
        out.append(md_text[at:start])
        at = stop
        count += 1


_PARSTART_RE = re.compile(r'`?\\IEEEPARstart\{(.)\}\{([^}]*)\}`?')
# `ack` is NeurIPS's acknowledgements environment. pandoc has no reader for it,
# so the whole block — translated prose, funding, thanks — reached the markdown
# as raw LaTeX and was dropped without a word on the HTML path. The wrapper
# lines carry nothing; only what is between them is content.
_ENV_WRAPPER_RE = re.compile(
    r'^[ \t]*\\(?:begin|end)\{(?:IEEEkeywords|IEEEtitleabstractindextext|'
    r'abstract|ack|acks|acknowledgements|acknowledgments|'
    r'appendices|subappendices)\}[ \t]*$\n?',
    re.MULTILINE)
# An empty inline code span, with or without pandoc's raw-inline marker. It is
# what a command stripped out of a code span leaves behind, it renders as two
# stray backticks, and all three books printed one right after a heading:
# "(Estimating Layer Importance in MoE) `` 캘리브레이션 시점의 활성값이…".
# Page 8 of SINQ had the marker form too -- "정의한다. ``{=latex}여기서 σ…".
#
# Two things it must NOT touch, both found by trying them:
#   ``code with a ` inside``   -- a double-backtick span opens with exactly
#                                 this shape, so only a run standing alone
#                                 between spaces counts as empty
#   `a``b`                     -- adjacent spans, likewise not alone
# And a raw inline holding `<!-- -->` is load-bearing: pandoc puts it between
# `$\times$` and `7B` so a closing `$` followed by a digit still reads as
# maths, so only EMPTY ones go.
_EMPTY_RAW_INLINE_RE = re.compile(
    r'(?<![`\S])`[ \t]*`(?![`\S])'          # alone between spaces
    r'|(?<![`\S])`[ \t]*`\{=[a-z]+\}')      # or carrying pandoc's marker
# The marker with no span left in front of it. SINQ page 8 printed
# `\end{equation}$$ {=latex}여기서 …` -- the backticks had already gone, so
# neither form above caught it and the attribute reached the reader.
#
# This one CANNOT live in _EMPTY_RAW_INLINE_RE: that regex is applied to the
# slices between code regions, and a slice can begin at `{=html}` with the
# backtick that owns it in the previous slice. The lookbehind then sees the
# start of a string and strips the marker off a live raw inline -- which is
# how `<!-- -->`, the comment that keeps `$\times$` apart from `7B`, became
# an ordinary code span and printed itself 21 times in AlphaQ.
# An OPENING bracket may also sit in front of it: BERT writes
# "네 번째 토큰({=latex}`hairy`에 해당)". Requiring whitespace there left that one
# marker on the page. A code span can never END with `(`, `[` or `{`, so
# admitting those cannot strip the attribute off a live raw inline -- which is
# the failure the lookbehind exists to prevent.
_ORPHAN_RAW_ATTR_RE = re.compile(
    r'(?:(?<![`\S])|(?<=[(\[{]))\{=[a-z]+\}')
# `\setlength\abovedisplayskip{3pt}` written INSIDE the display maths, as
# DeeR-VLA does on all eight of its equations. texmath has no reader for it
# and refuses the whole formula, so the `$$` print as text and the equation
# is gone. The WHOLE LINE has to go: taking only the command leaves a blank
# line, a blank line ends the display block, and the dollars print anyway --
# measured, 8 unrendered spans became 12.
_SETLENGTH_RE = re.compile(
    r'[ \t]*\\setlength\s*(?:\{\s*\\[a-zA-Z]+\s*\}|\\[a-zA-Z]+)'
    r'\s*\{[^{}]*\}[ \t]*\n?')
_SIDESET_RE = re.compile(r'\\sideset\s*\{\s*\}\s*\{')


def rewrite_sideset(text):
    r"""`\sideset{}{_{X}}\sum` -> `\sum\nolimits_{X}`. (text, count).

    Not a deletion and not an approximation: `\sideset` with an empty left
    argument asks for the scripts BESIDE the operator, and `\nolimits` says
    exactly that. DeeR-VLA's own equation already uses `\sum\nolimits`
    further along the same line.

    texmath has no reader for `\sideset`, so the whole formula was refused
    and the `$$` printed as text. The lesson is wider than the command: the
    boundary is not where a command is unsupported, it is where the
    supported subset has no equivalent -- and that is a much smaller place.
    A `\sideset` carrying BOTH sides really has none, and is left alone.
    """
    out, cursor, count = [], 0, 0
    for m in _SIDESET_RE.finditer(text):
        if m.start() < cursor:
            continue
        close = _balanced_group(text, m.end() - 1)
        if close < 0:
            continue
        scripts = text[m.end():close - 1].strip()
        tail = re.match(r'\s*(\\[a-zA-Z]+)', text[close:])
        if not tail:
            continue
        if scripts.startswith(('_', '^')):
            replacement = '%s\\nolimits%s' % (tail.group(1), scripts)
        elif _SIDESET_MARK_RE.fullmatch(scripts):
            # The primed sum: `\sideset{}{'}\sum` is a RESTRICTED sum, and the
            # mark belongs beside the operator. `{\sum}'` puts it there and
            # texmath reads it. Maynard writes it 7 times and every one of
            # those formulas printed as source -- the rewrite was here, but it
            # only knew the second argument as a SCRIPT, so a prime walked
            # straight past it. Dropping the mark is not available: it is what
            # makes the sum restricted.
            replacement = '{%s}%s' % (tail.group(1), scripts)
        else:
            continue
        out.append(text[cursor:m.start()])
        out.append(replacement)
        cursor = close + tail.end()
        count += 1
    out.append(text[cursor:])
    return ''.join(out), count


# A raw inline carrying only a length: what `\vspace*{-2em}` becomes.
# Two shapes. Backticked is what pandoc usually leaves; BARE is what a
# half-stripped `\vspace*{-2.5mm}` leaves, and it arrives on a line of its own
# directly above an image. The bare form is anchored to the whole line, so a
# brace inside ordinary prose is never touched.
_LENGTH = r'\{\s*-?[\d.]+\s*(?:em|ex|pt|cm|mm|in|bp)\s*\}'
_SPACING_INLINE_RE = re.compile(
    r'[ \t]*`' + _LENGTH + r'`(?:\{=[a-z]+\})?'
    r'|^[ \t]*' + _LENGTH + r'[ \t]*$', re.M)
# A literal [word] that pandoc escaped as \[word\]; the markdown reader then
# reads \[...\] as DISPLAY MATH under tex_math_single_backslash and renders it
# in math italic. Only unescaped when the content is plainly not math.
_ESCAPED_BRACKET_RE = re.compile(r'\\\[([^\\\]$]{1,40}?)\\\]')


# `\subcaption{Cayley SGD.}` labels one panel of a multi-panel float.
# pandoc leaves it as an inline code span, sometimes with a `{=latex}`
# tail, and it prints verbatim next to the image. Its argument is the
# panel's caption text, which belongs on the page.
# The body is read with a balanced scan, not `[^{}]*`: CafeQ's panel label is
# `\subcaption[t]{Adam; $\lambda_{orth}=0$.}`, whose nested braces made the
# old pattern miss it entirely and print the command to the reader verbatim.
_SUBCAPTION_OPEN_RE = re.compile(
    r'`?\\subcaption\*?\s*(?:\[[^\]]*\])?\s*(?=\{)')


def _drop_latex_commands(text, names, stats):
    """Remove `\\cmd{...}{...}` calls whole, across newlines."""
    for name in names:
        while True:
            m = re.search(r'\\' + name + r'\b', text)
            if not m:
                break
            end = m.end()
            # Consume every brace group that follows, balanced.
            while end < len(text):
                nxt = re.match(r'[ \t\n]*\{', text[end:])
                if not nxt:
                    break
                close = _balanced_group(text, end + nxt.end() - 1)
                if close < 0:
                    break
                end = close
            text = text[:m.start()] + text[end:]
            stats['dropped'] += 1
    return text


# pandoc's TeX reader implements none of the pre-LaTeX2e font switches, and it
# does not ignore them either: `{\rm max}` makes the *entire* formula fail to
# parse, so it reaches the page as literal `$s = (w_{\rm max} - ...)$`. One
# such token inside a display equation costs the reader the whole equation.
#
# Applied everywhere except code. Scoping this to math spans looks safer and
# is not: pairing `$` across a paragraph desynchronises on the first stray one
# (a literal price, an escaped \$, an unbalanced formula), and every span after
# it is scanned off by one. Three `{\rm Q}` in CafeQ survived that way and took
# two displayed equations to the page as raw source. `{\rm ...}` is broken TeX
# wherever it lands in markdown; code is the one place it is a quoted example.
# The trailing `(?<!\\)` matters: `\ ` is an ESCAPED SPACE, an atomic token,
# not cosmetic padding. Shor writes `{\rm \ (mod\ }n`, and trimming that last
# space welded the backslash to what followed — `\n`, a control sequence no
# renderer knows — so 77 formulas in one paper printed as source.
_OLD_FONT_RE = re.compile(
    r'\{\s*\\(rm|bf|it|sf|tt|sc|cal)\s+([^{}]*?)(?<!\\)\s*\}')
_OLD_FONT_MAP = {'rm': 'mathrm', 'bf': 'mathbf', 'it': 'mathit',
                 'sf': 'mathsf', 'tt': 'mathtt', 'sc': 'mathrm',
                 'cal': 'mathcal'}
# The other spelling: the switch CALLED with a braced argument, `\cal{A}`.
# That is not valid LaTeX2e either, and the cost is the same — texmath refuses
# the whole formula, so GAN's definition of a subderivative printed as raw
# source twice on the page. The group form above does not match it: there is
# no `{` before the command and no space after it.
_OLD_FONT_CALL_RE = re.compile(r'\\(rm|bf|it|sf|tt|sc|cal)\s*(?=\{)')
# And the third spelling: the switch with NO group at all, `$\rm P$`. The group
# form needs a `{` before it and the call form needs one after it, so a bare
# switch slips past both and texmath refuses the formula. `\mathrm P` is valid
# without braces, so the same substitution works here.
_OLD_FONT_BARE_RE = re.compile(
    r'\\(rm|bf|it|sf|tt|sc|cal)(?=\s+[^\s{])')

# `\textsc` is the OTHER half of the problem, and it must be treated
# differently: in text mode it is correct LaTeX and pandoc renders small caps,
# but texmath has no reader for it and refuses the whole formula. BERT names
# its two model sizes `BERT$_{\textsc{BASE}}$` and `BERT$_{\textsc{LARGE}}$`,
# so thirty-five formulas printed to the reader as raw source. Asked directly,
# pandoc renders the same span the moment `\textsc` becomes `\mathrm`.
#
# Scoped to inline math spans on one line — the same conservative shape the
# guard uses — because rewriting it in TEXT mode would break the small caps
# that are working.
# Display blocks count too, and they cost more: Neural ODE writes
# `\textnormal` inside fourteen `align` environments, so fourteen displayed
# derivations printed to the reader as raw LaTeX — 637 leaked tokens, every
# one of them from this. `$$…$$` is matched non-greedily across lines because
# a display block legitimately spans them.
# An inline span may WRAP. `$[t_\textnormal{start}, t_\textnormal{end}]$` sits
# across a line break in Neural ODE, and an alternative that stops at `\n`
# walks past it — nineteen `\textnormal` survived the rewrite that way while
# the same command was being fixed everywhere else. A newline is allowed
# inside a span; a BLANK line is not, because that ends the paragraph.
_INLINE_MATH_SPAN_RE = re.compile(
    r'(?<!\\)\$\$.*?(?<!\\)\$\$'
    r'|(?<![\\$\w])\$(?!\s)'
    r'(?:[^$\n\\]|\\.|\n(?![ \t]*\r?\n)){1,800}?(?<!\\)\$(?!\d)'
    r'|(?<=\w)\$[_^]'
    r'(?:[^$\n\\]|\\.|\n(?![ \t]*\r?\n)){1,800}?(?<!\\)\$(?!\d)', re.DOTALL)
_TEXT_FONT_IN_MATH_RE = re.compile(
    r'\\text(normal|sc|bf|it|tt|rm|sf|up|md)\s*(?=\{)')
_TEXT_FONT_MAP = {'normal': 'mathrm', 'sc': 'mathrm', 'bf': 'mathbf',
                  'it': 'mathit', 'tt': 'mathtt', 'rm': 'mathrm',
                  'sf': 'mathsf', 'up': 'mathrm', 'md': 'mathrm'}


# `\mkern18mu` is math-mode glue: it sets space and has nothing in it to read.
# texmath has no reader for it and refuses the formula around it, which is the
# same trade `\setlength` made in K100 — a spacing directive costing a whole
# derivation. Removed inside math only; it is meaningless outside.
_MKERN_RE = re.compile(r'\\mkern\s*-?[\d.]+\s*mu\s*')
# `\vphantom{...}` reserves height and prints nothing; texmath has no reader.
# Matched by brace BALANCE, not by a fixed depth: Neural ODE's is
# `\vphantom{\frac{\partial p(\mathbf{z}(t), t)}{\partial \mathbf{z}(t)}}`,
# four levels deep, and a two-level pattern walks straight past it.
_VPHANTOM_HEAD_RE = re.compile(r'\\(?:vphantom|hphantom|phantom)\s*(?=\{)')
# `\ref` and `\eqref` inside a formula. texmath has no reader for either, so a
# derivation annotated `\mathrm{(by Eq \ref{eq:chain_rule})}` prints as source
# in full. The label index knows the number; use it, and drop the command when
# it does not.
_MATH_REF_HEAD_RE = re.compile(r'\\(?:eqref|[A-Za-z]*ref)\s*\{([^{}]*)\}')
# `\nicefrac{a}{b}` is the nicefrac package's slanted fraction. texmath refuses
# it, and `\frac` says the same thing in the subset it does read — eleven of
# Neural ODE's inline formulas printed as source over this one command.
_NICEFRAC_RE = re.compile(r'\\nicefrac(?=\s*\{)')
# The mark a `\sideset` can carry beside an operator instead of a script: a
# prime, a double prime, or a star. Anything longer is not this shape.
_SIDESET_MARK_RE = re.compile(r"[*'\u2032]{1,2}")
# `\idotsint` is amsmath's iterated integral. texmath has no reader for it and
# `\int\cdots\int` is the same thing written in the subset it does read.
_IDOTSINT_RE = re.compile(r'\\idotsint(?![A-Za-z])')
# `{X \atop Y}` is the plain-TeX stack. texmath refuses it; `\substack` stacks
# the same two operands and renders. Measured both ways.
_ATOP_RE = re.compile(r'\{((?:[^{}]|\{[^{}]*\})*?)\\atop'
                      r'((?:[^{}]|\{[^{}]*\})*?)\}')
# `\multicolumn{1}{c}{X}` inside a math array spans ONE column, so it is pure
# alignment and X is the whole of its content. texmath refuses the formula
# over it. A span of 2 or more is left alone: dropping that would leave the
# row short of cells, which corrupts the array instead of rescuing it.
_MATH_MULTICOL1_RE = re.compile(
    r'\\multicolumn\s*\{\s*1\s*\}\s*\{[^{}]*\}\s*'
    r'\{((?:[^{}]|\{[^{}]*\})*)\}')
# `\hat\mathbf{x}` -- an accent whose argument is another command rather than a
# single token. LaTeX accepts it; texmath does not, and refuses the formula.
# Measured: `$\hat\mathbf{x}_0$` is rejected, `$\hat{\mathbf{x}}_0$` renders.
# Braces are added, never removed, so the meaning cannot change.
# `\text{\mathtt{[CLS] ...}}` -- a math font command wrapped in a text-mode
# box. texmath refuses it; `\mathtt{...}` alone renders and looks the same,
# because the inner command already sets the font. Measured both ways.
_TEXT_WRAPPING_MATHFONT_RE = re.compile(
    r'\\text(?:rm|normal|it|bf|sf|tt|up|md|sc)?\s*\{\s*'
    r'(\\math(?:tt|bf|rm|it|sf|cal|bb|frak|scr)\s*'
    r'\{(?:[^{}]|\{[^{}]*\})*\})\s*\}')
_BARE_ACCENT_RE = re.compile(
    r'\\(hat|bar|tilde|vec|dot|ddot|check|breve|acute|grave|widehat'
    r'|widetilde|widebar|overline|underline|mathring)\s*'
    r'(\\[A-Za-z]+\s*\{(?:[^{}]|\{[^{}]*\})*\})')
# `\qedhere` puts the QED box on the last display line and `\notag` suppresses
# an equation number. Both are typesetting directives with nothing to read, and
# both cost the whole formula -- four of randmat's displays, including the one
# carrying the proof's final inequality. The proof terminator is already
# handled as its own mark in the markdown, so nothing visible is lost.
# `\linebreak[3]` and friends carry an OPTIONAL argument, so the bracket has to
# go with the command; left behind, `[3]` prints as text in the middle of a
# formula. They are line-breaking hints with no content, like the rest here.
_MATH_DIRECTIVE_RE = re.compile(
    r'\\(?:qedhere|notag|nonumber|allowdisplaybreaks|displaybreak'
    r'|linebreak|nolinebreak|newline|pagebreak|nopagebreak)'
    r'(?![A-Za-z])\s*(?:\[[^\]\n]*\]\s*)?')


# `\mathrm{event at time $t$}` -- inside a text-mode argument the author
# switches back to math for one symbol. It is ordinary LaTeX, and it defeats
# every flat `$`-pairing scanner downstream, this module's own included: the
# span closes at the inner `$` and the dollars pair off by one from there.
# Inside `\mathrm{}` the argument is already set as text, so dropping the inner
# delimiters says the same thing -- measured against pandoc, which refuses the
# nested form and renders the flattened one.
# The nested formula carries braces of its own -- `$\mathbf{z}(t)$` -- so none
# of the three parts may exclude them outright. A brace-free pattern caught
# `$t$` and walked past `$\mathbf{z}(t)$`, leaving the whole display raw.
# The nested brace group must exclude `$` too, or the pattern runs from a
# `\text{` in one formula, through that formula's closing `$` and the next
# one's opening `$`, to a `}` further down.
_INNER = r'(?:[^{}$]|\{[^{}$]*\})'
_NESTED_MATH_IN_TEXT_RE = re.compile(
    r'(\\(?:math|text)(?:rm|normal|it|bf|sf|tt|up|md|sc)?\s*\{)'
    r'(' + _INNER + r'{0,120}?)\$(' + _INNER + r'{1,120})\$'
    r'(' + _INNER + r'{0,120}?)(\})')


def _drop_balanced_command(text, head_re):
    """Remove `\\cmd{...}` and its argument by brace BALANCE. (text, count)."""
    count = 0
    while True:
        m = head_re.search(text)
        if not m:
            return text, count
        close = _balanced_group(text, text.index('{', m.end() - 1))
        if close < 0:
            return text, count
        text = text[:m.start()] + text[close:]
        count += 1


def resolve_math_references(md_text, temp_dir):
    r"""Turn `\ref{key}` inside a formula into its number. (text, count).

    A derivation annotated `\mathrm{(by Eq \ref{eq:chain_rule})}` costs the
    whole display: texmath has no reader for `\ref`, so the entire block prints
    as LaTeX source. The number is already known here.
    """
    numbers = build_label_numbers(temp_dir)
    hits = [0]

    def fix_span(m):
        def sub(ref):
            hits[0] += 1
            number = numbers.get(ref.group(1).strip())
            return number if number else ''

        return _MATH_REF_HEAD_RE.sub(sub, m.group(0))

    return _INLINE_MATH_SPAN_RE.sub(fix_span, md_text), hits[0]


def split_nested_math_text(md_text):
    r"""`\text{A$X$B}` -> `\text{A}X\text{B}`. Returns (text, count).

    Measured against pandoc, not reasoned about, because the shape alone does
    not decide it: ResNet's `\text{3$\times$3, 64}` renders as written, and
    Neural ODE's `\mathrm{event at time $t$}` does not. Deleting the inner
    delimiters fixes the second and BREAKS the first — `\times` in text mode
    means nothing — which is how this was found: a clean ResNet went to 112
    leaked tokens on the flattening version of this pass.

    Closing the text group and reopening it is the one transformation both
    accept, and it is exact: A and B stay text, X stays maths. It also removes
    the nesting, so every flat `$`-pairing scanner downstream — this module's
    own included — stops mis-closing on these.

    X is reopened with `\ensuremath`, and that word is the whole of the repair.
    The split leaves X wherever the group already was, and the group is in one
    of two modes: inside a formula, where X needs no delimiters, or in text,
    where a bare `\pm` is nothing and pandoc drops it without a word. Emitting
    X bare is right in the first and wrong in the second; wrapping it in `$…$`
    is right in the second and wrong in the first, because the dollar closes
    the formula it is standing in. Looped flows shipped `97.9 0.4` in table 1
    for exactly this: three bold cells that read `\textbf{97.9 $\pm$ 0.4}`.

    Telling the two apart means a scanner that knows every way a paper can
    open a display — `$`, `$$`, `\[`, and the amsmath environments, of which
    this corpus alone carries equation, align and their starred forms — and a
    scanner like that is wrong the first time a paper spells one differently.
    `\ensuremath` asks that question at the point where the answer is known
    for certain, and both of pandoc's readers honour it: the LaTeX reader in a
    table cell and inside every display form above, and texmath in the `$…$`
    of the prose. One form, both modes, nothing to keep in step.

    Boundary: one nested span per argument. `\text{a$x$b$y$c}` is left exactly
    as it was rather than widened for; a pattern that reached further is what
    caused the ResNet regression above.
    """
    total = 0
    for _ in range(4):                        # an argument may hold several
        md_text, n = _NESTED_MATH_IN_TEXT_RE.subn(
            r'\1\2}\\ensuremath{\3}\1\4}', md_text)
        total += n
        if not n:
            break
    return md_text, total


# The paper's own shorthand. `\def \< {\langle}` is a control SYMBOL, so no
# letter boundary applies to it; `\def \E {\mathbb{E}}` is a control WORD and
# must not be found inside `\Ell`.
_MATH_MACRO_DEF_RE = re.compile(
    r'\\(?:newcommand|renewcommand|providecommand)\s*\*?\s*'
    r'(?:\{\s*(\\[A-Za-z]+|\\[^A-Za-z\s])\s*\}|(\\[A-Za-z]+|\\[^A-Za-z\s]))'
    r'\s*(?:\[\s*\d+\s*\][^{]*)?(?=\{)'
    r'|\\def\s*(\\[A-Za-z]+|\\[^A-Za-z\s])\s*(?=\{)'
    r'|\\DeclareMathOperator\s*\*?\s*\{\s*(\\[A-Za-z]+)\s*\}\s*(?=\{)')


_TEXMATH_READS = {}


def _texmath_reads(commands):
    r"""{command: bool} — can texmath render `$\cmd$`? Asked once, cached.

    One pandoc call for the whole batch, matched back by the TeX annotation it
    writes beside each formula. When pandoc cannot be reached every answer is
    False, which reproduces the conservative behaviour this replaces: a macro
    whose target may be unreadable is dropped rather than followed.
    """
    todo = [c for c in commands if c not in _TEXMATH_READS]
    if not todo:
        return {c: _TEXMATH_READS.get(c, False) for c in commands}
    pandoc = resolve_pandoc()
    if not pandoc:
        for c in todo:
            _TEXMATH_READS[c] = False
        return {c: False for c in commands}
    doc = '\n\n'.join('$%s$' % c for c in todo)
    try:
        proc = subprocess.run(
            [pandoc, '-f', 'markdown+tex_math_dollars', '-t', 'html',
             '--mathml'],
            input=doc, capture_output=True, text=True, encoding='utf-8',
            errors='replace', timeout=60)
        html = proc.stdout or ''
    except Exception:                                        # noqa: BLE001
        html = ''
    rendered = {' '.join(m.split()) for m in
                re.findall(r'<annotation\b[^>]*>(.*?)</annotation>', html,
                           re.DOTALL)}
    for c in todo:
        _TEXMATH_READS[c] = c in rendered
    return {c: _TEXMATH_READS.get(c, False) for c in commands}


def read_math_macros(temp_dir):
    r"""{name: body} for the paper's own zero-argument math shorthand.

    arxiv_backend already collects these into math_macros.tex -- and nothing
    ever read the file back, so the definitions were written to disk and
    dropped. Vershynin writes `\def \< {\langle}` and then uses `\<` in 56
    formulas; texmath has never heard of `\<`, so all 56 printed as source.

    Only zero-argument definitions are expanded. One taking `#1` needs a real
    macro expander, and guessing at one would corrupt formulas that render
    correctly today.
    """
    macros = {}
    for name in ('math_macros.tex', 'flat.tex'):
        path = os.path.join(temp_dir or '', name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as fh:
                text = fh.read()
        except OSError:
            continue
        if name == 'flat.tex':
            text = text.split(r'\begin{document}')[0]
        for m in _MATH_MACRO_DEF_RE.finditer(text):
            token = m.group(1) or m.group(2) or m.group(3) or m.group(4)
            open_at = text.find('{', m.end() - 1)
            if not token or open_at < 0:
                continue
            close = _balanced_group(text, open_at)
            if close < 0:
                continue
            body = text[open_at + 1:close - 1]
            if '#' in body or not body.strip():
                continue
            if m.group(4):                    # \DeclareMathOperator
                body = r'\operatorname{%s}' % body
            macros.setdefault(token, body)
        # An alias is only useful when its target is readable. `\let\gev\GeV`
        # with no usable `\GeV` turns a name texmath cannot read into a
        # different name it cannot read, so it is dropped rather than followed
        # into nothing (K121).
        #
        # But "not defined in this document" is the wrong test for readable,
        # and it was deleting the definitions it exists to protect:
        # `\def \< {\langle}` has exactly the shape of a dangling alias and
        # points at a command texmath knows perfectly well. Nine papers lost
        # macros to it — randmat lost `\<` and `\>` and printed 48 formulas as
        # source. Of the 22 distinct targets across the corpus, 17 render.
        # Shape cannot separate the two cases, so ask (K132).
        candidates = sorted({v.strip() for v in macros.values()
                             if re.fullmatch(r'\\[A-Za-z]+', v.strip())
                             and v.strip() not in macros})
        usable = _texmath_reads(candidates)
        for name in [k for k, v in macros.items()
                     if v.strip() in candidates and not usable.get(v.strip())]:
            del macros[name]
        if macros:
            break
    return macros


def expand_math_macros(md_text, temp_dir):
    r"""Replace the paper's shorthand with what it stands for, inside math.

    Safe at this point in the pipeline precisely because the translator never
    saw any of it: every formula travelled as a placeholder and was restored
    from its sidecar a moment ago. Returns (text, count).
    """
    macros = read_math_macros(temp_dir)
    if not macros:
        return md_text, 0
    subs = []
    for token, body in sorted(macros.items(), key=lambda kv: -len(kv[0])):
        tail = r'(?![A-Za-z])' if token[1:].isalpha() else ''
        subs.append((re.compile(re.escape(token) + tail), body))
    hits = [0]

    def expand(span):
        for _ in range(4):                    # shorthand can nest
            before = span
            for pattern, body in subs:
                # A callable replacement: a body full of backslashes must not
                # be read back as escape sequences.
                span = pattern.sub(lambda _m, b=body: b, span)
            if span == before:
                break
        return span

    def on_span(m):
        out = expand(m.group(0))
        if out != m.group(0):
            hits[0] += 1
        return out

    return _INLINE_MATH_SPAN_RE.sub(on_span, md_text), hits[0]


def unwrap_text_boxed_math_fonts(md_text):
    r"""`\text{\mathtt{X}}` -> `\mathtt{X}`. Returns (text, count).

    Runs AFTER the legacy font pass, not with the other span rewrites. BERT
    writes `\text{\tt {[CLS] ...}}`; `\tt` only becomes `\mathtt` in
    normalize_math_commands, so an unwrap placed before that never sees the
    shape it is looking for -- which is exactly how this first failed to fire.
    """
    count = [0]

    def fix_span(m):
        span = m.group(0)
        for _ in range(3):                    # boxes can nest
            span, hit = _TEXT_WRAPPING_MATHFONT_RE.subn(
                lambda inner: inner.group(1), span)
            if not hit:
                break
            count[0] += hit
        return span

    return _INLINE_MATH_SPAN_RE.sub(fix_span, md_text), count[0]


def rewrite_text_fonts_in_math(md_text):
    r"""Make a formula readable to texmath. Returns (text, count).

    Two shapes, both of which cost the WHOLE formula: a text-mode font switch
    (`\textsc`, `\textnormal`) and math glue (`\mkern`). Neither has a reader,
    and a formula with one in it reaches the reader as raw LaTeX.
    """
    count = [0]

    def fix_span(m):
        def swap(inner):
            count[0] += 1
            return '\\' + _TEXT_FONT_MAP[inner.group(1)]

        def drop(_inner):
            count[0] += 1
            return ' '

        def to_frac(_inner):
            count[0] += 1
            return '\\frac'
        span = _TEXT_FONT_IN_MATH_RE.sub(swap, m.group(0))
        span = _MKERN_RE.sub(drop, span)
        span, dropped = _drop_balanced_command(span, _VPHANTOM_HEAD_RE)
        count[0] += dropped
        span = _MATH_DIRECTIVE_RE.sub(drop, span)

        def to_iterated(_inner):
            count[0] += 1
            return r'\int\cdots\int'
        span = _IDOTSINT_RE.sub(to_iterated, span)

        def to_substack(inner):
            count[0] += 1
            return '\\substack{%s \\\\ %s}' % (inner.group(1).strip(),
                                               inner.group(2).strip())
        span = _ATOP_RE.sub(to_substack, span)

        def unspan(inner):
            count[0] += 1
            return inner.group(1)
        span = _MATH_MULTICOL1_RE.sub(unspan, span)

        def brace(inner):
            count[0] += 1
            return '\\%s{%s}' % (inner.group(1), inner.group(2))
        span = _BARE_ACCENT_RE.sub(brace, span)
        return _NICEFRAC_RE.sub(to_frac, span)

    return _INLINE_MATH_SPAN_RE.sub(fix_span, md_text), count[0]
_CODE_REGION_RE = re.compile(
    r'^[ \t]*(?P<fence>```+|~~~+).*?^[ \t]*(?P=fence)[ \t]*$'
    r'|`[^`\n]+`',
    re.MULTILINE | re.DOTALL)
# Raw LaTeX tables reach the reader through this module's own renderer, not
# through pandoc, and a cell in one is text mode.
_RAW_TABLE_RE = re.compile(
    r'\\begin\{(?P<tenv>table\*?|tabular\*?|tabularx|longtable)\}'
    r'.*?\\end\{(?P=tenv)\}', re.DOTALL)
# Math inside such a table, which is still math and still has to be modernised.
_MATH_REGION_RE = re.compile(
    r'(?<!\\)\$\$.+?(?<!\\)\$\$'
    r'|(?<!\\)\$(?:\\.|[^$\\\n])+?(?<!\\)\$'
    r'|\\\(.+?\\\)'
    r'|\\\[.+?\\\]'
    r'|\\begin\{(?P<menv>equation|align|alignat|flalign|gather|multline'
    r'|eqnarray|displaymath|math)\*?\}.+?\\end\{(?P=menv)\*?\}',
    re.DOTALL)


# An accent whose argument is another command, written without braces:
# `\widetilde\mathbf{A}`. LaTeX takes the following command as the argument
# and typesets it; texmath wants a brace there, gives up on the WHOLE span,
# and the formula reaches the page as literal TeX. VLA-Adapter printed six
# equations that way, and `leak_probe` then counted 75 fragments of them.
#
# Measured against pandoc 3.10.2: `\widetilde\mathbf{A}^0_t`,
# `\widehat\mathbf{B}`, `\bar\mathcal{C}`, `\vec\boldsymbol{d}` and
# `\tilde\mathrm{e}` all fail, and every one renders once the argument is
# braced. So the fix is the brace, and it belongs to the family rather than
# to the one command this paper happened to use.
_MATH_ACCENTS = ('widetilde', 'widehat', 'overline', 'overrightarrow',
                 'underline', 'bar', 'hat', 'tilde', 'vec', 'dot', 'ddot',
                 'check', 'breve', 'acute', 'grave', 'mathring')
_MATH_STYLES = ('mathbf', 'mathrm', 'mathcal', 'mathbb', 'mathsf', 'mathtt',
                'mathit', 'mathfrak', 'mathscr', 'boldsymbol', 'bm', 'symbf')
# One level of nesting inside the style's argument, so `\mathbf{A_{t}}` is
# still matched whole and never cut in half.
_ACCENT_ON_COMMAND_RE = re.compile(
    r'\\(' + '|'.join(_MATH_ACCENTS) + r')\s*'
    r'(\\(?:' + '|'.join(_MATH_STYLES) + r')'
    r'\{(?:[^{}]|\{[^{}]*\})*\})')


def normalize_math_commands(md_text):
    """Modernise the pre-LaTeX2e font switches. Returns (text, stats).

    Everywhere except the inside of a raw LaTeX table. `\\mathbf` and its
    siblings are math-mode commands and LaTeX rejects them in text mode, so
    rewriting a text-mode `{\\bf ...}` does not modernise it -- it corrupts
    it. A `tabular` cell is text mode: CafeQ's table 4 carried `{\\bf 46.6}`
    there, the rewrite turned it into `\\mathbf{46.6}`, and the table
    renderer, handed a cell it could not parse, dropped the row. Three
    numbers the paper reports left the book while the build printed
    `8 converted, 0 failed`.

    Only the tables are held back, not every text-mode span, because the
    rewrite is what makes the math legible to texmath: left alone, `{\\rm Q}`
    reaches the HTML as unrendered `$...$`. Scoping the rewrite to math
    document-wide is not available either -- that needs `$` to pair, and in
    CafeQ's prose it does not, so five Korean sentences parse as formulas.
    A table is a region this module can find exactly, which is why the line
    is drawn there.
    """
    stats = {'fonts': 0, 'accents': 0}

    def rewrite_font(m):
        stats['fonts'] += 1
        inner = m.group(2)
        # `{\rm \min}` -- the body is already an operator command, and
        # \mathrm{\min} is not valid TeX. Keep the command alone.
        if inner.startswith('\\'):
            return inner
        return '\\%s{%s}' % (_OLD_FONT_MAP[m.group(1)], inner)

    def rewrite_call(m):
        stats['fonts'] += 1
        return '\\%s' % _OLD_FONT_MAP[m.group(1)]

    def rewrite_plain(text):
        # Nested groups need more than one pass: {\rm a {\bf b}}.
        previous = None
        while previous != text:
            previous = text
            text = _OLD_FONT_RE.sub(rewrite_font, text)
        # `\cal{A}` keeps its braces; only the command name changes, so one
        # pass is enough and it must run AFTER the group form — otherwise
        # `{\rm x}` would have its command rewritten before the group rule
        # could see the shape it matches on.
        text = _OLD_FONT_CALL_RE.sub(rewrite_call, text)
        # Last, the bare switch with no group either side. It has to run after
        # both, or it would rewrite the command inside `{\rm x}` before the
        # group rule could recognise that shape.
        text = _OLD_FONT_BARE_RE.sub(rewrite_call, text)
        # Then brace an accent's command argument, AFTER the font rules and
        # not before: `\bar\cal{C}` only becomes `\bar\mathcal{C}` above, and
        # the accent rule has to be shown that form to catch it. A callable,
        # never a replacement string: the replacement carries a backslash.
        text, braced = _ACCENT_ON_COMMAND_RE.subn(
            lambda m: '\\%s{%s}' % (m.group(1), m.group(2)), text)
        stats['accents'] += braced
        return text

    held = sorted([(m.start(), m.end(), 'code')
                   for m in _CODE_REGION_RE.finditer(md_text)]
                  + [(m.start(), m.end(), 'table')
                     for m in _RAW_TABLE_RE.finditer(md_text)])

    pieces, cursor = [], 0
    for start, end, kind in held:
        if start < cursor:                # nested in a span already handled
            continue
        pieces.append(rewrite_plain(md_text[cursor:start]))
        block = md_text[start:end]
        if kind == 'table':
            # The cells stay as written; the formulas in them do not.
            block = _MATH_REGION_RE.sub(lambda m: rewrite_plain(m.group(0)),
                                        block)
        pieces.append(block)              # code: left exactly as written
        cursor = end
    pieces.append(rewrite_plain(md_text[cursor:]))
    return ''.join(pieces), stats


def rewrite_subcaptions(md_text, stats):
    """`\\subcaption{Cayley SGD.}` -> a bold paragraph of its own.

    Two things have to happen, not one. The command has to go, or it prints to
    the reader verbatim -- and it has to stop sharing a line with its image,
    because format_figure_blocks only recognises an image that is alone on its
    line. Left where pandoc put it, CafeQ's Figure 3 was three unlabelled
    pictures: no number, no caption, nothing tying them to the text.
    """
    out, cursor = [], 0
    while True:
        m = _SUBCAPTION_OPEN_RE.search(md_text, cursor)
        if not m:
            break
        close = _balanced_group(md_text, md_text.index('{', m.end() - 1))
        if close < 0:
            out.append(md_text[cursor:m.end()])
            cursor = m.end()
            continue
        inner = md_text[md_text.index('{', m.end() - 1) + 1:close - 1].strip()
        tail = md_text[close:]
        trail = re.match(r'`?(?:\{=latex\})?', tail)
        stats['dropped'] += 1
        # Whatever sat in front of it on the line stays put; the label moves
        # down into its own paragraph.
        lead = md_text[cursor:m.start()]
        out.append(lead.rstrip(' \t'))
        if inner:
            out.append('\n\n**%s**' % inner)
        cursor = close + trail.end()
    out.append(md_text[cursor:])
    return ''.join(out)


_FOOTNOTE_DEF_RE = re.compile(r'(?m)^\[\^([^\]\s]+)\]:[ \t]*')
_FOOTNOTE_REF_RE = re.compile(r'\[\^([^\]\s]+)\](?!:)')
_FIRST_HEADING_RE = re.compile(r'(?m)^#{1,6} ')


def _footnote_def_end(text, at):
    """Where the note definition whose body starts at `at` ends.

    pandoc's rule: continuation lines are indented, and a blank line only
    continues the note when an indented line follows it.
    """
    i = text.find('\n', at)
    while i >= 0:
        j = text.find('\n', i + 1)
        line = text[i + 1:j if j >= 0 else len(text)]
        if line.strip():
            if not line.startswith(('    ', '\t')):
                return i
        else:
            k = text.find('\n', j + 1) if j >= 0 else -1
            nxt = text[j + 1:k if k >= 0 else len(text)] if j >= 0 else ''
            if not nxt.startswith(('    ', '\t')):
                return i
        i = j
    return len(text)


def rescue_orphan_footnotes(md_text):
    r"""Render note definitions nothing references. Returns (text, count).

    An IEEE paper carries its front matter in `\thanks`: submission dates,
    every author's affiliation, the equal-contribution and corresponding-author
    notes, the funding, the DOI. pandoc reads each one as a footnote whose
    REFERENCE lives in the title block -- which the backend drops on purpose,
    because the title and authors come from the metadata. The definitions are
    left with nothing pointing at them, and pandoc drops an unreferenced note
    silently: TinyVLA translated 1271 characters of front matter and printed
    none of it. Nothing counted them, because a note that was never referenced
    is missing from every stage at once (K83).

    They are moved, not deleted: ahead of the first heading, which is where
    page-1 footnotes belong in the original. A note that IS referenced is left
    exactly where it is -- it is a working footnote and must stay one.
    """
    refs = set(_FOOTNOTE_REF_RE.findall(md_text))
    spans, bodies = [], []
    for m in _FOOTNOTE_DEF_RE.finditer(md_text):
        if m.group(1) in refs:
            continue
        end = _footnote_def_end(md_text, m.end())
        spans.append((m.start(), end))
        body = md_text[m.end():end]
        bodies.append(re.sub(r'(?m)^(?:    |\t)', '', body).strip())
    if not spans:
        return md_text, 0

    kept, cursor = [], 0
    for start, end in spans:
        kept.append(md_text[cursor:start])
        cursor = end
    kept.append(md_text[cursor:])
    md_text = re.sub(r'\n{3,}', '\n\n', ''.join(kept))

    block = '::: titlenotes\n' + '\n\n'.join(bodies) + '\n:::\n\n'
    heading = _FIRST_HEADING_RE.search(md_text)
    at = heading.start() if heading else len(md_text.rstrip()) + 1
    md_text = md_text[:at] + block + md_text[at:]
    return md_text, len(bodies)


def normalize_latex_leftovers(md_text):
    """Clear LaTeX that survived conversion and prints as literal text.

    Returns (text, stats). Conservative by design: it removes only commands
    that carry no reader-visible content, and rewrites only the two that do.
    """
    stats = {'parstart': 0, 'dropped': 0, 'brackets': 0}

    def parstart(m):
        stats['parstart'] += 1
        return m.group(1) + m.group(2)

    md_text = _PARSTART_RE.sub(parstart, md_text)

    md_text = rewrite_subcaptions(md_text, stats)

    def counted_drop(pattern, text):
        found = len(pattern.findall(text))
        stats['dropped'] += found
        return pattern.sub('', text)

    md_text, stats['index_terms'] = drop_index_terms(md_text)
    md_text, directives = drop_directive_spans(md_text)
    stats['dropped'] += directives
    md_text = _drop_latex_commands(md_text, _LEFTOVER_CMDS, stats)
    md_text = counted_drop(_ENV_WRAPPER_RE, md_text)
    # `\vspace*{-2em}` survives as a raw inline holding only its length. It is
    # page geometry with nothing in it to read, and leaving it costs more than
    # the stray `{-2em}` it prints: the figure formatter stops recognising the
    # image line it sits on, so CafeQ's figure 1 lost its `그림 1` label and
    # its caption printed as an ordinary paragraph.
    md_text = counted_drop(_SPACING_INLINE_RE, md_text)
    md_text = counted_drop(_SETLENGTH_RE, md_text)
    md_text, stats['sideset'] = rewrite_sideset(md_text)

    def keep_argument(m):
        stats['dropped'] += 1
        return m.group(1) or ''

    # Whole text, raw tables included — that is where it does its damage.
    md_text = _FONTSIZE_RE.sub(keep_argument, md_text)
    # Whole-text, before the slicing below: only here can the lookbehind see
    # whether a backtick owns this marker.
    md_text = counted_drop(_ORPHAN_RAW_ATTR_RE, md_text)
    # Outside code only: a fenced block may legitimately contain anything,
    # including two backticks, and rewriting inside one changes a listing.
    pieces, cursor = [], 0
    for code in _CODE_REGION_RE.finditer(md_text):
        pieces.append(counted_drop(_EMPTY_RAW_INLINE_RE,
                                   md_text[cursor:code.start()]))
        pieces.append(code.group(0))
        cursor = code.end()
    pieces.append(counted_drop(_EMPTY_RAW_INLINE_RE, md_text[cursor:]))
    md_text = ''.join(pieces)

    def unbracket(m):
        inner = m.group(1)
        # Math would carry operators, digits-with-symbols, or backslashes.
        # `%` and `°` belong here too: they are units, never a formula on
        # their own, and `\[%\]` -- the escaped `[\%]` of an Overhead column
        # -- was read back as display maths and rendered as nothing.
        if re.fullmatch(r'[\w \-/,.%°]+', inner):
            stats['brackets'] += 1
            return '[' + inner + ']'
        return m.group(0)

    md_text = _ESCAPED_BRACKET_RE.sub(unbracket, md_text)
    return md_text, stats


# =============================================================================
# Original document structure
# =============================================================================
#
# A translated paper read on its own gives no clue where you are in the
# original. IEEEtran (and every other class) numbers sections automatically, so
# the numbers exist nowhere in the markdown -- but flat.tex still has the
# heading ladder, and reproducing it is deterministic.
#
# Two rules keep this honest:
#   * strip LaTeX comments first. This paper has a `%\subsection{...}` the
#     authors commented out; counting it would consume a letter and shift every
#     heading after it.
#   * if the ladders do not line up 1:1, number nothing. A heading labelled "D"
#     that is really E is worse than no label at all.
#   * do not invent the numbering scheme. It belongs to the document class --
#     IEEEtran prints "III-B", ICML's article prints "2.1", and many classes
#     print nothing at all -- so it is read off the source PDF instead.

_HEADING_LINE_RE = re.compile(r'^(#{1,6}) +(.+?)\s*$', re.MULTILINE)


# `\subsection{Additional \texttt{PL\_Alpha\_Hill} Comparisons}` -- the title
# argument nests braces, so it has to be read with a balanced scan. A plain
# `\{([^}]*)\}` stops at the inner `}` and yields a title that is both
# truncated and unbalanced.
_HEADING_CMD_RE = re.compile(r'\\((?:sub)*)(section|paragraph)(\*?)\s*\{')

# Wrappers whose argument IS the text. \texorpdfstring{tex}{pdf} keeps the
# first; the second exists only because the PDF bookmark cannot take math.
_TITLE_UNWRAP_RE = re.compile(
    r'\\(?:textbf|textit|textrm|texttt|textsc|emph|mbox|text|'
    r'operatorname|mathrm|lowercase|uppercase)\s*\{([^{}]*)\}')
_ENSUREMATH_RE = re.compile(r'\\ensuremath\s*\{([^{}]*)\}')
_TEXORPDF_RE = re.compile(r'\\texorpdfstring\s*\{')
_SIMPLE_MACRO_RE = re.compile(
    r'\\(?:new|renew|provide)command\s*\*?\s*\{\\([A-Za-z]+)\}\s*\{')
_TEX_ESCAPES = (('\\&', '&'), ('\\_', '_'), ('\\%', '%'), ('\\#', '#'),
                ('\\$', '$'), ('~', ' '))


def read_simple_macros(tex):
    r"""{name: body} for the paper's own zero-argument \newcommands.

    CafeQ writes `\newcommand{\tx}{\ensuremath{M}}` and then
    `\subsection{Constraints on \tx}`. pandoc expands it in the body, so the
    translated heading reads "Constraints on $M$" -- but flat.tex still says
    `\tx`, and the bilingual suffix would show the macro name.
    """
    out = {}
    for m in _SIMPLE_MACRO_RE.finditer(tex):
        open_at = tex.index('{', m.end() - 1)
        close = _balanced_group(tex, open_at)
        if close < 0:
            continue
        body = tex[open_at + 1:close - 1]
        if '#' not in body:                       # takes no argument
            out.setdefault(m.group(1), body)
    return out


def clean_heading_title(raw, macros=None):
    """Reduce a LaTeX section title to the text a reader would see."""
    text = raw
    for _ in range(4):                            # macros can nest
        if macros:
            expanded = re.sub(
                r'\\([A-Za-z]+)(?![A-Za-z])',
                lambda m: macros.get(m.group(1), m.group(0)), text)
        else:
            expanded = text
        # \texorpdfstring{$\gamma$}{gamma} -> keep the TeX form
        while True:
            m = _TEXORPDF_RE.search(expanded)
            if not m:
                break
            first_open = expanded.index('{', m.end() - 1)
            first_close = _balanced_group(expanded, first_open)
            if first_close < 0:
                break
            second_close = _balanced_group(expanded, first_close) \
                if first_close < len(expanded) and expanded[first_close] == '{' else first_close
            expanded = (expanded[:m.start()]
                        + expanded[first_open + 1:first_close - 1]
                        + expanded[second_close:])
        # `Constraints on $\tx$` expands to `$\ensuremath{M}$`, and wrapping
        # the body in dollars again gives `$$M$$` -- display math. pandoc
        # then emits a centred block inside the heading, and CafeQ printed
        # `M에 대한 제약 (Constraints on` on one line with a lone centred `M`
        # 27pt below it and the `)` after that. The source already opened
        # math here, so take its dollars rather than adding a pair.
        expanded = re.sub(r'\$\s*\\ensuremath\s*\{([^{}]*)\}\s*\$',
                          r'$\1$', expanded)
        expanded = _ENSUREMATH_RE.sub(r'$\1$', expanded)
        expanded = _TITLE_UNWRAP_RE.sub(r'\1', expanded)
        if expanded == text:
            break
        text = expanded
    text = re.sub(r'\\label\s*\{[^{}]*\}', '', text)
    for old, new in _TEX_ESCAPES:
        text = text.replace(old, new)

    # Strip unknown commands OUTSIDE math only. `Sensitivity of $\\gamma$` would
    # otherwise become `Sensitivity of $$` -- the command removed, the empty
    # delimiters left behind.
    def strip_outside_math(chunk):
        return re.sub(r'\\[A-Za-z]+\s*', '', chunk)

    pieces, cursor = [], 0
    for span in re.finditer(r'\$[^$\n]+\$', text):
        pieces.append(strip_outside_math(text[cursor:span.start()]))
        pieces.append(span.group(0))
        cursor = span.end()
    pieces.append(strip_outside_math(text[cursor:]))
    text = ''.join(pieces)
    return re.sub(r'\s+', ' ', text).strip()


def read_tex_headings(temp_dir):
    """[(level, original_title, is_numbered)] from flat.tex, in document order."""
    flat = os.path.join(temp_dir, 'flat.tex')
    if not os.path.exists(flat):
        return []
    try:
        with open(flat, 'r', encoding='utf-8', errors='replace') as fh:
            tex = strip_tex_comments(fh.read())
    except OSError:
        return []
    macros = read_simple_macros(tex)
    out = []
    for m in _HEADING_CMD_RE.finditer(tex):
        open_at = m.end() - 1
        close = _balanced_group(tex, open_at)
        if close < 0:
            continue
        title = tex[open_at + 1:close - 1].strip()
        # A macro *definition* body, not a heading: a real title never has #1.
        if '#' in title or not title:
            continue
        subs = m.group(1).count('sub')
        title = clean_heading_title(title, macros)
        if not title:
            continue
        if m.group(2) == 'section':
            # Starred sections are unnumbered in LaTeX -- Abstract, Index
            # Terms. Numbering them would shift every real section after them.
            out.append((subs + 1, title, m.group(3) != '*'))
        else:
            # \paragraph and \subparagraph sit below the default secnumdepth
            # of every class these papers use, so LaTeX prints them with no
            # number. They still occupy a rung -- pandoc turns them into ####
            # headings -- and leaving them out is what made the ladder come up
            # short on all three of SINQ, CafeQ and AlphaQ, disabling section
            # numbering entirely.
            out.append((4 + subs, title, False))
    return out


def _source_pdf(temp_dir):
    """The PDF this temp dir was built from, per config.txt."""
    config = os.path.join(temp_dir, 'config.txt')
    try:
        with open(config, 'r', encoding='utf-8', errors='replace') as fh:
            for line in fh:
                if line.startswith('input_file='):
                    path = line.split('=', 1)[1].strip()
                    if path.lower().endswith('.pdf') and os.path.isfile(path):
                        return path
    except OSError:
        pass
    return None


def _normalize_heading(text):
    """Fold a heading to something two renderings of it can agree on."""
    text = re.sub(r'\$[^$]*\$', ' ', text)          # math renders differently
    text = re.sub(r'[^0-9A-Za-z]+', ' ', text)
    return re.sub(r'\s+', ' ', text).strip().lower()


# "2.1.1." / "III." / "A.3" / "4" -- whatever the class chose to print.
_PDF_PREFIX_RE = re.compile(
    r'^\s*((?:[0-9]+|[A-Z]|[IVXLC]+)(?:[.\-][0-9A-Z]+)*\.?)[ \t]+(\S.*)$')
# The same number, alone on its line. A class that sets the number and the
# title apart with a wide skip -- llncs, and whatever typeset Looped flows --
# comes out of PyMuPDF as two lines, `1` and then `Introduction`. Reading only
# the joined form called every one of those headings unnumbered, and the book
# printed Looped flows without a single section number while its own prose
# still said "(5.1절)".
_PDF_BARE_PREFIX_RE = re.compile(
    r'^\s*((?:[0-9]+|[A-Z]|[IVXLC]+)(?:[.\-][0-9A-Z]+)*)\.?\s*$')


def _prefix_fits_level(prefix, level):
    r"""Could `prefix` number a heading at `level`? Split-line reading only.

    A number on the line above a title is a weaker witness than one on the
    same line: a table cell holding `11.1` sits above a row labelled
    `Looped flows` in the very paper that needed this. A section number has
    one component per level, so `11.1` cannot number a top-level heading.
    A lone letter or Roman numeral is let through at any level, because
    IEEE-style papers number subsections `A.`, `B.` under `I.`, `II.`.
    """
    parts = [p for p in re.split(r'[.\-]', prefix.strip().rstrip('.')) if p]
    if len(parts) == level:
        return True
    return len(parts) == 1 and bool(re.fullmatch(r'[A-Z]|[IVXLC]+', parts[0]))


def read_pdf_section_prefixes(temp_dir, tex_heads):
    """[prefix or ''] per heading, read off the original PDF.

    Returns (prefixes, stats). An empty string means the paper prints that
    heading without a number -- which is a real answer, not a failure. None is
    returned for the whole list when the PDF cannot be consulted at all.
    """
    stats = {'matched': 0, 'unnumbered': 0, 'missing': 0,
             'wrapped': 0, 'run_in': 0, 'reason': None}
    # A level the class sets run-in prints no heading line at all, so failing
    # to find one says nothing about the numbering. Kept out of `missing` and
    # counted on its own.
    run_in_level = 0
    try:
        with open(os.path.join(temp_dir, 'flat.tex'), 'r',
                  encoding='utf-8', errors='replace') as fh:
            run_in_level = read_class_conventions(
                fh.read(40000)).get('run_in_level', 0)
    except OSError:
        pass
    pdf_path = _source_pdf(temp_dir)
    if not pdf_path:
        stats['reason'] = 'no source PDF recorded in config.txt'
        return None, stats
    try:
        import pymupdf                                     # optional dependency
    except ImportError:
        stats['reason'] = 'pymupdf not installed'
        return None, stats

    try:
        import pdf_text
        doc = pymupdf.open(pdf_path)
        try:
            # Page furniture out first. A page number is a bare number on its
            # own line, which is exactly what the split-line reading below
            # takes for a section number when a heading opens a page.
            lines = pdf_text.lines_without_furniture(doc)
        finally:
            doc.close()
    except Exception as exc:                               # noqa: BLE001
        stats['reason'] = 'could not read %s (%s)' % (os.path.basename(pdf_path), exc)
        return None, stats

    return prefixes_from_lines(lines, tex_heads, run_in_level, stats)


def prefixes_from_lines(lines, tex_heads, run_in_level=0, stats=None):
    """[prefix or '' or None] per heading, from the PDF's text lines.

    The half of `read_pdf_section_prefixes` that needs no PDF, so it can be
    tested on the lines a real paper produced. `stats` is updated in place.
    """
    if stats is None:
        stats = {'matched': 0, 'unnumbered': 0, 'missing': 0,
                 'wrapped': 0, 'run_in': 0, 'reason': None}
    # title -> prefix. First occurrence wins: a heading is printed before it is
    # cited, and the table of contents (if any) agrees with the body anyway.
    numbered, split, plain = {}, {}, set()
    before = ''
    for raw in lines:
        line = raw.strip()
        if not line or len(line) > 120:
            continue
        m = _PDF_PREFIX_RE.match(line)
        if m:
            key = _normalize_heading(m.group(2))
            if key and key not in numbered:
                numbered[key] = m.group(1).strip()
        bare = _PDF_BARE_PREFIX_RE.match(before)
        if bare:
            key = _normalize_heading(line)
            if key:
                split.setdefault(key, []).append(bare.group(1).strip())
        key = _normalize_heading(line)
        if key:
            plain.add(key)
        before = line

    prefixes, used = [], {}
    for level, title, _is_numbered in tex_heads:
        key = _normalize_heading(title)
        if key in numbered:
            prefixes.append(numbered[key])
            stats['matched'] += 1
            continue
        # Every candidate is kept and the first that can number this level
        # wins, so a table cell printed before the heading does not shadow it.
        # A title the paper uses twice takes the candidates in order: CafeQ
        # has `2 Related work` in the body and `A Related work` in the
        # appendix, and first-wins gave both of them 2.
        seen = used.get(key, 0)
        fitting = [p for p in split.get(key, ()) if _prefix_fits_level(p, level)]
        if len(fitting) > seen:
            used[key] = seen + 1
            prefixes.append(fitting[seen])
            stats['matched'] += 1
            stats['split'] = stats.get('split', 0) + 1
            continue
        if key in plain:
            prefixes.append('')
            stats['unnumbered'] += 1
            continue
        # The column was too narrow and the PDF wrapped the title, so the
        # extracted line holds only its beginning.
        partial = _longest_prefix_match(key, numbered)
        if partial is not None:
            prefixes.append(numbered[partial])
            stats['matched'] += 1
            stats['wrapped'] += 1
            continue
        # The title carries maths, which `_normalize_heading` deletes on the
        # LaTeX side and the PDF renders as an ordinary letter.
        extended = _math_extended_match(title, key, numbered)
        if extended is not None:
            prefixes.append(numbered[extended])
            stats['matched'] += 1
            stats['wrapped'] += 1
            continue
        prefixes.append(None)
        if run_in_level and level >= run_in_level:
            stats['run_in'] += 1
        else:
            stats['missing'] += 1
    return prefixes, stats


def locatable_headings(total, pdf_stats):
    r"""How many of a paper's headings the PDF could show at all.

    A level the class sets run-in is typeset inside the paragraph it opens,
    so there is no heading line to find and no amount of matching will ever
    find one. Counting those in the denominator made the ratio unreachable:
    amsart papers offered 11 locatable headings out of 30 and were refused
    numbering entirely, a refusal meant for a paper whose headings are
    MISSING landing on one whose headings are merely inline.
    """
    return max(0, total - (pdf_stats or {}).get('run_in', 0))


def enough_located(locatable, share=0.6, floor=3):
    r"""The number of headings that must be found before numbering is safe.

    Three at minimum, because a ratio over two or three headings says
    nothing. The share is what it always was; only what it is a share OF
    has changed.
    """
    return max(floor, int(share * locatable))


def _longest_prefix_match(key, numbered, minimum=14):
    """The longest heading in `numbered` that `key` starts with."""
    best = None
    for candidate in numbered:
        if len(candidate) >= minimum and key.startswith(candidate):
            if best is None or len(candidate) > len(best):
                best = candidate
    return best


def _math_extended_match(title, key, numbered, minimum=10):
    r"""The PDF heading that `key` is a prefix of, when maths was deleted.

    `_normalize_heading` drops `$...$` because two renderings of a formula
    never agree character for character. On the PDF side there is nothing to
    drop: `\section{Smooth choice of $y$}` prints as "Smooth choice of y", so
    the LaTeX key ends where the PDF key carries one more letter and neither
    the exact test nor the wrapped-title test can bridge it. Three of
    Maynard's ten sections are written that way, and all three came back as
    "not found" — which also cost the print TOC and the PDF outline their
    numbers until the same gap was closed on that side (K126).

    Only for titles that actually contain maths, and only when exactly one
    candidate extends the key: a heading that is a genuine prefix of another
    ("Notation" before "Notation and conventions") must stay unmatched rather
    than take its neighbour's number.
    """
    if '$' not in (title or '') or len(key) < minimum:
        return None
    hits = [c for c in numbered if c != key and c.startswith(key)]
    return hits[0] if len(hits) == 1 else None


def _already_says(translated, original):
    r"""Does the translated heading already carry the original's words?

    The translator glosses a term on first use, so `2.1.2. 타일링(tiling)`
    came back already carrying its English — and the bilingual suffix then
    added it a second time: `타일링(tiling) (Tiling)`, in the heading and
    again in the table of contents. Compare with spaces and case removed,
    which is what makes `No-Overhead SINQ` match `(No-Overhead SINQ)`.
    """
    flat = lambda s: re.sub(r'\s+', '', s).lower()
    return flat(original) in flat(translated)


# A heading's original-language gloss is there so a reader can match it to the
# paper; a cross-reference left raw inside it helps nobody. GAN's "Convergence
# of Algorithm \ref{alg:AGF}" reached the page as "(Convergence of Algorithm
# {alg:AGF})": the Korean half had its reference resolved, because
# resolve_references runs BEFORE this pass, and the gloss is lifted from the
# original afterwards, where nothing has touched it.
# `[a-z]{2,12}` and a key of word characters both assumed a naming convention.
# Vershynin labels his sections `{s: sums matrices}` -- a one-letter prefix and
# spaces in the key -- so ten headings kept a raw `{s: introduction}` beside
# their translated title.
_GLOSS_REF_RE = re.compile(
    r'\s*\\[a-zA-Z]*ref\*?\s*\{([^{}]*)\}'
    r'|\s*\{([a-z]{1,12}:[^{}]{1,60})\}')


def _gloss_reference(original, numbers):
    r"""The source heading as a reader should see it.

    A heading like `For Section~\ref{s: introduction}` carries a pointer, not a
    word. Print the number it stands for -- the surrounding text already reads
    "For Section" -- and fall back to dropping it when the label is unknown,
    which is what this did for every reference before.
    """
    def sub(m):
        key = (m.group(1) or m.group(2) or '').strip()
        number = numbers.get(key) if numbers else None
        return ' %s' % number if number else ''

    return _GLOSS_REF_RE.sub(sub, original).strip()


def theorem_declarations(temp_dir):
    r"""[(pandoc_number, printed_label)] for every theorem-like, in order.

    Two tallies over the same walk. `pandoc_number` is what pandoc wrote into
    the chunk: it honours the shared counter of `\newtheorem{lmm}[thrm]{Lemma}`
    but knows nothing of `[section]`, so it runs 1..N across the paper. The
    printed label is what the paper prints — the same counter with the section
    reset and prefix `_counter_label` already applies to equations.

    A starred declaration gets `''`: `\newtheorem*{rmk}{Remark}` prints no
    number at all, and pandoc invents one anyway — six of them in Maynard, and
    no check could see them because nothing `\ref`s an unnumbered environment.
    """
    flat = os.path.join(temp_dir, 'flat.tex')
    if not os.path.exists(flat):
        return []
    try:
        with open(flat, 'r', encoding='utf-8', errors='replace') as fh:
            tex = strip_tex_comments(fh.read(), keep_definitions=True)
    except OSError:
        return []

    envs = read_theorem_environments(tex)
    starred = _read_starred_theorem_envs(tex)
    if not envs and not starred:
        return []
    parents = read_counter_parents(tex)
    fixed = read_fixed_counter_prefix(tex)

    names = sorted(set(envs) | set(starred), key=lambda n: (-len(n), n))
    scan = re.compile(
        r'\\((?:sub)*)section(\*?)\s*\{'
        r'|\\begin\{(' + '|'.join(re.escape(n) for n in names) + r')\}')

    section_head = ''
    pandoc_n, paper_n = {}, {}
    out = []
    for m in scan.finditer(tex):
        if m.group(1) is not None and m.group(2) is not None:
            if m.group(2) == '*' or m.group(1).count('sub'):
                continue
            section_head = str(int(section_head or 0) + 1)
            for counter, parent in parents.items():
                if parent == 'section':
                    paper_n[counter] = 0
            continue
        env = m.group(3)
        if env in starred:
            pandoc_n[env] = pandoc_n.get(env, 0) + 1
            out.append((pandoc_n[env], ''))
            continue
        group = envs.get(env, 'theorem')
        pandoc_n[group] = pandoc_n.get(group, 0) + 1
        paper_n[group] = paper_n.get(group, 0) + 1
        out.append((pandoc_n[group],
                    _counter_label(group, paper_n[group], parents,
                                   section_head, fixed)))
    return out


def _read_starred_theorem_envs(tex):
    r"""Names declared with `\newtheorem*`, which print without a number."""
    out = set()
    for m in _NEWTHEOREM_RE.finditer(tex):
        if m.group(1) and m.group(2).strip():
            out.add(m.group(2).strip())
    return out


def number_theorem_statements(md_text, temp_dir, lang_cfg=None):
    r"""Give each `**Theorem 1**` the number the paper prints. (text, stats).

    The reference half of this was fixed first and on its own made the book
    WORSE: prose saying "정리 1.1" over a declaration line reading "정리 1" is
    less usable than two numbers that agree with each other and with nothing
    else. Both halves or neither.

    `**정리 1**` is characters in `output.md`, and this build rewrites that
    line as a matter of routine — the claim that pandoc owns theorem numbers
    (K113) was about pandoc's output, not about the book (K130).

    Refuses wholesale, the way `number_sections` does, and on a stronger
    condition: the site COUNT must match and every number already printed must
    equal the flat tally. If pandoc numbered anything differently from the way
    modelled here, nothing is rewritten and the reason is reported.
    """
    stats = {'numbered': 0, 'unnumbered': 0, 'skipped_reason': None}
    wanted = theorem_declarations(temp_dir)
    if not wanted:
        stats['skipped_reason'] = 'no theorem environments declared'
        return md_text, stats

    words = (lang_cfg or {}).get('theorem_words') or ()
    if not words:
        stats['skipped_reason'] = 'no theorem vocabulary for this language'
        return md_text, stats
    alt = '|'.join(re.escape(w) for w in
                   sorted(words, key=lambda w: (-len(w), w)))
    site_re = re.compile(r'\*\*(' + alt + r')\s+(\d+)\*\*')

    sites = list(site_re.finditer(md_text))
    if len(sites) != len(wanted):
        stats['skipped_reason'] = (
            '%d theorem-like(s) in flat.tex vs %d numbered statement(s) in the '
            'translation — refusing to guess' % (len(wanted), len(sites)))
        return md_text, stats
    for m, (flat_n, _label) in zip(sites, wanted):
        if int(m.group(2)) != flat_n:
            stats['skipped_reason'] = (
                'statement %r carries %s where the tally says %d — refusing '
                'to guess' % (m.group(0), m.group(2), flat_n))
            return md_text, stats

    pieces, cursor = [], 0
    for m, (_flat_n, label) in zip(sites, wanted):
        pieces.append(md_text[cursor:m.start()])
        if label:
            pieces.append('**%s %s**' % (m.group(1), label))
            stats['numbered'] += 1
        else:
            pieces.append('**%s**' % m.group(1))
            stats['unnumbered'] += 1
        cursor = m.end()
    pieces.append(md_text[cursor:])
    return ''.join(pieces), stats


def number_sections(md_text, temp_dir, bilingual=True):
    """Prefix each heading with its number in the original, and the original
    title. Returns (text, stats)."""
    stats = {'numbered': 0, 'skipped_reason': None}
    tex_heads = read_tex_headings(temp_dir)
    if not tex_heads:
        stats['skipped_reason'] = 'no flat.tex (not an arXiv-sourced build)'
        return md_text, stats

    md_heads = list(_HEADING_LINE_RE.finditer(md_text))
    if len(md_heads) != len(tex_heads):
        stats['skipped_reason'] = (
            f'{len(tex_heads)} headings in flat.tex vs {len(md_heads)} in the '
            f'translation — refusing to guess')
        return md_text, stats
    for m, (level, _title, _numbered) in zip(md_heads, tex_heads):
        if len(m.group(1)) != level:
            stats['skipped_reason'] = (
                f'heading levels diverge at {m.group(2)!r} — refusing to guess')
            return md_text, stats

    labels, pdf_stats = read_pdf_section_prefixes(temp_dir, tex_heads)
    if labels is None:
        stats['skipped_reason'] = (
            'cannot check numbering against the original (%s) -- refusing to '
            'invent a scheme' % pdf_stats['reason'])
        return md_text, stats
    found = pdf_stats['matched'] + pdf_stats['unnumbered']
    locatable = locatable_headings(len(tex_heads), pdf_stats)
    if found < enough_located(locatable):
        stats['skipped_reason'] = (
            'only %d of %d locatable headings could be found in the original '
            'PDF — refusing to guess' % (found, locatable))
        return md_text, stats
    stats['pdf'] = pdf_stats
    labels = ['' if lb is None else lb for lb in labels]
    gloss_numbers = build_label_numbers(temp_dir)
    pieces, cursor = [], 0
    for m, label, (_lvl, original, _num) in zip(md_heads, labels, tex_heads):
        translated = m.group(2).strip()
        if re.match(r'^(?:[IVXLC]+|[A-Z]|\d+)[.)] ', translated):
            continue  # already numbered; do not double up
        text = f'{label} {translated}'.strip()
        if bilingual and original and not _already_says(translated, original):
            gloss = _gloss_reference(original, gloss_numbers)
            if gloss:
                text += f' ({gloss})'
        pieces.append(md_text[cursor:m.start()])
        pieces.append(f'{m.group(1)} {text}')
        cursor = m.end()
        stats['numbered'] += 1
    pieces.append(md_text[cursor:])
    return ''.join(pieces), stats

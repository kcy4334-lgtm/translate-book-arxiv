# -*- coding: utf-8 -*-
r"""Resolve a paper's OWN shorthand macros before pandoc reads the source.

Every conference class ships abbreviations the author then writes everywhere:
cvpr.sty's `\ie`, dtrt.sty's `\parhead`, neurips_2024.sty's `\answerYes`,
naaclhlt2019.sty's `\newcite`. pandoc never sees those definitions -- a `.sty`
is not `\input`, so `flatten_tex` does not inline it -- and an unknown control
sequence survives `+raw_tex` verbatim. resnet's finished Korean book prints
`\ie` five times mid-sentence where the paper prints "i.e.".

Handing pandoc the definitions instead is worse, and measured so: inlining
dtrt.sty's real `\parhead` made pandoc emit NOTHING for
`\parhead{Exploiting Speculative Execution}` -- thirteen run-in headings
deleted, K110's swallow again -- and cvpr.sty's `\onedot`, which is
`\futurelet` lookahead, came out as `*i.e*..` with the period doubled because
pandoc cannot evaluate `\ifx` and emits both branches.

So the expansion happens here, under three rules that keep it from becoming
K121 (half a package is worse than none):

  * A body must reduce to LaTeX pandoc has a reader for. Anything still
    carrying `\ifx`, `\csname`, `\expandafter` or a `\newif` flag is refused
    whole -- never half-expanded.
  * A parameter must survive. If `#1` is gone after resolution, the macro eats
    its argument and expanding it would delete the author's text.
  * Two different definitions of one name means the source chose between them
    with a conditional this module does not evaluate. Refused, and REPORTED --
    spectre's `\dtcolornote` is defined once to print an author's margin note
    and once to print nothing, and picking the default (`\dt@notestrue`, line
    127 of dtrt.sty) would be picking the wrong one: the paper is built
    `camera`, and its PDF contains "NeedReference" zero times.

Refusal leaves the token exactly as it is today. Nothing this module declines
to do makes the book worse than it already is.
"""

import os
import re

MAX_DEPTH = 8

# Commands that occupy space but set no glyph. Dropping them is what turns a
# real macro body into something pandoc can read.
_NO_GLYPH = (
    'smallskip', 'medskip', 'bigskip', 'noindent', 'indent', 'ignorespaces',
    'ignorespacesafterend', 'xspace', 'null', 'relax', 'protect', 'leavevmode',
    'unskip', 'boldmath', 'unboldmath', 'normalfont', 'centering', 'raggedright',
    'allowbreak', 'nobreak', 'strut', 'hfill', 'vfill', 'par', 'noalign',
    # Size switches. These are the class's own `\@setfontsize` wrappers, which
    # are defined in terms of themselves -- resolving `\small` from bert's
    # class reported "recursive definition" and refused the macro that used it.
    'tiny', 'scriptsize', 'footnotesize', 'small', 'normalsize',
    'large', 'Large', 'LARGE', 'huge', 'Huge', 'smaller', 'larger',
)
_NO_GLYPH_RE = re.compile(r'\\(?:%s)(?![A-Za-z])' % '|'.join(_NO_GLYPH))

# Colour that paints a background rather than a glyph. `\cellcolor{gray!10}`
# takes a colour SPEC, not text, so dropping it with its argument loses
# nothing a reader sees -- SINQ's `\ours{#1}` is `\cellcolor{...}#1` and is
# otherwise refused, leaving `\ours` printed 92 times.
_DECORATION = ('cellcolor', 'rowcolor', 'columncolor', 'arrayrulecolor',
               'rowcolors', 'hypersetup', 'pagecolor')
_DECORATION_RE = re.compile(
    r'\\(?:%s)\s*(?:\[[^\[\]]*\])?\s*\{[^{}]*\}' % '|'.join(_DECORATION))

# `\ ` is an escaped interword space, and it is load-bearing: spectre's
# `\newcommand{\etal}{et~al.\ }` relies on it because LaTeX eats the space
# after a control word. Stripping it welds the next word on, and stripping
# only the space leaves a lone trailing backslash, which K136 records as the
# one thing that is NOT invalid LaTeX and so passes every check.
_ESCAPED_SPACE_RE = re.compile(r'\\ ')

# A body that is nothing but horizontal space is INDENTATION, and deleting it
# is the tabbing hazard wearing different clothes. `_TABBING_BODY_RE` only
# knows the tabbing primitives, so `\newcommand{\tab}{\hspace{1em}}` fell past
# it: `_GLUE_RE` ate the body, `_sets_no_glyph` saw nothing left, and the
# macro resolved to the empty string. CafeQ ships `\spcin` as `\hspace{1.0in}`
# and Shor writes his listing indentation as runs of `\ ` inline -- a paper
# that puts either behind a name would have had it removed.
_SPACING_TOKEN_RE = re.compile(
    r'\\(?:hspace\*?|vspace\*?|hskip|vskip|kern|quad|qquad|thinspace'
    r'|enspace|hfill|hfil|space)\s*\{?[^{}\s]*\}?'
    r'|\\[,;:!]'
    r'|\\ '
    r'|\s')


def _is_spacing_only(body):
    return bool(body.strip()) and not _SPACING_TOKEN_RE.sub('', body).strip()


# Any TeX conditional opens with `\if...` and closes with `\fi`; `\else` splits
# it. Only the depth matters here, not which conditional it is.
_IF_RE = re.compile(r'\\(if[a-zA-Z@]*|else|fi)(?![a-zA-Z@])')


def _resolve_ifmmode(body):
    r"""`\ifmmode A\else B\fi` -> `B`; `\ifmmode A\fi` -> nothing.

    Sound here and nowhere else. This module rewrites ONLY outside maths — the
    protected spans are the whole point of it — so at every site it touches the
    condition is false by construction. That is not a guess about the paper; it
    is the module's own contract read back.

    It is worth doing because the alternative is refusing the macro whole:
    ATLAS writes `\GeV` as `\ifmmode {\mathrm{\ Ge\kern -0.1em V}}\else
    \textrm{Ge\kern -0.1em V}\fi`, and that name stands verbatim 35 times in
    higgs_atlas's finished markdown, `\TeV` 25 more.

    No other conditional is touched. `\ifdim`, `\ifnum` and a package's own
    `\ifFOO` are genuinely unknown here and still refuse the body.
    """
    for _ in range(MAX_DEPTH):
        start = body.find('\\ifmmode')
        if start < 0:
            break
        if re.match(r'\\ifmmode[a-zA-Z@]', body[start:]):
            break                                   # a longer control word
        depth, else_at, end = 0, None, None
        for m in _IF_RE.finditer(body, start):
            kind = m.group(1)
            if kind.startswith('if'):
                depth += 1
            elif kind == 'else':
                if depth == 1 and else_at is None:
                    else_at = m
            else:
                depth -= 1
                if depth == 0:
                    end = m
                    break
        if end is None:
            break                                   # unbalanced; refused below
        taken = body[else_at.end():end.start()] if else_at else ''
        body = body[:start] + taken + body[end.end():]
    return body

# `\catcode13=10` -- an assignment, not text. Without this the digits survive
# as "printable content" and a body that sets no glyph looks like one that does.
_ASSIGN_RE = re.compile(
    r'\\(?:catcode|count|dimen|skip|muskip|chardef|mathcode|lccode|uccode|sfcode)'
    r'\s*[\'"`]?\\?[A-Za-z@]*\d*\s*=?\s*-?[\d.]*\s*[a-z]{0,2}')

# `\hskip 0.9em plus 0.3em minus 0.3em` -- a glue specification, all of it.
_GLUE_RE = re.compile(
    r'\\(?:hskip|vskip|kern|hspace\*?|vspace\*?)\s*'
    r'\{?\s*-?[\d.]*\s*[a-z]{0,2}\s*\}?'
    r'(?:\s*(?:plus|minus)\s*-?[\d.]*\s*[a-z]{0,2})*')

# Font switches that govern the rest of their group, and the wrapper each one
# becomes. `{\bfseries X}` is how a package writes what `\textbf{X}` means.
_FONT_GROUP = {
    'bfseries': 'textbf', 'bf': 'textbf',
    'itshape': 'emph', 'it': 'emph', 'em': 'emph',
    'ttfamily': 'texttt', 'tt': 'texttt',
    'scshape': 'textsc', 'sc': 'textsc',
}
_FONT_GROUP_RE = re.compile(r'\\(%s)(?![A-Za-z])' % '|'.join(_FONT_GROUP))

# Commands pandoc reads. A resolved body may keep these and nothing else.
_PANDOC_READS = frozenset((
    'emph', 'textbf', 'textit', 'texttt', 'textsc', 'textrm', 'textsf',
    'underline', 'textcolor', 'color', 'mbox', 'text', 'texorpdfstring',
    'cite', 'citet', 'citep', 'citealp', 'citeauthor', 'citeyear', 'cites',
    'ref', 'eqref', 'autoref', 'cref', 'Cref', 'label', 'url', 'href',
    'footnote', 'ensuremath', 'mathrm', 'mathit', 'mathbf', 'so', 'st',
))

# Machinery with no reader meaning. One of these anywhere and the body is
# refused -- this is the line that keeps a half-expansion from shipping.
_MACHINERY_RE = re.compile(
    r'\\(?:if[a-zA-Z@]*|else|fi|futurelet|csname|endcsname|expandafter'
    r'|@ifnextchar|@ifundefined|newif|let|global|edef|gdef|xdef|aftergroup'
    r'|begingroup|endgroup|catcode|the|number|romannumeral|string|meaning'
    r'|ifthenelse|boolean|newbool|booltrue|boolfalse|ifbool|setbool)'
    r'(?![A-Za-z])')

_VERBATIM_RE = re.compile(
    r'\\begin\{(verbatim|lstlisting|minted|Verbatim|alltt)\*?\}'
    r'.*?\\end\{\1\*?\}', re.DOTALL)

# Names this module must not touch even when the paper redefines them, because
# something downstream already does the job better. Measured, each one:
#
#   `\cite`   naaclhlt2019.sty makes it `\citep`, and rewriting 119 calls across
#             bert and SINQ would put citation rendering -- placeholdered as
#             `C####`, mapped by `build_citation_map`, rendered by citeproc --
#             through a textual substitution instead.
#   `\url`    the paper makes it `\texttt{#1}`. pandoc's reader makes it a LINK.
#             Expanding first is a downgrade that nothing would report.
#   `\newblock` is glue, so it resolves to nothing; deleting all 115 of them
#             runs adjacent reference fields together.
#
# Sectioning and front matter are here for the same reason: pandoc reads them,
# and `merge_and_build` reconstructs their numbering from the source.
_STRUCTURAL = frozenset((
    'section', 'subsection', 'subsubsection', 'paragraph', 'subparagraph',
    'chapter', 'part', 'maketitle', 'title', 'author', 'date', 'thanks',
    'caption', 'captionof', 'item', 'bibitem', 'newblock', 'thebibliography',
    'footnotemark', 'footnotetext', 'appendix', 'abstract', 'newtheorem',
    'begin', 'end', 'input', 'include', 'bibliography', 'bibliographystyle',
))
_NEVER_EXPAND = frozenset(_PANDOC_READS) | _STRUCTURAL

# A tabbing control, not an abbreviation. Shor writes `\newcommand{\tab}{\>}`
# and uses it 29 times to set the indentation of three algorithm listings;
# `neutralize_tabbing_tabs` turns those into the four-space steps that made the
# printed pseudocode match the paper. Resolving `\tab` to nothing -- which is
# what it is, typographically -- would delete all of it first.
_TABBING_BODY_RE = re.compile(
    r'^\s*(?:\\[>=<+\-\'`]|\\kill|\s)+\s*$')


class Definition(object):
    """One `\\newcommand` / `\\def`, with where it came from."""

    __slots__ = ('name', 'arity', 'optional', 'body', 'source', 'span',
                 'evidenced', 'kind', 'arg_suffix')

    def __init__(self, name, arity, optional, body, source, span, kind='def'):
        # Punctuation the macro appends to its argument unless the argument
        # already carries some. Set by `resolve` when it recognises the shape.
        self.arg_suffix = ''
        self.name = name
        self.arity = arity
        self.optional = optional      # first argument is optional (LaTeX [n][d])
        self.body = body
        self.source = source
        self.span = span              # (start, end) in its own source text
        self.kind = kind              # provide | renew | new | declare | def
        # Set when the printed paper picked this definition over a competing
        # one. It licenses the argument-discarding case below: the evidence IS
        # that the argument does not appear in the paper.
        self.evidenced = False

    def __repr__(self):
        return '<%s/%d from %s>' % (self.name, self.arity, self.source)


def _group_end(text, open_at):
    """Index just past the `}` matching the `{` at open_at, or -1."""
    if open_at >= len(text) or text[open_at] != '{':
        return -1
    depth = 0
    i = open_at
    while i < len(text):
        ch = text[i]
        if ch == '\\':
            i += 2
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return -1


def strip_comments(tex):
    """Blank out LaTeX comments, keeping every offset intact."""
    out = []
    i = 0
    n = len(tex)
    while i < n:
        ch = tex[i]
        if ch == '\\' and i + 1 < n:
            out.append(tex[i:i + 2])
            i += 2
            continue
        if ch == '%':
            j = tex.find('\n', i)
            if j < 0:
                j = n
            out.append(' ' * (j - i))
            i = j
            continue
        out.append(ch)
        i += 1
    return ''.join(out)


_NEWCOMMAND_RE = re.compile(
    r'\\(?:new|renew|provide)command\s*\*?\s*'
    r'(?:\{\s*\\([A-Za-z@]+)\s*\}|\\([A-Za-z@]+))'
    r'\s*(?:\[\s*(\d)\s*\])?\s*(?:\[([^\]]*)\])?\s*(?=\{)')
_DECLARE_RE = re.compile(
    r'\\DeclareRobustCommand\s*\*?\s*'
    r'(?:\{\s*\\([A-Za-z@]+)\s*\}|\\([A-Za-z@]+))'
    r'\s*(?:\[\s*(\d)\s*\])?\s*(?:\[([^\]]*)\])?\s*(?=\{)')
# `\def\name#1#2{...}` -- undelimited parameters only. A delimited one
# (`\def\x#1.{...}`) is a different language and `neutralize_tex_defs`
# already drops those before pandoc chokes on them.
_DEF_RE = re.compile(
    r'\\(?:long|global|outer|protected)?\s*(?:e|g|x)?def\s*'
    r'\\([A-Za-z@]+)\s*((?:#\d\s*)*)(?=\{)')


# Which declaration was used. It decides the winner when one name is defined
# twice, and LaTeX's rule is not "the last one": `\providecommand` on a name
# that already exists does NOTHING.
_KIND_PATTERNS = (
    ('provide', re.compile(r'\\providecommand')),
    ('renew', re.compile(r'\\renewcommand')),
    ('new', re.compile(r'\\newcommand')),
    ('declare', re.compile(r'\\DeclareRobustCommand')),
)


def _kind_of(head):
    for name, rx in _KIND_PATTERNS:
        if rx.match(head):
            return name
    return 'def'


def _latex_order(entries):
    r"""Processing order: a class or package is read before the preamble.

    `shipped_sources` yields flat.tex first because that is the document, but
    LaTeX loads `\usepackage` and `\documentclass` before reading a line of
    the preamble, and which definition wins depends on that order.
    """
    return ([d for d in entries if d.source != 'flat.tex']
            + [d for d in entries if d.source == 'flat.tex'])


def settle_by_declaration(entries):
    r"""The winner among competing definitions, where LaTeX itself decides.

    Two of the corpus's cases resolve in OPPOSITE directions, so source order
    alone must get one of them wrong:

      * higgs_atlas `\ttbar` -- `\def` in atlasphysics.sty, `\renewcommand` in
        flat.tex. The document preamble runs last, so flat.tex wins.
      * planck `\apj` -- `\def` in aa.cls, `\providecommand` in flat.tex. The
        provide is a no-op on a defined name, so aa.cls wins.

    Returns None when LaTeX's rules do not decide, which is the case that
    matters most: one name written once per branch of a conditional, where
    only one branch ever runs. spectre's `\dtcolornote` and `\footnote` are
    both that, and the printed paper (H38) is what settles them.
    """
    order = _latex_order(entries)
    kinds = set(d.kind for d in order)
    if kinds == {'provide'}:
        return order[0]                 # later ones are no-ops
    if len(set(d.source for d in order)) == 1 and len(kinds) == 1:
        return None                     # same file, same declaration: branches
    current = None
    for d in order:
        if d.kind == 'provide':
            if current is None:
                current = d
        else:
            current = d
    return current


def read_definitions(sources):
    r"""{name: [Definition, ...]} from (label, text) pairs, in reading order.

    `sources` is every file the paper SHIPS -- flat.tex plus the .sty/.cls in
    its tarball. A name found here is the paper's own by construction: TeX
    Live's copy of a standard package is not in the tarball.
    """
    found = {}
    for label, text in sources:
        clean = strip_comments(text)
        for rx, has_params in ((_NEWCOMMAND_RE, False),
                               (_DECLARE_RE, False),
                               (_DEF_RE, True)):
            for m in rx.finditer(clean):
                if has_params:
                    name = m.group(1)
                    arity = len(re.findall(r'#\d', m.group(2) or ''))
                    optional = False
                else:
                    name = m.group(1) or m.group(2)
                    arity = int(m.group(3)) if m.group(3) else 0
                    optional = m.group(4) is not None
                open_at = m.end()
                close = _group_end(clean, open_at)
                if close < 0:
                    continue
                body = text[open_at + 1:close - 1]
                found.setdefault(name, []).append(
                    Definition(name, arity, optional, body, label,
                               (m.start(), close),
                               _kind_of(clean[m.start():m.start() + 40])))
    return found


def _is_onedot(defs):
    r"""True when `\onedot` is the cvpr/eccv abbreviation-period idiom.

    cvpr.sty says it in words above the definition: "Add a period to the end
    of an abbreviation unless there's one already, then \xspace." The shape is
    checked rather than the name trusted, because a paper may bind the name to
    something else entirely.
    """
    one = defs.get('onedot')
    at_one = defs.get('@onedot')
    if not one or not at_one:
        return False
    if len(one) != 1 or len(at_one) != 1:
        return False
    return (re.search(r'\\futurelet\s*\\@let@token\s*\\@onedot',
                      one[0].body) is not None
            and re.search(r'\\ifx\s*\\@let@token\s*\.', at_one[0].body)
            is not None)


def _drop_no_glyph(body):
    body = _ESCAPED_SPACE_RE.sub(' ', body)
    body = _DECORATION_RE.sub('', body)
    body = _ASSIGN_RE.sub('', body)
    body = _GLUE_RE.sub('', body)
    body = _NO_GLYPH_RE.sub('', body)
    return body


# What is left of a body once every command has been removed. If nothing
# printable remains and the macro takes no argument, it sets no glyph -- which
# is a resolution (to nothing), not a failure. dtrt.sty's
# `\dt@ignorespacesandimplicitepars` is four grouping primitives and a catcode
# assignment; refusing it refused `\parhead` with it, and `\parhead` is
# thirteen real headings.
_CMD_RE = re.compile(r'\\(?:[A-Za-z@]+|.)')


def _sets_no_glyph(body, defs):
    r"""True only when EVERY command in the body is known to print nothing.

    Deleting commands first and asking what is left over is the wrong order:
    bert's `\newcite` is defined as `\citet`, whose body erases to the empty
    string under that test, and resolving it to nothing deleted the citation.
    A command that pandoc reads, or that the paper defines, prints something
    until proven otherwise.
    """
    rest = _ASSIGN_RE.sub('', body)
    for n in re.findall(r'\\([A-Za-z@]+)', rest):
        if n in _PANDOC_READS or n in defs:
            return False
        if n not in _NO_GLYPH and not _MACHINERY_RE.match('\\' + n):
            return False
    stripped = _CMD_RE.sub('', rest)
    return not re.search(r'[^\s{}\[\]%]', stripped) and '#' not in body


def _apply_font_groups(body):
    r"""`{\bfseries X}` -> `\textbf{X}`, so pandoc reads the emphasis."""
    for _ in range(4):
        m = _FONT_GROUP_RE.search(body)
        if not m:
            break
        # Find the group this switch governs: the innermost `{` before it.
        start = body.rfind('{', 0, m.start())
        if start < 0:
            body = body[:m.start()] + body[m.end():]
            continue
        close = _group_end(body, start)
        if close < 0:
            body = body[:m.start()] + body[m.end():]
            continue
        inner = (body[start + 1:m.start()] + body[m.end():close - 1]).strip()
        body = (body[:start] + '\\%s{%s}' % (_FONT_GROUP[m.group(1)], inner)
                + body[close:])
    return body


# `#1\ifdt@Punct \else .\fi` -- dtrt.sty line 699, and the shape of every
# "add a stop unless one is there" helper: the argument, then a conditional
# whose FALSE branch is a single punctuation mark. The flag is set by four
# delimited-parameter `\def`s that `read_definitions` deliberately does not
# read, so the conditional cannot be evaluated -- but it does not need to be.
# Whether the argument already ends in punctuation is visible at the call
# site, where `expand_in_source` holds the literal text.
#
# Confirmed against the artefact before it was written: all 13 of spectre's
# run-in headings are printed WITH the period and none without, and not one
# of them already ends in punctuation.
_PUNCT_SUFFIX_RE = re.compile(
    r'#1\s*\\if[a-zA-Z@]*\s*\\else\s*([.?!:;,])\s*\\fi')
_ALREADY_PUNCTUATED_RE = re.compile(r'[.?!:;,]\s*$')


def _unwrap_unresolved(body, defs):
    r"""`\dt@MaybeAddPunct{#1}` -> `#1` when that macro does print its argument.

    An unresolved wrapper is the dangerous case in both directions: keep it and
    pandoc drops the wrapper AND its contents (K110); drop the argument with it
    and the author's text is gone. The tie is broken by evidence -- the
    wrapper's OWN body is read, and the argument is kept only if that body
    references the parameter, i.e. the macro is one that prints what it is
    given.
    """
    suffix = ''
    for _ in range(MAX_DEPTH):
        target = None
        for m in re.finditer(r'\\([A-Za-z@]+)\s*\{', body):
            name = m.group(1)
            if name in _PANDOC_READS:
                continue
            own = defs.get(name)
            # Keep the argument only if the wrapper's own body prints one.
            if own and len(own) == 1 and re.search(r'#\d', own[0].body):
                target = m
                break
        if not target:
            break
        # Before dropping the wrapper, read what it was adding. A "stop unless
        # one is there" helper is the difference between a heading that prints
        # as the paper prints it and one that loses its period.
        punct = _PUNCT_SUFFIX_RE.search(defs[target.group(1)][0].body)
        if punct and not suffix:
            suffix = punct.group(1)
        close = _group_end(body, target.end() - 1)
        if close < 0:
            break
        body = (body[:target.start()] + body[target.end():close - 1]
                + body[close:])
    return body, suffix


def resolve(name, defs, seen=None, depth=0):
    r"""Reduce one macro to pandoc-readable LaTeX, or None with a reason.

    Returns (body, None) on success, (None, reason) on refusal.
    """
    if depth > MAX_DEPTH:
        return None, 'expansion did not terminate'
    seen = set(seen or ())
    if name in seen:
        return None, 'recursive definition'
    seen.add(name)

    entries = defs.get(name)
    if not entries:
        return None, 'no definition in the shipped source'
    if depth == 0 and name in _NEVER_EXPAND:
        return None, 'pandoc reads this one; its own reader beats a substitution'
    if any(_TABBING_BODY_RE.match(d.body) for d in entries):
        return None, 'a tabbing control, handled where the tab stops are read'
    if any(_is_spacing_only(d.body) for d in entries):
        return None, ('the body is horizontal space; resolving it to nothing '
                      'would delete indentation, not a name')
    bodies = set(d.body.strip() for d in entries)
    if len(bodies) > 1:
        # LaTeX decides most of these itself, and not by source order: a
        # `\providecommand` on a defined name does nothing. Only when its
        # rules are silent -- one name written once per conditional branch --
        # is the printed paper asked instead (H38).
        settled = settle_by_declaration(entries)
        if settled is None:
            return None, ('%d different definitions (%s); the source picks one '
                          'with a conditional this does not evaluate'
                          % (len(bodies),
                             ', '.join(sorted(set(d.source for d in entries)))))
        entries = [settled]
    d = entries[0]
    body = d.body

    # The one conditional whose value this module knows: it rewrites only
    # outside maths, so `\ifmmode` is false at every site it touches.
    body = _resolve_ifmmode(body)
    if d.arity == 0 and _is_spacing_only(body):
        return None, ('the body is horizontal space; resolving it to nothing '
                      'would delete indentation, not a name')

    # A body that is nothing but grouping and assignment prints nothing. That
    # is an answer, not a failure -- and refusing it refuses every macro that
    # calls it.
    #
    # Only when the macro takes no argument. bert defines `\eat[1]{\ignorespaces}`
    # and the same test would resolve it to nothing WITH the author's text
    # inside, silently, before the argument check below ever runs. A macro that
    # takes an argument and prints nothing is refused instead.
    if d.arity == 0 and _sets_no_glyph(body, defs):
        return '', None

    # cvpr.sty's abbreviation period, recognised by shape and by the printed
    # paper: resnet's PDF has "i.e." five times, never "i.e" alone.
    if _is_onedot(defs):
        body = re.sub(r'\\onedot(?![A-Za-z])', '.', body)

    # Expand the paper's own nested shorthand first, arguments and all.
    # spectre wraps its note command: `\paul{...}` is `\dtcolornote[Paul]{red}{#1}`,
    # so stopping at argument-free macros left eight of the twelve notes in
    # place after the wrapped one had been settled.
    tried = set()
    used_inner = []
    for _ in range(MAX_DEPTH * 4):
        hit = None
        for m in re.finditer(r'\\([A-Za-z@]+)(?![A-Za-z])', body):
            inner = m.group(1)
            if inner in _PANDOC_READS or inner in _NO_GLYPH or inner in tried:
                continue
            if inner in defs:
                hit = m
                break
        if not hit:
            break
        inner = hit.group(1)
        sub, why = resolve(inner, defs, seen, depth + 1)
        if sub is None:
            # Not fatal on its own. `\parhead` calls `\dt@MaybeAddPunct`, which
            # is a punctuation test written in `\ifx`; refusing the caller for
            # it cost thirteen headings. Leave the call in place and let
            # `_unwrap_unresolved` decide whether its argument is printed.
            tried.add(inner)
            continue
        d_inner = defs[inner][0]
        used_inner.append(inner)
        if d_inner.arity:
            taken = _take_args(body, hit.end(), d_inner.arity, d_inner.optional)
            if taken is None:
                return None, ('via \\%s: the call does not match its '
                              'definition' % inner)
            args, end = taken
            for n, arg in enumerate(args, 1):
                sub = sub.replace('#%d' % n, arg)
            body = body[:hit.start()] + sub + body[end:]
        else:
            body = body[:hit.start()] + sub + body[hit.end():]

    body = _drop_no_glyph(body)
    body = _apply_font_groups(body)
    body, suffix = _unwrap_unresolved(body, defs)
    body = _drop_no_glyph(body)

    if _MACHINERY_RE.search(body):
        return None, 'body still carries TeX machinery pandoc cannot evaluate'

    leftovers = [n for n in re.findall(r'\\([A-Za-z@]+)(?![A-Za-z])', body)
                 if n not in _PANDOC_READS]
    if leftovers:
        return None, ('unresolved command(s): %s'
                      % ', '.join('\\' + x for x in sorted(set(leftovers))))

    # An argument that vanished is normally the refusal that matters most --
    # expanding would delete the author's text and nothing downstream counts
    # the loss. It is licensed only when the printed paper established that
    # this text is not on the page, and that verdict is inherited by a wrapper
    # that does nothing but pass its argument along (`\paul` -> `\dtcolornote`).
    evidenced = d.evidenced or any(
        defs[n][0].evidenced for n in used_inner if n in defs)
    if not evidenced:
        for i in range(1, d.arity + 1):
            if '#%d' % i not in body:
                return None, ('argument #%d is discarded; expanding would '
                              'delete the text the author wrote there' % i)

    # A trailing space survives on purpose. `\etal` is `et~al.\ ` because
    # LaTeX eats the space after a control word; strip it and the next word is
    # welded on ("et al.analyze").
    if suffix:
        d.arg_suffix = suffix
    tail = ' ' if body[-1:] in (' ', '\t') else ''
    return body.strip() + tail, None


# --- rewriting the usages ---------------------------------------------------

# Maths is left alone on purpose. The leak this module exists for is a name
# that reached the PROSE; inside `$...$` the same name is texmath's business,
# and `check_math_fidelity` compares the formulas it finds against the source.
# Rewriting there would move a problem into the one place that is measured.
_MATH_SPAN_RE = re.compile(
    r'\$\$.*?\$\$'
    r'|(?<!\\)\$(?:\\.|[^$\\])*\$'
    r'|(?<!\\)\\\[.*?(?<!\\)\\\]'
    r'|(?<!\\)\\\(.*?(?<!\\)\\\)'
    r'|\\begin\{(equation|align|eqnarray|gather|multline|displaymath|array'
    r'|split|cases|aligned|alignat|math|subequations|gathered|flalign'
    r'|IEEEeqnarray|dmath|empheq)\*?\}.*?\\end\{\1\*?\}',
    re.DOTALL)

# The same environments, for the case where a macro opens one. planck defines
# `\be` as `\begin{equation}` and uses it 16 times, `\beglet` as
# `\begin{subequations}` 19 times; `_MATH_SPAN_RE` sees no `\begin` at all and
# the maths inside was rewritten as if it were prose. `\twoonesig` is worse
# than an alias -- it CONSTRUCTS the display, so the formula arrives as an
# argument in prose position and there is no `\begin` anywhere to find.
_MATH_ENVS = ('equation', 'align', 'eqnarray', 'gather', 'multline',
              'displaymath', 'array', 'split', 'cases', 'aligned', 'alignat',
              'math', 'subequations', 'gathered', 'flalign', 'IEEEeqnarray',
              'dmath', 'empheq')
_MATH_OPEN_RE = re.compile(
    r'^\s*\\begin\s*\{\s*(?:%s)\*?\s*\}' % '|'.join(_MATH_ENVS))
_MATH_CLOSE_RE = re.compile(
    r'^\s*\\end\s*\{\s*(?:%s)\*?\s*\}' % '|'.join(_MATH_ENVS))


def _blank(text, spans):
    """Replace each span with spaces, keeping every offset intact."""
    out = list(text)
    for start, end in spans:
        for i in range(start, min(end, len(out))):
            if out[i] != '\n':
                out[i] = ' '
    return ''.join(out)


def _alias_math_spans(tex, defs):
    r"""Displays opened by a MACRO rather than by `\begin`.

    An argument-free alias (`\be` -> `\begin{equation}`) is paired with its
    closing alias. One that takes arguments builds the display around them, so
    the whole call including its arguments is the formula.
    """
    openers, closers, builders = set(), set(), set()
    for name, entries in defs.items():
        if len(entries) != 1:
            continue
        body = entries[0].body
        if _MATH_OPEN_RE.match(body):
            (builders if entries[0].arity else openers).add(name)
        elif _MATH_CLOSE_RE.match(body):
            closers.add(name)

    spans = []
    if openers and closers:
        pat = re.compile(r'\\(%s)(?![A-Za-z])'
                         % '|'.join(re.escape(n)
                                    for n in sorted(openers | closers,
                                                    key=len, reverse=True)))
        depth, opened_at = 0, None
        for m in pat.finditer(tex):
            if m.group(1) in openers:
                if depth == 0:
                    opened_at = m.start()
                depth += 1
            elif depth:
                depth -= 1
                if depth == 0 and opened_at is not None:
                    spans.append((opened_at, m.end()))
                    opened_at = None
    for name in builders:
        d = defs[name][0]
        pat = re.compile(r'\\%s(?![A-Za-z])' % re.escape(name))
        for m in pat.finditer(tex):
            taken = _take_args(tex, m.end(), d.arity, d.optional)
            spans.append((m.start(), taken[1] if taken else m.end()))
    return spans


def _protected_spans(tex, defs):
    """(start, end) ranges no rewrite may touch."""
    spans = []
    for m in _VERBATIM_RE.finditer(tex):
        spans.append((m.start(), m.end()))
    spans.extend(_alias_math_spans(tex, defs))
    # A definition contains its own name. Rewriting there turns
    # `\newcommand{\etal}{et~al.\ }` into `\newcommand{et al. }{...}`.
    #
    # Located in THIS text rather than carried over from the file the
    # definition was read out of. In the pipeline those are the same string,
    # so a span taken from the other one happened to line up; when they differ
    # it protects an arbitrary stretch of prose instead, and the macros inside
    # it are silently left alone (K140).
    clean = strip_comments(tex)
    definitions = []
    for rx in (_NEWCOMMAND_RE, _DECLARE_RE, _DEF_RE):
        for m in rx.finditer(clean):
            close = _group_end(clean, m.end())
            if close > 0:
                definitions.append((m.start(), close))
    spans.extend(definitions)
    # Maths is paired on a text with the comments AND the definition bodies
    # blanked out, because a `$` inside a macro BODY is not a document
    # delimiter. planck defines `\Hunit` as `\ifmmode ...$\else ...\fi` — an
    # ODD number of `$`, which TeX balances through the conditional and a
    # regex cannot. Paired on the raw source, every later `$` paired inverted:
    # 328 spans that contained a blank line, which no formula does, and 73
    # rewrites landing INSIDE planck's formulas. Every other paper in the
    # corpus was 0, so nothing but a whole-corpus sweep would have shown it.
    spans.extend((m.start(), m.end())
                 for m in _MATH_SPAN_RE.finditer(_blank(clean, definitions)))
    spans.sort()
    return spans


def _in_span(pos, spans):
    for start, end in spans:
        if start <= pos < end:
            return True
        if start > pos:
            break
    return False


def _take_args(tex, at, arity, optional):
    """Read a call's arguments starting at `at`. Returns (args, end) or None."""
    args = []
    i = at
    if optional and arity:
        j = i
        while j < len(tex) and tex[j] in ' \t':
            j += 1
        if j < len(tex) and tex[j] == '[':
            close = tex.find(']', j)
            if close < 0:
                return None
            args.append(tex[j + 1:close])
            i = close + 1
            arity -= 1
        else:
            args.append('')           # the optional argument's default
            arity -= 1
    for _ in range(arity):
        j = i
        while j < len(tex) and tex[j] in ' \t\r\n':
            j += 1
        if j >= len(tex) or tex[j] != '{':
            return None
        close = _group_end(tex, j)
        if close < 0:
            return None
        args.append(tex[j + 1:close - 1])
        i = close
    return args, i


def _call_arguments(tex, name, entry, body_at, spans, limit=6, min_words=4):
    """Argument text from real call sites, longest first.

    Only a phrase of several words counts. spectre's `\\yval` is called with
    "processors", which occurs in the paper for reasons that have nothing to
    do with this macro; one common word is not evidence, and mixing it with
    real phrases turned a clear verdict into an inconclusive one.
    """
    found = []
    rx = re.compile(r'\\%s(?![A-Za-z])' % re.escape(name))
    for m in rx.finditer(tex, body_at):
        if _in_span(m.start(), spans):
            continue
        taken = _take_args(tex, m.end(), entry.arity, entry.optional)
        if taken is None:
            continue
        for arg in taken[0]:
            text = ' '.join(_CMD_RE.sub(' ', arg).split())
            if len(text.split()) >= min_words and re.search(r'[A-Za-z]{4}', text):
                found.append(text)
    found.sort(key=len, reverse=True)
    return found[:limit]


def _wrapper_samples(name, defs, tex, body_at, spans):
    r"""Call-site text of macros that pass their argument INTO `name`.

    spectre never calls `\dtcolornote` directly in the body -- all four
    occurrences are in the preamble, inside `\newcommand{\paul}` and its
    siblings. The text that would be printed arrives through those wrappers,
    so that is where the evidence is.
    """
    out = []
    for other, entries in defs.items():
        if other == name or len(entries) != 1:
            continue
        d = entries[0]
        if not re.search(r'\\%s(?![A-Za-z])' % re.escape(name), d.body):
            continue
        if not re.search(r'#\d', d.body):
            continue
        out.extend(_call_arguments(tex, other, d, body_at, spans))
    return out


def _appears_in_paper(samples, paper_text):
    """True if every sample is printed, False if none is, None if mixed.

    Matched as a CONTIGUOUS phrase. Asking instead whether a handful of the
    sample's words each occur somewhere in the paper answers yes for almost
    any English sentence -- "Delete the following as not background material"
    scored a hit on spectre because "following", "background" and "material"
    all appear elsewhere, and the mixed verdict refused the macro.
    """
    flat = ' '.join(paper_text.split())
    if not flat:
        return None
    hits = 0
    for s in samples:
        probe = ' '.join(_CMD_RE.sub(' ', s).split())
        words = probe.split()
        if len(words) > 6:
            probe = ' '.join(words[:6])
        if len(probe) < 8:
            continue
        if probe in flat:
            hits += 1
    if hits == 0:
        return False
    if hits == len(samples):
        return True
    return None


def disambiguate(name, defs, tex, paper_text, body_at, spans):
    r"""Pick between conflicting definitions using the printed paper.

    A macro defined once in each branch of a conditional cannot be resolved by
    reading the source alone -- the branch is chosen by a package option this
    module does not evaluate, and dtrt.sty's DEFAULT is the wrong one: line 127
    is `\newif\ifdt@notes \dt@notestrue`, but spectre is built `camera`, so the
    notes are off.

    The paper itself settles it. One candidate prints its argument, the other
    discards it; spectre's PDF contains "NeedReference" zero times, so the
    candidate that would have printed it is refuted. Measuring the artefact
    rather than the intermediate is K138.
    """
    entries = defs.get(name) or []
    if len(entries) < 2 or not paper_text or name in _NEVER_EXPAND:
        return None
    keeps = [bool(re.search(r'#\d', d.body)) for d in entries]
    if len(set(keeps)) < 2:
        return None                       # candidates agree; no question asked
    samples = (_call_arguments(tex, name, entries[0], body_at, spans)
               + _wrapper_samples(name, defs, tex, body_at, spans))
    if not samples:
        return None
    printed = _appears_in_paper(samples, paper_text)
    if printed is None:
        return None
    survivors = [d for d, k in zip(entries, keeps) if k == printed]
    if len(survivors) != 1:
        return None
    survivors[0].evidenced = True
    return survivors[0]


def shipped_sources(flat_tex, root):
    r"""(label, text) for flat.tex and every .sty/.cls in the paper's tarball.

    Only what the paper SHIPS. `flatten_tex` inlines `\input`, never
    `\usepackage`, so a definition found here is the paper's own by
    construction -- TeX Live's copy of a standard package is not in the
    tarball, and the ones that are have been edited by the author often
    enough to be worth reading rather than assuming.
    """
    sources = [('flat.tex', flat_tex)]
    for base, dirs, names in os.walk(root or ''):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for name in sorted(names):
            if not name.endswith(('.sty', '.cls')):
                continue
            try:
                with open(os.path.join(base, name), 'r', encoding='utf-8',
                          errors='replace') as fh:
                    sources.append((name, fh.read()))
            except OSError:
                continue
    return sources


def expand_in_source(tex, sources, paper_text=None):
    r"""Replace calls to the paper's own resolvable macros. Returns (tex, report).

    `report` carries `expanded` ({name: count}) and `refused` ({name: reason}),
    and only ever mentions names that actually OCCUR -- a paper defines
    hundreds of macros and reporting every one it did not use would bury the
    handful that matter.
    """
    defs = read_definitions(sources)
    report = {'expanded': {}, 'refused': {}}
    if not defs:
        return tex, report

    body_at = 0
    m = re.search(r'\\begin\s*\{\s*document\s*\}', tex)
    if m:
        body_at = m.end()

    spans = _protected_spans(tex, defs)

    # Settle the ambiguous names FIRST, once, so a decision is visible to every
    # macro that calls one. `\paul` is `\dtcolornote[Paul]{red}{#1}`; deciding
    # \dtcolornote only while resolving itself would leave its three wrappers
    # -- fourteen of the notes -- still refused.
    decided = {}
    for name, entries in defs.items():
        if len(entries) < 2:
            continue
        chosen = disambiguate(name, defs, tex, paper_text, body_at, spans)
        if chosen is not None:
            decided[name] = chosen
    if decided:
        defs = dict(defs)
        for name, d in decided.items():
            defs[name] = [d]
        report['decided'] = dict((n, d.source) for n, d in decided.items())

    resolved = {}
    for name in sorted(defs, key=len, reverse=True):
        if not re.search(r'\\%s(?![A-Za-z])' % re.escape(name), tex[body_at:]):
            continue                              # never used in the body
        body, why = resolve(name, defs)
        if body is None:
            report['refused'][name] = why
            continue
        resolved[name] = (body, defs[name][0])

    if not resolved:
        return tex, report

    # Longest name first: `\etal` must not be matched inside `\etalii`.
    pattern = re.compile(
        r'\\(%s)(?![A-Za-z])'
        % '|'.join(re.escape(n) for n in
                   sorted(resolved, key=len, reverse=True)))

    out = []
    i = body_at
    prefix = tex[:body_at]
    while True:
        m = pattern.search(tex, i)
        if not m:
            out.append(tex[i:])
            break
        if _in_span(m.start(), spans):
            out.append(tex[i:m.end()])
            i = m.end()
            continue
        name = m.group(1)
        body, d = resolved[name]
        taken = _take_args(tex, m.end(), d.arity, d.optional)
        if taken is None:
            out.append(tex[i:m.end()])            # call does not match arity
            i = m.end()
            continue
        args, end = taken
        text = body
        for n, arg in enumerate(args, 1):
            # The wrapper this macro dropped was adding a stop unless the
            # argument already carried one. That question is answerable here
            # and only here, where the literal argument is in hand.
            if n == 1 and d.arg_suffix and arg.strip() \
                    and not _ALREADY_PUNCTUATED_RE.search(arg):
                arg = arg + d.arg_suffix
            text = text.replace('#%d' % n, arg)
        out.append(tex[i:m.start()])
        out.append(text)
        report['expanded'][name] = report['expanded'].get(name, 0) + 1
        i = end

    return prefix + ''.join(out), report

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

    __slots__ = ('name', 'arity', 'optional', 'body', 'source', 'span')

    def __init__(self, name, arity, optional, body, source, span):
        self.name = name
        self.arity = arity
        self.optional = optional      # first argument is optional (LaTeX [n][d])
        self.body = body
        self.source = source
        self.span = span              # (start, end) in its own source text

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
                               (m.start(), close)))
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


def _unwrap_unresolved(body, defs):
    r"""`\dt@MaybeAddPunct{#1}` -> `#1` when that macro does print its argument.

    An unresolved wrapper is the dangerous case in both directions: keep it and
    pandoc drops the wrapper AND its contents (K110); drop the argument with it
    and the author's text is gone. The tie is broken by evidence -- the
    wrapper's OWN body is read, and the argument is kept only if that body
    references the parameter, i.e. the macro is one that prints what it is
    given.
    """
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
        close = _group_end(body, target.end() - 1)
        if close < 0:
            break
        body = (body[:target.start()] + body[target.end():close - 1]
                + body[close:])
    return body


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
    bodies = set(d.body.strip() for d in entries)
    if len(bodies) > 1:
        return None, ('%d different definitions (%s); the source picks one '
                      'with a conditional this does not evaluate'
                      % (len(bodies),
                         ', '.join(sorted(set(d.source for d in entries)))))
    d = entries[0]
    body = d.body

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

    # Expand the paper's own nested shorthand first.
    for _ in range(MAX_DEPTH):
        hit = None
        for m in re.finditer(r'\\([A-Za-z@]+)(?![A-Za-z])', body):
            inner = m.group(1)
            if inner in _PANDOC_READS or inner in _NO_GLYPH:
                continue
            if inner in defs and defs[inner][0].arity == 0:
                hit = m
                break
        if not hit:
            break
        sub, why = resolve(hit.group(1), defs, seen, depth + 1)
        if sub is None:
            return None, 'via \\%s: %s' % (hit.group(1), why)
        body = body[:hit.start()] + sub + body[hit.end():]

    body = _drop_no_glyph(body)
    body = _apply_font_groups(body)
    body = _unwrap_unresolved(body, defs)
    body = _drop_no_glyph(body)

    if _MACHINERY_RE.search(body):
        return None, 'body still carries TeX machinery pandoc cannot evaluate'

    leftovers = [n for n in re.findall(r'\\([A-Za-z@]+)(?![A-Za-z])', body)
                 if n not in _PANDOC_READS]
    if leftovers:
        return None, ('unresolved command(s): %s'
                      % ', '.join('\\' + x for x in sorted(set(leftovers))))

    for i in range(1, d.arity + 1):
        if '#%d' % i not in body:
            return None, ('argument #%d is discarded; expanding would delete '
                          'the text the author wrote there' % i)

    # A trailing space survives on purpose. `\etal` is `et~al.\ ` because
    # LaTeX eats the space after a control word; strip it and the next word is
    # welded on ("et al.analyze").
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
    r'|split|cases|aligned|alignat|math)\*?\}.*?\\end\{\1\*?\}',
    re.DOTALL)


def _protected_spans(tex, defs):
    """(start, end) ranges no rewrite may touch."""
    spans = []
    for m in _VERBATIM_RE.finditer(tex):
        spans.append((m.start(), m.end()))
    for m in _MATH_SPAN_RE.finditer(tex):
        spans.append((m.start(), m.end()))
    # A definition contains its own name. Rewriting there turns
    # `\newcommand{\etal}{et~al.\ }` into `\newcommand{et al. }{...}`.
    for entries in defs.values():
        for d in entries:
            if d.source == 'flat.tex':
                spans.append(d.span)
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


def expand_in_source(tex, sources):
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
            text = text.replace('#%d' % n, arg)
        out.append(tex[i:m.start()])
        out.append(text)
        report['expanded'][name] = report['expanded'].get(name, 0) + 1
        i = end

    return prefix + ''.join(out), report

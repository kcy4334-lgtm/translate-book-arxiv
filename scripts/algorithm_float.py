# -*- coding: utf-8 -*-
r"""Make `algorithm` floats reach the reader, and notice when a float does not.

A `⟦T####⟧` span holds a float verbatim so the math guard can protect its
backslashes, and the merge puts that LaTeX back into the markdown. From there
the pipeline converts `tabular` itself — that is why raw-LaTeX tables appear
in the book. Anything it does not convert is handed to pandoc as a raw LaTeX
block, and pandoc emits raw TeX only for LaTeX output: on the HTML path it
DROPS it, silently.

So an `algorithm` float was deleted between output.md and book.html in every
book this pipeline has ever built, and every check still passed, because the
checks count tables, images, equations and captions — and the thing that was
gone had never been counted. Two papers shipped without the algorithm listing
that is the point of the paper.

This module does two things:

  * `expand_algorithm_floats` rewrites the float as an ordinary markdown
    ordered list. Markdown, not HTML: raw HTML survives the HTML path and
    vanishes from the DOCX, which is the same trap one layer down. Keeping
    `$...$` intact lets the existing math path render it as MathML.

  * `check_latex_float_fidelity` asks the artifact instead of guessing. It
    does not carry a list of environments believed to be risky — it takes a
    fingerprint of the text inside each raw-LaTeX block and reports the ones
    that left no trace in the built HTML. A future paper using an environment
    nobody here has thought about is caught by the same check.

Pseudocode keywords stay English (`for`, `while`, `return`) the way they do in
Korean, Chinese and Japanese papers; only the structural labels are
translated.
"""
import html as _html_lib
import re

# Structural labels. Pseudocode keywords are deliberately NOT translated.
LABELS = {
    'ko': {'algorithm': '알고리즘', 'require': '입력', 'ensure': '출력'},
    'zh': {'algorithm': '算法', 'require': '输入', 'ensure': '输出'},
    'ja': {'algorithm': 'アルゴリズム', 'require': '入力', 'ensure': '出力'},
    'fr': {'algorithm': 'Algorithme', 'require': 'Entrée', 'ensure': 'Sortie'},
    'de': {'algorithm': 'Algorithmus', 'require': 'Eingabe',
           'ensure': 'Ausgabe'},
    'es': {'algorithm': 'Algoritmo', 'require': 'Entrada', 'ensure': 'Salida'},
}
DEFAULT_LABELS = {'algorithm': 'Algorithm', 'require': 'Input',
                  'ensure': 'Output'}

INDENT = '\u2003'          # EM SPACE: markdown will not read it as indentation

# The opening brace must start a line -- that is what makes pandoc read the
# whole thing as one raw LaTeX block, and therefore what makes it vanish. The
# closing one is matched wherever it falls, because a short float written on
# a single line is still a float.
_FLOAT_RE = re.compile(
    r'^\\begin\{algorithm\*?\}.*?\\end\{algorithm\*?\}',
    re.DOTALL | re.MULTILINE)

# Every control word that begins a pseudocode statement, in both the
# `algorithmic` (UPPERCASE) and `algpseudocode` (CamelCase) spellings. One
# paper in the corpus uses each, so neither spelling is optional.
_KEYWORDS = [
    'REQUIRE', 'Require', 'ENSURE', 'Ensure', 'INPUT', 'Input',
    'OUTPUT', 'Output', 'STATE', 'State', 'ENDFOR', 'EndFor',
    'ENDIF', 'EndIf', 'ENDWHILE', 'EndWhile', 'ENDLOOP', 'EndLoop',
    'ENDFUNCTION', 'EndFunction', 'ENDPROCEDURE', 'EndProcedure',
    'ELSIF', 'ElsIf', 'ELSE', 'Else', 'FOR', 'ForAll', 'For',
    'IF', 'If', 'WHILE', 'While', 'REPEAT', 'Repeat', 'UNTIL', 'Until',
    'LOOP', 'Loop', 'RETURN', 'Return', 'PRINT', 'Print',
    'FUNCTION', 'Function', 'PROCEDURE', 'Procedure',
]
_STATEMENT_RE = re.compile(r'\\(%s)(?![A-Za-z])' % '|'.join(_KEYWORDS))

# How each keyword prints, and what it does to the indentation level.
_OPENS = {'for': 1, 'forall': 1, 'if': 1, 'while': 1, 'repeat': 1,
          'loop': 1, 'function': 1, 'procedure': 1}
_CLOSES = {'endfor': 1, 'endif': 1, 'endwhile': 1, 'endloop': 1,
           'endfunction': 1, 'endprocedure': 1, 'until': 1}
_MIDDLE = {'else', 'elsif'}
_RENDER = {
    'for': '**for** %s **do**', 'forall': '**for all** %s **do**',
    'if': '**if** %s **then**', 'elsif': '**else if** %s **then**',
    'while': '**while** %s **do**', 'until': '**until** %s',
    'else': '**else**', 'endfor': '**end for**', 'endif': '**end if**',
    'endwhile': '**end while**', 'endloop': '**end loop**',
    'endfunction': '**end function**', 'endprocedure': '**end procedure**',
    'repeat': '**repeat**', 'loop': '**loop**',
    'function': '**function** %s', 'procedure': '**procedure** %s',
    'return': '**return** %s', 'print': '**print** %s',
}


def _matching_brace(text, open_at):
    """Index just past the `}` that closes the `{` at `open_at`."""
    depth, i = 0, open_at
    while i < len(text):
        if text[i] == '\\':
            i += 2
            continue
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return len(text)


def _strip_comments(text):
    r"""Drop LaTeX comments, without touching an escaped `\%`."""
    out = []
    for line in text.split('\n'):
        cut = None
        i = 0
        while i < len(line):
            if line[i] == '\\':
                i += 2
                continue
            if line[i] == '%':
                cut = i
                break
            i += 1
        kept = line if cut is None else line[:cut]
        if cut == 0:
            continue                      # a whole-line comment
        out.append(kept)
    return '\n'.join(out)


def extract_caption(tex):
    r"""The body of this float's `\caption{...}`, and its `\label{...}` key."""
    caption = ''
    m = re.search(r'\\caption\*?(?:\[[^\]]*\])?\{', tex)
    if m:
        end = _matching_brace(tex, m.end() - 1)
        caption = tex[m.end():end - 1].strip()
    label = None
    m = re.search(r'\\label\{([^}]*)\}', tex)
    if m:
        label = m.group(1)
    return ' '.join(caption.split()), label


def _clean_argument(text):
    r"""Tidy one statement's text: `\TO` is a word here, not a math arrow."""
    text = re.sub(r'\\(?:TO|To)(?![A-Za-z])', ' **to** ', text)
    text = re.sub(r'\\(?:DO|Do)(?![A-Za-z])', ' ', text)
    text = re.sub(r'\\(?:THEN|Then)(?![A-Za-z])', ' ', text)
    text = text.replace(r'\\', ' ')
    return ' '.join(text.split()).strip()


def _pull_comments(text):
    r"""Split `\Comment{...}` out of a statement; it annotates, it is not one."""
    notes = []
    while True:
        m = re.search(r'\\(?:COMMENT|Comment)\s*\{', text)
        if not m:
            return text, notes
        end = _matching_brace(text, m.end() - 1)
        notes.append(text[m.end():end - 1].strip())
        text = text[:m.start()] + text[end:]


def parse_body(tex):
    """The float's statements as (depth, markdown) pairs, plus its I/O lines.

    Returns (io_lines, steps) where io_lines is a list of (label_key, text).
    """
    body = tex
    m = re.search(r'\\caption\*?(?:\[[^\]]*\])?\{', body)
    if m:
        body = body[_matching_brace(body, m.end() - 1):]
    # `\begin{algorithmic}[1]` — and the `\undefined [1]` the flattener leaves
    # behind when the package was not resolvable.
    body = re.sub(r'\\begin\{algorithmic\*?\}(\s*\[[^\]]*\])?', '', body)
    body = re.sub(r'\\end\{algorithmic\*?\}', '', body)
    body = re.sub(r'\\undefined(\s*\[[^\]]*\])?', '', body)
    body = re.sub(r'\\end\{algorithm\*?\}', '', body)
    body = re.sub(r'\\label\{[^}]*\}', '', body)
    body = _strip_comments(body)

    marks = list(_STATEMENT_RE.finditer(body))
    io_lines, steps, depth = [], [], 0
    for n, mark in enumerate(marks):
        key = mark.group(1).lower()
        rest = body[mark.end():marks[n + 1].start() if n + 1 < len(marks)
                    else len(body)]
        # `\For{...}` and friends take their condition as a braced argument.
        argument = ''
        stripped = rest.lstrip()
        if stripped.startswith('{') and key in (
                'for', 'forall', 'if', 'elsif', 'while', 'until',
                'function', 'procedure'):
            offset = len(rest) - len(stripped)
            end = _matching_brace(rest, offset)
            argument, rest = rest[offset + 1:end - 1], rest[end:]
        rest, notes = _pull_comments(rest)
        argument, more = _pull_comments(argument)
        notes.extend(more)
        text = _clean_argument(argument if argument else rest)
        tail = _clean_argument(rest) if argument else ''

        if key in ('require', 'input'):
            io_lines.append(('require', text))
            continue
        if key in ('ensure', 'output'):
            io_lines.append(('ensure', text))
            continue

        if key in _CLOSES:
            depth = max(0, depth - _CLOSES[key])
        here = depth
        if key in _MIDDLE:
            here = max(0, depth - 1)

        if key == 'state':
            line = text
        elif key in _RENDER:
            template = _RENDER[key]
            line = template % text if '%s' in template else template
            if tail:
                line = '%s %s' % (line, tail)
        else:
            line = text
        if key in _OPENS:
            depth += _OPENS[key]

        if not line and not notes:
            continue                       # e.g. a bare `\State` before `\Return`
        for note in notes:
            line = '%s  *▷ %s*' % (line, note) if line else '*▷ %s*' % note
        steps.append((here, line))
    return io_lines, steps


def algorithm_to_markdown(tex, number, lang='en'):
    """One `algorithm` float as markdown a reader and pandoc both understand."""
    labels = LABELS.get((lang or 'en').split('-')[0].lower(), DEFAULT_LABELS)
    caption, label = extract_caption(tex)
    io_lines, steps = parse_body(tex)
    if not steps and not io_lines:
        return None

    head = '**%s %d.**' % (labels['algorithm'], number)
    if caption:
        head = '%s %s' % (head, caption)
    if label:
        head = '%s {#%s}' % (head, label)
    out = [head, '']
    for key, text in io_lines:
        # Each on its own paragraph. Consecutive lines are one paragraph in
        # markdown, and SINQ's first build printed "... s_max **출력:** ..."
        # running together on one line.
        out.append('**%s:** %s' % (labels[key], text))
        out.append('')
    for i, (depth, line) in enumerate(steps, 1):
        out.append('%d. %s%s' % (i, INDENT * depth, line))
    return '\n'.join(out)


def find_algorithm_floats(md_text):
    """Every raw-LaTeX `algorithm` float in the merged markdown."""
    return list(_FLOAT_RE.finditer(md_text))


def expand_algorithm_floats(md_text, lang='en', start_number=1):
    """Rewrite every `algorithm` float as markdown.

    Returns (new_text, converted, failed). A float that yields no statements
    is left exactly as it was, so the fidelity check below still reports it
    rather than the build quietly dropping it.
    """
    matches = find_algorithm_floats(md_text)
    if not matches:
        return md_text, 0, 0
    pieces, cursor, converted, failed = [], 0, 0, 0
    number = start_number
    for m in matches:
        markdown = algorithm_to_markdown(m.group(0), number, lang)
        if markdown is None:
            failed += 1
            continue
        pieces.append(md_text[cursor:m.start()])
        # A fenced div, so the print sheet has something to draw rules on.
        # Without it the float renders as ordinary paragraphs: the original
        # is a boxed object with a rule above the caption, one under it and
        # one at the foot, and the translation gave the reader nothing to
        # show where the algorithm began or ended.
        pieces.append('\n\n::: algorithm\n%s\n:::\n\n' % markdown.strip())
        cursor = m.end()
        converted += 1
        number += 1
    pieces.append(md_text[cursor:])
    return ''.join(pieces), converted, failed


# --- did every raw-LaTeX block actually reach the page? ---------------------

_BLOCK_RE = re.compile(r'^\\begin\{([A-Za-z]+\*?)\}', re.MULTILINE)
# Environments whose content is math or bibliography: handled elsewhere, and
# their text is not expected to survive as plain words.
_NOT_PROSE = {'equation', 'align', 'aligned', 'gather', 'multline', 'eqnarray',
              'split', 'cases', 'matrix', 'pmatrix', 'bmatrix', 'vmatrix',
              'smallmatrix', 'array', 'thebibliography', 'displaymath'}


def _plain_runs(candidate):
    r"""Runs of text that reach the page unchanged, split at every formula.

    A fingerprint must never SPAN a formula. `Mixtral-8$\times$7B` with the
    math taken out reads `Mixtral-8 7B`, and the page prints `Mixtral-8×7B` —
    the rendered formula sits in the gap, so the phrase matches nothing and a
    float that is perfectly present gets reported as lost.

    Macro NAMES go, their arguments stay: `\textbf{DeepSeek}` is printed.
    Environment delimiters go entirely, argument included, or `algorithmic`
    becomes the fingerprint and the check hunts the page for a word that was
    never meant to be printed.
    """
    text = re.sub(r'\\(?:begin|end)\s*\{[^}]*\}(\s*\[[^\]]*\])?', ' ',
                  candidate or '')
    # `\label{}` prints nothing, so it simply goes.
    text = re.sub(r'\\label\s*\{[^{}]*\}', ' ', text)
    # `\_` `\&` `\%` `\#` are PRINTED characters, not markup, and a bare `&`
    # or `_` is the opposite. Park the escaped ones out of reach of the strip
    # below and put them back after: turning them into spaces made
    # `\texttt{PL\_Alpha\_Hill}` fingerprint as `PL Alpha Hill`, which matches
    # nothing on a page that prints `PL_Alpha_Hill`, and the build aborted
    # over a table that was there all along.
    kept = {'_': '\ue000', '&': '\ue001', '%': '\ue002', '#': '\ue003'}
    for ch, hold in kept.items():
        text = text.replace('\\' + ch, hold)
    runs = []
    # Split at anything the PAGE fills in where the source has markup: a
    # formula, and a citation or cross-reference. `\cite{sglang}` prints as
    # "(Zheng et al. 2024)", so a fingerprint that spanned it joined two
    # words the page keeps apart and aborted a build over a table that was
    # there. Same lesson as `Mixtral-8$\times$7B`: never span a substitution.
    for piece in re.split(r'\$[^$]*\$|\\\(.*?\\\)'
                          r'|\\cite[a-zA-Z]*\s*(?:\[[^\]]*\])*\s*\{[^{}]*\}'
                          r'|\\(?:ref|autoref|eqref)\s*\{[^{}]*\}', text):
        piece = re.sub(r'\\[A-Za-z]+\*?', ' ', piece)
        # Quote marks go too: a caption writes them as ``...'' and the page
        # renders “...”, so a fingerprint carrying one can never match the
        # text it came from.
        piece = re.sub(r'[{}\[\]&\\~^_%`\'"]', ' ', piece)
        for ch, hold in kept.items():
            piece = piece.replace(hold, ch)
        # Every word is kept, one-character words included. Dropping them
        # breaks adjacency: `3비트 및 4비트` fingerprinted as `3비트 4비트`
        # matches nothing on a page that says what the source said.
        words = piece.split()
        if words:
            runs.append(words)
    return runs


# `\begin{tabular}{l|c}`, `\begin{tabular}[t]{@{}c@{}}`, `\begin{tabularx}
# {\textwidth}{lcc}` — the environment and the argument groups that follow it.
# One level of nesting is allowed because `@{}` lives inside the spec.
_LENGTH_RE = re.compile(
    r'^-?\d*\.?\d+(?:pt|em|ex|cm|mm|in|bp|sp|dd|pc|mu)$', re.IGNORECASE)
_TABULAR_SPEC_RE = re.compile(
    r'\\begin\{(?:tabular|tabularx|longtable|array)\*?\}'
    r'(?:\s*\[[^\]]*\])?'
    r'(?:\s*\{(?:[^{}]|\{[^{}]*\})*\})*')


def _fingerprint(tex):
    r"""The longest run of plain text in the block, capped at 8 words.

    Prefers the caption — that is the part a reader would miss first — and
    prefers a LONG phrase. A three-word phrase from a caption can occur again
    in the body by coincidence, and a fingerprint that matches something else
    on the page reports a float as present when it is gone.
    """
    # Strip the float BEFORE reading it, not each piece afterwards. The `%`
    # that comments out a whole caption sits in front of `\caption`, outside
    # the braces, so a body extracted from the raw text carries no comment
    # marker of its own and survives `_strip_comments` intact. DeeR-VLA's
    # first table keeps an older caption commented out above the live one;
    # `extract_caption` took the dead one, the fingerprint became English
    # prose that no reader sees, and the build aborted over a table that was
    # rendered and present.
    #
    # The earlier form of this comment records the same lesson one step in:
    # a `%`-commented sentence INSIDE a caption gave a fingerprint that ran
    # from `D.` across the marker into text nobody prints.
    #
    # A column specification reads as a word and can never be on the page.
    # ResNet's three appendix tables sit in a bare `center` with no caption,
    # so the fingerprint was drawn from the body and began `l|c`, `c|c|c`,
    # `l|c|c|c|cccc…`. No page will ever contain that, so the check reported
    # three tables as lost while all three were rendered and present — and it
    # aborted the build, which is how a false alarm costs a whole book.
    live = _strip_comments(tex)
    caption, _label = extract_caption(live)
    body = _TABULAR_SPEC_RE.sub(' ', live)
    for candidate in (caption or '', body):
        for words in sorted(_plain_runs(candidate), key=len, reverse=True):
            # A length is an argument, never prose. `\specialrule{1pt}{-1pt}`
            # opened one fingerprint with `6pt 1pt`, which is not on any page.
            words = [w for w in words if not _LENGTH_RE.match(w)]
            phrase = ' '.join(words[:8])
            if len(phrase) >= 12:
                return phrase
    return None


def _visible_text(html_text):
    r"""The HTML with tags gone, entities decoded, whitespace flattened.

    Decoding matters: a caption's `\&` prints as `&` and reaches the HTML as
    `&amp;`, so comparing the two without unescaping reports a caption that
    is sitting right there on the page.
    """
    # A stylesheet is not text a reader sees, and searching it is worse than
    # useless in both directions: ResNet's `\specialrule{1pt}{-1pt}{0pt}` gave
    # the fingerprint `6pt 1pt …`, whose first word matched `padding-top: 6pt`
    # in the CSS — and a phrase that matches the stylesheet by accident would
    # report a float as PRESENT when it is gone, which is the failure this
    # check exists to prevent.
    text = re.sub(r'(?is)<(style|script)\b.*?</\1>', ' ', html_text)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = _html_lib.unescape(text)
    # The same quote marks the fingerprint drops. A caption writes ``xattn''
    # and the page renders it with curly quotes, so stripping them on one
    # side only moved the mismatch instead of fixing it: the check went on
    # reporting a caption printed in plain sight.
    text = re.sub(r'[`\'"‘’“”]', ' ', text)
    text = text.replace('&nbsp;', ' ').replace(' ', ' ')
    return ' '.join(text.split())


def check_latex_float_fidelity(md_text, html_text):
    r"""Report raw-LaTeX blocks that left no trace in the built HTML.

    This is deliberately not a list of environments believed to be risky. It
    asks the artifact: for each block, is any of its prose on the page? The
    `algorithm` hole existed for as long as this pipeline has, and no list
    anybody wrote in advance contained it.

    The comparison ignores tags and whitespace. A phrase that pandoc wrapped
    across two lines, or split with a `<em>`, is still on the page, and a
    check that called that a loss would be trained away within a week.
    """
    visible = _visible_text(html_text)
    missing = []
    covered = 0                # a nested env is part of the float around it
    for m in _BLOCK_RE.finditer(md_text):
        if m.start() < covered:
            continue
        env = m.group(1)
        end = md_text.find('\\end{%s}' % env, m.end())
        end = end + len(env) + 6 if end >= 0 else len(md_text)
        covered = end
        if env.rstrip('*') in _NOT_PROSE:
            continue
        phrase = _fingerprint(md_text[m.start():end])
        if not phrase:
            continue
        # Whitespace is not the only thing that can differ. `_plain_runs`
        # drops brackets while the page keeps them, so a header written
        # `mAP@[.5, .95]` gives the phrase `mAP@ .5, .95` and a whitespace-only
        # join can never bridge the gap. Tolerate the punctuation one side
        # drops and the other does not.
        loose = r'[\s\[\](){}]*'.join(re.escape(w) for w in phrase.split())
        if not re.search(loose, visible):
            missing.append((env, phrase))
    return missing

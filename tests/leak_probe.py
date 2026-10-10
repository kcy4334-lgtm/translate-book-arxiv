# -*- coding: utf-8 -*-
r"""Markup that reached the reader — found by shape, not by name.

The scan this replaces was a list of things that had already gone wrong:
`{=latex}`, `{-2em}`, `:::`, `(tab:x)`, `[@key]`, `??`. Every entry earned
its place by printing in a book first, which means the list can only ever
be one build behind. `<!-- -->` printed twenty-one times in AlphaQ while a
scan looking for seven other shapes called the book clean, and a reader
found it.

So this asks the opposite question. Prose in these books is Hangul, Latin
letters, digits and ordinary punctuation. The characters markup is built
from -- `{ } < > \ $ & | ^ ~` -- do not belong in a sentence. Any token
carrying one is a candidate, and the exceptions are named here rather than
the offences: URLs, code spans, and the handful of symbols that legitimately
print.

    python tests/leak_probe.py <temp_dir> [--strict] [--all]

Reads `book_doc.html`, which is what the PDF is printed from, so it needs
nothing but the standard library.
"""
import argparse
import html as html_lib
import io
import os
import re
import sys
from collections import Counter


# A CLI prints, and what it prints may carry the book's text. A Windows
# console under a non-UTF-8 locale then raises UnicodeEncodeError and the
# command dies -- which stayed hidden while every caller happened to set
# PYTHONIOENCODING for it.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError, OSError):
        pass

# Regions whose contents are meant to look like markup.
CODE_RE = re.compile(r'(?s)<(code|pre|style|script|annotation)\b.*?</\1>')
TAG_RE = re.compile(r'<[^>]+>')

# The characters a sentence in these books never needs.
SYNTAX = set('{}<>\\$&|^~`')

# Markup built only from ordinary punctuation carries no syntax character,
# so the test above cannot see it. These are searched anywhere in the text
# rather than matched against a whole token: on a real page the markup has
# Korean attached to it -- `(table-mixtral)에서`, `{=latex}여기서` -- and
# anything anchored to a token boundary misses every one of them.
SHAPES = (
    ('cross-reference label', re.compile(
        r'\((?:tab|fig|eq|sec|alg|app|thm|lem|def|prop|table|figure)'
        r'[:.\-][A-Za-z0-9_:.\-]+\)')),
    # What pandoc prints for a `\cref` it could not resolve: PaLM's table
    # captions said "corresponding to [fig:contd_training_results]".
    ('cross-reference key', re.compile(
        r'\[(?:tab|fig|eq|sec|alg|app|thm|lem|def|prop|table|figure)'
        r'[:.\-][A-Za-z0-9_:.\-]+\]')),
    ('citation key', re.compile(r'\[@[A-Za-z0-9_:.\-]+\]')),
    ('fence', re.compile(r'(?<![:\w]):{3,}(?![:\w])')),
    ('unresolved reference', re.compile(r'\?\?')),
)

# Named exceptions. Each one is a thing a reader is supposed to see.
URL_RE = re.compile(r'^(?:https?://|www\.|doi:|arXiv:)', re.IGNORECASE)
# A syntax character STANDING ALONE is rendered content, not markup: the
# norm bars of `| w - ŵ |`, the braces of a set `{ 0.1, 0.5 }`, the `<` of
# `< 3 %`, the `&` of `Williams & Aletras`, the `\` of a `Method \ Weights`
# header. Markup arrives attached to something -- `{=latex}`, `<!--`,
# `\times`, `{-2em}`, `:::` -- which is what makes the length test the line
# between the two.

# The other exception the paper itself declares. `R\&D`, `pick\&place`, `50\%`:
# the backslash is the author saying "this character is a word here, not
# syntax". Re-spell the rendered token that way and look for it in flat.tex.
# A column separator that escaped from a table never matches, because a
# separator is written BARE -- which is the whole difference between the two,
# and the source is the only place it is still visible.
#
# `{` and `}` too: a set written `\{16, 32\}` prints its braces, and ViT's
# "ViT-B/{16,32}" and VAE's "{0.01, 0.02, 0.1}" are the papers' own notation.
ESCAPABLE = '&%#_${}'
# The letters MathML prints a formula in (𝒛, 𝜽, 𝝓). A `|` beside them is the
# formula's own bar: VAE's KL divergence `D_KL(q || p)` in a heading.
MATH_LETTERS_RE = re.compile('[\U0001D400-\U0001D7FF]')


def source_tex(temp_dir):
    """The paper's own LaTeX, or '' when this build has none."""
    path = os.path.join(temp_dir, 'flat.tex')
    if not os.path.isfile(path):
        return ''
    return io.open(path, encoding='utf-8', errors='replace').read()


def written_as_literal(token, source):
    """Does the source spell this token with LaTeX escapes?"""
    if not source:
        return False
    # A backslash the paper prints, written `{\textbackslash}`: gpt3 quotes a
    # scraped "(\displaystyle N=mg)" in a dataset example, and the PDF shows it.
    if '\\' in token and set(token) & SYNTAX <= {'\\'}:
        spelled = r'(?:\{\\textbackslash\}|\\textbackslash\s*(?:\{\})?)'.join(
            re.escape(part) for part in token.split('\\'))
        if re.search(spelled, source):
            return True
    # A tilde the paper prints, written `\~{}`: planck's reference to
    # "Reionization with z˜6 Quasars".
    if '~' in token and set(token) & SYNTAX <= {'~'}:
        spelled = r'\\~\s*(?:\{\})?'.join(re.escape(p) for p in token.split('~'))
        if re.search(spelled, source):
            return True
    if not any(c in ESCAPABLE for c in token):
        return False
    # Any OTHER syntax character means this is not simply an escaped word.
    if any(c in SYNTAX and c not in ESCAPABLE for c in token):
        return False
    spelled = ''.join('\\' + c if c in ESCAPABLE else c for c in token)
    return spelled in source


def visible(html):
    """What a reader sees: no tags, no code, entities resolved."""
    body = CODE_RE.sub(' ', html)
    body = TAG_RE.sub(' ', body)
    return html_lib.unescape(body)


def candidates(text, source=''):
    """Everything on the page that looks like markup. token -> count."""
    found = Counter()
    for raw in text.split():
        token = raw.strip('.,;:!?()[]"“”‘’')
        if not token or len(token) < 2 or URL_RE.match(token):
            continue
        if set(token) & SYNTAX and not written_as_literal(token, source):
            if set(token) & SYNTAX <= {'|'} and MATH_LETTERS_RE.search(token):
                continue
            # "~65 hours" is "about 65": Sentence-BERT's `\texttildelow`.
            # A tie that leaked sits after a word, not before a number.
            if re.match(r'~[\d.]+[%A-Za-z가-힣]*$', token):
                continue
            # "<0.1%" is "under 0.1%": PaLM's language shares. A tag that
            # leaked opens with a letter, `!` or `/`, never a digit.
            if re.match(r'[<>]=?[\d.]+%?$', token):
                continue
            found[token] += 1
    for _label, pattern in SHAPES:
        for m in pattern.finditer(text):
            found[m.group(0)] += 1
    return found


# Code is excluded above because a listing may quote LaTeX. A code span that
# OPENS with a colour or size command is not a quotation, though: it is a
# style pandoc could not apply, printed. gpt3's prompts showed `\color{gray}`
# sixteen times in monospace and this probe, reading around code, passed.
_CODE_SPAN_RE = re.compile(r'<code>(.*?)</code>', re.S)
_STYLE_HEAD_RE = re.compile(
    r'^\s*(\\(?:color|textcolor|footnotesize|small|scriptsize|tiny|normalsize'
    r'|large|Large|LARGE|huge|Huge|bfseries|itshape|ttfamily)(?![A-Za-z])'
    r'(?:\{[^{}]*\})?)')


def styled_code(html):
    """Style commands printed at the head of a code span. token -> count."""
    found = Counter()
    for m in _CODE_SPAN_RE.finditer(html):
        head = _STYLE_HEAD_RE.match(html_lib.unescape(m.group(1)))
        if head:
            found[head.group(1)] += 1
    return found


def probe(temp_dir, strict=False, show_all=False):
    path = os.path.join(temp_dir, 'book_doc.html')
    if not os.path.isfile(path):
        print('ERROR: no book_doc.html in %s — build first' % temp_dir)
        return 1
    html = io.open(path, encoding='utf-8', errors='replace').read()
    found = candidates(visible(html), source_tex(temp_dir))
    found.update(styled_code(html))

    total = sum(found.values())
    print('tokens carrying markup syntax: %d (%d distinct)'
          % (total, len(found)))
    if not found:
        print('PASS: nothing on the page looks like markup')
        return 0
    shown = found.most_common() if show_all else found.most_common(12)
    for token, n in shown:
        print('   x%-4d %r' % (n, token[:70]))
    if len(found) > len(shown):
        print('   … %d more distinct token(s); pass --all to see them'
              % (len(found) - len(shown)))
    print()
    print('Each of these is either markup that leaked or an exception this '
          'probe has not been told about. Decide which, then fix the book or '
          'name the exception here — do not leave it unexplained.')
    return 1 if strict else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('temp_dir')
    ap.add_argument('--strict', action='store_true')
    ap.add_argument('--all', action='store_true')
    args = ap.parse_args()
    raise SystemExit(probe(args.temp_dir, args.strict, args.all))


if __name__ == '__main__':
    main()

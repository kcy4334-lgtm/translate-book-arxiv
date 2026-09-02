# -*- coding: utf-8 -*-
r"""What the source contains, against what reached the page.

Every other check here compares two things this pipeline produced: our
snapshot against our output, the spans in our markdown against the `<math>`
in our HTML. Those find disagreements between stages. They are blind, by
construction, to anything that is missing from EVERY stage -- and that is
the shape most of the real defects have had.

CafeQ shipped with 61 references in `output.md` and none in the book. No
count disagreed with any other count, because nothing counted references at
all. The same held for the authors: known the whole time, laid out nowhere.

So this probe starts from `flat.tex` and asks, for each kind of thing the
paper contains, whether any of it reached the built page. It does not need
anyone to have thought of "reference list" as a check -- only that the
source says there is one.

    python tests/inventory_probe.py <temp_dir> [--lang ko] [--strict]

Reads `book_doc.html`, which is what the PDF is printed from, so it needs
nothing but the standard library.
"""
import argparse
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'scripts'))

COMMENT_RE = re.compile(r'(?<!\\)%[^\n]*')
TAG_RE = re.compile(r'<[^>]+>')
ANNOTATION_RE = re.compile(r'(?s)<annotation\b.*?</annotation>')
NON_PAGE_RE = re.compile(r'(?s)<(style|script)\b.*?</\1>')


def read(path):
    if not os.path.isfile(path):
        return ''
    return io.open(path, encoding='utf-8', errors='replace').read()


def visible(html):
    """The text a reader sees: no tags, no stylesheet, no TeX annotations."""
    body = NON_PAGE_RE.sub(' ', html)
    body = ANNOTATION_RE.sub(' ', body)
    return ' '.join(TAG_RE.sub(' ', body).split())


# --- what the source says it has -------------------------------------------

def source_inventory(flat):
    r"""{kind: count} for the things a paper is made of."""
    tex = COMMENT_RE.sub('', flat)
    cite_keys = set()
    for m in re.finditer(r'\\cite[a-zA-Z]*\s*(?:\[[^\]]*\])*\s*\{([^{}]*)\}',
                         tex):
        cite_keys.update(k.strip() for k in m.group(1).split(',') if k.strip())
    return {
        'bibliography entries': len(re.findall(r'\\bibitem\b', tex)),
        'works cited': len(cite_keys),
        'authors named': 1 if names_authors(tex) else 0,
        'figures': len(re.findall(r'\\begin\{figure\*?\}', tex)),
        'tables': len(re.findall(r'\\begin\{table\*?\}', tex)),
        'algorithms': len(re.findall(r'\\begin\{algorithm\*?\}', tex)),
        'numbered equations': len(re.findall(
            r'\\begin\{(?:equation|align|gather|multline|eqnarray)\}', tex)),
        'footnotes': _count_footnotes(tex),
    }


def _count_footnotes(tex):
    r"""Real footnotes, not the `\footnote{#1}` inside a macro definition.

    A body carrying `#` is a parameter, so the command is being DEFINED
    here, not used. Counting those two definitions in CafeQ said the book
    had lost two footnotes it never had.
    """
    total = 0
    for m in re.finditer(r'\\footnote\s*\{', tex):
        depth, i = 0, m.end() - 1
        while i < len(tex):
            if tex[i] == '{':
                depth += 1
            elif tex[i] == '}':
                depth -= 1
                if depth == 0:
                    break
            i += 1
        if '#' not in tex[m.end():i]:
            total += 1
    return total


_AUTHOR_CMD_RE = re.compile(
    r'\\(?:author|icmlauthor|Author|name)\s*(?:\[[^\]]*\])?\s*\{')


def names_authors(tex):
    r"""Does the source name its authors at all?

    Deliberately a yes/no. Papers write the byline every way there is --
    `\author{A, B \\ C}`, a run of `\icmlauthor{}{}`, names wrapped in
    `{\bf ...}\textsuperscript{1,2}` beside their affiliations -- and a
    parser that tries to recover the NAMES gets one of the three wrong and
    reports a defect that is its own. Whether a byline should exist is not
    in doubt, and that is the whole question here.
    """
    return bool(_AUTHOR_CMD_RE.search(tex))


# --- what the page actually shows ------------------------------------------

def page_inventory(html, lang):
    refs_word = {'ko': '참고문헌', 'zh': '参考文献', 'ja': '参考文献'}.get(
        lang, 'References')
    refs = re.search(r'(?s)<h[1-6][^>]*>\s*%s\s*</h[1-6]>(.*)'
                     % re.escape(refs_word), html)
    return {
        'bibliography entries': (len(re.findall(r'<p\b', refs.group(1)))
                                 if refs else 0),
        'figures': len(re.findall(r'<figure\b', html)),
        'tables': len(re.findall(r'<table\b', NON_PAGE_RE.sub(' ', html))),
        'algorithms': len(re.findall(r'class="algorithm"', html)),
        'numbered equations': len(re.findall(r'display="block"', html)),
        'footnotes': len(re.findall(r'id="fn\d|class="footnote', html)),
    }


def probe(temp_dir, lang='ko', strict=False):
    flat = read(os.path.join(temp_dir, 'flat.tex'))
    html = read(os.path.join(temp_dir, 'book_doc.html'))
    if not flat:
        print('inventory: no flat.tex in %s — skipped (calibre backend)'
              % temp_dir)
        return 0
    if not html:
        print('ERROR: no book_doc.html in %s — build first' % temp_dir)
        return 1

    want = source_inventory(flat)
    got = page_inventory(html, lang)

    # Absence only. A count in LaTeX and a count in HTML do not line up: a
    # three-panel float is one `figure` environment and three `<figure>`
    # elements, an `align` block is one environment and four numbered lines,
    # an inlined `.bbl` is dropped whole when citeproc rendered the list as
    # well. Reading those differences as shortfalls is how a check earns its
    # reputation for crying wolf. What does not vary is zero.
    findings = []
    # Say it on the page, not only in the comment above. Printed side by side
    # the two columns invite the reader to subtract them, and the difference
    # means nothing; I read one as a shortfall myself before this line existed.
    print('the two columns count different units — only a page count of 0 '
          'against a non-zero source is a finding')
    print()
    print('%-22s %8s %8s' % ('', 'source', 'page'))
    for kind in ('bibliography entries', 'figures', 'tables', 'algorithms',
                 'numbered equations', 'footnotes'):
        n, m = want.get(kind, 0), got.get(kind, 0)
        gone = bool(n) and not m
        print('%-22s %8d %8d%s'
              % (kind, n, m, '  <-- none of it reached the page' if gone
                 else ''))
        if gone:
            findings.append('%s: %d in the source, none on the page'
                            % (kind, n))

    # A paper that cites has a list to cite into. One invariant, and it holds
    # whether citeproc rendered the list or the source inlined its own .bbl.
    if want['works cited'] and not got['bibliography entries']:
        findings.append('%d work(s) cited and no reference list on the page'
                        % want['works cited'])

    named = names_authors(COMMENT_RE.sub('', flat))
    byline = bool(re.search(r'class="byline"', html))
    print('%-22s %8s %8s%s'
          % ('authors', 'named' if named else '-', 'byline' if byline else
             'none', '  <-- the book names no one'
             if named and not byline else ''))
    if named and not byline:
        findings.append('the source names its authors and the page has no '
                        'byline')

    print()
    if not findings:
        print('PASS: nothing the source has is missing from the page')
        return 0
    print('%d finding(s) against the source inventory:' % len(findings))
    for line in findings:
        print('   %s' % line)
    return 1 if strict else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('temp_dir')
    ap.add_argument('--lang', default='ko')
    ap.add_argument('--strict', action='store_true')
    args = ap.parse_args()
    raise SystemExit(probe(args.temp_dir, args.lang, args.strict))


if __name__ == '__main__':
    main()

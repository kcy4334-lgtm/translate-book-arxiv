# -*- coding: utf-8 -*-
r"""What shape was each paper? An append-only census, written by the build.

`old-man` advises against mistaking a pattern for a definition, and its advice
is only as good as the shapes it knows. Left to a model's recollection that is
guesswork; kept here it is evidence, and it grows by one row every time a paper
goes through the pipeline.

Two kinds of answer come out of it, and the second is the one that is hard to
get any other way:

  * "3 of 5 papers write their floats as `wrapfigure`" — frequency, so an
    advisor can rank what to check first.
  * "no paper in this corpus has yet used `\subcaption`" — ABSENCE, which is
    exactly the warning worth giving: a pattern that has never met a shape has
    never been tested against it, and the code was written by someone who had
    not seen one either.

Recorded automatically at the end of a successful build (see
`merge_and_build.py`), so it cannot be forgotten. Stdlib only.

    python scripts/corpus_census.py record <temp_dir>
    python scripts/corpus_census.py digest [--json]
"""
import argparse
import io
import json
import os
import re
import sys

if sys.platform == 'win32':
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding='utf-8')
        except AttributeError:
            pass

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE = os.path.join(SKILL_DIR, 'corpus', 'shapes.json')

# What to count. Every entry here decides a code path somewhere in this
# pipeline: if a paper has it, some normaliser, scanner or renderer behaves
# differently. Counting anything else would grow the file without informing
# a single decision.
#
# Keyed by group so a reader can ask "how does this corpus spell captions?"
# and get every spelling at once.
MARKERS = {
    'float': (
        (r'\\begin\{figure\}', 'figure'),
        (r'\\begin\{figure\*\}', 'figure*'),
        (r'\\begin\{table\}', 'table'),
        (r'\\begin\{table\*\}', 'table*'),
        (r'\\begin\{wrapfigure\}', 'wrapfigure'),
        (r'\\begin\{SCfigure\}', 'SCfigure'),
        (r'\\begin\{sidewaysfigure\}', 'sidewaysfigure'),
        (r'\\begin\{floatingtable\}', 'floatingtable'),
        (r'\\begin\{minipage\}', 'minipage'),
        (r'\\begin\{subfigure\}', 'subfigure'),
        (r'\\subfloat\b', 'subfloat'),
    ),
    'caption': (
        (r'\\caption\s*[\[{]', 'caption'),
        (r'\\captionof\b', 'captionof'),
        (r'\\subcaption\b', 'subcaption'),
        (r'\\captionsetup\b', 'captionsetup'),
    ),
    'table': (
        (r'\\begin\{tabular\}', 'tabular'),
        (r'\\begin\{tabularx\}', 'tabularx'),
        (r'\\begin\{longtable\}', 'longtable'),
        (r'\\multirow\b', 'multirow'),
        (r'\\multicolumn\b', 'multicolumn'),
        (r'\\rotatebox\b', 'rotatebox'),
        (r'\\resizebox\b', 'resizebox'),
        (r'\\scalebox\b', 'scalebox'),
        (r'\\cmidrule\b', 'cmidrule'),
        (r'\\addlinespace\b', 'addlinespace'),
        (r'\\makecell\b', 'makecell'),
        (r'\\thead\b', 'thead'),
        (r'\\tnote\b', 'tnote'),
        (r'\*\s*\{\s*\d+\s*\}\s*\{', 'repeat-column-spec'),
    ),
    'bibliography': (
        (r'\\bibitem\b', 'bibitem'),
        (r'\\begin\{thebibliography\}', 'thebibliography-inlined'),
        (r'\\bibliography\b', 'bibliography-file'),
        (r'\\citep\b', 'citep'),
        (r'\\citet\b', 'citet'),
        (r'\\cite\b', 'cite'),
    ),
    'math': (
        (r'\\begin\{equation\}', 'equation'),
        (r'\\begin\{align\}', 'align'),
        (r'\\begin\{gather\}', 'gather'),
        (r'\\begin\{eqnarray\}', 'eqnarray'),
        (r'\\sideset\b', 'sideset'),
        (r'\\substack\b', 'substack'),
        (r'\\nolimits\b', 'nolimits'),
        (r'\\setlength\b', 'setlength'),
        (r'\{\s*\\(?:rm|bf|it|sf|tt|sc)\s', 'old-font-switch'),
        # The delimiters that decide `paper_macros._MATH_SPAN_RE`, which marks
        # the regions no macro rewrite may touch. A miss here is the one
        # failure in that module that lands INSIDE a formula, so the corpus
        # has to be able to say whether it has ever met each spelling.
        (r'\\begin\{multline\}', 'multline'),
        (r'\\begin\{alignat\}', 'alignat'),
        (r'\\begin\{flalign\}', 'flalign'),
        (r'\\begin\{IEEEeqnarray\}', 'IEEEeqnarray'),
        (r'\\begin\{dmath\}', 'dmath-breqn'),
        (r'\\begin\{empheq\}', 'empheq'),
        (r'\\begin\{subequations\}', 'subequations'),
        (r'(?<!\\)\\\[', 'display-bracket'),
        (r'(?<!\\)\\\(', 'inline-paren'),
        # The two shapes that hid a formula from the span regex, each found by
        # an advisor rather than by this census, and each invisible to it at
        # the time. `\ifmmode ...$\else ...$\fi` carries an ODD number of `$`
        # per branch — correct TeX, since only one branch runs — and pairing
        # them lexically destroyed `$`-parity for the rest of the file.
        (r'\\ifmmode[^\n]*\$', 'ifmmode-dollar'),
        # `\newcommand{\be}{\begin{equation}}`: the display is opened by a
        # NAME, so a pattern looking for `\begin` finds nothing at all.
        (r'\\(?:new|renew|provide)command\s*\*?\s*\{?\s*\\[A-Za-z@]+\s*\}?'
         r'\s*\{\s*\\begin\s*\{\s*(?:equation|align|eqnarray|gather|multline'
         r'|subequations|displaymath|alignat|flalign)',
         'math-env-alias'),
    ),
    # How a paper defines its OWN shorthand, and how it uses it. Added because
    # the census could not see any of this while `\ie` was printing in the
    # middle of a sentence in a finished book (K135): asked how often the
    # corpus had met a definition spelling, the only way to answer was to read
    # 3.7 MB of flat.tex and 1 MB of .sty by hand.
    #
    # Two of these decide something destructive rather than merely missed.
    # `tab-stop` and `tabbing-kill` are how Shor writes indentation — a macro
    # bound to one of them looks exactly like an abbreviation, and expanding it
    # deletes the layout of three algorithm listings. `newif` is the
    # conditional-definition path, where the same name is defined twice and
    # the default is the wrong one.
    'macro': (
        (r'\\newcommand\s*\{', 'newcommand-braced'),
        (r'\\newcommand\s*\\', 'newcommand-bare'),
        (r'\\newcommand\s*\*', 'newcommand-starred'),
        (r'\\renewcommand\b', 'renewcommand'),
        (r'\\providecommand\b', 'providecommand'),
        (r'\\DeclareRobustCommand\b', 'DeclareRobustCommand'),
        (r'\\(?:new|renew|provide)command\s*\{?\s*\\[A-Za-z@]+\s*\}?'
         r'\s*\[\s*\d\s*\]\s*\[', 'optional-argument'),
        (r'\\let\s*\\[A-Za-z@]+', 'let-binding'),
        (r'\\newif\s*\\if[A-Za-z@]+', 'newif'),
        (r'\\futurelet\b', 'futurelet'),
        (r'\\onedot\b', 'onedot'),
        (r'\\xspace\b', 'xspace'),
        (r'\\ensuremath\b', 'ensuremath'),
        (r'\\(?:ie|eg|etal|etc|cf|wrt|dof|vs)(?![A-Za-z])', 'abbreviation-macro'),
        (r'\\parhead\b', 'run-in-heading-macro'),
        (r'\\newcite\b', 'newcite'),
        (r'\\begin\{tabbing\}', 'tabbing'),
        (r'\\kill(?![A-Za-z])', 'tabbing-kill'),
        (r'\\[>=+](?![A-Za-z])', 'tab-stop'),
        (r'\\cellcolor\b', 'cellcolor'),
        (r'\\rowcolor\b', 'rowcolor'),
        (r'\{\s*\\bfseries(?![A-Za-z])', 'bfseries-group'),
        # A name bound to horizontal space. It looks exactly like an
        # abbreviation and resolving it to nothing deletes indentation —
        # `_TABBING_BODY_RE` knew only the tabbing primitives, so a body
        # spelled `\hspace{1em}` walked past it. CafeQ ships one.
        (r'\\(?:new|renew|provide)command\s*\*?\s*\{?\s*\\[A-Za-z@]+\s*\}?'
         r'\s*\{\s*\\(?:hspace\*?|hskip|kern|quad|qquad)(?![A-Za-z])',
         'glue-only-macro'),
        # xparse. Its argument specification is `{ s O{} m }`, not `[n][d]`,
        # so `read_definitions` cannot read the signature at all.
        (r'\\(?:New|Declare|Renew|Provide)DocumentCommand', 'xparse-command'),
    ),
    # How the document declares itself. Added because the census could not see
    # this at all: when the backend rejected Shor 1995 for having "no
    # top-level .tex", there was no marker able to say how rare a
    # `\documentstyle` preamble is — so a NEVER SEEN answer would have been
    # blindness reported as evidence. `\documentstyle` is the LaTeX 2.09
    # spelling that `\documentclass` replaced in 1994.
    'preamble': (
        (r'\\documentclass\b', 'documentclass'),
        (r'\\documentstyle\b', 'documentstyle'),
    ),
    'front matter': (
        (r'\\thanks\b', 'thanks'),
        (r'\\footnote\s*[\[{]', 'footnote'),
        (r'\\footnotemark\b', 'footnotemark'),
        (r'\\twocolumn\s*\[', 'twocolumn-title'),
        (r'\\IEEEPARstart\b', 'IEEEPARstart'),
        (r'\\markboth\b', 'markboth'),
        (r'\\author\b', 'author'),
        # The affiliation family. Added because the census was blind to the
        # whole of it while Maynard's five-line `\address` was being dropped
        # with its own command and no count anywhere disagreed (K123). These
        # decide `unwrap_front_matter`, which keeps the prose in the first
        # three and deletes the last two outright.
        (r'\\address\s*[\[{]', 'address'),
        (r'\\institute\b', 'institute'),
        (r'\\email\s*[\[{]', 'email'),
        (r'\\maketitle\b', 'maketitle'),
        (r'\\bibliographystyle\b', 'bibliographystyle'),
        (r'\\(?:title|author)running\b', 'running-head'),
        # Class-specific spellings of the same thing, none of which this
        # corpus has met. Listed so the answer is NEVER SEEN rather than
        # silence: revtex, elsarticle, IEEEtran and ICML each name the
        # affiliation differently, and two of them put a bracketed label
        # between the command and its brace.
        (r'\\(?:affiliation|altaffiliation|ead|IEEEauthorblock[AN])\b',
         'class-affiliation'),
        (r'\\icml(?:author|affiliation|correspondingauthor)\b',
         'icml-frontmatter'),
    ),
    'other': (
        (r'\\begin\{algorithm\}', 'algorithm'),
        (r'\\begin\{algorithmic\}', 'algorithmic'),
        (r'\\begin\{tikzpicture\}', 'tikzpicture'),
        (r'\\begin\{lstlisting\}', 'lstlisting'),
        (r'\\newcommand\b', 'newcommand'),
        (r'\\def\b', 'def'),
        (r'\\input\b', 'input'),
    ),
}

# Counted on the comment-stripped text EXCEPT these, which are about the
# comments themselves. A commented-out caption cost a whole book its table
# numbering (K102), so "does this paper disable things in place?" is a shape
# worth knowing.
COMMENTED = (
    (r'(?m)^[ \t]*%.*\\caption', 'commented-caption'),
    (r'(?m)^[ \t]*%.*\\begin\{(?:figure|table)', 'commented-float'),
)


def _compile(pattern):
    r"""`\b` is the wrong boundary after a TeX control word.

    A control word ends at the first non-letter, and `_` is a word character
    to `re`: `\\nolimits\b` does not match `\nolimits_{X}`, which is how the
    command is nearly always written. The census reported `nolimits` as never
    seen while a paper in the corpus used it — and a census that under-reports
    manufactures exactly the false "never seen" warning it exists to give.

    Only a `\b` that follows a LETTER is the assertion: `\\begin` and
    `\\bibitem` carry the same two characters as their own second and third,
    and replacing those produced `\(?![A-Za-z])egin`, which does not compile.
    """
    return re.compile(re.sub(r'(?<=[A-Za-z])\\b', '(?![A-Za-z])', pattern))


MARKERS = dict((group, tuple((_compile(p), name) for p, name in patterns))
               for group, patterns in MARKERS.items())
COMMENTED = tuple((_compile(p), name) for p, name in COMMENTED)

# `flatten_tex` inlines `\input`, never `\usepackage`, so a definition that
# lives in a shipped `.sty` is absent from flat.tex entirely -- cvpr.sty's
# `\def\ie{\emph{i.e}\onedot}` among them. Surveying only the document would
# report the corpus has never seen `\def`-style definitions while nine papers
# ship them, which is blindness reported as evidence (the shape of K123).
# Only the macro group is counted here: the rest describe a document's body,
# and a style file has none.
STYLE_MARKERS = {'macro in style files': MARKERS['macro']}


def strip_comments(tex):
    return re.sub(r'(?m)(?<!\\)%.*$', '', tex)


def read(path):
    if not os.path.isfile(path):
        return ''
    return io.open(path, encoding='utf-8', errors='replace').read()


# An arXiv id carries a version suffix, and the same paper reaches this
# module spelled both ways: `--arxiv-id 2509.22944` from a caller, and
# `2509.22944v4` from detection. Keyed on the raw string the store holds two
# rows for one paper, and since every fraction `digest` prints is `len(users)`
# over `len(papers)`, both halves are then wrong: the paper is counted twice
# in the numerator it appears in and twice in the denominator of every other.
#
# Only ids shaped like arXiv's are stripped, so a folder-derived name that
# happens to end in a letter v and a digit is left exactly as it is.
_ARXIV_VERSIONED = re.compile(
    r'^(\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})v\d+$')


def normalise_id(name):
    """One paper, one key, however its id was spelled."""
    match = _ARXIV_VERSIONED.match(name)
    return match.group(1) if match else name


def paper_id(temp_dir):
    """How this paper is named in the census, and never renamed after."""
    cfg = read(os.path.join(temp_dir, 'config.txt'))
    arxiv = re.search(r'(?m)^arxiv_id=(.+)$', cfg)
    if arxiv and arxiv.group(1).strip():
        return normalise_id(arxiv.group(1).strip())
    name = os.path.basename(os.path.abspath(temp_dir))
    return normalise_id(re.sub(r'_temp.*$', '', name))


def read_style_files(temp_dir):
    r"""The `.sty`/`.cls` the paper SHIPS, concatenated.

    Its own files only. TeX Live's copy of a standard package is not in the
    tarball, so anything found here is the author's, which is what
    `paper_macros` reads and therefore what the census has to be able to
    count.
    """
    root = os.path.join(temp_dir, 'arxiv_src')
    if not os.path.isdir(root):
        return ''
    parts = []
    for base, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for name in sorted(names):
            if name.endswith(('.sty', '.cls')):
                parts.append(read(os.path.join(base, name)))
    return '\n'.join(parts)


def survey(tex, markers=None):
    """Every marker this paper carries, and how many times. {group: {name: n}}"""
    bare = strip_comments(tex)
    out = {}
    for group, patterns in (markers or MARKERS).items():
        found = {}
        for pattern, name in patterns:
            n = len(pattern.findall(bare))
            if n:
                found[name] = n
        if found:
            out[group] = found
    if markers is not None:
        # "Does this paper disable things in place?" is a question about the
        # document. Asking it of a style file would put a second
        # 'disabled in place' group into the same row and overwrite the real one.
        return out
    found = {}
    for pattern, name in COMMENTED:
        n = len(pattern.findall(tex))
        if n:
            found[name] = n
    if found:
        out['disabled in place'] = found
    return out


def load():
    if not os.path.isfile(STORE):
        return {'version': 1, 'papers': {}}
    try:
        with io.open(STORE, encoding='utf-8') as fh:
            data = json.load(fh)
    except (ValueError, IOError):
        return {'version': 1, 'papers': {}}
    data.setdefault('papers', {})
    return data


def save(data):
    folder = os.path.dirname(STORE)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    tmp = STORE + '.tmp'
    with io.open(tmp, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(json.dumps(data, ensure_ascii=False, indent=1,
                            sort_keys=True))
    if os.path.exists(STORE):
        os.remove(STORE)
    os.rename(tmp, STORE)


def record(temp_dir, quiet=False):
    """Add or refresh this paper's row. Returns the id, or None if no source."""
    tex = read(os.path.join(temp_dir, 'flat.tex'))
    if not tex:
        return None                     # calibre backend: no LaTeX to survey
    data = load()
    key = paper_id(temp_dir)
    title = re.search(r'(?m)^original_title=(.+)$',
                      read(os.path.join(temp_dir, 'config.txt')))
    known = data['papers'].get(key, {})
    shapes = survey(tex)
    style = read_style_files(temp_dir)
    if style:
        shapes.update(survey(style, STYLE_MARKERS))
    data['papers'][key] = {
        'title': (title.group(1).strip() if title else known.get('title', '')),
        'shapes': shapes,
    }
    save(data)
    if not quiet:
        groups = data['papers'][key]['shapes']
        print('Corpus census: %s recorded (%d shape(s) across %d group(s); '
              '%d paper(s) known)'
              % (key, sum(len(v) for v in groups.values()), len(groups),
                 len(data['papers'])))
    return key


def digest():
    """Every shape the corpus has met, with how many papers use it."""
    data = load()
    papers = data['papers']
    if not papers:
        return 'Corpus census is empty — no paper has been recorded yet.'
    lines = ['%d paper(s) recorded: %s' % (len(papers),
                                           ', '.join(sorted(papers)))]
    groups = {}
    for key, row in papers.items():
        for group, found in row.get('shapes', {}).items():
            for name in found:
                groups.setdefault(group, {}).setdefault(name, []).append(key)
    # STYLE_MARKERS is in this list because leaving it out does not drop the
    # data, it hides it: `record` writes the group, `digest` skips any group it
    # cannot name, and the census then answers "never seen" about shapes it has
    # counted 31 times. An entry nothing can reach may as well not be there.
    order = list(MARKERS) + list(STYLE_MARKERS) + ['disabled in place']
    for group in order:
        if group not in groups:
            continue
        lines.append('')
        lines.append('%s' % group)
        for name in sorted(groups[group], key=lambda n: (-len(groups[group][n]),
                                                         n)):
            users = sorted(groups[group][name])
            lines.append('   %-22s %d/%d  %s'
                         % (name, len(users), len(papers), ', '.join(users)))
    # The half that is hard to get any other way.
    unseen = []
    for source in (MARKERS, STYLE_MARKERS):
        for group, patterns in source.items():
            for _pattern, name in patterns:
                if name not in groups.get(group, {}):
                    unseen.append('%s (in .sty)' % name
                                  if source is STYLE_MARKERS else name)
    if unseen:
        lines.append('')
        lines.append('NEVER SEEN in this corpus — a pattern that decides on '
                     'one of these has never been tested against a real one:')
        lines.append('   ' + ', '.join(sorted(unseen)))
    return '\n'.join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd')
    rec = sub.add_parser('record', help='survey one temp dir into the census')
    rec.add_argument('temp_dir')
    rec.add_argument('--quiet', action='store_true')
    dig = sub.add_parser('digest', help='what the corpus has and has not seen')
    dig.add_argument('--json', action='store_true')
    args = ap.parse_args()

    if args.cmd == 'record':
        return 0 if record(args.temp_dir, args.quiet) else 1
    if args.cmd == 'digest':
        if args.json:
            print(json.dumps(load(), ensure_ascii=False, indent=1,
                             sort_keys=True))
        else:
            print(digest())
        return 0
    ap.print_help()
    return 1


if __name__ == '__main__':
    raise SystemExit(main())

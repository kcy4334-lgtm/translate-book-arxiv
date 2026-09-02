# -*- coding: utf-8 -*-
r"""Lint the SOURCE, not the behaviour.

Every other test here checks what the pipeline does. These check how it is
written, because three of this corpus's most expensive defects were the same
mistake wearing different clothes, and all three were already documented when
they happened again:

  * a hardcoded environment vocabulary  -> 225 cross-references numbered wrongly
  * an artefact written and never read  -> 56 formulas printed as source
  * a starred variant not accepted      -> a lost table, then a stray `{-2.5mm}`

Documentation did not stop any of them. A test that fails at the moment the
class of mistake reappears does.

Each check is written to force an explicit decision rather than to guess: when
something new shows up, the test fails and someone has to say what it is. That
is the point. Adding a name to a list here IS the decision being recorded.
"""
import json
import os
import re
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, 'scripts')


def _sources():
    for name in sorted(os.listdir(SCRIPTS)):
        if name.endswith('.py'):
            path = os.path.join(SCRIPTS, name)
            with open(path, 'r', encoding='utf-8') as fh:
                yield name, fh.read()


def _code_only(text):
    r"""The same text with comment lines blanked, line numbers preserved.

    The first thing this lint reported was one of its own comments: the note
    above `_LATEX_CRUFT_RE` quotes the broken idiom to explain what not to
    write, and the check read the explanation as the offence. A lint that
    flags its own documentation gets switched off.
    """
    out = []
    for line in text.split('\n'):
        stripped = line.lstrip()
        out.append('' if stripped.startswith('#') else line)
    return '\n'.join(out)


# ---------------------------------------------------------------------------
# 1. Starred variants
# ---------------------------------------------------------------------------
# LaTeX environments that really do have a starred form. `abstract`,
# `document`, `proof`, `itemize` and `thebibliography` do NOT, and demanding a
# star of them would flag 51 correct lines and get this check switched off.
STAR_ENVS = {
    'figure', 'table', 'tabular', 'equation', 'align', 'gather', 'multline',
    'eqnarray', 'alignat', 'flalign', 'longtable', 'wrapfigure', 'wraptable',
}
# corpus_census counts `figure` and `figure*` as DIFFERENT shapes on purpose --
# telling them apart is what the census is for.
STAR_EXEMPT_FILES = {'corpus_census.py'}

_BEGIN_FRAGMENT_RE = re.compile(r'\\\\begin\\\{(.{0,160}?)(?:\\\}|\}\')',
                                re.S)


class StarredVariantsAreAccepted(unittest.TestCase):
    """`\\begin{tabular}` is not a substring of `\\begin{tabular*}` (K111)."""

    def test_every_star_capable_environment_pattern_accepts_the_star(self):
        offenders = []
        for name, text in _sources():
            if name in STAR_EXEMPT_FILES:
                continue
            text = _code_only(text)
            for m in _BEGIN_FRAGMENT_RE.finditer(text):
                frag = m.group(1)
                named = {n for n in re.findall(r'[A-Za-z]+', frag)
                         if n in STAR_ENVS}
                if not named:
                    continue
                if '\\*' in frag or '*' in frag:
                    continue
                line = text[:m.start()].count('\n') + 1
                offenders.append('%s:%d names %s without accepting `\\*?`'
                                 % (name, line, sorted(named)))
        self.assertEqual(offenders, [], '\n' + '\n'.join(offenders))

    def test_no_pattern_takes_the_star_INSTEAD_OF_the_argument(self):
        r"""`(?:\{[^{}]*\}|\*)?` is the wrong shape, and it looks right.

        A starred command still takes its argument: `\vspace*{-2.5mm}` is a
        star AND a group. Written as an alternation the scanner eats the star,
        stops, and leaves `{-2.5mm}` standing on the page -- which is what it
        did, above twelve figures, after `\vspace{...}` had been handled
        correctly for years. Presence of `\*` is not enough to check; the
        either/or idiom is the tell.
        """
        offenders = []
        idiom = re.compile(r'\(\?:\\\{[^\n]{0,40}\\\}\|\\\*\)'
                           r'|\(\?:\\\*\|\\\{[^\n]{0,40}\\\}\)')
        for name, text in _sources():
            for m in idiom.finditer(_code_only(text)):
                line = text[:m.start()].count('\n') + 1
                offenders.append(
                    '%s:%d matches a star OR an argument, never both: %s'
                    % (name, line, m.group(0)[:60]))
        self.assertEqual(offenders, [], '\n' + '\n'.join(offenders))


# ---------------------------------------------------------------------------
# 2. Artefacts written and never read
# ---------------------------------------------------------------------------
# Every file the pipeline writes into a temp directory, and what consumes it.
# `math_macros.tex` sat in this position for the life of the project: written
# by the backend on every run, read by nothing, while the shorthand it held
# was costing whole formulas (K115).
#
# A new artefact must be added here WITH its reader. If nothing reads it, do
# not add it -- stop writing it.
ARTEFACT_CONSUMERS = {
    'input.md': 'convert.py, merge_and_build.py',
    'flat.tex': 'merge_and_build.py, verify_chunk.py, corpus_census.py',
    'math_macros.tex': 'merge_and_build.read_math_macros',
    'manifest.json': 'manifest.py, repair.py',
    'config.txt': 'backends.py, merge_and_build.py, corpus_census.py',
    'glossary.json': 'glossary.py, merge_meta.py, verify_chunk.py',
    'run_state.json': 'run_state.py',
    'source_fingerprint.json': 'convert.py',
    'output.md': 'merge_and_build.py',
    'shapes.json': 'corpus_census.py',
    'runs.json': 'referee.py',
    'unconverted_figures.txt': 'reported to the operator; not machine-read',
}

# A write site: an `open(` whose mode is w/a. The path expression is usually
# `os.path.join(temp_dir, 'name.tex')`, so it contains commas and parentheses
# -- a pattern that forbade those matched none of the real writes, and an
# artefact whose write is never seen is never checked. That blindness let the
# math_macros.tex case pass this very lint on its first run.
_WRITE_MODE_RE = re.compile(r"""open\((.{0,200}?),\s*['"][wa]['"]""", re.S)
_QUOTED_FILE_RE = re.compile(
    r"""['"]([A-Za-z0-9_.\-]+\.(?:json|tex|md|txt|html))['"]""")
# Artefacts that legitimately have no in-tree reader. Each needs a reason.
NO_READER_BY_DESIGN = {
    'unconverted_figures.txt': 'a report for the operator, not machine-read',
}


def _write_sites():
    """{artefact: number of open(..., 'w') sites naming it}."""
    writes = {}
    for _name, text in _sources():
        for m in _WRITE_MODE_RE.finditer(_code_only(text)):
            for art in set(_QUOTED_FILE_RE.findall(m.group(1))):
                writes[art] = writes.get(art, 0) + 1
    return writes


def _artefact_mentions():
    """{artefact: (total mentions, write sites)} across every script."""
    writes = _write_sites()
    counts = {}
    for art, n in writes.items():
        mentions = sum(_QUOTED_FILE_RE.findall(text).count(art)
                       for _name, text in _sources())
        counts[art] = (mentions, n)
    return counts


class WrittenArtefactsHaveAReader(unittest.TestCase):
    """An artefact nobody reads is a silent hole (K115).

    The assertion is mechanical on purpose. Requiring only that an artefact be
    listed in a table would pass for `math_macros.tex`, which was faithfully
    written on every run and read by nothing for the life of the project --
    a table entry naming a consumer that does not consume it looks exactly
    like one that does.
    """

    def test_every_written_artefact_is_mentioned_somewhere_other_than_its_write(self):
        orphans = []
        for artefact, (total, writes) in sorted(_artefact_mentions().items()):
            if artefact in NO_READER_BY_DESIGN:
                continue
            if total <= writes:
                orphans.append(
                    '%s is written %d time(s) and mentioned nowhere else: '
                    'nothing reads it' % (artefact, writes))
        self.assertEqual(orphans, [], '\n' + '\n'.join(orphans))

    def test_every_written_artefact_is_declared_with_its_consumer(self):
        undeclared = sorted(art for art in _write_sites()
                            if art not in ARTEFACT_CONSUMERS
                            and art not in NO_READER_BY_DESIGN)
        self.assertEqual(
            undeclared, [],
            'written with no declared consumer: %s\n'
            'Name what reads each one in ARTEFACT_CONSUMERS, or stop writing '
            'it.' % undeclared)

    def test_declared_consumers_are_not_stale(self):
        # A named consumer must exist AND actually mention the artefact.
        missing = []
        for artefact, consumer in ARTEFACT_CONSUMERS.items():
            for token in re.findall(r'[A-Za-z_]+\.py', consumer):
                path = os.path.join(SCRIPTS, token)
                if not os.path.isfile(path):
                    missing.append('%s -> %s does not exist'
                                   % (artefact, token))
                    continue
                with open(path, 'r', encoding='utf-8') as fh:
                    if artefact not in fh.read():
                        missing.append('%s -> %s never mentions it'
                                       % (artefact, token))
        self.assertEqual(missing, [], '\n' + '\n'.join(missing))


# ---------------------------------------------------------------------------
# 3. The corpus census as a vocabulary oracle
# ---------------------------------------------------------------------------
# The census is the accumulated experience of every paper translated so far.
# Using it as an oracle is what makes that experience enforce something: when
# paper N+1 introduces a construct nobody has met, this fails and the
# construct has to be classified before the paper ships.
#
# `handled`  - a pass in the pipeline acts on it
# `counted`  - recorded so it can be noticed, deliberately not acted on
# `gap`      - known to be unhandled; the reason belongs in KNOWLEDGE.md
CONSTRUCT_DISPOSITION = {
    'cite': 'handled', 'citep': 'handled', 'citet': 'handled',
    'bibitem': 'handled', 'thebibliography-inlined': 'handled',
    'bibliography-file': 'handled',
    'author': 'handled', 'thanks': 'handled', 'footnote': 'handled',
    'footnotemark': 'handled', 'markboth': 'counted',
    'caption': 'handled', 'captionof': 'handled', 'subcaption': 'handled',
    'captionsetup': 'counted', 'commented-caption': 'handled',
    'figure': 'handled', 'figure*': 'handled', 'table': 'handled',
    'table*': 'handled', 'subfigure': 'handled', 'subfloat': 'handled',
    'wrapfigure': 'handled', 'SCfigure': 'handled', 'minipage': 'handled',
    'commented-float': 'handled', 'tikzpicture': 'gap',
    'tabular': 'handled', 'multicolumn': 'handled', 'multirow': 'handled',
    'cmidrule': 'handled', 'addlinespace': 'handled',
    'repeat-column-spec': 'handled', 'tnote': 'handled',
    'equation': 'handled', 'align': 'handled', 'gather': 'handled',
    'eqnarray': 'handled', 'nolimits': 'handled', 'sideset': 'handled',
    # Maynard writes 74 of these, and Shor's one `\atop` is rewritten INTO
    # `\substack` by `_ATOP_RE` — so a gap here would be one the pipeline
    # creates for itself. Rendered through pandoc in the two-line, three-line
    # and `\prod` forms: all three give MathML with nothing left over.
    'substack': 'handled',
    # Both spellings of the document declaration. `documentstyle` is LaTeX
    # 2.09; the backend accepts it since Shor 1995, which it had rejected.
    'documentclass': 'handled', 'documentstyle': 'handled',
    # The affiliation family (K123). `unwrap_front_matter` keeps the prose in
    # the first, deletes the second as a directive. The rest of the family —
    # institute, running-head, class-affiliation, icml-frontmatter — has
    # markers in the census but no entry here on purpose: this table describes
    # what the corpus has MET, and saying NEVER SEEN is the census's job.
    'address': 'handled', 'email': 'handled', 'institute': 'handled',
    'running-head': 'handled',
    'maketitle': 'handled', 'bibliographystyle': 'handled',
    # `\icmlauthor{Name}{key}` keeps its FIRST argument and
    # `\icmlaffiliation{key}{Org}` its SECOND — read out of icml2026.sty. SINQ's
    # six authors and its affiliation appeared zero times in its own book until
    # this was handled (K138).
    'icml-frontmatter': 'handled',
    'newcommand': 'handled', 'def': 'handled', 'old-font-switch': 'handled',
    'setlength': 'handled', 'resizebox': 'handled', 'scalebox': 'handled',
    'rotatebox': 'handled', 'algorithm': 'handled', 'algorithmic': 'handled',
    'lstlisting': 'handled', 'IEEEPARstart': 'handled',
    'twocolumn-title': 'handled',
    # Tables the corpus met once the census widened from 19 papers to 24.
    # `\makecell{a\\b}` is unwrapped because pandoc renders that cell EMPTY.
    'longtable': 'handled', 'tabularx': 'handled', 'makecell': 'handled',
    # ---- the paper's own macros (K135) ----------------------------------
    # Every spelling `paper_macros.read_definitions` recognises. A spelling it
    # misses is not a crash: the macro is simply never collected, so its name
    # goes on printing at the reader, which is the defect the module exists
    # for. That is why each one is counted separately rather than as "a
    # definition".
    'newcommand-braced': 'handled', 'newcommand-bare': 'handled',
    'newcommand-starred': 'handled', 'renewcommand': 'handled',
    'providecommand': 'handled', 'DeclareRobustCommand': 'handled',
    'optional-argument': 'handled',
    # `\let\foo\bar` binds a name without a body, and `read_definitions` does
    # not read it. 16 of 24 papers ship one. See K141.
    'let-binding': 'gap',
    # The conditional-definition path. The flag is NOT evaluated — doing that
    # means executing package options — so a name defined once per branch is
    # settled by what the printed paper shows instead (H38).
    'newif': 'counted',
    # cvpr.sty's abbreviation period: `\futurelet` lookahead that adds a stop
    # unless one follows. Recognised by the shape of its body, not its name.
    'futurelet': 'handled', 'onedot': 'handled',
    'abbreviation-macro': 'handled', 'run-in-heading-macro': 'handled',
    'newcite': 'handled', 'xspace': 'handled', 'ensuremath': 'handled',
    'bfseries-group': 'handled',
    # Their argument is a colour, not text, so they are dropped whole.
    'cellcolor': 'handled', 'rowcolor': 'handled',
    # Destructive if mistaken for an abbreviation: a macro bound to a tab stop
    # looks exactly like one, and resolving it to nothing deletes the
    # indentation of a listing. Refused by shape.
    'tabbing': 'handled', 'tabbing-kill': 'handled', 'tab-stop': 'handled',
    # The maths delimiters that decide which regions no rewrite may touch.
    'display-bracket': 'handled', 'inline-paren': 'handled',
    # A wrapper, not a formula: what it holds is `equation` environments, and
    # those are spans in their own right. Counted so a paper that puts prose
    # directly inside one is noticed.
    'subequations': 'counted',
}


def _census_constructs():
    path = os.path.join(ROOT, 'corpus', 'shapes.json')
    if not os.path.isfile(path):
        return {}
    with open(path, 'r', encoding='utf-8') as fh:
        data = json.load(fh)
    seen = {}
    for paper in (data.get('papers') or {}).values():
        for group in (paper.get('shapes') or {}).values():
            if isinstance(group, dict):
                for construct, count in group.items():
                    if count:
                        seen[construct] = seen.get(construct, 0) + 1
    return seen


class CensusVocabularyIsClassified(unittest.TestCase):
    """Every construct the corpus has met has a recorded disposition."""

    def test_no_construct_is_unclassified(self):
        seen = _census_constructs()
        if not seen:
            self.skipTest('no corpus census in this checkout')
        unknown = sorted(c for c in seen if c not in CONSTRUCT_DISPOSITION)
        self.assertEqual(
            unknown, [],
            'the corpus has met construct(s) nobody has classified: %s\n'
            'Add each to CONSTRUCT_DISPOSITION as handled/counted/gap.'
            % unknown)

    def test_dispositions_use_a_known_value(self):
        bad = {c: d for c, d in CONSTRUCT_DISPOSITION.items()
               if d not in ('handled', 'counted', 'gap')}
        self.assertEqual(bad, {})

    def test_the_table_does_not_rot(self):
        # A construct listed here that the corpus has never met is either a
        # typo or a leftover; both make the oracle less trustworthy.
        seen = _census_constructs()
        if not seen:
            self.skipTest('no corpus census in this checkout')
        stale = sorted(c for c in CONSTRUCT_DISPOSITION if c not in seen)
        self.assertEqual(stale, [],
                         'classified but never seen in the corpus: %s' % stale)


# ---------------------------------------------------------------------------
# 4. The advisors are called by the pipeline, not by whoever remembers
# ---------------------------------------------------------------------------
class GrowthStoresAreWiredIn(unittest.TestCase):
    r"""An advisor you have to remember to consult is a document.

    The referee's tally sat at ten runs while nine books were rebuilt and one
    was re-translated from scratch, because recording was a separate command
    and nobody ran it. The census did grow over the same period -- it is
    called from the build. That is the whole difference, and it is worth a
    test: these calls are easy to drop in a refactor and nothing else notices,
    because a store that stops growing looks exactly like a quiet week.
    """

    def _main_body(self):
        with open(os.path.join(SCRIPTS, 'merge_and_build.py'), 'r',
                  encoding='utf-8') as fh:
            text = fh.read()
        at = text.rindex('\ndef main(')
        return text[at:]

    def test_the_build_records_the_corpus_census(self):
        body = self._main_body()
        self.assertIn('import corpus_census', body)
        self.assertIn('corpus_census.record(', body)

    def test_the_build_records_and_prints_the_referee(self):
        body = self._main_body()
        self.assertIn('import referee', body)
        self.assertIn('referee.collect(', body)
        self.assertIn('referee.save(', body,
                      'the referee must RECORD, not only comment: a judgement '
                      'nobody stores cannot notice a repeat next time')

    def test_the_build_reports_advisors_never_consulted(self):
        # The one state nobody could see: an advisor that leaves no trace.
        body = self._main_body()
        self.assertIn('import advisors', body)
        self.assertIn('advisors.build_note(', body)

    def test_none_of_them_can_fail_the_build(self):
        # Observability must never break a good book.
        body = self._main_body()
        for call in ('corpus_census.record(', 'referee.collect(',
                     'advisors.build_note('):
            at = body.index(call)
            window = body[max(0, at - 400):at]
            self.assertIn('try:', window,
                          '%s is not inside a try/except' % call)


# ---------------------------------------------------------------------------
# 5. Nothing shipped may name a path that exists on one machine only
# ---------------------------------------------------------------------------
# The advisors were unreachable for ten papers because they shipped to a
# location no runtime searches, and nothing said so. The same class in another
# costume: a doc pointing the reader at an output directory that exists only on
# the author's computer. Three of those were sitting in KNOWLEDGE.md and
# SKILL.md.
#
# The line is PERSONAL vs STANDARD, not absolute vs relative. `C:\Program
# Files\Calibre2` is the same on every Windows machine and the tool has to name
# it to find Calibre; a drive-letter path to anything else, or a path through
# somebody's home directory, works nowhere but here. A first attempt at this
# check flagged all eleven of the legitimate system paths and would have been
# switched off within the hour.
_SYSTEM_ROOTS = ('program files', 'program files (x86)', 'programdata',
                 'windows', 'users')
_DRIVE_PATH_RE = re.compile(r'(?<![A-Za-z0-9])([A-Za-z]):[\\/]{1,2}'
                            r'([A-Za-z0-9_ ()\-.]{0,40})')
_ABSOLUTE_PATH_RES = (
    ('home directory path',
     re.compile(r'/(?:home|Users)/(?!<)[a-z0-9_.\-]{2,}/')),
    ('personal Windows path',
     re.compile(r'(?<![A-Za-z0-9])[A-Za-z]:[\\/]{1,2}Users[\\/]{1,2}'
                r'(?!<)[A-Za-z0-9_.\-]+')),
)
# Files whose whole subject is where things live on a real machine.
PATH_DOC_ALLOWLIST = {'INSTALL.md'}
_SHIPPED_TEXT = ('.md', '.py', '.yml', '.yaml', '.json', '.html', '.txt')


def _shipped_text_files():
    skip_dirs = {'__pycache__', '.git', '.artifacts', 'arxiv_src', 'images'}
    for root, dirs, names in os.walk(ROOT):
        dirs[:] = [d for d in dirs
                   if d not in skip_dirs and not d.endswith('_temp')]
        for name in sorted(names):
            if not name.endswith(_SHIPPED_TEXT) or name in PATH_DOC_ALLOWLIST:
                continue
            path = os.path.join(root, name)
            rel = os.path.relpath(path, ROOT).replace('\\', '/')
            if rel.startswith('tests/.artifacts/'):
                continue
            try:
                with open(path, 'r', encoding='utf-8', errors='replace') as fh:
                    yield rel, fh.read()
            except OSError:
                continue


class NoMachineSpecificPaths(unittest.TestCase):
    def test_no_shipped_file_names_an_absolute_local_path(self):
        offenders = []
        for rel, text in _shipped_text_files():
            body = _code_only(text) if rel.endswith('.py') else text
            for label, pattern in _ABSOLUTE_PATH_RES:
                for m in pattern.finditer(body):
                    line = body[:m.start()].count('\n') + 1
                    offenders.append('%s:%d %s %r'
                                     % (rel, line, label,
                                        body[m.start():m.start() + 40]))
            for m in _DRIVE_PATH_RE.finditer(body):
                first = m.group(2).strip().strip('\\/').lower()
                if not first or first.startswith(_SYSTEM_ROOTS):
                    continue            # the same on every machine of this OS
                line = body[:m.start()].count('\n') + 1
                offenders.append('%s:%d drive-letter path %r'
                                 % (rel, line, body[m.start():m.start() + 40]))
        self.assertEqual(
            sorted(set(offenders)), [],
            '\n' + '\n'.join(sorted(set(offenders)))
            + '\nUse a portable reference (~, %USERPROFILE%, <output_dir>) '
              'instead: a resolved path works on one machine only.')


# ---------------------------------------------------------------------------
# 5b. Every file still naming the upstream author is listed in PUBLISHING.md
# ---------------------------------------------------------------------------
# This tree is an MIT fork. Publishing it as it stands would put a Sponsor
# button on the maintainer's own repository pointing at somebody else, and
# install instructions that install somebody else's copy. PUBLISHING.md is the
# checklist for that, and a checklist that goes stale is worse than none — so
# a NEW file carrying the upstream name has to be added to it before it can be
# committed.
_UPSTREAM = 'deusyu'


class UpstreamReferencesAreDocumented(unittest.TestCase):
    def test_publishing_md_exists(self):
        self.assertTrue(
            os.path.isfile(os.path.join(ROOT, 'PUBLISHING.md')),
            'PUBLISHING.md is what makes the fork publishable; without it the '
            'licence obligations live only in someone\'s memory')

    def test_every_file_naming_upstream_is_listed(self):
        with open(os.path.join(ROOT, 'PUBLISHING.md'), encoding='utf-8') as fh:
            doc = fh.read()
        missing = []
        for rel, text in _shipped_text_files():
            if rel == 'PUBLISHING.md' or _UPSTREAM not in text:
                continue
            name = os.path.basename(rel)
            if name not in doc and rel not in doc:
                missing.append(rel)
        # Files outside `_SHIPPED_TEXT` that have carried the upstream name.
        # `.github/FUNDING.yml` was deleted and the poster removed; both stay
        # named here so that restoring either one fails this test until
        # PUBLISHING.md is updated to say what it now is.
        for extra in ('assets/poster/pages/poster.page',
                      'assets/poster/pages/poster-en.page',
                      '.github/FUNDING.yml'):
            path = os.path.join(ROOT, *extra.split('/'))
            if not os.path.isfile(path):
                continue
            with open(path, encoding='utf-8', errors='replace') as fh:
                if _UPSTREAM in fh.read() and os.path.basename(extra) not in doc:
                    missing.append(extra)
        self.assertEqual(
            sorted(set(missing)), [],
            'these still name the upstream author and PUBLISHING.md does not '
            'mention them: %s' % sorted(set(missing)))

    def test_the_licence_keeps_the_upstream_copyright(self):
        # MIT's one condition. Removing this line is what turns a permitted
        # fork into an infringing one, and it is one careless edit away.
        with open(os.path.join(ROOT, 'LICENSE'), encoding='utf-8') as fh:
            licence = fh.read()
        self.assertIn('Copyright (c) 2025 Rainman', licence)
        self.assertIn('MIT License', licence)


# ---------------------------------------------------------------------------
# 6. The advisors ship in a usable state
# ---------------------------------------------------------------------------
class ShippedAdvisorsAreUsable(unittest.TestCase):
    """CI cannot see the user's home directory. It can see everything else.

    What went wrong was never caught because nothing checked the shipped
    definitions at all: they were valid, and in a place nothing reads. CI can
    confirm they are well formed, that their names are the ones the tooling
    expects, and that the installer actually puts them somewhere — which is
    every part of the failure except the one only the user's machine knows.
    """

    def _agents(self):
        d = os.path.join(ROOT, '.claude', 'agents')
        return d, sorted(n for n in os.listdir(d) if n.endswith('.md'))

    def test_every_definition_has_usable_frontmatter(self):
        d, names = self._agents()
        bad = []
        for name in names:
            with open(os.path.join(d, name), 'r', encoding='utf-8') as fh:
                text = fh.read()
            if not text.startswith('---'):
                bad.append('%s: no frontmatter' % name)
                continue
            head = text.split('---', 2)[1]
            for key in ('name:', 'description:', 'tools:'):
                if key not in head:
                    bad.append('%s: frontmatter has no %s' % (name, key))
            declared = re.search(r'^name:\s*(\S+)', head, re.M)
            if not declared:
                bad.append('%s: name is unreadable' % name)
            elif declared.group(1) != name[:-3]:
                bad.append('%s: declares name %r' % (name, declared.group(1)))
        self.assertEqual(bad, [], '\n'.join(bad))

    def test_the_shipped_set_matches_what_the_tooling_expects(self):
        sys.path.insert(0, SCRIPTS)
        import advisors
        _d, names = self._agents()
        self.assertEqual(sorted(n[:-3] for n in names),
                         sorted(advisors.KNOWN),
                         'the definitions on disk and advisors.KNOWN disagree; '
                         'status would report an advisor that cannot exist, or '
                         'miss one that does')

    def test_the_installer_puts_them_where_a_runtime_looks(self):
        sys.path.insert(0, SCRIPTS)
        import install_advisors
        dest = os.path.join(tempfile.mkdtemp(prefix='tb-ci-'), 'agents')
        installed, up_to_date, conflicts = install_advisors.install(dest)
        self.assertEqual(conflicts, [])
        self.assertEqual(sorted(installed + up_to_date),
                         sorted(install_advisors.shipped_agents()))
        for name in installed:
            self.assertTrue(os.path.isfile(os.path.join(dest, name)))

    def test_installing_twice_changes_nothing(self):
        sys.path.insert(0, SCRIPTS)
        import install_advisors
        dest = os.path.join(tempfile.mkdtemp(prefix='tb-ci2-'), 'agents')
        install_advisors.install(dest)
        installed, up_to_date, conflicts = install_advisors.install(dest)
        self.assertEqual((installed, conflicts), ([], []))
        self.assertTrue(up_to_date)


if __name__ == '__main__':
    unittest.main()

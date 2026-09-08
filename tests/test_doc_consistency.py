# -*- coding: utf-8 -*-
r"""The documentation is checked the way the code is, or it rots unnoticed.

Every finding here was found by hand, once, because somebody asked. That is
the failure this file exists to end: a sweep that lives in a scratch
directory is a sweep that happens when a user thinks to request it.

What the hand sweep found, and what would have caught it:

  * SKILL.md and AGENTS.md still told the next agent to centre a display
    equation with `display: flex` -- the rule removed for dropping the first
    child of a wide formula, which cost equation (3) its left-hand side.
    AGENTS.md's copy sat in the "do not" list, read as a rule. A document
    that recommends a removed rule is worse than one that says nothing.
  * A prose citation pointed at K128 for a finding that is K139. The existing
    index test only checks markdown links, so a bare `K139` in a sentence --
    which is how findings are cited in prose and in every other document --
    was never validated at all.
  * A Status line cited a test count that had grown.

These run on the standard library alone, like the rest of the suite.
"""
import json
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DOCS = ['README.md', 'SKILL.md', 'AGENTS.md', 'CLAUDE.md', 'KNOWLEDGE.md',
        'KNOWHOW.md', 'INSTALL.md', 'PUBLISHING.md', 'REFEREE.md']

# `K12` but not the `12` of `K12`-like noise inside a longer token.
CITATION_RE = re.compile(r'(?<![A-Za-z0-9])K(\d+)(?![0-9])')
ENTRY_RE = re.compile(r'^### K(\d+)\s*$', re.MULTILINE)


def read(name):
    return (REPO / name).read_text(encoding='utf-8')


def docs():
    return {name: read(name) for name in DOCS if (REPO / name).is_file()}


# A preceding slash is the NORMAL case: the run book writes
# `python {baseDir}/scripts/glossary.py`. Only a word character or a dot in
# front means this is some other directory that merely ends in "scripts".
SCRIPT_RE = re.compile(r'(?<![\w.])(scripts|tests)[/\\]([A-Za-z0-9_]+\.py)')


class EveryCommandTheDocsNameExists(unittest.TestCase):
    r"""A document that points at a script nobody kept is a dead end.

    SKILL.md is a run book: an agent follows it by typing what it says. When
    a script is renamed or absorbed, the sentence naming it keeps reading
    perfectly well and the command fails at the moment somebody needs it,
    which is halfway through a paper. Nothing in the suite noticed that
    `sidecar_edit.py` had been added and nothing would have noticed it being
    taken away.
    """

    def named(self):
        """(document, relative path) for every script any document names."""
        for name, text in docs().items():
            for folder, script in SCRIPT_RE.findall(text):
                yield name, '%s/%s' % (folder, script)

    def test_every_named_script_is_on_disk(self):
        missing = sorted({(doc, path) for doc, path in self.named()
                          if not (REPO / path).is_file()})
        self.assertEqual(missing, [], 'named in a document, absent from the '
                                      'repository: %s' % missing)

    def test_the_docs_actually_name_the_pipeline(self):
        """Guards the regex, not the docs: a pattern that matches nothing
        passes the test above for the wrong reason."""
        found = {path for _, path in self.named()}
        for expected in ('scripts/merge_and_build.py', 'scripts/convert.py',
                         'scripts/sidecar_edit.py', 'tests/table_probe.py'):
            self.assertIn(expected, found)


class CitationsPointSomewhere(unittest.TestCase):
    r"""A citation that points at the wrong entry is worse than none: it
    lends a claim the authority of a finding that says something else.

    K160 was written citing K128 for the refusal of an unparseable author
    block. K128 is about `\begin{comment}`; the refusal is K139."""

    def setUp(self):
        self.entries = {int(n) for n in ENTRY_RE.findall(read('KNOWLEDGE.md'))}
        self.assertTrue(self.entries, 'KNOWLEDGE.md has no entries')

    def test_every_citation_in_every_document_exists(self):
        dangling = {}
        for name, body in docs().items():
            bad = sorted({int(n) for n in CITATION_RE.findall(body)}
                         - self.entries)
            if bad:
                dangling[name] = bad
        self.assertFalse(
            dangling,
            'citations point at entries that do not exist: %s' % dangling)

    def test_the_index_and_the_entries_agree(self):
        """Already covered for links; repeated here so a failure names the
        direction, and so this file stands on its own."""
        indexed = {int(a) for a, _b
                   in re.findall(r'\[K(\d+)\]\(#k(\d+)\)', read('KNOWLEDGE.md'))}
        self.assertEqual(indexed - self.entries, set())
        self.assertEqual(self.entries - indexed, set())


class StatusLinesNameRealTests(unittest.TestCase):
    """`*Status: LOCKED, `SomeTests`.*` is the entry's evidence. A name that
    no longer exists turns the evidence into a claim."""

    def setUp(self):
        source = []
        for sub in ('tests', 'scripts'):
            for path in sorted((REPO / sub).glob('*.py')):
                source.append(path.read_text(encoding='utf-8',
                                             errors='replace'))
        self.defined = set(re.findall(r'^\s*(?:def|class)\s+([A-Za-z_]\w*)',
                                      '\n'.join(source), re.M))
        self.files = {p.name for p in (REPO / 'tests').glob('*.py')}

    def test_every_cited_test_name_exists(self):
        missing = set()
        for line in re.findall(r'\*Status:[^*]*\*', read('KNOWLEDGE.md')):
            for name in re.findall(r'`([A-Za-z_][\w.]*)`', line):
                if name.endswith('.py'):
                    if name not in self.files:
                        missing.add(name)
                elif name[0].isupper() and name not in self.defined:
                    missing.add(name)
        self.assertFalse(missing,
                         'Status lines cite tests that do not exist: %s'
                         % sorted(missing))


class NoDocumentRecommendsARemovedRule(unittest.TestCase):
    r"""The one that mattered most, because it was an instruction.

    `display: flex` on a block `<math>` centres correctly and drops the first
    child of any formula wider than the container. It is allowed to appear in
    KNOWLEDGE.md, where K63 strikes it through and K151 explains what it
    cost. Anywhere else it reads as advice."""

    BANNED = [
        ('justify-content',
         'flex centring for display maths, removed in K151'),
    ]

    def test_removed_rules_survive_only_where_they_are_explained(self):
        for needle, why in self.BANNED:
            for name, body in docs().items():
                if name == 'KNOWLEDGE.md':
                    continue
                self.assertNotIn(
                    needle, body,
                    '%s still names `%s` (%s); a reader takes that as the '
                    'way to do it' % (name, needle, why))

    def test_the_knowledge_entry_that_explains_it_is_still_there(self):
        """If K151 is ever deleted the exemption above becomes a hole."""
        self.assertIn('### K151', read('KNOWLEDGE.md'))


class EveryModuleIsDescribedSomewhere(unittest.TestCase):
    r"""A module no document mentions is one the next agent will not find,
    and will rebuild badly. `equation_fit` shipped before anything named it.

    The mention has to be of the module ITSELF. A bare substring test
    passed `scripts/table_language.py` on the day it was written, because
    `check_table_language` -- a different symbol, in a different file,
    named in a Status line -- contains its name. The module was documented
    nowhere and the check said it was fine, which is the failure this whole
    file exists to end.
    """

    def named_as_itself(self, stem, joined):
        return re.search(r'(?<![A-Za-z0-9_])%s(?![A-Za-z0-9_])'
                         % re.escape(stem), joined) is not None

    def test_each_script_is_named_by_a_document(self):
        joined = '\n'.join(docs().values())
        unmentioned = [p.stem for p in sorted((REPO / 'scripts').glob('*.py'))
                       if not self.named_as_itself(p.stem, joined)]
        self.assertFalse(unmentioned,
                         'scripts no document mentions: %s' % unmentioned)

    def test_a_longer_symbol_does_not_count_as_a_mention(self):
        """Guards the boundary, not the docs."""
        self.assertFalse(self.named_as_itself(
            'table_language', 'see `check_table_language` in format_probe'))
        self.assertTrue(self.named_as_itself(
            'table_language', 'see `scripts/table_language.py` for the list'))


def entry_count(doc, letter):
    return len(re.findall(r'^### %s\d+\s*$' % letter, read(doc), re.M))


def corpus_papers():
    raw = json.loads((REPO / 'corpus' / 'shapes.json')
                     .read_text(encoding='utf-8'))
    rows = raw.get('papers', raw) if isinstance(raw, dict) else raw
    return len(rows)


def suite_size():
    r"""What `unittest discover` will report, without importing anything.

    Counted by regex rather than by loading the suite, because this file is
    part of what it counts. `test_the_regex_agrees_with_the_runner` below
    holds the two together.

    The indent class is `[ \t]` and not `\s`, which matches a newline: with
    `re.M`, `^\s+def test_` starts at a blank line, eats the newline, and
    counts a module-level `def test_...` helper as a method of a class. That
    is how this function -- named `test_methods` at the time -- counted
    itself, and the number was one too high until the runner disagreed.
    """
    total = 0
    for path in sorted((REPO / 'tests').glob('test_*.py')):
        total += len(re.findall(r'^[ \t]+def test_', path.read_text(
            encoding='utf-8', errors='replace'), re.M))
    return total


# (label, what the repository actually holds, how the docs spell the claim,
#  how many places spell it). Patterns stay on one line: a claim is always
#  written next to the thing it counts.
CLAIMS = [
    ('KNOWLEDGE.md entries', lambda: entry_count('KNOWLEDGE.md', 'K'),
     r'`KNOWLEDGE\.md`[^\n]{0,80}?(\d[\d,]*)', 2),
    ('KNOWHOW.md entries', lambda: entry_count('KNOWHOW.md', 'H'),
     r'`KNOWHOW\.md`[^\n]{0,80}?(\d[\d,]*)', 2),
    ('REFEREE.md entries', lambda: entry_count('REFEREE.md', 'R'),
     r'`REFEREE\.md`[^\n]{0,80}?(\d[\d,]*)', 2),
    ('corpus papers, in the census sentence', corpus_papers,
     r'corpus has met across (\d[\d,]*) papers', 1),
    ('corpus papers, in the structure table', corpus_papers,
     r'`corpus/shapes\.json`[^\n]{0,140}?(\d[\d,]*) papers', 1),
    ('tests', suite_size, r'\*\*Tests\*\*[^\n]{0,20}?(\d[\d,]*)', 1),
]


class CountsInTheDocsMatchWhatIsThere(unittest.TestCase):
    r"""A number in the README is a claim, and it is the one a reader checks.

    This file's own docstring already records "a Status line cited a test
    count that had grown" -- found by hand, written down, and then not
    turned into a check. It grew again: the README said 1,608 tests against
    2,001, 150 KNOWLEDGE entries against 175, and KNOWHOW 38 in one row and
    39 in the row above it.

    That is the worst place to be wrong. The pitch is carefulness, and the
    first thing a sceptical reader does is clone the repository and run the
    suite. Every count here is derived from the artefact rather than
    restated, so the claim cannot drift from the thing it describes.
    """

    def located(self, pattern):
        """(document, number) for every place the docs spell this claim."""
        for name, body in sorted(docs().items()):
            for hit in re.findall(pattern, body):
                yield name, int(hit.replace(',', '').rstrip(','))

    def test_every_count_the_docs_state_is_the_count_on_disk(self):
        wrong = []
        for label, actual, pattern, _sites in CLAIMS:
            want = actual()
            for name, said in self.located(pattern):
                if said != want:
                    wrong.append('%s: %s says %d, repository holds %d'
                                 % (name, label, said, want))
        self.assertEqual(wrong, [], 'stale counts: %s' % wrong)

    def test_each_claim_is_still_found_where_it_was(self):
        """The failure this guards is a pattern that stops matching.

        A rephrased sentence would leave the test above passing over an
        empty set, which is the shape of every check this session had to
        repair: not missing the answer, but confidently answering a
        question nobody asked.
        """
        for label, _actual, pattern, sites in CLAIMS:
            found = list(self.located(pattern))
            self.assertEqual(
                len(found), sites,
                '%s: matched %d places, expected %d (%s). A reworded claim '
                'is not checked by anything; update the pattern or the '
                'count.' % (label, len(found), sites, found))


class TheCountingItselfIsChecked(unittest.TestCase):
    """An oracle nobody checks is a second thing that can be wrong."""

    def test_the_regex_agrees_with_the_runner(self):
        r"""`def test_` counted by regex equals what `unittest discover`
        reports, so the README's test number needs no test run to verify.
        Inheritance or a generated case would break the equality, and this
        is where that would show."""
        import unittest as ut
        loader = ut.TestLoader()
        suite = loader.discover(str(REPO / 'tests'), pattern='test_*.py')
        self.assertEqual(suite.countTestCases(), suite_size())
        self.assertEqual(loader.errors, [])

    def test_the_entry_counters_find_entries(self):
        """A regex that matches nothing makes every count zero and every
        claim equally wrong."""
        for doc, letter in (('KNOWLEDGE.md', 'K'), ('KNOWHOW.md', 'H'),
                            ('REFEREE.md', 'R')):
            self.assertGreater(entry_count(doc, letter), 0, doc)
        self.assertGreater(corpus_papers(), 0)
        self.assertGreater(suite_size(), 0)


if __name__ == '__main__':
    unittest.main()

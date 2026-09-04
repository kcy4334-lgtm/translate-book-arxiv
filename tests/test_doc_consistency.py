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
    """A module no document mentions is one the next agent will not find,
    and will rebuild badly. `equation_fit` shipped before anything named it."""

    def test_each_script_is_named_by_a_document(self):
        joined = '\n'.join(docs().values())
        unmentioned = [p.stem for p in sorted((REPO / 'scripts').glob('*.py'))
                       if p.stem not in joined]
        self.assertFalse(unmentioned,
                         'scripts no document mentions: %s' % unmentioned)


if __name__ == '__main__':
    unittest.main()

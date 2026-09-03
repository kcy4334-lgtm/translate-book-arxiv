# -*- coding: utf-8 -*-
r"""The consultation log, and the one thing it exists to make visible.

`referee` could be diagnosed because it kept a store: a stalled count is what
showed that recording had stopped. The other three kept nothing, so the
question "has old-man ever been consulted?" had no answer anywhere in the
repository -- not for the operator and not for the agent supposed to be
calling it.

So the load-bearing behaviour here is not `record`. It is that an advisor with
no rows is reported as never consulted, out loud, without anyone asking.
"""
import io
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import advisors  # noqa: E402


class _Store(unittest.TestCase):
    """Each test gets its own store; none of them touch the real log."""

    def setUp(self):
        self._dir = tempfile.mkdtemp(prefix='tb-advisors-')
        self._old = (advisors.STORE_DIR, advisors.STORE)
        advisors.STORE_DIR = self._dir
        advisors.STORE = os.path.join(self._dir, 'consults.jsonl')

    def tearDown(self):
        advisors.STORE_DIR, advisors.STORE = self._old


class SilenceIsVisible(_Store):
    r"""These are about the CONSULTATION log, so the install state has to be
    held still — `build_note` reports both, and an uninstalled advisor is the
    louder of the two.

    Left to inherit the machine, two of these passed here and failed on CI from
    the first push: this developer's `~/.claude/agents/` has the four, a fresh
    Ubuntu runner has none, and the note came back "NOT INSTALLED" where the
    test expected silence. `NotInstalledIsLouderThanNotConsulted` below already
    pins the opposite state; this is the same trick pointed the other way.
    """

    def setUp(self):
        _Store.setUp(self)
        self._home = os.path.expanduser
        self._cwd = os.getcwd()
        self._fake = tempfile.mkdtemp(prefix='tb-home-')
        agents = os.path.join(self._fake, '.claude', 'agents')
        os.makedirs(agents)
        for name in advisors.KNOWN:
            with io.open(os.path.join(agents, '%s.md' % name), 'w',
                         encoding='utf-8') as fh:
                fh.write('installed, for this test only\n')
        os.path.expanduser = lambda p: p.replace('~', self._fake)
        os.chdir(self._fake)

    def tearDown(self):
        os.path.expanduser = self._home
        os.chdir(self._cwd)
        _Store.tearDown(self)

    def test_the_four_are_installed_for_these_tests(self):
        # If this fails the rest of the class is measuring the wrong thing.
        for name in advisors.KNOWN:
            self.assertIsNotNone(advisors.installed_where(name))

    def test_an_advisor_with_no_rows_is_reported_as_never_consulted(self):
        lines = '\n'.join(advisors.status_lines())
        for name in advisors.KNOWN:
            self.assertIn(name, lines)
        self.assertIn('never consulted', lines)

    def test_the_build_note_names_every_silent_advisor(self):
        note = advisors.build_note()
        self.assertIsNotNone(note, 'an empty log must not be silent itself')
        for name in advisors.KNOWN:
            self.assertIn(name, note)

    def test_the_build_note_goes_quiet_once_all_have_been_consulted(self):
        for name in advisors.KNOWN:
            advisors.record(name, paper='p1', asked='q', verdict='v')
        self.assertIsNone(advisors.build_note())

    def test_one_consulted_advisor_does_not_hide_the_others(self):
        advisors.record('old-man', paper='p1', asked='q', verdict='v')
        note = advisors.build_note()
        self.assertNotIn('old-man', note)
        self.assertIn('question-monster', note)
        self.assertIn('fast-finder', note)


class Recording(_Store):
    def test_a_row_survives_a_round_trip(self):
        advisors.record('fast-finder', paper='1810.04805v2',
                        asked='where is the starred-variant lesson',
                        verdict='K111')
        rows = advisors.load()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['advisor'], 'fast-finder')
        self.assertEqual(rows[0]['paper'], '1810.04805v2')
        self.assertIn('at', rows[0])

    def test_the_log_is_append_only(self):
        advisors.record('old-man', paper='a', asked='q1', verdict='v1')
        advisors.record('old-man', paper='b', asked='q2', verdict='v2')
        rows = advisors.load()
        self.assertEqual([r['paper'] for r in rows], ['a', 'b'])

    def test_an_unknown_advisor_is_refused(self):
        with self.assertRaises(SystemExit):
            advisors.record('oracle', paper='a')

    def test_a_torn_line_does_not_lose_the_rest(self):
        advisors.record('old-man', paper='a', asked='q', verdict='v')
        with io.open(advisors.STORE, 'a', encoding='utf-8') as fh:
            fh.write('{not json\n')
        advisors.record('referee', paper='b', asked='q', verdict='v')
        rows = advisors.load()
        self.assertEqual([r['advisor'] for r in rows], ['old-man', 'referee'])

    def test_a_consultation_with_no_finding_is_still_recorded(self):
        # The load-bearing case: an advisor that looked and saw nothing has
        # still been consulted, and a log of hits only cannot show that.
        advisors.record('old-man', paper='a', asked='is X absent',
                        verdict='safe as it stands')
        rows = advisors.load()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['verdict'], 'safe as it stands')
        self.assertEqual(advisors.summary()['old-man']['count'], 1)


class RefereeIsNotDoubleCounted(_Store):
    def test_status_separates_being_consulted_from_tallying_runs(self):
        # referee/runs.json holding rows must not read as "consulted", and
        # reporting `never consulted` beside it must not read as a
        # contradiction either.
        lines = '\n'.join(advisors.status_lines())
        runs = advisors._referee_runs()
        if runs:
            self.assertIn('its script has judged', lines)


class NotInstalledIsLouderThanNotConsulted(_Store):
    r"""The state the first ten papers actually ran in.

    The advisors ship at `<skill>/.claude/agents/`, which no runtime searches:
    a runtime looks in `~/.claude/agents/` and `<project>/.claude/agents/`.
    So they were not merely unused, they were uncallable — and from the
    consultation log that is indistinguishable from a caller who never
    bothered. The two need opposite fixes, so they must not read the same.
    """

    def setUp(self):
        _Store.setUp(self)
        self._home = os.path.expanduser
        self._cwd = os.getcwd()
        self._empty = tempfile.mkdtemp(prefix='tb-nohome-')

    def tearDown(self):
        os.path.expanduser = self._home
        os.chdir(self._cwd)
        _Store.tearDown(self)

    def _pretend_not_installed(self):
        os.path.expanduser = lambda p: p.replace('~', self._empty)
        os.chdir(self._empty)

    def test_an_uninstalled_advisor_is_detected(self):
        self._pretend_not_installed()
        for name in advisors.KNOWN:
            self.assertIsNone(advisors.installed_where(name))

    def test_the_build_says_uninstalled_not_merely_unconsulted(self):
        self._pretend_not_installed()
        note = advisors.build_note()
        self.assertIn('NOT INSTALLED', note)
        self.assertNotIn('never consulted', note)

    def test_being_consulted_does_not_hide_being_uninstalled(self):
        # A log with rows must not make an unreachable advisor look fine.
        for name in advisors.KNOWN:
            advisors.record(name, paper='p', asked='q', verdict='v')
        self._pretend_not_installed()
        note = advisors.build_note()
        self.assertIsNotNone(note)
        self.assertIn('NOT INSTALLED', note)

    def test_the_skills_own_copy_does_not_count_as_installed(self):
        r"""Running from the skill directory must not look installed.

        `<cwd>/.claude/agents` is a real place to install, but when cwd IS the
        skill folder it resolves to the shipped copies — the one location no
        runtime searches. Reading those as installed reported the exact broken
        state this detector exists for as healthy, and only a clean-room run
        against the zip exposed it.
        """
        self._pretend_not_installed()
        os.chdir(ROOT)                      # the skill's own directory
        for name in advisors.KNOWN:
            self.assertIsNone(
                advisors.installed_where(name),
                '%s: the skill\'s own .claude/agents was counted' % name)
        self.assertIn('NOT INSTALLED', advisors.build_note())

    def test_status_marks_each_uninstalled_advisor(self):
        self._pretend_not_installed()
        lines = '\n'.join(advisors.status_lines())
        self.assertIn('[NOT INSTALLED]', lines)
        self.assertIn('INSTALL.md', lines)


class InstallDocsNameTheStep(unittest.TestCase):
    def test_install_md_tells_you_to_copy_the_agents_out(self):
        with io.open(os.path.join(ROOT, 'INSTALL.md'), 'r',
                     encoding='utf-8') as fh:
            body = fh.read()
        self.assertIn('.claude/agents', body,
                      'INSTALL.md must say where the advisors have to go; '
                      'omitting it is what made them unreachable')
        self.assertIn('advisors.py status', body)


class EveryAdvisorIsToldToRecord(unittest.TestCase):
    """A store nothing writes to is the state this replaced."""

    def test_each_definition_names_the_record_command(self):
        agents = os.path.join(ROOT, '.claude', 'agents')
        missing = []
        for name in advisors.KNOWN:
            path = os.path.join(agents, '%s.md' % name)
            if not os.path.isfile(path):
                missing.append('%s.md is absent' % name)
                continue
            with io.open(path, 'r', encoding='utf-8') as fh:
                body = fh.read()
            if 'advisors.py record %s' % name not in body:
                missing.append('%s.md never tells it to record' % name)
        self.assertEqual(missing, [], '\n'.join(missing))


if __name__ == '__main__':
    unittest.main()

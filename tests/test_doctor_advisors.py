# -*- coding: utf-8 -*-
r"""The install step that can be skipped without anything saying so.

The four advisor definitions ship at `<skill>/.claude/agents/`, and no runtime
searches that path — sub-agents are found in `~/.claude/agents/` and in a
project's own `.claude/agents/`. Left where they ship they cannot be called at
all. `install_advisors.py` records what that cost: ten papers were translated
in exactly that state, with nothing anywhere reporting it.

`SKILL.md` names these four sixteen times and tells the orchestrator when to
call each, so the skill's own instructions depend on a step the installer can
silently miss. `doctor.py` is the tool whose whole job is "what is present",
and it did not look here.

RECOMMENDED, not REQUIRED, on purpose: the pipeline still produces a book
without them. What it loses is the ability to get better at producing the next
one, which is a different kind of missing and should not fail `--strict`
alongside a missing pandoc.
"""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import doctor  # noqa: E402

SHIPPED = ROOT / ".claude" / "agents"


class TheAdvisorCheckNoticesASkippedInstall(unittest.TestCase):
    def fake_home(self):
        """A home directory this test owns, restored afterwards."""
        home = tempfile.mkdtemp(prefix="doctor-home")
        self.addCleanup(shutil.rmtree, home, True)
        for var in ("HOME", "USERPROFILE"):
            self.addCleanup(os.environ.pop, var, None)
            if var in os.environ:
                self.addCleanup(os.environ.__setitem__, var, os.environ[var])
            os.environ[var] = home
        return home

    def install_into(self, home, names):
        dest = os.path.join(home, ".claude", "agents")
        os.makedirs(dest)
        for name in names:
            shutil.copy2(str(SHIPPED / name), os.path.join(dest, name))

    def shipped_names(self):
        return sorted(p.name for p in SHIPPED.glob("*.md"))

    def test_the_skill_ships_four_advisors(self):
        # If this ever changes, the counts in the messages below change with it.
        self.assertEqual(len(self.shipped_names()), 4, self.shipped_names())

    def test_absent_when_the_step_was_skipped(self):
        self.fake_home()
        ok, detail, why = doctor.check_advisors()
        self.assertFalse(ok)
        self.assertIn("0 of 4", detail)
        self.assertIn("install_advisors", why)

    def test_present_once_they_are_copied(self):
        home = self.fake_home()
        self.install_into(home, self.shipped_names())
        ok, detail, _why = doctor.check_advisors()
        self.assertTrue(ok)
        self.assertIn("4 of 4", detail)

    def test_a_partial_install_is_not_a_pass(self):
        # Half the advisors is not "the growth loop works" — the caller who
        # reaches for question-monster and finds nothing gets no warning.
        home = self.fake_home()
        self.install_into(home, self.shipped_names()[:2])
        ok, detail, _why = doctor.check_advisors()
        self.assertFalse(ok)
        self.assertIn("2 of 4", detail)

    def test_a_brief_edited_after_it_was_installed_is_reported(self):
        # The state the check could not see. Presence was all it asked, so
        # four copies a week old passed as "4 of 4 installed" while the
        # briefs beside them were edited four times — a referee brief
        # corrected on the 6th never reached a session, and the installer
        # refuses to overwrite what it did not put there, so it was never
        # going to say so either.
        home = self.fake_home()
        names = self.shipped_names()
        self.install_into(home, names)
        stale = os.path.join(home, ".claude", "agents", names[0])
        with open(stale, "a", encoding="utf-8") as fh:
            fh.write("\nan edit the shipped brief does not have\n")
        ok, detail, _why = doctor.check_advisors()
        self.assertFalse(ok, detail)
        self.assertIn("out of date", detail)
        self.assertIn(names[0][:-3], detail)

    def test_a_current_install_says_so_rather_than_only_counting(self):
        home = self.fake_home()
        self.install_into(home, self.shipped_names())
        ok, detail, _why = doctor.check_advisors()
        self.assertTrue(ok, detail)
        self.assertIn("current", detail)

    def test_the_remedy_names_the_flag_a_stale_copy_needs(self):
        # Told only to run install_advisors.py, a reader runs it, sees it
        # decline every file, and is no better off.
        self.fake_home()
        _ok, _detail, why = doctor.check_advisors()
        self.assertIn("--force", why)

    def test_it_is_recommended_rather_than_required(self):
        source = (SCRIPT_DIR / "doctor.py").read_text(encoding="utf-8")
        self.assertIn("(RECOMMENDED, 'advisor sub-agents'", source)
        self.assertNotIn("(REQUIRED, 'advisor sub-agents'", source)


class TheCommandIsDeliberatelyNotInstalled(unittest.TestCase):
    r"""A decision that looks exactly like an oversight from outside.

    The skill ships `.claude/commands/release.md` and the installer does
    not copy it, while it does copy four advisors from the directory next
    door. Nothing said which of those was intended, so the question had to
    be asked out loud once; this makes sure it is answered in the file
    where it comes up rather than asked again.

    The asymmetry is who calls the thing. `SKILL.md` reaches for the
    advisors sixteen times during a run, so one missing breaks the skill
    silently. Nothing invokes `/release`; that flow is followed by reading
    it. And `release` is a name every project wants -- installed globally
    it would hand this fork's tagging rules to unrelated repositories, and
    lose quietly to the next tool shipping the same name.
    """

    def installer_source(self):
        return (SCRIPT_DIR / "install_advisors.py").read_text(
            encoding="utf-8")

    def test_the_command_ships_with_the_skill(self):
        self.assertTrue((ROOT / ".claude" / "commands" / "release.md")
                        .is_file())

    def test_the_installer_copies_agents_and_not_commands(self):
        source = self.installer_source()
        self.assertIn("agents", source)
        # Only as the explanation below, never as a directory it walks.
        self.assertNotIn("'commands'", source)
        self.assertNotIn('"commands"', source)

    def test_the_reason_is_written_where_the_question_arises(self):
        """Someone wondering why their command was not installed opens the
        installer. A decision recorded anywhere else is one they will not
        find, and they will 'fix' it."""
        head = self.installer_source().split('"""')[1]
        self.assertIn("release.md", head)
        for word in ("decision", "collide"):
            self.assertIn(word, head)


if __name__ == "__main__":
    unittest.main()

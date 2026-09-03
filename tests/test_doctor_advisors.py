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

    def test_it_is_recommended_rather_than_required(self):
        source = (SCRIPT_DIR / "doctor.py").read_text(encoding="utf-8")
        self.assertIn("(RECOMMENDED, 'advisor sub-agents'", source)
        self.assertNotIn("(REQUIRED, 'advisor sub-agents'", source)


if __name__ == "__main__":
    unittest.main()

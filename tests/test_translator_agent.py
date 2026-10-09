# -*- coding: utf-8 -*-
r"""Chunks go to an agent with a short tool list, wherever the skill is installed.

Measured on one paper: a general-purpose sub-agent started each chunk with
about 27,000 tokens of context before reading a word, because it carries every
tool in the session, and it pays that again on every turn. The advisors, with
five tools each, started at about 6,000, and the same chunk translated both
ways cost the translator under half the tokens. One table-word agent also
spent eight of its 32 turns reading the pipeline's own source. `translator` is
the dispatched worker with a short tool list and a brief that forbids that.

It only helps if the runtime can find it. As a plain skill the definitions are
copied to `~/.claude/agents/` by `install_advisors.py`; as a plugin they have
to sit in the plugin's `agents/` folder, because a directory install never
runs that script.
"""
import filecmp
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
TOOLS_DIR = ROOT / "tools"
for d in (SCRIPT_DIR, TOOLS_DIR):
    if str(d) not in sys.path:
        sys.path.insert(0, str(d))

import doctor  # noqa: E402

SHIPPED = ROOT / ".claude" / "agents" / "translator.md"


class TheDefinition(unittest.TestCase):
    def setUp(self):
        self.text = SHIPPED.read_text(encoding="utf-8")

    def test_its_tool_list_is_short(self):
        tools = next(line for line in self.text.splitlines()
                     if line.startswith("tools:"))
        names = [t.strip() for t in tools.split(":", 1)[1].split(",")]
        self.assertLessEqual(len(names), 6, names)
        self.assertNotIn("Agent", names)

    def test_it_forbids_reading_the_skill_and_shell_written_files(self):
        self.assertIn("Do not read the skill", self.text)
        self.assertIn("Write tool", self.text)


class TheSkillDispatchesToIt(unittest.TestCase):
    def setUp(self):
        self.skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")

    def test_chunks_and_tables_name_both_forms(self):
        step4 = self.skill[self.skill.index("### 4. Parallel Translation"):
                           self.skill.index("### 4.4.")]
        self.assertIn("`translator`", step4)
        self.assertIn("`translate-book-arxiv:translator`", step4)
        step46 = self.skill[self.skill.index("### 4.6."):
                            self.skill.index("### 4.7.")]
        self.assertIn("`translator`", step46)


class DoctorFindsItWhereverItIsInstalled(unittest.TestCase):
    def fake(self, plugin):
        root = tempfile.mkdtemp(prefix="tb-root")
        home = tempfile.mkdtemp(prefix="tb-home")
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        self.addCleanup(shutil.rmtree, home, ignore_errors=True)
        if plugin:
            os.makedirs(os.path.join(root, "agents"))
            shutil.copyfile(SHIPPED, os.path.join(root, "agents",
                                                  "translator.md"))
        patches = [mock.patch.object(doctor, "PLUGIN_AGENTS",
                                     os.path.join(root, "agents")),
                   mock.patch.dict(os.environ, {"HOME": home,
                                                "USERPROFILE": home})]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_absent_when_nothing_installed_it(self):
        self.fake(plugin=False)
        ok, detail, _why = doctor.check_translator()
        self.assertFalse(ok)
        self.assertEqual(detail, "not installed")

    def test_present_in_a_plugin_install(self):
        self.fake(plugin=True)
        ok, detail, _why = doctor.check_translator()
        self.assertTrue(ok, detail)


@unittest.skipUnless(TOOLS_DIR.is_dir(), "the plugin folder ships no tools/")
class ThePluginBranchShipsTheAgents(unittest.TestCase):
    def test_each_definition_is_copied_to_agents(self):
        import build_plugin_branch
        entries = [
            ("100644", "a" * 40, 10, ".claude/agents/translator.md"),
            ("100644", "b" * 40, 10, ".claude/agents/old-man.md"),
            ("100644", "c" * 40, 10, ".claude/commands/release.md"),
            ("100644", "d" * 40, 10, "SKILL.md"),
        ]
        out = build_plugin_branch.plugin_agents(entries)
        self.assertEqual(sorted(e[3] for e in out),
                         ["agents/old-man.md", "agents/translator.md"])
        self.assertEqual({e[1] for e in out}, {"a" * 40, "b" * 40})


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
r"""The plugin's SKILL.md pre-approves its own scripts, not Python as a whole.

Anthropic's directory held v0.4.6 and v0.4.7 for "pre-approves broad shell
access in allowed-tools": `Bash(python *)` lets the skill run any Python at
all without a prompt. Its reviewer asked for one rule per bundled script,
written with `${CLAUDE_PLUGIN_ROOT}`. Main keeps `{baseDir}` and the broad
rules for the runtimes that know no such variable, so the plugin branch's
builder rewrites SKILL.md, and these tests hold it to that.

Checked by hand on 2026-10-09 with `claude -p --plugin-dir` and only the
Skill tool allowed: `python <root>/scripts/doctor.py --strict` ran without a
prompt, and the same command with `; echo` appended was refused.
"""
import os
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

# These check the builder, and the plugin folder it writes ships no tools/.
HAVE_TOOLS = (TOOLS_DIR / "build_plugin_branch.py").is_file()
NO_TOOLS = "the plugin folder ships no tools/"
if HAVE_TOOLS:
    import build_plugin_branch as bpb  # noqa: E402


def allowed(text):
    line = re.search(r"^allowed-tools:[ \t]*(.+)$", text, re.M).group(1)
    return [t.strip() for t in line.split(",")]


@unittest.skipUnless(HAVE_TOOLS, NO_TOOLS)
class ThePluginSkill(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        cls.plugin = bpb.plugin_skill(cls.main)

    def test_no_rule_pre_approves_a_whole_command(self):
        for tool in allowed(self.plugin):
            if tool.startswith("Bash("):
                self.assertRegex(
                    tool, r"^Bash\(python3? \$\{CLAUDE_PLUGIN_ROOT\}/[\w./-]+\.py:\*\)$")

    def test_every_script_the_skill_runs_is_allowed_under_both_names(self):
        rules = set(allowed(self.plugin))
        calls = set(bpb.SCRIPT_CALL.findall(self.plugin))
        self.assertIn("scripts/doctor.py", calls)
        for script in calls:
            for py in ("python", "python3"):
                self.assertIn("Bash(%s ${CLAUDE_PLUGIN_ROOT}/%s:*)" % (py, script),
                              rules)

    def test_the_other_tools_are_kept(self):
        kept = [t for t in allowed(self.main) if not t.startswith("Bash(")]
        self.assertEqual(kept,
                         [t for t in allowed(self.plugin) if not t.startswith("Bash(")])

    def test_the_text_names_the_same_paths_the_rules_match(self):
        self.assertNotIn("{baseDir}", self.plugin)
        body = self.plugin.replace(allowed_line(self.plugin), "")
        self.assertEqual(self.main.count("{baseDir}"),
                         body.count("${CLAUDE_PLUGIN_ROOT}/"))

    def test_only_the_allowed_tools_line_changes_beyond_the_paths(self):
        a = self.main.replace("{baseDir}", "${CLAUDE_PLUGIN_ROOT}").splitlines()
        b = self.plugin.splitlines()
        self.assertEqual(len(a), len(b))
        changed = [x for x, y in zip(a, b) if x != y]
        self.assertEqual(len(changed), 1)
        self.assertTrue(changed[0].startswith("allowed-tools:"))


def allowed_line(text):
    return re.search(r"^allowed-tools:.*$", text, re.M).group(0)


@unittest.skipUnless(HAVE_TOOLS, NO_TOOLS)
class ItRefusesWhatItCannotNarrow(unittest.TestCase):
    def skill(self, tools, body="Run `python {baseDir}/scripts/doctor.py`.\n"):
        return "---\nname: x\nallowed-tools: %s\n---\n%s" % (tools, body)

    def test_an_unknown_shell_rule(self):
        with self.assertRaises(SystemExit):
            bpb.plugin_skill(self.skill("Read, Bash(node *)"))

    def test_a_path_that_is_not_a_python_call(self):
        with self.assertRaises(SystemExit):
            bpb.plugin_skill(self.skill("Read, Bash(python *)",
                                        "Open {baseDir}/README.md.\n"))

    def test_a_skill_without_a_broad_rule_still_gets_its_scripts(self):
        out = bpb.plugin_skill(self.skill("Read"))
        self.assertIn("Bash(python ${CLAUDE_PLUGIN_ROOT}/scripts/doctor.py:*)",
                      allowed(out))


@unittest.skipUnless(HAVE_TOOLS, NO_TOOLS)
class NoShippedFileIsTooBigToRead(unittest.TestCase):
    """The directory's validator reads every text file up to 256 KiB, and
    holds a release for a human reviewer when one is bigger. merge_and_build.py
    reached 393 KB and held v0.4.6 and v0.4.7 that way, until it was split
    into latex_cleanup.py, numbering.py, latex_tables.py and build_common.py.
    """

    def test_every_shipped_text_file_is_under_the_limit(self):
        big = []
        for folder, dirs, files in os.walk(ROOT):
            dirs[:] = [d for d in dirs if d not in (".git", "__pycache__")]
            for name in files:
                path = Path(folder) / name
                rel = path.relative_to(ROOT).as_posix()
                if bpb.is_excluded(rel) or path.suffix.lower() in bpb.IMAGE_OR_FONT:
                    continue
                if path.stat().st_size > bpb.REVIEW_TEXT_BYTES:
                    big.append("%s (%d bytes)" % (rel, path.stat().st_size))
        self.assertEqual(big, [], "the directory would hold a release for: %s"
                         % big)


if __name__ == "__main__":
    unittest.main()

"""The findings log only accumulates if its own rules are enforced.

A log that drifts out of its index, reuses numbers, or stops being pointed at
from the workflow stops being read — and an unread log is worse than none,
because it looks like the knowledge is captured.
"""
import re
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
KNOWLEDGE = REPO / "KNOWLEDGE.md"
SKILL = REPO / "SKILL.md"

ENTRY_RE = re.compile(r"^### K(\d+)\s*$", re.MULTILINE)
INDEX_LINK_RE = re.compile(r"\[K(\d+)\]\(#k(\d+)\)")


class KnowledgeFileTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(KNOWLEDGE.is_file(), "KNOWLEDGE.md is missing")
        self.text = KNOWLEDGE.read_text(encoding="utf-8")
        self.numbers = [int(n) for n in ENTRY_RE.findall(self.text)]

    def test_has_entries(self):
        self.assertGreater(len(self.numbers), 0, "no ### K<n> entries found")

    def test_entry_numbers_are_unique(self):
        """Rule 2: numbers are never reused, even when an entry is superseded."""
        dupes = {n for n in self.numbers if self.numbers.count(n) > 1}
        self.assertFalse(dupes, f"duplicate entry numbers: {sorted(dupes)}")

    def test_every_entry_is_reachable_from_the_symptom_index(self):
        """Rule 1: an entry nobody can find is not knowledge."""
        indexed = {int(a) for a, _b in INDEX_LINK_RE.findall(self.text)}
        missing = sorted(set(self.numbers) - indexed)
        self.assertFalse(
            missing,
            f"K{missing} have no row in the symptom index — add one, "
            f"or they will never be found when it matters")

    def test_index_links_point_at_entries_that_exist(self):
        known = set(self.numbers)
        for label, anchor in INDEX_LINK_RE.findall(self.text):
            self.assertEqual(label, anchor,
                             f"index link [K{label}](#k{anchor}) is inconsistent")
            self.assertIn(int(label), known,
                          f"symptom index points at K{label}, which does not exist")

    def test_entries_stay_short(self):
        """Rule 4: past ~10 lines a finding wants to be code, not prose."""
        blocks = re.split(r"^### K\d+\s*$", self.text, flags=re.MULTILINE)[1:]
        for number, block in zip(self.numbers, blocks):
            # Stop at the next entry OR the next top-level section: the last
            # entry is followed by ## Environment notes, not by another ###.
            body = re.split(r"^#{2,3} ", block, flags=re.MULTILINE)[0]
            lines = body.strip().splitlines()
            self.assertLessEqual(
                len(lines), 14,
                f"K{number} is {len(lines)} lines — compress it, or make it code")

    def test_maintenance_protocol_is_present(self):
        for heading in ("## Symptom index", "## The diagnostic chain",
                        "## Maintenance protocol", "## Environment notes"):
            self.assertIn(heading, self.text, f"{heading} section is missing")


class SubAgentGateTests(unittest.TestCase):
    """The gate has to live in the workflow, not in someone's memory."""

    def setUp(self):
        self.skill = SKILL.read_text(encoding="utf-8")

    def test_the_gate_is_a_numbered_step(self):
        self.assertIn("### 4.4. Check the Work Before You Record It",
                      self.skill)

    def test_the_gate_runs_before_the_chunk_is_recorded(self):
        gate = self.skill.index("verify_chunk.py")
        record = self.skill.index("run_state.py record")
        self.assertLess(gate, record,
                        "a chunk must be checked before it is recorded")

    def test_the_whole_book_is_checked_before_the_merge(self):
        step5 = self.skill.index("### 5. Verify Completeness and Retry")
        self.assertIn("verify_chunk.py", self.skill[step5:step5 + 3000])

    def test_a_sub_agent_report_is_not_treated_as_evidence(self):
        self.assertIn("is not evidence", self.skill)

class WorkflowWiringTests(unittest.TestCase):
    """The log accumulates because it is a workflow step, not a chore."""

    def setUp(self):
        self.skill = SKILL.read_text(encoding="utf-8")

    def test_skill_points_at_the_log_before_the_workflow(self):
        self.assertIn("KNOWLEDGE.md", self.skill)
        self.assertLess(self.skill.index("KNOWLEDGE.md"),
                        self.skill.index("### 1. Collect Parameters"),
                        "the pointer must come before the workflow, not after it")

    def test_recording_is_a_numbered_step(self):
        self.assertIn("### 9. Record What You Learned", self.skill)

    def test_step_9_names_the_verification_gate(self):
        step9 = self.skill[self.skill.index("### 9. Record What You Learned"):]
        for command in ("unittest discover", "layout_probe.py --strict",
                        "--stress"):
            self.assertIn(command, step9, f"Step 9 does not name {command!r}")


if __name__ == "__main__":
    unittest.main()

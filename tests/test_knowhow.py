"""The practice log only accumulates if its own rules are enforced.

KNOWHOW.md and KNOWLEDGE.md answer different questions — *how should I
proceed?* and *why did this break?* — and the split only survives if it is
checked. Two files that drift into each other are one file with a redundant
copy, and then neither gets read.
"""
import re
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
KNOWHOW = REPO / "KNOWHOW.md"
KNOWLEDGE = REPO / "KNOWLEDGE.md"
SKILL = REPO / "SKILL.md"

ENTRY_RE = re.compile(r"^### H(\d+)\s*$", re.MULTILINE)
INDEX_LINK_RE = re.compile(r"\[H(\d+)\]\(#h(\d+)\)")


class KnowhowFileTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(KNOWHOW.is_file(), "KNOWHOW.md is missing")
        self.text = KNOWHOW.read_text(encoding="utf-8")
        self.numbers = [int(n) for n in ENTRY_RE.findall(self.text)]

    def test_has_entries(self):
        self.assertGreater(len(self.numbers), 0, "no ### H<n> entries found")

    def test_entry_numbers_are_unique(self):
        dupes = {n for n in self.numbers if self.numbers.count(n) > 1}
        self.assertFalse(dupes, f"duplicate entry numbers: {sorted(dupes)}")

    def test_every_entry_is_reachable_from_the_task_index(self):
        """Rule 1: an entry nobody can find is not knowhow."""
        indexed = {int(a) for a, _b in INDEX_LINK_RE.findall(self.text)}
        missing = sorted(set(self.numbers) - indexed)
        self.assertFalse(
            missing,
            f"H{missing} have no row in an index — add one, or they will "
            f"never be found when it matters")

    def test_index_links_point_at_entries_that_exist(self):
        known = set(self.numbers)
        for label, anchor in INDEX_LINK_RE.findall(self.text):
            self.assertEqual(label, anchor,
                             f"index link [H{label}](#h{anchor}) is inconsistent")
            self.assertIn(int(label), known,
                          f"an index points at H{label}, which does not exist")

    def test_every_entry_carries_the_cost_of_skipping_it(self):
        """Rule 3: a practice with no incident behind it is a preference."""
        blocks = re.split(r"^### H\d+\s*$", self.text, flags=re.MULTILINE)[1:]
        for number, block in zip(self.numbers, blocks):
            body = re.split(r"^#{2,3} ", block, flags=re.MULTILINE)[0]
            self.assertIn(
                "*Cost when skipped:", body,
                f"H{number} has no cost line — say what it actually cost, "
                f"or it reads as generic advice and gets skimmed past")

    def test_entries_stay_short(self):
        """Rule 4: past ~14 lines a practice wants to be a checklist."""
        blocks = re.split(r"^### H\d+\s*$", self.text, flags=re.MULTILINE)[1:]
        for number, block in zip(self.numbers, blocks):
            body = re.split(r"^#{2,3} ", block, flags=re.MULTILINE)[0]
            lines = body.strip().splitlines()
            self.assertLessEqual(
                len(lines), 14,
                f"H{number} is {len(lines)} lines — compress it")

    def test_the_sections_that_make_it_navigable_are_present(self):
        for heading in ("## Which document, for which task", "## Task index",
                        "## Entries", "## Maintenance protocol"):
            self.assertIn(heading, self.text, f"{heading} is missing")


class SeparationOfConcernsTests(unittest.TestCase):
    """The two logs answer different questions. Keep them answering them."""

    def setUp(self):
        self.knowhow = KNOWHOW.read_text(encoding="utf-8")
        self.knowledge = KNOWLEDGE.read_text(encoding="utf-8")

    def test_knowhow_states_the_split(self):
        self.assertIn("KNOWLEDGE.md", self.knowhow,
                      "KNOWHOW.md must say what it is NOT, or the two drift")

    def test_the_numbering_schemes_do_not_collide(self):
        self.assertFalse(re.search(r"^### K\d+\s*$", self.knowhow, re.MULTILINE),
                         "KNOWHOW.md uses H<n>; a K<n> entry belongs in "
                         "KNOWLEDGE.md")
        self.assertFalse(re.search(r"^### H\d+\s*$", self.knowledge, re.MULTILINE),
                         "KNOWLEDGE.md uses K<n>; an H<n> entry belongs in "
                         "KNOWHOW.md")

    def test_both_files_have_a_maintenance_protocol(self):
        for name, text in (("KNOWHOW.md", self.knowhow),
                           ("KNOWLEDGE.md", self.knowledge)):
            self.assertIn("## Maintenance protocol", text,
                          f"{name} has no protocol, so nothing tells anyone "
                          f"when to append to it")


class WorkflowWiringTests(unittest.TestCase):
    """A log the workflow never points at is a log nobody opens."""

    def setUp(self):
        self.skill = SKILL.read_text(encoding="utf-8")

    def test_the_skill_points_at_knowhow(self):
        self.assertIn("KNOWHOW.md", self.skill,
                      "nothing in SKILL.md sends the reader to KNOWHOW.md")

    def test_the_skill_says_which_file_takes_which_finding(self):
        at = self.skill.index("KNOWHOW.md")
        window = self.skill[max(0, at - 1200):at + 1200]
        self.assertIn("KNOWLEDGE.md", window,
                      "SKILL.md mentions KNOWHOW.md without saying how it "
                      "differs from KNOWLEDGE.md — the split has to be stated "
                      "where the choice is made")


class DispatchWiringTests(unittest.TestCase):
    """Chunks are dispatched as a queue, and handled in a fixed order."""

    def setUp(self):
        self.skill = SKILL.read_text(encoding="utf-8")

    DISPATCH = "**Dispatch as a work queue"

    def test_dispatch_is_a_work_queue(self):
        self.assertIn(self.DISPATCH, self.skill,
                      "Step 4 must dispatch as a queue")

    def test_the_batch_barrier_has_not_come_back(self):
        # Measured at 23% / 16% / 9% of wall-clock across three papers.
        for phrase in ("Wait for the current batch to complete",
                       "wait for the current batch to complete"):
            self.assertNotIn(phrase, self.skill,
                             "the batch barrier is back: it waits for the "
                             "slowest chunk in every group and buys nothing "
                             "the queue does not also give")

    def test_a_chunk_is_recorded_before_its_meta_is_merged(self):
        """run_state files which glossary terms the chunk used."""
        record = self.skill.index("run_state.py record")
        merge = self.skill.index("merge_meta.py prepare-merge")
        self.assertLess(record, merge,
                        "merging before recording files the wrong glossary "
                        "version against the chunk")

    def test_the_reason_the_queue_is_safe_is_written_down(self):
        # It is safe because the term table is built at dispatch time, so an
        # enriched glossary reaches the next chunk without a barrier.
        at = self.skill.index(self.DISPATCH)
        window = self.skill[at:at + 1400]
        self.assertIn("DISPATCH time", window,
                      "say why dropping the barrier is safe, or the next "
                      "person restores it")


if __name__ == "__main__":
    unittest.main()

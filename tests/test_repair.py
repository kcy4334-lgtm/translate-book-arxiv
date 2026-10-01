r"""Fixing a finished book in place, instead of re-translating it.

Re-converting moves every chunk boundary and renumbers every `⟦M####⟧`, so
nearly every hash changes and the planner asks to translate the lot again --
throwing away the review already done on the prose. These are the repairs that
avoid that, and the reasons they exist.
"""

import contextlib
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import repair  # noqa: E402

BS = chr(92)
NL = "\n"


class ColumnSpecRepairTests(unittest.TestCase):
    """Reading `{l l l*{9}{r}}` pandoc expands the repeat; writing the raw
    block back out it emits the ORIGINAL spec and the expansion together.
    Twenty-one columns where the paper has twelve, so every row printed with
    nine empty cells after it."""

    def test_the_repeat_goes_and_the_expansion_stays(self):
        self.assertEqual(repair.undouble_spec("l l l*{9}{r}rrrrrrrrr"),
                         "l l lrrrrrrrrr")

    def test_a_spec_that_was_never_doubled_is_untouched(self):
        for spec in ("l l lrrrrrrrrr", "lcr", "l@{} l lcc"):
            self.assertEqual(repair.undouble_spec(spec), spec)

    def test_a_repeat_with_no_expansion_after_it_is_left_alone(self):
        """That is a spec pandoc has not chewed yet; expanding is not our job
        here, and removing it would lose nine columns."""
        self.assertEqual(repair.undouble_spec("l l l*{9}{r}"), "l l l*{9}{r}")

    def test_two_doubled_repeats_in_one_spec(self):
        self.assertEqual(repair.undouble_spec("*{2}{c}cc*{3}{r}rrr"), "ccrrr")

    def test_repair_reports_what_it_did(self):
        latex = (BS + "begin{tabular}{l l l*{9}{r}rrrrrrrrr}" + NL
                 + "a & b" + BS + BS + NL + BS + "end{tabular}")
        fixed, notes = repair.repair_latex(latex)
        self.assertIn("column spec", notes)
        self.assertIn("{l l lrrrrrrrrr}", fixed)


class BoxedLabelRepairTests(unittest.TestCase):
    """pandoc drops \\rotatebox and \\multirow whole, argument included, so the
    label a narrow group column carries disappears and the rows sit there with
    nothing saying which group they belong to."""

    def test_a_rotated_label_is_lifted_out(self):
        latex = (BS + "begin{tabular}{ll}" + NL
                 + BS + "rotatebox[origin=c]{90}{" + BS + "textsc{4-bit}} & x"
                 + NL + BS + "end{tabular}")
        fixed, notes = repair.repair_latex(latex)
        self.assertIn(BS + "textsc{4-bit}", fixed)
        self.assertNotIn("rotatebox", fixed)
        self.assertTrue(any("label" in n for n in notes))

    def test_a_table_needing_nothing_is_returned_unchanged(self):
        latex = BS + "begin{tabular}{lc}" + NL + "a & b" + NL + BS + "end{tabular}"
        fixed, notes = repair.repair_latex(latex)
        self.assertEqual(fixed, latex)
        self.assertEqual(notes, [])


class RehashTests(unittest.TestCase):
    """A chunk's source hash is what decides whether it needs translating
    again. Repair a chunk in place and forget this and the next run quietly
    re-translates it -- paying again for text that was already right, and
    discarding any review done on it."""

    def setUp(self):
        self.temp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.temp, True)
        Path(os.path.join(self.temp, "chunk0001.md")).write_text(
            "edited by hand", encoding="utf-8")
        Path(os.path.join(self.temp, "chunk0002.md")).write_text(
            "untouched", encoding="utf-8")
        manifest = {"chunk_count": 2, "chunks": [
            {"id": "chunk0001", "source_file": "chunk0001.md",
             "source_hash": "stale", "output_file": "output_chunk0001.md"},
            {"id": "chunk0002", "source_file": "chunk0002.md",
             "source_hash": hashlib.sha256(b"untouched").hexdigest(),
             "output_file": "output_chunk0002.md"},
        ]}
        Path(os.path.join(self.temp, "manifest.json")).write_text(
            json.dumps(manifest), encoding="utf-8")

    def manifest(self):
        with io.open(os.path.join(self.temp, "manifest.json"),
                     encoding="utf-8") as fh:
            return json.load(fh)

    def rehash(self):
        with contextlib.redirect_stdout(io.StringIO()):
            repair.cmd_rehash([self.temp], False)

    def test_a_stale_hash_is_refreshed(self):
        self.rehash()
        entry = self.manifest()["chunks"][0]
        self.assertEqual(entry["source_hash"],
                         hashlib.sha256(b"edited by hand").hexdigest())

    def test_an_unchanged_chunk_keeps_its_hash(self):
        before = self.manifest()["chunks"][1]["source_hash"]
        self.rehash()
        self.assertEqual(self.manifest()["chunks"][1]["source_hash"], before)

    def test_rehashing_twice_changes_nothing(self):
        self.rehash()
        once = self.manifest()
        self.rehash()
        self.assertEqual(self.manifest(), once)


if __name__ == "__main__":
    unittest.main()

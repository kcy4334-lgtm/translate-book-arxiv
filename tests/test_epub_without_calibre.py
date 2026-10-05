# -*- coding: utf-8 -*-
r"""Calibre is needed for the EPUB, not for the book.

On the arXiv path Calibre writes the EPUB and nothing else: Pandoc writes the
DOCX and headless Chromium prints the PDF. `doctor.py` listed it as REQUIRED,
and once SKILL.md began stopping on any required component, a machine without
Calibre could not translate an arXiv paper at all, though its PDF would have
come out fine. The build now skips the EPUB when Calibre is absent, and the
check says what is lost instead of refusing.

A PDF, DOCX or EPUB input still needs Calibre, and `convert.py` stops before
anything is translated when it is missing, so nothing late is hidden by this.
"""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import merge_and_build  # noqa: E402


class TheBuildSkipsOnlyTheEpub(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="no-calibre")
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        with open(os.path.join(self.temp_dir, "book_doc.html"), "w",
                  encoding="utf-8") as f:
            f.write("<html><body><p>x</p></body></html>")

    def fake_format(self, html_file, temp_dir, ext, *args, **kwargs):
        self.asked.append(ext)
        out = os.path.join(temp_dir, "book" + ext)
        with open(out, "wb") as f:
            f.write(b"x")
        return out

    def build(self, calibre):
        self.asked = []
        with mock.patch.object(merge_and_build, "calibre_available",
                               return_value=calibre), \
             mock.patch.object(merge_and_build, "resolve_pandoc",
                               return_value=None), \
             mock.patch.object(merge_and_build, "generate_format",
                               side_effect=self.fake_format):
            return merge_and_build.generate_formats(self.temp_dir, "ko")

    def test_without_calibre_the_build_still_succeeds(self):
        self.assertTrue(self.build(calibre=False))

    def test_without_calibre_no_epub_is_attempted(self):
        self.build(calibre=False)
        self.assertNotIn(".epub", self.asked)
        self.assertIn(".pdf", self.asked)

    def test_with_calibre_the_epub_is_built(self):
        self.assertTrue(self.build(calibre=True))
        self.assertIn(".epub", self.asked)


class TheCheckDoesNotRefuseAnArxivPaper(unittest.TestCase):
    def test_calibre_is_recommended_rather_than_required(self):
        source = (SCRIPT_DIR / "doctor.py").read_text(encoding="utf-8")
        self.assertIn("(RECOMMENDED, 'Calibre ebook-convert'", source)
        self.assertNotIn("(REQUIRED, 'Calibre ebook-convert'", source)

    def test_the_skill_says_what_to_do_without_calibre(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        step0 = skill[skill.index("### 0. Check the Machine"):
                      skill.index("### 1. Collect Parameters")]
        self.assertIn("Calibre", step0)
        self.assertIn("skips the EPUB", step0)


if __name__ == "__main__":
    unittest.main()

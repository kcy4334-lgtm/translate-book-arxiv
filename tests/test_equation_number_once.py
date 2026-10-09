# -*- coding: utf-8 -*-
r"""An equation number prints once, in a paper with no LaTeX table too.

The DOCX copy (prepared.md) carries each number inside its formula, because
pandoc builds book.docx from markdown and never sees the HTML. The HTML path
numbers equations on its own. A paper with tables built its HTML from
pandoc_input.md; a paper without them was built from prepared.md, so the
number arrived twice -- every equation in VAE's PDF, EPUB and HTML read
`... (1)   (1)`.
"""
import contextlib
import io
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import layout  # noqa: E402
import merge_and_build as mb  # noqa: E402

BS = '\\'
FLAT = (BS + 'section{Method}' + '\n'
        + BS + 'begin{equation}' + '\n' + 'a = b' + '\n'
        + BS + 'end{equation}' + '\n')
MD = ('# 방법\n\n식은 다음과 같다.\n\n$$' + BS + 'begin{equation}\na = b\n'
      + BS + 'end{equation}$$\n\n끝.\n')


@unittest.skipUnless(mb.resolve_pandoc(), 'needs pandoc')
class EquationNumberOnce(unittest.TestCase):

    def test_a_table_free_paper_numbers_each_equation_once(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        os.makedirs(os.path.join(d, 'images'))
        for name, text in (('output.md', MD), ('flat.tex', FLAT),
                           ('config.txt', 'output_lang=ko\n')):
            with open(os.path.join(d, name), 'w', encoding='utf-8') as fh:
                fh.write(text)
        with contextlib.redirect_stdout(io.StringIO()):
            ok = mb.convert_md_to_html(d, 'T', layout.get_lang_config('ko'),
                                       force=True)
        self.assertTrue(ok)
        with open(os.path.join(d, 'pandoc_input.md'), encoding='utf-8') as fh:
            html_source = fh.read()
        self.assertNotIn(BS + 'qquad(1)', html_source)
        with open(os.path.join(d, 'prepared.md'), encoding='utf-8') as fh:
            self.assertIn(BS + 'qquad(1)', fh.read(),
                          'the DOCX copy still carries its number')


if __name__ == '__main__':
    unittest.main()

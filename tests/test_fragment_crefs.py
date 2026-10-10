# -*- coding: utf-8 -*-
r"""A `\cref` inside a raw table prints its word and number.

A protected table float never meets `resolve_references`, and pandoc prints
a `\cref` it cannot resolve as the bare key: PaLM's table captions read
"corresponding to [fig:contd_training_results]", fourteen times in all.
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import latex_tables  # noqa: E402
import merge_and_build as mb  # noqa: E402
import numbering  # noqa: E402

FLAT = ('\\begin{document}\n'
        '\\begin{figure}\\includegraphics{a.png}\\caption{A.}\\label{fig:a}'
        '\\end{figure}\n'
        '\\begin{figure}\\includegraphics{b.png}\\caption{B.}\\label{fig:b}'
        '\\end{figure}\n'
        '\\begin{table}\\caption{T.}\\label{tab:t}\\begin{tabular}{c}x'
        '\\end{tabular}\\end{table}\n\\end{document}\n')


class FragmentCrefs(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='tb-cref-')
        with open(os.path.join(self.dir, 'flat.tex'), 'w', encoding='utf-8') as fh:
            fh.write(FLAT)
        self.render = numbering.reference_renderer(
            self.dir, mb.get_lang_config('ko'))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_the_word_and_number_replace_the_key(self):
        out, done, missed = latex_tables.resolve_fragment_crefs(
            'corresponding to \\cref{fig:b}.', self.render)
        self.assertEqual(out, 'corresponding to 그림 2.')
        self.assertEqual((done, missed), (1, []))

    def test_a_list_of_keys_prints_every_number(self):
        out, _done, _missed = latex_tables.resolve_fragment_crefs(
            '\\Cref{fig:a,tab:t}', self.render)
        self.assertEqual(out, '그림 1, 표 1')

    def test_an_unknown_key_stays_visible(self):
        out, done, missed = latex_tables.resolve_fragment_crefs(
            'see \\cref{fig:nowhere}', self.render)
        self.assertEqual(out, 'see \\cref{fig:nowhere}')
        self.assertEqual((done, missed), (0, ['fig:nowhere']))

    def test_a_badge_gloss_is_not_a_reference(self):
        # gpt3: "(Fig. G.12)" in a badge counted as 56 unresolved references.
        md = 'see (fig:b) and **그림 1 (Fig. 1)** caption.'
        out, stats = numbering.resolve_references(md, self.dir,
                                                  mb.get_lang_config('ko'))
        self.assertEqual((stats['xrefs'], stats['xrefs_missed']), (1, 0))
        self.assertIn('**그림 1 (Fig. 1)**', out)

    def test_without_a_source_nothing_resolves(self):
        render = numbering.reference_renderer(None)
        self.assertIsNone(render('fig:a'))


if __name__ == '__main__':
    unittest.main()

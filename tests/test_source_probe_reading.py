# -*- coding: utf-8 -*-
r"""How source_probe reads PaLM's original, where every number was right.

Seven false failures on a correct book: a probe reading the N of a citation,
a footnote's text and a hyphenated "Sec- tion" as reference numbers, and two
toxicity scores as equation numbers.
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import source_probe as sp


def references(tex, printed, numbers):
    with mock.patch.object(sp.mb, 'build_label_numbers',
                           return_value=dict(numbers)), \
            mock.patch.object(sp.mb, 'build_float_numbers', return_value={}):
        return sp.check_references(None, tex, printed)


class References(unittest.TestCase):

    def test_a_citation_before_a_cref_is_not_its_number(self):
        tex = ('We use Adversarial NLI~\\citep{nie}.\n\n'
               '\\cref{tab:main} includes the results for the large model.')
        printed = ('We use Adversarial NLI (Nie et al., 2019) Table 1 '
                   'includes the results for the large model.')
        _a, disagree, _s, problems = references(tex, printed, {'tab:main': '1'})
        self.assertEqual((disagree, problems), (0, []))

    def test_a_hyphenated_word_still_reads(self):
        tex = 'Results are in the code completion tasks~(\\cref{sec:tasks}), and more.'
        printed = 'Results are in the code completion tasks (Sec- tion 6.4), and more.'
        agree, disagree, _s, _p = references(tex, printed, {'sec:tasks': '6.4'})
        self.assertEqual((agree, disagree), (1, 0))

    def test_a_number_run_into_a_word_is_not_read(self):
        tex = 'role in achieving these results.\n\n\\cref{tab:main} lists the scores.'
        printed = 'role in achieving these results. 5In the closed book format.'
        agree, disagree, _s, problems = references(tex, printed, {'tab:main': '5'})
        self.assertEqual((agree, disagree, problems), (0, 0, []))

    def test_a_real_disagreement_is_still_caught(self):
        tex = 'the results are given in Section~\\ref{sec:tasks} of the paper.'
        printed = 'the results are given in Section 7.1 of the paper.'
        _a, disagree, _s, _p = references(tex, printed, {'sec:tasks': '6.4'})
        self.assertEqual(disagree, 1)


class EquationMarkers(unittest.TestCase):
    def test_a_score_is_not_an_equation_number(self):
        lines = ['(0.8)', '(0.02)', '(1)', '(2)', '(3.05)']
        self.assertEqual(sp.check_equations('', lines)[1], 2)


class TwoCaptionsThatOpenAlike(unittest.TestCase):
    """PaLM's Figures 24 and 26 both open "Model performance as a function
    of total training FLOP count"; the probe of 26 found 24's caption."""

    def test_an_ambiguous_probe_is_skipped_not_failed(self):
        tex = ('\\begin{figure}\\caption{Model performance as a function of '
               'total training FLOP count. On the 58 tasks.}\\end{figure}\n')
        printed = ('Figure 24: Model performance as a function of total '
                   'training FLOP count. The PaLM line. Figure 1: Model '
                   'performance as a function of total training FLOP count. '
                   'On the 58 tasks.')
        agree, disagree, skipped, problems = sp.check_floats(None, tex, printed)
        self.assertEqual((agree, disagree, skipped, problems), (0, 0, 1, []))


if __name__ == '__main__':
    unittest.main()

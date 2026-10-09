# -*- coding: utf-8 -*-
"""A heading's closing tag is printed once, not again inside the gloss.

2609.11801 tags three sections (Q1), (Q2) and (Q3). The book printed
"정확하고 확장 가능한 순환 추론 (Q1) (Accurate and scalable recurrent
reasoning (Q1))": the translator kept the tag and the gloss repeated it.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import latex_cleanup as lc  # noqa: E402


class SharedTag(unittest.TestCase):
    def test_the_tag_the_translation_kept_leaves_the_gloss(self):
        self.assertEqual(
            lc._without_shared_tag('Accurate and scalable recurrent reasoning (Q1)',
                                   '정확하고 확장 가능한 순환 추론 (Q1)'),
            'Accurate and scalable recurrent reasoning')

    def test_a_tag_the_translation_dropped_stays(self):
        self.assertEqual(lc._without_shared_tag('Results (Q1)', '결과'),
                         'Results (Q1)')

    def test_a_long_parenthetical_is_not_a_tag(self):
        gloss = 'Training (with a very long note)'
        self.assertEqual(lc._without_shared_tag(gloss, '학습 (with a very long note)'),
                         gloss)


if __name__ == '__main__':
    unittest.main()

# -*- coding: utf-8 -*-
"""The reference heading goes over the first entry, wherever the list sits.

Two things put it under the first entry instead. The entry pattern allowed 60
characters of authors, so an entry naming many people was not an entry: SINQ's
first reference had always been left above its heading, and the demo paper's
was once its list named every author. And the list was found by walking back
from the LAST entry, which held only while citeproc appended it to the end;
it now stays ahead of the appendix.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import merge_and_build as mb  # noqa: E402

LONG = ('Agarwal, Manan, Sheel Shah, Chanhyuk Lee, Jaehoon Yoo, Jerry Huang, '
        'Seunghoon Hong, Aditi Raghunathan, Jinwoo Kim, and Nicholas M Boffi. '
        '2026. “Posterior Refinement.” *arXiv*.')
ENTRIES = '\n\n'.join(['Albergo, Michael. 2022. “Flows.” *arXiv*.',
                       'Baek, Kim. 2026. “Loops.” *arXiv*.',
                       'Cameron, Ann. 2026. “DRM.” *arXiv*.',
                       'Du, Yilun. 2024. “Energy.” *ICML*.'])


class ReferenceHeading(unittest.TestCase):
    def test_a_first_entry_with_many_authors_is_part_of_the_list(self):
        md = '# 감사의 글\n\n고마운 분들께 감사드린다.\n\n' + LONG + '\n\n' + ENTRIES
        self.assertEqual(md[mb._citeproc_block_start(md):].split('\n')[0], LONG)

    def test_the_list_ahead_of_an_appendix_is_found(self):
        md = ('# 결론\n\n본문 문단이 여기에 있다.\n\n' + LONG + '\n\n' + ENTRIES
              + '\n\n# 부록\n\n부록 본문은 여러 문장으로 이루어져 있으며 실험 세부를 설명한다.\n\n'
              + 'Zed, Alpha. 2020. “A line that looks like an entry.”\n\n'
              + '부록의 다른 문단도 실험 세부 사항을 길게 설명하고 있다.\n')
        self.assertEqual(md[mb._citeproc_block_start(md):].split('\n')[0], LONG)


if __name__ == '__main__':
    unittest.main()

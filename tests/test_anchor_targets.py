# -*- coding: utf-8 -*-
r"""A float that already carries its LaTeX label must still get a number anchor.

`\label{tab:diag_block_size}` arrives as the table's HTML id, and an element
can hold only one id, so `_add_id` returned the tag untouched and no `tab-N`
target was ever created. Meanwhile every reference to that table had been
rewritten to point at `#tab-N`. The result is a dead in-page link, which
neither errors nor prints nor changes any count — six of CafeQ's eight tables
and five of SINQ's nineteen were in that state in BOTH builds, including the
ones already shipped.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import merge_and_build as mb

KO = {'figure_label': '그림', 'table_label': '표'}


def table(attrs='', caption='<strong>표 5 (Table 5)</strong> 캡션 본문'):
    return ('<table%s>\n<caption>%s</caption>\n<tbody><tr><td>1</td></tr>'
            '</tbody>\n</table>' % (attrs, caption))


def figure(attrs='', caption='<strong>그림 2 (Fig. 2)</strong> 캡션'):
    return ('<figure%s><img src="x.png" />\n<figcaption>%s</figcaption>'
            '</figure>' % (attrs, caption))


class TableAnchorTests(unittest.TestCase):
    def test_a_table_with_no_id_gets_the_number_anchor(self):
        html, targets = mb.anchor_reference_targets(table(), KO)
        self.assertIn('tab-5', targets)
        self.assertIn('<table id="tab-5">', html)

    def test_a_table_that_already_has_a_label_id_still_gets_a_target(self):
        html, targets = mb.anchor_reference_targets(
            table(' id="tab:diag_block_size"'), KO)
        self.assertIn('tab-5', targets, 'the reference had nothing to point at')
        self.assertIn('id="tab:diag_block_size"', html,
                      'the source label must survive')
        self.assertIn('<caption id="tab-5">', html)

    def test_the_caption_keeps_its_own_id_when_it_has_one(self):
        html, targets = mb.anchor_reference_targets(
            '<table id="tab:x">\n<caption id="cap-x"><strong>표 5 (Table 5)'
            '</strong> 본문</caption>\n</table>', KO)
        # Nothing is free to hold the number, so the label id is the target
        # rather than a `tab-5` that does not exist.
        self.assertNotIn('tab-5', targets)
        self.assertIn('tab:x', targets)
        self.assertIn('id="cap-x"', html)

    def test_a_table_with_no_number_is_left_alone(self):
        block = table(caption='<strong>제목</strong> 번호 없음')
        html, targets = mb.anchor_reference_targets(block, KO)
        self.assertEqual(html, block)
        self.assertFalse(targets)


class FigureAnchorTests(unittest.TestCase):
    def test_a_figure_with_no_id_gets_the_number_anchor(self):
        html, targets = mb.anchor_reference_targets(figure(), KO)
        self.assertIn('fig-2', targets)
        self.assertIn('<figure id="fig-2">', html)

    def test_a_figure_that_already_has_a_label_id_still_gets_a_target(self):
        html, targets = mb.anchor_reference_targets(
            figure(' id="fig:alpha_score"'), KO)
        self.assertIn('fig-2', targets)
        self.assertIn('id="fig:alpha_score"', html)
        self.assertIn('<figcaption id="fig-2">', html)


class NoDanglingTests(unittest.TestCase):
    """The property that actually matters: every link has somewhere to land."""

    def test_references_resolve_after_anchoring(self):
        body = (table(' id="tab:x"') + '\n<p>자세한 내용은 (tab:x)를 보라.</p>')
        html, targets = mb.anchor_reference_targets(body, KO)
        import re
        ids = set(re.findall(r'\bid="([^"]+)"', html))
        for target in targets:
            self.assertIn(target, ids,
                          '%s was announced as a target but is not in the '
                          'document' % target)


if __name__ == '__main__':
    unittest.main()

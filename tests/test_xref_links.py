# -*- coding: utf-8 -*-
"""References a reader can see, and click where a target exists.

The original preprint carries 332 link annotations drawn in #001473; the
translation carried 48 — the table of contents and ten bare URLs — and every
"그림 3", "표 5", "식 (7)" was black body text, so nothing caught the eye of
a reader scanning for the figure under discussion.

Two treatments, split on whether a correct target exists. A caption is a
LABEL, not a reference, so it must stay plain: linking "그림 1 (Fig. 1)" to
the figure it already sits under is a link to itself.
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))

import merge_and_build as mb                                     # noqa: E402

KO = {"figure_label": "그림", "table_label": "표",
      "equation_label": "식", "appendix_label": "부록"}

FIGURE = ('<figure><img src="a.png"/>'
          '<figcaption aria-hidden="true"><strong>그림 3 (Fig. 3)</strong> '
          '설명</figcaption></figure>')
TABLE = ('<table class="cols-wide"><caption><strong>표 5 (Table 5)</strong> '
         '설명</caption><tbody><tr><td>1</td></tr></tbody></table>')
EQUATION = '<math data-eqno="(7)" display="block"><mi>x</mi></math>'


def build(body):
    return mb.link_cross_references(body, KO)


class AnchorTests(unittest.TestCase):
    """Every target gets an id, taken from its own caption."""

    def test_a_figure_is_anchored_from_its_caption(self):
        html, targets = mb.anchor_reference_targets(FIGURE, KO)
        self.assertIn("fig-3", targets)
        self.assertIn('<figure id="fig-3"', html)

    def test_a_table_is_anchored_from_its_caption(self):
        html, targets = mb.anchor_reference_targets(TABLE, KO)
        self.assertIn("tab-5", targets)
        self.assertRegex(html, r'<table[^>]*\bid="tab-5"')

    def test_a_numbered_equation_is_anchored(self):
        html, targets = mb.anchor_reference_targets(EQUATION, KO)
        self.assertIn("eq-7", targets)
        self.assertIn('id="eq-7"', html)

    def test_a_caption_longer_than_the_window_still_anchors(self):
        # AlphaQ's figure 1 caption is 24 KB of inline MathML. Requiring the
        # closing tag inside a fixed window lost three figures their anchor.
        huge = FIGURE.replace("설명", "설명" + ("<mi>x</mi>" * 4000))
        _html, targets = mb.anchor_reference_targets(huge, KO)
        self.assertIn("fig-3", targets)

    def test_an_existing_id_is_not_overwritten(self):
        html, targets = mb.anchor_reference_targets(
            FIGURE.replace("<figure>", '<figure id="mine">'), KO)
        self.assertIn('id="mine"', html)
        self.assertNotIn('<figure id="fig-3"', html)
        # This used to assert that NO fig-3 existed anywhere, which locked in
        # the defect: a float carrying its `\label{}` as an id got no number
        # anchor, while every reference to it had already been rewritten to
        # `#fig-3`. Six of CafeQ's eight tables and five of SINQ's nineteen
        # shipped with dead links that way, in v1 as well as v2. The source
        # id stays where it is; the number goes on the caption, which is
        # inside the float and is where a reader following the link lands.
        self.assertIn("fig-3", targets)
        caption = re.search(r'<figcaption\b[^>]*>', html).group(0)
        self.assertIn('id="fig-3"', caption)


class LinkTests(unittest.TestCase):
    """A reference with a target becomes a link; one without gets colour."""

    def test_a_figure_reference_becomes_a_link(self):
        html, stats = build(FIGURE + "<p>그림 3은 이를 보여준다.</p>")
        self.assertIn('<a class="xref" href="#fig-3">그림 3</a>', html)
        self.assertEqual(stats["linked"], 1)

    def test_a_table_reference_becomes_a_link(self):
        html, _ = build(TABLE + "<p>결과는 표 5에 정리하였다.</p>")
        self.assertIn('<a class="xref" href="#tab-5">표 5</a>', html)

    def test_an_equation_reference_becomes_a_link(self):
        html, _ = build(EQUATION + "<p>식 (7)에서 유도한다.</p>")
        self.assertIn('<a class="xref" href="#eq-7">식 (7)</a>', html)

    def test_the_particle_stays_outside_the_link(self):
        html, _ = build(FIGURE + "<p>그림 3은 이를 보여준다.</p>")
        self.assertIn('</a>은 이를', html)

    def test_a_reference_to_a_missing_target_is_left_alone(self):
        html, stats = build("<p>그림 9는 없다.</p>")
        self.assertNotIn("<a", html)
        self.assertEqual(stats["linked"], 0)

    def test_a_caption_is_a_label_and_must_not_link_to_itself(self):
        html, _ = build(FIGURE)
        self.assertNotIn("<a", html)

    def test_a_table_caption_is_left_alone_too(self):
        html, _ = build(TABLE)
        self.assertNotIn("<a", html)


class ColourOnlyTests(unittest.TestCase):
    """Coloured, never linked: guessing a target is worse than not linking."""

    def test_a_citation_is_coloured(self):
        html, stats = build("<p>널리 쓰인다 (Martin et al. 2021).</p>")
        self.assertIn('<span class="xref">(Martin et al. 2021)</span>', html)
        self.assertEqual(stats["coloured"], 1)

    def test_a_multi_entry_citation_is_one_span(self):
        html, _ = build("<p>여럿 (Kim 2020; Lee et al. 2021)이 있다.</p>")
        self.assertEqual(html.count('<span class="xref">'), 1)

    def test_an_appendix_reference_is_coloured_but_not_linked(self):
        # The appendix subsections carry no headings to anchor to.
        html, _ = build("<p>자세한 내용은 부록 A.8에 있다.</p>")
        self.assertIn('<span class="xref">부록 A.8</span>', html)
        self.assertNotIn("<a", html)

    def test_ordinary_parentheses_are_not_a_citation(self):
        html, _ = build("<p>이 값은 (1, 2)이며 범위는 (a, b)이다.</p>")
        self.assertNotIn("xref", html)


class SafetyTests(unittest.TestCase):
    """Markup is not prose."""

    def test_script_and_style_are_untouched(self):
        body = ('<style>.x { content: "그림 3"; }</style>'
                '<script>var s = "표 5";</script>')
        html, stats = build(FIGURE + TABLE + body)
        self.assertIn('content: "그림 3"', html)
        self.assertIn('var s = "표 5"', html)

    def test_an_existing_link_is_not_nested(self):
        html, _ = build(FIGURE + '<a href="#x">그림 3</a>')
        self.assertNotIn('<a class="xref"', html)

    def test_code_is_untouched(self):
        html, _ = build(TABLE + "<p><code>표 5</code></p>")
        self.assertNotIn('<a class="xref"', html)

    def test_the_stylesheet_defines_the_colour_outside_the_print_block(self):
        # An e-reader never applies a print sheet, and Calibre deletes a class
        # no active rule matches (K67).
        path = os.path.join(os.path.dirname(HERE), "scripts",
                            "template_ebook.html")
        with open(path, encoding="utf-8") as fh:
            css = fh.read()
        at = css.index("@media print")
        self.assertLess(css.index(".xref { color: #001473; }"), at)
        self.assertIn("a.xref, span.xref", css[at:])


if __name__ == "__main__":
    unittest.main()

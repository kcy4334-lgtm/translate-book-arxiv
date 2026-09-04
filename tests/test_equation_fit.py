# -*- coding: utf-8 -*-
r"""Keeping a display equation clear of its own number.

VLA-Adapter's equation (3) filled the text column, and the number -- set
flush right the way LaTeX sets it -- printed on top of the formula's last
term. The result is unreadable and every content check passed: the formula
was complete, the number was present, no ink crossed the margin.

CSS cannot fix it. `max-width` clamps a MathML box and the glyphs overflow it
unchanged, so the only lever is font size, and the size that works is not
knowable without laying the formula out. Honouring the `\small` the source
already carries is not enough either -- measured, it leaves the formula ten
points inside the number.

Hence measurement. These tests cover everything except the measuring itself,
which needs a renderer and a PDF reader; the CI suite runs on the standard
library alone, so `measure_probe` is exercised by a probe outside it.
"""
import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import equation_fit as ef

HTML = '''<!doctype html><html lang="ko"><head><meta charset="utf-8">
<style>body { font-size: 11.5pt }</style></head><body>
<p>앞 문단</p>
<p><math id="eq-1" data-eqno="(1)" display="block"><semantics><mrow>
<mi>a</mi></mrow></semantics></math></p>
<p><math id="eq-2" data-eqno="(2)" display="block"><semantics><mrow>
<mi>b</mi></mrow></semantics></math></p>
<p><math display="block"><semantics><mrow><mi>c</mi></mrow></semantics></math></p>
</body></html>'''

CFG = {'margin_left_mm': 18, 'margin_right_mm': 18}


class FindingTheEquations(unittest.TestCase):

    def test_only_numbered_ones_are_found(self):
        """The third equation has no number, so it has nothing to collide
        with and no reason to be measured."""
        found = ef.numbered_equations(HTML)
        self.assertEqual([(k, n) for k, n, _e in found],
                         [('eq-1', '(1)'), ('eq-2', '(2)')])

    def test_the_element_is_captured_whole(self):
        _key, _eqno, element = ef.numbered_equations(HTML)[0]
        self.assertTrue(element.startswith('<math id="eq-1"'))
        self.assertTrue(element.endswith('</math>'))
        self.assertIn('<mi>a</mi>', element)

    def test_an_equation_with_no_id_is_reported_not_dropped(self):
        """Without an id there is no way to patch it later, so it must be
        visible rather than quietly absent."""
        html = HTML.replace('<math id="eq-1" ', '<math ')
        found = ef.numbered_equations(html)
        self.assertEqual(found[0][0], None)
        self.assertEqual(found[0][1], '(1)')

    def test_an_unclosed_element_does_not_swallow_the_document(self):
        html = '<math data-eqno="(1)" display="block"><mi>a</mi>'
        self.assertEqual(ef.numbered_equations(html), [])


class BuildingTheProbe(unittest.TestCase):

    def test_one_page_per_equation_per_size(self):
        probe, plan = ef.build_probe_html(HTML, scales=(1.0, 0.9))
        self.assertEqual(plan, [('eq-1', '(1)', 1.0), ('eq-1', '(1)', 0.9),
                                ('eq-2', '(2)', 1.0), ('eq-2', '(2)', 0.9)])
        self.assertEqual(probe.count('break-after:page'), 4)

    def test_the_books_own_stylesheet_is_carried(self):
        """A probe with its own styles would be measuring a different page:
        column width, body font and math font all come from the head."""
        probe, _plan = ef.build_probe_html(HTML)
        self.assertIn('<style>body { font-size: 11.5pt }</style>', probe)
        self.assertIn('lang="ko"', probe)

    def test_the_size_is_forced_on_the_math_element(self):
        probe, _plan = ef.build_probe_html(HTML, scales=(0.88,))
        self.assertIn('font-size:0.88em', probe)

    def test_full_size_pages_carry_no_style(self):
        """1.0 means 'leave it alone', so it must render the element exactly
        as the book has it -- otherwise the baseline is not the baseline."""
        probe, _plan = ef.build_probe_html(HTML, scales=(1.0,))
        self.assertNotIn('font-size:', probe.split('</head>')[1])

    def test_an_existing_style_attribute_is_kept(self):
        html = HTML.replace('<math id="eq-1" ',
                            '<math id="eq-1" style="color:red" ')
        probe, _plan = ef.build_probe_html(html, scales=(0.9,))
        self.assertIn('style="color:red;font-size:0.9em"', probe)

    def test_a_document_with_no_numbered_equations_makes_no_probe(self):
        probe, plan = ef.build_probe_html('<html><body>x</body></html>')
        self.assertEqual((probe, plan), ('', []))


PATCHED = HTML.replace(
    '<math id="eq-1" data-eqno="(1)" display="block">',
    '<math id="eq-1" data-eqno="(1)" display="block" '
    'style="font-size:0.94em">')


class MeasuringAgainstYesterdaysPatch(unittest.TestCase):
    r"""The pass runs on a document it has already edited.

    `book_doc.html` keeps whatever size the last build wrote, so every run
    after the first starts from a patched file. A second `font-size`
    PREPENDED into the same style attribute loses to the one already there
    -- last declaration wins inside one block -- so all six candidate sizes
    laid out identically, the pass reported the same collision at 1.0 as at
    0.7, and the size it settled on changed nothing on the page. The build
    log said the equation had been reduced; the PDF had it at full size with
    its number still printed across the tail.
    """

    def test_the_baseline_really_is_unstyled(self):
        """Size 1.0 is what every other size is compared against, so it has
        to be the element as the stylesheet alone would set it."""
        probe, _plan = ef.build_probe_html(PATCHED, scales=(1.0,))
        body = probe.split('</head>')[1]
        self.assertNotIn('font-size', body)

    def tags(self, html):
        """The <math> open tags alone. The document's own stylesheet says
        `font-size` too, so a whole-document search proves nothing."""
        import re
        return re.findall(r'<math\b[^>]*>', html)

    def test_a_new_size_replaces_the_old_one(self):
        probe, _plan = ef.build_probe_html(PATCHED, scales=(0.7,))
        tags = self.tags(probe.split('</head>')[1])
        self.assertEqual(len(tags), 2, 'one page per numbered equation')
        for tag in tags:
            self.assertIn('font-size:0.7em', tag)
            self.assertNotIn('0.94em', tag)
            self.assertEqual(tag.count('font-size'), 1)

    def test_applying_twice_is_the_same_as_applying_once(self):
        once, _n = ef.apply_scales(HTML, {'eq-1': 0.88})
        twice, _n = ef.apply_scales(once, {'eq-1': 0.88})
        self.assertEqual(once, twice)

    def test_a_stale_reduction_is_taken_back_off(self):
        """An equation that fits today must not keep last week's size, which
        no log for today's build would mention."""
        out, applied = ef.apply_scales(PATCHED, {})
        self.assertEqual(applied, 0)
        self.assertEqual(out, HTML)
        for tag in self.tags(out):
            self.assertNotIn('font-size', tag)

    def test_other_declarations_survive_the_strip(self):
        html = HTML.replace(
            '<math id="eq-1" data-eqno="(1)" display="block">',
            '<math id="eq-1" data-eqno="(1)" display="block" '
            'style="color:red;font-size:0.8em">')
        out, _applied = ef.apply_scales(html, {})
        self.assertIn('style="color:red"', out)
        for tag in self.tags(out):
            self.assertNotIn('font-size', tag)


class SteppingDownUntilItFits(unittest.TestCase):
    r"""The loop that renders, measures what it rendered, and tries again.

    Measuring an isolated probe instead was the first attempt and it was
    wrong in a way worth keeping written down: laid out alone the equation
    shrank with its font size exactly as arithmetic says, and in the book the
    same element at the same size did not move at all, because there the
    formula is wider than its box and Chromium compresses the spacing to fit.
    The probe certified 0.94em, the build log announced a reduction, and the
    page was unchanged. So the thing measured has to be the thing shipped.
    """

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, 'book_doc.html')
        self.pdf = os.path.join(self.dir, 'book.pdf')
        with io.open(self.path, 'w', encoding='utf-8') as fh:
            fh.write(HTML)
        self.rendered = []
        # Pinned, because otherwise these tests mean different things on
        # different machines. The PyMuPDF guard added below returns before
        # the loop when no reader is installed; with one installed it never
        # runs. The suite passed here and failed on CI, where there is no
        # PyMuPDF, on a test that asserts what the log says after a failed
        # render -- it was reading the guard's message instead. A test whose
        # branch depends on what happens to be installed is not a test.
        real = ef.pymupdf_available
        ef.pymupdf_available = lambda: True
        self.addCleanup(setattr, ef, 'pymupdf_available', real)

    def render(self, src, out):
        with io.open(src, encoding='utf-8') as fh:
            self.rendered.append(fh.read())
        return True

    def sizes_seen(self):
        """The size on eq-1 in each document that was handed to the renderer."""
        import re
        out = []
        for doc in self.rendered:
            tag = re.search(r'<math id="eq-1"[^>]*>', doc).group(0)
            found = re.search(r'font-size:([\d.]+)em', tag)
            out.append(float(found.group(1)) if found else 1.0)
        return out

    def measurer(self, fits_at):
        def measure(_pdf, eqnos, _cfg, _gap):
            size = self.sizes_seen()[-1]
            return [(e, size <= fits_at or e != '(1)', 'x') for e in eqnos]
        return measure

    def test_a_book_that_fits_is_rendered_once(self):
        ok, stuck = ef.fit_equations(
            self.path, self.pdf, self.render, CFG,
            measure=lambda *a: [(e, True, 'x') for e in a[1]],
            log=lambda _m: None)
        self.assertEqual((ok, stuck), (True, []))
        self.assertEqual(len(self.rendered), 1)
        self.assertEqual(self.sizes_seen(), [1.0])

    def test_it_steps_down_until_the_number_is_clear(self):
        notes = []
        ok, stuck = ef.fit_equations(
            self.path, self.pdf, self.render, CFG,
            scales=(1.0, 0.94, 0.88, 0.82),
            measure=self.measurer(0.88), log=notes.append)
        self.assertEqual((ok, stuck), (True, []))
        self.assertEqual(self.sizes_seen(), [1.0, 0.94, 0.88])
        self.assertTrue(any('0.88' in n for n in notes))

    def test_the_last_render_is_the_one_left_on_disk(self):
        """The caller does not render again, so the final pass has to be the
        one that fit."""
        ef.fit_equations(self.path, self.pdf, self.render, CFG,
                         scales=(1.0, 0.94, 0.88),
                         measure=self.measurer(0.88), log=lambda _m: None)
        self.assertEqual(self.sizes_seen()[-1], 0.88)
        with io.open(self.path, encoding='utf-8') as fh:
            self.assertIn('font-size:0.88em', fh.read())

    def test_an_equation_that_never_fits_is_named_not_shipped_quietly(self):
        ok, stuck = ef.fit_equations(
            self.path, self.pdf, self.render, CFG,
            scales=(1.0, 0.9, 0.8),
            measure=self.measurer(0.0), log=lambda _m: None)
        self.assertTrue(ok)
        self.assertEqual(stuck, ['(1)'])

    def test_a_render_failure_stops_the_loop(self):
        notes = []
        ok, stuck = ef.fit_equations(self.path, self.pdf,
                                     lambda s, o: False, CFG,
                                     log=notes.append)
        self.assertEqual((ok, stuck), (False, []))
        self.assertTrue(any('render failed' in n for n in notes))


class ApplyingTheSize(unittest.TestCase):

    def test_only_the_named_equation_changes(self):
        out, applied = ef.apply_scales(HTML, {'eq-2': 0.88})
        self.assertEqual(applied, 1)
        self.assertIn('<math id="eq-2" data-eqno="(2)" display="block" '
                      'style="font-size:0.88em">', out)
        self.assertIn('<math id="eq-1" data-eqno="(1)" display="block">', out)

    def test_the_rest_of_the_document_is_byte_identical(self):
        out, _applied = ef.apply_scales(HTML, {'eq-2': 0.88})
        self.assertEqual(out.replace(' style="font-size:0.88em"', ''), HTML)

    def test_nothing_to_do_is_a_no_op(self):
        self.assertEqual(ef.apply_scales(HTML, {}), (HTML, 0))

    def test_an_unknown_key_changes_nothing(self):
        out, applied = ef.apply_scales(HTML, {'eq-99': 0.8})
        self.assertEqual((out, applied), (HTML, 0))


class TheColumn(unittest.TestCase):

    def test_a4_with_18mm_margins(self):
        left, right = ef.column_bounds(595.0, CFG)
        self.assertAlmostEqual(left, 51.0, places=1)
        self.assertAlmostEqual(right, 544.0, places=1)

    def test_margins_default_when_the_profile_omits_them(self):
        self.assertEqual(ef.column_bounds(595.0, {}),
                         ef.column_bounds(595.0, CFG))


class WithoutAPdfReader(unittest.TestCase):
    r"""A machine that cannot measure the PDF must still get a PDF.

    The renderer treats PyMuPDF as optional -- it warns and carries on when
    page numbers cannot be stamped -- and this pass imported it flat. On a
    fresh clone without that one package the import raised inside the PDF
    branch and took the whole file with it: a book that used to build,
    stopped, because a formula's spacing could not be checked.
    """

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, 'book_doc.html')
        self.pdf = os.path.join(self.dir, 'book.pdf')
        with io.open(self.path, 'w', encoding='utf-8') as fh:
            fh.write(HTML)
        self.real = ef.pymupdf_available
        ef.pymupdf_available = lambda: False
        self.addCleanup(setattr, ef, 'pymupdf_available', self.real)

    def test_the_book_is_still_rendered(self):
        calls = []
        ok, stuck = ef.fit_equations(
            self.path, self.pdf,
            lambda s, o: calls.append(s) or True, CFG,
            log=lambda _m: None)
        self.assertEqual((ok, stuck), (True, []))
        self.assertEqual(calls, [self.path], 'exactly one render')

    def test_it_says_what_is_missing_and_how_to_get_it(self):
        notes = []
        ef.fit_equations(self.path, self.pdf, lambda s, o: True, CFG,
                         log=notes.append)
        joined = ' '.join(notes)
        self.assertIn('PyMuPDF', joined)
        self.assertIn('pip install pymupdf', joined)

    def test_the_document_is_not_touched(self):
        before = io.open(self.path, encoding='utf-8').read()
        ef.fit_equations(self.path, self.pdf, lambda s, o: True, CFG,
                         log=lambda _m: None)
        self.assertEqual(io.open(self.path, encoding='utf-8').read(), before)

    def test_an_injected_measurer_still_runs(self):
        """The absence of the reader is only a reason to skip the DEFAULT
        measurement; a caller that brought its own is unaffected."""
        seen = []

        def measure(_pdf, eqnos, _cfg, _gap):
            seen.append(tuple(eqnos))
            return [(e, True, 'x') for e in eqnos]

        ef.fit_equations(self.path, self.pdf, lambda s, o: True, CFG,
                         measure=measure, log=lambda _m: None)
        self.assertEqual(seen, [('(1)', '(2)')])


class ADocumentWithNoNumberedEquations(unittest.TestCase):
    """Most books. The pass must cost them exactly the one render the build
    was doing anyway."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, 'book_doc.html')
        self.pdf = os.path.join(self.dir, 'book.pdf')
        with io.open(self.path, 'w', encoding='utf-8') as fh:
            fh.write('<html><body>no maths here</body></html>')
        # Pinned for the same reason as above: these assert the path taken
        # when a reader IS available, and must not change with the machine.
        real = ef.pymupdf_available
        ef.pymupdf_available = lambda: True
        self.addCleanup(setattr, ef, 'pymupdf_available', real)

    def test_it_still_renders_exactly_once(self):
        calls = []

        def render(src, out):
            calls.append(src)
            return True

        ok, stuck = ef.fit_equations(self.path, self.pdf, render, CFG)
        self.assertEqual((ok, stuck), (True, []))
        self.assertEqual(calls, [self.path])

    def test_it_never_reaches_the_measurer(self):
        def measure(*_a):
            raise AssertionError('nothing to measure')

        ef.fit_equations(self.path, self.pdf, lambda s, o: True, CFG,
                         measure=measure)

    def test_the_document_is_untouched(self):
        ef.fit_equations(self.path, self.pdf, lambda s, o: True, CFG)
        with io.open(self.path, encoding='utf-8') as fh:
            self.assertEqual(fh.read(),
                             '<html><body>no maths here</body></html>')


if __name__ == '__main__':
    unittest.main()

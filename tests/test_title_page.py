# -*- coding: utf-8 -*-
r"""The page a paper opens with.

The book opened on its table of contents. No title, no authors, no
affiliations -- VLA-Adapter names sixteen people in its title block and the
finished book credited one of them, inside a `<meta>` tag no reader sees.

The names were never missing. `config.txt` has held them under `creator=`
since the paper was converted; there was simply nowhere in the template for
them to go, and nothing anywhere reported the omission, because a count of
what arrived cannot see what never left (K110).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import merge_and_build as mb

NAMES = 'Yihao Wang; Pengxiang Ding; Lingxiao Li'


class BuildingIt(unittest.TestCase):

    def test_the_title_is_the_heading(self):
        got = mb.build_title_page('VLA-Adapter')
        self.assertIn('<h1 class="title-page-title">VLA-Adapter</h1>', got)
        self.assertTrue(got.startswith('<section class="title-page">'))
        self.assertTrue(got.endswith('</section>'))

    def test_it_carries_no_byline_of_its_own(self):
        r"""`apply_template_to_html` already inserts one after the first
        `</h1>`, which is now this heading. A byline here as well printed
        both: the short metadata form, left-aligned, above the full list."""
        got = mb.build_title_page('T')
        self.assertNotIn('byline', got)

    def test_the_source_is_shown(self):
        got = mb.build_title_page('T', source='arXiv:2509.09372v2')
        self.assertIn('arXiv:2509.09372v2', got)

    def test_no_title_means_no_page(self):
        """A source that never had a title must not gain a blank leaf."""
        self.assertEqual(mb.build_title_page(''), '')
        self.assertEqual(mb.build_title_page('   '), '')
        self.assertEqual(mb.build_title_page(None), '')

    def test_a_title_alone_is_enough(self):
        got = mb.build_title_page('T')
        self.assertIn('title-page-title', got)
        self.assertNotIn('title-page-source', got)

    def test_markup_in_the_title_cannot_escape(self):
        """The title comes from a PDF's metadata, which is not the
        pipeline's to trust."""
        got = mb.build_title_page('a < b & c', source='<script>x</script>')
        self.assertNotIn('<script>', got)
        self.assertIn('&lt;script&gt;', got)
        self.assertIn('&amp;', got)


class TheBylineCarriesEveryone(unittest.TestCase):
    r"""`author` is a catalogue entry; the byline is what a reader sees.

    They were the same string, so the title page credited "Yihao Wang 외" --
    one of sixteen. The full list has been in `config.txt` under `creator=`
    all along.
    """

    def render(self, **kw):
        import io
        import shutil
        import tempfile
        from pathlib import Path
        work = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, work, True)
        template = os.path.join(work, 't.html')
        with io.open(template, 'w', encoding='utf-8') as fh:
            fh.write('<html lang="$lang$"><head><title>$title$</title></head>'
                     '<body>$title_page$$body$</body></html>')
        out = os.path.join(work, 'out.html')
        cfg = {'lang_attr': 'ko', 'font_family': 'serif',
               'toc_label': '목차'}
        mb.apply_template_to_html('<p>x</p>', template, out, 'T', cfg, **kw)
        return io.open(out, encoding='utf-8').read()

    def test_the_full_list_reaches_the_page(self):
        html = self.render(author='Yihao Wang 외',
                           byline=NAMES,
                           title_page=mb.build_title_page('T'))
        self.assertIn('Yihao Wang, Pengxiang Ding, Lingxiao Li', html)

    def test_the_metadata_keeps_the_short_form(self):
        html = self.render(author='Yihao Wang 외', byline=NAMES,
                           title_page=mb.build_title_page('T'))
        self.assertIn('<meta name="author" content="Yihao Wang 외">', html)

    def test_only_one_byline_is_printed(self):
        html = self.render(author='Yihao Wang 외', byline=NAMES,
                           title_page=mb.build_title_page('T'))
        self.assertEqual(html.count('class="byline"'), 1)

    def test_without_a_byline_the_author_is_used(self):
        html = self.render(author='Solo Author',
                           title_page=mb.build_title_page('T'))
        self.assertIn('<p class="byline">Solo Author</p>', html)

    def test_semicolons_become_commas(self):
        html = self.render(author='x', byline='A; B; C',
                           title_page=mb.build_title_page('T'))
        self.assertIn('A, B, C', html)
        self.assertNotIn('A; B; C', html)

    def test_a_stylesheet_that_names_the_tag_cannot_take_the_byline(self):
        r"""The insertion used to scan the whole document for the title's
        closing tag. A CSS comment in `<head>` that merely mentioned it
        matched first, and the sixteen authors were written into the
        stylesheet -- present in the file, rendering as nothing, and the
        title page came out with no names on it at all."""
        import io
        import shutil
        import tempfile
        work = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, work, True)
        template = os.path.join(work, 't.html')
        closing = '</h1>'          # the very string the old regex hunted for
        with io.open(template, 'w', encoding='utf-8') as fh:
            fh.write('<html lang="$lang$"><head><title>$title$</title>'
                     '<style>/* styled after the first %s heading */'
                     '</style></head>'
                     '<body>$title_page$$body$</body></html>' % closing)
        out = os.path.join(work, 'out.html')
        cfg = {'lang_attr': 'ko', 'font_family': 'serif', 'toc_label': 'T'}
        mb.apply_template_to_html('<p>x</p>', template, out, 'T', cfg,
                                  'Solo Author',
                                  title_page=mb.build_title_page('T'))
        html = io.open(out, encoding='utf-8').read()
        body = html[html.index('<body'):]
        self.assertIn('class="byline"', body,
                      'the byline must land in the body, not the head')
        self.assertEqual(html.count('class="byline"'), 1)


class TheTemplateHasSomewhereToPutIt(unittest.TestCase):

    def sheet(self):
        import io
        from pathlib import Path
        path = (Path(__file__).resolve().parents[1] / 'scripts'
                / 'template_ebook.html')
        return io.open(path, encoding='utf-8').read()

    def test_the_slot_is_in_the_body(self):
        sheet = self.sheet()
        self.assertIn('$title_page$', sheet)
        self.assertLess(sheet.index('$title_page$'), sheet.index('$body$'),
                        'the title page comes before the book')

    def test_the_token_is_one_the_substituter_knows(self):
        """A `$token$` the regex does not list is left on the page verbatim;
        one the regex lists without a value raises KeyError inside sub()."""
        self.assertTrue(mb._TEMPLATE_TOKEN_RE.match('$title_page$'))

    def test_both_sheets_style_it(self):
        import re
        for cls in ('title-page', 'title-page-title', 'title-page-source'):
            found = re.findall(r'\.%s\s*\{' % re.escape(cls), self.sheet())
            self.assertEqual(len(found), 2, cls)

    def test_both_sheets_centre_the_title_itself(self):
        r"""The heading rules set `text-align: left` for every h1..h6, and
        this class said nothing, so the title sat at the left margin with
        the byline and the arXiv line centred beneath it. A title that fills
        the measure hides this; a short one does not, and the first paper
        run through the finished pipeline had a short one."""
        import re
        found = re.findall(r'\.title-page-title\s*\{[^}]*\}', self.sheet())
        self.assertEqual(len(found), 2)
        for rule in found:
            self.assertIn('text-align: center', rule)

    def test_both_sheets_centre_the_byline_on_it(self):
        """The byline is inserted after the first `</h1>` by the template
        step, not emitted with the page, so it is styled by descent."""
        import re
        found = re.findall(r'\.title-page \.byline\s*\{[^}]*\}', self.sheet())
        self.assertEqual(len(found), 2)
        for rule in found:
            self.assertIn('text-align: center', rule)

    def test_the_print_sheet_gives_it_a_leaf_of_its_own(self):
        import re
        block = re.search(r'\.title-page\s*\{[^}]*break-after: page[^}]*\}',
                          self.sheet())
        self.assertIsNotNone(block, 'the print rule must break after')


class TheContentsComeSecond(unittest.TestCase):
    r"""Where the table of contents is inserted.

    It was pinned to the opening `<body>` tag, so once the title page existed
    the book still opened on its contents and put the title on the leaf
    behind them. The page was built, present in the HTML and invisible in the
    reading order -- which is why the fix looked like it had not worked.
    """

    BODY = ('<html><body>\n'
            '<section class="title-page"><h1 class="title-page-title">T</h1>'
            '</section>\n'
            '<h1 id="one">One</h1><p>x</p>\n'
            '</body></html>')

    def test_the_toc_lands_after_the_title_page(self):
        out, count = mb.build_print_toc(self.BODY, '목차')
        self.assertTrue(count)
        self.assertLess(out.index('title-page'), out.index('print-toc'))

    def test_the_title_page_still_opens_the_body(self):
        out, _count = mb.build_print_toc(self.BODY, '목차')
        after_body = out[out.index('<body>') + len('<body>'):]
        self.assertLess(after_body.index('title-page'),
                        after_body.index('print-toc'))

    def test_without_a_title_page_it_still_opens_the_body(self):
        plain = ('<html><body>\n<h1 id="one">One</h1><p>x</p>\n'
                 '</body></html>')
        out, count = mb.build_print_toc(plain, '목차')
        self.assertTrue(count)
        after_body = out[out.index('<body>') + len('<body>'):]
        self.assertLess(after_body.index('print-toc'),
                        after_body.index('id="one"'))


if __name__ == '__main__':
    unittest.main()

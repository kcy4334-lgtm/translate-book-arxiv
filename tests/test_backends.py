"""Tests for backend selection and arXiv source handling."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts'))

import arxiv_backend
import backends


class NormalizeArxivIdTests(unittest.TestCase):
    def test_plain_id(self):
        self.assertEqual(arxiv_backend.normalize_arxiv_id('2606.04980'), '2606.04980')

    def test_versioned_id(self):
        self.assertEqual(arxiv_backend.normalize_arxiv_id('2606.04980v1'), '2606.04980v1')

    def test_abs_url(self):
        self.assertEqual(
            arxiv_backend.normalize_arxiv_id('https://arxiv.org/abs/2606.04980v1'),
            '2606.04980v1')

    def test_pdf_url(self):
        self.assertEqual(
            arxiv_backend.normalize_arxiv_id('arxiv.org/pdf/2509.22944v4.pdf'),
            '2509.22944v4')

    def test_arxiv_prefix(self):
        self.assertEqual(arxiv_backend.normalize_arxiv_id('arXiv:2511.19705'), '2511.19705')

    def test_empty(self):
        self.assertIsNone(arxiv_backend.normalize_arxiv_id(''))


class SelectBackendTests(unittest.TestCase):
    def test_non_pdf_uses_calibre(self):
        backend, aid, _ = backends.select_backend('book.epub', 'auto', None, True)
        self.assertEqual(backend, backends.BACKEND_CALIBRE)
        self.assertIsNone(aid)

    def test_explicit_calibre_skips_detection(self):
        backend, aid, reason = backends.select_backend('paper.pdf', 'calibre', None, True)
        self.assertEqual(backend, backends.BACKEND_CALIBRE)
        self.assertIn('explicit', reason)

    def test_explicit_arxiv_on_non_pdf_aborts(self):
        with self.assertRaises(SystemExit):
            backends.select_backend('book.epub', 'arxiv', None, True)

    def test_arxiv_id_without_network_aborts(self):
        """Downloading is a network action; never do it implicitly."""
        with self.assertRaises(SystemExit):
            backends.select_backend('paper.pdf', 'auto', '2606.04980', False)

    def test_arxiv_id_override_selects_arxiv(self):
        backend, aid, _ = backends.select_backend('paper.pdf', 'auto', '2606.04980', True)
        self.assertEqual(backend, backends.BACKEND_ARXIV)
        self.assertEqual(aid, '2606.04980')

    def test_unparseable_arxiv_id_aborts(self):
        with self.assertRaises(SystemExit):
            backends.select_backend('paper.pdf', 'auto', '   ', True)


class NormalizeBackendNameTests(unittest.TestCase):
    def test_legacy_alias_adopted(self):
        """Temp dirs written by older versions must stay resumable."""
        self.assertEqual(backends.normalize_backend_name('calibre_htmlz'),
                         backends.BACKEND_CALIBRE)

    def test_passthrough(self):
        self.assertEqual(backends.normalize_backend_name('arxiv'), 'arxiv')

    def test_empty_is_none(self):
        self.assertIsNone(backends.normalize_backend_name(''))


class CheckBackendSwitchTests(unittest.TestCase):
    def _make_temp(self, recorded, with_input_md=True):
        tmp = tempfile.mkdtemp()
        with open(os.path.join(tmp, 'config.txt'), 'w', encoding='utf-8') as f:
            f.write(f'conversion_method={recorded}\n')
        if with_input_md:
            with open(os.path.join(tmp, 'input.md'), 'w', encoding='utf-8') as f:
                f.write('# doc\n')
        return tmp

    def test_no_config_is_fine(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(backends.check_backend_switch(tmp, 'arxiv'))

    def test_same_backend_is_fine(self):
        tmp = self._make_temp('arxiv')
        self.assertIsNone(backends.check_backend_switch(tmp, 'arxiv'))

    def test_legacy_value_matches_calibre(self):
        tmp = self._make_temp('calibre_htmlz')
        self.assertIsNone(backends.check_backend_switch(tmp, 'calibre'))

    def test_mismatch_reports_error(self):
        tmp = self._make_temp('calibre')
        msg = backends.check_backend_switch(tmp, 'arxiv')
        self.assertIsNotNone(msg)
        self.assertIn('Backend mismatch', msg)

    def test_mismatch_without_input_md_is_fine(self):
        """Nothing has been derived yet, so there is nothing to mix."""
        tmp = self._make_temp('calibre', with_input_md=False)
        self.assertIsNone(backends.check_backend_switch(tmp, 'arxiv'))


class FindMainTexTests(unittest.TestCase):
    def test_requires_documentclass_and_begin_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, 'frag.tex'), 'w', encoding='utf-8') as f:
                f.write('Just a fragment with $x$.\n')
            self.assertIsNone(arxiv_backend.find_main_tex(tmp))

    def test_finds_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, 'main.tex'), 'w', encoding='utf-8') as f:
                f.write('\\documentclass{article}\n\\begin{document}\nHi\n\\end{document}\n')
            found = arxiv_backend.find_main_tex(tmp)
            self.assertIsNotNone(found)
            self.assertTrue(found.endswith('main.tex'))

    def test_honours_readme_toplevelfile(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ('a.tex', 'b.tex'):
                with open(os.path.join(tmp, name), 'w', encoding='utf-8') as f:
                    f.write('\\documentclass{article}\n\\begin{document}\nx\n\\end{document}\n')
            with open(os.path.join(tmp, '00README.XXX'), 'w', encoding='utf-8') as f:
                f.write('toplevelfile b.tex\n')
            self.assertTrue(arxiv_backend.find_main_tex(tmp).endswith('b.tex'))


class FlattenTexTests(unittest.TestCase):
    def test_inlines_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, 'sec.tex'), 'w', encoding='utf-8') as f:
                f.write('SECTION BODY\n')
            main = os.path.join(tmp, 'main.tex')
            with open(main, 'w', encoding='utf-8') as f:
                f.write('Start\n\\input{sec}\nEnd\n')
            out = arxiv_backend.flatten_tex(main, tmp)
            self.assertIn('SECTION BODY', out)

    def test_does_not_mistake_includegraphics_for_include(self):
        r"""`\includegraphics{fig.pdf}` must not be read as `\include`."""
        with tempfile.TemporaryDirectory() as tmp:
            main = os.path.join(tmp, 'main.tex')
            line = r'\includegraphics[width=0.6\linewidth]{fig.pdf}'
            with open(main, 'w', encoding='utf-8') as f:
                f.write(line + '\n')
            out = arxiv_backend.flatten_tex(main, tmp)
            self.assertIn(line, out)

    def test_ignores_commented_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, 'sec.tex'), 'w', encoding='utf-8') as f:
                f.write('SHOULD NOT APPEAR\n')
            main = os.path.join(tmp, 'main.tex')
            with open(main, 'w', encoding='utf-8') as f:
                f.write('% \\input{sec}\nBody\n')
            out = arxiv_backend.flatten_tex(main, tmp)
            self.assertNotIn('SHOULD NOT APPEAR', out)

    def test_cycle_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = os.path.join(tmp, 'a.tex')
            b = os.path.join(tmp, 'b.tex')
            with open(a, 'w', encoding='utf-8') as f:
                f.write('A\n\\input{b}\n')
            with open(b, 'w', encoding='utf-8') as f:
                f.write('B\n\\input{a}\n')
            out = arxiv_backend.flatten_tex(a, tmp)  # must terminate
            self.assertIn('A', out)
            self.assertIn('B', out)


class CleanRawInlineLatexTests(unittest.TestCase):
    def test_drops_layout_only_command(self):
        src = 'Text `\\looseness=-1`{=latex} more'
        self.assertNotIn('looseness', arxiv_backend.clean_raw_inline_latex(src))

    def test_keeps_ref_label(self):
        src = 'See Eq. `\\ref{eq:hill}`{=latex} above'
        out = arxiv_backend.clean_raw_inline_latex(src)
        self.assertIn('eq:hill', out)
        self.assertNotIn('{=latex}', out)

    def test_unwraps_unknown_command(self):
        src = 'A `\\somecmd{x}`{=latex} B'
        out = arxiv_backend.clean_raw_inline_latex(src)
        self.assertNotIn('{=latex}', out)
        self.assertIn('somecmd', out)


class NormalizeNewlinesTests(unittest.TestCase):
    def test_crlf_collapsed(self):
        """Left as CRLF, Windows text-mode writing yields \\r\\r\\n on disk,
        which reads back as a blank line that terminates $$ math."""
        self.assertEqual(arxiv_backend.normalize_newlines('a\r\nb\rc'), 'a\nb\nc')


if __name__ == '__main__':
    unittest.main()

"""Tests for backend selection and arXiv source handling."""

import contextlib
import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts'))

import arxiv_backend
import backends


class LayoutDirectivesMustNotReachTheReader(unittest.TestCase):
    r"""`\endgroup` printed in monospace in the middle of a Korean page.

    Grouping and penalty directives control where TeX may break a page and
    nothing a reader sees, but they arrive as an ordinary inline escape.
    Two things let them through: they were missing from the layout list, and
    `_RAW_INLINE_RE` matched only ONE command per span, so
    `\begingroup\postdisplaypenalty=10000` was never matched at all and was
    neither cleaned nor dropped.
    """

    def test_a_grouping_directive_is_dropped(self):
        self.assertEqual(
            arxiv_backend.clean_raw_inline_latex(
                'text `\\endgroup`{=latex} more'),
            'text  more')

    def test_several_directives_in_one_escape_are_dropped(self):
        self.assertEqual(
            arxiv_backend.clean_raw_inline_latex(
                'a `\\begingroup\\postdisplaypenalty=10000`{=latex} b'),
            'a  b')

    def test_a_command_the_reader_needs_survives(self):
        """The guard: an escape is dropped for what is LEFT after the layout
        is removed, never for what it happens to start with."""
        got = arxiv_backend.clean_raw_inline_latex(
            'x `\\textbf{Important}`{=latex} y')
        self.assertIn('Important', got)

    def test_layout_followed_by_content_keeps_the_content(self):
        got = arxiv_backend.clean_raw_inline_latex(
            'x `\\vspace{2mm}\\textbf{Important}`{=latex} y')
        self.assertIn('Important', got)

    def test_a_reference_still_keeps_its_label(self):
        got = arxiv_backend.clean_raw_inline_latex(
            'see `\\ref{fig:one}`{=latex} there')
        self.assertIn('fig:one', got)


class GraphicsPathIsHowAPaperNamesItsFigureFolder(unittest.TestCase):
    r"""`\graphicspath{{figures/}}` is how a paper says that a bare
    `\includegraphics{plot.pdf}` means `figures/plot.pdf`.

    Not reading it reports the figure missing while the file sits in the
    tarball. On the paper that found this, the five calls written
    `figures/x.pdf` resolved and the two written `x.pdf` did not: two
    figures were dropped with nothing but a warning, and their captions
    were left on the page with no picture under them.
    """

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(_rmtree, self.root)
        os.makedirs(os.path.join(self.root, 'figures'))

    def test_the_declared_folder_is_searched(self):
        got = arxiv_backend.graphics_search_dirs(
            r'\graphicspath{{figures/}}', [self.root])
        self.assertEqual(got, [os.path.join(self.root, 'figures')])

    def test_several_folders_are_all_searched(self):
        os.makedirs(os.path.join(self.root, 'plots'))
        got = arxiv_backend.graphics_search_dirs(
            r'\graphicspath{{figures/}{plots/}}', [self.root])
        self.assertEqual(sorted(got), sorted([
            os.path.join(self.root, 'figures'),
            os.path.join(self.root, 'plots')]))

    def test_a_folder_that_is_not_there_is_not_offered(self):
        """A declared path the tarball does not ship must not become a
        search directory, or every later lookup walks a dead end."""
        self.assertEqual(
            arxiv_backend.graphics_search_dirs(
                r'\graphicspath{{nowhere/}}', [self.root]),
            [])

    def test_no_declaration_adds_nothing(self):
        self.assertEqual(
            arxiv_backend.graphics_search_dirs(r'\section{One}', [self.root]),
            [])

    def test_a_missing_base_is_survivable(self):
        self.assertEqual(
            arxiv_backend.graphics_search_dirs(
                r'\graphicspath{{figures/}}', [None, '']),
            [])


def _rmtree(path):
    import shutil
    shutil.rmtree(path, ignore_errors=True)


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


class ArxivWasExplicitTests(unittest.TestCase):
    """K146: `--arxiv-id` implies the backend, so it has to count as explicit.

    `convert.py` refuses to fall back to calibre when the arXiv backend was
    chosen deliberately. That test read `args.backend`, which `--arxiv-id`
    never sets, so the one flag documented as implying the backend was also
    the one request that got silently downgraded.
    """

    def test_backend_arxiv_is_explicit(self):
        self.assertTrue(backends.arxiv_was_explicit('arxiv', None))

    def test_the_id_alone_is_explicit(self):
        self.assertTrue(backends.arxiv_was_explicit('auto', '2609.02668v1'))

    def test_auto_with_no_id_is_not(self):
        self.assertFalse(backends.arxiv_was_explicit('auto', None))

    def test_calibre_is_not(self):
        self.assertFalse(backends.arxiv_was_explicit('calibre', None))

    def test_the_legacy_spelling_is_not_arxiv(self):
        self.assertFalse(backends.arxiv_was_explicit('calibre_htmlz', None))

    def test_it_agrees_with_what_select_backend_chose(self):
        """The two must not drift: when an id alone selects the arXiv backend,
        the failure path has to read that request as explicit."""
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as fh:
            fh.write(b'%PDF-1.4\n')
            path = fh.name
        self.addCleanup(os.unlink, path)
        backend, arxiv_id, reason = backends.select_backend(
            path, 'auto', '2609.02668v1', True)
        self.assertEqual(backend, backends.BACKEND_ARXIV)
        self.assertEqual(arxiv_id, '2609.02668v1')
        self.assertTrue(
            backends.arxiv_was_explicit('auto', '2609.02668v1'),
            'select_backend chose arxiv from the id alone, so the fallback '
            'guard must call that request explicit; reason was %r' % reason)


class _FakePandoc(object):
    """Stands in for pypandoc so the failure path can be reached offline.

    `latex_to_markdown` imports pypandoc inside its own body, so putting one
    here is enough; nothing has to be installed and no pandoc is run.
    """

    def __init__(self, error):
        self._error = error

    def convert_text(self, *_args, **_kwargs):
        raise RuntimeError(self._error)


class BibliographyErrorGuidanceTests(unittest.TestCase):
    """K145: a `.bib` the PAPER ships can stop the whole conversion.

    The generic advice on that path is "fix the cause reported above", and
    the cause is a file the reader did not write. So the failure has to say
    whose file it is and what actually works on it.
    """

    PANDOC_SAYS = ("Error reading bibliography file '/tmp/x/cas-refs.bib':\n"
                   "(line 3006, column 1):\nunexpected '@'")

    def _run(self, error):
        saved = sys.modules.get('pypandoc')
        sys.modules['pypandoc'] = _FakePandoc(error)
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                result = arxiv_backend.latex_to_markdown(
                    'BODY', '/tmp/x', '/tmp/x', bib_files=['/tmp/x/a.bib'])
            return result, buf.getvalue()
        finally:
            if saved is None:
                del sys.modules['pypandoc']
            else:
                sys.modules['pypandoc'] = saved

    def test_the_path_is_recognised(self):
        m = arxiv_backend._BIB_READ_ERROR_RE.search(self.PANDOC_SAYS)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), '/tmp/x/cas-refs.bib')

    def test_an_unrelated_pandoc_error_is_not(self):
        self.assertIsNone(arxiv_backend._BIB_READ_ERROR_RE.search(
            'Error at "source" (line 12, column 3): unexpected "\\\\"'))

    def test_the_guidance_names_the_file_and_whose_it_is(self):
        result, out = self._run(self.PANDOC_SAYS)
        self.assertIsNone(result)
        self.assertIn('cas-refs.bib', out)
        self.assertIn("paper's own tarball", out)
        self.assertIn('K145', out)

    def test_it_does_not_tell_anyone_to_repair_the_file_in_place(self):
        """The first version of this message did, and it cannot work.

        `fetch_and_convert` calls `shutil.rmtree` on the work directory before
        unpacking, so a hand-repaired `.bib` is deleted on the next run and
        pandoc never sees it. Measured: the edit was gone and the failure was
        byte-identical. Advice that cannot be followed is worse than none.
        """
        _result, out = self._run(self.PANDOC_SAYS)
        self.assertIn('will not help', out)
        self.assertIn('re-unpacked on every run', out)
        self.assertNotIn('and re-run', out)

    def test_another_failure_keeps_the_plain_message(self):
        """The advice is only right for a bibliography, so it must not appear
        on every failure; otherwise it sends readers at the wrong file."""
        result, out = self._run('Pandoc died with exitcode "43"')
        self.assertIsNone(result)
        self.assertIn('conversion failed', out)
        self.assertNotIn("paper's own tarball", out)
        self.assertNotIn('K145', out)


if __name__ == '__main__':
    unittest.main()

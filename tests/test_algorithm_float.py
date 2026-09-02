# -*- coding: utf-8 -*-
r"""Tests for the algorithm-float converter and the raw-LaTeX loss check.

The defect these lock down shipped in every book this pipeline built: the
`algorithm` float reached output.md intact and pandoc deleted it on the way
to HTML, while every existing check passed. The checks counted tables,
images, equations and captions; nothing counted the float, so nothing noticed
it was gone. Two of the fixtures below are the real floats from the corpus --
one paper uses the `algorithmic` package's UPPERCASE macros, the other uses
`algpseudocode`'s CamelCase, so neither spelling is optional.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import algorithm_float as af


UPPER = r"""\begin{algorithm}[ht]\caption{Adaptive rounding.}
\begin{algorithmic}[1]
\REQUIRE Matrices $W_1$ and $W_2$, iterations $I$.
\STATE $\widehat{W_1} \leftarrow {\rm Q}(W_1)$ %
\FOR{$i \leftarrow 1$ \TO $I$}
    \STATE $\widehat{W_2} \leftarrow {\rm Q}(W_1 W_2)$.
\ENDFOR
\RETURN $\widehat{W_1}, \widehat{W_2}$.
\end{algorithmic}
\end{algorithm}"""

# The flattener leaves `\undefined [1]` where it could not resolve
# `\begin{algorithmic}`; the real SINQ float arrives in exactly this shape.
CAMEL = r"""\begin{algorithm}[t]\caption{SINQ normalisation.}
\undefined    [1]
\Require Weight matrix $\mathbf{W}$, iterations $K$
\Ensure Quantized weights $\mathbf{Q}$
% Initialization
\State $\tau \gets \min(\vec{\sigma})$ \Comment{Target variance}
\For{$k \gets 1$ to $K$}
    \State $\mathbf{\hat{W}} \gets \mathbf{W}$ \Comment{Apply current scales}
    \If{$I < I_{\text{best}}$}
        \State $I_{\text{best}} \gets I$
    \EndIf
\EndFor
\State \Return $\mathbf{Q}$
\undefined
\end{algorithm}"""


class ParseTests(unittest.TestCase):
    def test_uppercase_macros_are_understood(self):
        io_lines, steps = af.parse_body(UPPER)
        self.assertEqual([k for k, _ in io_lines], ['require'])
        self.assertEqual(len(steps), 5)          # STATE FOR STATE ENDFOR RETURN

    def test_camelcase_macros_are_understood(self):
        io_lines, steps = af.parse_body(CAMEL)
        self.assertEqual([k for k, _ in io_lines], ['require', 'ensure'])
        self.assertTrue(steps, 'algpseudocode spelling produced nothing')

    def test_require_is_not_a_numbered_step(self):
        _io, steps = af.parse_body(UPPER)
        self.assertFalse(any('Matrices' in line for _d, line in steps),
                         'the input line was numbered as a step')

    def test_loop_body_is_indented_and_closed(self):
        _io, steps = af.parse_body(UPPER)
        depths = [d for d, _line in steps]
        self.assertEqual(depths, [0, 0, 1, 0, 0])

    def test_nested_if_inside_for(self):
        _io, steps = af.parse_body(CAMEL)
        depths = [d for d, _line in steps]
        self.assertEqual(max(depths), 2, 'the if-body should sit two deep')
        self.assertEqual(depths[-1], 0, 'the float should close back to zero')

    def test_comment_annotates_its_step_and_is_not_a_step(self):
        _io, steps = af.parse_body(CAMEL)
        lines = [line for _d, line in steps]
        self.assertTrue(any('Target variance' in l and '\\gets' in l
                            for l in lines),
                        'the comment left its own step')

    def test_a_bare_state_before_return_does_not_leave_an_empty_step(self):
        _io, steps = af.parse_body(CAMEL)
        self.assertFalse(any(not line.strip() for _d, line in steps))
        self.assertTrue(any(line.startswith('**return**')
                            for _d, line in steps))

    def test_math_is_carried_through_unchanged(self):
        _io, steps = af.parse_body(UPPER)
        joined = ' '.join(line for _d, line in steps)
        self.assertIn(r'$\widehat{W_1} \leftarrow {\rm Q}(W_1)$', joined)

    def test_the_flatteners_undefined_residue_is_dropped(self):
        markdown = af.algorithm_to_markdown(CAMEL, 1, 'ko')
        self.assertNotIn('undefined', markdown)

    def test_whole_line_latex_comments_are_dropped(self):
        markdown = af.algorithm_to_markdown(CAMEL, 1, 'en')
        self.assertNotIn('Initialization', markdown)

    def test_an_escaped_percent_is_not_a_comment(self):
        tex = (r'\begin{algorithm}\caption{c}\begin{algorithmic}'
               '\n' r'\STATE accuracy is 90\% here' '\n'
               r'\end{algorithmic}\end{algorithm}')
        _io, steps = af.parse_body(tex)
        self.assertIn('here', steps[0][1])


class RenderTests(unittest.TestCase):
    def test_labels_follow_the_target_language(self):
        self.assertIn('**알고리즘 1.**', af.algorithm_to_markdown(UPPER, 1, 'ko'))
        self.assertIn('**입력:**', af.algorithm_to_markdown(UPPER, 1, 'ko'))
        self.assertIn('**算法 2.**', af.algorithm_to_markdown(UPPER, 2, 'zh'))
        self.assertIn('**出力:**', af.algorithm_to_markdown(CAMEL, 1, 'ja'))

    def test_a_regional_code_still_resolves(self):
        self.assertIn('**算法 1.**', af.algorithm_to_markdown(UPPER, 1, 'zh-CN'))

    def test_an_unknown_language_falls_back_to_english(self):
        out = af.algorithm_to_markdown(UPPER, 1, 'xx')
        self.assertIn('**Algorithm 1.**', out)
        self.assertIn('**Input:**', out)

    def test_pseudocode_keywords_stay_english(self):
        out = af.algorithm_to_markdown(UPPER, 1, 'ko')
        self.assertIn('**for**', out)
        self.assertIn('**end for**', out)
        self.assertIn('**return**', out)

    def test_steps_are_a_markdown_ordered_list(self):
        out = af.algorithm_to_markdown(UPPER, 1, 'en')
        body = [l for l in out.split('\n') if l[:2] in ('1.', '2.', '3.')]
        self.assertGreaterEqual(len(body), 3)

    def test_indentation_uses_a_character_markdown_will_not_eat(self):
        # Four leading ASCII spaces inside a list item become a code block.
        out = af.algorithm_to_markdown(UPPER, 1, 'en')
        indented = [l for l in out.split('\n') if af.INDENT in l]
        self.assertTrue(indented)
        for line in indented:
            after = line.split('. ', 1)[1]
            self.assertFalse(after.startswith('    '), line)

    def test_input_and_output_are_separate_paragraphs(self):
        """SINQ's first build printed `... s_max **출력:** ...` on one line.

        Two consecutive lines are ONE paragraph in markdown, so the labels
        ran together and the reader saw the inputs and the outputs as a
        single sentence.
        """
        out = af.algorithm_to_markdown(CAMEL, 1, 'ko')
        lines = out.split('\n')
        i = next(n for n, l in enumerate(lines) if l.startswith('**입력:**'))
        self.assertEqual(lines[i + 1], '',
                         'the output label would join the input paragraph')
        self.assertTrue(lines[i + 2].startswith('**출력:**'))

    def test_a_label_becomes_an_anchor(self):
        tex = UPPER.replace(r'\caption{Adaptive rounding.}',
                            r'\caption{Adaptive rounding.}\label{alg:x}')
        self.assertIn('{#alg:x}', af.algorithm_to_markdown(tex, 1, 'en'))

    def test_a_float_with_no_statements_is_refused_not_faked(self):
        tex = r'\begin{algorithm}\caption{empty}\end{algorithm}'
        self.assertIsNone(af.algorithm_to_markdown(tex, 1, 'en'))


class ExpandTests(unittest.TestCase):
    def test_the_float_is_gone_from_the_markdown(self):
        md = 'before\n\n%s\n\nafter\n' % UPPER
        out, ok, bad = af.expand_algorithm_floats(md, 'ko')
        self.assertEqual((ok, bad), (1, 0))
        self.assertNotIn(r'\begin{algorithm}', out)
        self.assertIn('before', out)
        self.assertIn('after', out)

    def test_two_floats_are_numbered_in_order(self):
        md = '%s\n\n%s\n' % (UPPER, CAMEL)
        out, ok, _bad = af.expand_algorithm_floats(md, 'en')
        self.assertEqual(ok, 2)
        self.assertLess(out.index('**Algorithm 1.**'),
                        out.index('**Algorithm 2.**'))

    def test_a_document_with_no_floats_is_returned_untouched(self):
        md = 'nothing to do here\n'
        self.assertEqual(af.expand_algorithm_floats(md, 'ko'), (md, 0, 0))

    def test_an_unconvertible_float_is_left_in_place_to_be_reported(self):
        md = r'\begin{algorithm}\caption{empty}\end{algorithm}'
        out, ok, bad = af.expand_algorithm_floats(md, 'en')
        self.assertEqual((ok, bad), (0, 1))
        self.assertIn(r'\begin{algorithm}', out,
                      'a float we could not convert must stay visible')


class FidelityTests(unittest.TestCase):
    """The check that would have caught this in the first place."""

    def test_a_dropped_float_is_reported(self):
        md = 'text\n\n%s\n' % UPPER
        html = '<p>text</p>'          # pandoc dropped the float
        lost = af.check_latex_float_fidelity(md, html)
        self.assertEqual(len(lost), 1)
        self.assertEqual(lost[0][0], 'algorithm')

    def test_a_float_that_reached_the_page_is_not_reported(self):
        md = 'text\n\n%s\n' % UPPER
        html = '<p>Adaptive rounding.</p>'
        self.assertEqual(af.check_latex_float_fidelity(md, html), [])

    def test_wrapping_and_tags_do_not_look_like_loss(self):
        md = 'text\n\n%s\n' % UPPER
        html = '<p>Adaptive\n  <em>rounding.</em></p>'
        self.assertEqual(af.check_latex_float_fidelity(md, html), [],
                         'a check that fails on reflowed text gets ignored')

    def test_an_escaped_underscore_is_part_of_the_word(self):
        r"""`\_` prints as `_`; treating it as markup aborted a good build.

        AlphaQ's table 6 caption is `\texttt{PL\_Alpha\_Hill}`. Stripping the
        escape fingerprinted it as `PL Alpha Hill`, which matches nothing on
        a page that prints `PL_Alpha_Hill`, so the check reported a table
        that was present and the build stopped.
        """
        md = ('\\begin{table}\n'
              '\\caption{\\texttt{PL\\_Alpha\\_Hill} offline cost}\n'
              '\\begin{tabular}{ll}a & b\\\\\\end{tabular}\n\\end{table}')
        html = '<table><caption><code>PL_Alpha_Hill</code> offline cost</caption></table>'
        self.assertEqual(af.check_latex_float_fidelity(md, html), [])

    def test_an_escaped_ampersand_is_part_of_the_word(self):
        md = ('\\begin{table}\n\\caption{Dettmers \\& Zettlemoyer results}\n'
              '\\begin{tabular}{ll}a & b\\\\\\end{tabular}\n\\end{table}')
        html = '<table><caption>Dettmers &amp; Zettlemoyer results</caption></table>'
        self.assertEqual(af.check_latex_float_fidelity(md, html), [])

    def test_a_bare_ampersand_is_still_a_separator(self):
        # The cell divider must not become part of a fingerprint.
        md = ('\\begin{table}\n\\caption{Results across every held out split}\n'
              '\\begin{tabular}{ll}alpha & beta\\\\\\end{tabular}\n\\end{table}')
        lost = af.check_latex_float_fidelity(md, '<p>nothing here</p>')
        self.assertEqual(len(lost), 1)
        self.assertNotIn('&', lost[0][1])

    def test_a_citation_key_is_not_part_of_the_fingerprint(self):
        r"""The page shows an author and a year, never the bibtex key.

        SINQ's table 6 caption cites `\cite{sglang}`. Leaving the key in the
        fingerprint sent the check hunting the page for `sglang` and aborted
        a build over a table that was sitting right there.
        """
        md = ('\\begin{table}\n'
              '\\caption{Baseline throughput on SGLang \\cite{sglang} for '
              'every decode setting}\n'
              '\\begin{tabular}{ll}a & b\\\\\\end{tabular}\n\\end{table}')
        html = ('<table><caption>Baseline throughput on SGLang '
                '(Zheng et al. 2024) for every decode setting</caption></table>')
        self.assertEqual(af.check_latex_float_fidelity(md, html), [])

    def test_a_label_key_is_not_part_of_the_fingerprint(self):
        md = ('\\begin{table}\n\\caption{Evaluation datasets we considered}\n'
              '\\label{tab:task_descs}\n'
              '\\begin{tabular}{ll}a & b\\\\\\end{tabular}\n\\end{table}')
        html = '<table><caption>Evaluation datasets we considered</caption></table>'
        self.assertEqual(af.check_latex_float_fidelity(md, html), [])

    def test_math_environments_are_not_reported(self):
        md = r'\begin{equation}' '\n' r'E = mc^2 \alpha \beta \gamma' '\n' \
             r'\end{equation}'
        self.assertEqual(af.check_latex_float_fidelity(md, '<p></p>'), [])

    def test_a_table_that_reached_the_page_is_not_reported(self):
        md = ('\\begin{table}\n\\caption{Results on the held out split}\n'
              '\\begin{tabular}{ll}a & b\\\\\\end{tabular}\n\\end{table}')
        html = '<table><caption>Results on the held out split</caption></table>'
        self.assertEqual(af.check_latex_float_fidelity(md, html), [])

    def test_a_dropped_table_is_reported_too(self):
        md = ('\\begin{table}\n\\caption{Results on the held out split}\n'
              '\\begin{tabular}{ll}a & b\\\\\\end{tabular}\n\\end{table}')
        lost = af.check_latex_float_fidelity(md, '<p>nothing</p>')
        self.assertEqual([env for env, _p in lost], ['table'])


if __name__ == '__main__':
    unittest.main()

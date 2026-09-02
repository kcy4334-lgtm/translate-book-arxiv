# -*- coding: utf-8 -*-
r"""The theorem counter must read the document, not a fixed list of names.

A hardcoded environment vocabulary produced no error and no warning -- it
produced 52 wrong theorem numbers out of 59, and 225 of 274 body references
would have pointed at the wrong result. The failure is invisible by
construction: every number still looks like a number.

These tests pin the three things that made it invisible.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import merge_and_build as mb


def _temp_dir_with(tex):
    d = tempfile.mkdtemp()
    with open(os.path.join(d, 'flat.tex'), 'w', encoding='utf-8') as fh:
        fh.write(tex)
    return d


class ReadTheoremEnvironments(unittest.TestCase):
    def test_shared_counter_is_reported(self):
        envs = mb.read_theorem_environments(
            r'\newtheorem{theorem}{Theorem}'
            r'\newtheorem{lemma}[theorem]{Lemma}')
        self.assertEqual(envs['theorem'], 'theorem')
        self.assertEqual(envs['lemma'], 'theorem')

    def test_own_counter_is_its_own_group(self):
        envs = mb.read_theorem_environments(
            r'\newtheorem{theorem}{Theorem}'
            r'\newtheorem{definition-notag}{Definition}')
        self.assertEqual(envs['definition-notag'], 'definition-notag')

    def test_starred_declaration_takes_no_number(self):
        envs = mb.read_theorem_environments(
            r'\newtheorem*{note}{Note}\newtheorem{theorem}{Theorem}')
        self.assertNotIn('note', envs)

    def test_the_within_argument_does_not_disturb_the_counter_group(self):
        # It says where the counter RESETS, not which counter it is. The group
        # is still the environment's own.
        envs = mb.read_theorem_environments(
            r'\newtheorem{theorem}{Theorem}[section]')
        self.assertEqual(envs['theorem'], 'theorem')


class TheWithinArgumentIsRead(unittest.TestCase):
    r"""It used to be described as "deliberately ignored" and was in fact
    invisible: `_NEWTHEOREM_RE` captured only the LEADING optional argument, so
    `[section]` never reached a group and the test that pinned the claim
    asserted something the code could not have done otherwise. Maynard's 35
    theorem references each named a number the paper does not print (K130).
    """

    def test_a_trailing_within_is_captured(self):
        self.assertEqual(
            mb.read_theorem_parents(r'\newtheorem{thrm}{Theorem}[section]'),
            {'thrm': 'section'})

    def test_a_leading_shared_counter_is_not_a_parent(self):
        # `\newtheorem{lmm}[thrm]{Lemma}` shares thrm's counter; the scope
        # belongs to thrm, and naming lmm here would reset a counter that
        # does not exist.
        self.assertEqual(
            mb.read_theorem_parents(r'\newtheorem{lmm}[thrm]{Lemma}'), {})

    def test_both_arguments_on_one_declaration(self):
        self.assertEqual(
            mb.read_theorem_parents(r'\newtheorem{lmm}[thrm]{Lemma}[section]'),
            {})

    def test_a_starred_declaration_has_no_counter_to_scope(self):
        self.assertEqual(
            mb.read_theorem_parents(r'\newtheorem*{rmk}{Remark}[section]'), {})

    def test_no_within_means_no_entry(self):
        self.assertEqual(
            mb.read_theorem_parents(r'\newtheorem{thrm}{Theorem}'), {})

    def test_read_counter_parents_carries_it_through(self):
        parents = mb.read_counter_parents(
            r'\newtheorem{thrm}{Theorem}[section]' '\n'
            r'\numberwithin{equation}{section}' '\n'
            r'\begin{document}')
        self.assertEqual(parents.get('thrm'), 'section')
        self.assertEqual(parents.get('equation'), 'section')

    def test_a_declaration_in_the_body_is_not_read_as_preamble(self):
        parents = mb.read_counter_parents(
            r'\begin{document}' '\n'
            r'\newtheorem{thrm}{Theorem}[section]')
        self.assertNotIn('thrm', parents)


class DeclaredEnvironmentsAreCounted(unittest.TestCase):
    def test_undeclared_names_do_not_shift_the_counter(self):
        # `example` is declared and used. If the scanner does not know it, the
        # theorem that follows it is numbered 2 instead of 3.
        tex = (r'\newtheorem{theorem}{Theorem}'
               r'\newtheorem{example}[theorem]{Example}'
               r'\begin{theorem}\label{first}x\end{theorem}'
               r'\begin{example}\label{ex}y\end{example}'
               r'\begin{theorem}\label{third}z\end{theorem}')
        d = _temp_dir_with(tex)
        idx = mb.build_label_index(d)
        self.assertEqual(idx['first'], ('1', 'theorem'))
        self.assertEqual(idx['ex'], ('2', 'theorem'))
        self.assertEqual(idx['third'], ('3', 'theorem'))

    def test_own_counter_restarts_without_disturbing_the_shared_one(self):
        tex = (r'\newtheorem{theorem}{Theorem}'
               r'\newtheorem{definition-notag}{Definition}'
               r'\begin{theorem}\label{a}x\end{theorem}'
               r'\begin{definition-notag}\label{d}y\end{definition-notag}'
               r'\begin{theorem}\label{b}z\end{theorem}')
        d = _temp_dir_with(tex)
        idx = mb.build_label_index(d)
        self.assertEqual(idx['a'], ('1', 'theorem'))
        self.assertEqual(idx['d'], ('1', 'theorem'))   # its own counter
        self.assertEqual(idx['b'], ('2', 'theorem'))   # shared one untouched

    def test_hyphenated_name_is_not_read_as_its_prefix(self):
        # `definition-notag` must not match the `definition` alternative.
        pattern = mb._label_token_re({'definition': 'theorem',
                                      'definition-notag': 'definition-notag'})
        m = pattern.search(r'\begin{definition-notag}')
        self.assertEqual(m.group(4), 'definition-notag')

    def test_paper_without_newtheorem_keeps_the_default_vocabulary(self):
        tex = (r'\begin{theorem}\label{a}x\end{theorem}'
               r'\begin{lemma}\label{b}y\end{lemma}')
        d = _temp_dir_with(tex)
        idx = mb.build_label_index(d)
        self.assertEqual(idx['a'], ('1', 'theorem'))
        self.assertEqual(idx['b'], ('2', 'theorem'))


class EquationLabelsKeepTheirOwnCounter(unittest.TestCase):
    def test_equation_inside_a_theorem_is_not_a_theorem_number(self):
        tex = (r'\newtheorem{theorem}{Theorem}'
               r'\begin{theorem}\label{thm}'
               r'\begin{equation}\label{eq}x\end{equation}'
               r'\end{theorem}')
        d = _temp_dir_with(tex)
        idx = mb.build_label_index(d)
        self.assertEqual(idx['thm'], ('1', 'theorem'))
        self.assertEqual(idx['eq'], ('1', 'equation'))


class UnprefixedReferences(unittest.TestCase):
    """A label without a `thm:` prefix is still a reference."""

    WORDS = {'theorem': '정리', 'section': '절', 'equation': '식',
             'figure': '그림', 'table': '표'}
    FORMATS = {'equation': '{label} ({number})', 'section': '{number}{label}'}

    LEADS = ('보조정리', '따름정리', '정리', '명제', '정의', '비고', '예')

    def _resolve(self, text, index):
        return mb.resolve_unprefixed_references(text, index, self.WORDS,
                                                self.FORMATS,
                                                lead_words=self.LEADS)

    def test_key_without_a_prefix_resolves(self):
        got, n = self._resolve('자세한 내용은 정리 (Bai-Yin)을 보라.',
                               {'Bai-Yin': ('31', 'theorem')})
        self.assertEqual(n, 1)
        self.assertIn('정리 31', got)
        self.assertNotIn('Bai-Yin)', got)

    def test_the_translators_own_label_word_survives(self):
        # The index knows the number, not whether this one is a Lemma.
        got, _ = self._resolve('보조정리 (Rudelson)에 의하여',
                               {'Rudelson': ('28', 'theorem')})
        self.assertIn('보조정리 28', got)
        self.assertNotIn('정리 28', got.replace('보조정리 28', ''))

    def test_declaration_site_keeps_its_name(self):
        # `**정리 32** (Gaussian).` states the theorem; it does not point at it.
        text = '**정리 32** (Gaussian). 다음이 성립한다.'
        got, n = self._resolve(text, {'Gaussian': ('32', 'theorem')})
        self.assertEqual(n, 0)
        self.assertEqual(got, text)

    def test_section_reference_uses_the_language_order(self):
        got, _ = self._resolve('절 (s: covariance)에서',
                               {'s: covariance': ('4.3', 'section')})
        self.assertIn('4.3절', got)

    def test_key_containing_regex_metacharacters(self):
        got, n = self._resolve('정리 (A*A rows)를 보라',
                               {'A*A rows': ('40', 'theorem')})
        self.assertEqual(n, 1)
        self.assertIn('정리 40', got)

    def test_unknown_key_is_left_exactly_as_it_was(self):
        text = '정리 (never declared)를 보라'
        got, n = self._resolve(text, {'Bai-Yin': ('31', 'theorem')})
        self.assertEqual(n, 0)
        self.assertEqual(got, text)

    def test_empty_index_is_a_no_op(self):
        text = '정리 (Bai-Yin)'
        self.assertEqual(self._resolve(text, {}), (text, 0))


if __name__ == '__main__':
    unittest.main()

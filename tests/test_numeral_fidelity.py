# -*- coding: utf-8 -*-
r"""A numeral keeps the spelling the source gave it.

French, German and Spanish write 58,9 where English writes 58.9, and German
writes 60.000 for sixty thousand. Three translators applied those conventions
in one run, correctly by the rules of their languages, and the book cannot
follow them. A table float is protected LaTeX reproduced verbatim from the
paper, and `verify_tables` refuses any change to the numbers inside one --
the guard that stops a retyped value reaching a reader. So the page came out
carrying 58,9 % in a sentence and 58.9\% in the table that sentence is about,
and in German 60.000 sat a page away from 58.9, where it reads as a decimal.

Consistency is only reachable from one side, so the prose follows the tables.

The CJK books never showed this: their convention is the source's already.
The check was written the day the first Latin editions were built, which is
the day the defect first existed.
"""
from __future__ import unicode_literals

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts'))

import verify_chunk


SOURCE = ('The baseline gives 58.9% frame accuracy and a WER of 10.9%, '
          'trained on 60,000 examples with a temperature of 2.5.\n')


class ItFires(unittest.TestCase):

    def only_finding(self, output, source=SOURCE):
        found = verify_chunk.check_numerals(source, output)
        self.assertEqual(len(found), 1, found)
        self.assertEqual(found[0]['severity'], 'fail')
        return found[0]

    def test_a_decimal_comma(self):
        french = SOURCE.replace('58.9', '58,9').replace('10.9', '10,9')
        finding = self.only_finding(french)
        self.assertIn('58.9', finding['detail'])
        self.assertIn('10.9', finding['detail'])

    def test_a_german_thousands_separator(self):
        german = SOURCE.replace('60,000', '60.000')
        self.assertIn('60,000', self.only_finding(german)['detail'])

    def test_a_thin_space_between_thousands(self):
        french = SOURCE.replace('60,000', '60\u202f000')
        self.assertIn('60,000', self.only_finding(french)['detail'])

    def test_a_separator_simply_dropped(self):
        self.assertIn('60,000',
                      self.only_finding(SOURCE.replace('60,000', '60000'))
                      ['detail'])

    def test_it_is_language_independent(self):
        r"""The Korean books never showed the defect because Korean uses the
        source's convention, not because anything checked."""
        korean = ('\uae30\uc900\uc120\uc740 58,9%\uc758 \uc815\ud655\ub3c4'
                  '\uc640 10.9%\uc758 WER\uc744 60,000\uac1c\uc758 '
                  '\uc608\uc81c\uc5d0\uc11c 2.5\uc758 \uc628\ub3c4\ub85c '
                  '\uc5bb\ub294\ub2e4.\n')
        self.assertIn('58.9', self.only_finding(korean)['detail'])

    def test_the_evidence_comes_from_the_source(self):
        finding = self.only_finding(SOURCE.replace('58.9', '58,9'))
        self.assertIn('58.9', finding['evidence'])

    def test_it_names_the_step_in_the_detail(self):
        """A finding that does not say what happened gets waved through."""
        self.assertIn('locale',
                      self.only_finding(SOURCE.replace('58.9', '58,9'))
                      ['detail'])


class ItStaysQuietOnCorrectWork(unittest.TestCase):
    r"""K157: a check that fires on a good translation teaches its reader to
    skip it, and this one runs on every chunk of every book."""

    def quiet(self, output, source=SOURCE):
        self.assertEqual(verify_chunk.check_numerals(source, output), [])

    def test_a_faithful_translation(self):
        self.quiet('La r\u00e9f\u00e9rence donne 58.9% de pr\u00e9cision par '
                   'trame et un WER de 10.9%, sur 60,000 exemples \u00e0 une '
                   'temp\u00e9rature de 2.5.\n')

    def test_a_bare_integer_spelled_out_in_words(self):
        r"""Only numerals with an internal separator are checked, so
        "10 models" -> "dix mod\u00e8les" is still allowed."""
        self.quiet('dix mod\u00e8les', 'we averaged 10 models')

    def test_a_chunk_with_no_grouped_numerals(self):
        self.quiet('irgendein Text', 'some prose with 8 layers and 2560 units')

    def test_reordering_and_rewording_around_the_numbers(self):
        self.quiet('60,000 exemples, 2.5 de temp\u00e9rature, 10.9% de WER, '
                   '58.9% de pr\u00e9cision.\n')

    def test_a_numeral_repeated_only_once_in_the_translation(self):
        """Presence, not count: a translation may state a figure once where
        the source stated it twice, and that is a wording choice."""
        self.quiet('La référence: 58.9%, WER 10.9%, 60,000 '
                   'exemples, température 2.5.\n',
                   SOURCE + 'Again, 58.9% and 58.9%.\n')

    def test_a_verbatim_bibliography(self):
        """The reference list is copied through, so it must never fire."""
        biblio = ('\\bibitem{SPM}\n\\newblock {\\em Signal Processing '
                  'Magazine, IEEE}, 29(6):82--97, 2012.\n')
        self.quiet(biblio, biblio)


class AUnitGluedToItsNumberStaysGlued(unittest.TestCase):
    r"""The separator rule missed these: the digits themselves do not move.

    French and German wrote `58.9 %` for `58.9%` and `10 ms` for `10ms`,
    thirteen times each. A page then carried `58.9 %` in a sentence and
    `58.9%` in the table that sentence was about, which is the contradiction
    the whole numerals rule exists to prevent. Found by reading the finished
    books, not by any check.
    """

    SOURCE = ('The baseline reaches 58.9% frame accuracy at a 10ms advance '
              'per frame, closing 28% of the gap.\n')

    def test_a_space_before_the_percent_sign(self):
        found = verify_chunk.check_numerals(
            self.SOURCE, self.SOURCE.replace('58.9%', '58.9 %'))
        self.assertEqual(len(found), 1)
        self.assertIn('58.9%', found[0]['detail'])

    def test_a_space_before_a_unit(self):
        found = verify_chunk.check_numerals(
            self.SOURCE, self.SOURCE.replace('10ms', '10 ms'))
        self.assertEqual(len(found), 1)

    def test_a_faithful_translation_is_quiet(self):
        self.assertEqual(verify_chunk.check_numerals(
            self.SOURCE, 'La référence atteint 58.9% par trame avec une '
                         'avance de 10ms, comblant 28% de l\'écart.\n'), [])


class AMyriadRegroupingIsNotARespelling(unittest.TestCase):
    r"""Korean, Japanese and Chinese count in myriads, so a magnitude word
    changes the digits legitimately: 1.4 billion is 14억, because 억 is 10^8.

    The first version of this check flagged that, and it took running it over
    five books shipped long beforehand to notice -- TinyVLA says "parameters
    ranging from 70 million to 1.4 billion". K163 again: a rule measured on
    one set of books fires on the next.
    """

    def test_a_decimal_before_a_magnitude_word(self):
        source = 'parameters ranging from 70 million to 1.4 billion.\n'
        self.assertEqual(verify_chunk.check_numerals(
            source, '70억에서 14억 개의 '
                    '파라미터.\n'), [])

    def test_but_a_decimal_with_no_magnitude_word_is_still_checked(self):
        source = 'it falls to 13.2 test errors on the set.\n'
        found = verify_chunk.check_numerals(source, 'passe à 13,2 erreurs.\n')
        self.assertEqual(len(found), 1)

    def test_a_bare_magnitude_suffix_is_not_checked_either(self):
        r"""`85M` is 8500만 in Korean, 8500万 in Japanese. A check that fires
        on every CJK book is the mistake K157 is about. The real defect is
        narrower -- one book printing both forms -- and this cannot see it."""
        source = 'to fit the 85M parameters of the baseline model.\n'
        self.assertEqual(verify_chunk.check_numerals(
            source, '기준 모델의 8500만 개 '
                    '파라미터.\n'), [])


class ItRunsOnEveryChunk(unittest.TestCase):

    def test_verify_chunk_calls_it(self):
        r"""A check nothing calls is a comment. `verify_chunk` is the per-chunk
        gate, and it has both the source and the translation in hand."""
        import io
        from pathlib import Path
        path = (Path(__file__).resolve().parents[1] / 'scripts'
                / 'verify_chunk.py')
        with io.open(path, encoding='utf-8') as handle:
            source = handle.read()
        body = source[source.index('def verify_chunk('):]
        self.assertIn('findings += check_numerals(source, output)', body)


if __name__ == '__main__':
    unittest.main()

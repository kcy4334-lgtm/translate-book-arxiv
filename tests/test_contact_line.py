# -*- coding: utf-8 -*-
r"""An address that is translated stops being an address.

Rescuing the affiliation from `\address` (K123) put a line of French street
address into the body of Maynard's first chunk, and to `untranslated_block`
that is twenty-five Latin words with no Korean. The check was right about what
it saw and wrong about what it meant: the line reached a translator, which
left it alone deliberately, exactly as the reference list is left alone.

The exemption is narrow because the check's failure mode is silence. Measured
over every output chunk in the corpus it skips one line — Maynard's — and
leaves all 62 higgs_atlas findings standing, which is correct: that paper
genuinely was never translated. ATLAS's own affiliation list keeps firing as
well, having neither a number nor an e-mail, and that is the right way round.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import verify_chunk as vc  # noqa: E402

MAYNARD = ('Centre de recherches mathématiques, Université de Montréal, '
           'Pavillon André-Aisenstadt, 2920 Chemin de la tour, Room 5357, '
           'Montréal (Québec) H3T 1J4 maynardj@dms.umontreal.ca')

PROSE = ('The Standard Model of particle physics has been tested by many '
         'experiments over the last four decades and describes with high '
         'accuracy all the phenomena observed so far')


class AContactLineIsRecognised(unittest.TestCase):
    def test_the_maynard_affiliation(self):
        self.assertTrue(vc.is_contact_line(MAYNARD))

    def test_an_address_without_an_email_but_with_a_number(self):
        self.assertTrue(vc.is_contact_line(
            'Computer Science Department, University of Freiburg, '
            'Georges-Koehler-Allee 052, 79110 Freiburg, Germany'))

    def test_an_email_alone_is_not_enough_without_the_commas(self):
        self.assertFalse(vc.is_contact_line('maynardj@dms.umontreal.ca'))


class OrdinaryProseIsNot(unittest.TestCase):
    def test_a_paragraph_that_never_reached_a_translator_still_fires(self):
        self.assertFalse(vc.is_contact_line(PROSE))
        found = vc.check_untranslated_blocks(PROSE, 'ko')
        self.assertEqual([f['check'] for f in found], ['untranslated_block'])

    def test_a_sentence_disqualifies_a_line_however_many_commas(self):
        self.assertFalse(vc.is_contact_line(
            'First, we note that a, b, c and 3 are distinct. Then we proceed.'))

    def test_the_atlas_affiliation_list_still_fires(self):
        # No number, no e-mail: not exempted. A check whose failure mode is
        # silence should err towards reporting.
        line = ('Department of Physics, Ankara University, Ankara; '
                'Department of Physics, Dumlupinar University, Kutahya; '
                'Department of Physics, Gazi University, Ankara; '
                'Turkish Atomic Energy Authority, Ankara, Turkey')
        self.assertFalse(vc.is_contact_line(line))


class TheExemptionReachesTheCheck(unittest.TestCase):
    def test_the_affiliation_line_is_not_reported(self):
        self.assertEqual(vc.check_untranslated_blocks(MAYNARD, 'ko'), [])

    def test_an_affiliation_beside_real_prose_hides_neither(self):
        found = vc.check_untranslated_blocks(MAYNARD + '\n\n' + PROSE, 'ko')
        self.assertEqual(len(found), 1)
        self.assertIn('Standard Model', found[0]['evidence'])

    def test_a_translated_line_is_untouched_by_either(self):
        self.assertEqual(
            vc.check_untranslated_blocks('이것은 한국어 문장이다.', 'ko'), [])


if __name__ == '__main__':
    unittest.main()

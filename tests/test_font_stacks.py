# -*- coding: utf-8 -*-
"""The Korean and math faces doctor.py checks are the faces the stacks name.

doctor.py checked Noto Serif KR/CJK for Korean while no stack named either,
so a Linux machine passed and its book printed Type3 on 14 of 16 pages. Its
math check accepted STIX and Latin Modern, which ship as CFF .otf and print as
Type3 too, while the formulas on that machine fell to FreeSerif because the
stacks named no face it had. Measured on Ubuntu 20.04 (layout.py has the
numbers). These tests hold the three places to one list.
"""
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, 'scripts')
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import doctor  # noqa: E402
import layout  # noqa: E402


def read(name):
    with open(os.path.join(SCRIPTS, name), encoding='utf-8') as f:
        return f.read()


def faces(stack):
    return [f.strip().strip('\'"') for f in stack.split(',')]


EBOOK = read('template_ebook.html')
KO_BLOCK = EBOOK[EBOOK.index('html:lang(ko) {'):]
KO_BLOCK = KO_BLOCK[:KO_BLOCK.index('}')]
ROOT_BLOCK = EBOOK[EBOOK.index(':root {'):]
ROOT_BLOCK = ROOT_BLOCK[:ROOT_BLOCK.index('}')]


def var(block, name):
    return faces(re.search(r'--%s:[ \t]*([^;]+);' % name, block).group(1))


class TheStacksNameWhatDoctorChecks(unittest.TestCase):
    def test_every_korean_serif_face_is_in_every_korean_serif_stack(self):
        ko = layout.LANG_CONFIG['ko']
        for stack in (faces(ko['font_family']), faces(ko['font_family_ebook']),
                      var(KO_BLOCK, 'p-serif')):
            for name, _needle in layout.KOREAN_SERIF_FACES:
                self.assertIn(name, stack)

    def test_every_korean_sans_face_is_in_the_korean_sans_stack(self):
        for name, _needle in layout.KOREAN_SANS_FACES:
            self.assertIn(name, var(KO_BLOCK, 'p-sans'))

    def test_the_truetype_math_faces_come_before_the_cff_ones(self):
        """A CFF math face ahead of a TrueType one would win on a machine
        that has both, and print the formulas as Type3."""
        tex_fallback = re.search(r'span\.math\.tex-fallback\s*\{\s*font-family:'
                                 r'\s*([^;]+);', read('template.html')).group(1)
        for stack in (var(ROOT_BLOCK, 'p-math'), var(KO_BLOCK, 'p-math'),
                      faces(tex_fallback)):
            names = [name for name, _needle in layout.MATH_FACES]
            for name in names:
                self.assertIn(name, stack)
            last_truetype = max(stack.index(n) for n in names)
            for cff in ('STIX Two Math', 'Latin Modern Math'):
                if cff in stack:
                    self.assertGreater(stack.index(cff), last_truetype)


class DoctorPassesOnlyAFaceABuildWillUse(unittest.TestCase):
    def korean(self, fonts):
        return doctor.check_font(doctor._needles(layout.KOREAN_SERIF_FACES),
                                 '', set(fonts))[0]

    def math(self, fonts):
        return doctor.check_font(doctor._needles(layout.MATH_FACES), '',
                                 set(fonts))[0]

    def test_noto_cjk_alone_is_not_a_korean_serif(self):
        self.assertFalse(self.korean(['notoserifcjk-regular.ttc',
                                      'notosanscjk-regular.ttc']))

    def test_each_named_korean_face_passes_by_its_file(self):
        for f in ('nanummyeongjo.ttf', 'nanummyeongjo-regular.ttf',
                  'hanbatang.ttf', 'batang.ttc'):
            self.assertTrue(self.korean([f]), f)

    def test_cff_math_faces_do_not_pass(self):
        self.assertFalse(self.math(['latinmodern-math.otf',
                                    'stixtwomath-regular.otf',
                                    'freeserif.ttf']))

    def test_each_truetype_math_face_passes_by_its_file(self):
        for f in ('cambria.ttc', 'dejavumathtexgyre.ttf',
                  'notosansmath-regular.ttf'):
            self.assertTrue(self.math([f]), f)


class DoctorReadsWhatFontconfigLists(unittest.TestCase):
    """On Ubuntu, fonts that fontconfig was pointed at outside the usual
    folders were used by the build and reported absent by doctor, because
    fc-list was read only when those folders were empty."""

    def test_a_font_only_fontconfig_knows_is_found(self):
        from unittest import mock
        listing = ('/opt/extra-fonts/NanumMyeongjo-Regular.ttf: \n'
                   '/usr/share/fonts/truetype/dejavu/DejaVuMathTeXGyre.ttf: \n')
        done = mock.Mock(stdout=listing)
        with mock.patch.object(doctor.os, 'name', 'posix'), \
                mock.patch.object(doctor.shutil, 'which', return_value='/usr/bin/fc-list'), \
                mock.patch.object(doctor.subprocess, 'run', return_value=done), \
                mock.patch.object(doctor.os.path, 'isdir', return_value=False):
            names = doctor._font_files()
        self.assertIn('nanummyeongjo-regular.ttf', names)
        self.assertIn('dejavumathtexgyre.ttf', names)


if __name__ == '__main__':
    unittest.main()

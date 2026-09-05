#!/usr/bin/env python3
"""
layout.py - Language and print-layout configuration.

Single source of truth for everything that depends on the output language or on
page geometry. Deliberately a LEAF module: it imports nothing from this project,
only the standard library. That makes an import cycle impossible by
construction, which matters because both merge_and_build.py and
calibre_html_publish.py need this data.

Two tables live here:

  LANG_CONFIG    per-language fonts and labels (moved out of merge_and_build.py,
                 which used to own it while calibre_html_publish.py kept a
                 second, silently drifting copy)
  PRINT_PROFILES page geometry and base type size for the PDF renderer
"""

# =============================================================================
# Language configuration
# =============================================================================
#
# Font-stack ordering rule: font-family is resolved PER CHARACTER, so a
# Latin-only face listed FIRST captures Latin letters, digits and punctuation
# while CJK characters -- absent from it -- fall through to the CJK face. That
# buys real italics and real bold for the embedded English, which most CJK
# faces cannot supply.
#
# Korean note: the faces below were chosen by measurement, not preference.
# Chromium's PDF writer cannot subset-embed a VARIABLE font; it falls back to
# one Type3 font object per glyph, which bloats the file ~8x and emits
# path-outline text instead of real text. NotoSerifKR-VF.ttf and
# NotoSansKR-VF.ttf are both variable and both fail this way (measured: 258 KB
# and 55 Type3 objects for a single page, vs 33 KB and zero for HCR Batang).
# 'HCR Batang' (Hancom's Korean serif) embeds cleanly as Type0 along with a
# real HCRBatang-Bold companion. Batang is the stock-Windows fallback; it
# embeds but has no bold face.

LANG_CONFIG = {
    'zh': {
        'lang_attr': 'zh-CN',
        # SimSun and Noto Serif SC are named rather than left to the generic
        # `serif`. FangSong is absent on a stock Windows outside China, and
        # what the generic keyword resolves to for Han script is the
        # browser's guess -- for Japanese on this machine it guessed a sans.
        # Naming a real serif makes the fallback a decision instead of luck.
        # The CFF Source Han faces are left out for the reason given under
        # `ja`: this Chromium emits them as Type3.
        'font_family': "'FangSong', '仿宋', 'STFangSong', '华文仿宋', "
                       "'Noto Serif SC', 'SimSun', serif",
        'font_family_ebook': '"FangSong", "FangSong_GB2312", "仿宋", '
                             '"仿宋_GB2312", "STFangSong", "Noto Serif SC", '
                             '"SimSun", serif',
        'figure_label': '图',
        'table_label': '表',
        # `式`, not `公式`. The cross-reference pass absorbs the word standing
        # in front of a key only when it matches the configured label, and a
        # Chinese translator writes `式 (eq:kl)` -- the same single-character
        # shape as 图, 表 and 节 above. With `公式` configured the two never
        # matched, so the template added its own word in front of the
        # translator's and the book printed `式 公式 (3)`, three times.
        # Korean is clean for this reason and no other: its translator
        # happens to write the label the config names.
        'equation_label': '式',
        'section_label': '节',
        'appendix_label': '附录',
        'algorithm_label': '算法',
        'theorem_label': '定理',
        'theorem_words': ('定理', '引理', '推论', '命题', '定义', '注', '例',
                          '事实', '观察', '猜想', '断言'),
        'ref_formats': {'section': '第{number}{label}'},
        'particle_agreement': False,
        'references_label': '参考文献',
        'toc_label': '目录',
        'pdf_font': 'FangSong',
    },
    'en': {
        'lang_attr': 'en',
        'font_family': "Georgia, 'Times New Roman', Times, serif",
        'font_family_ebook': 'Georgia, "Times New Roman", Times, serif',
        'figure_label': 'Figure',
        'table_label': 'Table',
        'equation_label': 'Equation',
        'section_label': 'Section',
        'appendix_label': 'Appendix',
        'algorithm_label': 'Algorithm',
        'theorem_label': 'Theorem',
        'theorem_words': ('Proposition', 'Observation', 'Conjecture',
                          'Corollary', 'Definition', 'Theorem', 'Example',
                          'Lemma', 'Remark', 'Claim', 'Fact'),
        'ref_formats': {},
        'particle_agreement': False,
        'references_label': 'References',
        'toc_label': 'Contents',
        'pdf_font': 'Georgia',
    },
    'ja': {
        'lang_attr': 'ja',
        # The first three Mincho faces are not portable: Hiragino is macOS,
        # Yu Mincho wants a Japanese Windows, MS Mincho ships with the
        # language pack. Measured on a Korean Windows with none of them
        # installed, the stack fell through to the generic `serif` and that
        # resolved to Yu GOTHIC -- a sans. A different serif is a matter of
        # preference; a sans where the design says serif is the wrong kind of
        # typeface for the script.
        #
        # The two added after them are TrueType-flavoured. Source Han Serif
        # JP was tried here and deliberately left out: it is CFF, and this
        # Chromium emits it as a Type3 font -- the failure this project
        # already refuses for Korean, where the rule is "static, 0 Type3".
        # Naming it would have made a machine WITHOUT a Mincho pick a Type3
        # serif over a cleanly embedded Gothic, which is worse than the
        # problem it was added to solve.
        'font_family': "'Hiragino Mincho ProN', 'Yu Mincho', 'MS Mincho', "
                       "'BIZ UDMincho', 'Noto Serif JP', serif",
        'font_family_ebook': '"Hiragino Mincho ProN", "Yu Mincho", '
                             '"MS Mincho", "BIZ UDMincho", "Noto Serif JP", '
                             'serif',
        'figure_label': '図',
        'table_label': '表',
        'equation_label': '式',
        'section_label': '節',
        'appendix_label': '付録',
        'algorithm_label': 'アルゴリズム',
        'theorem_label': '定理',
        'theorem_words': ('定理', '補題', '系', '命題', '定義', '注意', '例',
                          '事実', '観察', '予想', '主張'),
        'ref_formats': {'section': '第{number}{label}'},
        'particle_agreement': False,
        'references_label': '参考文献',
        'toc_label': '目次',
        'pdf_font': 'Hiragino Mincho ProN',
    },
    'ko': {
        'lang_attr': 'ko',
        'font_family': "'Noto Serif', 'HCR Batang', '함초롬바탕', Batang, serif",
        'font_family_ebook': '"Noto Serif", "HCR Batang", "함초롬바탕", "Batang", serif',
        'figure_label': '그림',
        'table_label': '표',
        'equation_label': '식',
        'section_label': '절',
        'ref_formats': {'section': '{number}{label}'},
        # Korean chooses a particle by the sound of the syllable before it, so
        # substituting a number into a finished sentence can leave the wrong
        # one standing: "그림 1를" instead of "그림 1을".
        'particle_agreement': True,
        'appendix_label': '부록',
        'algorithm_label': '알고리즘',
        'theorem_label': '정리',
        # Every word the translator may put in front of a theorem reference.
        # They all share one counter, so the label index cannot tell them
        # apart -- only the translator knows this particular number is a
        # Lemma. Without the list, resolving "보조정리 (Rudelson)" appends the
        # generic word and prints "보조정리 정리 28".
        'theorem_words': ('보조정리', '따름정리', '정리', '명제', '정의',
                          '비고', '예제', '예', '사실', '관찰', '추측', '주장'),
        'references_label': '참고문헌',
        'toc_label': '목차',
        'pdf_font': 'HCR Batang',
    },
    'fr': {
        'lang_attr': 'fr',
        'font_family': "Georgia, 'Times New Roman', Times, serif",
        'font_family_ebook': 'Georgia, "Times New Roman", Times, serif',
        'figure_label': 'Figure',
        'table_label': 'Tableau',
        'equation_label': 'Équation',
        'section_label': 'Section',
        'appendix_label': 'Annexe',
        'algorithm_label': 'Algorithme',
        'theorem_label': 'Théorème',
        'theorem_words': ('Proposition', 'Observation', 'Conjecture',
                          'Corollaire', 'Définition', 'Théorème', 'Exemple',
                          'Lemme', 'Remarque', 'Fait'),
        'ref_formats': {},
        'particle_agreement': False,
        'references_label': 'Références',
        'toc_label': 'Table des matières',
        'pdf_font': 'Georgia',
    },
    'de': {
        'lang_attr': 'de',
        'font_family': "Georgia, 'Times New Roman', Times, serif",
        'font_family_ebook': 'Georgia, "Times New Roman", Times, serif',
        'figure_label': 'Abbildung',
        'table_label': 'Tabelle',
        'equation_label': 'Gleichung',
        'section_label': 'Abschnitt',
        'appendix_label': 'Anhang',
        'algorithm_label': 'Algorithmus',
        'theorem_label': 'Satz',
        'theorem_words': ('Proposition', 'Beobachtung', 'Vermutung',
                          'Korollar', 'Definition', 'Beispiel', 'Bemerkung',
                          'Lemma', 'Folgerung', 'Satz', 'Fakt'),
        'ref_formats': {},
        'particle_agreement': False,
        'references_label': 'Literatur',
        'toc_label': 'Inhaltsverzeichnis',
        'pdf_font': 'Georgia',
    },
    'es': {
        'lang_attr': 'es',
        'font_family': "Georgia, 'Times New Roman', Times, serif",
        'font_family_ebook': 'Georgia, "Times New Roman", Times, serif',
        'figure_label': 'Figura',
        'table_label': 'Tabla',
        'equation_label': 'Ecuación',
        'section_label': 'Sección',
        'appendix_label': 'Apéndice',
        'algorithm_label': 'Algoritmo',
        'theorem_label': 'Teorema',
        'theorem_words': ('Proposición', 'Observación', 'Conjetura',
                          'Corolario', 'Definición', 'Teorema', 'Ejemplo',
                          'Lema', 'Nota', 'Hecho'),
        'ref_formats': {},
        'particle_agreement': False,
        'references_label': 'Referencias',
        'toc_label': 'Índice',
        'pdf_font': 'Georgia',
    },
}

# Default fallback for unknown languages
DEFAULT_LANG_CONFIG = {
    'lang_attr': 'en',
    'figure_label': 'Figure',
    'table_label': 'Table',
    'equation_label': 'Equation',
    'section_label': 'Section',
    'appendix_label': 'Appendix',
    'algorithm_label': 'Algorithm',
    'theorem_label': 'Theorem',
    # See the ko entry: theorem-likes share one counter, so the index knows
    # the number but not which word belongs in front of it.
    'theorem_words': ('Proposition', 'Observation', 'Conjecture', 'Corollary',
                      'Definition', 'Theorem', 'Example', 'Lemma', 'Remark',
                      'Claim', 'Fact'),
    'ref_formats': {},
    'references_label': 'References',
    'font_family': "Georgia, 'Times New Roman', Times, serif",
    'font_family_ebook': 'Georgia, "Times New Roman", Times, serif',
    'toc_label': 'Contents',
    'pdf_font': 'Georgia',
}

# Private alias kept so merge_and_build.py can re-export the old name.
_DEFAULT_LANG_CONFIG = DEFAULT_LANG_CONFIG


def get_lang_config(lang_code):
    """Get language config, falling back to defaults for unknown languages."""
    return LANG_CONFIG.get(lang_code, DEFAULT_LANG_CONFIG)


def get_lang_config_loose(lang):
    """Resolve 'zh-CN' / 'ko-KR' / 'KO' / None to a LANG_CONFIG entry.

    calibre_html_publish.py is handed lang_attr values ('zh-CN'), while
    merge_and_build.py holds short codes ('zh'). One table, two doors.
    """
    key = (lang or '').lower().replace('_', '-').split('-')[0]
    return LANG_CONFIG.get(key, DEFAULT_LANG_CONFIG)


# =============================================================================
# Print profiles
# =============================================================================
#
# Geometry is stored as NUMBERS, not as a CSS string, because two consumers
# need different forms of it: template_ebook.html wants a `margin:` shorthand,
# and chromium_pdf.stamp_page_numbers() needs margin_bottom_mm as a float to
# place the folio. Deriving both from one dict is what keeps the stamped page
# number from colliding with the text block.
#
# 'a4-book' arithmetic (Korean body text, A4 210x297mm):
#     width  210 - 18 - 18 = 174mm = 493.2pt
#            493.2 / (0.966em x 11.5pt) = 44.4 Hangul per line   [target 35-45]
#     height 297 - 18 - 22 = 257mm = 728.5pt
#            728.5 / (11.5 x 1.75)      = 36.2 lines per page
# The bottom margin is 4mm deeper than the top so the stamped folio gets a
# clear band and the text block sits optically centred.

TEMPLATE_TOKENS = ('page_size', 'page_margin', 'print_font_size',
                   'print_line_height', 'h1_break_before',
                   'h1_page_break_before')

# section_break: start every top-level heading on a fresh page.
# OFF by default, and that default is measured rather than assumed: in this
# pipeline h1 is every top-level section (Introduction, Method, Experiments,
# ...), not a chapter. On a real 17-page paper turning it on produced 21
# pages and left ~4.7 pages' worth of trailing whitespace, against ~0.9
# with it off.
_PAGE_NUMBER_DEFAULTS = {
    'section_break': False,
    'page_number': True,
    'page_number_font_size_pt': 9.0,
    'page_number_skip_first': 1,
    'page_number_position': 'bottom-center',
}

PRINT_PROFILES = {
    # Default. Print readability first: large type, tight margins.
    'a4-book': dict(_PAGE_NUMBER_DEFAULTS,
                    page_size='A4',
                    margin_top_mm=18.0, margin_right_mm=18.0,
                    margin_bottom_mm=22.0, margin_left_mm=18.0,
                    base_font_size_pt=11.5, line_height=1.75),
    # Larger type; measure drops to ~39 Hangul/line.
    'a4-large': dict(_PAGE_NUMBER_DEFAULTS,
                     page_size='A4',
                     margin_top_mm=18.0, margin_right_mm=18.0,
                     margin_bottom_mm=22.0, margin_left_mm=18.0,
                     base_font_size_pt=13.0, line_height=1.80),
    # Fewer pages. Still far clear of the old Calibre 25.4mm default.
    'a4-dense': dict(_PAGE_NUMBER_DEFAULTS,
                     page_size='A4',
                     margin_top_mm=15.0, margin_right_mm=15.0,
                     margin_bottom_mm=18.0, margin_left_mm=15.0,
                     base_font_size_pt=10.5, line_height=1.60),
    # US Letter equivalent of a4-book.
    'letter-book': dict(_PAGE_NUMBER_DEFAULTS,
                        page_size='Letter',
                        margin_top_mm=18.0, margin_right_mm=20.0,
                        margin_bottom_mm=22.0, margin_left_mm=20.0,
                        base_font_size_pt=11.5, line_height=1.75),
}

DEFAULT_PRINT_PROFILE = 'a4-book'


def get_print_profile(name=None, overrides=None):
    """Return a print profile by name, falling back to the default.

    Always returns a fresh dict; PRINT_PROFILES is never mutated.
    """
    cfg = dict(PRINT_PROFILES.get(name or DEFAULT_PRINT_PROFILE,
                                  PRINT_PROFILES[DEFAULT_PRINT_PROFILE]))
    if overrides:
        cfg.update(overrides)
    return cfg


def docx_fonts(lang_cfg):
    """(latin_face, cjk_face) for the Word reference document.

    Word needs the two split apart -- w:ascii/w:hAnsi for Latin and
    w:eastAsia for CJK -- where CSS just takes an ordered stack. The stack is
    already ordered Latin-first for exactly this reason, so the CJK face is
    pdf_font and the Latin face is the first entry that is not it.
    """
    cjk = (lang_cfg or {}).get('pdf_font') or 'Georgia'
    stack = (lang_cfg or {}).get('font_family_ebook', '') or ''
    for raw in stack.split(','):
        name = raw.strip().strip('"').strip("'")
        if name and name != cjk and not name.endswith('serif'):
            return name, cjk
    return 'Georgia', cjk


HEADING_FONTS = {
    'ko': ('Noto Sans', 'Malgun Gothic'),
    'ja': ('Noto Sans', 'Yu Gothic'),
    'zh': ('Noto Sans', 'Microsoft YaHei'),
}


def docx_heading_fonts(lang_cfg):
    """(latin, cjk) for Word headings.

    Gothic headings over a serif body: the same pairing the print stylesheet
    uses, and the dominant convention in Korean and Japanese typesetting.
    """
    lang = (lang_cfg or {}).get('lang_attr', 'en').lower().split('-')[0]
    if lang in HEADING_FONTS:
        return HEADING_FONTS[lang]
    latin, _cjk = docx_fonts(lang_cfg)
    return latin, latin


def page_size_mm(cfg):
    """(width, height) in mm for the profile's paper."""
    return (215.9, 279.4) if cfg.get('page_size') == 'Letter' else (210.0, 297.0)


def page_margin_css(cfg):
    """CSS `margin` shorthand for @page, in top right bottom left order."""
    return ' '.join('{0:g}mm'.format(cfg['margin_{0}_mm'.format(side)])
                    for side in ('top', 'right', 'bottom', 'left'))


def template_values(cfg):
    """The $token$ values template_ebook.html consumes.

    Keys must exactly equal TEMPLATE_TOKENS -- tests/test_layout.py asserts it,
    because a token present in _TEMPLATE_TOKEN_RE but missing from this dict
    raises KeyError inside the substitution.
    """
    section_break = bool(cfg.get('section_break', False))
    return {
        'page_size': cfg['page_size'],
        'page_margin': page_margin_css(cfg),
        'print_font_size': '{0:g}pt'.format(cfg['base_font_size_pt']),
        'print_line_height': '{0:g}'.format(cfg['line_height']),
        # Both spellings: the modern property and the legacy alias, which
        # take different keywords ('page' vs 'always').
        'h1_break_before': 'page' if section_break else 'auto',
        'h1_page_break_before': 'always' if section_break else 'auto',
    }

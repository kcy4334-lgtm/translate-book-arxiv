#!/usr/bin/env python3
"""
consistency_probe.py - Defects a READER of the finished book would notice.

Not named test_*.py: it needs a built temp dir, so `unittest discover` must not
collect it.

    python tests/consistency_probe.py <temp_dir> --lang ko [--strict]

layout_probe measures the page. format_probe checks that each output format
carries the same tables and images. Neither looks at the words, and every
defect below shipped at least once with both of those green:

  * "식 식 (5)을 풀면"   - the substitution absorbed the English reference word
                          but not the Korean one the translator wrote (36 of
                          these across three papers)
  * 멱법칙 and 거듭제곱 법칙 for the same English term, because forty chunks
    were translated by forty sub-agents that could not see each other
  * 대리 손실(proxy loss) in one chunk and 대리 손실(surrogate loss) in another
  * `\\cellcolor{...}` and `{\\rm max}` printing as literal text
  * "(sec:method)" printed where a section number belongs
  * a heading left in English, which also loses its bilingual annotation

The chunk checks compare each translated chunk against its untouched English
source, which is the only reference that cannot itself have drifted.
"""

import argparse
import glob
import json
import io
import os
import re
import sys
from collections import Counter, defaultdict

B = chr(92)

# --- what a reader actually sees --------------------------------------------
#
# <annotation encoding="application/x-tex"> carries the TeX source of every
# rendered formula, and <style> survives tag-stripping. Counting either as
# "visible" reports correctly-rendered equations and CSS comments as defects.
_STYLE_RE = re.compile(r'(?s)<style\b.*?</style>')
_SCRIPT_RE = re.compile(r'(?s)<script\b.*?</script>')
_ANNOTATION_RE = re.compile(r'(?s)<annotation\b[^>]*>.*?</annotation>')
_TAG_RE = re.compile(r'<[^>]+>')

_LATEX_CMD_RE = re.compile(re.escape(B) + r'([a-zA-Z]{2,})')
_INLINE_MATH_RE = re.compile(r'\$[^$\n]{1,120}\$')
_RAW_REF_RE = re.compile(
    r'\((?:sec|subsec|eq|eqn|alg|app|fig|tab|thm|lem|def|prop|cor)'
    r'[:.][A-Za-z0-9_:\-]+\)')

# `한국어(English)` -- at most three words, starting at a script boundary.
_GLOSS_RE = re.compile(
    r'(?<![가-힣぀-ヿ一-鿿])'
    r'((?:[가-힣぀-ヿ一-鿿]+ ){0,2}'
    r'[가-힣぀-ヿ一-鿿]+)\(([A-Za-z][^()]{2,44})\)')
# `Tseng et al. 2024c` is a citation. The trailing letter that disambiguates
# two papers from one year also defeats a `\b` after the digits, so the year
# has to allow it -- otherwise the citation reads as an English gloss and
# `양자화` is reported as clashing with a surname.
_YEAR_RE = re.compile(r'\b(?:19|20)\d{2}[a-z]?\b')

_SCRIPT_RANGES = {
    'ko': (0xAC00, 0xD7A3),
    'ja': (0x3040, 0x30FF),
    'zh': (0x4E00, 0x9FFF),
}

# Renderings a Korean translator picks between. One book should use one.
_DOUBLETS = {
    'ko': [
        ('power law', ['멱법칙', '거듭제곱 법칙', '거듭제곱법칙']),
        ('noise', ['잡음', '노이즈']),
        ('task', ['태스크', '과제']),
        ('robust', ['견고', '강건', '로버스트']),
        ('front', ['프런트', '프론트']),
        ('outlier', ['이상치', '아웃라이어']),
        ('threshold', ['임계값', '문턱값']),
        ('gradient', ['기울기', '그래디언트']),
        ('inference', ['추론', '인퍼런스']),
        ('baseline', ['베이스라인', '기준선']),
        ('projection', ['프로젝션', '사영']),
        # Deliberately NOT here: layer/계층 and overhead/추가 비용. Both
        # minority forms are ordinary words that occur inside other words
        # (계층적 "hierarchical"), so they only ever produced false alarms.
    ],
}

# One Korean word doing two technical jobs. The inverse of _DOUBLETS: there
# the same concept got two words, here two concepts share one, which is worse
# because nothing on the page marks it. Each entry names the senses and the
# English cues that prove BOTH senses are really in this paper -- the check
# only fires when the source carries both, so a book that happens to use the
# word for one sense is left alone.
#
# Deliberately NOT here: 표현 (representation/expression) and 변환
# (transform/conversion). Korean uses one word for both in ordinary technical
# prose without ambiguity, so they produced only noise.
_HOMOGRAPHS = {
    'ko': [
        ('적합', r'(?<!\uacfc)\uc801\ud569', [
            ('fit', ['fitting', 'fitted', 'we fit', 'is fit', 'are fit',
                     'fit a', 'fit the', 'power-law fit', 'tail fit']),
            ('suitable', ['suitable', 'appropriate', 'better suited',
                          'more suited', 'is apt']),
        ]),
        ('\uc815\uaddc\ud654', None, [
            ('normalization', ['normalization', 'normalized', 'normalize',
                               'normalisation']),
            ('regularization', ['regularization', 'regularized', 'regularize',
                                'regularisation']),
        ]),
        ('\uc815\ub82c', None, [
            ('sorting', ['sorted', 'sorting', 'ascending order',
                         'descending order']),
            ('alignment', ['aligned', 'alignment', 'align ']),
        ]),
        ('\ubd84\ud574', None, [
            ('decomposition', ['decomposition', 'decompose', 'decomposed']),
            ('factorization', ['factorization', 'factorized',
                               'factorisation']),
        ]),
    ],
}

# "\uc808\ub2e8 \uba71\ubc95\uce59" on one page and "\uc808\ub2e8\ub41c \uba71\ubc95\uce59" on another are the same
# term spelled two ways. Restricted to head nouns the glossary knows, because
# without that restriction ordinary Korean ("\uc81c\uc548 \ubc29\ubc95" / "\uc81c\uc548\ub41c \ubc29\ubc95") fires
# constantly and the signal drowns.
# Stems that are connectives rather than terms. "캘리브레이션 기반 양자화"
# (X-based) and "반올림에 기반한 양자화" (based on X) are different
# constructions that happen to share a shape, not one term spelled two ways --
# and a check whose findings are mostly like that is a check people stop
# reading.
_DRIFT_STEM_STOP = frozenset([
    '기반', '관련', '사용', '제안', '언급', '포함', '위치', '대응', '해당',
])

_DRIFT_RE = re.compile(r'([\uac00-\ud7a3]{2,6})(\ub41c|\ud55c)\s+([\uac00-\ud7a3]{2,10})')


# Reference words, per language, for the doubled-label check.
_REF_WORDS = {
    'ko': ['그림', '표', '식', '절', '부록', '알고리즘', '정리'],
    'ja': ['図', '表', '式', '節', '付録'],
    'zh': ['图', '表', '式', '节', '附录'],
}
_ENGLISH_REF = (r'Figs?|Figures?|Tabs?|Tables?|Secs?|Sections?|Eqs?|Eqn|'
                r'Equations?|App|Appendix|Algs?|Algorithms?')


def read(path):
    with open(path, encoding='utf-8', errors='replace') as fh:
        return fh.read()


def visible_text(html):
    """The characters a reader sees, with markup and math source removed."""
    text = _SCRIPT_RE.sub(' ', _STYLE_RE.sub(' ', html))
    text = _ANNOTATION_RE.sub(' ', text)
    return _TAG_RE.sub(' ', text)


def in_target_script(text, lang):
    lo, hi = _SCRIPT_RANGES.get(lang, (0, 0))
    if not hi:
        return True
    return any(lo <= ord(ch) <= hi for ch in text)


def is_citation(text):
    return bool(_YEAR_RE.search(text))


# A word ending this way is grammar in front of the term, not part of it.
# The gloss pattern takes up to two preceding words so that `블록 대각 행렬`
# survives whole, and that same window drags in `절에서는` and `수행한`,
# which made one `어블레이션` look like three different renderings.
_CONTEXT_TAIL_RE = re.compile(
    r'(?:은|는|이|가|을|를|의|에|에서|에서는|에는|와|과|로|으로|도|만|부터'
    r'|까지|별|한|된|하는|되는|있는|없는|따른|위한|대한|같은)$')


def _trim_leading_context(native):
    r"""`절에서는 어블레이션` -> `어블레이션`; `블록 대각 행렬` unchanged."""
    words = native.split()
    while len(words) > 1 and _CONTEXT_TAIL_RE.search(words[0]):
        words.pop(0)
    return ' '.join(words)


def _is_acronym_of(short, long_form):
    """`PTQ` beside `post-training quantization` is practice, not a clash."""
    letters = re.sub(r'[^A-Za-z]', '', short)
    # Not all-caps: this field writes its acronyms MoE, LoRA, GeLU. Demanding
    # PTQ-style capitals missed those and reported them as term clashes.
    if not letters or letters == letters.lower() or len(letters) > 6:
        return False
    initials = ''.join(w[0] for w in re.findall(r'[A-Za-z]+', long_form))
    return letters.lower() in (initials.lower(), initials.lower()[:len(letters)])


def _same_term(candidates):
    """One candidate ending with another is the same term with more context.

    The gloss pattern also catches the words in front of the term, so
    `종단 간`, `에서의 종단 간` and `형식의 종단 간` are one term seen three
    times, not three renderings.
    """
    shortest = min(candidates, key=len)
    if all(c.endswith(shortest) for c in candidates):
        return True
    # Trimming the front only reaches words the tail list knows, and it stops
    # at the first one it does not: `가장 높은 양자화된` keeps all three words
    # because `가장` is neither a particle nor an ending. Comparing the head
    # noun instead needs no list -- `계산 오버헤드` and `추론 오버헤드` are the
    # same term glossed once, since the gloss annotates the noun, not the
    # modifier in front of it.
    tails = {c.split()[-1] for c in candidates if c.split()}
    return len(tails) == 1


# --- the checks --------------------------------------------------------------

def check_visible_latex(html):
    """LaTeX that reached the page as literal text."""
    text = visible_text(html)
    commands = Counter(_LATEX_CMD_RE.findall(text))
    math = _INLINE_MATH_RE.findall(text)
    envs = Counter(re.findall(re.escape(B) + r'begin\{([a-zA-Z*]+)\}', text))
    return commands, math, envs


def check_unresolved_refs(html):
    return Counter(_RAW_REF_RE.findall(visible_text(html)))


# The particles that may follow a label without making it a different word.
_PARTICLE_RE = (r'(?:으로|에서|에게|부터|까지|보다|처럼|마다|조차|밖에|라도'
                r'|이나|을|를|이|가|은|는|에|의|와|과|로|도|만|나)')


def check_doubled_labels(html, lang):
    """"식 식 (5)" -- the emitted label landed beside the one already there."""
    words = _REF_WORDS.get(lang)
    if not words:
        return []
    alt = '|'.join(map(re.escape, words))
    text = re.sub(r'[ \t ]+', ' ', visible_text(html))
    # A label may be followed by a particle and still be doubled:
    # `3.2절 절을 따라`. The bare (?![가-힣]) guard misses every one of
    # those, which is most of them in Korean. It cannot simply be
    # dropped either -- 표 is also the first syllable of 표현/표시/표준.
    # The same guard is needed in front. 식 is also the last syllable of
    # 방식, so "Sinkhorn-Knopp 방식 알고리즘을" -- an ordinary sentence --
    # read as the label 식 doubled by the label 알고리즘.
    doubled = re.compile(
        r'(?<![가-힣])(%s) ?(%s)(?:(?![가-힣])|(?=%s(?![가-힣])))'
        % (alt, alt, _PARTICLE_RE))
    mixed = re.compile(r'(?:%s) ?(?:%s)\.?' % (alt, _ENGLISH_REF))
    out = []
    for m in list(doubled.finditer(text))[:20]:
        out.append(('doubled', m.group(0), text[max(0, m.start() - 40):m.start() + 40]))
    for m in list(mixed.finditer(text))[:20]:
        out.append(('mixed', m.group(0), text[max(0, m.start() - 40):m.start() + 40]))
    return out


def check_glosses(text):
    """`한국어(English)` used inconsistently, in either direction."""
    ko_to_en, en_to_ko, seen = defaultdict(set), defaultdict(set), Counter()
    for m in _GLOSS_RE.finditer(text):
        native, english = m.group(1).strip(), m.group(2).strip()
        if is_citation(english) or '$' in english:
            # `평균 제로샷 정확도(Avg. $\uparrow$)` is a column label, not a gloss.
            continue
        # Keep the original casing for ko_to_en: the acronym test below needs
        # it (PTQ is an acronym, ptq is not). Fold case only when grouping the
        # other way, where Block and block are one word.
        ko_to_en[native].add(english)
        # Trimmed only on this side. Grouping by English asks whether one term
        # was rendered several ways, and the words the pattern drags in front
        # of it are not renderings. Grouping by Korean asks the opposite, and
        # there `채널별 양자화` and `양자화` are two terms, not one.
        en_to_ko[english.lower()].add(_trim_leading_context(native))
        seen[(native, english.lower())] += 1
    problems = []
    for native, englishes in sorted(ko_to_en.items()):
        if len(englishes) < 2:
            continue
        forms = sorted(englishes)
        if len({f.lower() for f in forms}) < 2:
            continue        # Block vs block is one word
        if any(_is_acronym_of(a, b) for a in forms for b in forms if a != b):
            continue        # an acronym beside its expansion is practice
        problems.append('one term, several English: %s -> %s' % (native, forms))
    for english, natives in sorted(en_to_ko.items()):
        if len(natives) > 1 and not _same_term(natives):
            problems.append('one English, several terms: %s -> %s'
                            % (english, sorted(natives)))
    for (native, english), n in sorted(seen.items()):
        # Twice is the normal shape: once where the term is introduced and once
        # in a terminology appendix that re-defines it. Three times is a term
        # nobody remembered was already glossed.
        if n > 2:
            problems.append('glossed %d times, should be once: %s(%s)'
                            % (n, native, english))
    return problems



def _source_text(temp_dir):
    """Every source chunk, concatenated. The original English, not ours."""
    parts = []
    for path in sorted(glob.glob(os.path.join(temp_dir, 'chunk*.md'))):
        if os.path.basename(path).startswith('output_'):
            continue
        parts.append(read(path))
    return '\n'.join(parts)


def check_homographs(merged, source, lang):
    """A Korean word worth checking: the source keeps two senses apart.

    A POINTER, not a verdict. It knows the word is in the translation and
    that both senses are somewhere in the paper; it does not know which
    sense each occurrence carries. Read the occurrences before acting.
    """
    out = []
    for word, pattern, senses in _HOMOGRAPHS.get(lang, []):
        uses = (len(re.findall(pattern, merged)) if pattern
                else merged.count(word))
        if uses < 2:
            continue
        low = source.lower()
        present = [name for name, cues in senses
                   if any(cue.lower() in low for cue in cues)]
        if len(present) > 1:
            out.append('%s x%d: the source keeps %s apart -- read the '
                       'occurrences and check which sense each one carries'
                       % (word, uses, ' and '.join(present)))
    return out


def check_term_drift(merged, temp_dir):
    """The same term spelled two ways: "X Y" here, "X된 Y" there."""
    known = set()
    path = os.path.join(temp_dir, 'glossary.json')
    if os.path.isfile(path):
        try:
            with io.open(path, encoding='utf-8') as handle:
                for entry in json.load(handle).get('terms', []):
                    target = (entry.get('target') or '').strip()
                    if len(target) >= 2:
                        known.add(target)
        except (ValueError, OSError):
            pass
    if not known:
        return []
    out, seen = [], set()
    for match in _DRIFT_RE.finditer(merged):
        stem, suffix, head = match.groups()
        if head not in known or (stem, head) in seen:
            continue
        if stem in _DRIFT_STEM_STOP:
            continue
        bare = '%s %s' % (stem, head)
        if bare in merged:
            seen.add((stem, head))
            out.append('"%s" x%d vs "%s%s %s" x%d'
                       % (bare, merged.count(bare), stem, suffix, head,
                          merged.count(match.group(0))))
    return out


def check_doublets(text, lang):
    """One English term rendered two ways inside one book."""
    out = []
    for label, forms in _DOUBLETS.get(lang, []):
        present = [(f, text.count(f)) for f in forms if text.count(f)]
        if len(present) > 1:
            out.append('%s: %s' % (label, ', '.join('%s x%d' % p for p in present)))
    return out


_PLACEHOLDER_RE = re.compile('⟦[MCT]\\d+⟧')
_HEADING_RE = re.compile(r'(?m)^(#+) +(.*)$')
_IMAGE_RE = re.compile(r'!\[[^\]]*\]\(([^)]+)\)')
# Only DATA values: Korean renumbers ordinary quantities by convention
# ("100 billion" -> "1,000억"), and flagging those buries the real ones.
_DATA_NUM_RE = re.compile(r'\d+\.\d+|\d{4,}')
_ENV_RE = re.compile(re.escape(B) + r'(begin|end)\{([a-zA-Z*]+)\}')


_TRUNCATION_FLOOR = 0.40
_TRUNCATION_MIN_CHARS = 800


def book_compression(lengths):
    """The ratio this book's chunks normally come out at, or None.

    `lengths` is (source chars, translated chars) per chunk.
    """
    return _verify_chunk.median_ratio(
        float(out) / src for src, out in lengths
        if src >= _TRUNCATION_MIN_CHARS and src)


def looks_truncated(src_len, out_len, book=None):
    """Is this translation too short to still hold its source's content?

    A sub-agent that stops early loses whole paragraphs and nothing else
    notices: the placeholders it did copy still balance, and the headings it
    did reach still ladder correctly. Only the bulk gives it away.

    The floor used to be a constant, and the constant was fitted to Korean:
    38 chunks of three papers, ratio 0.52 to 1.00. Chinese says the same
    thing in fewer characters again -- one paper translated into seven
    languages runs 0.35 to 0.39 for zh against 0.43 to 0.50 for ko, 0.51 to
    0.57 for ja and 1.14 to 1.27 for the Latin three -- so a Korean floor of
    0.40 failed every Chinese chunk of a book that was complete, headings,
    placeholders and paragraphs all matching.

    So compare a chunk against its own book instead of against a number. A
    book's chunks compress alike: within one edition the spread is under 10%
    of the median, while a chunk that stopped early is around half. `book` is
    the median from `book_compression`; without it the old constant stands.
    """
    if src_len < _TRUNCATION_MIN_CHARS:
        return False
    return out_len < src_len * _verify_chunk.truncation_floor(
        book, _TRUNCATION_FLOOR)


_MATH_EL_RE = re.compile(r'<math\b[^>]*>.*?</math>', re.DOTALL)
_TAG_RE = re.compile(r'<[^>]+>')


def check_broken_math(html):
    """(formulas that render as nothing, <merror> count).

    A formula that renders to nothing still counts as a formula everywhere
    else: the <math> element is there, its <annotation> is there, and every
    parity check between the formats agrees. SINQ's `\\textbf{Overhead [\\%]}`
    -- the units of a column -- was read back as display maths holding one
    `%` and drew nothing, so the header said "오버헤드" and stopped.
    """
    blank = 0
    for element in _MATH_EL_RE.findall(html):
        if not _TAG_RE.sub('', _ANNOTATION_RE.sub('', element)).strip():
            blank += 1
    return blank, len(re.findall(r'<merror\b', html))


def check_chunks(temp_dir, lang):
    """Each translated chunk against its untouched English source."""
    problems = []
    bulk = []
    for src_path in sorted(glob.glob(os.path.join(temp_dir, 'chunk*.md'))):
        name = os.path.basename(src_path)
        if name.startswith('output_'):
            continue
        out_path = os.path.join(temp_dir, 'output_' + name)
        if not os.path.isfile(out_path):
            continue
        src, out = read(src_path), read(out_path)

        a = Counter(_PLACEHOLDER_RE.findall(src))
        b = Counter(_PLACEHOLDER_RE.findall(out))
        if a != b:
            problems.append('%s: placeholders %s' % (name, dict((a - b) + (b - a))))
        repeated = [t for t, n in b.items() if n > 1]
        if repeated:
            problems.append('%s: placeholder repeated %s' % (name, repeated))

        src_h, out_h = _HEADING_RE.findall(src), _HEADING_RE.findall(out)
        if [len(h) for h, _t in src_h] != [len(h) for h, _t in out_h]:
            problems.append('%s: heading ladder %d -> %d'
                            % (name, len(src_h), len(out_h)))
        # A single-token heading is a name the paper itself uses -- AlphaQ,
        # SINQ -- and translating it would be wrong. Only a multi-word English
        # heading is a heading the translator skipped.
        english = [t for _h, t in out_h
                   if ' ' in t.strip() and not in_target_script(t, lang)]
        if english:
            problems.append('%s: heading not translated %s' % (name, english[:3]))

        if _IMAGE_RE.findall(src) != _IMAGE_RE.findall(out):
            problems.append('%s: image references changed' % name)

        src_e = Counter('%s{%s}' % p for p in _ENV_RE.findall(src))
        out_e = Counter('%s{%s}' % p for p in _ENV_RE.findall(out))
        if src_e != out_e:
            problems.append('%s: LaTeX envs %s'
                            % (name, dict((src_e - out_e) + (out_e - src_e))))

        lost = (Counter(_DATA_NUM_RE.findall(_PLACEHOLDER_RE.sub(' ', src)))
                - Counter(_DATA_NUM_RE.findall(_PLACEHOLDER_RE.sub(' ', out))))
        if lost:
            problems.append('%s: data values lost %s'
                            % (name, dict(list(lost.items())[:6])))

        # A sub-agent that stops early loses whole paragraphs and nothing
        # above notices: the placeholders it did copy still balance, and the
        # headings it did reach still ladder correctly. Only the bulk gives
        # it away. Judged after the loop, against this book's own
        # compression, because a constant floor is a floor fitted to one
        # language.
        bulk.append((name,
                     len(_PLACEHOLDER_RE.sub(' ', src).strip()),
                     len(_PLACEHOLDER_RE.sub(' ', out).strip())))

    book = book_compression([(s, o) for _n, s, o in bulk])
    for name, src_body, out_body in bulk:
        if looks_truncated(src_body, out_body, book):
            problems.append('%s: translation is %.0f%% the length of its '
                            'source, against %.0f%% for the rest of this '
                            'book — content may be missing'
                            % (name, 100.0 * out_body / max(1, src_body),
                               100.0 * (book or _TRUNCATION_FLOOR)))
    return problems


_HANGUL_RE = re.compile(r'[가-힣]')

SCRIPT_DIR = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'scripts')
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

# The same detector the merge deduplicates with. Two copies of "is this a
# gloss or a unit?" would drift, and then the floor and the ceiling would be
# arguing about different sentences.
import glossary as _glossary                                     # noqa: E402

# Same reason again. The truncation floor lives in `verify_chunk`, which is
# the gate; this probe reports on the same books. Two copies of "is this
# chunk too short?" drifted once already -- a Korean constant of 0.40 here
# and 0.35 there -- and the two disagreed about a complete Chinese book.
# Bound after the functions above are defined, which is fine: they are
# called from main(), long after this module has finished loading.
import verify_chunk as _verify_chunk                             # noqa: E402

_GLOSS_PAREN_RE = _glossary._GLOSS_RE
_looks_like_gloss = _glossary._is_first_use_gloss


def check_gloss_coverage(text, temp_dir):
    r"""Which translated terms carry their English the first time they appear?

    `check_glosses` above is a CEILING: it complains when one term is glossed
    three times. Nothing was ever a floor, and that asymmetry cost three
    books about half their first-use English between one version and the
    next. Nobody removed it. The term tables simply got bigger and more
    authoritative, so the sub-agents stopped annotating the terms the table
    already decided for them, and no number moved.

    This CANNOT prove that a term deserves a gloss — that is a judgement
    about the reader, not a fact about the file — so it does not pretend to.
    The headline is a COUNT, not a ratio: most glossary entries (accuracy,
    baseline, benchmark) need no gloss at all, so a percentage against the
    glossary would read like 6% of a target that does not exist, and a
    misleading number is one people learn to skip. The count is comparable
    between two builds of the same book, which is the comparison that would
    have caught this.

    Returns (count, glossed, eligible), or None when there is no glossary.
    `count` is every first-use gloss in the text; `eligible`/`glossed` cover
    only the glossary's own terms, as a list to read rather than a score.
    """
    path = os.path.join(temp_dir, 'glossary.json')
    if not os.path.isfile(path):
        return None
    with io.open(path, encoding='utf-8') as fh:
        terms = json.load(fh).get('terms', [])
    count = sum(1 for m in _GLOSS_PAREN_RE.finditer(text)
                if _looks_like_gloss(' '.join(m.group(1).split())))
    glossed, eligible = [], []
    for term in terms:
        source = (term.get('source') or '').strip()
        target = (term.get('target') or '').strip()
        if not source or not target or source == target:
            continue
        if not _HANGUL_RE.search(target):
            continue                    # kept in English; nothing to gloss
        if target not in text:
            continue                    # the term never comes up in this book
        eligible.append(source)
        if re.search(r'%s\s*\(\s*%s' % (re.escape(target), re.escape(source)),
                     text, re.IGNORECASE):
            glossed.append(source)
    return count, glossed, eligible


def probe(temp_dir, lang='ko', strict=False):
    html_path = os.path.join(temp_dir, 'book_doc.html')
    if not os.path.isfile(html_path):
        print('ERROR: no book_doc.html in %s — build first' % temp_dir)
        return 1
    html = read(html_path)
    merged_path = os.path.join(temp_dir, 'output.md')
    merged = read(merged_path) if os.path.isfile(merged_path) else ''

    fails = []

    commands, math, envs = check_visible_latex(html)
    print('reader-visible LaTeX : %d command(s), %d inline-math span(s), %d env(s)'
          % (sum(commands.values()), len(math), sum(envs.values())))
    if commands:
        print('   top: %s' % commands.most_common(6))
    if math:
        print('   math: %s' % [m[:30] for m in math[:4]])
    if commands or math or envs:
        fails.append('%d LaTeX fragment(s) printed as literal text'
                     % (sum(commands.values()) + len(math) + sum(envs.values())))

    blank, errors = check_broken_math(html)
    print('formulas rendering as nothing: %d, <merror>: %d' % (blank, errors))
    if blank:
        fails.append('%d formula(s) render as nothing at all' % blank)
    if errors:
        fails.append('%d formula(s) pandoc could not parse (<merror>)' % errors)

    refs = check_unresolved_refs(html)
    print('unresolved references: %d  %s'
          % (sum(refs.values()), [r for r, _n in refs.most_common(4)]))
    if refs:
        fails.append('%d cross-reference(s) printed as a raw label' % sum(refs.values()))

    doubled = check_doubled_labels(html, lang)
    print('doubled reference labels: %d' % len(doubled))
    for kind, text, ctx in doubled[:4]:
        print('   %-8s %-12r ...%s...' % (kind, text, ' '.join(ctx.split())))
    if doubled:
        fails.append('%d reference label(s) printed twice' % len(doubled))

    gloss_problems = check_glosses(merged or visible_text(html))
    print('glossing collisions  : %d' % len(gloss_problems))
    for line in gloss_problems[:6]:
        print('   ' + line)
    if gloss_problems:
        fails.append('%d glossing collision(s)' % len(gloss_problems))

    coverage = check_gloss_coverage(merged or visible_text(html), temp_dir)
    if coverage is not None:
        count, glossed, eligible = coverage
        # A count, comparable between two builds of the same book. Not a
        # ratio: most glossary entries need no gloss, so a percentage would
        # describe a target nobody set.
        print('first-use glosses    : %d in the book; %d of %d glossary '
              'term(s) carry theirs' % (count, len(glossed), len(eligible)))
        never = sorted(set(eligible) - set(glossed))
        if never:
            print('   glossary terms never glossed: %s%s'
                  % (', '.join(never[:8]),
                     ' …+%d' % (len(never) - 8) if len(never) > 8 else ''))
        # Total absence is the only thing this check can prove is wrong.
        if eligible and not count:
            fails.append('no term carries its English on first use '
                         '(%d glossary term(s) in the text)' % len(eligible))

    doublets = check_doublets(merged or visible_text(html), lang)
    print('split renderings     : %d' % len(doublets))
    for line in doublets[:6]:
        print('   ' + line)
    # A doublet can be legitimate (과제 is both *task* and *challenge*), so it
    # is reported for a human to judge rather than failed on.


    homographs = check_homographs(merged or visible_text(html),
                                  _source_text(temp_dir), lang)
    print('one word, two senses : %d' % len(homographs))
    for line in homographs[:6]:
        print('   ' + line)
    # Reported, not failed on. This compares the SOURCE for both senses
    # against the OUTPUT for the word, which finds a word worth looking at
    # but cannot prove the translation actually used it both ways -- once
    # 정렬 was fixed to mean only "sorted" it kept firing, because the paper
    # still contains "aligned" somewhere. Proving it needs sentence-level
    # alignment this pipeline does not have; chunk granularity is too coarse,
    # both senses sat in one chunk. Same standing as check_doublets above.

    drift = check_term_drift(merged or visible_text(html), temp_dir)
    print('term spelled two ways: %d' % len(drift))
    for line in drift[:6]:
        print('   ' + line)
    if drift:
        fails.append('%d term(s) are spelled two ways' % len(drift))

    chunk_problems = check_chunks(temp_dir, lang)
    print('chunk invariants     : %d problem(s)' % len(chunk_problems))
    for line in chunk_problems[:8]:
        print('   ' + line)
    if chunk_problems:
        fails.append('%d chunk(s) drifted from their source' % len(chunk_problems))

    print()
    if fails:
        print('FAIL:')
        for line in fails:
            print('  - ' + line)
        return 1 if strict else 0
    print('PASS: nothing a reader would trip over')
    return 0


def resolve_lang(temp_dir, given):
    r"""The language to judge this book by: the flag, else its own config.

    `--lang` defaulted to `ko` and nothing read the answer sitting in the
    directory the command is already pointed at. `verify_chunk` was fixed for
    exactly this and left a note saying so; this probe was not, which is
    KNOWLEDGE.md K114's shape -- learned in one place, not the other.

    Run against the Chinese DeeR-VLA it judged every heading by the Hangul
    range, so three headings that ARE Chinese were reported untranslated,
    while the doublet list it compared renderings against was the Korean one,
    so `split renderings: 0` meant nothing. The reports it did print were
    about a book that was not there, and the one real defect it should have
    caught -- `第 第3.2节 节` -- was reported as a heading problem instead.
    """
    if given:
        return given
    try:
        import verify_chunk
        return verify_chunk.config_lang(temp_dir) or 'ko'
    except Exception:                                     # noqa: BLE001
        return 'ko'


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    ap.add_argument('temp_dir', help='a built <name>_temp directory')
    ap.add_argument('--lang', default=None,
                    help="target language code; taken from the temp dir's "
                         "config.txt when not given, and 'ko' only if that "
                         "has nothing to say")
    ap.add_argument('--strict', action='store_true',
                    help='exit non-zero when a defect is found')
    args = ap.parse_args()
    lang = resolve_lang(args.temp_dir, args.lang)
    sys.exit(probe(args.temp_dir, lang, args.strict))


if __name__ == '__main__':
    main()

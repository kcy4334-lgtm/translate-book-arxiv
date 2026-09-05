# -*- coding: utf-8 -*-
"""Check what a sub-agent produced, not what it said it did.

A sub-agent reports success by finishing. Nothing about that report is
evidence: the file it wrote is the evidence, and until this runs, the only
thing standing between a fabricated translation and the finished book is the
merge -- which checks two things (placeholders, image refs), hours later,
after every other chunk has already been paid for.

Everything here compares the OUTPUT file against the SOURCE file, the
glossary the agent was given, and the chunk the agent was told to quote from.
Nothing consults the agent's own account of its work. Each finding carries the
offending text, so the retry prompt can name it instead of asking the agent to
"try harder".

    python scripts/verify_chunk.py <temp_dir> --lang ko [chunk0007 ...]
    python scripts/verify_chunk.py <temp_dir> --lang ko --strict --json

Exit code is 1 under --strict when any chunk fails, so a batch loop can gate
on it. Without --strict it reports and exits 0.
"""
from __future__ import unicode_literals

import argparse
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import glossary as glossary_mod                                  # noqa: E402
import math_guard                                                # noqa: E402

try:
    import chunk_context
except ImportError:                                              # pragma: no cover
    chunk_context = None


# --------------------------------------------------------------------------
# Target scripts. A latin target cannot be checked this way, and this says so
# rather than inventing a number it cannot stand behind (KNOWLEDGE K68).
# A tuple of ranges per language, not one range: Japanese needs two.
_SCRIPT_RANGES = {
    'ko': ((0xAC00, 0xD7A3),),
    # Kana AND kanji. Kana alone was the whole range, and Japanese academic
    # prose is kanji-dense, so a correctly translated paragraph counted as
    # almost no Japanese at all.
    'ja': ((0x3040, 0x30FF), (0x4E00, 0x9FFF)),
    'zh': ((0x4E00, 0x9FFF),),
    'ru': ((0x0400, 0x04FF),),
}


def _in_target_script(ch, ranges):
    code = ord(ch)
    return any(lo <= code <= hi for lo, hi in ranges)


def config_lang(temp_dir):
    r"""`output_lang` from the run's own config.txt, or None.

    The `--lang` flag defaulted to `ko` while the answer sat in the temp
    directory the command is already pointed at, and nothing read it. Every
    chunk of every non-Korean book was therefore checked against Hangul:
    five of nine correct Japanese chunks reported "only 0% of the letters
    are ko" and would have been sent back for re-translation, on a book
    whose own config.txt said `output_lang=ja`.
    """
    try:
        with io.open(os.path.join(temp_dir or '', 'config.txt'),
                     encoding='utf-8', errors='replace') as fh:
            for line in fh:
                if line.startswith('output_lang='):
                    return line.split('=', 1)[1].strip() or None
    except OSError:
        return None
    return None

_LATIN_WORD_RE = re.compile(r'[A-Za-z][A-Za-z\'-]{1,}')
_PLACEHOLDER_RE = re.compile(r'\u27e6[MCT]\d{4}\u27e7')
_MD_IMAGE_RE = re.compile(r'!\[[^\]]*\]\(([^)\s]+)')
# A file path is not prose. `images/fig0012_gamma_ablation_curve.png`
# contains the word 'ablation' and no check should read it as one.
_IMAGE_PATH_RE = re.compile(r'!\[[^\]]*\]\([^)]*\)|<img\b[^>]*>')
_HTML_IMAGE_RE = re.compile(r'<img\b[^>]*?\bsrc\s*=\s*["\']([^"\']+)["\']',
                            re.IGNORECASE)
_FENCE_RE = re.compile(r'^\s*(```|~~~)', re.MULTILINE)
_HEADING_RE = re.compile(r'^(#{1,6})\s+\S', re.MULTILINE)
_TABLE_ROW_RE = re.compile(r'^\s*\|.*\|\s*$', re.MULTILINE)
_LIST_ITEM_RE = re.compile(r'^\s*(?:[-*+]\s+|\d+[.)]\s+)\S', re.MULTILINE)
_URL_RE = re.compile(r'https?://\S+|www\.\S+|doi:\S+|arxiv[:/]\S+',
                     re.IGNORECASE)
# An unresolved LaTeX label, as it looks between the translator and the merge:
# `(app:activation_pattern)`. The merge turns it into "Appendix A.1" from
# flat.tex, so it is machinery in transit, not prose anyone failed to
# translate -- and not a glossary term the translator ignored.
_LABEL_RE = re.compile(r'\(?\b[a-z]{2,12}:[A-Za-z0-9_.-]{2,}\)?')

# Regions where Latin prose is correct and expected.
_CODE_BLOCK_RE = re.compile(r'```.*?```|~~~.*?~~~', re.DOTALL)
# Markdown's OTHER code block: a run of indented lines, no fence anywhere.
# pandoc turns a LaTeX `lstlisting` into exactly this, so by the time a chunk
# reaches a translator the listing carries no marker the fenced pattern above
# can see. Neural ODE's autograd listing put its chunk at 21% Korean and
# failed it — for code the translator had been told to copy verbatim.
# Three lines minimum, so an indented continuation of a list item is safe.
_INDENTED_CODE_RE = re.compile(
    r'(?:^(?:[ ]{4}|\t)[^\n]*\n){3,}', re.MULTILINE)
# A raw LaTeX environment whose contents are code, not prose. These arrive
# unfenced, so the markdown pattern above never saw them, and three chunks
# were failed for leaving them exactly as instructed: a Python `lstlisting`
# put the language ratio at 25%, and a pgfplots `table[x=timestep,…]
# {plot_data/….csv}` was read as eighteen untranslated words — one of which
# the glossary check then demanded be translated, though `timestep` there is
# a CSV COLUMN NAME and rendering it in Korean would break the figure.
_LATEX_VERBATIM_RE = re.compile(
    r'\\begin\{(lstlisting|verbatim|Verbatim|minted|tikzpicture|pgfpicture|'
    r'filecontents)\*?\}.*?\\end\{\1\*?\}', re.DOTALL)
# A code span may WRAP. pandoc emits the LNCS `\institute{...}` block as one
# inline span carrying an address, an e-mail and a URL across four lines, and
# a pattern that stops at the first newline does not strip it — so the
# untranslated-block check counted fourteen English words the translator had
# been told, correctly, not to touch, and failed the chunk for obeying.
# A newline is allowed inside a span; a BLANK line is not, since that ends the
# paragraph the span lives in.
_INLINE_CODE_RE = re.compile(r'`(?:[^`\n]|\n(?![ \t]*\r?\n)){1,2000}?`')
_MATH_RE = re.compile(r'\$\$.*?\$\$|\$[^$\n]+\$', re.DOTALL)
_RAW_LATEX_RE = re.compile(r'\\[a-zA-Z@]+\s*(?:\[[^\]]*\])?(?:\{[^{}]*\})*')
# A bibliography entry. The reference list is deliberately kept in the
# original language, so Latin prose there is the correct answer.
# A footnote definition is prose that happens to cite something, so it must
# not read as a bibliography entry.
_FOOTNOTE_RE = re.compile(r'^\s*\[\^[^\]]+\]:')


# A sentence that opens with a discourse connective has the same shape as
# an author list -- "Second, AlphaQ relies on..." against "Zoph, Barret."
# -- and a citation later in the sentence satisfies any year requirement.
# These are a small closed set and none of them is a surname.
_CONNECTIVE_RE = re.compile(
    r'^\s*(?:First|Second|Third|Fourth|Fifth|Finally|However|Moreover'
    r'|Furthermore|Therefore|Instead|Similarly|Nevertheless|Meanwhile'
    r'|Additionally|Consequently|Specifically|Notably|Overall|Indeed'
    r'|Thus|Hence|Conversely|Importantly|Crucially|Here|Note|Next'
    r'|Lastly|Alternatively|Nonetheless|Accordingly),',
    re.IGNORECASE)


def _is_reference_line(line):
    if not line.strip() or _FOOTNOTE_RE.match(line):
        return False
    # The heading is part of the section it names.
    if _REFERENCE_HEADING_RE.match(line.strip()):
        return True
    if _CONNECTIVE_RE.match(line):
        return False
    return bool(_BIB_LINE_RE.search(line))


# The LaTeX bibliography environment. An exact delimiter, so it is used in
# preference to any heuristic: inside it, every line is a reference whatever
# shape it has.
_BIB_ENV_RE = re.compile(
    r'\\begin\{thebibliography\}.*?(?:\\end\{thebibliography\}|\Z)',
    re.DOTALL)


def _blank_lines_like(match):
    """Replace a region with the same number of newlines, to keep line count."""
    return '\n' * match.group(0).count('\n')


def _prose_only(text):
    """The text with references removed, keeping everything else in place.

    Replaces "everything after the reference cut is exempt". That guessed a
    position, and a wrong guess turned the language checks off for whatever
    followed it -- a whole Limitation section, in one measured case.
    """
    text = _BIB_ENV_RE.sub(_blank_lines_like, text)
    return '\n'.join('' if _is_reference_line(line) else line
                     for line in text.split('\n'))


_BIB_LINE_RE = re.compile(
    # "[12]" / "1. Surname," / a bare year in parentheses
    r'^\s*(?:[-*]\s*)?(?:\[\d+\]|\(\d{4}\)|\d+\.\s+[A-Z][a-z]+,)'
    # "Surname, Firstname" and "Surname, F." -- how every style opens an
    # entry. The year requirement is what separates an author list from an
    # ordinary sentence: "Second, AlphaQ relies on..." has the same shape and
    # no date, and without this it cut the Limitation section in half.
    r'|^\s*[A-Z][A-Za-z\u00C0-\u024F\'-]+,\s+[A-Z]'
    r'(?=[^\n]*(?:\b(?:19|20)\d{2}[a-z]?\b|n\.d\.))'
    # LaTeX bibliographies, and the vocabulary of a citation
    r'|\\(?:bibitem|newblock|emph\{|href\{)'
    r'|\b(?:arXiv|arxiv|preprint|In Proceedings|In Advances|In \*|pp\.|vol\.'
    r'|no\.|et al\.|n\.d\.|Cambridge University|MIT Press|IEEE|ACM|NeurIPS'
    r'|ICLR|ICML|CVPR|Conference on|Journal of|Transactions on)\b')

# Referenced by _is_reference_line above, which is defined earlier in the
# file and resolves the name when it runs, not when it is defined.
_BIB_MARKER_RE = re.compile(
    r'\\begin\{thebibliography\}|\\bibitem|\\printbibliography|\\bibliography\{')
_REFERENCE_HEADING_RE = re.compile(
    r'^#{1,6}\s*(?:\d+\.?\s*)?(?:References?|Bibliography|\uCC38\uACE0\s*'
    r'\uBB38\uD5CC|\u53C2\u8003\u6587\u732E|\u53C2\u8003\u6587\u737B)\s*$',
    re.MULTILINE | re.IGNORECASE)

# What a model says when it is talking to you instead of translating.
_COMMENTARY_RE = re.compile(
    r'^(?:\s*(?:Here(?:\'s| is)\b[^\n]*|Sure[,!][^\n]*|Certainly[,!][^\n]*'
    r'|I(?:\'ll| will| have)\b[^\n]*translat[^\n]*'
    r'|(?:Below|Following) is\b[^\n]*translat[^\n]*'
    r'|Translated (?:text|content|markdown)\s*:?[^\n]*'
    r'|\uBC88\uC5ED(?:\uBCF8|\uBB38)?\s*[:\uC785\uB2C8][^\n]*'
    r'|\u4EE5\u4E0B[^\n]*\u7FFB\u8BD1[^\n]*))\s*$',
    re.MULTILINE)
_TRAILING_NOTE_RE = re.compile(
    r'^\s*(?:Note\s*:|Notes?\s+on\s+the\s+translation|\uBC88\uC5ED\s*\uB178'
    r'\uD2B8\s*:|I hope this helps|Let me know if)[^\n]*$',
    re.MULTILINE | re.IGNORECASE)


def _read(path):
    with io.open(path, encoding='utf-8', errors='replace') as handle:
        return handle.read()


def _counter(items):
    out = {}
    for item in items:
        out[item] = out.get(item, 0) + 1
    return out


def _diff_counts(want, have):
    """(missing, extra) as sorted (item, n) pairs."""
    missing, extra = [], []
    for key in sorted(set(want) | set(have)):
        delta = want.get(key, 0) - have.get(key, 0)
        if delta > 0:
            missing.append((key, delta))
        elif delta < 0:
            extra.append((key, -delta))
    return missing, extra


def _strip_verbatim(text):
    """Blank out every region where Latin text is the correct answer."""
    for pattern in (_CODE_BLOCK_RE, _LATEX_VERBATIM_RE, _INDENTED_CODE_RE,
                    _MATH_RE, _INLINE_CODE_RE, _URL_RE,
                    _PLACEHOLDER_RE, _RAW_LATEX_RE, _LABEL_RE,
                    _IMAGE_PATH_RE):
        text = pattern.sub(' ', text)
    return text


_LABEL_KEY_RE = re.compile(r'\\label\s*\{([^}]+)\}')
# `**정리 29** (Non-commutative Bernstein-type inequality).` -- the name a
# theorem was declared with, in the optional argument. The brief tells the
# translator to leave it exactly as the source writes it.
_RESULT_NAME_RE = re.compile(
    r'(?:\*\*|\*)[^*\n]*\d[^*\n]*(?:\*\*|\*)[ \t]*\(([^)\n]{2,90})\)')


def _verbatim_by_instruction(temp_dir, text):
    """Blank the Latin the translator was ORDERED to keep.

    Two shapes, both mandated by the brief and both previously read as the
    translator ignoring the glossary:

    * a cross-reference token -- `(A*A rows non-isotropic)` is a `\\label` key
      standing in for a number, not a phrase anyone may translate;
    * the parenthesised name after a structural label.

    Three of four rejections in one run were this: the check failing chunks for
    obeying the instructions they were given. A check has to be calibrated
    against the brief the translator actually received, or it teaches the
    translator to disobey it.
    """
    text = _RESULT_NAME_RE.sub(' ', text)
    flat = os.path.join(temp_dir or '', 'flat.tex')
    if not os.path.isfile(flat):
        return text
    try:
        with io.open(flat, 'r', encoding='utf-8', errors='replace') as fh:
            keys = {k.strip() for k in _LABEL_KEY_RE.findall(fh.read())}
    except OSError:
        return text
    for key in keys:
        if key:
            text = text.replace('(%s)' % key, ' ')
    return text


def _reference_cut(text):
    """Where the bibliography starts, or len(text) when there is none.

    Three signals, because papers do not agree on how to mark it. A heading
    finds the markdown form; \bibitem finds the raw-LaTeX form, which has no
    heading at all; and counting citation-shaped lines finds the case the
    other two miss -- a chunk that is nothing but entries, its heading having
    landed in the chunk before it.
    """
    cuts = []
    match = _REFERENCE_HEADING_RE.search(text)
    if match:
        cuts.append(match.start())
    match = _BIB_MARKER_RE.search(text)
    if match:
        cuts.append(text.rfind('\n', 0, match.start()) + 1)

    # A dense run of citation-shaped lines, taken from the first line of the
    # run rather than from wherever the density happens to be measured.
    lines = text.split('\n')
    offsets, at = [], 0
    for line in lines:
        offsets.append(at)
        at += len(line) + 1
    shaped = [bool(line.strip()) and bool(_BIB_LINE_RE.search(line))
              for line in lines]
    filled = [i for i, line in enumerate(lines) if line.strip()]
    for pos, i in enumerate(filled):
        rest = filled[pos:]
        if len(rest) < 6:
            break
        # The cut has to land ON a citation line. Without this the scan
        # measures density from line 0 and a chunk of prose followed by a
        # long reference list reads as all-references from its first word --
        # which exempted a whole "Limitation" section from the language
        # checks (KNOWLEDGE K74).
        if not shaped[i]:
            continue
        if sum(1 for j in rest if shaped[j]) >= len(rest) * 0.75:
            cuts.append(offsets[i])
            break
    return min(cuts) if cuts else len(text)


def is_all_references(text):
    """Is this chunk nothing but the reference list?

    Then returning it unchanged is the correct answer, not a failure. Asked
    as a fraction of the lines rather than as a position, because a position
    has to be guessed and a fraction can be counted.
    """
    lines = [line for line in text.split('\n') if line.strip()]
    if not lines:
        return False
    left = [line for line in _prose_only(text).split('\n') if line.strip()]
    return len(left) <= len(lines) * 0.1


def _script_ratio(text, lang):
    ranges = _SCRIPT_RANGES.get(lang)
    if not ranges:
        return None
    target = sum(1 for ch in text if _in_target_script(ch, ranges))
    latin = sum(1 for ch in text if ('a' <= ch <= 'z') or ('A' <= ch <= 'Z'))
    if target + latin == 0:
        return None
    return float(target) / (target + latin)


# --------------------------------------------------------------------------
# Individual checks. Each returns a list of finding dicts:
#   {'check': str, 'severity': 'fail'|'warn', 'detail': str, 'evidence': str}


def check_placeholders(source, output, spans):
    report = math_guard.verify(source, output, spans)
    out = []
    for kind, label in (('missing', 'dropped by the translator'),
                        ('duplicated', 'emitted more than once'),
                        ('foreign', 'invented, not in the source')):
        if report.get(kind):
            out.append({
                'check': 'placeholders',
                'severity': 'fail',
                'detail': '%d placeholder(s) %s' % (len(report[kind]), label),
                'evidence': ', '.join(report[kind][:8]),
            })
    return out


def check_images(source, output):
    out = []
    for name, pattern in (('markdown', _MD_IMAGE_RE), ('html', _HTML_IMAGE_RE)):
        missing, extra = _diff_counts(_counter(pattern.findall(source)),
                                      _counter(pattern.findall(output)))
        if missing:
            out.append({
                'check': 'images',
                'severity': 'fail',
                'detail': '%d %s image reference(s) lost' % (len(missing), name),
                'evidence': ', '.join('%s x%d' % (p, n) for p, n in missing[:6]),
            })
        if extra:
            out.append({
                'check': 'images',
                'severity': 'warn',
                'detail': '%d %s image reference(s) appeared' % (len(extra), name),
                'evidence': ', '.join('%s x%d' % (p, n) for p, n in extra[:6]),
            })
    return out


_NAME_TOKEN_RE = re.compile(r'\b[A-Z][A-Za-zÀ-ɏ.\'-]*')


def _drop_carried_names(body, source):
    r"""Remove capitalised tokens the source spells exactly the same way.

    A person's name and an institution's name are Latin BY RIGHT — the
    translator is told to leave them — and counting their letters against the
    target-language ratio punishes a correct translation for obeying. GAN's
    author-affiliation footnotes are four names, four institutions and a short
    Korean predicate each; every translatable word had been translated and the
    chunk failed at 23%.

    Untranslated PROSE is not protected by this. It is lower-case, so it stays
    in the denominator and the ratio still collapses, and long runs of it are
    `untranslated_block`'s job anyway.
    """
    return _NAME_TOKEN_RE.sub(
        lambda m: '' if m.group(0) in source else m.group(0), body)


_DRAWN_ENV = ('picture', 'tikzpicture', 'pgfpicture', 'pspicture',
              'verbatim', 'Verbatim', 'lstlisting', 'minted', 'filecontents')
_DRAWN_ONLY_RE = re.compile(
    r'\A\s*\\begin\{(' + '|'.join(_DRAWN_ENV) + r')\*?\}'
    r'.*\\end\{\1\*?\}\s*\Z', re.S)


def has_no_prose(source):
    r"""A chunk that is one drawing or one listing and nothing else.

    Shor's chunk0011 is a single gnuplot `\begin{picture}` — 11,905 characters
    of `\put`, `\rule` and `\makebox`, whose only strings are axis tick
    numbers. Returning it unchanged is the correct translation, and
    `untranslated` failed it for being byte-identical to its source. The rule
    is the same one `is_all_references` already encodes: identical output is
    only a defect where there was something to translate.
    """
    return bool(_DRAWN_ONLY_RE.match(source or ''))


_FOOTNOTE_MARKER_RE = re.compile(r'(?m)^\s*\[\^[^\]\s]+\]:')
# Two or more letters of ANY script: Latin, Hangul, CJK. Digits and
# underscores are excluded, so `[^1]:` and `224x224` are not words.
_WORD_RE = re.compile(r'[^\W\d_]{2,}', re.UNICODE)


def has_nothing_to_translate(source):
    r"""A chunk that is machine tokens end to end, with no word in it.

    VLA-Adapter's last chunk is three footnote definitions holding one bare
    URL each. Nothing in it is prose, so byte-identical output is the only
    faithful answer, and `untranslated` failed it and asked for a
    re-translation that could only produce the same bytes and fail again.

    The same rule `is_all_references` and `has_no_prose` already encode,
    applied to a third shape: identical output is a defect only where there
    was something to translate. `_strip_verbatim` already blanks every region
    where Latin is the right answer (URLs, code, maths, raw LaTeX, labels,
    image paths), so what it leaves is what a translator was actually asked
    to render.
    """
    left = _strip_verbatim(_prose_only(source or ''))
    left = _FOOTNOTE_MARKER_RE.sub(' ', left)
    return not _WORD_RE.search(left)


def check_translated(source, output, lang):
    """Did anything happen at all, and is it in the target language?"""
    out = []
    if source.strip() == output.strip():
        if is_all_references(source):
            return out          # the reference list is kept in the original
        if has_no_prose(source):
            return out          # a drawing has nothing to translate
        if has_nothing_to_translate(source):
            return out          # machine tokens only: no word to render
        return [{'check': 'untranslated', 'severity': 'fail',
                 'detail': 'the output is byte-identical to the source',
                 'evidence': output.strip()[:80]}]
    body = _drop_carried_names(_strip_verbatim(_prose_only(output)), source)
    ratio = _script_ratio(body, lang)
    if ratio is None:
        return out
    if ratio < 0.30:
        out.append({
            'check': 'target_language',
            'severity': 'fail',
            'detail': 'only %d%% of the letters are %s' % (ratio * 100, lang),
            'evidence': ' '.join(body.split())[:100],
        })
    return out


_EMAIL_RE = re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+')
_SENTENCE_END_RE = re.compile(r'[.!?](?:\s|$)')


def is_contact_line(line):
    r"""A postal address or contact block, which stays in the original.

    The same decision the reference list gets, for the same reason: an address
    that is translated stops being an address. It arrives here because
    `unwrap_front_matter` now rescues the affiliation that `\address` used to
    take with it (K123), and one line of French street address is, to this
    check, twenty-five Latin words with no Korean.

    Narrow on purpose — no sentences, four or more comma-separated fragments,
    and either an e-mail or a fragment carrying a number. Measured over every
    output chunk in the corpus, it exempts exactly one line: Maynard's
    affiliation. The other 62 findings are higgs_atlas, which genuinely was
    never translated, and they all still fire. ATLAS's own affiliation list
    keeps firing too — it has no number and no e-mail — which is the right way
    round for a check whose failure mode is silence.
    """
    if _SENTENCE_END_RE.search(line):
        return False
    parts = [p.strip() for p in line.split(',') if p.strip()]
    if len(parts) < 4:
        return False
    return bool(_EMAIL_RE.search(line)) or any(re.search(r'\d', p)
                                               for p in parts)


def check_untranslated_blocks(output, lang, min_words=14):
    """A paragraph of source-language prose that never reached a translator.

    Bounded hard on purpose. Model names, benchmark names and citation keys
    are Latin by right, and the reference list is Latin by decision, so this
    looks only for long runs of ORDINARY WORDS in a line carrying no target
    script at all.
    """
    ranges = _SCRIPT_RANGES.get(lang)
    if not ranges:
        return []
    findings = []
    for raw_line in _strip_verbatim(_prose_only(output)).split('\n'):
        line = raw_line.strip()
        if not line or line.startswith('|'):
            continue
        if any(_in_target_script(ch, ranges) for ch in line):
            continue
        if is_contact_line(line):
            continue
        words = _LATIN_WORD_RE.findall(line)
        if len(words) >= min_words:
            findings.append({
                'check': 'untranslated_block',
                'severity': 'fail',
                'detail': '%d consecutive source-language words with no %s'
                          % (len(words), lang),
                'evidence': line[:100],
            })
    return findings[:5]


def check_commentary(output):
    """The prompt forbids commentary. Sub-agents add it anyway."""
    out = []
    head = '\n'.join(output.strip().split('\n')[:3])
    match = _COMMENTARY_RE.search(head)
    if match:
        out.append({'check': 'commentary', 'severity': 'fail',
                    'detail': 'the output opens with a message to the reader',
                    'evidence': match.group(0).strip()[:100]})
    tail = '\n'.join(output.strip().split('\n')[-3:])
    match = _TRAILING_NOTE_RE.search(tail)
    if match:
        out.append({'check': 'commentary', 'severity': 'fail',
                    'detail': 'the output ends with a note to the reader',
                    'evidence': match.group(0).strip()[:100]})
    stripped = output.strip()
    if stripped.startswith('```') and stripped.endswith('```') \
            and stripped.count('```') == 2:
        out.append({'check': 'commentary', 'severity': 'fail',
                    'detail': 'the whole file is wrapped in one code fence',
                    'evidence': stripped[:60]})
    return out


def check_fences(source, output):
    if _FENCE_RE.findall(output).__len__() % 2 == 0:
        return []
    return [{'check': 'fences', 'severity': 'fail',
             'detail': 'odd number of code fences: one is unclosed',
             'evidence': 'source had %d, output has %d'
                         % (len(_FENCE_RE.findall(source)),
                            len(_FENCE_RE.findall(output)))}]


_GROUPED_NUMERAL_RE = re.compile(r'(?<![\w.,])(\d+[.,]\d+)(?![\d.,])')
# A numeral with a UNIT glued to it. The separator rule missed these because
# the digits themselves do not move: French and German wrote `58.9 %` for
# `58.9%` and `10 ms` for `10ms`, thirteen times each, so a page carried
# `58.9 %` in a sentence and `58.9%` in the table it was about.
#
# A magnitude suffix is deliberately NOT here. `85M` becomes 8500만 in Korean,
# 8500万 in Japanese and 8500 万 in Chinese, and all three are how those
# languages write the quantity; a check that fires on every CJK book is the
# mistake K157 is about. The real defect there is narrower and is a
# CONSISTENCY one -- the Japanese book prints `85M` on one page and `8500万`
# four pages later -- which this cannot see and should not pretend to.
_ATTACHED_NUMERAL_RE = re.compile(
    r'(?<![\w.,])(\d+(?:[.,]\d+)?(?:%|ms|GB|Hz))(?![\w.,])')
# A numeral in front of a magnitude WORD is regrouped, not respelled, when
# the target counts in myriads: Korean writes "1.4 billion" as 14억 because
# 억 is 10^8, so the digits themselves legitimately change. TinyVLA, a book
# shipped long before any of this, is where that surfaced -- the check
# written this morning had never been run against it.
_MAGNITUDE_RE = re.compile(
    r'(?<![\w.,])(\d+(?:[.,]\d+)?)\s*'
    r'(?:million|billion|trillion|thousand|hundred)\b', re.IGNORECASE)


def check_numerals(source, output):
    r"""A numeral keeps the spelling the source gave it.

    French, German and Spanish write 58,9 where English writes 58.9, and
    German writes 60.000 for sixty thousand. Translators apply those
    conventions, correctly by the rules of their languages, and the book
    cannot follow: a table float is protected LaTeX reproduced verbatim from
    the paper, and `verify_tables` refuses any change to the numbers inside
    one, which is the guard that stops a retyped value reaching a reader. The
    page then carries 58,9 % in a sentence and 58.9\% in the table it is
    about, and a reader who reads the source convention meets 60.000 as a
    decimal.

    Consistency is only reachable from one side, so the prose follows the
    tables. Nothing else in the pipeline compares the two, and the CJK books
    never showed it because their convention is the source's already.

    Only numerals with an internal separator are checked. Those are the ones
    whose spelling moves between locales, and a bare integer is left alone so
    that spelling one out in words is still allowed.
    """
    wanted = set(_GROUPED_NUMERAL_RE.findall(source))
    wanted |= set(_ATTACHED_NUMERAL_RE.findall(source))
    wanted -= set(_MAGNITUDE_RE.findall(source))
    if not wanted:
        return []
    missing = sorted(n for n in wanted if n not in output)
    if not missing:
        return []
    return [{
        'check': 'numerals',
        'severity': 'fail',
        'detail': '%d numeral(s) the source writes are not in the '
                  'translation, most likely respelled for the target '
                  'locale: %s' % (len(missing), ', '.join(missing[:6])),
        'evidence': _quote_around(source, missing[0]),
    }]


def check_structure(source, output):
    """Headings, table rows and list items may be added -- not lost."""
    out = []
    for name, pattern, severity in (
            ('heading', _HEADING_RE, 'warn'),
            ('table row', _TABLE_ROW_RE, 'fail'),
            ('list item', _LIST_ITEM_RE, 'warn')):
        want, have = len(pattern.findall(source)), len(pattern.findall(output))
        if have < want:
            out.append({
                'check': 'structure',
                'severity': severity,
                'detail': '%d of %d %s(s) are gone' % (want - have, want, name),
                'evidence': '%s count: source %d, output %d'
                            % (name, want, have),
            })
    return out


_BOOK_RATIO = {}
_CHUNK_NAME_RE = re.compile(r'^chunk\d+\.md$')

# A chunk that stopped early comes out around half the length its book
# normally gives; a chunk that simply is what it is comes out within a tenth
# of the median. 0.55 sits between those, far from both.
TRUNCATION_OF_BOOK = 0.55
# A whole book can be truncated, and then it is its own baseline and says so.
TRUNCATION_HARD_FLOOR = 0.20


def median_ratio(ratios, minimum=3):
    """The middle ratio, or None when there are too few to have a middle."""
    ordered = sorted(r for r in ratios if r)
    if len(ordered) < minimum:
        return None
    return ordered[len(ordered) // 2]


def truncation_floor(book, default):
    """The floor one chunk is judged by, given what its book usually does."""
    if not book:
        return default
    return max(TRUNCATION_HARD_FLOOR, book * TRUNCATION_OF_BOOK)


def book_compression(temp_dir):
    r"""The ratio this book's chunks normally come out at, or None.

    A constant floor is a floor fitted to whatever language was at hand when
    it was written. This one was fitted to Korean, and Chinese says the same
    thing in fewer characters again: one paper translated into seven
    languages runs 0.35 to 0.39 for zh against 0.43 to 0.50 for ko, 0.51 to
    0.57 for ja and 1.14 to 1.27 for the Latin three. The Chinese book sat
    one hundredth above a floor of 0.35 with nothing missing from it.

    A book's own chunks compress alike -- within an edition the spread is
    under a tenth of the median -- so the book is its own baseline, the way
    a table's snapshot is. None when there are too few chunks to have one.
    """
    if temp_dir in _BOOK_RATIO:
        return _BOOK_RATIO[temp_dir]
    ratios = []
    try:
        names = sorted(os.listdir(temp_dir)) if temp_dir else []
    except (IOError, OSError):
        names = []
    for name in names:
        if not _CHUNK_NAME_RE.match(name):
            continue
        out_path = os.path.join(temp_dir, 'output_' + name)
        if not os.path.isfile(out_path):
            continue
        source = _read(os.path.join(temp_dir, name))
        src = len(''.join(source.split()))
        if src < 200 or is_all_references(source):
            continue
        ratios.append(len(''.join(_read(out_path).split())) / float(src))
    median = median_ratio(ratios)
    _BOOK_RATIO[temp_dir] = median
    return median


def check_length(source, output, lang, low=0.35, high=2.5, book=None):
    """Truncation, the failure that leaves a perfectly valid short file."""
    src = len(''.join(source.split()))
    out_len = len(''.join(output.split()))
    if src < 200 or is_all_references(source):
        return []
    ratio = float(out_len) / src
    low = truncation_floor(book, low)
    if ratio < low:
        return [{'check': 'length', 'severity': 'fail',
                 'detail': 'the translation is %d%% of the source length'
                           % (ratio * 100),
                 'evidence': 'source %d chars, output %d chars' % (src, out_len)}]
    if ratio > high:
        return [{'check': 'length', 'severity': 'warn',
                 'detail': 'the translation is %.1fx the source length' % ratio,
                 'evidence': 'source %d chars, output %d chars' % (src, out_len)}]
    return []


def check_neighbor_leak(temp_dir, chunk_name, output, source=''):
    r"""The neighbour excerpts are read-only context. They get pasted anyway.

    Sixty characters of verbatim agreement is not a coincidence -- unless the
    two chunks share boilerplate. Shor's chunk0006 and chunk0007 each contain a
    `\begin{tabbing}` block, and every tabbing block in a paper opens with the
    same run of `\ \ \=` alignment markup, so they agree for 388 characters
    without either having seen the other. The brief tells the translator to
    leave that markup byte for byte, so the check was failing a chunk for
    obeying its instructions -- the third time that class has cost a rejection
    (H21, K108).

    The chunk's own source settles it: text the chunk already had is not text
    it took from its neighbour.
    """
    if chunk_context is None:
        return []
    try:
        context = chunk_context.get_neighbor_context(temp_dir, chunk_name)
    except Exception:
        return []
    out = []
    # The keys are prev_excerpt / next_excerpt. Reading 'previous' / 'next'
    # made this check pass on everything, silently, and it went on doing so
    # until a fault injection asked it to catch something.
    flat = ' '.join(output.split())
    own = ' '.join((source or '').split())
    for side, key in (('previous', 'prev_excerpt'), ('next', 'next_excerpt')):
        excerpt = ' '.join(((context or {}).get(key) or '').split())
        # Windows, not one probe: an agent that pastes half the excerpt has
        # still pasted it, and a single tail-anchored probe misses that.
        region = excerpt[-180:] if side == 'previous' else excerpt[:180]
        hit = next((region[i:i + 60] for i in range(0, max(1, len(region) - 59), 30)
                    if len(region[i:i + 60]) == 60 and region[i:i + 60] in flat
                    and region[i:i + 60] not in own),
                   None)
        if hit:
            out.append({'check': 'neighbor_leak', 'severity': 'fail',
                        'detail': 'the %s chunk\'s excerpt was copied into '
                                  'the output verbatim' % side,
                        'evidence': hit})
    return out


def check_glossary(temp_dir, source, output):
    """Terms the agent was handed, and whether it used them."""
    path = os.path.join(temp_dir, 'glossary.json')
    if not os.path.isfile(path):
        return []
    try:
        loaded = glossary_mod.load_glossary(path)
    except Exception:
        return []
    data = loaded[0] if isinstance(loaded, tuple) else loaded
    try:
        terms = glossary_mod.select_terms_for_chunk(data, source)
    except Exception:
        return []
    out = []
    # A paper title in the reference list is Latin by decision, and so is a
    # \texttt{} identifier: neither is the translator ignoring the glossary.
    body = _strip_verbatim(_prose_only(output))
    # Nor is a first-use gloss. The prompt asks the translator for
    # `부합하도록(aligned)` — the English is on the page BECAUSE the term was
    # translated. Reading it as "left untranslated" failed three chunks that
    # had followed the rule exactly. A check has to be calibrated against the
    # instructions the translator was actually given.
    body = glossary_mod._GLOSS_RE.sub(
        lambda m: '' if glossary_mod._is_first_use_gloss(
            ' '.join(m.group(1).split())) else m.group(0), body)
    body = _verbatim_by_instruction(temp_dir, body)
    for term in terms:
        target = (term.get('target') or '').strip()
        surface = (term.get('source') or '').strip()
        if not target or not surface or target == surface:
            continue
        if surface not in source:
            continue                      # selected for frequency, not presence
        if target in output:
            continue
        if glossary_mod._appears_in_text(surface, body):
            out.append({
                'check': 'glossary',
                'severity': 'fail',
                'detail': '"%s" was left untranslated; the glossary says "%s"'
                          % (surface, target),
                'evidence': _quote_around(body, surface),
            })
    return out[:6]


def _quote_around(text, needle, width=40):
    at = text.find(needle)
    if at < 0:
        return ''
    start, stop = max(0, at - width), min(len(text), at + len(needle) + width)
    return ' '.join(text[start:stop].split())


# pandoc's latex READER smartens quotes and dashes; `_WRITER` ends in `-smart`
# so the markdown writer no longer turns them back. The chunk an agent reads
# therefore says `Zhang’s` where the author wrote `Zhang's`, and a quote copied
# faithfully from the paper fails against the chunk over a character nobody can
# see. Measured through the pipeline's own writer spec rather than recalled:
# en/em dash, the four curly quotes, and the non-breaking space from `~`.
#
# The ellipsis is left out, and the reason is the corpus rather than a claim
# about pandoc: 433 `\ldots`/`\dots` and 50 literal `...` in the flat sources
# produced no prose ellipsis in any chunk. The three U+2026 that do exist are
# figure-grid spacers this pipeline emitted, not smartened prose.
#
# U+00A0 is defensive. `_fold_typography`'s callers hand it text already
# through `' '.join(x.split())`, and `str.split()` treats U+00A0 as whitespace,
# so it never arrives — but the function should be right for a caller that does
# not pre-split.
_SMART_FOLD = {
    '‘': "'", '’': "'", '“': '"', '”': '"',
    '–': '-', '—': '-', '\u00a0': ' ',
}
# Wider than the smart pass strictly needs, and deliberately: a source-side
# `--` and a chunk-side `–` have to meet somewhere, so both collapse to one
# hyphen. It merges characters an author may have written; it cannot invent or
# delete a token, which is why the extra width cannot admit a bad quote.
_DASH_RUN_RE = re.compile(r'-{2,}')


def _fold_typography(text):
    r"""Collapse the differences pandoc's `smart` pass created, and only those.

    Applied to BOTH sides, so it cannot let a bad quote through — measured, not
    argued: over all 246 metas in the store the four real failures keep their
    longest matching prefixes to the character, 52 of 127, 23 of 111 and 12 of
    47 twice, folded or not. Structurally they must. Every one of them is a
    deletion or an encoding fault (K129), and this only substitutes characters.
    """
    for fancy, plain in _SMART_FOLD.items():
        text = text.replace(fancy, plain)
    # `--` in the source and `–` in the chunk must land on the same string.
    return _DASH_RUN_RE.sub('-', text)


def check_meta_evidence(temp_dir, chunk_name, source):
    """Every quote a sub-agent offered as evidence must be in the chunk.

    The schema check accepts any string of the right length, so an agent that
    invents a plausible quote gets its invention merged into the glossary and
    from there into every later chunk. A quote is checkable. Check it.
    """
    stem = os.path.splitext(chunk_name)[0]
    path = os.path.join(temp_dir, 'output_%s.meta.json' % stem)
    if not os.path.isfile(path):
        # A reference chunk's output is written by the converter, not by an
        # agent, so no agent was there to write a meta either. Warning about
        # it fires on every paper that has a bibliography — which is every
        # paper — and a check heard every run is a check nobody reads.
        if is_all_references(source):
            return []
        return [{'check': 'meta', 'severity': 'warn',
                 'detail': 'no meta file was written',
                 'evidence': os.path.basename(path)}]
    try:
        with io.open(path, encoding='utf-8') as handle:
            data = json.load(handle)
    except ValueError as exc:
        return [{'check': 'meta', 'severity': 'fail',
                 'detail': 'the meta file is not valid JSON',
                 'evidence': str(exc)[:100]}]
    if not isinstance(data, dict):
        return [{'check': 'meta', 'severity': 'fail',
                 'detail': 'the meta file is not an object', 'evidence': ''}]
    out = []
    if 'chunk_id' in data:
        out.append({'check': 'meta', 'severity': 'fail',
                    'detail': 'meta carries a chunk_id field, which is derived '
                              'from the filename and must not be asserted',
                    'evidence': repr(data['chunk_id'])[:60]})
    flat = _fold_typography(' '.join(source.split()))
    for key in ('new_entities', 'alias_hypotheses', 'attribute_hypotheses',
                'conflicts'):
        for item in data.get(key) or []:
            if not isinstance(item, dict):
                continue
            raw = ' '.join((item.get('evidence') or '').split())
            quote = _fold_typography(raw)
            if len(quote) < 8:
                continue
            if quote not in flat:
                out.append({
                    'check': 'meta_evidence',
                    'severity': 'fail',
                    'detail': 'a quote offered as evidence in %s is not in '
                              'the chunk' % key,
                    # The agent's own text, not the folded form: a reader
                    # chasing this needs the string that was written.
                    'evidence': raw[:100],
                })
    return out[:6]


# --------------------------------------------------------------------------


def verify_chunk(temp_dir, chunk_name, lang):
    """Every check, against the files. Returns a result dict."""
    source_path = os.path.join(temp_dir, chunk_name)
    stem = os.path.splitext(chunk_name)[0]
    output_path = os.path.join(temp_dir, 'output_%s.md' % stem)
    result = {'chunk': stem, 'findings': [], 'ok': False}
    if not os.path.isfile(source_path):
        result['findings'] = [{'check': 'source', 'severity': 'fail',
                               'detail': 'source chunk is missing',
                               'evidence': source_path}]
        return result
    if not os.path.isfile(output_path):
        result['findings'] = [{'check': 'output', 'severity': 'fail',
                               'detail': 'no translation was written',
                               'evidence': os.path.basename(output_path)}]
        return result

    source, output = _read(source_path), _read(output_path)
    if not output.strip():
        result['findings'] = [{'check': 'output', 'severity': 'fail',
                               'detail': 'the translation is blank',
                               'evidence': os.path.basename(output_path)}]
        return result

    all_spans = math_guard.load_sidecar(temp_dir, chunk_name)
    spans = None
    if all_spans:
        try:
            spans = math_guard.spans_for_chunk(source, all_spans)
        except Exception:
            spans = None

    findings = []
    findings += check_placeholders(source, output, spans)
    findings += check_images(source, output)
    findings += check_translated(source, output, lang)
    findings += check_untranslated_blocks(output, lang)
    findings += check_commentary(output)
    findings += check_fences(source, output)
    findings += check_structure(source, output)
    findings += check_numerals(source, output)
    findings += check_length(source, output, lang,
                             book=book_compression(temp_dir))
    findings += check_neighbor_leak(temp_dir, chunk_name, output, source)
    findings += check_glossary(temp_dir, source, output)
    findings += check_meta_evidence(temp_dir, chunk_name, source)

    result['findings'] = findings
    result['ok'] = not any(f['severity'] == 'fail' for f in findings)
    return result


def chunk_names(temp_dir, wanted):
    if wanted:
        return [name if name.endswith('.md') else name + '.md'
                for name in wanted]
    names = [os.path.basename(p) for p in
             sorted(_glob_chunks(temp_dir))]
    return names


def _glob_chunks(temp_dir):
    import glob as _glob
    return [p for p in _glob.glob(os.path.join(temp_dir, 'chunk*.md'))
            if not os.path.basename(p).startswith('output_')]


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('temp_dir')
    parser.add_argument('chunks', nargs='*',
                        help='chunk ids to check; default is all of them')
    parser.add_argument('--lang', default=None,
                        help="target language code; taken from the temp "
                             "dir's config.txt when not given, and 'ko' "
                             "only if that has nothing to say")
    parser.add_argument('--strict', action='store_true',
                        help='exit 1 when any chunk fails')
    parser.add_argument('--json', action='store_true',
                        help='machine-readable report on stdout')
    parser.add_argument('--quiet', action='store_true',
                        help='print only the chunks that failed')
    args = parser.parse_args()

    lang = args.lang or config_lang(args.temp_dir) or 'ko'
    results = [verify_chunk(args.temp_dir, name, lang)
               for name in chunk_names(args.temp_dir, args.chunks)]
    failed = [r for r in results if not r['ok']]
    warned = [r for r in results
              if r['ok'] and any(f['severity'] == 'warn' for f in r['findings'])]

    if args.json:
        print(json.dumps({'results': results,
                          'failed': [r['chunk'] for r in failed],
                          'warned': [r['chunk'] for r in warned]},
                         ensure_ascii=False, indent=2))
    else:
        for result in results:
            if args.quiet and result['ok']:
                continue
            mark = 'PASS' if result['ok'] else 'FAIL'
            print('%s %s' % (mark, result['chunk']))
            for finding in result['findings']:
                print('   [%s] %s: %s' % (finding['severity'],
                                          finding['check'], finding['detail']))
                if finding['evidence']:
                    print('          %s' % finding['evidence'])
        print()
        print('%d chunk(s) checked, %d failed, %d with warnings'
              % (len(results), len(failed), len(warned)))
        if failed:
            print('re-translate: %s' % ' '.join(r['chunk'] for r in failed))

    return 1 if (failed and args.strict) else 0


if __name__ == '__main__':
    sys.exit(main())

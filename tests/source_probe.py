#!/usr/bin/env python3
"""
source_probe.py - Do our numbers say what the ORIGINAL paper prints?

Not named test_*.py: it needs a built temp dir and pymupdf, so
`unittest discover` must not collect it.

    python tests/source_probe.py <temp_dir> [--strict]

Section numbers, figure numbers, equation numbers and cross-reference values
are all reconstructed from flat.tex. Reconstruction can be self-consistent and
still wrong -- an early version numbered SINQ's headings I. / A. / 1) because
that is what IEEEtran does, while SINQ prints 1. / 2.1. / 2.1.1. Forty-one
headings were labelled confidently and wrongly, and nothing complained.

The source PDF is the input to the whole pipeline and config.txt records where
it is. It is the one reference that cannot have drifted, so every number gets
compared against what it actually prints.

Everything here reads flat.tex and the PDF, never the translation, so it works
the same before and after the chunks are translated.
"""

import argparse
import os
import re
import sys

SCRIPT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          'scripts')
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import merge_and_build as mb                                    # noqa: E402

B = chr(92)
_MATH_ENV_RE = re.compile(
    re.escape(B) + r'begin\{(equation|align|gather|multline|eqnarray|flalign)(\*?)\}')
_REF_RE = re.compile(re.escape(B) + r'(?:c|C)?ref\s*\{([^}]+)\}')
# A paper that resets its equation counter per section prints `(2.1)`, not
# `(2)`. Matching only the undotted form made this probe report "48 numbered by
# LaTeX, 0 printed in the PDF" about a paper that prints all 48 — a missing
# number that was really the probe declining to look, and it was quoted back
# as a reason to accept the defect.
_EQ_MARKER_RE = re.compile(r'^\(\d{1,3}(?:\.\d{1,3})*\)$')
_PLAIN_RUN_RE = re.compile(r"[A-Za-z][A-Za-z0-9 ,.\-()/']{22,}")
_REF_WORD_RE = re.compile(
    r'(?:Equations?|Sections?|Appendix|Appendices|Figures?|Tables?|Algorithms?|'
    r'Lemmas?|Theorems?|Eqs?\.|Figs?\.|Secs?\.|Tabs?\.|Alg\.)\s*', re.IGNORECASE)


def read(path):
    with open(path, encoding='utf-8', errors='replace') as fh:
        return fh.read()


def pdf_text(path):
    import pymupdf
    doc = pymupdf.open(path)
    try:
        lines = []
        for page in doc:
            lines.extend(page.get_text('text').split('\n'))
        return lines, re.sub(r'\s+', ' ', ' '.join(lines))
    finally:
        doc.close()


def probe_of(text):
    """The longest contiguous run of ordinary prose in a caption or sentence."""
    runs = _PLAIN_RUN_RE.findall(re.sub(r'\s+', ' ', text))
    return max(runs, key=len).strip()[:60] if runs else None


def check_sections(temp_dir, flat):
    heads = mb.read_tex_headings(temp_dir)
    prefixes, stats = mb.read_pdf_section_prefixes(temp_dir, heads)
    if prefixes is None:
        return None, stats
    return prefixes, stats


_ENV_EDGE_RE = re.compile(re.escape(B) + r'(begin|end)\s*\{')


def align_rows(body):
    r"""Rows in an align body: `\\` that can actually break one.

    `body.count('\\\\') + 1` credits every double backslash in the block, and
    most of them are not row breaks. Maynard writes 74 `\substack{a\\b}`, whose
    `\\` sits inside a brace group, plus `\begin{cases}...\\...\end{cases}`
    inside three more. Counting those made the probe claim 167 numbered
    equations about a paper that prints 106, and FAIL a book whose numbering
    was never in question — the same shape as K124, a check reading structure
    it should have skipped and reporting the difference as damage.

    A row breaks only at brace depth zero and environment depth zero. On
    Maynard this brings the claim from 167 to 121, and matches the paper
    exactly for the four sections that carry most of the displays (5, 32, 22,
    21). A residual of about fifteen remains in the opening sections and is
    NOT explained: not `\notag` in a plain `equation` (0 of them), not
    `subequations` (0), not material after `\end{document}` (0).
    """
    depth = env = rows = 0
    i = 0
    while i < len(body):
        ch = body[i]
        if ch == '\\':
            if body.startswith(B + B, i):
                if depth == 0 and env == 0:
                    rows += 1
                i += 2
                continue
            edge = _ENV_EDGE_RE.match(body, i)
            if edge:
                env = max(0, env + (1 if edge.group(1) == 'begin' else -1))
                i = edge.end()
                continue
            i += 2                      # any other control sequence
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth = max(0, depth - 1)
        i += 1
    return rows + 1


def check_equations(flat, pdf_lines):
    """How many equations LaTeX numbers, against the (N) the PDF prints."""
    counted = 0
    for m in _MATH_ENV_RE.finditer(flat):
        env, star = m.group(1), m.group(2)
        if star:
            continue
        end = flat.find('%send{%s}' % (B, env), m.end())
        body = flat[m.end():end if end > 0 else m.end()]
        if env in ('align', 'eqnarray', 'flalign'):
            counted += max(0, align_rows(body) - len(re.findall(
                re.escape(B) + r'(?:nonumber|notag)', body)))
        else:
            counted += 1
    printed = [l.strip() for l in pdf_lines if _EQ_MARKER_RE.match(l.strip())]
    return counted, printed_equation_count(printed)


def printed_equation_count(markers):
    r"""How many numbers the paper printed, allowing for a missed extraction.

    A number is only counted above when the `(N)` stands alone on its extracted
    line, and one of Maynard's — `(6.15)` — shares a line with the tail of its
    equation. Counting the markers therefore said 105 about a paper that prints
    106, which is a FAIL on a book whose numbering is right.

    The counter runs 1..max within each group, so the maxima are the true
    total and survive a gap. Used only when the extraction is nearly complete:
    if more than a tenth of a group is missing the extraction is not trustworthy
    enough to extrapolate from, and the raw count stands.
    """
    groups = {}
    for text in markers:
        parts = text.strip('()').split('.')
        try:
            nums = [int(p) for p in parts]
        except ValueError:
            continue
        groups.setdefault(tuple(nums[:-1]), set()).add(nums[-1])
    if not groups:
        return len(markers)
    total = 0
    for prefix, seen in groups.items():
        top = max(seen)
        if len(seen) < top * 0.9:
            return len(markers)
        total += top
    return total


def check_floats(temp_dir, flat, pdf_flat):
    """Each float's caption, against the Figure/Table number beside it."""
    agree = disagree = skipped = 0
    problems = []
    tex = flat                        # probe() strips comments once, up front
    for unit in mb.float_units(tex):
        if unit['number'] is None:
            continue
        region = tex[unit['start']:unit['stop']]
        cap = mb._CAPTION_CMD_RE.search(region)
        if not cap:
            skipped += 1
            continue
        start = region.index('{', cap.end() - 1)
        close = mb._balanced_group(region, start)
        if close < 0:
            skipped += 1
            continue
        probe = probe_of(region[start + 1:close - 1])
        if not probe:
            skipped += 1
            continue
        at = pdf_flat.find(probe[:44])
        if at < 0:
            skipped += 1
            continue
        head = pdf_flat[max(0, at - 30):at]
        # Dotted here too: a float counter reset per section prints
        # `Table 3.1`. Comparison is by STRING, because `3.1` has no integer
        # form and `int()` threw the number away rather than disagreeing.
        got = re.search(r'(?:Figure|Fig\.?|Table|Tab\.?)\s*'
                        r'(\d+(?:\.\d+)*)\s*[:.]?\s*$', head)
        if not got:
            skipped += 1
            continue
        if got.group(1) == str(unit['number']):
            agree += 1
        else:
            disagree += 1
            problems.append('we number this %s %s, the paper prints %s: %s'
                            % (unit['kind'], unit['number'], got.group(1),
                               probe[:44]))
    return agree, disagree, skipped, problems


def check_references(temp_dir, flat, pdf_flat):
    """Every \\ref target, against the number printed at that spot."""
    labels = mb.build_label_numbers(temp_dir)
    floats = mb.build_float_numbers(temp_dir)
    agree = disagree = skipped = 0
    problems = []
    for m in _REF_RE.finditer(flat):
        key = m.group(1).strip()
        ours = labels.get(key)
        if ours is None and key in floats:
            ours = str(floats[key])
        if ours is None:
            continue
        before = re.sub(r'\s+', ' ', flat[max(0, m.start() - 160):m.start()])
        # Brace groups are macro arguments -- \ref{eq:pl_alpha_hill} leaves
        # `eq:pl_alpha_hill` in the context, which appears nowhere in the PDF.
        before = re.sub(r'\{[^{}]*\}', ' ', before)
        before = re.sub(re.escape(B) + r'[a-zA-Z]+\s*', ' ', before)
        before = re.sub(r'[{}$~]', ' ', before)
        words = [w for w in before.split() if w]
        # "is provided in Appendix" occurs a dozen times in one paper, and the
        # first hit reported a mismatch the paper does not have. Only a
        # context that lands in exactly one place identifies a reference site.
        at = -1
        for take in (8, 6, 4):
            if len(words) < take:
                continue
            probe = ' '.join(words[-take:])
            if len(probe) > 10 and pdf_flat.count(probe) == 1:
                at = pdf_flat.find(probe)
                break
        if at < 0:
            skipped += 1
            continue
        tail = _REF_WORD_RE.sub('', pdf_flat[at + len(probe):at + len(probe) + 30], 1)
        got = re.match(r'\s*\(?([0-9A-Z]+(?:\.[0-9]+)*)\)?', tail)
        if not got:
            skipped += 1
            continue
        if got.group(1) == ours:
            agree += 1
        else:
            disagree += 1
            problems.append('%s: we say %s, the paper prints %s' % (key, ours, got.group(1)))
    return agree, disagree, skipped, problems


def probe(temp_dir, strict=False):
    flat_path = os.path.join(temp_dir, 'flat.tex')
    if not os.path.isfile(flat_path):
        print('SKIP: no flat.tex — not an arXiv-sourced build, nothing to compare')
        return 0
    source = mb._source_pdf(temp_dir)
    if not source:
        print('SKIP: config.txt records no readable source PDF')
        return 0
    try:
        pdf_lines, pdf_flat = pdf_text(source)
    except Exception as exc:                                    # noqa: BLE001
        print('SKIP: could not read %s (%s)' % (os.path.basename(source), exc))
        return 0

    # Commented-out floats and equations number nothing. Stripping here, once,
    # is what every reader in merge_and_build does -- and the one that forgot
    # is what put a figure's caption and its cross-reference one apart.
    flat = mb.strip_tex_comments(read(flat_path))
    print('comparing against %s' % os.path.basename(source))
    fails = []

    prefixes, stats = check_sections(temp_dir, flat)
    if prefixes is None:
        print('sections   : not checked (%s)' % stats.get('reason'))
    else:
        print('sections   : %d numbered, %d unnumbered in the original, %d not found'
              % (stats['matched'], stats['unnumbered'], stats['missing']))
        if stats['missing'] > max(2, 0.2 * len(prefixes)):
            fails.append('%d heading(s) could not be found in the original'
                         % stats['missing'])

    counted, printed = check_equations(flat, pdf_lines)
    print('equations  : %d numbered by LaTeX, %d "(N)" printed in the PDF'
          % (counted, printed))
    if counted != printed:
        fails.append('equation count disagrees with the original (%d vs %d)'
                     % (counted, printed))

    agree, disagree, skipped, problems = check_floats(temp_dir, flat, pdf_flat)
    print('float numbers: %d agree, %d disagree, %d not located'
          % (agree, disagree, skipped))
    for line in problems[:6]:
        print('   ' + line)
    if disagree:
        fails.append('%d float number(s) disagree with the original' % disagree)

    agree, disagree, skipped, problems = check_references(temp_dir, flat, pdf_flat)
    print('references : %d agree, %d disagree, %d not located'
          % (agree, disagree, skipped))
    for line in problems[:6]:
        print('   ' + line)
    if disagree:
        fails.append('%d cross-reference(s) disagree with the original' % disagree)

    print()
    if fails:
        print('FAIL:')
        for line in fails:
            print('  - ' + line)
        return 1 if strict else 0
    print('PASS: every number matches what the original prints')
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    ap.add_argument('temp_dir', help='a built <name>_temp directory')
    ap.add_argument('--strict', action='store_true',
                    help='exit non-zero when a number disagrees')
    args = ap.parse_args()
    sys.exit(probe(args.temp_dir, args.strict))


if __name__ == '__main__':
    main()

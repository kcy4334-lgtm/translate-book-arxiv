#!/usr/bin/env python3
"""
dry_run.py - Build the book before translating a word of it.

Not named test_*.py: it shells out to the real build, so `unittest discover`
must not collect it.

    python tests/dry_run.py <temp_dir> [--lang ko] [--keep]

Every structural defect this pipeline has ever shipped -- a figure that never
became an image, a float numbered one too high, a table whose columns moved,
a caption attached to the wrong picture -- is decided before translation and
is perfectly visible without it. Finding one afterwards is not a rebuild; the
chunk boundaries and the math placeholders both move when the source is
re-converted, so it is a re-translation of prose that was already correct.

So: copy each source chunk over its own output slot in a scratch directory,
build that, and read the result. Ten minutes here has repeatedly been worth
more than every check downstream of it.

The real temp dir is never written to. The scratch copy is <temp_dir>_dryrun.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)

# Everything the build reads. arxiv_src/ is deliberately absent: it is the
# largest thing in the temp dir and only the conversion step needs it.
COPY_FILES = ('input.md', 'manifest.json', 'config.txt', 'flat.tex',
              'math_macros.tex', 'glossary.json', 'source_fingerprint.json')
COPY_DIRS = ('images',)


def stage(temp_dir, scratch):
    if os.path.isdir(scratch):
        shutil.rmtree(scratch)
    os.makedirs(scratch)
    for name in COPY_FILES:
        src = os.path.join(temp_dir, name)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(scratch, name))
    for name in COPY_DIRS:
        src = os.path.join(temp_dir, name)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(scratch, name))

    chunks = sorted(n for n in os.listdir(temp_dir)
                    if re.fullmatch(r'chunk\d+\.md', n))
    if not chunks:
        raise SystemExit('no source chunks in %s' % temp_dir)
    for name in chunks:
        shutil.copy2(os.path.join(temp_dir, name), os.path.join(scratch, name))
        # The untranslated chunk stands in for its own translation.
        shutil.copy2(os.path.join(temp_dir, name),
                     os.path.join(scratch, 'output_' + name))
        side = os.path.join(temp_dir, name[:-3] + '.math.json')
        if os.path.isfile(side):
            shutil.copy2(side, os.path.join(scratch, os.path.basename(side)))
    return chunks


# A relative pronoun cannot open a sentence: it needs an antecedent inside the
# same one. "While", "Since" and "Because" can, so they are not listed.
_ORPHAN_RE = re.compile(
    r'(?:(?<=[.!?])\s+|(?<=\n\n))((?:which|who|whom|whose)\b[^.!?\n]{10,150}[.!?])',
    re.IGNORECASE)


def source_sanity(scratch):
    """Sentences already broken in the SOURCE, before anyone translates.

    A translator renders a broken sentence faithfully and the reader blames
    the translation. CafeQ's published PDF reads "...particularly in the
    attention modules. which in contrast, aims to quantize an already-trained
    model", so the Korean inherits a pronoun with no antecedent and looks like
    a translation error.

    Reported, never failed: the paper is what it is. Knowing before you
    translate is what lets you annotate it instead of being blamed for it.
    """
    path = os.path.join(scratch, 'input.md')
    if not os.path.isfile(path):
        return []
    with open(path, encoding='utf-8', errors='replace') as fh:
        text = fh.read()
    text = re.sub(r'\$\$.*?\$\$|\$[^$\n]*\$', ' ', text, flags=re.DOTALL)
    text = re.sub(r'(?m)^\s*[#|>].*$', ' ', text)
    text = re.sub(r'`[^`\n]*`|⟦[MCT]\d+⟧', ' ', text)
    found = []
    for m in _ORPHAN_RE.finditer(text):
        before = re.sub(r'\s+', ' ', text[max(0, m.start() - 90):m.start()])
        found.append((before.strip()[-70:],
                      re.sub(r'\s+', ' ', m.group(1))[:110]))
    return found


def run(argv, label):
    print('\n--- %s ---' % label)
    proc = subprocess.run(argv, capture_output=True, text=True,
                          encoding='utf-8', errors='replace')
    out = (proc.stdout or '') + (proc.stderr or '')
    keep = re.compile(
        r'^(Sections|Figures|References|Equations|Tables|Images|Sub-figure|'
        r'float|table captions|Unwrapped|Rewrote|Carried|PASS|FAIL|SKIP|'
        r'Warning|Error|\s+[-•])|error|failed|mismatch|degraded|not found',
        re.IGNORECASE)
    for line in out.split('\n'):
        if line.strip() and keep.search(line):
            print('  ' + line.rstrip())
    return proc.returncode


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    ap.add_argument('temp_dir')
    ap.add_argument('--lang', default=None, help='target language code')
    ap.add_argument('--keep', action='store_true',
                    help='leave <temp_dir>_dryrun on disk for inspection')
    args = ap.parse_args()

    temp_dir = os.path.abspath(args.temp_dir.rstrip('\\/'))
    if not os.path.isdir(temp_dir):
        raise SystemExit('no such temp dir: %s' % temp_dir)
    scratch = temp_dir + '_dryrun'

    chunks = stage(temp_dir, scratch)
    print('staged %d untranslated chunk(s) into %s'
          % (len(chunks), os.path.basename(scratch)))

    lang = args.lang
    if not lang:
        config = os.path.join(temp_dir, 'config.txt')
        if os.path.isfile(config):
            with open(config, encoding='utf-8', errors='replace') as fh:
                for line in fh:
                    if line.startswith('output_lang='):
                        lang = line.split('=', 1)[1].strip()
        lang = lang or 'en'

    build = [sys.executable, os.path.join(BASE, 'scripts', 'merge_and_build.py'),
             '--temp-dir', scratch, '--lang', lang, '--force-html']
    if run(build, 'build') != 0:
        print('\nFAIL: the build itself did not finish')
        return 1

    status = 0
    # format_probe's --lang check asks whether the table captions were
    # translated. Nothing here has been, so passing it would fail every dry
    # run for the one reason a dry run cannot speak to.
    for probe, extra in (('source_probe.py', []),
                         ('format_probe.py', [])):
        code = run([sys.executable, os.path.join(HERE, probe), scratch] + extra,
                   probe)
        status = status or code

    broken = source_sanity(scratch)
    if broken:
        print('\n--- the source itself ---')
        print('  %d sentence(s) that are already broken in the paper. Translate'
              % len(broken))
        print('  them faithfully and annotate; do not quietly repair them, or')
        print('  the book says something the paper does not.')
        for before, sentence in broken[:5]:
            print('    ...%s' % before)
            print('    >> %s' % sentence)

    print('\nWhat a dry run cannot tell you: whether the prose is any good.')
    print('What it does tell you is whether translating it would be wasted.')
    raw = len([1 for n in os.listdir(scratch) if n.endswith('.math.json')])
    if raw:
        print('Run format_probe with --lang after translating: raw-LaTeX table')
        print('captions sit behind placeholders and no sub-agent ever sees them.')
    if not args.keep:
        shutil.rmtree(scratch, ignore_errors=True)
    else:
        print('kept: %s' % scratch)
    return status


if __name__ == '__main__':
    sys.exit(main())

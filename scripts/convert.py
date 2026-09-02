#!/usr/bin/env python3
"""
convert.py - Convert PDF/DOCX/EPUB to Markdown chunks via Calibre HTMLZ
Combines the original steps 1-2 into a single script.
"""

import os
import sys
import subprocess
import zipfile
import shutil
import tempfile
import argparse
import bisect
import glob
import json
import re

from manifest import create_manifest, file_hash
import arxiv_backend
import backends
import math_guard
# The calibrated answer to "what does a citation look like".
# One copy, so the splitter and the checker cannot drift apart.
from verify_chunk import _is_reference_line

# Windows consoles default to a legacy codepage; force UTF-8 so non-ASCII
# progress output cannot crash the conversion.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError, OSError):
        pass

# [] = unresolved, [None] = definitively absent
_CALIBRE_CACHE = []


def find_calibre_convert():
    """Find ebook-convert command from Calibre installation.

    The Windows installer does not add Calibre to PATH, so the standard install
    locations must be probed explicitly. Result is cached.
    """
    if _CALIBRE_CACHE:
        return _CALIBRE_CACHE[0]

    exe = 'ebook-convert.exe' if os.name == 'nt' else 'ebook-convert'
    possible_paths = [
        shutil.which('ebook-convert'),
        os.environ.get('CALIBRE_EBOOK_CONVERT'),
        r"C:\Program Files\Calibre2\ebook-convert.exe",
        r"C:\Program Files (x86)\Calibre2\ebook-convert.exe",
        os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Programs', 'Calibre2', exe),
        "/Applications/calibre.app/Contents/MacOS/ebook-convert",
        "/usr/bin/ebook-convert",
        "/usr/local/bin/ebook-convert",
        "/opt/homebrew/bin/ebook-convert",
        "ebook-convert"  # If in PATH
    ]

    for path in [p for p in possible_paths if p]:
        try:
            result = subprocess.run([path, "--version"], capture_output=True, text=True,
                                    encoding='utf-8', errors='replace', timeout=15)
            if result.returncode == 0:
                print(f"Found Calibre ebook-convert: {path}")
                _CALIBRE_CACHE.append(path)
                return path
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            continue

    _CALIBRE_CACHE.append(None)
    return None


def convert_to_htmlz(input_file, htmlz_file, calibre_path):
    """Convert input file to HTMLZ using Calibre"""
    try:
        print(f"Converting {input_file} to HTMLZ...")
        cmd = [calibre_path, input_file, htmlz_file]
        # encoding= is required: Calibre emits UTF-8, and decoding it with the
        # Windows locale codepage raises UnicodeDecodeError inside
        # subprocess.run before the returncode check can run.
        result = subprocess.run(cmd, capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=600)

        if result.returncode == 0:
            file_size = os.path.getsize(htmlz_file)
            print(f"HTMLZ conversion successful: {htmlz_file} ({file_size} bytes)")
            return True
        else:
            print(f"HTMLZ conversion failed: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        print("HTMLZ conversion timed out")
        return False
    except Exception as e:
        print(f"HTMLZ conversion error: {e}")
        return False


def extract_metadata_from_htmlz(extract_dir):
    """Extract metadata from metadata.opf file in HTMLZ"""
    try:
        import xml.etree.ElementTree as ET

        metadata_file = None
        for root, dirs, files in os.walk(extract_dir):
            for file in files:
                if file.lower() == 'metadata.opf':
                    metadata_file = os.path.join(root, file)
                    break
            if metadata_file:
                break

        if not metadata_file:
            return {}

        tree = ET.parse(metadata_file)
        root = tree.getroot()

        namespaces = {
            'opf': 'http://www.idpf.org/2007/opf',
            'dc': 'http://purl.org/dc/elements/1.1/',
            'dcterms': 'http://purl.org/dc/terms/'
        }

        metadata = {}

        title_elem = root.find('.//dc:title', namespaces)
        if title_elem is not None and title_elem.text:
            metadata['title'] = title_elem.text.strip()

        creator_elem = root.find('.//dc:creator', namespaces)
        if creator_elem is not None and creator_elem.text:
            metadata['creator'] = creator_elem.text.strip()

        publisher_elem = root.find('.//dc:publisher', namespaces)
        if publisher_elem is not None and publisher_elem.text:
            metadata['publisher'] = publisher_elem.text.strip()

        language_elem = root.find('.//dc:language', namespaces)
        if language_elem is not None and language_elem.text:
            metadata['language'] = language_elem.text.strip()

        return metadata

    except Exception as e:
        print(f"Warning: Error extracting metadata: {e}")
        return {}


def extract_htmlz(htmlz_file, temp_dir):
    """Extract HTMLZ file and return paths to HTML and images"""
    try:
        with zipfile.ZipFile(htmlz_file, 'r') as zip_file:
            zip_file.extractall(temp_dir)

        html_file = None
        images_dir = None

        for root, dirs, files in os.walk(temp_dir):
            for file in files:
                if file.lower() in ['index.html', 'index.htm']:
                    html_file = os.path.join(root, file)
                    break
            for dir_name in dirs:
                if dir_name.lower() in ['images', 'image', 'pics', 'pictures']:
                    images_dir = os.path.join(root, dir_name)
                    break

        if not html_file:
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    if file.lower().endswith(('.html', '.htm')):
                        html_file = os.path.join(root, file)
                        break
                if html_file:
                    break

        return html_file, images_dir

    except Exception as e:
        print(f"Error extracting HTMLZ: {e}")
        return None, None


def build_temp_dir(input_file, temp_root=None):
    """Return the working directory path for an input file.

    Default is the historical cwd-local {book_name}_temp/. When temp_root is
    provided, only the root changes; the leaf directory name stays compatible.
    """
    base_name = os.path.splitext(os.path.basename(input_file))[0]
    leaf = f"{base_name}_temp"
    if temp_root:
        return os.path.join(temp_root, leaf)
    return leaf


SOURCE_FINGERPRINT_FILE = "source_fingerprint.json"

# Files whose presence means the temp dir carries conversion state derived
# from some source book — and must therefore be tied to the current one.
_SOURCE_CACHE_MARKERS = (
    "input.html",
    "input.md",
    "manifest.json",
    "run_state.json",
    "glossary.json",
    "output.md",
)


def source_fingerprint(input_file):
    """Stable identity of the exact source bytes being converted."""
    return {
        "path": os.path.realpath(input_file),
        "size": os.path.getsize(input_file),
        "sha256": file_hash(input_file),
    }


def _write_source_fingerprint(temp_dir, fingerprint):
    os.makedirs(temp_dir, exist_ok=True)
    path = os.path.join(temp_dir, SOURCE_FINGERPRINT_FILE)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(fingerprint, f, indent=2, sort_keys=True)
        f.write('\n')


def _load_source_fingerprint(temp_dir):
    path = os.path.join(temp_dir, SOURCE_FINGERPRINT_FILE)
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _has_reusable_source_cache(temp_dir):
    if not os.path.isdir(temp_dir):
        return False
    for name in _SOURCE_CACHE_MARKERS:
        if os.path.exists(os.path.join(temp_dir, name)):
            return True
    for pattern in ('chunk*.md', 'output_chunk*.md'):
        if glob.glob(os.path.join(temp_dir, pattern)):
            return True
    return False


def check_source_cache(temp_dir, current_fingerprint):
    """Compare the temp dir's cached source identity against the current input.

    Returns (status, message):
      (None, None)        — fresh temp dir, or fingerprint matches; proceed.
      ('adopt', message)  — cache predates fingerprinting; adopt it and record
                            the current fingerprint (trust-on-first-use, keeps
                            pre-upgrade temp dirs resumable).
      ('mismatch', message) — cache was built from different source bytes;
                              the caller must abort.

    Only content identity (sha256 + size) is compared — moving or renaming the
    source file does not invalidate the cache.
    """
    if not _has_reusable_source_cache(temp_dir):
        return None, None

    stored = _load_source_fingerprint(temp_dir)
    if stored is None:
        return 'adopt', (
            f"{temp_dir}/ contains cached conversion artifacts without a "
            f"{SOURCE_FINGERPRINT_FILE} (created by an older version). "
            f"Assuming they were built from the current input file. "
            f"If you replaced the source file, delete {temp_dir}/ and re-run."
        )

    for key in ("sha256", "size"):
        if stored.get(key) != current_fingerprint.get(key):
            return 'mismatch', (
                f"{temp_dir}/ was created from different source bytes "
                f"(cached sha256 {str(stored.get('sha256', ''))[:12]}..., "
                f"current {current_fingerprint['sha256'][:12]}...). "
                f"Reusing its chunks would translate the wrong book."
            )
    return None, None


def _abort_on_source_cache_mismatch(status, message, temp_dir):
    if status == 'mismatch':
        print(f"Error: {message}")
        print(f"Delete {temp_dir}/ (or use a fresh --temp-root) and re-run.")
        sys.exit(1)
    if status == 'adopt':
        print(f"Warning: {message}")


def setup_temp_directory(input_file, html_file, images_dir, temp_root=None):
    """Setup temp directory with HTML and images"""
    try:
        temp_dir = build_temp_dir(input_file, temp_root)
        os.makedirs(temp_dir, exist_ok=True)

        input_html = os.path.join(temp_dir, "input.html")
        if os.path.exists(input_html):
            print(f"Skipping HTML copy - input.html already exists")
        else:
            shutil.copy2(html_file, input_html)
            print(f"Copied HTML to: {input_html}")

        if images_dir and os.path.exists(images_dir):
            target_images_dir = os.path.join(temp_dir, "images")
            if os.path.exists(target_images_dir):
                print(f"Skipping images copy - images directory already exists")
            else:
                shutil.copytree(images_dir, target_images_dir)
                print(f"Copied images to: {target_images_dir}")

        return temp_dir
    except Exception as e:
        print(f"Error setting up temp directory: {e}")
        return None


def sanitize_calibre_html(html_file):
    """Strip Calibre's presentational wrappers before pandoc sees them.

    Calibre's pdftohtml output wraps nearly every text run in
    `<span class="calibreN">` and every internal cross-reference in
    `<a href="#calibre_link-N">`. pandoc faithfully renders those as
    `[text]{.calibreN}` and `[text](#calibre_link-N)`, which is the root cause
    of the `[bracket]` fragmentation seen throughout converted output.

    Removing them at the HTML layer is unambiguous — a span with only
    calibre-generated classes carries no semantics. Doing the same job with
    regexes on the produced markdown is not: there, `[text]` is
    indistinguishable from footnote refs, reference links, and real links.

    Idempotent, so re-running on an already-sanitized file is a no-op.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("Warning: bs4 not available — skipping HTML sanitization")
        return False

    try:
        with open(html_file, 'r', encoding='utf-8', errors='replace') as f:
            soup = BeautifulSoup(f.read(), 'lxml')
    except Exception as e:
        print(f"Warning: could not parse HTML for sanitization: {e}")
        return False

    n_anchors = n_spans = n_attrs = 0

    # 1. Internal-only or empty anchors: keep the text, drop the link.
    for a in list(soup.find_all('a')):
        href = (a.get('href') or '').strip()
        if href.startswith('#calibre_link') or href in ('', '#'):
            a.unwrap()
            n_anchors += 1

    # 2. Spans whose only classes are calibre-generated carry no meaning.
    for span in list(soup.find_all('span')):
        classes = span.get('class') or []
        if not classes or all(c.startswith('calibre') for c in classes):
            span.unwrap()
            n_spans += 1

    # 3. Strip leftover calibre class/id from whatever survives.
    for el in soup.find_all(True):
        classes = el.get('class')
        if classes:
            keep = [c for c in classes if not c.startswith('calibre')]
            if keep:
                el['class'] = keep
            else:
                del el['class']
                n_attrs += 1
        el_id = el.get('id')
        if el_id and el_id.startswith('calibre_link'):
            del el['id']
            n_attrs += 1

    try:
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(str(soup))
    except Exception as e:
        print(f"Warning: could not write sanitized HTML: {e}")
        return False

    print(f"Sanitized calibre HTML: unwrapped {n_anchors} anchor(s), "
          f"{n_spans} span(s), cleared {n_attrs} attribute(s)")
    return True


# Writer extensions that stop pandoc from re-introducing attribute syntax.
# raw_html stays ENABLED: HTML input legitimately carries <sup>, <table>, <br>.
_MD_WRITER = ('markdown-bracketed_spans-native_spans-native_divs'
              '-header_attributes-link_attributes-inline_code_attributes'
              '-markdown_attribute+tex_math_dollars')


def convert_html_to_markdown(html_file, md_file, strip_page_numbers=False):
    """Convert HTML to Markdown using pandoc"""
    try:
        import pypandoc

        pypandoc.convert_file(
            html_file,
            _MD_WRITER,
            outputfile=md_file,
            extra_args=['--wrap=none']
        )

        if os.path.exists(md_file):
            with open(md_file, 'r', encoding='utf-8') as f:
                content = f.read()

            content = content.replace('\ufeff', '')
            content = content.replace('\u00a0', ' ')
            # Collapse CRLF/CR: see the newline= note on the write below.
            content = content.replace('\r\n', '\n').replace('\r', '\n')
            content = clean_calibre_markers(content, strip_page_numbers=strip_page_numbers)

            with open(md_file, 'w', encoding='utf-8', newline='\n') as f:
                f.write(content)

            print(f"Markdown conversion successful: {md_file}")
            return True
        else:
            print("Markdown file was not created")
            return False
    except ImportError:
        print("pypandoc not found. Install with: pip install pypandoc")
        return False
    except Exception as e:
        print(f"HTML to Markdown conversion failed: {e}")
        return False


_PAGE_SEQUENCE_MIN_LENGTH = 4
_PAGE_SEQUENCE_MIN_RATIO = 0.5


def _detect_page_number_lines(lines):
    """Detect standalone-digit lines that form a monotonic page-number sequence.

    Returns a set of line indices that should be dropped as page numbers.

    Algorithm: collect every standalone-digit line in document order, find the
    Longest Non-Decreasing Subsequence (LNDS) of their integer values via
    bisect_right with parent-pointer reconstruction. If the LNDS is long enough
    and covers a large enough fraction of all standalone digits, treat those
    elements as page numbers. Outliers (years like 1984, chapter numbers,
    citation indices) sit off the monotonic spine and stay preserved.
    """
    digit_indices = []
    digit_values = []
    for i, line in enumerate(lines):
        s = line.strip()
        if s.isdigit():
            digit_indices.append(i)
            digit_values.append(int(s))

    n = len(digit_values)
    if n < _PAGE_SEQUENCE_MIN_LENGTH:
        return set()

    tails = []
    tails_idx = []
    parents = [-1] * n

    for i, v in enumerate(digit_values):
        pos = bisect.bisect_right(tails, v)
        if pos > 0:
            parents[i] = tails_idx[pos - 1]
        if pos == len(tails):
            tails.append(v)
            tails_idx.append(i)
        else:
            tails[pos] = v
            tails_idx[pos] = i

    lnds = []
    cur = tails_idx[-1]
    while cur != -1:
        lnds.append(cur)
        cur = parents[cur]
    lnds.reverse()

    if len(lnds) < _PAGE_SEQUENCE_MIN_LENGTH:
        return set()
    if len(lnds) / n < _PAGE_SEQUENCE_MIN_RATIO:
        return set()

    return {digit_indices[i] for i in lnds}


_CODE_FENCE_RE = re.compile(r'^```.*?^```', re.S | re.M)
_INLINE_CODE_RE = re.compile(r'(?<!`)(`+)(?!`).*?(?<!`)\1(?!`)', re.S)


def _mask_code(content):
    """Replace fenced and inline code with \\x00N\\x00 sentinels.

    Code samples legitimately contain `[x]{...}` and `(#...)`, so unwrapping
    must not reach inside them."""
    store = []

    def take(m):
        store.append(m.group(0))
        return f'\x00{len(store) - 1}\x00'

    content = _CODE_FENCE_RE.sub(take, content)
    content = _INLINE_CODE_RE.sub(take, content)
    return content, store


def _unmask_code(content, store):
    return re.sub(r'\x00(\d+)\x00', lambda m: store[int(m.group(1))], content)


# Bracket body: no unescaped brackets, length-capped so a DOTALL match cannot
# run away across the document.
_BRACKET_BODY = r'(?:[^\[\]\\]|\\.){0,2000}'

# Order matters. Every pattern is anchored on a calibre-specific suffix, which
# is why footnote refs `[^1]`, reference links `[t][r]`, link definitions
# `[r]: url`, real links `[t](http...)` and images `![a](p)` cannot match.
_UNWRAP_PATTERNS = [
    # [text]{.calibreN ...} -> text  (one shot; never strip the braces alone)
    (re.compile(r'(?<!\\)\[(' + _BRACKET_BODY + r')\]\{[^{}]*\.calibre[^{}]*\}', re.S), r'\1'),
    # [text](#calibre_link-N) -> text; (?<![!\\]) preserves ![alt](...)
    (re.compile(r'(?<![!\\])\[(' + _BRACKET_BODY + r')\]\(#calibre_link-\d+\)', re.S), r'\1'),
    # heading attribute blocks: {#calibre_link-N .calibreM}
    (re.compile(r'[ \t]*\{#calibre_link-\d+[^{}]*\}'), ''),
    # Orphaned `[**bold**]` with NO link target following. The lookahead is the
    # whole point: without it (as in the original code) this rule rewrote the
    # real link `[**Bold**](https://x)` into `**Bold**(https://x)`.
    (re.compile(r'(?<![!\\])\[(\*\*[^*\[\]]+\*\*)\](?![\(\[:])'), r'\1'),
    # residual empty link/image shells
    (re.compile(r'(?<!\\)!?\[\s*\]\(\s*\)'), ''),
]

# Applied ONCE, after the fixpoint loop has finished. These must not run inside
# the loop: stripping `{.calibre2}` from `[in out]{.calibre2}` mid-loop would
# orphan the brackets and make the outer span un-unwrappable.
# Safe by construction — they touch no brackets, so no markdown construct can
# be broken by removing them.
_ORPHAN_PATTERNS = [
    (re.compile(r'\{\.calibre[^{}]*\}'), ''),
    (re.compile(r'(?<!\])\(#calibre_link-\d+\)'), ''),
]


def _unwrap_calibre_spans(content):
    """Unwrap calibre bracket spans, looping to a fixpoint.

    Nested spans like `[[a]{.calibre1} b]{.calibre2}` need inner-then-outer
    passes because _BRACKET_BODY deliberately excludes brackets.
    """
    for _ in range(6):
        before = content
        for pattern, repl in _UNWRAP_PATTERNS:
            content = pattern.sub(repl, content)
        if content == before:
            break
    else:
        print("Warning: calibre span unwrapping did not reach a fixpoint in 6 passes")

    # Only now that no bracket span is left to pair with them.
    for pattern, repl in _ORPHAN_PATTERNS:
        content = pattern.sub(repl, content)
    return content


def clean_calibre_markers(content, strip_page_numbers=False):
    """Clean up Calibre-specific markers from markdown content.

    Standalone digit lines are handled in two layers:
      1. If a line is adjacent to Calibre noise (::: fence, .ct}/.cn} marker),
         drop it — clearly leftover.
      2. Otherwise, run LNDS over all standalone digits to detect a monotonic
         page-number sequence and drop those. Outliers like years (1984),
         chapter numbers, and citation indices stay preserved.

    Pass strip_page_numbers=True to bypass both layers and aggressively delete
    every standalone-digit line (legacy behavior).
    """
    # Anchored safety net. sanitize_calibre_html() removes the wrappers at the
    # HTML layer, so normally there is nothing left for these to match; they
    # exist for temp dirs converted before that step, and for inputs where bs4
    # was unavailable.
    #
    # The previous implementation stripped only the `{.calibreN}` half and left
    # the `[`/`]` behind, which is what produced the pervasive `[bracket]`
    # fragmentation. It also carried an unanchored `[**text**]` rule that
    # destroyed legitimate links like `[**bold**](https://x)`.
    content, _code_store = _mask_code(content)
    content = _unwrap_calibre_spans(content)
    content = _unmask_code(content, _code_store)

    # Remove the vertical stamp arXiv prints in the page-1 margin
    # ("arXiv:2606.04980v1 [cs.LG] 3 Jun 2026"), which pdftohtml drops into the
    # middle of the body text.
    #
    # Only the stamp itself is removed, never the whole line: pdftohtml
    # concatenates real body text after it. And the full shape — id + bracketed
    # category + date — is required so that a plain bibliography entry like
    # "arXiv:1803.05457, 2018." is left alone.
    content = re.sub(
        r'arXiv:\d{4}\.\d{4,5}(?:v\d+)?\s*\\?\[[a-zA-Z][\w.\-]*\\?\]\s*'
        r'\d{1,2}\s+[A-Z][a-z]{2}\s+\d{4}\s*',
        '', content
    )

    lines = content.split('\n')

    page_number_lines = set() if strip_page_numbers else _detect_page_number_lines(lines)

    def is_calibre_noise(line):
        s = line.strip()
        if not s:
            return False
        if s.startswith(':::'):
            return True
        if s.endswith('.ct}') or s.endswith('.cn}'):
            return True
        return False

    def prev_nonblank(idx):
        for j in range(idx - 1, -1, -1):
            if lines[j].strip():
                return lines[j]
        return None

    def next_nonblank(idx):
        for j in range(idx + 1, len(lines)):
            if lines[j].strip():
                return lines[j]
        return None

    cleaned_lines = []
    for i, line in enumerate(lines):
        stripped_line = line.strip()

        if stripped_line.startswith(':::'):
            continue
        if stripped_line.endswith('.ct}') or stripped_line.endswith('.cn}'):
            continue

        if re.match(r'^\s*\d+\s*$', line):
            if strip_page_numbers:
                continue
            if i in page_number_lines:
                continue
            prev = prev_nonblank(i)
            nxt = next_nonblank(i)
            if (prev is not None and is_calibre_noise(prev)) or \
               (nxt is not None and is_calibre_noise(nxt)):
                continue
            # else: preserve as real content

        cleaned_lines.append(line)

    content = '\n'.join(cleaned_lines)
    content = re.sub(r'\n{3,}', '\n\n', content)
    return content


# =============================================================================
# Structural block parsing and chunk splitting (Step 3)
# =============================================================================

_MATH_ENV = (r'equation|align|gather|multline|split|eqnarray|displaymath'
             r'|alignat|flalign|cases|array|CD|aligned|gathered')
_MATH_OPEN_RE = re.compile(r'^(?:\$\$|\\\[|\\begin\{(?:' + _MATH_ENV + r')\*?\})')
_MATH_ENV_OPEN_RE = re.compile(r'\\begin\{(?:' + _MATH_ENV + r')\*?\}')
_MATH_ENV_CLOSE_RE = re.compile(r'\\end\{(?:' + _MATH_ENV + r')\*?\}')

# A caption paragraph. Deliberately strict — it requires a caption keyword AND a
# number AND must match at the START of the block, so a body sentence that
# merely mentions "as Figure 3 shows" is not mistaken for a caption.
_CAPTION_RE = re.compile(
    r'^\s*(?:[*_]{1,2})?\s*'
    r'(?:Fig(?:ure|\.)?|Table|Tab\.|Chart|Algorithm|Alg\.|Listing|Scheme'
    r'|\u56fe|\u8868|\uadf8\ub9bc|\ud45c|Abbildung|Tabelle|Figura|Tabla)'
    r'\s*(?:S|A)?\s*\d+(?:[.\-]\d+)*\s*'
    r'(?:[:.\uff1a\uff0e\u3001\uff09)\]|]|\s|$)', re.IGNORECASE)

_IMG_LINE_RE = re.compile(r'^\s*!\[')

# Raw LaTeX environments that must survive chunking intact. Floats come first so
# \begin{table} claims its inner tabular and \caption as one block.
_LATEX_ENV = (r'table|figure|tabular|longtable|tabularx|wraptable|wrapfigure'
              r'|subfigure|subtable|algorithm|algorithmic|lstlisting|verbatim'
              r'|minted|thebibliography')
_LATEX_ENV_OPEN_RE = re.compile(r'^\\begin\{(' + _LATEX_ENV + r')\*?\}')


def _is_caption(text):
    return bool(_CAPTION_RE.match(text.strip()))


def _is_image_block(text):
    return bool(_IMG_LINE_RE.match(text.strip()))


def weld_figure_blocks(blocks):
    """Fuse image<->caption and table<->caption so a chunk boundary cannot
    separate a figure from the text that explains it.

    An image line and its caption are two separate structural blocks, so
    without this a flush lands between them and the translator sees a caption
    with no figure (or worse, they end up in different chunks translated by
    different sub-agents).
    """
    welded = []
    i = 0
    n = len(blocks)
    while i < n:
        text, btype = blocks[i]

        if btype in ('image', 'paragraph') and _is_image_block(text):
            group = [text]
            j = i + 1
            # image + optional caption paragraph
            if j < n:
                nxt_text, nxt_type = blocks[j]
                if nxt_type == 'paragraph' and (
                    _is_caption(nxt_text) or len(nxt_text.strip()) <= 400
                ) and not _is_image_block(nxt_text):
                    group.append(nxt_text)
                    j += 1
            # a run of consecutive images shares one caption
            while j < n and blocks[j][1] in ('image', 'paragraph') and _is_image_block(blocks[j][0]):
                group.append(blocks[j][0])
                j += 1
                if j < n and blocks[j][1] == 'paragraph' and _is_caption(blocks[j][0]):
                    group.append(blocks[j][0])
                    j += 1
            welded.append(('\n\n'.join(group), 'figure'))
            i = j
            continue

        # caption paragraph immediately followed by its image
        if btype == 'paragraph' and _is_caption(text) and i + 1 < n:
            nxt_text, nxt_type = blocks[i + 1]
            if _is_image_block(nxt_text):
                welded.append((f'{text}\n\n{nxt_text}', 'figure'))
                i += 2
                continue

        # table <-> caption, both orders
        if btype == 'table' and i + 1 < n:
            nxt_text, nxt_type = blocks[i + 1]
            if nxt_type == 'paragraph' and _is_caption(nxt_text):
                welded.append((f'{text}\n\n{nxt_text}', 'table'))
                i += 2
                continue
        if btype == 'paragraph' and _is_caption(text) and i + 1 < n:
            if blocks[i + 1][1] == 'table':
                welded.append((f'{text}\n\n{blocks[i + 1][0]}', 'table'))
                i += 2
                continue

        welded.append((text, btype))
        i += 1

    return welded


def parse_structural_blocks(content):
    """Parse markdown into structural blocks that should not be split.

    Returns list of (text, block_type) tuples where block_type is one of:
    'heading', 'code_block', 'table', 'list', 'blockquote', 'image', 'paragraph'
    """
    blocks = []
    lines = content.split('\n')
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Code block (fenced)
        if stripped.startswith('```'):
            block_lines = [line]
            i += 1
            while i < len(lines):
                block_lines.append(lines[i])
                if lines[i].strip().startswith('```') and len(block_lines) > 1:
                    i += 1
                    break
                i += 1
            blocks.append(('\n'.join(block_lines), 'code_block'))
            continue

        # Heading
        if re.match(r'^#{1,6}\s', stripped):
            blocks.append((line, 'heading'))
            i += 1
            continue

        # Raw LaTeX float/table environments, kept whole. These reach the
        # markdown as raw LaTeX (pandoc cannot parse tabular), so without this
        # they fall through to the paragraph branch and get split mid-table.
        # Matching the OUTER environment first means \begin{table} carries its
        # \caption and inner tabular along with it.
        env_open = _LATEX_ENV_OPEN_RE.match(stripped)
        if env_open:
            env_name = env_open.group(1)
            close_re = re.compile(r'\\end\{' + re.escape(env_name) + r'\*?\}')
            open_re = re.compile(r'\\begin\{' + re.escape(env_name) + r'\*?\}')
            block_lines = [line]
            depth = len(open_re.findall(line)) - len(close_re.findall(line))
            i += 1
            while i < len(lines) and depth > 0:
                block_lines.append(lines[i])
                depth += len(open_re.findall(lines[i])) - len(close_re.findall(lines[i]))
                i += 1
            blocks.append(('\n'.join(block_lines), 'latex_env'))
            continue

        # Display math. Must be tested BEFORE the `|`-table branch: an `array`
        # row legitimately starts with `|`, and before the paragraph fallback,
        # which would otherwise swallow a formula and let it be split mid-way.
        if _MATH_OPEN_RE.match(stripped):
            block_lines = [line]
            if stripped.startswith('$$'):
                closed = stripped.count('$$') >= 2       # one-liner $$x$$
            elif stripped.startswith('\\['):
                closed = '\\]' in stripped[2:]
            else:
                closed = False
            depth = (len(_MATH_ENV_OPEN_RE.findall(line))
                     - len(_MATH_ENV_CLOSE_RE.findall(line)))
            i += 1
            while i < len(lines) and not closed:
                block_lines.append(lines[i])
                cur = lines[i]
                if stripped.startswith('$$'):
                    if '$$' in cur:
                        closed = True
                elif stripped.startswith('\\['):
                    if '\\]' in cur:
                        closed = True
                else:
                    # Depth counting keeps \begin{equation}\begin{split}...
                    # together as one block.
                    depth += (len(_MATH_ENV_OPEN_RE.findall(cur))
                              - len(_MATH_ENV_CLOSE_RE.findall(cur)))
                    if depth <= 0:
                        closed = True
                i += 1
            blocks.append(('\n'.join(block_lines), 'equation'))
            continue

        # Blockquote
        if stripped.startswith('>'):
            block_lines = [line]
            i += 1
            while i < len(lines) and (lines[i].strip().startswith('>') or
                                       (lines[i].strip() and not re.match(r'^#{1,6}\s', lines[i].strip())
                                        and not lines[i].strip().startswith('```')
                                        and not lines[i].strip().startswith('|')
                                        and not re.match(r'^[-*+]\s', lines[i].strip())
                                        and not re.match(r'^\d+\.\s', lines[i].strip())
                                        and block_lines[-1].strip().startswith('>'))):
                block_lines.append(lines[i])
                i += 1
            blocks.append(('\n'.join(block_lines), 'blockquote'))
            continue

        # Table (lines starting with |)
        if stripped.startswith('|'):
            block_lines = [line]
            i += 1
            while i < len(lines) and lines[i].strip().startswith('|'):
                block_lines.append(lines[i])
                i += 1
            blocks.append(('\n'.join(block_lines), 'table'))
            continue

        # List (unordered or ordered)
        if re.match(r'^[-*+]\s', stripped) or re.match(r'^\d+\.\s', stripped):
            block_lines = [line]
            i += 1
            while i < len(lines):
                s = lines[i].strip()
                # Continue list: list items, indented continuation, or blank lines within list
                if (re.match(r'^[-*+]\s', s) or re.match(r'^\d+\.\s', s) or
                        (lines[i].startswith('  ') and s) or
                        (s == '' and i + 1 < len(lines) and
                         (re.match(r'^[-*+]\s', lines[i+1].strip()) or
                          re.match(r'^\d+\.\s', lines[i+1].strip()) or
                          lines[i+1].startswith('  ')))):
                    block_lines.append(lines[i])
                    i += 1
                else:
                    break
            blocks.append(('\n'.join(block_lines), 'list'))
            continue

        # Image line (standalone or with surrounding caption)
        if re.match(r'!\[', stripped):
            blocks.append((line, 'image'))
            i += 1
            continue

        # Empty line — just a paragraph separator
        if stripped == '':
            blocks.append((line, 'paragraph'))
            i += 1
            continue

        # Regular paragraph — collect contiguous non-empty, non-special lines
        block_lines = [line]
        i += 1
        while i < len(lines):
            s = lines[i].strip()
            if (s == '' or s.startswith('```') or re.match(r'^#{1,6}\s', s) or
                    s.startswith('>') or s.startswith('|') or
                    re.match(r'^[-*+]\s', s) or re.match(r'^\d+\.\s', s) or
                    re.match(r'!\[', s)):
                break
            block_lines.append(lines[i])
            i += 1
        blocks.append(('\n'.join(block_lines), 'paragraph'))
        continue

    return blocks


# A heading only ends the current chunk once the chunk is already substantial.
# Without this floor, a document with many short sections (i.e. any real paper,
# where every subsection is a heading) is shattered into dozens of tiny chunks —
# measured: 42 chunks averaging 1.7 KB, nine of them under 500 bytes. Tiny
# chunks cost a sub-agent call each and give the translator almost no context.
_HEADING_FLUSH_MIN_RATIO = 0.6


def merge_blocks_to_chunks(blocks, target_size=6000):
    """Merge structural blocks into chunks respecting target_size.

    Splits at heading boundaries when the current chunk is already large enough
    to stand alone. Never splits within a single structural block unless the
    block itself exceeds target_size * 2.
    """
    chunks = []
    current_parts = []
    current_size = 0
    heading_floor = target_size * _HEADING_FLUSH_MIN_RATIO

    def flush():
        nonlocal current_parts, current_size
        if current_parts:
            chunks.append('\n'.join(current_parts))
            current_parts = []
            current_size = 0

    for text, btype in blocks:
        block_size = len(text)

        # If a single block is oversized, handle degradation
        if block_size > target_size * 2:
            flush()
            print(f"  WARNING: Oversized {btype} block ({block_size} chars), force-splitting")
            sub_chunks = _force_split_block(text, target_size, btype=btype)
            chunks.extend(sub_chunks)
            continue

        # Prefer to split at heading boundaries — but only once the accumulated
        # chunk is worth emitting on its own.
        if btype == 'heading' and current_size >= heading_floor:
            flush()

        # Would adding this block exceed target?
        if current_size + block_size > target_size and current_parts:
            flush()

        current_parts.append(text)
        current_size += block_size

    flush()
    return chunks


def _force_split_block(text, target_size, btype=None):
    """Force-split an oversized block by paragraph (empty lines), then by lines.

    For fenced code blocks, each resulting chunk gets proper opening/closing fences
    so it remains valid Markdown.

    Equations and welded figures are never split: a bisected formula renders as
    garbage, and an over-target chunk is strictly better than that.
    """
    if btype in ('equation', 'figure', 'latex_env'):
        print(f"  NOTE: oversized {btype} block ({len(text)} chars) kept intact "
              f"— chunk will exceed the target size")
        return [text]

    stripped = text.strip()
    is_fenced_code = stripped.startswith('```')

    # Extract fence info for code blocks
    fence_opener = ''
    if is_fenced_code:
        first_line = stripped.split('\n', 1)[0]
        fence_opener = first_line  # e.g. "```python"

    # Try splitting by empty lines first (not applicable for code blocks — no empty lines expected)
    if not is_fenced_code:
        # Empty pieces come out of this split whenever the block starts or
        # ends on a blank line, and a piece made only of those is a chunk
        # with nothing in it: DeeR-VLA produced chunk0017 at zero bytes, a
        # sub-agent would have been dispatched to translate it, and the
        # merge refused the empty output it came back with.
        paragraphs = [p for p in re.split(r'\n\n+', text) if p.strip()]
        if len(paragraphs) > 1:
            chunks = []
            current = []
            current_size = 0
            for para in paragraphs:
                para_size = len(para)
                if current_size + para_size > target_size and current:
                    chunks.append('\n\n'.join(current))
                    current = [para]
                    current_size = para_size
                else:
                    current.append(para)
                    current_size += para_size
            if current:
                chunks.append('\n\n'.join(current))
            return chunks

    # Split by lines
    lines = text.split('\n')

    # For code blocks, strip the opening and closing fences before splitting content
    if is_fenced_code:
        # Remove opening fence line
        content_lines = lines[1:]
        # Remove closing fence line if present
        if content_lines and content_lines[-1].strip().startswith('```'):
            content_lines = content_lines[:-1]
        lines = content_lines

    chunks = []
    current = []
    current_size = 0
    for line in lines:
        line_size = len(line) + 1
        if current_size + line_size > target_size and current:
            chunks.append('\n'.join(current))
            current = [line]
            current_size = line_size
        else:
            current.append(line)
            current_size += line_size
    if current:
        chunks.append('\n'.join(current))

    # The line path can leave an empty piece behind too, the same way the
    # paragraph path did: a block that is only blank lines splits into
    # nothing at all. Filter here so the function never hands back a chunk
    # with no content, whichever path produced it.
    chunks = [c for c in chunks if c.strip()]

    # Re-wrap each chunk in fences for code blocks
    if is_fenced_code:
        chunks = [f"{fence_opener}\n{chunk}\n```" for chunk in chunks]

    return chunks



# The reference list is kept in the original language, so it must not share a
# chunk with anything that is translated: a mixed chunk costs a full
# translation to get most of its text back unchanged, and it is the chunk
# where the exemption starts leaking onto real prose.
_BIB_OPEN_RE = re.compile(
    r'\\begin\{thebibliography\}|\\bibitem\b'
    r'|^#{1,6}\s*(?:\d+\.?\s*)?(?:References?|Bibliography)\s*$',
    re.MULTILINE | re.IGNORECASE)
_BIB_CLOSE_RE = re.compile(r'\\end\{thebibliography\}')
_HEADING_BLOCK_RE = re.compile(r'^(#{1,6})\s+\S', re.MULTILINE)


def _block_text(block):
    """A structural block is a (text, kind) tuple. Read it, do not guess."""
    if isinstance(block, tuple) and block:
        return block[0] if isinstance(block[0], str) else ''
    return block if isinstance(block, str) else ''


def _is_reference_block(block):
    """Is this block a bibliography entry (or several)?

    Uses verify_chunk's line predicate, which is the calibrated one. No
    second opinion about what a citation looks like.
    """
    lines = [x for x in _block_text(block).split('\n') if x.strip()]
    if not lines:
        return False
    return sum(1 for x in lines if _is_reference_line(x)) >= len(lines) * 0.9


def segment_blocks_by_bibliography(blocks):
    r"""[(is_bibliography, [block, ...]), ...] in document order.

    A run starts at the first block that opens a bibliography and ends at
    \end{thebibliography} or at the next heading of the same level or higher
    -- some papers put an appendix after their references, and that appendix
    is ordinary content.
    """
    segments, current, in_bib, level = [], [], False, 1

    def flush():
        if current:
            segments.append((in_bib, list(current)))
            del current[:]

    dense = [_is_reference_block(b) for b in blocks]
    for index, block in enumerate(blocks):
        text = _block_text(block)
        # Two consecutive reference-dense blocks also open a run: a paper
        # whose references came through citeproc has no marker and no
        # heading, only entries.
        # The next NON-EMPTY block: entries are separated by blank ones,
        # so looking at index + 1 always found a blank and never opened.
        nxt = next((j for j in range(index + 1, len(blocks))
                    if _block_text(blocks[j]).strip()), None)
        opens = bool(_BIB_OPEN_RE.search(text)) or (
            dense[index] and nxt is not None and dense[nxt])
        if not in_bib and opens:
            flush()
            in_bib = True
            heading = _HEADING_BLOCK_RE.search(text)
            level = len(heading.group(1)) if heading else 1
            current.append(block)
            if _BIB_CLOSE_RE.search(text):
                flush()
                in_bib = False
            continue
        if in_bib:
            heading = _HEADING_BLOCK_RE.search(text)
            if heading and len(heading.group(1)) <= level:
                flush()
                in_bib = False
                current.append(block)
                continue
            # A block holding a `\bibitem` is not prose, whatever its density
            # says. Without this test the run ended on every second entry and
            # reopened on the next: the segments alternated, and exactly half
            # the bibliography lost its exemption — 20 of Attention's 41
            # entries and 25 of ResNet's 51 were dispatched to a sub-agent to
            # be TRANSLATED, which is the one thing a reference must not be.
            if (text.strip() and not dense[index]
                    and not _BIB_CLOSE_RE.search(text)
                    and not _BIB_OPEN_RE.search(text)):
                flush()                      # prose again: the run is over
                in_bib = False
                current.append(block)
                continue
            current.append(block)
            if _BIB_CLOSE_RE.search(text):
                flush()
                in_bib = False
            continue
        current.append(block)
    flush()
    return segments

def split_markdown_structured(md_file, temp_dir, target_size=6000, math_guard_on=True):
    """Split markdown into structural chunks.

    Returns list of chunk filenames (e.g. ['chunk0001.md', ...]).

    With math_guard_on, formulas/citations/raw-LaTeX floats are replaced by
    opaque tokens in the chunks (never in input.md, which stays the readable
    canonical conversion) and recorded in per-chunk .math.json sidecars. The
    translator then cannot corrupt a formula because it never sees one.

    A useful side effect: a display equation collapses to a single-line token
    before block parsing, making it structurally unsplittable.
    """
    try:
        with open(md_file, 'r', encoding='utf-8') as f:
            content = f.read()

        all_spans = []
        if math_guard_on:
            content, all_spans = math_guard.protect(content)
            if all_spans:
                kinds = {}
                for s in all_spans:
                    kinds[s['kind']] = kinds.get(s['kind'], 0) + 1
                summary = ', '.join(f'{k}={v}' for k, v in sorted(kinds.items()))
                print(f"Math guard: protected {len(all_spans)} span(s) ({summary})")

        blocks = parse_structural_blocks(content)
        blocks = weld_figure_blocks(blocks)

        # Chunk each segment on its own, in place, so no chunk ever mixes the
        # reference list with text that has to be translated.
        chunk_texts, reference_chunks = [], set()
        for is_bib, group in segment_blocks_by_bibliography(blocks):
            if is_bib:
                # One chunk, whatever its size. The target size bounds
                # what a translator holds at once and nothing translates
                # this; splitting it only produced a 165-character tail.
                pieces = ['\n\n'.join(_block_text(b) for b in group)]
            else:
                pieces = merge_blocks_to_chunks(group, target_size)
            for text in pieces:
                # Whatever path produced it, a chunk with nothing in it is
                # a sub-agent dispatched to translate a blank file and a
                # merge that then refuses the blank it gets back.
                if not text.strip():
                    continue
                chunk_texts.append(text)
                if is_bib:
                    reference_chunks.add(len(chunk_texts))

        chunk_files = []
        for i, chunk_text in enumerate(chunk_texts, 1):
            filename = f"chunk{i:04d}.md"
            chunk_file = os.path.join(temp_dir, filename)
            with open(chunk_file, 'w', encoding='utf-8', newline='\n') as f:
                f.write(chunk_text)
            if all_spans:
                math_guard.write_sidecar(
                    temp_dir, filename,
                    math_guard.spans_for_chunk(chunk_text, all_spans)
                )
            chunk_files.append(filename)
            if i in reference_chunks:
                # Its translation IS the original. Writing it now means the
                # planner finds a valid output and never dispatches an agent.
                out = os.path.join(temp_dir, 'output_' + filename)
                with open(out, 'w', encoding='utf-8', newline='\n') as f:
                    f.write(chunk_text)

        if reference_chunks:
            saved = sum(len(chunk_texts[i - 1]) for i in sorted(reference_chunks))
            print(f"Reference list: {len(reference_chunks)} chunk(s), "
                  f"{saved} characters — copied, not translated")

        print(f"Split into {len(chunk_files)} chunks")
        for filename in chunk_files:
            filepath = os.path.join(temp_dir, filename)
            size = os.path.getsize(filepath)
            print(f"  {filename}: {size} characters")

        return chunk_files
    except Exception as e:
        print(f"Error splitting markdown: {e}")
        return []


def _find_existing_chunk_files(temp_dir):
    """Find existing chunk source filenames (excluding output_ prefixed), sorted."""
    chunk_files = glob.glob(os.path.join(temp_dir, 'chunk*.md'))
    chunk_files = [os.path.basename(f) for f in chunk_files if not os.path.basename(f).startswith('output_')]
    return sorted(chunk_files)


def create_config_file(temp_dir, input_file, input_lang, output_lang, metadata=None,
                       backend='calibre', arxiv_id=None, math_guard_on=True):
    """Create config.txt file for the pipeline"""
    try:
        config_file = os.path.join(temp_dir, "config.txt")

        config_content = f"""# Translation Configuration
input_file={input_file}
input_lang={input_lang}
output_lang={output_lang}
conversion_method={backend}
"""
        config_content += "math_guard=" + ("on" if math_guard_on else "off") + "\n"
        if arxiv_id:
            config_content += f"arxiv_id={arxiv_id}\n"
        if metadata:
            config_content += f"\n# Book Metadata\n"
            if 'title' in metadata:
                config_content += f"original_title={metadata['title']}\n"
            if 'creator' in metadata:
                config_content += f"creator={metadata['creator']}\n"
            if 'publisher' in metadata:
                config_content += f"publisher={metadata['publisher']}\n"
            if 'language' in metadata:
                config_content += f"source_language={metadata['language']}\n"

        with open(config_file, 'w', encoding='utf-8') as f:
            f.write(config_content)

        print(f"Created config file: {config_file}")
        return True
    except Exception as e:
        print(f"Error creating config file: {e}")
        return False


def _chunks_contain_unprotected_math(temp_dir, chunk_names):
    """True if any existing chunk still holds raw LaTeX math."""
    probe = re.compile(r'\$|\\begin\{(?:equation|align|gather|multline)')
    for name in chunk_names:
        try:
            with open(os.path.join(temp_dir, name), encoding='utf-8') as f:
                if probe.search(f.read()):
                    return True
        except OSError:
            continue
    return False


def _do_split_and_manifest(temp_dir, input_md, chunk_size, math_guard_on=True):
    """Split markdown and create manifest. Returns chunk count or 0 on failure."""
    existing = _find_existing_chunk_files(temp_dir)
    if existing:
        print(f"Skipping markdown splitting - found {len(existing)} existing chunk files")
        # Warn, never auto-delete, when reused chunks predate the math guard:
        # re-splitting changes every manifest source_hash and would invalidate
        # every translation already completed against these chunks.
        if math_guard_on and not glob.glob(
                os.path.join(temp_dir, '*' + math_guard.SIDECAR_SUFFIX)):
            if _chunks_contain_unprotected_math(temp_dir, existing):
                print("Warning: existing chunks contain unprotected math and no "
                      ".math.json sidecars.")
                print("  The math guard will NOT apply to this run. Delete "
                      "chunk*.md to re-split with protection")
                print("  (that discards any translations already made against them).")
        # Create/update manifest for existing files
        create_manifest(temp_dir, existing, input_md)
        return len(existing)

    chunk_files = split_markdown_structured(input_md, temp_dir, chunk_size,
                                            math_guard_on=math_guard_on)
    if not chunk_files:
        return 0
    create_manifest(temp_dir, chunk_files, input_md)
    return len(chunk_files)


def _check_strip_page_numbers_cache_conflict(strip_flag, temp_dir, input_md):
    """Return list of cached files that would silently neutralize --strip-page-numbers.

    The flag only takes effect inside clean_calibre_markers, which runs during
    HTML→Markdown conversion. If input.md or chunk*.md already exist from a
    prior run, both are reused as-is and the flag becomes a no-op. Surface
    that conflict so the user knows to clean up.
    """
    if not strip_flag:
        return []
    if not os.path.isdir(temp_dir):
        return []

    blockers = []
    if os.path.exists(input_md):
        blockers.append(input_md)

    existing_chunks = [
        f for f in glob.glob(os.path.join(temp_dir, 'chunk*.md'))
        if not os.path.basename(f).startswith('output_')
    ]
    if existing_chunks:
        blockers.append(f"{len(existing_chunks)} chunk file(s) under {temp_dir}/")

    return blockers


def _abort_on_strip_cache_conflict(blockers, temp_dir):
    if not blockers:
        return
    print("Error: --strip-page-numbers cannot take effect because cached files exist:")
    for b in blockers:
        print(f"  - {b}")
    print(f"Delete the cached files (or remove the entire {temp_dir}/ directory) and re-run.")
    sys.exit(1)


def _metadata_from_config(temp_dir):
    """Read book metadata back out of a previously written config.txt."""
    metadata = {}
    config_file = os.path.join(temp_dir, "config.txt")
    if not os.path.exists(config_file):
        return metadata
    keys = {
        'original_title': 'title',
        'creator': 'creator',
        'publisher': 'publisher',
        'source_language': 'language',
    }
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            for line in f:
                if '=' not in line or line.strip().startswith('#'):
                    continue
                key, value = line.strip().split('=', 1)
                if key in keys:
                    metadata[keys[key]] = value
    except Exception as e:
        print(f"Warning: Could not read metadata from config: {e}")
    return metadata


def main():
    """Main conversion function"""
    parser = argparse.ArgumentParser(description="Convert PDF/DOCX/EPUB to markdown chunks via HTMLZ")
    parser.add_argument("input_file", help="Input file (PDF, DOCX, or EPUB)")
    parser.add_argument("-l", "--ilang", default="auto", help="Input language (default: auto)")
    parser.add_argument("--olang", default="zh", help="Output language (default: zh)")
    parser.add_argument("--chunk-size", type=int, default=6000, help="Target chunk size in characters (default: 6000)")
    parser.add_argument(
        "--temp-root",
        default=None,
        help="Directory under which {book_name}_temp/ will be created (default: current working directory)",
    )
    parser.add_argument(
        "--strip-page-numbers",
        action="store_true",
        help="Aggressively delete every standalone-digit line (legacy behavior). "
             "Default is off: standalone digits are preserved unless adjacent to Calibre noise.",
    )
    parser.add_argument(
        "--backend",
        choices=["auto", "calibre", "arxiv"],
        default="auto",
        help="Conversion backend. 'arxiv' converts the paper's LaTeX source, which is "
             "the only path that preserves equations; 'calibre' goes through pdftohtml. "
             "'auto' (default) prefers arxiv when the PDF is an arXiv preprint AND "
             "--allow-network is given.",
    )
    parser.add_argument(
        "--arxiv-id",
        default=None,
        help="Explicit arXiv id (e.g. 2606.04980 or 2606.04980v1). Implies --backend arxiv.",
    )
    parser.add_argument(
        "--no-math-guard",
        action="store_true",
        help="Disable math placeholdering. Debug only: without it the translator "
             "sees raw LaTeX and can silently corrupt formulas.",
    )
    parser.add_argument(
        "--allow-network",
        action="store_true",
        help="Permit the arXiv backend to download the paper's LaTeX source from "
             "arxiv.org. Without it, --backend auto falls back to calibre.",
    )

    args = parser.parse_args()
    input_file = args.input_file

    if not os.path.exists(input_file):
        print(f"Error: Input file not found: {input_file}")
        sys.exit(1)

    file_ext = os.path.splitext(input_file)[1].lower()
    if file_ext not in ['.pdf', '.docx', '.epub']:
        print(f"Error: Unsupported file type: {file_ext}")
        sys.exit(1)

    print("=== File Conversion ===")
    print(f"Input file: {input_file}")
    print(f"Target chunk size: {args.chunk_size} characters")
    if args.temp_root:
        print(f"Temp root: {args.temp_root}")

    backend, arxiv_id, reason = backends.select_backend(
        input_file, args.backend, args.arxiv_id, args.allow_network
    )
    print(f"Backend: {backend} ({reason})")

    htmlz_file = f"{os.path.splitext(input_file)[0]}.htmlz"

    try:
        temp_dir = build_temp_dir(input_file, args.temp_root)
        current_fingerprint = source_fingerprint(input_file)
        _abort_on_source_cache_mismatch(
            *check_source_cache(temp_dir, current_fingerprint), temp_dir=temp_dir
        )
        backends.abort_on_backend_switch(backends.check_backend_switch(temp_dir, backend))

        # --- arXiv LaTeX-source backend ---------------------------------
        if backend == backends.BACKEND_ARXIV:
            input_md = os.path.join(temp_dir, "input.md")
            if os.path.exists(input_md):
                print("Skipping arXiv conversion - input.md already exists")
                metadata = _metadata_from_config(temp_dir)
                # The names live in flat.tex, which is already on disk, so a
                # temp dir converted before this existed picks them up without
                # re-converting anything (K139). Only when the config has none:
                # a value already there came from the PDF's own metadata and is
                # better evidence than a parse of the author block.
                if not metadata.get('creator'):
                    flat = os.path.join(temp_dir, "flat.tex")
                    if os.path.isfile(flat):
                        with open(flat, encoding="utf-8", errors="replace") as fh:
                            names = arxiv_backend.extract_latex_authors(fh.read())
                        if names:
                            metadata['creator'] = names
                            print(f"Authors: read {names.count(';') + 1} name(s) "
                                  f"from the LaTeX; the config carried none")
                ok = True
            else:
                ok, metadata = arxiv_backend.build(
                    input_file, temp_dir, arxiv_id, allow_network=args.allow_network
                )

            if ok:
                chunk_count = _do_split_and_manifest(temp_dir, input_md, args.chunk_size,
                                              math_guard_on=not args.no_math_guard)
                if chunk_count == 0:
                    sys.exit(1)
                create_config_file(temp_dir, input_file, args.ilang, args.olang,
                                   metadata, backend=backend, arxiv_id=arxiv_id,
                               math_guard_on=not args.no_math_guard)
                _write_source_fingerprint(temp_dir, current_fingerprint)
                print("Conversion completed successfully!")
                print(f"Temp directory: {temp_dir}")
                return

            # `--backend arxiv` is documented to fail loudly rather than
            # downgrade, and it did not: ResNet was asked for on the arXiv
            # path, died on one \newcolumntype, and came back through calibre
            # with every equation gone — reported as a successful conversion.
            # An explicit choice of backend is a choice about what the book
            # will contain, so the fallback belongs to `auto` alone.
            if args.backend == backends.BACKEND_ARXIV:
                print("Error: the arXiv backend failed and --backend arxiv "
                      "was requested explicitly.")
                print("  Not falling back: the calibre path cannot recover "
                      "equations, so it would answer a different question.")
                print("  Re-run with --backend auto to accept that trade, or "
                      "fix the cause reported above.")
                sys.exit(1)
            print("arXiv backend failed — falling back to the calibre backend.")
            print("  NOTE: equations cannot be recovered on the calibre path.")
            backend = backends.BACKEND_CALIBRE

        calibre_path = find_calibre_convert()
        if not calibre_path:
            print("Error: Calibre ebook-convert not found")
            print("Please install Calibre: https://calibre-ebook.com/")
            sys.exit(1)

        input_html_path = os.path.join(temp_dir, "input.html")

        if os.path.exists(input_html_path):
            print(f"Skipping HTMLZ conversion - input.html already exists")

            metadata = {}
            config_file = os.path.join(temp_dir, "config.txt")
            if os.path.exists(config_file):
                try:
                    with open(config_file, 'r', encoding='utf-8') as f:
                        for line in f:
                            if '=' in line:
                                key, value = line.strip().split('=', 1)
                                if key == 'original_title':
                                    metadata['title'] = value
                                elif key == 'creator':
                                    metadata['creator'] = value
                                elif key == 'publisher':
                                    metadata['publisher'] = value
                                elif key == 'source_language':
                                    metadata['language'] = value
                except Exception as e:
                    print(f"Warning: Could not read metadata from config: {e}")

            input_md = os.path.join(temp_dir, "input.md")
            _abort_on_strip_cache_conflict(
                _check_strip_page_numbers_cache_conflict(args.strip_page_numbers, temp_dir, input_md),
                temp_dir,
            )
            if os.path.exists(input_md):
                print(f"Skipping HTML to Markdown conversion - input.md already exists")
            else:
                sanitize_calibre_html(input_html_path)
                if not convert_html_to_markdown(input_html_path, input_md, strip_page_numbers=args.strip_page_numbers):
                    sys.exit(1)

            chunk_count = _do_split_and_manifest(temp_dir, input_md, args.chunk_size,
                                              math_guard_on=not args.no_math_guard)
            if chunk_count == 0:
                sys.exit(1)

            create_config_file(temp_dir, input_file, args.ilang, args.olang,
                               metadata, backend=backend, arxiv_id=arxiv_id,
                               math_guard_on=not args.no_math_guard)
            _write_source_fingerprint(temp_dir, current_fingerprint)
            print("Conversion completed successfully!")
            print(f"Temp directory: {temp_dir}")
            return

        if not convert_to_htmlz(input_file, htmlz_file, calibre_path):
            sys.exit(1)

        with tempfile.TemporaryDirectory() as extract_dir:
            html_file, images_dir = extract_htmlz(htmlz_file, extract_dir)
            if not html_file:
                sys.exit(1)

            metadata = extract_metadata_from_htmlz(extract_dir)

            temp_dir = setup_temp_directory(input_file, html_file, images_dir, temp_root=args.temp_root)
            if not temp_dir:
                sys.exit(1)

            input_html = os.path.join(temp_dir, "input.html")
            input_md = os.path.join(temp_dir, "input.md")

            _abort_on_strip_cache_conflict(
                _check_strip_page_numbers_cache_conflict(args.strip_page_numbers, temp_dir, input_md),
                temp_dir,
            )
            if os.path.exists(input_md):
                print(f"Skipping HTML to Markdown conversion - input.md already exists")
            else:
                sanitize_calibre_html(input_html)
                if not convert_html_to_markdown(input_html, input_md, strip_page_numbers=args.strip_page_numbers):
                    sys.exit(1)

            chunk_count = _do_split_and_manifest(temp_dir, input_md, args.chunk_size,
                                              math_guard_on=not args.no_math_guard)
            if chunk_count == 0:
                sys.exit(1)

            create_config_file(temp_dir, input_file, args.ilang, args.olang,
                               metadata, backend=backend, arxiv_id=arxiv_id,
                               math_guard_on=not args.no_math_guard)
            _write_source_fingerprint(temp_dir, current_fingerprint)

            print("Conversion completed successfully!")
            print(f"Temp directory: {temp_dir}")
            print(f"Markdown chunks: {chunk_count} files")

            if os.path.exists(htmlz_file):
                os.remove(htmlz_file)

    except KeyboardInterrupt:
        print("\nConversion interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

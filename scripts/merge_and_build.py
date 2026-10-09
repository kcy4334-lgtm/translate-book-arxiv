#!/usr/bin/env python3
"""
merge_and_build.py - Merge translated pages and build final outputs
Combines original steps 4-7: merge -> HTML -> TOC -> DOCX/EPUB/PDF

Usage: merge_and_build.py --temp-dir <path> [--title <title>] [--author <author>] [--lang <lang>]
"""

import os
import sys
import re
import glob
import shutil
import subprocess
import tempfile
import zipfile
import argparse
import html as _html_lib
from collections import Counter
from pathlib import Path

import json

import algorithm_float
import glossary
import math_guard
import layout
import chromium_pdf
import equation_fit
import table_language
from manifest import read_output_text, validate_for_merge

# Windows consoles default to a legacy codepage (e.g. cp949), which raises
# UnicodeEncodeError on em-dashes and CJK in our own progress output. Force
# UTF-8 so a real error is never masked by an encoding traceback.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError, OSError):
        pass

# Most of the build lives in four modules beside this one, split out so no
# file goes over the 256 KiB Anthropic's plugin directory reads before it will
# publish a release. Every name the build below uses, or a test or another
# script reaches for as merge_and_build.<name>, is imported back here.
from build_common import (
    _CAPTION_CMD_RE, _PANDOC_PATH, _balanced_group, _in_latex_comment,
    _scan_image_refs, _scan_img_tags, drop_false_conditionals, resolve_pandoc,
    strip_tex_comments,
)
from numbering import (
    _CODE_DRAWN_FIGURES, _COUNTED_STRUCTURAL_ENVS, _DEFAULT_THEOREM_ENVS,
    _FIG_IMAGE_RE, _NUMBERED_MATH_ENVS, _PANEL_WIDTH, _PANEL_WIDTH_MANY,
    _counter_label, _graphic_stem, _label_token_re, _numbers_for_block,
    _spacing_only_prefix, _xref_regex, apply_graphics_trim,
    build_bibitem_numbers, build_float_numbers, build_label_index,
    build_label_numbers, build_subfigure_letters, counter_events,
    drop_doubled_labels, equation_numbers, figures_with_captions,
    fix_particles, flat_equation_numbers, float_units, format_figure_blocks,
    read_class_conventions, read_counter_parents, read_fixed_counter_prefix,
    read_float_units, read_theorem_environments, read_theorem_parents,
    resolve_bare_float_labels, resolve_references,
    resolve_unprefixed_references, roman_numeral, tag_equations_for_markdown,
    tag_equations_in_html, template_affixes, unwrap_prose_environments,
)
from latex_cleanup import (
    _SPACING_INLINE_RE, _TEXMATH_READS, _longest_prefix_match,
    _math_extended_match, _normalize_heading, _prefix_fits_level, _source_pdf,
    _texmath_reads, clean_heading_title, drop_directive_spans,
    drop_index_terms, enough_located, expand_math_macros, locatable_headings,
    normalize_latex_leftovers, normalize_math_commands, number_sections,
    number_theorem_statements, prefixes_from_lines, read_math_macros,
    read_pdf_section_prefixes, read_tex_headings, rescue_orphan_footnotes,
    resolve_math_references, rewrite_sideset, rewrite_subcaptions,
    rewrite_text_fonts_in_math, split_nested_math_text, theorem_declarations,
    unwrap_text_boxed_math_fonts,
)
from latex_tables import (
    _FRAGMENT_WRITER, _TBODY_RE, _TEXT_MACRO_RE, _TR_RE, _clean_colspec,
    _extract_caption, _is_markdown_table, _latex_fragment_to_markdown,
    _widen_to_float, body_rule_rows, build_citation_labels,
    build_citation_labels_from_bib, check_badge_placement,
    count_raw_latex_tables, expand_raw_latex_tables, find_raw_latex_tables,
    fragment_reference_numbers, grid_tables_to_pipe, header_row_count,
    labelled_group_starts, mark_body_rules, mark_shaded_rows,
    markdown_table_captions, normalise_tabular_preambles,
    number_table_captions, promote_header_rows, read_one_argument_macros,
    resolve_fragment_citations, resolve_fragment_references,
    rewrite_color_declarations, shaded_body_rows, simplify_symbol_math,
    split_row_groups, substitute_dings, unwrap_tabbing,
    unwrap_table_cell_wrappers,
)


def _validate_chunk_images(temp_dir):
    """Verify each output_chunk*.md preserves the image structure of its chunk*.md.

    Bad-attribute detection uses a per-chunk DELTA: a malformed <img> attribute
    is flagged only if it appears in the output chunk but not in the source
    chunk. This avoids false positives on code blocks that legitimately contain
    deliberately-broken <img> examples — both chunks carry the same example, so
    the delta is empty.

    Returns False on any divergence; collects all errors and prints them
    together so an agent can fix many chunks in one pass.
    """
    temp_path = Path(temp_dir)
    errors = []
    for src_chunk in sorted(temp_path.glob('chunk*.md')):
        if src_chunk.name.startswith('output_'):
            continue
        out_chunk = temp_path / f'output_{src_chunk.name}'
        if not out_chunk.exists():
            continue  # missing-output is the manifest validator's job
        src_html, src_md, src_bad = _scan_image_refs(src_chunk.read_text(encoding='utf-8'))
        out_html, out_md, out_bad = _scan_image_refs(out_chunk.read_text(encoding='utf-8'))

        src_bad_counts = Counter(name for _, name in src_bad)
        out_bad_counts = Counter(name for _, name in out_bad)
        new_bad_counts = out_bad_counts - src_bad_counts
        if new_bad_counts:
            new_bad_examples = [
                (raw_tag, attr_name)
                for raw_tag, attr_name in out_bad
                if new_bad_counts.get(attr_name, 0) > 0
            ]
            for raw_tag, attr_name in new_bad_examples:
                errors.append(
                    f"ERROR: {out_chunk.name} introduced malformed <img> tag (not present in source)\n"
                    f"  tag: {raw_tag}\n"
                    f"  problem: attribute name '{attr_name}' is not a valid HTML identifier\n"
                    f"  likely cause: an unescaped quote inside alt=\"...\" or title=\"...\" closed the attribute early\n"
                    f"  fix: in {out_chunk.name}, replace the inner quote with a curly quote in the target language or with &quot; / &#39;\n"
                    f"  source chunk for reference: {src_chunk.name}"
                )

        if src_html != out_html or src_md != out_md:
            errors.append(
                f"ERROR: {out_chunk.name} image references diverge from {src_chunk.name}\n"
                f"  missing <img src> (count): {sorted((src_html - out_html).items()) or 'none'}\n"
                f"  extra   <img src> (count): {sorted((out_html - src_html).items()) or 'none'}\n"
                f"  missing ![](path) (count): {sorted((src_md - out_md).items()) or 'none'}\n"
                f"  extra   ![](path) (count): {sorted((out_md - src_md).items()) or 'none'}\n"
                f"  fix: restore the missing image refs in {out_chunk.name} from {src_chunk.name}"
            )

    if errors:
        print("\n=== Image validation failed ===")
        for e in errors:
            print(e)
            print()
        return False
    return True


def _chunk_id_from_output(path):
    """output_chunk0001.md -> chunk0001.md"""
    name = os.path.basename(path)
    return name[len('output_'):] if name.startswith('output_') else name


def _latex_shape(text):
    """Structural fingerprint of the LaTeX in one chunk.

    Deliberately excludes the raw backslash count: the translation prompt
    explicitly allows deleting line-ending backslashes, so that number moves
    legitimately. What must NOT move is environment balance and the row/cell
    structure inside a tabular -- translation changes cell TEXT, never the
    grid around it.
    """
    envs = Counter(re.findall(r'\\begin\{([^}]+)\}', text))
    ends = Counter(re.findall(r'\\end\{([^}]+)\}', text))
    blocks = []
    for t in find_raw_latex_tables(text):
        bare = t['bare']
        blocks.append({
            'rows': bare.count('\\\\'),
            'cells': bare.count('&'),
            'rules': (bare.count('\\toprule') + bare.count('\\midrule')
                      + bare.count('\\bottomrule') + bare.count('\\hline')),
        })
    return {'begin': envs, 'end': ends, 'blocks': blocks}


def _validate_chunk_latex(temp_dir):
    """Verify each translated chunk kept the LaTeX skeleton of its source.

    A shell heredoc silently collapses `\\\\` to `\\`, which strips every row
    separator out of a tabular. The table then renders as one run-on row, or
    fails to convert at all -- and nothing else in the pipeline notices,
    because the text is all still there.
    """
    temp_path = Path(temp_dir)
    errors = []
    for out in sorted(temp_path.glob('output_chunk*.md')):
        stem = out.name[len('output_'):]
        srcf = temp_path / stem
        if not srcf.exists():
            continue
        try:
            a = _latex_shape(srcf.read_text(encoding='utf-8'))
            b = _latex_shape(out.read_text(encoding='utf-8'))
        except OSError as e:
            errors.append(f"ERROR: {out.name}: {e}")
            continue

        problems = []
        for env in sorted(set(a['begin']) | set(b['begin'])):
            if a['begin'][env] != b['begin'][env]:
                problems.append(f"\\begin{{{env}}}: source {a['begin'][env]} "
                                f"-> output {b['begin'][env]}")
        for env in sorted(set(a['end']) | set(b['end'])):
            if a['end'][env] != b['end'][env]:
                problems.append(f"\\end{{{env}}}: source {a['end'][env]} "
                                f"-> output {b['end'][env]}")
        if len(a['blocks']) != len(b['blocks']):
            problems.append(f"tabular blocks: source {len(a['blocks'])} "
                            f"-> output {len(b['blocks'])}")
        else:
            for i, (x, y) in enumerate(zip(a['blocks'], b['blocks']), 1):
                for key, human in (('rows', 'row separators (\\\\)'),
                                   ('cells', 'cell separators (&)'),
                                   ('rules', 'booktabs rules')):
                    if x[key] != y[key]:
                        problems.append(f"table {i} {human}: source {x[key]} "
                                        f"-> output {y[key]}")
        if problems:
            errors.append(
                f"ERROR: {out.name} lost LaTeX structure\n"
                + ''.join(f"  {p}\n" for p in problems[:8])
                + f"  cause: the translated file was almost certainly written "
                  f"through a shell\n"
                  f"         heredoc/printf, which collapses '\\\\' to '\\'.\n"
                  f"  fix: rewrite {out.name} with the LaTeX skeleton copied "
                  f"verbatim from\n"
                  f"       {stem} (use a file-writing tool or Python, never the "
                  f"shell), or\n"
                  f"       delete it and re-translate that chunk."
            )

    if errors:
        print("\n=== LaTeX structure validation failed ===")
        for e in errors:
            print(e)
        return False
    return True


def _validate_chunk_math(temp_dir):
    """Verify every math placeholder survived translation exactly once.

    A dropped token means a formula vanished from the book — invisible in the
    build log, obvious to a reader. So this is a hard failure naming the chunk,
    not a warning.

    Chunks with no sidecar are skipped, so temp dirs created before the math
    guard existed still merge unchanged.
    """
    temp_path = Path(temp_dir)
    sidecars = sorted(temp_path.glob('chunk*' + math_guard.SIDECAR_SUFFIX))
    if not sidecars:
        return True

    errors = []
    checked = 0
    for sidecar in sidecars:
        stem = sidecar.name[:-len(math_guard.SIDECAR_SUFFIX)]
        src = temp_path / f'{stem}.md'
        out = temp_path / f'output_{stem}.md'
        if not src.exists() or not out.exists():
            continue
        try:
            spans = math_guard.load_sidecar(temp_dir, f'{stem}.md')
        except (ValueError, OSError, json.JSONDecodeError) as e:
            errors.append(f"ERROR: {sidecar.name}: {e}")
            continue

        checked += 1
        report = math_guard.verify(src.read_text(encoding='utf-8'),
                                  out.read_text(encoding='utf-8'), spans)
        if report['missing'] or report['duplicated'] or report['foreign']:
            errors.append(
                f"ERROR: output_{stem}.md corrupted math placeholders\n"
                f"  dropped by translator : {report['missing'][:10] or 'none'}\n"
                f"  duplicated            : {report['duplicated'][:10] or 'none'}\n"
                f"  not from this chunk   : {report['foreign'][:10] or 'none'}\n"
                f"  fix: delete output_{stem}.md and re-translate that chunk. Every\n"
                f"       ⟦M####⟧ / ⟦C####⟧ / ⟦T####⟧ token must be copied\n"
                f"       through verbatim, exactly once."
            )

    if errors:
        print("\n=== Math placeholder validation failed ===")
        for e in errors:
            print(e)
            print()
        return False

    if checked:
        print(f"Math placeholder check: {checked} chunk(s) OK")
    return True


def _restore_math_for(temp_dir, output_path, content):
    """Substitute math tokens back to LaTeX at merge-read time.

    Deliberately non-destructive: rewriting output_chunk*.md in place would flip
    run_state's output-hash check for every chunk and make resume logic think
    every translation had changed.
    """
    chunk_name = _chunk_id_from_output(output_path)
    try:
        spans = math_guard.load_sidecar(temp_dir, chunk_name)
    except (ValueError, OSError, json.JSONDecodeError) as e:
        print(f"Warning: {e}")
        return content
    if spans is None:
        return content  # pre-upgrade temp dir: no-op
    return math_guard.restore(content, spans)


def _check_generated_html_sanity(html_path):
    """Sanity-check generated HTML for malformed <img> tags. Returns False on problems.

    Note: we deliberately do NOT flag `&lt;img` in the rendered HTML — books that
    discuss HTML in prose or code blocks legitimately render escaped `<img>` text,
    and that's not a corruption signal. Real corruption produces a malformed
    actual `<img>` tag, which the attribute-name check catches."""
    try:
        text = Path(html_path).read_text(encoding='utf-8')
    except Exception as e:
        print(f"ERROR: cannot read {html_path}: {e}")
        return False

    _, bad_attrs = _scan_img_tags(text)
    if not bad_attrs:
        return True

    print(f"ERROR: image sanity check failed on {Path(html_path).name}")
    for raw_tag, attr_name in bad_attrs:
        print(f"  - malformed <img>: {raw_tag}")
        print(f"    bad attribute name: '{attr_name}'")
    print(
        "  fix: inspect output.md and the corresponding output_chunk*.md;\n"
        "       if alt text contains literal quotes, replace with curly quotes or HTML entity"
    )
    return False

# Try to import BeautifulSoup for TOC generation
try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False

# Try to import markdown
try:
    import markdown
    MARKDOWN_AVAILABLE = True
except ImportError:
    MARKDOWN_AVAILABLE = False

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# =============================================================================
# Language configuration — single source of truth for lang-dependent values
# =============================================================================

# The tables themselves live in layout.py so calibre_html_publish.py can
# share the one copy; they used to be duplicated there and had already
# drifted. Re-exported under the old names because callers and tests reach
# for merge_and_build.LANG_CONFIG / .get_lang_config.
LANG_CONFIG = layout.LANG_CONFIG
_DEFAULT_LANG_CONFIG = layout.DEFAULT_LANG_CONFIG
get_lang_config = layout.get_lang_config


def load_config(temp_dir):
    """Load configuration from config.txt"""
    config_file = os.path.join(temp_dir, 'config.txt')
    if not os.path.exists(config_file):
        print("Error: config.txt not found in temp directory.")
        sys.exit(1)

    config = {}
    with open(config_file, 'r', encoding='utf-8') as f:
        for line in f:
            if '=' in line and not line.strip().startswith('#'):
                key, value = line.strip().split('=', 1)
                config[key] = value
    return config


def natural_sort_key(text):
    """Natural sorting key for filenames with numbers"""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', text)]


# =============================================================================
# Step 4: Merge translated markdown files
# =============================================================================

_LEADING_BLANK_LINES_RE = re.compile(r'\A(?:[ \t]*\r?\n)+')


def trim_chunk_edges(content):
    r"""Drop blank lines around a chunk without touching its indentation.

    `.strip()` stood here, and it also removed the leading spaces of the
    first line. A chunk boundary can fall inside a code listing:
    VLA-Adapter's chunk0012 begins `            # RoPE`, and once those
    twelve spaces are gone markdown reads the line as a top-level heading.
    It reached the book as an H1 with its own table-of-contents entry,
    sitting between two halves of the same Python class.

    The translator was not involved -- `output_chunk0012.md` still had the
    indentation. Only the seam lost it, which is why nothing that reads a
    single chunk could ever have seen this.
    """
    return _LEADING_BLANK_LINES_RE.sub('', content.rstrip())


def merge_markdown_files(temp_dir):
    """Merge all translated output files into output.md"""
    print("=== Merging translated markdown files ===")

    output_md = os.path.join(temp_dir, 'output.md')

    # Always validate manifest, even if output.md exists (catch stale/corrupt outputs)
    ok, ordered_files, warnings = validate_for_merge(temp_dir)

    # Image structure validation runs unconditionally — bad chunks invalidate any cached output.md
    if not _validate_chunk_images(temp_dir):
        if os.path.exists(output_md):
            print("Removing stale output.md (built from chunks that failed image validation)")
            os.remove(output_md)
        return False

    # Math placeholders are compared BEFORE restoration, while both source and
    # translated chunks still hold tokens.
    if not _validate_chunk_math(temp_dir):
        if os.path.exists(output_md):
            print("Removing stale output.md (chunks failed math placeholder validation)")
            os.remove(output_md)
        return False

    # LaTeX skeleton check. Compared BEFORE merging, while each translated
    # chunk can still be matched against the source it came from.
    if not _validate_chunk_latex(temp_dir):
        if os.path.exists(output_md):
            print("Removing stale output.md (chunks failed LaTeX structure validation)")
            os.remove(output_md)
        return False

    # A temp dir cleaned with --cleanup has no chunk*.md left, so
    # validate_for_merge() can never succeed there. In that state output.md is
    # the ONLY surviving copy of the translation — deleting it would destroy
    # hours of work that cannot be rebuilt without re-translating.
    src_chunks_present = any(
        not p.name.startswith('output_') for p in Path(temp_dir).glob('chunk*.md')
    )

    if os.path.exists(output_md):
        if not ok and not src_chunks_present:
            print("Chunk sources absent (post-cleanup temp dir) — reusing existing output.md as-is")
            print("  NOTE: chunk-level validation skipped. Re-run convert.py to re-split if needed.")
            return True
        if not ok:
            print(f"WARNING: output.md exists but manifest validation failed — deleting stale output.md")
            os.remove(output_md)
        else:
            # Check if any output_chunk is newer than output.md (re-translated chunks)
            output_md_mtime = os.path.getmtime(output_md)
            newer_chunks = []
            if ordered_files:
                newer_chunks = [
                    os.path.basename(f) for f in ordered_files
                    if os.path.getmtime(f) > output_md_mtime
                ]
            if newer_chunks:
                print(f"Re-merging — {len(newer_chunks)} chunk(s) newer than output.md: {', '.join(newer_chunks[:5])}{'...' if len(newer_chunks) > 5 else ''}")
                os.remove(output_md)
            else:
                print(f"Skipping merge - output.md already exists and is up to date")
                return True

    if not ok:
        print("ERROR: Merge validation failed. Fix the issues above before merging.")
        return False

    if ordered_files is not None:
        # Manifest-based merge
        print(f"Merging {len(ordered_files)} translated files (manifest-ordered)")
        merged_content = ""
        for file_path in ordered_files:
            content = read_output_text(file_path)
            if content is None:
                print(f"ERROR: Cannot read {os.path.basename(file_path)} — aborting merge")
                return False
            content = trim_chunk_edges(content)
            if not content:
                # validate_for_merge already rejects blank outputs; this is a
                # last line of defense so a chunk can never vanish silently.
                print(f"ERROR: Blank output {os.path.basename(file_path)} — aborting merge")
                return False
            content = _restore_math_for(temp_dir, file_path, content)
            merged_content += content + "\n\n"
    else:
        # Legacy fallback: glob-based merge (no manifest)
        print("WARNING: No manifest.json found — using legacy glob-based merge.")
        print("  For hash validation, re-run convert.py to generate manifest.json")

        # Match chunk output files
        output_files = glob.glob(os.path.join(temp_dir, 'output_chunk*.md'))

        # Count original source files
        original_files = glob.glob(os.path.join(temp_dir, 'chunk*.md'))
        original_files = [f for f in original_files if not os.path.basename(f).startswith('output_')]

        if not output_files:
            print("Error: No translated markdown files found.")
            return False

        # Build expected output filename for each source file and verify 1:1 match
        source_basenames = sorted(
            [os.path.basename(f) for f in original_files],
            key=natural_sort_key
        )
        expected_outputs = set(f"output_{name}" for name in source_basenames)
        actual_outputs = set(os.path.basename(f) for f in output_files)

        missing = expected_outputs - actual_outputs
        orphaned = actual_outputs - expected_outputs

        if missing or orphaned:
            if missing:
                print(f"ERROR: Missing translations for: {', '.join(sorted(missing, key=natural_sort_key))}")
            if orphaned:
                print(f"ERROR: Orphaned outputs (no matching source): {', '.join(sorted(orphaned, key=natural_sort_key))}")
            return False

        # Verify no empty, unreadable, or whitespace-only output files
        for fp in output_files:
            if os.path.getsize(fp) == 0:
                print(f"ERROR: Empty output file: {os.path.basename(fp)}")
                return False
            text = read_output_text(fp)
            if text is None:
                print(f"ERROR: Unreadable output file: {os.path.basename(fp)}")
                return False
            if not text.strip():
                print(f"ERROR: Blank output file: {os.path.basename(fp)}")
                return False

        # Use source order to determine merge order (via expected output names)
        output_files = [
            os.path.join(temp_dir, f"output_{name}")
            for name in source_basenames
        ]
        print(f"Merging {len(output_files)} translated files (legacy glob)")

        merged_content = ""
        for file_path in output_files:
            content = read_output_text(file_path)
            if content is None:
                print(f"ERROR: Cannot read {os.path.basename(file_path)} — aborting merge")
                return False
            content = trim_chunk_edges(content)
            if not content:
                print(f"ERROR: Blank output {os.path.basename(file_path)} — aborting merge")
                return False
            content = _restore_math_for(temp_dir, file_path, content)
            merged_content += content + "\n\n"

    # Belt-and-braces: whichever merge branch ran, no placeholder may survive
    # into output.md. A leaked token would render literally in the final PDF.
    leftover = sorted({m.group(0) for m in math_guard.TOKEN_RE.finditer(merged_content)})
    if leftover:
        print(f"ERROR: {len(leftover)} math token(s) survived the merge: {leftover[:10]}")
        print("  cause: a sidecar is missing or stale for a chunk that contains tokens.")
        print("  fix: re-run convert.py to regenerate chunks and sidecars.")
        return False

    try:
        with open(output_md, 'w', encoding='utf-8', newline='\n') as f:
            f.write(merged_content)
        file_size = os.path.getsize(output_md)
        print(f"Merged into output.md ({file_size:,} bytes)")
        return True
    except Exception as e:
        print(f"Error saving merged file: {e}")
        return False


# =============================================================================
# Step 5: Convert markdown to HTML
# =============================================================================

# Reader extensions used for every markdown->X pandoc call.
#   tex_math_dollars        : $...$ / $$...$$ become real math (not literal text)
#   tex_math_single_backslash: also accept \(...\) and \[...\]
#   pipe_tables/grid_tables : tables must survive to every output format
#   -markdown_in_html_blocks: the only block-level HTML this pipeline emits is
#     the raw-LaTeX tables, rendered here as finished HTML with MathML inside.
#     Left on, pandoc reads markdown in them, and a literal `*` or `_` in a
#     formula pairs with the next one and splices an `<em>` through the middle
#     of the MathML: CafeQ's table 3 printed `45.6^{}` and lost the asterisk
#     its own caption explains. Nothing in these blocks is markdown, so the
#     parsing has nothing to do but damage.
PANDOC_FROM = ('markdown+smart+east_asian_line_breaks+tex_math_dollars'
               '+tex_math_single_backslash+pipe_tables+grid_tables+raw_html'
               '-markdown_in_html_blocks')

# Scripts that write no space between words, so a wrapped line has none to
# lose. Korean is East Asian to pandoc and to Unicode, and is NOT one of them.
_NO_INTERWORD_SPACE = ('zh', 'ja')


def pandoc_from(lang=None):
    r"""The reader extensions, minus any this language must not have.

    `east_asian_line_breaks` deletes the newline between two East Asian
    characters. That is right for Chinese and Japanese, where a line wrapped
    in the source carries no space to begin with. Korean separates words with
    spaces and pandoc classifies Hangul as East Asian too, so a paragraph
    wrapped across lines in the merged markdown came back with its words run
    together: `가로지르고 있든\n손잡이를` printed as `있든손잡이를`.

    No shipped book has shown it, for one reason: translator sub-agents happen
    to write each paragraph as a single long line. That is luck rather than
    design -- the merged markdown is an ordinary text file, a hand edit or a
    differently-behaved agent can wrap it, and the damage is silent because
    every count still agrees.
    """
    base = (lang or '').split('-')[0].lower()
    if base in _NO_INTERWORD_SPACE:
        return PANDOC_FROM
    return PANDOC_FROM.replace('+east_asian_line_breaks', '')


# =============================================================================
# Bibliography
# =============================================================================

_THEBIB_RE = re.compile(
    r'\\begin\{thebibliography\}.*?\\end\{thebibliography\}', re.DOTALL)
# citeproc renders "Surname, First, and Other. 2024. “Title.” *Venue* 1: 2-3."
# strip_pandoc_divs has already removed the ::: {#refs} wrapper by this point,
# so the shape of the paragraph is all there is to go on.
_CITEPROC_ENTRY_RE = re.compile(
    r'^[A-Z][^\n]{2,60}?\.\s+(?:\d{4}[a-z]?|n\.d\.)\.\s', re.MULTILINE)


def source_has_bib_files(temp_dir):
    """Did the arXiv source ship a .bib? Then citeproc rendered the references.

    arxiv_backend picks citeproc over inlining the .bbl on exactly this test,
    so asking the same question here says whether a reference list already
    exists somewhere in the document.
    """
    root = os.path.join(temp_dir or '', 'arxiv_src')
    if not os.path.isdir(root):
        return False
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            if name.lower().endswith('.bib'):
                return True
    return False


_LIST_EDGE_HEADING_RE = re.compile(r'(?m)^#{1,6} ')
_LIST_EDGE_PROSE_RE = re.compile(r'[가-힣]{4,}')


def _citeproc_block_start(md_text):
    """Index where the trailing run of citeproc reference paragraphs begins.

    The walk back stops at the EDGE of the list -- a heading, or a paragraph
    of body prose -- and not at an entry that happens to carry a blank line
    inside it. Counting blank lines meant one long preprint entry truncated
    the run: of AlphaQ's 52 references the walk kept one, so the `참고문헌`
    heading was inserted between the last two entries, six pages after the
    list actually began, and the contents page pointed the reader there.
    """
    matches = list(_CITEPROC_ENTRY_RE.finditer(md_text))
    if len(matches) < 5:
        return -1
    start = matches[-1].start()
    for m in reversed(matches[:-1]):
        between = md_text[m.start():start]
        if _LIST_EDGE_HEADING_RE.search(between):
            break
        if len(_LIST_EDGE_PROSE_RE.findall(between)) > 2:
            break
        start = m.start()
    # do not swallow a heading that sits directly above the first entry
    head = md_text.rfind('\n#', 0, start)
    if head != -1 and md_text[head:start].count('\n\n') <= 1:
        return -1
    return start


_THEBIB_ENTRY_RE = re.compile(r'\\bibitem\s*(?:\[[^\]]*\])?\s*\{[^{}]*\}')
# A command separated from its argument by a LINE BREAK. A space there is fine;
# a newline is not, and pandoc fails the whole fragment over it.
_BIB_ARG_GAP_RE = re.compile(r'(\\[A-Za-z]+)[ \t]*\r?\n[ \t]*(?=\{)')


def expand_thebibliography(md_text, label, pandoc=None):
    r"""Render a raw `thebibliography` into text. Returns (md_text, entries).

    Keeping the environment as it was meant handing pandoc raw LaTeX on the
    HTML path, and pandoc drops that without a word -- the same silence that
    ate the algorithm floats. CafeQ's 61 references reached output.md and
    then stopped: the book carries 19 in-text citations and no list for them
    to point at, and no check counted a reference.
    """
    m = _THEBIB_RE.search(md_text)
    if not m:
        return md_text, 0
    inner = re.sub(r'\\begin\{thebibliography\}\s*(?:\{[^{}]*\})?', '',
                   m.group(0))
    inner = re.sub(r'\\end\{thebibliography\}', '', inner)
    first = _THEBIB_ENTRY_RE.search(inner)
    if not first:
        return md_text, 0
    # Everything before the first \bibitem is the .bbl's own preamble.
    entries = [e.strip() for e
               in _THEBIB_ENTRY_RE.split(inner[first.start():]) if e.strip()]
    if not entries:
        return md_text, 0
    # `\newblock` only asks for space between the parts of an entry, but
    # pandoc has no reader for it and takes the group that follows as its
    # argument. A title written `{FrameQuant}: Flexible low-bit ...` -- the
    # braces protect the capitals -- then printed as `: Flexible low-bit`,
    # with the name of the method missing.
    entries = [re.sub(r'\\newblock\b\s*', ' ', e).strip() for e in entries]
    # A `.bbl` escapes a literal punctuation mark by wrapping it in math:
    # `QuIP$\#$`. texmath has nothing to do with `\#`, so the dollars reach
    # the page and the reader sees the markup instead of the character.
    entries = [re.sub(r'\$\\([#%&_${}])\$', r'\1', e) for e in entries]
    # And the same character after the conversion has escaped the raw block:
    # `QuIP$\#$` arrives as `Qu{IP}\${\textbackslash}\#\$`, four pieces of
    # markup standing in for one `#`, and all four print.
    entries = [re.sub(r'\\\$\{\\textbackslash\}\\([#%&_$])\\\$', r'\1', e)
               for e in entries]
    # A `.bbl` wraps its lines, so a command and its argument can end up on
    # separate lines: `\href\n  {url} {text}`. A SPACE there converts; a
    # NEWLINE does not, and pandoc fails the fragment it is in. Two of BERT's
    # 56 entries were written that way.
    entries = [_BIB_ARG_GAP_RE.sub(r'\1', e) for e in entries]

    rendered = []
    pandoc = pandoc or resolve_pandoc()
    if pandoc:
        with tempfile.TemporaryDirectory(prefix='tb-bib-') as work:
            out = _latex_fragment_to_markdown('\n\n'.join(entries), pandoc,
                                              work, 'bib.tex')
            if out:
                rendered = [p.strip() for p in out.split('\n\n') if p.strip()]
            if len(rendered) != len(entries):
                # One entry pandoc cannot read fails the WHOLE fragment, and
                # the fallback below then prints all 56 as raw LaTeX -- the
                # reader loses a formatted reference list over one bad line.
                # Convert them one at a time so a bad entry costs only itself.
                rendered = []
                for i, entry in enumerate(entries):
                    one = _latex_fragment_to_markdown(entry, pandoc, work,
                                                      'bib%04d.tex' % i)
                    rendered.append(' '.join((one or entry).split()))
    if not rendered:                       # no pandoc: the text, unformatted
        rendered = [' '.join(e.split()) for e in entries]

    # Number them. `build_bibitem_numbers` numbers the in-text citations 1..N
    # from this same `\bibitem` list in this same order, and the list itself
    # was rendered as bare paragraphs with no labels at all, so every book
    # this pipeline has produced carries citations reading [1] to [9] over a
    # list of nine unlabelled paragraphs. The reader cannot resolve any of
    # them. It reached the English pass-through edition too, which is what
    # says it was never a translation defect; six reading passes found it and
    # no check did, because nothing had ever compared the two.
    #
    # `[n]` and not `n.`: the citations print `[1]` and a multi-key one
    # prints `[1, 3]`, so the list has to answer in the same notation.
    rendered = ['[%d] %s' % (i + 1, text) for i, text in enumerate(rendered)]

    return (md_text[:m.start()] + '\n\n# %s\n\n' % label
            + '\n\n'.join(rendered) + '\n\n' + md_text[m.end():],
            len(entries))


def resolve_bibliography(md_text, temp_dir, lang_cfg=None):
    """One reference list, with a heading. Returns (text, stats)."""
    lang_cfg = lang_cfg or {}
    label = lang_cfg.get('references_label', 'References')
    stats = {'dropped_duplicate': 0, 'heading_added': 0, 'inlined_rendered': 0}

    has_citeproc = _citeproc_block_start(md_text) != -1
    if _THEBIB_RE.search(md_text):
        if source_has_bib_files(temp_dir) and has_citeproc:
            # The source inlined its own .bbl and also shipped the .bib that
            # citeproc read. Both lists are in the document; keep the rendered
            # one, which carries no LaTeX and no \providecommand preamble.
            md_text, n = _THEBIB_RE.subn('', md_text)
            stats['dropped_duplicate'] = n
        else:
            md_text, stats['inlined_rendered'] = expand_thebibliography(
                md_text, label)

    start = _citeproc_block_start(md_text)
    if start != -1:
        before = md_text[:start].rstrip()
        heading = '\n\n# %s\n\n' % label
        md_text = before + heading + md_text[start:]
        stats['heading_added'] = 1
    return md_text, stats


def convert_with_pandoc(md_file, html_file, title, lang_attr, math_mode='mathml'):
    """Convert markdown to HTML using pandoc.

    math_mode='mathml' emits native MathML with no JavaScript and no external
    requests, so equations render offline and survive into EPUB/PDF. KaTeX and
    MathJax modes are deliberately not offered: pandoc points them at a CDN,
    which is dead in an offline reader and inert inside DOCX.
    """
    pandoc = resolve_pandoc()
    if not pandoc:
        return False

    cmd = [
        pandoc, md_file, '-o', html_file,
        '--standalone',
        '--metadata', f'title={title}',
        '--metadata', f'lang={lang_attr}',
        '--from', pandoc_from(lang_attr),
        '--to', 'html5',
        '--wrap=preserve',
    ]
    if math_mode == 'mathml':
        cmd.append('--mathml')

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding='utf-8', errors='replace', check=True
        )
        if result.stderr and result.stderr.strip():
            print(f"pandoc warnings:\n{result.stderr.strip()[:1500]}")
        print(f"Converted with pandoc ({math_mode} math)")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Pandoc conversion failed (rc={e.returncode}): {(e.stderr or '')[:1500]}")
        return False


# A math span: $$...$$ (may span lines) or $...$ (single line, non-empty).
_MATH_SPAN_RE = re.compile(r'(?<!\\)(\$\$.+?\$\$|\$[^$\n]+?\$)', re.DOTALL)


def _protect_math(text):
    """Stash math spans behind sentinels so markdown emphasis rules cannot
    mangle them. LaTeX subscripts (`x_1 ... y_2`) are otherwise eaten by the
    `_italic_` rule, which silently corrupts every formula."""
    stash = []

    def take(m):
        stash.append(m.group(1))
        return f'\x00MATH{len(stash) - 1}\x00'

    return _MATH_SPAN_RE.sub(take, text), stash


def _restore_math_as_tex(html, stash):
    """Re-insert stashed math as marked-up TeX. Tier 1 has no TeX->MathML
    engine, so the formula stays legible and machine-recoverable rather than
    being silently mangled."""
    for i, raw in enumerate(stash):
        span = f'<span class="math tex-fallback">{_html_lib.escape(raw)}</span>'
        html = html.replace(f'\x00MATH{i}\x00', span)
    return html


def convert_with_python_markdown(md_file, html_file, title):
    """Convert markdown to HTML using python-markdown (fallback 1)"""
    if not MARKDOWN_AVAILABLE:
        return False

    try:
        with open(md_file, 'r', encoding='utf-8') as f:
            md_content = f.read()

        md_content, math_stash = _protect_math(md_content)

        # 'codehilite' is dropped: it silently requires Pygments. 'attr_list'
        # and 'md_in_html' keep pandoc-style attributes and raw HTML blocks
        # (e.g. <figure>) intact.
        extensions = ['toc', 'tables', 'fenced_code', 'attr_list',
                      'md_in_html', 'sane_lists', 'nl2br']
        md = markdown.Markdown(extensions=extensions)
        html_content = md.convert(md_content)
        html_content = _restore_math_as_tex(html_content, math_stash)
        if math_stash:
            print(f"WARNING: tier-1 converter used — {len(math_stash)} formula(s) "
                  f"emitted as raw TeX, not rendered math.")

        full_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>{title}</title>
</head>
<body>
{html_content}
</body>
</html>"""

        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(full_html)

        print("Converted with python-markdown (fallback)")
        return True
    except Exception as e:
        print(f"python-markdown conversion failed: {e}")
        return False


def convert_with_basic_regex(md_file, html_file, title):
    """Convert markdown to HTML using basic regex (fallback 2)"""
    try:
        with open(md_file, 'r', encoding='utf-8') as f:
            md_content = f.read()

        # Even in the degraded path, keep math out of reach of the emphasis
        # regexes below — `_` is pervasive in LaTeX subscripts.
        html_content, math_stash = _protect_math(md_content)

        # Headers
        html_content = re.sub(r'^#### (.*?)$', r'<h4>\1</h4>', html_content, flags=re.MULTILINE)
        html_content = re.sub(r'^### (.*?)$', r'<h3>\1</h3>', html_content, flags=re.MULTILINE)
        html_content = re.sub(r'^## (.*?)$', r'<h2>\1</h2>', html_content, flags=re.MULTILINE)
        html_content = re.sub(r'^# (.*?)$', r'<h1>\1</h1>', html_content, flags=re.MULTILINE)

        # Bold and italic
        html_content = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', html_content)
        html_content = re.sub(r'\*(.*?)\*', r'<em>\1</em>', html_content)
        # Narrowed: only underscores that delimit a word, so identifiers like
        # PL_Alpha_Hill and aten::copy_ survive intact.
        html_content = re.sub(r'(?<![\w\\])_([^_\n]+)_(?![\w])', r'<em>\1</em>', html_content)

        # Images — escape alt and src so quotes in alt text don't break the tag
        def _md_img_to_html(m):
            alt = _html_lib.escape(m.group(1), quote=True)
            src = _html_lib.escape(m.group(2), quote=True)
            return f'<img src="{src}" alt="{alt}">'
        html_content = re.sub(r'!\[([^\]]*)\]\(([^)]*)\)', _md_img_to_html, html_content)

        # Links
        html_content = re.sub(r'\[([^\]]*)\]\(([^)]*)\)', r'<a href="\2">\1</a>', html_content)

        # Lists and paragraphs
        lines = html_content.split('\n')
        result_lines = []
        in_list = False

        for line in lines:
            stripped = line.strip()
            if stripped.startswith('- '):
                if not in_list:
                    result_lines.append('<ul>')
                    in_list = 'ul'
                item = stripped[2:]
                result_lines.append(f'<li>{item}</li>')
            elif re.match(r'^\d+\. ', stripped):
                if not in_list:
                    result_lines.append('<ol>')
                    in_list = 'ol'
                item = re.sub(r'^\d+\. ', '', stripped)
                result_lines.append(f'<li>{item}</li>')
            else:
                if in_list:
                    result_lines.append(f'</{in_list}>')
                    in_list = False
                if stripped and not stripped.startswith('<'):
                    result_lines.append(f'<p>{line}</p>')
                else:
                    result_lines.append(line)

        if in_list:
            result_lines.append(f'</{in_list}>')

        html_content = '\n'.join(result_lines)

        # Page separators
        html_content = re.sub(r'<p>---</p>', '<div class="page-separator"></div>', html_content)

        html_content = _restore_math_as_tex(html_content, math_stash)

        full_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>{title}</title>
</head>
<body>
{html_content}
</body>
</html>"""

        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(full_html)

        print("Converted with basic regex (fallback 2)")
        return True
    except Exception as e:
        print(f"Basic regex conversion failed: {e}")
        return False


_TEMPLATE_TOKEN_RE = re.compile(
    r'\$(body|title|title_page|lang|body_font|toc_label'
    r'|page_size|page_margin|print_font_size|print_line_height'
    r'|h1_break_before|h1_page_break_before)\$')


def build_title_page(title, source=''):
    r"""The page a paper opens with, or '' when there is nothing to put on it.

    The book opened on its table of contents: no title, no authors, no
    affiliations. VLA-Adapter names sixteen people in its title block and the
    book credited one of them, in a `<meta>` tag no reader sees.

    Carries no byline of its own on purpose. `apply_template_to_html` already
    puts one after the first `</h1>`, which is now this heading -- a second
    one here printed both, the short metadata form above the full list. The
    names reach it through the `byline` argument instead.

    Returns '' without a title, so a source that never had one does not gain
    a blank leaf.
    """
    if not (title or '').strip():
        return ''
    parts = ['<section class="title-page">',
             '<h1 class="title-page-title">%s</h1>'
             % _html_lib.escape(title.strip())]
    if (source or '').strip():
        parts.append('<p class="title-page-source">%s</p>'
                     % _html_lib.escape(source.strip()))
    parts.append('</section>')
    return '\n'.join(parts)


def apply_template_to_html(html_content, template_file, output_file, title, lang_cfg,
                           author=None, print_cfg=None, title_page='',
                           byline=None):
    """Apply a template to HTML content with language-aware substitutions.

    `author` is the metadata form and goes in the `<meta>` tag. `byline` is
    what the reader sees under the title; it defaults to `author` and is
    given the full list when one is known, because the metadata form is a
    catalogue entry -- "Yihao Wang et al." -- and a title page that credits
    one of sixteen people is not a title page.
    """
    if not template_file or not os.path.exists(template_file):
        print(f"Warning: Template {template_file} not found")
        return False

    try:
        with open(template_file, 'r', encoding='utf-8') as f:
            template_content = f.read()

        # Normalize the body placeholder so one substitution pass handles all
        # template shapes.
        if '$body$' not in template_content:
            if '{{content}}' in template_content:
                template_content = template_content.replace('{{content}}', '$body$')
            elif '</body>' in template_content:
                template_content = template_content.replace('</body>', '$body$\n</body>')
            else:
                template_content = template_content + '$body$'

        values = {
            'body': html_content,
            'title': title,
            'title_page': title_page,
            'lang': lang_cfg['lang_attr'],
            'body_font': lang_cfg['font_family'],
            'toc_label': lang_cfg['toc_label'],
        }
        # Every alternative in _TEMPLATE_TOKEN_RE must have a value here, or a
        # template that happens to use one raises KeyError inside the sub().
        # template.html ignores these; that costs nothing.
        values.update(layout.template_values(print_cfg or layout.get_print_profile()))

        # ONE pass over the TEMPLATE only. Substituted values are never
        # rescanned, so `$...$` math in the body — or a `$` in the title —
        # can never be reinterpreted as a template token.
        full_html = _TEMPLATE_TOKEN_RE.sub(lambda m: values[m.group(1)], template_content)

        # Inject author meta tag into <head> so calibre_html_publish.py can extract it
        if author:
            # escape(): a quote in the author name would otherwise close the
            # attribute early. Callable replacement: a backslash or `\g<1>` in
            # the name would otherwise be read as a regex escape and corrupt
            # (or crash) the substitution.
            author_meta = f'<meta name="author" content="{_html_lib.escape(author, quote=True)}">'
            if '<head>' in full_html or '<head ' in full_html:
                full_html = re.sub(
                    r'(<head[^>]*>)',
                    lambda m: m.group(1) + '\n    ' + author_meta,
                    full_html,
                    count=1,
                    flags=re.IGNORECASE
                )
            # And on the page. The names reached the metadata and stopped
            # there, so all three books opened with a bare title and no byline
            # anywhere -- a paper that does not say who wrote it. The title is
            # the body's first <h1>; the contents page is added after this.
            shown = (byline or author).replace(';', ',')
            byline_html = '<p class="byline">%s</p>' % _html_lib.escape(
                re.sub(r'\s{2,}', ' ', shown).strip())
            # Searched from <body>, not from the top of the file. The old
            # `re.sub(r'</h1>', ..., count=1)` matched the whole document,
            # and a CSS comment in <head> that merely NAMED the tag took the
            # byline: sixteen authors went into the stylesheet, where they
            # rendered as nothing at all and the title page came out bare.
            body_at = re.search(r'<body[^>]*>', full_html, re.IGNORECASE)
            start = body_at.end() if body_at else 0
            heading = re.search(r'</h1>', full_html[start:])
            if heading:
                at = start + heading.end()
                full_html = (full_html[:at] + '\n' + byline_html
                             + full_html[at:])

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(full_html)
        return True
    except Exception as e:
        print(f"Error applying template: {e}")
        return False


_MD_TABLE_DELIM_RE = re.compile(
    r'^\s*\|?(?:\s*:?-{2,}:?\s*\|)+\s*:?-{2,}:?\s*\|?\s*$'
)


def count_md_tables(md_text):
    """Count pipe tables by a delimiter row preceded by a header row."""
    lines = md_text.splitlines()
    total = 0
    for i, line in enumerate(lines):
        if i and _MD_TABLE_DELIM_RE.match(line) and lines[i - 1].count('|') >= 2:
            total += 1
    return total


def check_table_fidelity(md_file, html_text, strict=True):
    """Fail if markdown tables did not become real <table> elements.

    The regex fallback has no table support at all, so it renders every row as
    `<p>| a | b |</p>`. That is invisible in a build log but obvious in the
    PDF, which is exactly the kind of silent degradation this check exists to
    turn into a loud error."""
    md_text = Path(md_file).read_text(encoding='utf-8')
    md_tables = count_md_tables(md_text)
    # Raw LaTeX tables count too. Leaving them out is what let five arXiv
    # result tables disappear while this check printed "OK".
    tex_tables = count_raw_latex_tables(md_text)
    want = md_tables + tex_tables
    if want == 0:
        return True

    got = len(re.findall(r'<table\b', html_text, re.IGNORECASE))
    detail = f"{md_tables} markdown"
    if tex_tables:
        detail += f" + {tex_tables} raw-LaTeX"
    if got >= want:
        print(f"Table check: {got} <table> for {want} table(s) ({detail}) — OK")
        return True

    stray = len(re.findall(r'<p>\s*\|', html_text))
    print(f"ERROR: table fidelity check failed — output.md has {want} "
          f"table(s) ({detail}) but the HTML has only {got} <table> element(s)"
          + (f" ({stray} paragraph(s) start with a literal '|', i.e. tables "
             f"were rendered as plain text)" if stray else ""))
    print("  cause: the markdown->HTML converter does not support tables "
          "(regex fallback), the table syntax in output.md is malformed, or a "
          "raw LaTeX tabular could not be converted (pandoc's markdown reader "
          "DROPS raw LaTeX blocks on the HTML path, it does not warn).")
    return not strict


_MATH_ELEMENT_RE = re.compile(r'<math\b.*?</math>', re.DOTALL)
_EMPHASIS_TAG_RE = re.compile(r'</?(?:em|i|strong|b)\b[^>]*>')


def find_spliced_math(html_text):
    """Formulas with markdown emphasis run through the middle of them.

    Every other check here counts: spans in, spans out. This one is the
    reason that is not enough. The count was right -- 225 formulas asked for,
    225 delivered -- while five of them had an `<em>` opened inside one and
    closed inside another, because a literal `*` in the MathML paired with
    the next `*` further down the table. The reader got `45.6^{}` where the
    paper prints `45.6*`, and no total anywhere disagreed.
    """
    return [m for m in _MATH_ELEMENT_RE.findall(html_text)
            if _EMPHASIS_TAG_RE.search(m)]


# MathML keeps the formula's ORIGINAL TeX in an annotation element. When a
# display nests math inside a text argument — Maynard's
# `\text{for infinitely many $n$ all of $n+h_1$, ...}` — that annotation
# contains real `$...$` pairs, and a leftover count taken over the whole page
# reads them back as unrendered math. Maynard reported four while the formula
# was on the page, correctly typeset, every glyph present.
#
# The cost is not the noise. A genuine leak produces the same number and looks
# identical, so the check could no longer tell "a formula printed as source"
# from "a formula rendered and described". Excluding the annotation restores
# the distinction; nothing that renders is counted.
_MATHML_ANNOTATION_RE = re.compile(r'<annotation\b[^>]*>.*?</annotation>',
                                   re.DOTALL)


def check_math_fidelity(md_file, html_text):
    """Warn/fail if math in output.md did not render in the HTML."""
    md_text = Path(md_file).read_text(encoding='utf-8')
    want = len(_MATH_SPAN_RE.findall(md_text))
    if want == 0:
        print("Math check: no $...$ math in output.md — skipped")
        return True

    got = (len(re.findall(r'<math\b', html_text))
           + len(re.findall(r'class="[^"]*\bmath\b', html_text)))
    leftover = len(_MATH_SPAN_RE.findall(
        _MATHML_ANNOTATION_RE.sub(' ', html_text)))
    print(f"Math check: {want} TeX span(s) in md -> {got} rendered, "
          f"{leftover} raw $ span(s) remaining")
    if got == 0:
        print("ERROR: math present in output.md but nothing rendered in the HTML.")
        print("  cause: the converter dropped math, or +tex_math_dollars is missing.")
        return False
    if leftover:
        print(f"WARNING: {leftover} TeX span(s) reached the HTML unrendered")

    spliced = find_spliced_math(html_text)
    if spliced:
        print(f"ERROR: {len(spliced)} formula(s) have markdown emphasis "
              f"spliced through them")
        for blob in spliced[:3]:
            ann = re.search(r'<annotation[^>]*>(.*?)</annotation>', blob,
                            re.DOTALL)
            print("  %s" % ' '.join((ann.group(1) if ann else blob).split())[:90])
        print("  cause: markdown was parsed inside the raw HTML tables, so a "
              "literal * or _ in one formula paired with the next one and the "
              "character it consumed is gone from the page.")
        return False
    return True


def check_image_refs_resolve(temp_dir):
    """Verify every image reference in output.md points at a real file."""
    md_path = os.path.join(temp_dir, 'output.md')
    if not os.path.exists(md_path):
        return True
    md = Path(md_path).read_text(encoding='utf-8')
    html_srcs, md_srcs, _ = _scan_image_refs(md)
    refs = set(html_srcs) | set(md_srcs)

    missing, external = [], []
    for ref in sorted(refs):
        if ref.startswith(('http://', 'https://', 'data:', '//')):
            external.append(ref)
            continue
        clean = ref.split('#')[0].split('?')[0]
        if not os.path.isfile(os.path.normpath(os.path.join(temp_dir, clean))):
            missing.append(ref)

    print(f"Image check: {len(refs)} unique ref(s), {len(missing)} missing, "
          f"{len(external)} external")
    if external:
        print(f"  WARNING: external image refs will not render offline: {external[:5]}")
    if missing:
        print("ERROR: image references in output.md do not resolve under the temp dir:")
        for m in missing[:20]:
            print(f"  - {m}")
        print("  fix: re-run convert.py to re-extract images, or correct the paths "
              "in output.md / the offending output_chunk*.md")
        return False
    return True


_TABLE_EL_RE = re.compile(r'<table(?:\s[^>]*)?>.*?</table>', re.DOTALL)
_TABULAR_IN_FLOAT_RE = re.compile(
    r'\\begin\{(tabular\*?|tabularx|longtable|array)\}.*?\\end\{\1\}',
    re.DOTALL)


def table_structures(temp_dir):
    """[{'header': n, 'rules': {...}}] per table, in the order they appear.

    The rules a paper draws live in flat.tex and nowhere else. Whether a
    given table reaches the page as raw LaTeX or as a pandoc table is decided
    by what pandoc happened to be able to convert -- half of AlphaQ's tables
    changed sides once the ingest stopped fighting it -- and a converted one
    arrives as pipe syntax, which carries no rule at all. Reading the
    structure from the source and applying it by table ORDER covers both, and
    the order is the same one the caption numbering uses, which source_probe
    already checks against the original PDF.
    """
    flat = os.path.join(temp_dir or '', 'flat.tex')
    if not temp_dir or not os.path.exists(flat):
        return []
    try:
        with open(flat, 'r', encoding='utf-8', errors='replace') as fh:
            tex = strip_tex_comments(fh.read())
    except OSError:
        return []
    out = []
    for unit in float_units(tex):
        if unit['kind'] != 'table' or unit['number'] is None:
            continue
        found = _TABULAR_IN_FLOAT_RE.search(tex, unit['start'], unit['stop'])
        if not found:
            out.append({'header': 0, 'rules': {}})
            continue
        tab = found.group(0)
        out.append({'header': header_row_count(tab),
                    'rules': body_rule_rows(tab)})
    return out


def apply_table_structure(html, temp_dir):
    """Give every table its header and its group rules. (html, count)."""
    plans = table_structures(temp_dir)
    if not plans:
        return html, 0
    # Plans are matched to tables BY POSITION, which is only meaningful while
    # both counts agree. If one table failed to render, every table after it
    # would quietly receive the previous one's header depth and rule rows --
    # a wrong answer that looks exactly like a right one.
    found = len(_TABLE_EL_RE.findall(html))
    if found != len(plans):
        sys.stderr.write(
            'warning: %d table(s) in the source, %d in the HTML; header rows '
            'and group rules are matched by position, so this book needs a '
            'look before its tables are trusted\n' % (len(plans), found))
    index, applied = [0], [0]

    def fix(m):
        table = m.group(0)
        i = index[0]
        index[0] += 1
        if i >= len(plans):
            return table
        plan = plans[i]
        before = table
        if plan['header']:
            table = _promote_html_header(table, plan['header'])
        if plan['rules']:
            table = _mark_html_rules(table, plan['rules'])
        if table != before:
            applied[0] += 1
        return table

    return _TABLE_EL_RE.sub(fix, html), applied[0]


def _promote_html_header(table, wanted):
    if '<thead' in table:
        return table
    body = _TBODY_RE.search(table)
    if not body:
        return table
    rows = _TR_RE.findall(body.group(1))
    if not 0 < wanted < len(rows):
        return table
    head = '\n'.join(re.sub(r'<(/?)td\b', r'<\1th', r) for r in rows[:wanted])
    rest = '\n'.join(rows[wanted:])
    return (table[:body.start()]
            + '<thead>\n%s\n</thead>\n<tbody>\n%s\n</tbody>' % (head, rest)
            + table[body.end():])


def _mark_html_rules(table, rules):
    body = _TBODY_RE.search(table)
    if not body:
        return table
    rows = _TR_RE.findall(body.group(1))
    out = []
    for i, row in enumerate(rows):
        kind = rules.get(i)
        if kind and 'rule-above' not in row:
            css = 'rule-above' if kind == 'hard' else 'rule-above-soft'
            row = re.sub(r'<tr\b', '<tr class="%s"' % css, row, count=1)
        out.append(row)
    return (table[:body.start()] + '<tbody>\n' + '\n'.join(out) + '\n</tbody>'
            + table[body.end():])


_SUMMARY_ROW_RE = re.compile(
    r'^\s*(?:<[^>]+>|\s)*(?:평균|합계|전체|총계|平均|合计|合計|总计|總計'
      r'|全体|全體|Average|Avg\.?|Total|Mean'
    r'|Overall)\b', re.IGNORECASE)
_CELL_ONE_RE = re.compile(r'<t[hd][^>]*>(.*?)</t[hd]>', re.DOTALL)


def rule_off_summary_rows(html):
    """Rule off the Average/Total block at the foot of a long table.

    A paper ends a long results table with summary rows and separates them
    with a `\\midrule`. Tables pandoc could convert take the markdown path,
    where pipe syntax has no way to carry a rule, so the boundary is simply
    gone -- CafeQ's twenty-row per-task table ran its four averages straight
    on from its sixteen benchmarks.

    Narrow on purpose: only a table that has no group rule already, only a
    summary row in the last third, only the first such row. Measured across
    three papers it fires once, exactly where the source has its rule.
    """
    def fix(m):
        table = m.group(0)
        if 'rule-above' in table:
            return table
        body = _TBODY_RE.search(table)
        if not body:
            return table
        rows = _TR_RE.findall(body.group(1))
        if len(rows) < 6:
            return table
        for i, row in enumerate(rows):
            if i < len(rows) * 2 / 3:
                continue
            cell = _CELL_ONE_RE.search(row)
            if not cell or not _SUMMARY_ROW_RE.match(cell.group(1)):
                continue
            rows[i] = re.sub(r'<tr\b', '<tr class="rule-above"', row, count=1)
            inner = '\n'.join(rows)
            return (table[:body.start()] + '<tbody>\n' + inner + '\n</tbody>'
                    + table[body.end():])
        return table

    return _TABLE_EL_RE.sub(fix, html)


def finish_table_rules(html_file, temp_dir):
    """Give every table the rules the paper drew, whichever path it took.

    Source first, guess second: a table whose structure is still readable in
    flat.tex gets exactly that, and only one with nothing left to read falls
    through to the summary-row heuristic.
    """
    try:
        with open(html_file, 'r', encoding='utf-8') as fh:
            content = fh.read()
    except OSError as exc:
        print(f"Error reading HTML for table rules: {exc}")
        return
    content, applied = apply_table_structure(content, temp_dir)
    content = rule_off_summary_rows(content)
    try:
        with open(html_file, 'w', encoding='utf-8') as fh:
            fh.write(content)
    except OSError as exc:
        print(f"Error writing table rules: {exc}")
        return
    if applied:
        print(f"Tables: {applied} given the header and group rules the source "
              f"draws")



# Elements whose text must never be rewritten: markup that is not prose, and
# the captions themselves -- "그림 1 (Fig. 1)" inside a figcaption would
# otherwise become a link to the figure it already labels.
_XREF_SKIP = frozenset((
    'style', 'script', 'math', 'code', 'pre', 'a', 'figcaption', 'caption',
    'head', 'title', 'nav', 'textarea',
))
_XREF_TAG_RE = re.compile(r'<!--.*?-->|<(/?)([a-zA-Z][\w:-]*)([^>]*)>', re.DOTALL)
_FIGURE_BLOCK_RE = re.compile(r'<figure\b[^>]*>.*?</figure>', re.DOTALL)
# `(\d+)` alone cannot see a section-scoped number, and the failure is silent
# in the K80 way: the anchor is simply never created, "식 (2.2)" links to an id
# nothing carries, and every cross-reference in the book points at nothing
# without one error or warning. Dots are safe in an id — only `href="#..."`
# selects these, never CSS or JS.
_MATH_EQNO_RE = re.compile(
    r'<math\b(?![^>]*\bid=)([^>]*\bdata-eqno="\((\d+(?:\.\d+)*)\)")')
_HAS_ID_RE = re.compile(r'\bid\s*=')
# An author-year citation: opens on a capital, closes on a year. Bracketed
# citations are deliberately not matched -- across these three books the
# pattern found two, and both were ordinary prose.
_CITE_TEXT_RE = re.compile(r'\((?=[A-Z])[^()]{2,200}?(?:19|20)\d{2}[a-z]?\)')


def _walk_text_nodes(html, transform):
    """Apply `transform` to prose only, never to markup or to a caption."""
    out, pos, open_skips = [], 0, {}

    def prose():
        return not any(open_skips.values())

    for match in _XREF_TAG_RE.finditer(html):
        chunk = html[pos:match.start()]
        if chunk:
            out.append(transform(chunk) if prose() else chunk)
        out.append(match.group(0))
        pos = match.end()
        name = (match.group(2) or '').lower()
        if name in _XREF_SKIP:
            if match.group(1):
                open_skips[name] = max(0, open_skips.get(name, 0) - 1)
            elif not (match.group(3) or '').rstrip().endswith('/'):
                open_skips[name] = open_skips.get(name, 0) + 1
    tail = html[pos:]
    if tail:
        out.append(transform(tail) if prose() else tail)
    return ''.join(out)


def _add_id(tag_text, anchor):
    """Put an id on an opening tag that has none."""
    if _HAS_ID_RE.search(tag_text):
        return tag_text
    return tag_text[:tag_text.index('>')].rstrip() \
        + ' id="%s"' % anchor + tag_text[tag_text.index('>'):]


_EM_RE = re.compile(r'(?s)<(em|i)((?:\s[^>]*)?)>(.*?)</\1>')
# Hangul, kana and Han. None of the three has a real italic in the faces this
# pipeline can rely on, and Chromium answers a request for one by synthesising
# an oblique -- which for Chinese it then emits as a Type3 object, one per
# glyph. Was Hangul only, and Chinese emphasis went on producing Type3 long
# after the Korean case was solved.
_CJK_TEXT_RE = re.compile(r'[가-힣぀-ヿ一-鿿]')


def mark_cjk_emphasis(html):
    r"""Tag emphasis that actually contains CJK. Returns (html, marked).

    CJK has no italic, so the print sheet renders such emphasis bold instead
    of letting Chromium synthesise an oblique. That rule was written as
    `:lang(ko) em` -- and the root element is `lang="ko"`, so it matched
    EVERY <em> in the book. `\textit{16.67}` and `\textit{Wiki2}` printed
    bold, inside tables whose caption says the best result is the bold one:
    ten of SINQ's tables showed their FP16 baseline row as the winner. Which
    is why this looks at what the element CONTAINS and never at the document
    language.
    """
    marked = [0]

    def sub(m):
        tag, attrs, body = m.group(1), m.group(2), m.group(3)
        text = re.sub(r'<[^>]+>', '', body)
        if not _CJK_TEXT_RE.search(text):
            return m.group(0)
        marked[0] += 1
        if re.search(r'\bclass="', attrs):
            attrs = re.sub(r'\bclass="([^"]*)"', r'class="\1 cjk"', attrs, 1)
        else:
            attrs += ' class="cjk"'
        return '<%s%s>%s</%s>' % (tag, attrs, body, tag)

    return _EM_RE.sub(sub, html), marked[0]


def anchor_reference_targets(html, lang_cfg=None):
    """Give each figure, table and numbered equation an id. (html, targets)."""
    lang_cfg = lang_cfg or {}
    fig_label = lang_cfg.get('figure_label', 'Figure')
    tab_label = lang_cfg.get('table_label', 'Table')
    targets = set()

    def number_in(block, label, opener):
        # A window after the opening tag, NOT the whole element: one AlphaQ
        # caption is 24 KB of inline MathML, and requiring the closing tag
        # made three figures match nothing at all. The label is always at the
        # very front of a caption.
        start = re.search(r'<%s\b[^>]*>' % opener, block)
        if not start:
            return None
        window = re.sub(r'<[^>]+>', ' ', block[start.end():start.end() + 400])
        hit = re.search(re.escape(label) + r'\s*(\d+)', window)
        return hit.group(1) if hit else None

    def anchored(block, anchor, inner):
        """Put `anchor` on the element, or on its caption if it has an id.

        A float that carried a `\\label{}` in the source arrives with that
        label AS its id, and an element can hold only one. `_add_id` then
        returns the tag untouched, no `tab-N` is created, and every reference
        rewritten to `#tab-N` points at nothing — a dead in-page link, which
        neither errors nor prints. Six of CafeQ's eight tables were in that
        state in both builds. The caption is inside the element and is where
        a reader following the link wants to land anyway.
        """
        targets.add(anchor)
        head = block[:block.index('>') + 1]
        rest = block[block.index('>') + 1:]
        if not _HAS_ID_RE.search(head):
            return _add_id(head, anchor) + rest
        cap = re.search(r'<%s\b[^>]*>' % inner, rest)
        if cap and not _HAS_ID_RE.search(cap.group(0)):
            return head + rest[:cap.start()] + _add_id(cap.group(0), anchor) \
                + rest[cap.end():]
        # Both already spoken for: keep the label id and let the reference
        # resolve to it, rather than inventing a target that is not there.
        existing = re.search(r'\bid="([^"]+)"', head)
        if existing:
            targets.discard(anchor)
            targets.add(existing.group(1))
        return block

    def fig_sub(match):
        block = match.group(0)
        number = number_in(block, fig_label, 'figcaption')
        if number is None:
            return block
        return anchored(block, 'fig-%s' % number, 'figcaption')

    def tab_sub(match):
        block = match.group(0)
        number = number_in(block, tab_label, 'caption')
        if number is None:
            return block
        return anchored(block, 'tab-%s' % number, 'caption')

    def eq_sub(match):
        targets.add('eq-%s' % match.group(2))
        return '<math id="eq-%s"%s' % (match.group(2), match.group(1))

    html = _FIGURE_BLOCK_RE.sub(fig_sub, html)
    html = _TABLE_EL_RE.sub(tab_sub, html)
    html = _MATH_EQNO_RE.sub(eq_sub, html)
    return html, targets


def link_cross_references(html, lang_cfg=None):
    """Colour every reference; link the ones whose target is unambiguous.

    Takes and returns the body HTML rather than a file, because it has to run
    AFTER the equations are numbered, and by then the body is a string on its
    way into both templates.
    """
    lang_cfg = lang_cfg or {}
    html, targets = anchor_reference_targets(html, lang_cfg)

    fig = re.escape(lang_cfg.get('figure_label', 'Figure'))
    tab = re.escape(lang_cfg.get('table_label', 'Table'))
    eqn = re.escape(lang_cfg.get('equation_label', 'Equation'))
    app = re.escape(lang_cfg.get('appendix_label', 'Appendix'))
    stats = {'linked': 0, 'coloured': 0}

    linkable = [
        # Dotted, for the same reason as _MATH_EQNO_RE above: a paper that
        # numbers per section prints `그림 3.1`, and matching only `3` would
        # link the reference to an anchor that does not exist.
        (re.compile(fig + r'\s*(\d+(?:\.\d+)*)'), 'fig'),
        (re.compile(tab + r'\s*(\d+(?:\.\d+)*)'), 'tab'),
        (re.compile(eqn + r'\s*\((\d+(?:\.\d+)*)\)'), 'eq'),
    ]
    plain = [
        re.compile(app + r'\s*[A-Z](?:\.\d+)*'),
        _CITE_TEXT_RE,
    ]

    def link_sub(prefix):
        def sub(match):
            anchor = '%s-%s' % (prefix, match.group(1))
            if anchor not in targets:
                return match.group(0)
            stats['linked'] += 1
            return '<a class="xref" href="#%s">%s</a>' % (anchor, match.group(0))
        return sub

    def colour_sub(match):
        stats['coloured'] += 1
        return '<span class="xref">%s</span>' % match.group(0)

    def transform(text):
        if '<' in text or '>' in text:
            return text                # never rewrite a fragment of markup
        for pattern in plain:
            text = pattern.sub(colour_sub, text)
        for pattern, prefix in linkable:
            text = pattern.sub(link_sub(prefix), text)
        return text

    return _walk_text_nodes(html, transform), stats

def process_html_separators(html_file):
    """Process page separators in HTML"""
    try:
        with open(html_file, 'r', encoding='utf-8') as f:
            content = f.read()

        content = re.sub(r'<hr\s*/?>', '<div class="page-separator"></div>', content)
        content = re.sub(r'<p>\s*---\s*</p>', '<div class="page-separator"></div>', content)

        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(content)
    except Exception as e:
        print(f"Error processing separators: {e}")


_CAPTION_BODY_RE = re.compile(r'\\caption\s*(?:\[[^\]]*\])?\s*\{')


def source_captions(temp_dir):
    r"""Every `\caption{}` body in `flat.tex`, whitespace collapsed.

    `flat.tex` is the flattened LaTeX the whole book was built from, and it is
    the one file the table agents never touch: the sidecars they edit are
    copies. So it is the only pristine record of what a caption said before
    anybody translated it, which is what makes a caption still identical to
    its source detectable in ANY target language, not just the ones written
    in another script.
    """
    path = os.path.join(temp_dir or '', 'flat.tex')
    if not temp_dir or not os.path.isfile(path):
        return set()
    try:
        with open(path, encoding='utf-8', errors='replace') as handle:
            text = handle.read()
    except (IOError, OSError):
        return set()
    out = set()
    for match in _CAPTION_BODY_RE.finditer(text):
        start = match.end() - 1
        depth, i = 1, start + 1
        while i < len(text) and depth:
            depth += (text[i] == '{') - (text[i] == '}')
            i += 1
        body = ' '.join(text[start + 1:i - 1].split())
        if len(body) >= 12:
            out.add(body)
    return out


_CAPTION_WORD_RE = re.compile(r'[^\W\d_]+', re.UNICODE)
_CAPTION_COMMENT_RE = re.compile(r'(?<!\\)%.*')
_CAPTION_KEYED_RE = re.compile(
    r'\\(?:cite[a-z]*|label|ref|eqref|nameref)\s*\{[^{}]*\}')
_CAPTION_MATH_RE = re.compile(r'\$[^$]*\$')
_CAPTION_COMMAND_RE = re.compile(r'\\[A-Za-z]+')

# Measured over 73 correctly translated captions from six papers and eight
# books: the longest run any of them shares with its source is THREE, and the
# shortest run in a caption nobody translated is SIX. The threshold sits in
# that gap. Raising it costs short untranslated fragments; lowering it below
# four would have fired on VLA-Adapter's model-name captions.
_UNTRANSLATED_RUN = 4


def caption_prose(text):
    r"""A caption with its LaTeX removed, so only words a reader sees remain.

    Every part taken out here is identical in the source and in a correct
    translation, by design, and each one was measured making a correctly
    translated caption look untranslated:

      * `% ...` comments. SINQ's captions keep the paper's own commented-out
        English wording below the Korean, and the reader never sees it. That
        alone scored a run of 28.
      * `\citep{OpenVLA-2024}`, `\label{}`, `\ref{}`: the key must not change.
      * `$...$` maths.
      * command names. `\textbf`, `\texttt`, `\mbox` are structure, not words.
    """
    text = _CAPTION_COMMENT_RE.sub(' ', text)
    text = _CAPTION_KEYED_RE.sub(' ', text)
    text = _CAPTION_MATH_RE.sub(' ', text)
    text = _CAPTION_COMMAND_RE.sub(' ', text)
    return text.replace('{', ' ').replace('}', ' ')


def caption_words(text):
    """Words of the caption's prose, original case kept: capitalisation is
    what separates a model name from a function word."""
    return _CAPTION_WORD_RE.findall(caption_prose(text))


def _is_prose_word(token):
    r"""Lowercase and alphabetic: the shape a function word has.

    What a correct translation shares with its source is names -- OpenVLA,
    DeepSeek-V2-Lite, Qwen1.5-MoE, CALVIN, LIBERO-Long -- and every one of
    them is capitalised or carries a digit. Untranslated prose brings
    lowercase words along and cannot avoid them. Frequency was tried first
    and is worse: the commonest short words of an ML paper include MoE, so a
    run of model names passes a frequency test.
    """
    return len(token) >= 2 and token.isalpha() and token.islower()


def longest_source_run(caption, originals):
    r"""The longest run of PROSE words this caption shares with its source.

    A translator borrows single words from the source: an acronym, a dataset
    name, a cognate. Text nobody translated arrives as a contiguous run. The
    length of the longest run tells the two apart in any target language,
    because the run is made of source words whatever the target is written
    in. A run of names does not count, or a Korean caption naming four models
    in a row would be reported as untranslated.
    """
    have = caption_words(caption)
    if not have:
        return 0
    best = 0
    for original in originals:
        want = [w.lower() for w in caption_words(original)]
        row = [0] * (len(want) + 1)
        for i in range(1, len(have) + 1):
            prev = 0
            for j in range(1, len(want) + 1):
                keep = row[j]
                row[j] = prev + 1 if have[i - 1].lower() == want[j - 1] else 0
                if row[j] > best and any(_is_prose_word(w)
                                         for w in have[i - row[j]:i]):
                    best = row[j]
                prev = keep
    return best


def translation_is_passthrough(temp_dir):
    r"""Did this run copy its chunks through instead of translating them?

    An English edition of an English paper is the pipeline's honest answer
    when there is nothing to translate, and its captions are identical to
    `flat.tex` because that is CORRECT, not because a step was skipped. No
    caption check can tell those apart, so it must not try.

    Asking `lang == 'en'` would be the wrong question twice over: it assumes
    every source paper is English, so a French paper rendered into English
    would silently lose its caption check, and an English paper rendered into
    English is recognisable without guessing at either language. Ask the
    artefact instead. If the translated chunks are the source chunks, nothing
    was translated anywhere, and the captions are not evidence of anything.
    """
    if not temp_dir or not os.path.isdir(temp_dir):
        return False
    names = sorted(n for n in os.listdir(temp_dir)
                   if re.match(r'^chunk\d+\.md$', n))
    checked = 0
    for name in names:
        output = os.path.join(temp_dir, 'output_' + name)
        if not os.path.isfile(output):
            continue
        try:
            with open(os.path.join(temp_dir, name), encoding='utf-8',
                      errors='replace') as fh:
                source = fh.read()
            with open(output, encoding='utf-8', errors='replace') as fh:
                translated = fh.read()
        except (IOError, OSError):
            return False
        if ' '.join(source.split()) != ' '.join(translated.split()):
            return False
        checked += 1
        if checked >= 3:
            break
    return checked > 0


def untranslated_captions(md_text, lang, temp_dir=None):
    r"""Table captions still in the source language. [] when unmeasurable.

    Step 4.6 of SKILL.md translates the words inside table floats, because a
    float is protected behind a `⟦T####⟧` placeholder and no translator ever
    sees its `\caption{}`. That step is prose, and prose gets skipped: it was
    skipped for three editions of one paper in a single session, twice after
    being raised.

    Nothing noticed, and the step's own text says why -- the book comes out
    with its tables in the source language and EVERY existing check passes,
    because they count tables, images and values and those are all correct.
    A green run actively confirms the wrong conclusion.

    So the build asks the artefact instead of trusting that the step ran,
    three ways, because no one of them covers every way the step can be half
    done:

      * the caption is not in the target's script at all. Decisive for ko,
        ja and zh, and blind to fr, de and es.
      * the caption is still word for word what `flat.tex` says. Works in any
        target language, and is the only thing that catches a caption of two
        or three words nobody touched.
      * the caption carries a run of four or more consecutive source words.
        This is what catches a caption translated HALFWAY, which the other
        two both wave through: one target-script character satisfies the
        first, and a half-translated caption is not identical, so it
        satisfies the second.

    A run that copied its chunks through instead of translating them, which
    is the honest rendering of an English paper into English, cannot be
    judged by the last two: a caption identical to the source is correct
    there and indistinguishable from a skipped step. That is recognised from
    the chunks rather than from the language name (K68).
    """
    base = (lang or '').split('-')[0]
    try:
        import verify_chunk
        ranges = verify_chunk._SCRIPT_RANGES.get(base)
    except Exception:                                     # noqa: BLE001
        ranges = None
    # A run that copied its chunks through translated nothing anywhere, so a
    # caption that is not in the target's script is not evidence that step
    # 4.6 was skipped: there was no step 4.6 to skip. The abstention was
    # first applied only to `originals`, which left the SCRIPT test running,
    # and that broke the dry run of SKILL.md 2.5 -- a build with nothing
    # translated is exactly what that step is for, and the gate refused it
    # for every paper holding a table. Found by putting a new paper through
    # the pipeline, not by any check.
    if translation_is_passthrough(temp_dir):
        return []
    originals = source_captions(temp_dir)
    if not ranges and not originals:
        return []

    out = []
    for table in find_raw_latex_tables(md_text):
        caption = (table.get('caption') or '').strip()
        # A very short caption is a label, not prose, and says nothing about
        # whether anybody translated it.
        if len(caption) < 12:
            continue
        flat = ' '.join(caption.split())
        wrong_script = ranges and not any(
            verify_chunk._in_target_script(ch, ranges) for ch in caption)
        half_done = (originals
                     and longest_source_run(caption, originals)
                     >= _UNTRANSLATED_RUN)
        if wrong_script or flat in originals or half_done:
            out.append(flat[:70])
    return out


def untranslated_table_words(md_text, lang, temp_dir=None):
    r"""What step 4.6 left in English BELOW the caption. [] when unmeasurable.

    The caption gate above stopped the build and the header shipped. Step
    4.6 asks for three more things -- column headers, rotated row-group
    labels, and the prose under `\begin{tablenotes}` -- and nothing checked
    any of them, so a book could pass every check with `Method` and
    `Params` across the top of its results table. Two of the five papers on
    this machine shipped exactly that.

    A header cell is one to three words, so `longest_source_run` cannot see
    it: no cell holds a run of four. Headers are matched against a closed
    vocabulary instead (`table_language.HEADER_WORDS`), and notes are prose
    and go through the script test.

    Two abstentions, both about asking a question the artefact can answer:

      * an English target. The vocabulary is English, so a header still in
        English is only evidence of a skipped step when the book was not
        meant to be English. Nothing else here can tell those apart.
      * a run that copied its chunks through, which is the honest rendering
        of an English paper into English and is recognised from the chunks
        rather than the language name (K68), exactly as captions are.

    Known incompleteness, stated rather than hidden: the vocabulary is
    English, so a German paper whose headers stay German is not caught. The
    corpus is 24 papers and all of them are written in English.
    """
    base = (lang or '').split('-')[0]
    if base == 'en' or translation_is_passthrough(temp_dir):
        return []
    try:
        import verify_chunk
        ranges = verify_chunk._SCRIPT_RANGES.get(base)
    except Exception:                                     # noqa: BLE001
        ranges = None

    out = []
    for table in find_raw_latex_tables(md_text):
        for cell in table_language.untranslated_header_cells(
                table.get('bare') or ''):
            out.append('header cell "%s"' % cell)
        note = ' '.join((table.get('notes') or '').split())
        # Only the script test applies to a note: `source_captions` holds
        # captions, so a run measured against it would be measuring the
        # wrong corpus, and saying nothing is better than a number that
        # answers a different question.
        if len(note) >= 12 and ranges and not any(
                verify_chunk._in_target_script(ch, ranges) for ch in note):
            out.append('table note "%s"' % note[:60])
    return out


_ATX_HEADING_LINE_RE = re.compile(r'^#{1,6}\s+\S')


def separate_headings(md_text):
    r"""A heading needs a blank line in front of it or it is not a heading.

    pandoc reads `### Methods` glued to the line above as a lazy
    continuation of that paragraph, so the `###` prints as literal text and
    the section never exists. Silent, and invisible in the markdown: the
    file looks perfectly structured.

    It bites whenever the source had no blank lines to begin with, which is
    every paper read out of a PDF. A translator told to mark the headings
    marks them on the line where the title sits, and the line above is the
    end of the previous paragraph. Measured on the paper that found this:
    19 headings in `output.md`, 18 of them glued, 4 surviving into the HTML,
    a 3-entry table of contents and ONE PDF bookmark for 22 pages.

    Inserting the blank line changes no words and cannot merge two blocks,
    so it is safe to run over any markdown.
    """
    lines = (md_text or '').split('\n')
    out = []
    for line in lines:
        if _ATX_HEADING_LINE_RE.match(line) and out and out[-1].strip():
            out.append('')
        out.append(line)
    return '\n'.join(out)


def convert_md_to_html(temp_dir, title, lang_cfg, author=None,
                       allow_degraded=False, math_mode='mathml', force=False,
                       print_cfg=None):
    """Convert output.md to HTML with templates"""
    print("=== Converting markdown to HTML ===")

    md_file = os.path.join(temp_dir, 'output.md')
    if not os.path.exists(md_file):
        print("Error: output.md not found.")
        return False

    with open(md_file, encoding='utf-8', errors='replace') as fh:
        _merged = fh.read()
    stale_captions = untranslated_captions(_merged,
                                           lang_cfg.get('lang_attr', ''),
                                           temp_dir)
    if stale_captions:
        print("ERROR: %d table caption(s) are still in the source language."
              % len(stale_captions))
        for line in stale_captions[:4]:
            print("  - %s" % line)
        print("  A table float sits behind a placeholder, so no translator "
              "saw its \\caption{}. Every other check passes: the tables, "
              "the values and the counts are all correct.")
        print("  SKILL.md step 4.6 translates them. Start with:")
        print("      python tests/format_probe.py \"%s\" --lang %s"
              % (temp_dir, (lang_cfg.get('lang_attr') or '').split('-')[0]))
        raise SystemExit(1)

    # The caption is the first row of a table, not the whole of it. This gate
    # is separate from the one above because it fires on books whose captions
    # ARE translated: step 4.6 has four parts and stopping after the first is
    # the common way to half-do it.
    stale_words = untranslated_table_words(_merged,
                                           lang_cfg.get('lang_attr', ''),
                                           temp_dir)
    if stale_words:
        print("ERROR: %d table header cell(s) or note(s) are still in the "
              "source language." % len(stale_words))
        for line in stale_words[:6]:
            print("  - %s" % line)
        print("  The captions passed, so step 4.6 was started and stopped "
              "after them. Column headers, rotated row labels and the prose "
              "under a table are the rest of it.")
        print("  Edit through scripts/sidecar_edit.py, never a script of "
              "your own; SKILL.md step 4.6 says why.")
        raise SystemExit(1)

    book_doc_file = os.path.join(temp_dir, 'book_doc.html')

    # Skip HTML generation if book_doc.html exists and is newer than output.md
    if os.path.exists(book_doc_file) and not force:
        if os.path.getmtime(book_doc_file) > os.path.getmtime(md_file):
            if _check_generated_html_sanity(book_doc_file):
                print("Skipping HTML generation - book_doc.html is up to date")
                return True
            print("Stale book_doc.html failed image sanity — regenerating")
            os.remove(book_doc_file)
        else:
            print("Re-generating HTML - output.md is newer")

    temp_html_file = os.path.join(temp_dir, 'output.html')

    # Raw LaTeX tables must become HTML before ANY markdown->HTML converter
    # sees them: pandoc's markdown reader parses them as raw LaTeX blocks, and
    # a raw block only survives into its own output format, so on the HTML path
    # they vanish without a warning. output.md itself is left untouched -- it
    # stays the faithful merged translation -- and the converters read the
    # expanded copy instead.
    source_md = md_file
    md_text = Path(md_file).read_text(encoding='utf-8')

    # Citations and cross-references first: they are plain-text substitutions
    # and must happen before any table becomes HTML.
    md_text, unwrapped = unwrap_prose_environments(md_text)
    if unwrapped:
        print(f"Prose environments: {unwrapped} rewritten as markdown; pandoc "
              f"takes each as one raw block and drops it whole")

    md_text, cells = unwrap_table_cell_wrappers(md_text)
    if cells:
        print("Tables: %d \\makecell/\\thead cell(s) unwrapped; pandoc drops "
              "the command WITH its text and leaves the cell empty" % cells)

    md_text, tabbed = unwrap_tabbing(
        md_text, read_one_argument_macros(temp_dir))
    if tabbed:
        print("Pseudocode: %d tabbing environment(s) rewritten as code blocks; "
              "pandoc has no reader for tabbing and drops it silently" % tabbed)

    md_text, leftover_stats = normalize_latex_leftovers(md_text)
    if any(leftover_stats.values()):
        print("LaTeX leftovers: %d drop-cap(s) restored, %d stray command(s) "
              "removed, %d escaped bracket(s) un-mathed"
              % (leftover_stats['parstart'], leftover_stats['dropped'],
                 leftover_stats['brackets']))
    if leftover_stats.get('index_terms'):
        # A reduction, not a repair: the paper has an index and this book will
        # not. Said out loud so it is not one more silent loss (K110).
        print("Index: %d \\index term(s) dropped — the original builds an "
              "index, this book has none" % leftover_stats['index_terms'])

    md_text, nested_hits = split_nested_math_text(md_text)
    if nested_hits:
        print("Math: %d nested $...$ inside a text-mode argument split out; "
              "every $-pairing scanner downstream mis-closes on those"
              % nested_hits)

    md_text, math_refs = resolve_math_references(md_text, temp_dir)
    if math_refs:
        print("Math: %d \\ref(s) inside formulas resolved; texmath has no "
              "reader for one and refuses the whole display" % math_refs)

    md_text, macro_hits = expand_math_macros(md_text, temp_dir)
    if macro_hits:
        print("Math: %d formula(s) had the paper's own shorthand expanded "
              "(\\< -> \\langle); texmath knows only standard commands"
              % macro_hits)

    md_text, text_fonts = rewrite_text_fonts_in_math(md_text)
    if text_fonts:
        print(f"Math: {text_fonts} text-mode font switch(es) inside formulas "
              f"rewritten (\\textsc -> \\mathrm); texmath refuses the whole "
              f"formula over one")

    md_text, math_stats = normalize_math_commands(md_text)
    if math_stats['fonts']:
        print("Math: %d legacy font switch(es) rewritten (\\rm -> \\mathrm)"
              % math_stats['fonts'])
    if math_stats['accents']:
        print("Math: %d accent argument(s) braced "
              "(\\widetilde\\mathbf{X} -> \\widetilde{\\mathbf{X}}); texmath "
              "drops the whole formula over one"
              % math_stats['accents'])

    md_text, unboxed = unwrap_text_boxed_math_fonts(md_text)
    if unboxed:
        print("Math: %d math font(s) unwrapped from a text box "
              "(\\text{\\mathtt{x}} -> \\mathtt{x}); texmath refuses the "
              "nesting" % unboxed)

    md_text, ref_stats = resolve_references(md_text, temp_dir, lang_cfg)
    if ref_stats.get('subrefs'):
        print("Sub-figure references: %d resolved to panel letters"
              % ref_stats['subrefs'])

    # Restore the original's section numbering, so a reader can map a
    # translated heading back to the paper they are holding.
    md_text, sec_stats = number_sections(md_text, temp_dir)
    if sec_stats['numbered']:
        pdf = sec_stats.get('pdf') or {}
        detail = ''
        if pdf:
            bits = ['%d numbered' % pdf.get('matched', 0)]
            if pdf.get('unnumbered'):
                bits.append('%d unnumbered in the original' % pdf['unnumbered'])
            if pdf.get('wrapped'):
                bits.append('%d matched across a line break' % pdf['wrapped'])
            if pdf.get('missing'):
                bits.append('%d not found' % pdf['missing'])
            detail = ' (%s)' % ', '.join(bits)
        print(f"Sections: {sec_stats['numbered']} heading(s) keyed to the "
              f"original{detail}")
    elif sec_stats['skipped_reason']:
        print(f"Sections: not numbered — {sec_stats['skipped_reason']}")

    # Immediately after, because the two halves have to agree: the reference
    # pass above now resolves a theorem label to the number the paper prints,
    # and a declaration line still reading `정리 1` under prose saying
    # `정리 1.1` is worse than either alone (K130).
    md_text, thm_stats = number_theorem_statements(md_text, temp_dir, lang_cfg)
    if thm_stats['numbered'] or thm_stats['unnumbered']:
        bits = ['%d renumbered' % thm_stats['numbered']]
        if thm_stats['unnumbered']:
            bits.append('%d left unnumbered, as the paper prints them'
                        % thm_stats['unnumbered'])
        print('Theorem statements: %s' % ', '.join(bits))
    elif thm_stats['skipped_reason']:
        print('Theorem statements: left as they are — %s'
              % thm_stats['skipped_reason'])

    # After numbering, deliberately: the heading this adds is not in flat.tex,
    # and inserting it first made the ladder come out one too long.
    md_text, bib_stats = resolve_bibliography(md_text, temp_dir, lang_cfg)
    if bib_stats['dropped_duplicate']:
        print("References: dropped the inlined \\thebibliography — the source "
              "also ships a .bib and citeproc already rendered the list")
    if bib_stats['heading_added']:
        print("References: heading added over the rendered reference list")

    md_text, orphan_notes = rescue_orphan_footnotes(md_text)
    if orphan_notes:
        print(f"Footnotes: {orphan_notes} note(s) nothing referenced moved to "
              f"the front matter, where pandoc would have dropped them")

    # Captions become real <figure>/<figcaption> so they stop reading as body.
    md_text, trimmed = apply_graphics_trim(md_text, temp_dir)
    if trimmed:
        print(f"Figures: {trimmed} cropped as the source asked")
    md_text, fig_count = format_figure_blocks(md_text, lang_cfg, temp_dir)
    if fig_count:
        print(f"Figures: {fig_count} caption(s) formatted")

    md_text, grid_count = grid_tables_to_pipe(md_text)
    if grid_count:
        print(f"Tables: {grid_count} grid table(s) rewritten as pipe tables "
              f"(a grid one collapses once its cells change width)")

    md_text, tab_count = number_table_captions(md_text, temp_dir, lang_cfg)
    if tab_count:
        print(f"Tables: {tab_count} caption(s) numbered")
    # Where they landed, not how many were written. The count agreed while
    # ten of fifteen sat on prose, so the count is not the check (K151).
    placed_ok, placed_detail = check_badge_placement(md_text, lang_cfg)
    if not placed_ok:
        print("BLOCKING: %s" % placed_detail)
        print("  A table number on prose sends every sentence that cites it "
              "at the wrong thing, and no count can see it.")
        raise SystemExit(1)
    if tab_count:
        print("Tables: %s" % placed_detail)

    if any(ref_stats.values()):
        print("References: %d citation(s), %d cross-reference(s) resolved"
              % (ref_stats['cites'], ref_stats['xrefs'])
              + ("; %d citation(s) and %d cross-reference(s) had no target"
                 % (ref_stats['cites_missed'], ref_stats['xrefs_missed'])
                 if (ref_stats['cites_missed'] or ref_stats['xrefs_missed']) else ""))

    # Two prepared copies, because the two output paths cannot share one.
    #
    #   prepared.md      -> DOCX. Tables as MARKDOWN: pandoc drops raw HTML
    #                       entirely when writing DOCX, and injecting <table>
    #                       here left book.docx with zero tables and no check
    #                       complaining. Not every LaTeX table survives the
    #                       trip, so the shortfall is reported.
    #   pandoc_input.md  -> HTML/PDF/EPUB. Tables as HTML, which keeps the
    #                       column-count classes the print sheet sizes on.
    #
    # output.md itself is never rewritten; it stays the faithful translation.
    #
    # Algorithm floats are expanded FIRST, and into markdown rather than HTML,
    # so both prepared copies carry them: raw HTML survives only the HTML path,
    # which is the trap the two table copies exist to avoid. Everything the
    # float contains -- `$...$` included -- then travels the ordinary route.
    md_text, algo_ok, algo_bad = algorithm_float.expand_algorithm_floats(
        md_text, lang=lang_cfg.get('lang_attr', 'en'))
    if algo_ok or algo_bad:
        note = f"Algorithm floats: {algo_ok} converted to markdown"
        if algo_bad:
            note += f", {algo_bad} FAILED (they will be missing)"
        print(note)

    # The prompt tells every sub-agent to spell a term out on ITS first use,
    # because each one sees a single chunk and that is the only first use it
    # can know about. A term running through ten chunks therefore arrives
    # glossed ten times. Here the whole book is in one string, so the second
    # and later copies come out. output.md keeps them: it is the faithful
    # record of what each sub-agent wrote.
    md_text, glosses_dropped = glossary.dedupe_glosses(md_text)
    if glosses_dropped:
        print(f"First-use glosses: {glosses_dropped} repeat(s) removed")

    # Before the two output paths diverge, so the DOCX and the HTML agree
    # about which lines are headings. A heading glued to the paragraph above
    # is not a heading to pandoc, and the loss is silent.
    md_text = separate_headings(md_text)
    docx_md, docx_ok, docx_bad = expand_raw_latex_tables(
        md_text, math_mode=math_mode, output='markdown', temp_dir=temp_dir)
    # pandoc builds book.docx straight from this file and never sees the HTML
    # the other formats are styled through, so the equation number has to go
    # inside the formula here.
    docx_md, docx_tagged = tag_equations_for_markdown(docx_md, temp_dir)
    prepared = os.path.join(temp_dir, 'prepared.md')
    with open(prepared, 'w', encoding='utf-8', newline='') as fh:
        fh.write(docx_md)
    if docx_ok or docx_bad:
        note = f"Raw LaTeX tables (DOCX): {docx_ok} converted to markdown"
        if docx_bad:
            note += (f", {docx_bad} could not be expressed as a markdown table "
                     f"and stay as text")
        print(note)

    expanded_md, tables_ok, tables_bad = expand_raw_latex_tables(
        md_text, math_mode=math_mode, output='html', temp_dir=temp_dir)
    if tables_ok or tables_bad:
        note = f"Raw LaTeX tables: {tables_ok} converted to HTML"
        if tables_bad:
            note += f", {tables_bad} FAILED (they will be missing)"
        print(note)
    source_md = os.path.join(temp_dir, 'pandoc_input.md') if tables_ok else prepared
    if tables_ok:
        with open(source_md, 'w', encoding='utf-8', newline='') as fh:
            fh.write(expanded_md)

    # Tier 0 pandoc -> tier 1 python-markdown -> (only on request) regex
    success = False
    used = None
    pandoc = resolve_pandoc()
    if pandoc:
        success = convert_with_pandoc(source_md, temp_html_file, title,
                                      lang_cfg['lang_attr'], math_mode=math_mode)
        if success:
            used = 'pandoc'
    else:
        print("WARNING: pandoc not found (checked pypandoc, PATH, and standard "
              "install dirs)")

    if not success and MARKDOWN_AVAILABLE:
        if convert_with_python_markdown(source_md, temp_html_file, title):
            success, used = True, 'python-markdown'

    if not success:
        if not allow_degraded:
            print("\nERROR: no high-fidelity markdown converter available.")
            print(f"  pandoc:          {'found' if pandoc else 'NOT FOUND'}")
            print(f"  python-markdown: {'installed' if MARKDOWN_AVAILABLE else 'NOT INSTALLED'}")
            print("  The regex fallback cannot render tables or math and would")
            print("  silently produce a degraded book. Refusing to continue.")
            print("  fix: install pandoc (https://pandoc.org/installing.html) or")
            print("       run `python -m pip install markdown`,")
            print("  or re-run with --allow-degraded-html to accept table-less output.")
            return False
        print("WARNING: --allow-degraded-html — using the regex fallback. "
              "Tables will be LOST and math may be mangled.")
        if convert_with_basic_regex(source_md, temp_html_file, title):
            success, used = True, 'basic-regex(DEGRADED)'

    if not success:
        print("Error: All markdown-to-HTML converters failed")
        return False
    print(f"HTML converter used: {used}")

    process_html_separators(temp_html_file)
    finish_table_rules(temp_html_file, temp_dir)

    # Extract body content
    try:
        with open(temp_html_file, 'r', encoding='utf-8') as f:
            html_content = f.read()
    except Exception as e:
        print(f"Error reading HTML file: {e}")
        return False

    body_match = re.search(r'<body[^>]*>(.*?)</body>', html_content, re.DOTALL | re.IGNORECASE)
    body_content = body_match.group(1).strip() if body_match else html_content

    # Mark the numbered equations. The stylesheet sets the label flush right,
    # so nothing is added to the formula text itself and a copy-paste of the
    # equation stays clean.
    body_content, eq_tagged = tag_equations_in_html(body_content, md_text,
                                                    temp_dir)
    if eq_tagged or docx_tagged:
        print("Equations: %d numbered (%d in the DOCX copy)"
              % (eq_tagged, docx_tagged))

    body_content, cjk_em = mark_cjk_emphasis(body_content)
    if cjk_em:
        print("Emphasis: %d CJK run(s) marked for the bold substitute "
              "(Latin emphasis keeps real italics)" % cjk_em)

    # After the equations are numbered, so "식 (7)" has something to point at.
    body_content, xrefs = link_cross_references(body_content, lang_cfg)
    if xrefs['linked'] or xrefs['coloured']:
        print("References: %d linked, %d coloured"
              % (xrefs['linked'], xrefs['coloured']))

    if not check_table_fidelity(md_file, body_content, strict=not allow_degraded):
        return False
    if not check_math_fidelity(md_file, body_content):
        return False

    # Every check above counts something: tables, images, equations, captions.
    # A float in an environment nobody wrote a handler for is not counted by
    # any of them, so it can be deleted between output.md and the HTML while
    # the build reports success. This one asks the opposite question -- does
    # each raw-LaTeX block still have prose on the page? -- and needs no list
    # of environments to be kept up to date.
    # Fingerprint the text we HANDED to pandoc, not the text we started with.
    # `md_text` has already had its algorithm floats expanded and its repeated
    # glosses removed, so a caption reading `다운스트림(downstream)` before the
    # dedupe and `다운스트림` after it no longer looks like a lost table. A
    # float the expander could not convert is still `\begin{...}` here, so
    # nothing that matters escapes the check.
    lost = algorithm_float.check_latex_float_fidelity(md_text, body_content)
    # A picture DRAWN IN CODE has no image file anywhere in the source, and no
    # stage of this pipeline can produce one — the absence is a limitation, not
    # a defect, and failing the build over it only stops the other 99% of the
    # book from being made. Say what the reader loses and carry on.
    drawn = [row for row in lost if row[0].rstrip('*') in _CODE_DRAWN_FIGURES]
    lost = [row for row in lost if row not in drawn]
    if drawn:
        print("WARNING: %d figure(s) are drawn in TikZ/PGF code with no image "
              "file in the source, so they cannot be rendered and are absent "
              "from the book:" % len(drawn))
        for env, phrase in drawn:
            print("  \\begin{%s} ... %s" % (env, phrase))
    if lost:
        print("ERROR: %d raw LaTeX block(s) reached the markdown and left no "
              "trace in the HTML. pandoc drops raw LaTeX on the HTML path "
              "without warning, so this content is missing from the book:"
              % len(lost))
        for env, phrase in lost:
            print("  \\begin{%s} ... %s" % (env, phrase))
        if not allow_degraded:
            return False

    # Generate book_doc.html with ebook template.
    # The ebook template gets font_family_ebook (double-quoted CSS, which is
    # what Calibre's parser wants); until now that config key was never read.
    template_ebook = os.path.join(SCRIPT_DIR, 'template_ebook.html')
    book_doc_file = os.path.join(temp_dir, 'book_doc.html')
    ebook_cfg = {**lang_cfg,
                 'font_family': lang_cfg.get('font_family_ebook', lang_cfg['font_family'])}
    # The names have been in config.txt under `creator=` since conversion,
    # with nowhere to go: the book opened on its table of contents and
    # credited one of sixteen authors, in a <meta> tag no reader sees.
    book_cfg = load_config(temp_dir) or {}
    arxiv_id = (book_cfg.get('arxiv_id') or '').strip()
    title_page = build_title_page(
        title, source='arXiv:%s' % arxiv_id if arxiv_id else '')
    full_byline = (book_cfg.get('creator') or '').strip() or author
    apply_template_to_html(body_content, template_ebook, book_doc_file, title,
                           ebook_cfg, author, print_cfg=print_cfg,
                           title_page=title_page, byline=full_byline)

    # Generate book.html with web template
    template_web = os.path.join(SCRIPT_DIR, 'template.html')
    book_file = os.path.join(temp_dir, 'book.html')
    apply_template_to_html(body_content, template_web, book_file, title, lang_cfg, author)

    if not _check_generated_html_sanity(book_doc_file):
        return False
    if not _check_generated_html_sanity(book_file):
        return False

    print(f"Generated: output.html, book_doc.html, book.html")
    return True


# =============================================================================
# Step 6: Add TOC
# =============================================================================

# MathML keeps the TeX source of every formula in an <annotation> element for
# copy-paste. Anything that turns heading HTML into plain text has to drop it
# first, or a heading with math in it reads as the glyph followed by its own
# source -- "γ\gamma의 ..." in the TOC, the bookmarks and the print TOC.
_ANNOTATION_RE = re.compile(r'<annotation\b[^>]*>.*?</annotation>', re.DOTALL)


def generate_heading_id(text, existing_ids):
    """Generate unique ID for heading"""
    base_id = re.sub(r'[^\w\s-]', '', text.lower())
    base_id = re.sub(r'[-\s]+', '-', base_id)
    base_id = base_id.strip('-')

    if not base_id:
        base_id = 'heading'

    heading_id = base_id
    counter = 1
    while heading_id in existing_ids:
        heading_id = f"{base_id}-{counter}"
        counter += 1

    return heading_id


def generate_simple_toc_html(toc_data):
    """Generate simple HTML for table of contents"""
    if not toc_data:
        return ""

    toc_html = '<ul>\n'
    current_level = 1

    for item in toc_data:
        level = item['level']
        text = item['text']
        heading_id = item['id']

        if level > current_level:
            while current_level < level:
                toc_html += '<li><ul>\n'
                current_level += 1
        elif level < current_level:
            while current_level > level:
                toc_html += '</ul></li>\n'
                current_level -= 1

        toc_html += f'<li><a href="#{heading_id}">{text}</a></li>\n'

    while current_level > 1:
        toc_html += '</ul></li>\n'
        current_level -= 1

    toc_html += '</ul>\n'
    return toc_html


def insert_toc_with_bs4(html_file):
    """Insert TOC using BeautifulSoup"""
    try:
        with open(html_file, 'r', encoding='utf-8') as f:
            html_content = f.read()
    except Exception as e:
        print(f"Error reading HTML file: {e}")
        return False

    soup = BeautifulSoup(html_content, 'html.parser')

    toc_data = []
    existing_ids = []

    for heading in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
        level = int(heading.name[1])
        text = heading.get_text().strip()
        if not text:
            continue

        heading_id = generate_heading_id(text, existing_ids)
        existing_ids.append(heading_id)
        heading['id'] = heading_id
        toc_data.append({'level': level, 'text': text, 'id': heading_id})

    if not toc_data:
        print("No headings found for TOC")
        return False

    toc_html = generate_simple_toc_html(toc_data)

    toc_content_div = soup.find('div', class_='toc-content')
    if toc_content_div:
        toc_content_div.clear()
        toc_soup = BeautifulSoup(toc_html, 'html.parser')
        toc_content_div.append(toc_soup)
        print(f"TOC inserted ({len(toc_data)} headings)")
    else:
        print("Warning: .toc-content div not found, TOC not inserted")
        return False

    try:
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(str(soup))
        return True
    except Exception as e:
        print(f"Error saving HTML file: {e}")
        return False


def insert_toc_with_regex(html_file):
    """Insert TOC using regex (fallback)"""
    try:
        with open(html_file, 'r', encoding='utf-8') as f:
            html_content = f.read()
    except Exception as e:
        print(f"Error reading HTML file: {e}")
        return False

    # Rewrite in one pass over the matches. Building `<h2>text</h2>` and
    # str.replace()-ing it finds nothing, because pandoc writes
    # `<h2 id="slug">`: every link in the floating TOC pointed at an anchor
    # that was never created, so the whole sidebar was dead on the web page.
    heading_pattern = r'<(h[1-6])([^>]*)>(.*?)</\1>'
    matches = list(re.finditer(heading_pattern, html_content,
                               re.IGNORECASE | re.DOTALL))
    if not matches:
        print("No headings found for TOC")
        return False

    toc_html = '<ul>\n'
    pieces, cursor = [], 0
    for i, m in enumerate(matches):
        tag, attrs, text = m.group(1), m.group(2), m.group(3)
        level = int(tag[1])
        clean_text = re.sub(r'<[^>]+>', '',
                            _ANNOTATION_RE.sub('', text)).strip()
        # Keep the anchor the heading already has -- other links may use it.
        existing = re.search(r'\bid="([^"]+)"', attrs)
        if existing:
            heading_id = existing.group(1)
            pieces.append(html_content[cursor:m.end()])
        else:
            heading_id = f"heading-{i+1}"
            pieces.append(html_content[cursor:m.start()])
            pieces.append(f'<{tag} id="{heading_id}"{attrs}>{text}</{tag}>')
        cursor = m.end()

        toc_html += '  ' * (level - 1)
        toc_html += f'<li><a href="#{heading_id}">{clean_text}</a></li>\n'

    pieces.append(html_content[cursor:])
    html_content = ''.join(pieces)
    toc_html += '</ul>\n'

    toc_content_pattern = r'(<div[^>]*class="toc-content[^"]*"[^>]*>).*?(</div>)'
    if re.search(toc_content_pattern, html_content, re.DOTALL):
        # A callable, not a template: toc_html carries whatever the
        # headings carry, and a heading with math in it ($\ell_2$) puts a
        # backslash into the replacement, where re reads it as an escape.
        html_content = re.sub(
            toc_content_pattern,
            lambda m: m.group(1) + toc_html + m.group(2),
            html_content,
            flags=re.DOTALL
        )
        print(f"TOC inserted ({len(matches)} headings)")
    else:
        print("Warning: .toc-content div not found")
        return False

    try:
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        return True
    except Exception as e:
        print(f"Error saving HTML file: {e}")
        return False


# The page-number slot in a print TOC entry. chromium_pdf renders once to find
# out which page each heading landed on, substitutes the real numbers, then
# renders again -- Chromium implements no `target-counter()`, so there is no
# way to ask CSS for "the page this link points at".
PRINT_TOC_SENTINEL = '\u00a7\u00a7%d\u00a7\u00a7'


def build_print_toc(html_content, toc_label='Contents', max_level=3):
    """Return (html_with_ids_and_toc, entry_count).

    book.html gets a floating sidebar TOC, which is a screen affordance and is
    hidden in print. book_doc.html -- the source for both EPUB and PDF -- had
    no TOC at all, so every generated book shipped without one.
    """
    headings = list(re.finditer(r'<(h[1-6])([^>]*)>(.*?)</\1>',
                                html_content, re.IGNORECASE | re.DOTALL))
    entries, pieces, cursor, n = [], [], 0, 0
    for m in headings:
        tag, attrs, inner = m.group(1), m.group(2), m.group(3)
        text = re.sub(r'<[^>]+>', '', _ANNOTATION_RE.sub('', inner)).strip()
        text = _html_lib.unescape(text)
        if not text:
            continue
        level = int(tag[1])
        # pandoc renders the document title as <h1 class="title"> inside
        # <header id="title-block-header">. A book's own title is not a TOC
        # entry, and listing it makes the first line point at itself.
        is_title = re.search(r'class="[^"]*\btitle\b', attrs or '') is not None
        n += 1
        heading_id = 'sec-%d' % n
        if 'id=' not in attrs.lower():
            pieces.append(html_content[cursor:m.start()])
            pieces.append('<%s id="%s"%s>%s</%s>' % (tag, heading_id, attrs, inner, tag))
            cursor = m.end()
        else:
            found = re.search(r'id="([^"]+)"', attrs)
            heading_id = found.group(1) if found else heading_id
        if level <= max_level and not is_title:
            entries.append({'level': level, 'text': text, 'id': heading_id})
    pieces.append(html_content[cursor:])
    html_content = ''.join(pieces)

    if not entries:
        return html_content, 0

    rows = ['<nav class="print-toc" role="doc-toc">',
            '<h1 class="print-toc-title">%s</h1>' % _html_lib.escape(toc_label),
            '<ul class="print-toc-list">']
    for i, e in enumerate(entries):
        rows.append(
            '<li class="toc-l%d"><a href="#%s">'
            '<span class="toc-text">%s</span>'
            '<span class="toc-dots"></span>'
            '<span class="toc-page" data-toc="%d">%s</span>'
            '</a></li>' % (e['level'], e['id'], _html_lib.escape(e['text']), i,
                           PRINT_TOC_SENTINEL % i))
    rows.append('</ul></nav>')
    toc_html = '\n'.join(rows)

    # After the title page, when there is one. Pinned to the opening <body>
    # tag the contents came first and the title page second, so the book
    # opened on its own table of contents with the title on the leaf behind
    # it -- which is how the title page looked absent even once it was built.
    title_page = re.search(r'<section class="title-page">.*?</section>',
                           html_content, re.DOTALL)
    if title_page:
        at = title_page.end()
        html_content = html_content[:at] + '\n' + toc_html + html_content[at:]
    elif re.search(r'<body[^>]*>', html_content, re.IGNORECASE):
        html_content = re.sub(r'(<body[^>]*>)', lambda mm: mm.group(1) + '\n' + toc_html,
                              html_content, count=1, flags=re.IGNORECASE)
    else:
        html_content = toc_html + html_content
    return html_content, len(entries)


def add_print_toc_to_ebook(temp_dir, toc_label='Contents'):
    """Insert the print/EPUB table of contents into book_doc.html."""
    path = os.path.join(temp_dir, 'book_doc.html')
    if not os.path.exists(path):
        print("Warning: book_doc.html not found, skipping print TOC")
        return False
    with open(path, 'r', encoding='utf-8') as fh:
        content = fh.read()
    if 'class="print-toc"' in content:
        return True
    content, count = build_print_toc(content, toc_label)
    if not count:
        print("No headings found for the print TOC")
        return False
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(content)
    print(f"Print TOC inserted into book_doc.html ({count} entries)")
    return True


def add_toc(temp_dir, lang_cfg=None):
    """Add the sidebar TOC to book.html and a print TOC to book_doc.html"""
    print("=== Adding Table of Contents ===")

    book_file = os.path.join(temp_dir, 'book.html')
    if not os.path.exists(book_file):
        print("Warning: book.html not found, skipping TOC")
        return False

    if BS4_AVAILABLE:
        ok = insert_toc_with_bs4(book_file)
    else:
        ok = insert_toc_with_regex(book_file)

    # book_doc.html feeds BOTH the EPUB and the PDF and used to get no TOC at
    # all, while this step still printed "TOC inserted" -- which read as though
    # every format had one.
    label = (lang_cfg or {}).get('toc_label', 'Contents')
    add_print_toc_to_ebook(temp_dir, label)
    return ok


# =============================================================================
# Step 7: Generate DOCX/EPUB/PDF with error transparency
# =============================================================================

def calibre_available():
    """True when Calibre's ebook-convert can be found."""
    import calibre_html_publish
    return bool(calibre_html_publish.find_calibre_convert())


def generate_format(html_file, temp_dir, output_ext, lang_attr, cover=None,
                    pdf_engine='chromium', print_cfg=None):
    """Generate a specific format.

    PDF goes to headless Chromium by default, because Calibre honours
    neither @page nor the print stylesheet and was silently producing
    US Letter pages with 25.4mm margins. Everything else still goes to
    calibre_html_publish.py.
    """
    output_file = os.path.join(temp_dir, f"book{output_ext}")
    cover = cover if output_ext == '.epub' else None
    if cover and not os.path.isfile(cover):
        print(f"Cover image not found: {cover}")
        return None

    if os.path.exists(output_file):
        output_mtime = os.path.getmtime(output_file)

        # Check if source HTML is newer
        html_newer = os.path.getmtime(html_file) > output_mtime

        # Check if any image asset is newer (Calibre embeds these)
        images_newer = False
        images_dir = os.path.join(temp_dir, 'images')
        if os.path.isdir(images_dir):
            for img in os.listdir(images_dir):
                img_path = os.path.join(images_dir, img)
                if os.path.isfile(img_path) and os.path.getmtime(img_path) > output_mtime:
                    images_newer = True
                    break

        cover_newer = bool(cover and os.path.getmtime(cover) > output_mtime)

        if not html_newer and not images_newer and not cover_newer:
            file_size = os.path.getsize(output_file)
            print(f"Skipping {output_ext} - already exists and up to date ({file_size:,} bytes)")
            return output_file
        else:
            reasons = []
            if html_newer:
                reasons.append("source HTML changed")
            if images_newer:
                reasons.append("image assets changed")
            if cover_newer:
                reasons.append("cover image changed")
            print(f"Rebuilding {output_ext} - {', '.join(reasons)}")

    if output_ext == '.pdf' and pdf_engine == 'chromium':
        # Rendered in place: book_doc.html sits next to images/, so a
        # relative <img src="images/x.png"> resolves with no copying,
        # no work.html and no temp directory to clean up.
        def _render(src, out):
            return chromium_pdf.html_to_pdf(src, out, lang=lang_attr,
                                            profile=print_cfg)

        # A formula as wide as the text column prints under its own number,
        # and no stylesheet can prevent it: MathML compresses its spacing to
        # the box rather than shrinking into it. The size that clears the
        # number cannot be known without laying the page out, so this renders,
        # measures what it rendered, and renders again if anything collided.
        # A book with no collision costs exactly one render, as before.
        ok, collided = equation_fit.fit_equations(html_file, output_file,
                                                  _render, print_cfg)
        if collided:
            print("ERROR: equation %s still prints under its own number at "
                  "the smallest size tried." % ', '.join(collided))
            print("  The formula fills the text column; nothing downstream "
                  "can separate them, and the number is unreadable on the "
                  "page while every content check passes.")
            raise SystemExit(1)
        return output_file if ok and os.path.exists(output_file) else None

    publish_script = os.path.join(SCRIPT_DIR, "calibre_html_publish.py")
    if not os.path.exists(publish_script):
        print(f"calibre_html_publish.py not found at: {publish_script}")
        return None

    try:
        # sys.executable, not "python3": on Windows only `python`/`py` resolve,
        # so a hardcoded python3 fails every format from cmd/PowerShell.
        cmd = [sys.executable, publish_script, html_file, "-o", output_file,
               "--lang", lang_attr]
        if cover:
            cmd.extend(["--cover", cover])
        env = {**os.environ, 'PYTHONIOENCODING': 'utf-8'}
        result = subprocess.run(cmd, check=True, capture_output=True, text=True,
                                encoding='utf-8', errors='replace', env=env)

        if os.path.exists(output_file):
            file_size = os.path.getsize(output_file)
            return output_file
        else:
            print(f"Failed to generate {output_ext}")
            if result.stdout:
                print(f"  stdout: {result.stdout[-500:]}")
            return None
    except subprocess.CalledProcessError as e:
        print(f"Failed to generate {output_ext}")
        if e.stdout:
            print(f"  stdout: {e.stdout[-500:]}")
        if e.stderr:
            print(f"  stderr: {e.stderr[-500:]}")
        return None
    except Exception as e:
        print(f"Error generating {output_ext}: {e}")
        return None


def build_reference_docx(temp_dir, lang_cfg, print_cfg):
    """Produce a pandoc --reference-doc matching the print profile.

    Without one, pandoc uses its built-in default: Calibri 11pt on US Letter
    with 1-inch margins and no East Asian font mapping at all, so a Korean
    translation opened in Word came out in whatever fallback face Word chose.

    Starts from pandoc's own default so every style pandoc writes into
    (Heading N, Source Code, Table Caption, ...) definitely exists, then
    overrides page setup and fonts. Returns the path, or None if unavailable.
    """
    try:
        import docx
        from docx.shared import Pt, Mm
        from docx.oxml.ns import qn
    except ImportError:
        print("  (python-docx not installed — DOCX keeps pandoc's default styling)")
        return None

    pandoc = resolve_pandoc()
    if not pandoc:
        return None

    ref_path = os.path.join(temp_dir, 'reference.docx')
    try:
        with open(ref_path, 'wb') as fh:
            result = subprocess.run(
                [pandoc, '--print-default-data-file', 'reference.docx'],
                stdout=fh, stderr=subprocess.PIPE, timeout=120)
        if result.returncode != 0 or not os.path.getsize(ref_path):
            return None

        latin, cjk = layout.docx_fonts(lang_cfg)
        body_pt = print_cfg.get('base_font_size_pt', 11.5)
        line_height = print_cfg.get('line_height', 1.5)
        width_mm, height_mm = layout.page_size_mm(print_cfg)

        doc = docx.Document(ref_path)

        section = doc.sections[0]
        section.page_width = Mm(width_mm)
        section.page_height = Mm(height_mm)
        section.left_margin = Mm(print_cfg.get('margin_left_mm', 18))
        section.right_margin = Mm(print_cfg.get('margin_right_mm', 18))
        section.top_margin = Mm(print_cfg.get('margin_top_mm', 18))
        section.bottom_margin = Mm(print_cfg.get('margin_bottom_mm', 22))

        def set_fonts(style, latin_face, cjk_face, size_pt=None, bold=None):
            font = style.font
            font.name = latin_face
            if size_pt is not None:
                font.size = Pt(size_pt)
            if bold is not None:
                font.bold = bold
            rpr = style.element.get_or_add_rPr()
            rfonts = rpr.get_or_add_rFonts()
            for attr in ('w:ascii', 'w:hAnsi', 'w:cs'):
                rfonts.set(qn(attr), latin_face)
            # The one Word needs for Hangul/CJK runs, and the one pandoc's
            # default reference doc never sets.
            rfonts.set(qn('w:eastAsia'), cjk_face)

        names = {s.name for s in doc.styles}

        if 'Normal' in names:
            normal = doc.styles['Normal']
            set_fonts(normal, latin, cjk, body_pt)
            normal.paragraph_format.line_spacing = line_height
            normal.paragraph_format.space_after = Pt(0)

        # 제목 고딕 / 본문 명조: the same pairing the print sheet uses.
        heading_latin, heading_cjk = layout.docx_heading_fonts(lang_cfg)
        ladder = {'Title': body_pt * 1.9, 'Heading 1': body_pt * 1.75,
                  'Heading 2': body_pt * 1.45, 'Heading 3': body_pt * 1.22,
                  'Heading 4': body_pt * 1.05, 'Heading 5': body_pt,
                  'Heading 6': body_pt}
        for style_name, size in ladder.items():
            if style_name in names:
                set_fonts(doc.styles[style_name], heading_latin, heading_cjk,
                          round(size, 1), bold=True)

        for mono_style in ('Source Code', 'Verbatim Char'):
            if mono_style in names:
                set_fonts(doc.styles[mono_style], 'Consolas', 'DotumChe',
                          round(body_pt * 0.85, 1))

        doc.save(ref_path)
        return ref_path
    except Exception as e:
        print(f"  (could not build a DOCX reference doc: {e})")
        try:
            os.remove(ref_path)
        except OSError:
            pass
        return None



_W_TBL_RE = re.compile(r'<w:tbl>.*?</w:tbl>', re.DOTALL)
_W_TR_RE = re.compile(r'<w:tr\b[^>]*>.*?</w:tr>', re.DOTALL)
_W_TRPR_RE = re.compile(r'<w:trPr>(.*?)</w:trPr>', re.DOTALL)
# Everything the schema puts BEFORE w:tblHeader inside w:trPr. Word rejects
# the file outright if a child turns up out of order.
_W_BEFORE_HEADER_RE = re.compile(
    r'(?:<w:cnfStyle\b[^>]*/?>|<w:divId\b[^>]*/?>|<w:gridBefore\b[^>]*/?>'
    r'|<w:gridAfter\b[^>]*/?>|<w:wBefore\b[^>]*/?>|<w:wAfter\b[^>]*/?>'
    r'|<w:cantSplit\b[^>]*/?>|<w:trHeight\b[^>]*/?>)*')


def _mark_row_as_header(row):
    """Add <w:tblHeader/> to one <w:tr>, in schema order."""
    if 'w:tblHeader' in row:
        return row, False
    body = _W_TRPR_RE.search(row)
    if body:
        head = _W_BEFORE_HEADER_RE.match(body.group(1))
        at = body.start(1) + head.end()
        return row[:at] + '<w:tblHeader/>' + row[at:], True
    at = row.index('>') + 1
    return row[:at] + '<w:trPr><w:tblHeader/></w:trPr>' + row[at:], True


def mark_docx_header_rows(docx_path, temp_dir):
    """Repeat each table's header rows on every page in Word. (marked, tables).

    pandoc marks one header row or none, so a multi-deck header -- the case
    the reader most needs repeated -- was never repeated at all.
    """
    plans = table_structures(temp_dir)
    if not plans or not os.path.isfile(docx_path):
        return 0, 0
    try:
        with zipfile.ZipFile(docx_path) as zf:
            names = zf.namelist()
            blobs = {name: zf.read(name) for name in names}
    except (zipfile.BadZipFile, OSError):
        return 0, 0
    if 'word/document.xml' not in blobs:
        return 0, 0
    doc = blobs['word/document.xml'].decode('utf-8')

    tables = _W_TBL_RE.findall(doc)
    if len(tables) != len(plans):
        # Matched by position, so a disagreement means the mapping cannot be
        # trusted. Leaving Word as pandoc left it is the safe answer.
        sys.stderr.write(
            'warning: %d table(s) in the source, %d in the DOCX; Word header '
            'rows left as pandoc set them\n' % (len(plans), len(tables)))
        return 0, len(tables)

    marked, index = [0], [0]

    def fix(match):
        table = match.group(0)
        want = plans[index[0]].get('header') or 0
        index[0] += 1
        if want < 1:
            return table
        rows, count = [], [0]

        def row_fix(row_match):
            if count[0] >= want:
                return row_match.group(0)
            count[0] += 1
            row, changed = _mark_row_as_header(row_match.group(0))
            if changed:
                marked[0] += 1
            return row

        rows.append(_W_TR_RE.sub(row_fix, table))
        return rows[0]

    doc = _W_TBL_RE.sub(fix, doc)
    if not marked[0]:
        return 0, len(tables)

    blobs['word/document.xml'] = doc.encode('utf-8')
    tmp = docx_path + '.tmp'
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as out:
        for name in names:
            out.writestr(name, blobs[name])
    os.replace(tmp, docx_path)
    return marked[0], len(tables)


def generate_docx_with_pandoc(temp_dir, title, author, lang_attr,
                              lang_cfg=None, print_cfg=None):
    """Build book.docx straight from output.md via pandoc.

    Calibre's DOCX writer has no math support whatsoever (its from_html class
    exposes no math handling), so routing DOCX through Calibre silently drops
    every equation. pandoc emits native OMML — real, editable Word equations.
    """
    pandoc = resolve_pandoc()
    if not pandoc:
        return None

    # prepared.md is output.md with citations and cross-references resolved.
    # DOCX is built straight from markdown, so without this it would still show
    # raw [@key] and (fig:x) markers that the HTML path had already fixed.
    md_file = os.path.join(temp_dir, 'prepared.md')
    if not os.path.exists(md_file):
        md_file = os.path.join(temp_dir, 'output.md')
    out_file = os.path.join(temp_dir, 'book.docx')
    if not os.path.exists(md_file):
        return None

    # pandoc runs with cwd=temp_dir so that relative `images/x.png` refs
    # resolve and get embedded into the .docx. That means the paths handed to
    # pandoc must be relative to temp_dir too — passing `temp_dir/output.md`
    # there makes pandoc look for `temp_dir/temp_dir/output.md`, which fails
    # and silently downgrades the whole DOCX to the math-less Calibre path.
    cmd = [
        pandoc, os.path.basename(md_file), '-o', os.path.basename(out_file),
        '--from', pandoc_from(lang_attr), '--to', 'docx',
        '--standalone', '--toc', '--toc-depth=3',
        '--metadata', f'title={title}',
        '--metadata', f'author={author}',
        '--metadata', f'lang={lang_attr}',
        '--resource-path', '.',
        '--wrap=preserve',
    ]

    # Page setup and CJK fonts. Without this pandoc falls back to Calibri 11pt
    # on Letter with 1-inch margins and no eastAsia mapping.
    reference = build_reference_docx(temp_dir, lang_cfg or {},
                                     print_cfg or layout.get_print_profile())
    if reference:
        cmd.extend(['--reference-doc', os.path.basename(reference)])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=temp_dir,
                                encoding='utf-8', errors='replace', timeout=600)
        if result.returncode != 0:
            print(f"pandoc docx failed: {(result.stderr or '')[:1200]}")
            return None
        return out_file if os.path.exists(out_file) else None
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"pandoc docx error: {e}")
        return None


def generate_formats(temp_dir, lang_attr, cover=None, title=None, author=None,
                     docx_engine='pandoc', pdf_engine='chromium', print_cfg=None,
                     lang_cfg=None):
    """Generate DOCX, EPUB, and PDF with result summary"""
    print("=== Generating output formats ===")

    html_file = os.path.join(temp_dir, "book_doc.html")
    if not os.path.exists(html_file):
        html_files = glob.glob(os.path.join(temp_dir, "*.html"))
        if html_files:
            html_file = max(html_files, key=os.path.getmtime)
        else:
            print("No HTML files found for format generation")
            return

    results = {}

    if docx_engine == 'pandoc' and resolve_pandoc():
        docx = generate_docx_with_pandoc(temp_dir, title or 'Translated Book',
                                         author or 'Unknown Author', lang_attr,
                                         lang_cfg=lang_cfg, print_cfg=print_cfg)
        if docx:
            marked, seen = mark_docx_header_rows(docx, temp_dir)
            if marked:
                print(f"  Word header rows repeated: {marked} row(s) "
                      f"across {seen} table(s)")
            results['.docx'] = ('OK', f"{os.path.getsize(docx):,} bytes (pandoc/OMML)")
        else:
            print("pandoc docx failed — falling back to Calibre (math will be lost)")
            docx = generate_format(html_file, temp_dir, '.docx', lang_attr)
            results['.docx'] = (('OK', f"{os.path.getsize(docx):,} bytes")
                                if docx else ('FAILED', ''))
    else:
        docx = generate_format(html_file, temp_dir, '.docx', lang_attr)
        results['.docx'] = (('OK', f"{os.path.getsize(docx):,} bytes")
                            if docx else ('FAILED', ''))

    for ext in ['.epub', '.pdf']:
        # Calibre is the only EPUB writer, and on the arXiv path it is the
        # only thing Calibre is used for. A machine without it still gets the
        # PDF and DOCX, so a missing Calibre skips the EPUB rather than
        # failing a build whose PDF came out fine.
        if ext == '.epub' and not calibre_available():
            print("Skipping .epub - Calibre ebook-convert is not installed "
                  "(https://calibre-ebook.com/)")
            results[ext] = ('SKIPPED', 'Calibre is not installed')
            continue
        result = generate_format(html_file, temp_dir, ext, lang_attr, cover=cover,
                                 pdf_engine=pdf_engine, print_cfg=print_cfg)
        if result:
            file_size = os.path.getsize(result)
            detail = f"{file_size:,} bytes"
            if ext == '.pdf':
                detail += f" ({pdf_engine})"
            results[ext] = ('OK', detail)
        else:
            results[ext] = ('FAILED', '')

    # Print summary table
    print("\nFormat results:")
    has_failures = False
    for ext, (status, detail) in results.items():
        if status in ('OK', 'SKIPPED'):
            print(f"  {ext}: {status} ({detail})")
        else:
            print(f"  {ext}: {status}")
            has_failures = True

    return not has_failures


def _validate_export_name(name):
    """Validate an export filename stem. Keep aliases inside temp_dir."""
    if not name or not name.strip():
        raise ValueError("--export-name must not be empty")
    if '\x00' in name or '/' in name or '\\' in name:
        raise ValueError("--export-name must be a filename stem, not a path")
    return name.strip()


def export_named_aliases(temp_dir, export_name):
    """Copy canonical outputs to optional user-facing filenames.

    Canonical artifacts remain untouched. The alias names use export_name as a
    filename stem, with book_doc.html receiving a _doc suffix to avoid colliding
    with the web HTML alias.
    """
    stem = _validate_export_name(export_name)
    mappings = {
        "book.html": f"{stem}.html",
        "book_doc.html": f"{stem}_doc.html",
        "book.docx": f"{stem}.docx",
        "book.epub": f"{stem}.epub",
        "book.pdf": f"{stem}.pdf",
    }
    copied = []
    for src_name, dst_name in mappings.items():
        src = os.path.join(temp_dir, src_name)
        if not os.path.exists(src):
            continue
        dst = os.path.join(temp_dir, dst_name)
        if os.path.abspath(src) == os.path.abspath(dst):
            continue
        shutil.copy2(src, dst)
        copied.append(dst_name)
    return copied


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description='Merge translated pages and build final outputs')
    parser.add_argument('--temp-dir', required=True, help='Temp directory path')
    parser.add_argument('--title', default=None, help='Translated book title (override config)')
    parser.add_argument('--author', default=None, help='Author name (override config)')
    parser.add_argument('--lang', default=None, help='Output language code (override config)')
    parser.add_argument('--cover', default=None, help='Cover image path for EPUB output')
    parser.add_argument('--export-name', default=None, help='Optional filename stem for exported alias copies')
    parser.add_argument('--cleanup', action='store_true', help='Remove intermediate artifacts after successful build')
    parser.add_argument('--build-only', action='store_true',
                        help='Skip the merge step and build from the existing output.md')
    parser.add_argument('--force-html', action='store_true',
                        help='Always regenerate HTML even if book_doc.html looks fresh')
    parser.add_argument('--allow-degraded-html', action='store_true',
                        help='Permit the regex fallback, which loses tables and mangles math')
    parser.add_argument('--math', choices=['mathml', 'none'], default='mathml',
                        help='Math rendering mode for HTML output (default: mathml)')
    parser.add_argument('--docx-engine', choices=['pandoc', 'calibre'], default='pandoc',
                        help='DOCX generator. pandoc gives native editable equations; '
                             'calibre drops math entirely (default: pandoc)')
    parser.add_argument('--pdf-engine', choices=['chromium', 'calibre'],
                        default='chromium',
                        help='PDF renderer. chromium uses the local Chrome/Edge '
                             'print engine and honours the @page print CSS; '
                             'calibre is the legacy path and ignores it '
                             '(default: chromium)')
    parser.add_argument('--section-break', dest='section_break',
                        action='store_true', default=None,
                        help='Start every top-level heading on a new page. '
                             'Off by default: in this pipeline h1 is every '
                             'section, so it costs ~20%% more pages')
    parser.add_argument('--no-section-break', dest='section_break',
                        action='store_false',
                        help='Explicitly keep sections running on (the default)')
    parser.add_argument('--print-profile', choices=sorted(layout.PRINT_PROFILES),
                        default=layout.DEFAULT_PRINT_PROFILE,
                        help='Page geometry and base type size for the PDF. '
                             'Changing it needs --force-html, because HTML '
                             'regeneration is keyed on output.md mtime '
                             f'(default: {layout.DEFAULT_PRINT_PROFILE})')

    args = parser.parse_args()
    temp_dir = args.temp_dir

    if not os.path.isdir(temp_dir):
        print(f"Error: Temp directory not found: {temp_dir}")
        sys.exit(1)

    cover = args.cover
    if cover:
        if not os.path.isfile(cover):
            print(f"Error: Cover image not found: {cover}")
            sys.exit(1)
        cover = os.path.abspath(cover)

    export_name = None
    if args.export_name:
        try:
            export_name = _validate_export_name(args.export_name)
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)

    # Load config as base, CLI args override
    config = load_config(temp_dir)

    lang_code = args.lang or config.get('output_lang', 'zh')
    lang_cfg = get_lang_config(lang_code)
    print_cfg = layout.get_print_profile(
        args.print_profile,
        None if args.section_break is None else {'section_break': args.section_break})

    title = args.title or config.get('original_title', 'Translated Book')
    author = args.author or config.get('creator', 'Unknown Author')

    print(f"=== Merge and Build ===")
    print(f"Temp directory: {temp_dir}")
    print(f"Title: {title}")
    print(f"Author: {author}")
    print(f"Language: {lang_code} (attr: {lang_cfg['lang_attr']})")
    if args.pdf_engine == 'chromium':
        print(f"PDF: {args.print_profile} "
              f"({print_cfg['page_size']}, {layout.page_margin_css(print_cfg)}, "
              f"{print_cfg['base_font_size_pt']:g}pt)")

    # Step 4: Merge
    if args.build_only:
        if not os.path.exists(os.path.join(temp_dir, 'output.md')):
            print("Error: --build-only requires an existing output.md")
            sys.exit(1)
        print("=== Skipping merge (--build-only) ===")
    elif not merge_markdown_files(temp_dir):
        sys.exit(1)

    if not check_image_refs_resolve(temp_dir):
        sys.exit(1)

    # Step 5: Convert to HTML
    if not convert_md_to_html(temp_dir, title, lang_cfg, author,
                              allow_degraded=args.allow_degraded_html,
                              math_mode=args.math,
                              force=args.force_html or args.build_only,
                              print_cfg=print_cfg):
        sys.exit(1)

    # Step 6: Add TOC
    add_toc(temp_dir, lang_cfg)

    # Step 7: Generate formats
    all_formats_ok = generate_formats(temp_dir, lang_cfg['lang_attr'], cover=cover,
                                      title=title, author=author,
                                      docx_engine=args.docx_engine,
                                      pdf_engine=args.pdf_engine,
                                      print_cfg=print_cfg,
                                      lang_cfg=lang_cfg)

    if export_name:
        if all_formats_ok:
            aliases = export_named_aliases(temp_dir, export_name)
            if aliases:
                print("\nExport aliases:")
                for name in aliases:
                    print(f"  {name}")
        else:
            print("\nSkipping export aliases — some formats failed.")

    print("\n=== Build Complete ===")
    print(f"All outputs saved to: {temp_dir}")

    # The corpus census grows here, and only here. Made a step someone has to
    # remember, it would be skipped — and an advisor whose evidence stops
    # growing is back to guessing about the paper in front of it.
    try:
        import corpus_census
        corpus_census.record(temp_dir)
    except Exception as exc:                      # never fail a good build
        print(f"Corpus census: not recorded ({exc})")

    # And the referee, for the same reason and with better evidence against it:
    # its tally sat at ten runs while nine books were rebuilt and one was
    # re-translated, because calling it was left to whoever ran the build and
    # nobody did. An advisor you have to remember to consult is a document, not
    # an advisor. It speaks here whether or not anyone asked.
    # Collecting, judging and recording all live in `referee`. They were
    # inlined here as well, which put the history filter in three places, the
    # record sequence in two and the flag wording in two -- and the wording had
    # already drifted from the copy it was taken from. A fix that reaches one
    # copy and not the other is what K114 names, and this module has been
    # repaired for it twice.
    try:
        import referee
        for line in referee.judge_and_record(temp_dir, lang_code, 'REFEREE/'):
            print(line)
    except Exception as exc:                      # never fail a good build
        print(f"Referee: not recorded ({exc})")

    # An advisor nobody consults leaves no trace, so nobody — including the
    # agent meant to be calling it — can tell it is being skipped. Say it here.
    try:
        import advisors
        note = advisors.build_note()
        if note:
            print(note)
    except Exception as exc:                      # never fail a good build
        print(f"Advisors: status unavailable ({exc})")

    # List generated files
    for ext in ['book.html', 'book_doc.html', 'book.docx', 'book.epub', 'book.pdf']:
        filepath = os.path.join(temp_dir, ext)
        if os.path.exists(filepath):
            size = os.path.getsize(filepath)
            print(f"  {ext}: {size:,} bytes")

    # Cleanup intermediate artifacts if requested (skip if any format failed)
    if args.cleanup:
        if all_formats_ok:
            cleanup_intermediate_files(temp_dir)
        else:
            print("\nSkipping cleanup — some formats failed. Intermediate files kept for diagnosis/retry.")


def cleanup_intermediate_files(temp_dir):
    """Remove intermediate artifacts, keeping only final outputs."""
    print("\n=== Cleaning up intermediate files ===")

    removed = []

    # Remove chunk*.md and output_chunk*.md.
    # NOTE: chunk*.math.json sidecars are deliberately KEPT — output.md is
    # already restored, but a later --build-only re-merge would need them.
    for pattern in ['chunk*.md', 'output_chunk*.md']:
        for filepath in glob.glob(os.path.join(temp_dir, pattern)):
            os.remove(filepath)
            removed.append(os.path.basename(filepath))

    # Remove specific intermediate files
    for name in ['input.html', 'input.md', 'output.html']:
        filepath = os.path.join(temp_dir, name)
        if os.path.exists(filepath):
            os.remove(filepath)
            removed.append(name)

    if removed:
        print(f"Removed {len(removed)} intermediate file(s):")
        # Summarize chunk files instead of listing each one
        chunk_files = [f for f in removed if 'chunk' in f]
        other_files = [f for f in removed if 'chunk' not in f]
        if chunk_files:
            print(f"  {len(chunk_files)} chunk files (chunk*.md, output_chunk*.md)")
        for f in other_files:
            print(f"  {f}")
    else:
        print("No intermediate files to remove.")


if __name__ == "__main__":
    main()

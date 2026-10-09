# -*- coding: utf-8 -*-
r"""Figures, floats, labels and the numbers cross-references point at.

Reads the paper's float order, counters and document class from flat.tex,
wraps figures with their captions, and turns `\ref`, `\eqref` and
citations into the numbers the original prints.

Moved out of merge_and_build.py, which re-exports every name here that the
build or a test reaches for.
"""

import os
import re

import latex_rows
import layout

from build_common import (
    _CAPTION_CMD_RE, _balanced_group, _scan_image_refs, strip_tex_comments,
)

_DEFAULT_LANG_CONFIG = layout.DEFAULT_LANG_CONFIG


# =============================================================================
# Figure captions
# =============================================================================
#
# The arXiv path emits a bare image followed by a bold paragraph, which prints
# as ordinary body text -- there is nothing to tell a reader where the caption
# stops and the argument resumes. Wrapping the pair in <figure>/<figcaption>
# gives the print sheet something to style, and the float order in flat.tex
# gives the number.

# [ \t]*$ rather than \s*$: a trailing \s* swallows the blank lines
# after the image, and then the caption-gap guard below has nothing left to
# measure -- an uncaptioned figure could reach forward and take the next
# paragraph as its caption.
# The trailing raw span is a spacing directive the source put on the image's
# own line -- `` `{-2em}`{=latex} ``. Requiring the line to end at the image
# meant a figure carrying one was never recognised as a figure AT ALL: no
# number, no printed label, no anchor, and its caption left behind as loose
# prose. CafeQ's figure 1 went that way while three cross-references kept
# pointing at it. Only a brace-wrapped span is allowed in, so a raw span
# holding real content cannot be swallowed here.
_FIG_IMAGE_RE = re.compile(
    r'^!\[([^\]]*)\]\((images/fig(\d+)[^)]*)\)(?:\{[^}]*\})?'
    r'(?:[ \t]*`\{[^`\n]*\}`\{=[a-z]+\})?[ \t]*$',
    re.MULTILINE)

# How wide to draw one panel of a multi-panel float, by panel count.
#
# A panel drawn at full text width is about 125mm tall against a 257mm text
# block, so two cannot share a page: SINQ printed three panels of one figure
# on three pages, and seven of its thirty-six pages held a single picture and
# fourteen characters of caption.
#
# Each width is the largest that still lets the whole float sit on one page,
# from panels x (0.125 x width + 15mm of caption and margin) <= 257mm. Beyond
# four panels no width both fits and stays legible, so they fill a page at a
# time; 38% of the 174mm text width is 66mm, still wider than the ~40mm these
# same panels get in the printed original.
_PANEL_WIDTH = {2: 80, 3: 55}
_PANEL_WIDTH_MANY = 38


def _figure_number_from_path(path, index_fallback):
    m = re.search(r'fig(\d+)', path)
    return int(m.group(1)) if m else index_fallback


# A vertical-space directive the source parked between an image and its
# caption: `{-2em}` on its own, or `` `{-2em}`{=latex} `` once pandoc has
# wrapped it as a raw span. It holds no words, so it is not a caption -- but
# it sits exactly where the caption would be, and the blank line after it
# ended the search. CafeQ's figure 1 lost its number, its printed label and
# the anchor three cross-references pointed at, for that alone: the same
# figure in the same paper kept all three in the previous build, where the
# directive happened to arrive without a blank line after it.
_SPACING_SPAN_RE = re.compile(
    r'^(?:`(?P<raw>[^`\n]*)`\{=[a-z]+\}|(?P<bare>\{[^{}\n]*\}))[ \t]*(?=\n|$)')
_SPACING_BODY_RE = re.compile(
    r'^\{?\s*(?:\\(?:vspace|hspace|vskip|hskip)\*?)?\s*'
    r'[-+]?\d*\.?\d*\s*(?:em|ex|pt|cm|mm|in|bp|sp|mu|\\baselineskip)?\s*\}?$')


def _spacing_only_prefix(tail):
    """The leading run of tail that is pure spacing, or '' if there is none."""
    m = _SPACING_SPAN_RE.match(tail)
    if not m:
        return ''
    body = m.group('raw') if m.group('raw') is not None else m.group('bare')
    if not _SPACING_BODY_RE.match((body or '').strip()):
        return ''
    return m.group(0)


_GRAPHIC_RE = re.compile(
    r'\\includegraphics\s*(?:\[([^\]]*)\])?\s*\{([^}]*)\}')


def _graphic_stem(path, options=''):
    """'figures/corr_alignment_Qwen3-1.7B.pdf' -> 'corralignmentqwen317b'.

    A page beyond the first joins the stem, because the backend gives that
    panel its own file. CafeQ draws two panels of one figure from page 1 and
    page 4 of the same PDF; keyed on the path alone they collapse into one
    panel and the second image is left unclaimed.
    """
    stem = os.path.basename(path).rsplit('.', 1)[0]
    page = re.search(r'\bpage\s*=\s*(\d+)', options or '')
    if page and page.group(1) != '1':
        stem += '_p' + page.group(1)
    return re.sub(r'[^0-9a-z]', '', stem.lower())


_FLOAT_ENV_RE = re.compile(
    r'\\begin\{((?:SC|wrap|sideways|long|floating)?(?:figure|table)\*?)\}'
    r'(.*?)\\end\{\1\}', re.DOTALL)

# Figures the paper DRAWS rather than includes. There is no image file for one
# anywhere in the source, so no stage here can render it; its absence from the
# book is a limitation to report, not a fault to stop the build over.
_CODE_DRAWN_FIGURES = {'tikzpicture', 'pgfpicture', 'pspicture', 'picture'}

_PROOF_ENV_RE = re.compile(
    r'^[ \t]*\\begin\{proof\}(?:\s*\[[^\]]*\])?[ \t]*$\n?'
    r'|^[ \t]*\\end\{proof\}[ \t]*$\n?', re.MULTILINE)
_LIST_ENV_RE = re.compile(
    r'^[ \t]*\\begin\{(enumerate|itemize)\}(?:\s*\[[^\]]*\])?[ \t]*$\n'
    r'(.*?)'
    r'^[ \t]*\\end\{\1\}[ \t]*$\n?', re.MULTILINE | re.DOTALL)
_ITEM_RE = re.compile(r'^[ \t]*\\item[ \t]*', re.MULTILINE)
_LISTING_ENV_RE = re.compile(
    r'^[ \t]*\\begin\{(lstlisting|verbatim|minted)\}'
    r'(?:\s*\[[^\]]*\])?(?:\s*\{[^{}]*\})?[ \t]*$\n'
    r'(.*?)'
    r'^[ \t]*\\end\{\1\}[ \t]*$\n?', re.MULTILINE | re.DOTALL)


def unwrap_prose_environments(md_text):
    r"""Turn leftover LaTeX prose environments into markdown. (text, count).

    pandoc's markdown reader takes `\begin{env}…\end{env}` as ONE raw LaTeX
    block and the HTML writer drops it whole, without a word. Neural ODE's
    appendix lost a proof, a Python listing, a numbered list and a figure that
    way — all of them already translated.

    They are not exotic: a proof is paragraphs, a list is a list, a listing is
    a code block. Written as markdown they render everywhere, DOCX included,
    which raw LaTeX never does.
    """
    count = [0]

    def drop_wrapper(m):
        count[0] += 1
        return ''

    def as_list(m):
        count[0] += 1
        kind, body = m.group(1), m.group(2)
        marker = '1. ' if kind == 'enumerate' else '- '
        return '\n' + _ITEM_RE.sub(marker, body).strip('\n') + '\n\n'

    def as_code(m):
        count[0] += 1
        return '\n```\n' + m.group(2).strip('\n') + '\n```\n\n'

    md_text = _LISTING_ENV_RE.sub(as_code, md_text)
    md_text = _LIST_ENV_RE.sub(as_list, md_text)
    # The proof's own wrapper only; its paragraphs stay where they are.
    md_text = _PROOF_ENV_RE.sub(drop_wrapper, md_text)
    return md_text, count[0]


_THE_COUNTER_RE = re.compile(
    r'\\(?:re)?newcommand\s*\{?\s*\\the(figure|table)\s*\}?\s*'
    r'(\{(?:[^{}]|\{[^{}]*\})*\})')
_SETCOUNTER_RE = re.compile(r'\\setcounter\s*\{(figure|table)\}\s*\{(-?\d+)\}')


def counter_events(tex):
    r"""Explicit counter declarations, in source order.

    A paper can letter its appendix floats by hand instead of scoping the
    counter to a section. VLA-Adapter gives each of its nine appendix
    sections a `\renewcommand{\thefigure}{A\arabic{figure}}` and a
    `\setcounter{figure}{0}`, lettering A through I, so what it prints as
    Figure A1 is this counter's ninth figure. Numbering straight through
    sent seventeen cross-references to the wrong float, and `source_probe`
    caught it by reading the number off the original PDF.

    Returns [(position, kind, 'prefix'|'set', value)]. A redefinition whose
    prefix is itself a command is skipped rather than guessed at: the point
    is to read what the source declares, not to evaluate TeX.
    """
    events = []
    for m in _THE_COUNTER_RE.finditer(tex):
        kind, body = m.group(1), m.group(2)
        inner = re.search(r'\\arabic\s*\{\s*' + kind + r'\s*\}', body)
        if not inner:
            continue          # not `<prefix>\arabic{kind}`; leave it alone
        prefix = body[1:inner.start()].strip()
        if '\\' in prefix:
            continue          # the prefix is a command; do not evaluate it
        events.append((m.start(), kind, 'prefix', prefix))
    for m in _SETCOUNTER_RE.finditer(tex):
        events.append((m.start(), m.group(1), 'set', int(m.group(2))))
    events.sort(key=lambda e: e[0])
    return events


def float_units(tex):
    """One entry per figure/table number the paper actually issues.

    Counting float ENVIRONMENTS is the obvious reading and it is wrong twice
    over. LaTeX numbers a float when \\caption runs, so a float can be worth
    two numbers or none:

      * AlphaQ puts two `minipage`s inside one `table*`, each with its own
        \\caption. That is two tables, and reading it as one numbered every
        later table two too low.
      * SINQ leaves two figures commented out. Those number nothing, and
        counting them numbered every figure after the first one too high.

    Both shipped, because the caption side of the pipeline had stripped
    comments and the cross-reference side had not: the caption under the plot
    read "그림 6" while the sentence pointing at it read "그림 7".

    Pass comment-stripped `tex`. Returns [{'kind','number','start','stop',
    'labels'}] where start..stop is the slice of the float owned by that
    caption, and `number` is None for a float that has no caption at all.
    """
    units, counters = [], {'figure': 0, 'table': 0}
    # A float counter can be scoped to the section, in which case the paper
    # prints `Table 3.1` and restarts at every section. This function sees
    # floats but not sections, so the boundaries have to be walked alongside
    # them; without it Shor's four table and figure references named numbers
    # the paper does not print.
    parents = read_counter_parents(tex)
    scoped = {k for k in ('figure', 'table') if parents.get(k) == 'section'}
    # A class can print a float counter in Roman without saying so anywhere
    # in the source. The value stays whatever the counter produces -- a
    # string here, an int below -- and both already flow through: a
    # section-scoped counter has produced `3.1` for a long time, and the
    # caption badge formats with `%s` for exactly that reason.
    float_styles = read_class_conventions(tex).get('float') or {}
    sections = []
    if scoped:
        depth0 = 0
        in_appendix = False
        # The appendix letters this walk too. A paper that scopes its table
        # counter to the section AND has an appendix prints Table A.1; this
        # said Table 8.1. The FIFTH place to need the same fact, after
        # `build_label_index`, the class table, `flat_equation_numbers` and
        # `read_pdf_section_prefixes` -- which is why a lint now refuses a
        # section walk that cannot see it.
        walker = re.compile(r'\\(?:sub)*section(\*?)\s*\{'
                            r'|\\(appendix(?![a-zA-Z])'
                            r'|begin\s*\{append(?:ix|ices)\})')
        for m in walker.finditer(tex):
            if m.group(2):
                in_appendix, depth0 = True, 0
                continue
            if m.group(1):                 # starred: numbers nothing
                continue
            if m.group(0).count('sub') == 0:
                depth0 += 1
                sections.append((m.start(),
                                 chr(ord('A') + depth0 - 1) if in_appendix
                                 else str(depth0)))
    section_head, next_section = '', 0
    # The other way a paper letters its floats: by declaring it, rather than
    # by scoping the counter to a section. Walked alongside the floats for the
    # same reason the sections are.
    events, next_event = counter_events(tex), 0
    prefixes = {'figure': '', 'table': ''}

    for float_match in _FLOAT_ENV_RE.finditer(tex):
        while next_section < len(sections) \
                and sections[next_section][0] < float_match.start():
            section_head = sections[next_section][1]
            for name in scoped:
                counters[name] = 0
            next_section += 1
        while next_event < len(events) \
                and events[next_event][0] < float_match.start():
            _at, event_kind, action, value = events[next_event]
            if action == 'prefix':
                prefixes[event_kind] = value
            else:
                counters[event_kind] = value
            next_event += 1
        kind = 'table' if 'table' in float_match.group(1).lower() else 'figure'
        body, base = float_match.group(2), float_match.start(2)
        panels = _panel_spans(body)
        # A \caption inside a subfigure is a subcaption; it letters the panel
        # rather than numbering the float.
        nested = _nested_counter_spans(body)
        captions = [m for m in _CAPTION_CMD_RE.finditer(body)
                    if not any(s <= m.start() < e for s, e, _t in panels)
                    and not any(s <= m.start() < e for s, e in nested)]
        # Split at caption STARTS, which is the one rule that survives both
        # layouts in the wild: content-then-caption and caption-then-content.
        bounds = [0] + [m.start() for m in captions[1:]] + [len(body)]
        for index in range(max(1, len(captions))):
            if captions:
                counters[kind] += 1
            region = tex[base + bounds[index]:base + bounds[index + 1]]
            if not captions:
                number = None                 # a float that numbers nothing
            elif kind in scoped:
                number = _counter_label(kind, counters[kind], parents,
                                        section_head)
            elif prefixes[kind]:
                # The paper declared the prefix itself: `A\arabic{figure}`.
                number = '%s%d' % (prefixes[kind], counters[kind])
            elif float_styles.get(kind) == 'Roman':
                number = roman_numeral(counters[kind])
            else:
                number = counters[kind]
            units.append({
                'kind': kind,
                'number': number,
                'start': base + bounds[index],
                'stop': base + bounds[index + 1],
                'labels': [l.strip() for l in
                           re.findall(r'\\label\{([^}]+)\}', region)],
            })
    return units


def read_float_units(temp_dir):
    """float_units() over a temp dir's flat.tex, or [] when there is none."""
    flat = os.path.join(temp_dir or '', 'flat.tex')
    if not temp_dir or not os.path.exists(flat):
        return []
    try:
        with open(flat, 'r', encoding='utf-8', errors='replace') as fh:
            return float_units(strip_tex_comments(fh.read()))
    except OSError:
        return []


def figure_panels(temp_dir):
    """{image filename: {'float': 2, 'letter': 'b', 'panels': 3, 'caption': True}}

    A float with three \\includegraphics is ONE figure with three panels, not
    three figures. Panels are matched to extracted files by name: SINQ has 17
    \\includegraphics but 13 image files, because tikz pictures and unresolved
    graphics leave nothing behind, so counting positions drifts after the
    first one that produced no file.

    Returns None when flat.tex or images/ is missing, meaning "fall back".
    """
    flat = os.path.join(temp_dir or '', 'flat.tex')
    images_dir = os.path.join(temp_dir or '', 'images')
    if not temp_dir or not os.path.exists(flat) or not os.path.isdir(images_dir):
        return None
    try:
        with open(flat, 'r', encoding='utf-8', errors='replace') as fh:
            tex = strip_tex_comments(fh.read())
        files = sorted(os.listdir(images_dir))
    except OSError:
        return None

    by_stem = {}
    for name in files:
        # extracted as fig0003_random_walk_hyp.png
        body = re.sub(r'^fig\d+_', '', name).rsplit('.', 1)[0]
        by_stem.setdefault(re.sub(r'[^0-9a-z]', '', body.lower()), name)

    out = {}
    for unit in float_units(tex):
        if unit['kind'] != 'figure':
            continue
        resolved = []
        for options, graphic in _GRAPHIC_RE.findall(tex[unit['start']:unit['stop']]):
            name = by_stem.get(_graphic_stem(graphic, options))
            # The same graphic can be included twice in one float
            # (an overlay, a repeated panel); it is still one panel.
            if name and name not in out and name not in resolved:
                resolved.append(name)
        for index, name in enumerate(resolved):
            out[name] = {'float': unit['number'],
                         'letter': chr(ord('a') + index) if len(resolved) > 1 else None,
                         'panels': len(resolved),
                         'caption': (unit['number'] is not None
                                     and index == len(resolved) - 1)}
    return out or None


def figures_with_captions(temp_dir):
    """{figure_number} for the floats that carry a \\caption in the source.

    Most LaTeX captions open with \\textbf{...} and so arrive as
    `**Lead-in.** rest`, which is easy to spot -- but a caption that simply
    lacks bold is still a caption, and figure 10 of a real paper was losing its
    caption for exactly that reason. Asking flat.tex which floats HAVE one
    turns a guess into a lookup.

    Returns None when flat.tex is absent, meaning "fall back to the heuristic".
    """
    flat = os.path.join(temp_dir or '', 'flat.tex')
    if not temp_dir or not os.path.exists(flat):
        return None
    return {unit['number'] for unit in read_float_units(temp_dir)
            if unit['kind'] == 'figure' and unit['number'] is not None}


_INCLUDEGRAPHICS_RE = re.compile(
    r'\\includegraphics\s*\[([^\]]*)\]\s*\{([^{}]*)\}')
_TRIM_OPT_RE = re.compile(r'trim\s*=\s*\{([^}]*)\}|trim\s*=\s*([^,\]]+)')
_LEN_RE = re.compile(r'(-?[\d.]+)\s*(cm|mm|in|pt|bp|px)?')
_PT_PER = {'cm': 28.3464567, 'mm': 2.83464567, 'in': 72.0,
           'pt': 1.0, 'bp': 1.0, 'px': 1.0, None: 1.0}


def _trim_of(options):
    r"""The four `trim=` lengths in points, LaTeX order: left bottom right top."""
    m = _TRIM_OPT_RE.search(options)
    if not m or 'clip' not in options:
        return None
    parts = (m.group(1) or m.group(2) or '').replace(',', ' ').split()
    if len(parts) != 4:
        return None
    out = []
    for part in parts:
        hit = _LEN_RE.match(part.strip())
        if not hit:
            return None
        out.append(float(hit.group(1)) * _PT_PER.get(hit.group(2), 1.0))
    return out


def apply_graphics_trim(md_text, temp_dir):
    r"""Crop each image the way its `\includegraphics[trim=...,clip]` asked.

    Returns (text, cropped). The extracted PNG is the whole source page, so a
    figure the paper crops arrives with whatever the author cropped OFF still
    on it: CafeQ's figure 1 carries the plot's own debug title band --
    `dperf ~ qerr; m=leaderboard_all_nodrop_mean; n=4; q=-1` -- which the
    original hides. The reader sees something the paper does not show.
    """
    try:
        import fitz
    except ImportError:
        return md_text, 0
    flat_path = os.path.join(temp_dir or '', 'flat.tex')
    if not os.path.isfile(flat_path):
        return md_text, 0
    with open(flat_path, encoding='utf-8', errors='replace') as fh:
        flat = strip_tex_comments(fh.read())

    wanted = {}
    for m in _INCLUDEGRAPHICS_RE.finditer(flat):
        trim = _trim_of(m.group(1))
        if not trim:
            continue
        page = re.search(r'page\s*=\s*(\d+)', m.group(1))
        stem = os.path.splitext(os.path.basename(m.group(2)))[0]
        wanted[(stem, int(page.group(1)) if page else 1)] = (trim, m.group(2))

    if not wanted:
        return md_text, 0

    html_srcs, md_srcs, _ = _scan_image_refs(md_text)
    cropped = 0
    for ref in sorted(set(html_srcs) | set(md_srcs)):
        name = os.path.basename(ref)
        hit = re.match(r'fig\d+_(.+?)(?:_p(\d+))?\.[a-z]+$', name)
        if not hit:
            continue
        key = (hit.group(1), int(hit.group(2) or 1))
        if key not in wanted:
            continue
        trim, source = wanted[key]
        image = os.path.normpath(os.path.join(temp_dir, ref))
        origin = _source_file(temp_dir, source)
        if not os.path.isfile(image) or not origin:
            continue
        out_ref = '%s_trim%s' % os.path.splitext(ref)
        out_path = os.path.normpath(os.path.join(temp_dir, out_ref))
        # Re-render the cropped region from the source rather than cutting
        # the PNG: same resolution, and no dependence on which Pixmap
        # constructors this build of PyMuPDF happens to offer.
        if not os.path.isfile(out_path):
            try:
                doc = fitz.open(origin)
                page = doc[min(key[1], doc.page_count) - 1]
                rect = page.rect
                scale = fitz.Pixmap(image).width / rect.width
                left, bottom, right, top = trim
                clip = fitz.Rect(rect.x0 + left, rect.y0 + top,
                                 rect.x1 - right, rect.y1 - bottom)
                if clip.is_empty or clip.width < 2 or clip.height < 2:
                    doc.close()
                    continue
                page.get_pixmap(matrix=fitz.Matrix(scale, scale),
                                clip=clip).save(out_path)
                doc.close()
            except Exception as exc:
                print(f"WARNING: could not crop {ref}: {exc}")
                continue
        md_text = md_text.replace(ref, out_ref)
        cropped += 1
    return md_text, cropped


def _source_file(temp_dir, source):
    """The extracted-source file an `\\includegraphics` path points at."""
    stem = os.path.splitext(os.path.basename(source))[0]
    for root, _dirs, files in os.walk(os.path.join(temp_dir, 'arxiv_src')):
        for name in files:
            if os.path.splitext(name)[0] == stem:
                return os.path.join(root, name)
    return None


def _figure_caption_md(label, body):
    r"""`**label** body`, safe to sit inside an image's alt text."""
    body = (body or '').strip()
    caption = f'**{label}** {body}'.strip() if body else f'**{label}**'
    # Square brackets would close the alt-text span early. Escaping is safe
    # here: normalize_latex_leftovers has already run, so nothing will re-read
    # `\[` as display math afterwards.
    caption = caption.replace('[', r'\[').replace(']', r'\]')
    # One line: implicit_figures needs the image alone in its paragraph, and a
    # newline inside the alt text would end it.
    return re.sub(r'\s*\n\s*', ' ', caption)


def _last_of_float(matches, n, panels):
    """Is the n-th match (1-based) the last panel of its float?"""
    def float_of(match):
        panel = (panels or {}).get(os.path.basename(match.group(2)))
        return panel['float'] if panel and panel['panels'] > 1 else None

    if n >= len(matches):
        return True
    return float_of(matches[n - 1]) != float_of(matches[n])


def format_figure_blocks(md_text, lang_cfg=None, temp_dir=None):
    """Fold each image + caption paragraph into one markdown image.

    Emitted as MARKDOWN, not raw HTML. pandoc's `implicit_figures` turns a
    paragraph holding nothing but an image into <figure>/<figcaption> natively,
    and the alt text keeps going through the markdown and math readers on the
    way. Hand-built HTML looked equivalent and was not: raw HTML is dropped
    entirely on the DOCX path (every figure vanished, 5.4MB -> 25KB) and skips
    the math reader, so `$...$` inside a caption printed literally.

    Returns (text, count).
    """
    lang_cfg = lang_cfg or {}
    fig_label = lang_cfg.get('figure_label', 'Figure')
    captioned = figures_with_captions(temp_dir)
    panels = figure_panels(temp_dir)
    matches = list(_FIG_IMAGE_RE.finditer(md_text))
    if not matches:
        return md_text, 0

    pieces, cursor, count = [], 0, 0
    open_group, group_caption = False, ''
    for n, m in enumerate(matches, 1):
        if m.start() < cursor:
            continue
        alt, path = m.group(1), m.group(2)
        panel = (panels or {}).get(os.path.basename(path))
        if panel:
            number, letter = panel['float'], panel['letter']
            wants_caption = panel['caption']
        else:
            number, letter = _figure_number_from_path(path, n), None
            wants_caption = None          # decided below, as before

        # The caption is the paragraph after the image. Skip whatever gap is
        # there, but only across a blank line or two, so an uncaptioned figure
        # cannot reach forward and steal the next section's opening sentence.
        rest = md_text[m.end():]
        gap = re.match(r'\s*', rest).group(0)
        caption_md, sub_md, end = '', '', m.end()
        # the image line's own newline, plus at most three blank lines
        if gap.count('\n') <= 4:
            tail = rest[len(gap):]
            # Step over a spacing directive standing between the image and
            # its caption, and over the blank line that follows it. Without
            # this the directive IS the caption the search finds, and the
            # real one is left behind as ordinary prose.
            spacing = _spacing_only_prefix(tail)
            if spacing:
                lead = re.match(r'\s*', tail[len(spacing):]).group(0)
                if gap.count('\n') + lead.count('\n') <= 4:
                    gap += spacing + lead
                    tail = tail[len(spacing) + len(lead):]
            # Prefer the source's own answer; the bold lead-in is only a
            # fallback for builds with no flat.tex to consult.
            if wants_caption is None:
                take = (number in captioned) if captioned is not None \
                    else tail.startswith('**')
            else:
                take = wants_caption
            # The next paragraph is the next panel of this same float, never a
            # caption. Folding it in cost two of SINQ's thirteen images.
            if _FIG_IMAGE_RE.match(tail):
                take = False
            # A panel of a multi-panel float can carry its own \subcaption,
            # which arrives as a short bold paragraph. It belongs to this
            # panel whether or not this panel also carries the float caption.
            if panel and panel['panels'] > 1 and not _FIG_IMAGE_RE.match(tail):
                first = re.match(r'\*\*[^\n*][^\n]{0,78}?\*\*[ \t]*(?=\n|$)', tail)
                if first:
                    sub_md = first.group(0).strip()
                    consumed = len(gap) + len(sub_md)
                    end = m.end() + consumed
                    tail = tail[len(sub_md):]
                    gap = re.match(r'\s*', tail).group(0)
                    tail = tail[len(gap):]
                    if take and _FIG_IMAGE_RE.match(tail):
                        take = False
            if take and tail.strip():
                stop = re.search(r'\n\s*\n', tail)
                caption_md = (tail[:stop.start()] if stop else tail).strip()
                end = (end if sub_md else m.end()) + len(gap) + len(caption_md)

        if number is None:
            # The float carries no \caption, so the paper never numbered it.
            # Printing "Figure N" here would invent a number the reader cannot
            # find and push every later figure out of step.
            pieces.append(md_text[cursor:m.start()])
            pieces.append(f'\n\n![{alt}]({path})\n\n')
            cursor = m.end()
            count += 1
            continue

        if letter and not caption_md:
            # A panel that does not carry the float's caption says only which
            # panel it is. Numbering every one of them printed
            # `그림 6 (Fig. 6)` four times over what the paper prints once,
            # and a reader counting figures found four where there is one.
            label = f'({letter})'
        else:
            label = f'{fig_label} {number}'
            if fig_label != 'Figure':
                label += f' (Fig. {number})'
            if letter:
                # The caption refers to its panels as (a)/(b)/(c) -- and
                # \subref resolves to those letters -- so the panel carrying
                # the caption still has to say which one it is.
                label += f' ({letter})'
        # The label is bold so the print sheet can pick it out with
        # `figcaption strong`; the caption keeps whatever markdown it had.
        grouped = bool(panel and panel['panels'] > 1)
        if grouped and caption_md:
            # The float's caption belongs under the whole float, not under
            # whichever panel happened to carry it in the source. SINQ's
            # figure 2 explained panel (a) in a caption printed beneath panel
            # (c), a page later; the panel keeps only its own subcaption.
            group_caption = _figure_caption_md(
                f'{fig_label} {number}'
                + (f' (Fig. {number})' if fig_label != 'Figure' else ''),
                caption_md)
            caption = _figure_caption_md(f'({letter})' if letter else label,
                                         sub_md)
        else:
            caption = _figure_caption_md(
                label, ' '.join(p for p in (sub_md, caption_md) if p))

        # No per-image width on a panel: the group's row divides itself
        # between them. An inline `width:33%` here means 33% of the panel's
        # OWN box, which left each panel on a line of its own and spread one
        # float down a whole page.
        attr = ''
        pieces.append(md_text[cursor:m.start()])
        if grouped and not open_group:
            pieces.append('\n\n::: figuregroup\n')
            open_group = True
        pieces.append(f'\n\n![{caption}]({path}){attr}\n\n')
        if open_group and (not grouped or _last_of_float(matches, n, panels)):
            if group_caption:
                pieces.append('\n%s\n' % group_caption)
                group_caption = ''
            pieces.append('\n:::\n\n')
            open_group = False
        cursor = end
        count += 1
    pieces.append(md_text[cursor:])
    return ''.join(pieces), count


# =============================================================================
# Citations and cross-references
# =============================================================================
#
# Two kinds of marker survive the arXiv path and used to print verbatim:
#
#   [@brohan2023rt-2]   pandoc citation syntax. The paper ships a precompiled
#                       main.bbl rather than a .bib, so there is nothing for
#                       --citeproc to read -- but the inlined \bibitem list IS
#                       the numbering, so keys resolve against it exactly.
#   (fig:compare)       what \ref{fig:compare} degrades to. flat.tex still has
#                       every \label in float order, which gives the real
#                       figure and table numbers with no guessing.
#
# Both are resolved on the merged markdown, so an already-translated book can
# be fixed by rebuilding rather than re-translating.

_CITE_RE = re.compile(r'\[(@[^\]]+)\]')
_CITE_KEY_RE = re.compile(r'@([A-Za-z0-9_:\-\.]+)')
# The reference word that sits in front of the number. \ref leaves the one the
# author typed ("See Tab.~\ref{tab:x}"); \cref generates it, so pandoc emits
# nothing and the sentence arrives as "in ( (eq:y))". Absorbing it either way
# is what stops the output reading "See Tab. 표 16".
_XREF_LEAD = (r'(?:\b(?:Figs?|Figures?|Tabs?|Tables?|Secs?|Sections?|Eqs?|Eqn|'
              r'Equations?|App|Appendix|Appendices|Algs?|Algorithms?|Lemmas?|'
              r'Theorems?|Defs?|Definitions?)\.?[ \t\u00a0~]*)?')
# [^()] matters: without it 'increase (Sec.\u00a0(sec:method))' lets the
# leading \( swallow the outer bracket, 'Sec' is taken for the kind and the
# label is captured as '(sec:method' -- which resolves to nothing.
_XREF_BODY = (
    r'\(\s*(fig|figure|tab|table|eq|eqn|equation|sec|section|subsec|'
    r'app|appendix|alg|algorithm|thm|theorem|lem|lemma|def|definition|'
    r'prop|proposition|cor|corollary)[:.]\s*([^()\s]+?)\s*\)')
_XREF_RE = re.compile(_XREF_LEAD + _XREF_BODY, re.IGNORECASE)

# `\Cref{tab:a,tab:b}` is ONE reference naming two floats, and cleveref prints
# both numbers. pandoc hands the whole list over inside one bracket, so the
# body above captures `a,tab:b` as the name and nothing resolves: Looped flows
# printed `(tab:sde_ablation,tab:multi_solution_sde_ablation)` to its readers,
# and five more pairs like it across four pages.
#
# The first label arrives with its kind already taken off by the pattern; the
# ones after it carry their own, and need not agree -- `\cref{fig:a,tab:b}` is
# ordinary usage. A label may itself contain a colon, so only the first one
# separates the kind from the name.
_XREF_PART_RE = re.compile(r'^([A-Za-z]+)[:.](.+)$')


def _xref_parts(kind, rest):
    """[(kind, name), ...] for one reference, which may name several labels."""
    out = []
    for piece in (rest or '').split(','):
        piece = piece.strip()
        if not piece:
            continue
        head = _XREF_PART_RE.match(piece) if out else None
        out.append((head.group(1).lower(), head.group(2)) if head
                   else (kind, piece))
    return out


def template_affixes(formats, words):
    r"""The literal words a reference template puts around the number.

    Chinese writes a section reference `第3.2节`, so `ref_formats` carries
    `第{number}{label}`. A translator writes that same 第 in front of the
    placeholder and that same 节 after it. Neither was absorbed: 第 is not a
    label word at all, and the closing 节 is only reachable after the
    substitution, where `(?!\w)` can never hold because the next character in
    Chinese is another ideograph. DeeR-VLA printed `第 第3.2节 节在任意...`.

    Only non-ASCII affixes are returned. The equation template is
    `{label} ({number})`, whose literal head is ` (` -- punctuation, not a
    word a translator repeats, and absorbing a bracket would eat the
    reference's own parenthesis.
    """
    lead, trail = [], []
    for slot, template in (formats or {}).items():
        head, _sep, after = template.partition('{number}')
        opener = head.replace('{label}', ' ').strip()
        if opener and not opener.isascii():
            lead.append(opener)
        label = (words or {}).get(slot)
        if label and '{label}' in after and not label.isascii():
            trail.append(label)
        closer = after.replace('{label}', ' ').strip()
        if closer and not closer.isascii():
            trail.append(closer)
    return lead, trail


def _xref_regex(labels, trailing=()):
    """The reference pattern, also absorbing the target language's own words.

    A translator writes "표 (tab:main)에서", not "Tab. (tab:main)". Absorbing
    only the English word left the Korean one standing beside the label this
    emits -- "표 표 12". The lookbehind keeps compounds intact: the word has to
    start where it stands, so "수식 (eq:x)" is not split at "식".

    `trailing` is for a language whose reference form CLOSES with a word.
    Cleaning that up after the substitution means guessing, because 节 also
    opens 节点 and a script with no word boundaries cannot tell a duplicate
    from the next word. Here the placeholder's own `)` bounds it, so there is
    nothing to guess. It is captured rather than dropped: `xref_sub` puts it
    back unless the resolved reference already ends in it.
    """
    words = sorted({w.strip() for w in labels if w and w.strip()},
                   key=len, reverse=True)
    close = sorted({w.strip() for w in trailing if w and w.strip()},
                   key=len, reverse=True)
    tail = ''
    if close:
        tail = (r'(?:[ \t\xa0~]*(%s))?'
                % '|'.join(re.escape(w) for w in close))
    if not words:
        if not tail:
            return _XREF_RE
        return re.compile(_XREF_LEAD + _XREF_BODY + tail, re.IGNORECASE)
    native = (r'(?:(?<!\w)(?:%s)[ \t\u00a0~]*)?'
              % '|'.join(re.escape(w) for w in words))
    return re.compile(_XREF_LEAD + native + _XREF_BODY + tail, re.IGNORECASE)

# reference kind -> (which map holds the number, which label word to use)
_XREF_KINDS = {
    'fig': ('float', 'figure'), 'figure': ('float', 'figure'),
    'tab': ('float', 'table'), 'table': ('float', 'table'),
    'eq': ('label', 'equation'), 'eqn': ('label', 'equation'),
    'equation': ('label', 'equation'),
    'sec': ('label', 'section'), 'section': ('label', 'section'),
    'subsec': ('label', 'section'),
    'app': ('label', 'appendix'), 'appendix': ('label', 'appendix'),
    'alg': ('label', 'algorithm'), 'algorithm': ('label', 'algorithm'),
    'thm': ('label', 'theorem'), 'theorem': ('label', 'theorem'),
    'lem': ('label', 'theorem'), 'lemma': ('label', 'theorem'),
    'def': ('label', 'theorem'), 'definition': ('label', 'theorem'),
    'prop': ('label', 'theorem'), 'proposition': ('label', 'theorem'),
    'cor': ('label', 'theorem'), 'corollary': ('label', 'theorem'),
}

_XREF_WORDS = {'figure': 'Figure', 'table': 'Table', 'equation': 'Equation',
               'section': 'Section', 'appendix': 'Appendix',
               'algorithm': 'Algorithm', 'theorem': 'Theorem'}

# Korean puts the section marker after the number ("4.1절"); everything else
# reads as a prefix in every language here.
_XREF_FORMATS = {'equation': '{label} ({number})'}


def build_bibitem_numbers(md_text):
    r"""{citekey: number} from the inlined \bibitem list, in its own order.

    The optional label is not optional in practice: natbib and plainnat write
    `\bibitem[Adleman 1994]{Adle}`, and requiring the bare form found 0 keys in
    a file holding 75 of them — so all 30 of Shor's citations resolved to
    nothing and `[@Knut]` printed on the page. `_BIBITEM_LABEL_RE` elsewhere in
    this module already accepts the labelled form; this reader had simply never
    been told (K114 is the same shape: learned in one place, not the other).
    """
    keys = re.findall(r'\\bibitem\s*(?:\[[^\]]*\])?\s*\{([^{}]+)\}', md_text)
    return {k.strip(): i + 1 for i, k in enumerate(keys)}


def build_float_numbers(temp_dir):
    """{'fig:compare': 1, 'tab:main result': 2, ...} parsed from flat.tex.

    LaTeX numbers figures and tables in the order their captions appear,
    counting `figure` and `figure*` together, so that is what float_units
    reproduces. A float is not always \\begin{figure}: CafeQ opens with an
    SCfigure from the sidecap package, which LaTeX counts as Figure 1 --
    missing it shifted every later figure down by one, so the caption of
    Figure 2 read "그림 1".

    Returns {} when flat.tex is absent (the calibre backend).
    """
    numbers = {}
    for unit in read_float_units(temp_dir):
        if unit['number'] is None:
            continue
        for label in unit['labels']:
            numbers.setdefault(label, unit['number'])
    return numbers


_SUBENV_RE = re.compile(
    r'\\begin\{(subfigure|subtable)\}(.*?)\\end\{\1\}', re.DOTALL)
_SUBFLOAT_RE = re.compile(r'\\subfloat\s*(?:\[[^\]]*\])?\s*\{')
# `\subfloat[Title]{...}` is lettered; `\subfloat{...}` is not.
_SUBFLOAT_CAPTIONED_RE = re.compile(r'\\subfloat\s*\[[^\]]*\]\s*\{')
_PANEL_CAPTION_RE = re.compile(r'\\caption(?![A-Za-z])')
_SUBREF_RE = re.compile(r'\\subref\s*\{([^{}]+)\}')


# An environment that numbers ITSELF. A `\caption` inside one belongs to that
# environment's counter, not to the float around it. A paper laying two
# `algorithm`s side by side inside one uncaptioned `\begin{figure}` is the
# common idiom, and reading their captions as the figure's numbered two
# figures the paper never prints: every later figure reference named a number
# two too high, while the captions under the plots stayed right.
#
# Kept to the non-float environments on purpose. A nested `figure` or `table`
# is itself a float, and `_FLOAT_ENV_RE` already walks it on its own.
_SELF_NUMBERING_ENVS = ('algorithm', 'algorithm2e', 'algorithmic',
                        'listing', 'lstlisting', 'minted')
_SELFNUM_ENV_RE = re.compile(
    r'\\begin\s*\{(%s)\*?\}' % '|'.join(_SELF_NUMBERING_ENVS))


def _nested_counter_spans(body):
    """[(start, stop)] for each self-numbering environment inside a float."""
    spans = []
    for m in _SELFNUM_ENV_RE.finditer(body):
        close = re.search(r'\\end\s*\{%s\*?\}' % re.escape(m.group(1)),
                          body[m.end():])
        spans.append((m.start(),
                      m.end() + close.end() if close else len(body)))
    return spans


def _panel_spans(body):
    """[(start, stop, text)] for each panel in a float, in source order.

    A panel is its own environment. Slicing "from this panel to the next"
    instead would hand the last panel everything after it, including the
    float's own \\caption and \\label.
    """
    spans = []
    for m in _SUBENV_RE.finditer(body):
        spans.append((m.start(), m.end(), m.group(2)))
    for m in _SUBFLOAT_RE.finditer(body):
        close = _balanced_group(body, m.end() - 1)
        if close > 0:
            # Carry the optional argument along so a captioned subfloat can be
            # told from an uncaptioned one downstream.
            spans.append((m.start(), close, body[m.start():close]))
    spans.sort(key=lambda s: s[0])
    return spans


def _panel_is_lettered(scope):
    r"""Does this panel take a letter?

    `subcaption` steps the sub-counter on `\caption`, not on the environment.
    Neural ODE's figure holds four `subfigure`s and the third is a legend with
    no caption, so the paper prints (a) (b) (c) — verified in the source PDF —
    while lettering by position printed `(d)` for the last one. A caption is
    what makes a panel a panel.
    """
    if _PANEL_CAPTION_RE.search(scope):
        return True
    return bool(_SUBFLOAT_CAPTIONED_RE.match(scope.lstrip()))


def _panel_scopes(body):
    """[(start, text)] for each panel in a float, in source order."""
    return [(start, text) for start, _stop, text in _panel_spans(body)]


def build_subfigure_letters(temp_dir):
    """{'fig:corr': 'a', 'fig:adam': 'b', ...} parsed from flat.tex.

    A multi-panel figure letters its panels in source order, and its caption
    refers to them with \\subref. Without this the caption reads
    "(\\subref{fig:corr}) In LLMs ..." and the reader cannot tell which of the
    three plots the sentence is about.
    """
    flat = os.path.join(temp_dir, 'flat.tex')
    if not os.path.exists(flat):
        return {}
    try:
        with open(flat, 'r', encoding='utf-8', errors='replace') as fh:
            tex = strip_tex_comments(fh.read())
    except OSError:
        return {}

    letters = {}
    # The same prefixes `_label_token_re` already accepts. A `wrapfigure` is a
    # float like any other and its panels are lettered like any other's —
    # Neural ODE puts three `subfigure`s inside one, and scanning only for
    # `figure` found no panels at all, so all three `\subref` in its caption
    # printed as LaTeX beside the plots they were pointing at.
    float_re = re.compile(
        r'\\begin\{((?:SC|wrap|sideways|long|floating)?(?:figure|table)\*?)\}'
        r'(.*?)\\end\{\1\}', re.DOTALL)
    for float_match in float_re.finditer(tex):
        index = 0
        for _start, scope in _panel_scopes(float_match.group(2)):
            if not _panel_is_lettered(scope):
                continue          # a legend panel takes no letter, and does
                                  # not advance the one the next panel gets
            for label in re.findall(r'\\label\{([^}]+)\}', scope):
                letters.setdefault(label.strip(), chr(ord('a') + index))
            index += 1
    return letters


_DEFAULT_THEOREM_ENVS = ('theorem', 'lemma', 'definition', 'proposition',
                         'corollary', 'remark', 'assumption')
# `alignat`, `flalign` and `IEEEeqnarray` were missing, and the cost is not
# that their labels went uncounted: a `\label` inside one kept whatever
# `current` the PREVIOUS display had set, so it silently named an earlier
# formula. 2609.05354 has eight labels inside `alignat` blocks.
#
# `subequations` is here for its own branch below. It numbers nothing itself
# -- what it holds does -- but a label on the WRAPPER names the group, and
# without being seen at all that label kept the section's number and sent
# the reader to a section instead of a formula.
_COUNTED_STRUCTURAL_ENVS = ('equation', 'align', 'gather', 'multline',
                            'eqnarray', 'alignat', 'flalign',
                            'IEEEeqnarray', 'subequations', 'algorithm')

# `\newtheorem` carries an optional argument on EITHER side of the title, and
# they mean opposite things: `\newtheorem{lmm}[thrm]{Lemma}` shares the `thrm`
# counter, `\newtheorem{thrm}{Theorem}[section]` scopes it to the section. Only
# the leading one was captured, so `[section]` was not ignored — it could not
# be seen. `read_theorem_environments` said so anyway, and the test that pinned
# the claim passed on a group that was always None.
_NEWTHEOREM_RE = re.compile(
    r'\\newtheorem(\*?)\s*\{([^}]+)\}\s*(?:\[([^\]]*)\])?\s*\{[^}]*\}'
    r'\s*(?:\[([^\]]*)\])?')


def read_theorem_environments(tex):
    """{env: counter_group}, read from the document's own \\newtheorem lines.

    A fixed list of environment names is a guess about the author's taste, and
    Vershynin spends it immediately: he declares `example`, `fact`,
    `observation`, `conjecture`, `remarks` and `definition-notag` too. Five of
    those appear in the body, none were in the list, so the theorem counter
    silently skipped them -- 52 of 59 labels came out with the wrong number and
    225 of 274 body references would have printed one. Nothing errored; the
    numbers were simply, confidently wrong.

    The document already says which environments are numbered and which counter
    each one shares. Read that instead of guessing.

    `\\newtheorem*` takes no number at all. The TRAILING optional argument —
    `\\newtheorem{thrm}{Theorem}[section]` — says the counter is scoped to the
    section; `read_counter_parents` reads it, and `_counter_label` puts the
    section number in front. That used to be waved away as pandoc's business
    (K113), which cost Maynard every one of its 35 theorem references.
    """
    envs = {}
    for m in _NEWTHEOREM_RE.finditer(tex):
        star, name, shared = m.group(1), m.group(2).strip(), m.group(3)
        if star or not name:
            continue
        envs[name] = (shared or name).strip() or name
    return envs


def read_theorem_parents(tex):
    r"""{counter: parent} from the trailing `[within]` of `\newtheorem`.

    Only for a declaration that owns its counter. `\newtheorem{lmm}[thrm]{...}`
    shares `thrm`'s, so the scope belongs to `thrm` and naming `lmm` here would
    reset a counter that does not exist.
    """
    parents = {}
    for m in _NEWTHEOREM_RE.finditer(tex):
        star, name, shared, within = (m.group(1), m.group(2).strip(),
                                      m.group(3), m.group(4))
        if star or not name or shared:
            continue
        within = (within or '').strip()
        if within:
            parents[name] = within
    return parents


_COUNTER_WITHIN_RE = re.compile(
    r'\\(?:counter|number)within\s*\*?\s*\{\s*([A-Za-z@]+)\s*\}'
    r'\s*\{\s*([A-Za-z@]+)\s*\}')
_THE_REDEF_RE = re.compile(
    r'\\def\s*\\the([A-Za-z@]+)\s*\{((?:[^{}]|\{[^{}]*\})*)\}'
    r'|\\renewcommand\s*\*?\s*\{?\s*\\the([A-Za-z@]+)\s*\}?'
    r'\s*\{((?:[^{}]|\{[^{}]*\})*)\}')


def read_counter_parents(tex):
    r"""{counter: parent} for counters printed with another counter in front.

    Shor 1995 prints `(2.1)`, not `(2)`: its preamble resets the equation,
    figure and table counters at each section and redefines `\theequation` to
    carry `\thesection`. Nothing in this pipeline read either signal, so all 48
    equation references and every float reference named a number the paper does
    not print — and the mismatch was nearly accepted as a limit of the
    supported subset.

    It is not one. The number on an equation or a float is stamped by THIS
    pipeline (K46, K62), so it is ours to choose. ~~Only theorem-likes are
    numbered by pandoc and stay out of reach (K113).~~ Nor are they: what
    pandoc wrote is characters in `output.md`, and the build rewrites that line
    anyway (K130). The trailing `[within]` of `\newtheorem` is read here too.

    Nor is this a LaTeX interpreter. One fact is needed per counter — which
    counter, if any, prefixes it — and a document can only say it a few ways.
    Everything else inside `\the...` means "print arabic", which is what we
    already do. Across the whole corpus exactly two papers say anything at all.
    """
    # `[0] or tex` looked like a sensible fallback for a fragment with no
    # \begin{document}, and it also fired when the document begins with one:
    # the empty preamble is falsy, so the whole body got scanned and a counter
    # redefined mid-document was read as a preamble declaration.
    at = tex.find(r'\begin{document}')
    preamble = tex[:at] if at >= 0 else tex
    parents = read_theorem_parents(preamble)
    for m in _COUNTER_WITHIN_RE.finditer(preamble):
        parents[m.group(1)] = m.group(2)
    for m in _THE_REDEF_RE.finditer(preamble):
        name = m.group(1) or m.group(3)
        body = m.group(2) if m.group(1) else m.group(4)
        if not name:
            continue
        ref = re.search(r'\\the([A-Za-z@]+)', body or '')
        # `\def\theequation{\arabic{equation}}` names no parent: it only says
        # how to print, and that is already what happens.
        if ref and ref.group(1) != name:
            parents[name] = ref.group(1)
    return parents


_SETCOUNTER_RE = re.compile(
    r'\\setcounter\s*\{\s*([A-Za-z@]+)\s*\}\s*\{\s*(\d+)\s*\}')


def read_fixed_counter_prefix(tex):
    r"""{counter: value} for a counter set once and never advanced.

    randmat is one chapter of a `book` shipped on its own: it declares
    `\newtheorem{theorem}{Theorem}[chapter]`, writes `\setcounter{chapter}{5}`
    just before the first section, and contains no `\chapter{}` at all. Its
    PDF prints Theorem 5.44, and 258 of its references are dotted while none
    is plain — but with the chapter counter treated as absent the numbers came
    out flat and all 157 disagreed.

    The `5` is in the source, not only in the PDF. Read it, but only when the
    counter is never advanced: a document that really uses `\chapter{}` has a
    prefix that moves, and this must leave that alone rather than pin it.
    """
    fixed = {}
    for m in _SETCOUNTER_RE.finditer(tex):
        name, value = m.group(1), m.group(2)
        if re.search(r'\\%s\b(?!\s*\{\s*\})' % re.escape(name), tex) \
                and re.search(r'\\%s\s*\*?\s*[\[{]' % re.escape(name), tex):
            continue                       # the counter's own command is used
        fixed[name] = value
    return fixed


def _counter_label(counter, n, parents, section_head, fixed=None):
    """`2.1` when the counter is scoped to a section, else `1`.

    `fixed` covers the other way a prefix can be constant: a counter set once
    with `\\setcounter` and never advanced (see `read_fixed_counter_prefix`).
    """
    parent = parents.get(counter)
    if parent == 'section' and section_head:
        return '%s.%d' % (section_head, n)
    if fixed and parent in fixed:
        return '%s.%d' % (fixed[parent], n)
    return str(n)


def _label_token_re(theorem_envs):
    """Compile the scanner for one document's environment vocabulary.

    Longest name first: `definition-notag` must not be read as `definition`
    followed by stray text.
    """
    names = set(_COUNTED_STRUCTURAL_ENVS) | set(theorem_envs)
    alt = '|'.join(re.escape(name) for name in
                   sorted(names, key=lambda n: (-len(n), n)))
    return re.compile(
        # Both spellings, in ONE group: the branches below are read by
        # position, so a new group here would renumber every one of them.
        # `\appendix` is the command; `\begin{appendix}` and
        # `\begin{appendices}` are the environments the appendix package
        # offers, and a paper that uses one does not also write the other.
        # 2609.05354 opens with `\begin{appendix}` and no command anywhere,
        # so its appendix sections numbered 11 and 11.5 where the paper
        # prints A and A.5, and every `\ref` into them followed.
        r'\\(appendix(?![a-zA-Z])|begin\s*\{append(?:ix|ices)\})'
        r'|\\((?:sub)*)section(\*?)\s*\{'
        r'|\\begin\{(' + alt + r')(\*?)\}'
        r'|\\begin\{(?:SC|wrap|sideways|long|floating)?(figure|table)\*?\}'
        r'|\\begin\{(tabular|lstlisting|listing|minted|verbatim'
        r'|thebibliography)\*?\}'
        r'|\\end\{(?:SC|wrap|sideways|long|floating)?(figure|table|tabular'
        r'|lstlisting|listing|minted|verbatim|thebibliography)\*?\}'
        r'|\\label\s*\{([^}]+)\}')


_LABEL_TOKEN_RE = _label_token_re(_DEFAULT_THEOREM_ENVS)

_NUMBERED_MATH_ENVS = ('equation', 'align', 'gather', 'multline', 'eqnarray',
                       'alignat', 'flalign', 'IEEEeqnarray')

_DOCUMENTCLASS_RE = re.compile(
    r'\\documentclass\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}')

# Numbering a class chooses for a paper that never states it. Two papers
# disagreed with their own PDFs for this one reason, and neither carried a
# `\renewcommand{\thesection}` or a `\numberwithin` to read: revtex4-2
# prints sections I, II, III, and amsart numbers a display within its
# section, so a formula in section 2 prints (2.1).
#
# Only classes something here can CHECK belong in this table. Both of these
# were measured against the paper's own PDF -- 2609.05337 for the Roman
# headings, 2609.05354 for 57 dotted equation markers and no undotted one --
# and `source_probe` re-checks them on every run. A class added from memory
# would be the NEVER SEEN trap wearing a different coat.
_CLASS_CONVENTIONS = {
    'revtex4-2': {'section': 'Roman'},
    'revtex4-1': {'section': 'Roman'},
    'revtex4': {'section': 'Roman'},
    # amsart also sets a subsection RUN-IN, on the same line as the paragraph
    # it opens. There is no heading line in the PDF for a line-matcher to
    # find, so 17 of 2609.05354's subsections counted as "could not be found
    # in the original" and failed a paper whose numbering was right. Counted
    # separately rather than ignored: a check that fails correct work teaches
    # people to stop reading it, and one that hides a real loss is worse.
    'amsart': {'parents': {'equation': 'section'}, 'run_in_level': 2},
    # llncs (Springer LNCS) sets \subsubsection and \paragraph run-in as
    # well: AdamX prints `Baseline Algorithms To evaluate AdamX, ...` on one
    # line, bold then roman. Its eight such headings were "not found".
    'llncs': {'run_in_level': 3},
    # IEEEtran prints TABLE I, TABLE II and Fig. 1, Fig. 2: Roman for tables
    # and arabic for figures, which is why only the table is listed. TinyVLA
    # is the paper that showed it, with all six of its disagreeing
    # cross-references naming a table the reader cannot find.
    'IEEEtran': {'float': {'table': 'Roman'}},
}

_ROMAN_PLACES = ((1000, 'M'), (900, 'CM'), (500, 'D'), (400, 'CD'),
                 (100, 'C'), (90, 'XC'), (50, 'L'), (40, 'XL'),
                 (10, 'X'), (9, 'IX'), (5, 'V'), (4, 'IV'), (1, 'I'))


def roman_numeral(n):
    """`3` -> `III`. Section counts are small; this stays exact anyway."""
    if n <= 0:
        return str(n)
    out = []
    for value, sign in _ROMAN_PLACES:
        while n >= value:
            out.append(sign)
            n -= value
    return ''.join(out)


def read_class_conventions(tex):
    """What the document class numbers differently, and never says so."""
    m = _DOCUMENTCLASS_RE.search(tex)
    if not m:
        return {}
    return _CLASS_CONVENTIONS.get(m.group(1).strip(), {})


def build_label_index(temp_dir):
    """{'eq:pqe': ('5', 'equation'), 'sec:single': ('4.1', 'section')}.

    The kind matters as much as the number. A label's prefix is the author's
    naming habit, not a fact: CafeQ writes `\\label{lem:norm}` INSIDE an
    `equation`, and reading `lem` as "lemma" printed `정리 3` in a book that
    contains no theorems -- sending the reader to look for something that
    was never there. What the label is attached to is what it names.

    Sections, appendices, equations, algorithms and theorem-likes: everything
    LaTeX numbers except floats, which build_float_numbers already owns.

    Rebuilding the counters is necessary even when the headings show no
    numbers: \\ref returns the counter either way, so the body still says
    "Section 4.1" and "Appendix A.2". CafeQ and AlphaQ were long taken for
    papers that hide their heading numbers. They print them; PyMuPDF puts the
    number on a line of its own, and only the joined form used to be read
    (see prefixes_from_lines).
    """
    flat = os.path.join(temp_dir, 'flat.tex')
    if not os.path.exists(flat):
        return {}
    try:
        with open(flat, 'r', encoding='utf-8', errors='replace') as fh:
            tex = strip_tex_comments(fh.read())
    except OSError:
        return {}

    section = [0, 0, 0]
    in_appendix = False
    counters = {'equation': 0, 'algorithm': 0, 'theorem': 0}
    theorem_envs = read_theorem_environments(tex)
    token_re = _label_token_re(theorem_envs or _DEFAULT_THEOREM_ENVS)
    parents = read_counter_parents(tex)
    # The class fills in only what the paper did not say. An explicit
    # `\numberwithin` is an author overriding their own class, so it wins.
    conventions = read_class_conventions(tex)
    for counter, parent in (conventions.get('parents') or {}).items():
        parents.setdefault(counter, parent)
    section_style = conventions.get('section')
    fixed = read_fixed_counter_prefix(tex)
    section_head = ''                   # the number a section-scoped counter
                                        # carries in front of its own
    current = None                      # what the next \label would name
    kind = None                         # and what kind of thing that is
    suspended = []                      # section context stacked over floats
    numbers = {}
    for m in token_re.finditer(tex):
        if m.group(1):
            in_appendix = True
            section = [0, 0, 0]
            current, kind = None, None
        elif m.group(2) is not None and m.group(3) is not None:
            if m.group(3) == '*':       # starred sections take no number
                current, kind = None, None
                continue
            depth = m.group(2).count('sub')
            section[depth] += 1
            for deeper in range(depth + 1, 3):
                section[deeper] = 0
            if in_appendix:
                head = chr(ord('A') + section[0] - 1)
            elif section_style == 'Roman':
                head = roman_numeral(section[0])
            else:
                head = str(section[0])
            # A `book` shipped as one chapter numbers its sections under it:
            # randmat writes `\setcounter{chapter}{5}` and its own text says
            # "Section 5.4.3", never "Section 4.3". The prefix comes from the
            # source, not from the PDF, and only when no `\chapter{}` moves it.
            if not in_appendix and fixed.get('chapter'):
                head = '%s.%s' % (fixed['chapter'], head)
            current = '.'.join([head] + [str(x) for x in section[1:depth + 1]])
            kind = 'section'
            if depth == 0:
                # A counter scoped to `section` restarts here, and from here on
                # prints this number in front of its own.
                section_head = head
                for counter, parent in parents.items():
                    if parent == 'section':
                        counters[counter] = 0
        elif m.group(4):
            if m.group(5):
                current, kind = None, None
                continue
            env = m.group(4)
            if env in _NUMBERED_MATH_ENVS:
                counters['equation'] += 1
                current = _counter_label('equation', counters['equation'],
                                         parents, section_head, fixed)
                kind = 'equation'
            elif env == 'algorithm':
                counters['algorithm'] += 1
                current, kind = str(counters['algorithm']), 'algorithm'
            elif env == 'subequations':
                # The wrapper carries the group's number, and that is the
                # SAME number its first inner display takes: LaTeX advances
                # the parent counter once for the whole group and letters
                # the rows under it. So name it WITHOUT consuming it. The
                # inner environment does the incrementing a moment later
                # and lands on the same string, which is why this needs no
                # suppression flag and changes no arithmetic.
                current = _counter_label('equation', counters['equation'] + 1,
                                         parents, section_head, fixed)
                kind = 'equation'
            else:
                # Environments sharing one counter must share one tally, and
                # an environment declared with its own counter must not touch
                # anyone else's: `definition-notag` restarts at 1 mid-paper,
                # and pandoc prints exactly that.
                group = theorem_envs.get(env, 'theorem')
                counters[group] = counters.get(group, 0) + 1
                # The same call the equation branch makes eight lines up. A
                # counter scoped to the section prints `4.1`, and the reset
                # loop above has already zeroed it at the section head.
                current = _counter_label(group, counters[group],
                                         parents, section_head, fixed)
                kind = 'theorem'
        elif m.group(6) or m.group(7):
            # Entering a float or a verbatim block. A \label inside a float
            # belongs to the float's own counter -- build_float_numbers owns
            # those -- so suspend whatever the last section or equation was.
            suspended.append((current, kind))
            current, kind = None, None
        elif m.group(8):
            # Leaving it. LaTeX scopes a float's \refstepcounter to the float,
            # so a \label placed after \end{figure} still names the enclosing
            # section: AlphaQ's app:hill-derivation is Appendix A.3, and the
            # paper prints exactly that.
            if suspended:
                current, kind = suspended.pop()
        elif m.group(9) and current is not None:
            numbers.setdefault(m.group(9).strip(), (current, kind))
    return numbers


def build_label_numbers(temp_dir):
    """{label: number}, the numbering half of build_label_index."""
    return {key: value[0] for key, value in
            build_label_index(temp_dir).items()}


# A declaration site, not a reference: `**정리 32** (Gaussian).` names the
# theorem being stated. Vershynin labels it `\label{Gaussian}` too, so the key
# alone cannot tell the two apart -- but a declaration always closes an
# emphasis span carrying the number right before the parenthesis, and a
# reference in running prose never does.
_DECL_SITE_TAIL_RE = re.compile(
    r'(?:\*\*|\*)[^*\n]*\d[^*\n]*(?:\*\*|\*)[ \t ]*$')


def _unprefixed_xref_regex(keys, label_words):
    """`(Bai-Yin)` -- a reference whose label carries no kind prefix.

    build_label_index already learned that a label's prefix is the author's
    naming habit rather than a fact. The resolver had not: it only recognised a
    reference by that prefix, so a paper writing `\\label{Bai-Yin}` instead of
    `\\label{thm:bai-yin}` had every one of its cross-references left standing
    as the raw label key. Vershynin has 260 of them, and the reader meets
    `정리 (deviation from 1)` where the paper says Lemma 44.

    Match the keys themselves. They are known exactly, so nothing is guessed.
    """
    if not keys:
        return None
    body = '|'.join(re.escape(k) for k in
                    sorted(keys, key=len, reverse=True))
    lead = ''
    words = sorted({w.strip() for w in label_words if w and w.strip()},
                   key=len, reverse=True)
    if words:
        lead = (r'(?:(?<!\w)(%s)[ \t ~]*)?'
                % '|'.join(re.escape(w) for w in words))
    return re.compile(_XREF_LEAD + lead + r'\(\s*(' + body + r')\s*\)')


def resolve_unprefixed_references(md_text, index, words, formats,
                                  lead_words=None):
    """Resolve `(key)` against the label index. Returns (text, count)."""
    if not index:
        return md_text, 0
    leads = list(words.values()) + list(lead_words or ())
    pattern = _unprefixed_xref_regex(index.keys(), leads)
    if pattern is None:
        return md_text, 0
    hits = [0]

    def sub(m):
        entry = index.get(m.group(2).strip())
        if entry is None:
            return m.group(0)
        number, kind = entry
        lead = m.group(1)
        if lead is None and _DECL_SITE_TAIL_RE.search(md_text[:m.start()]):
            return m.group(0)       # the statement itself, not a pointer to it
        slot = kind if kind in words else 'theorem'
        hits[0] += 1
        if kind == 'theorem' and lead:
            # Keep the word the translator wrote. The index knows the number
            # but not whether this one is a Lemma, a Corollary or a Remark,
            # and "보조정리 28" must not be flattened to "정리 28".
            return '%s %s' % (lead, number)
        template = formats.get(slot, '{label} {number}')
        return template.format(label=words[slot], number=number)

    return pattern.sub(sub, md_text), hits[0]


def resolve_references(md_text, temp_dir, lang_cfg=None):
    """Turn [@key] into [N] and (fig:x) into 'Figure N'.

    Returns (text, stats). Anything that cannot be resolved is left exactly as
    it was, so it stays visible rather than silently becoming a wrong number.
    """
    lang_cfg = lang_cfg or {}
    fig_label = lang_cfg.get('figure_label', 'Figure')
    tab_label = lang_cfg.get('table_label', 'Table')
    stats = {'cites': 0, 'cites_missed': 0, 'xrefs': 0, 'xrefs_missed': 0,
             'subrefs': 0}

    sub_letters = build_subfigure_letters(temp_dir)

    def subref_sub(m):
        letter = sub_letters.get(m.group(1).strip())
        if letter is None:
            return m.group(0)
        stats['subrefs'] += 1
        return letter

    md_text = _SUBREF_RE.sub(subref_sub, md_text)

    bib = build_bibitem_numbers(md_text)

    def cite_sub(m):
        keys = _CITE_KEY_RE.findall(m.group(1))
        # Only rewrite when EVERY key resolves; a half-numbered citation is
        # worse than an untouched one.
        if not keys or any(k not in bib for k in keys):
            stats['cites_missed'] += 1
            return m.group(0)
        stats['cites'] += 1
        return '[' + ', '.join(str(bib[k]) for k in keys) + ']'

    if bib:
        md_text = _CITE_RE.sub(cite_sub, md_text)
    else:
        stats['cites_missed'] = len(_CITE_RE.findall(md_text))

    floats = build_float_numbers(temp_dir)
    index = build_label_index(temp_dir)
    words = {'figure': fig_label, 'table': tab_label}
    for slot, fallback in _XREF_WORDS.items():
        words.setdefault(slot, lang_cfg.get(slot + '_label', fallback))
    formats = dict(_XREF_FORMATS)
    formats.update(lang_cfg.get('ref_formats') or {})

    def render_xref(kind, name):
        """One `kind:name` as the reader should see it, or None.

        None means it did not resolve, and the caller then leaves the
        reference exactly as it was rather than printing a wrong number.
        """
        source, slot = _XREF_KINDS.get(kind, (None, None))
        if source is None:
            return None
        if source == 'float':
            prefix = 'fig' if slot == 'figure' else 'tab'
            number = floats.get('%s:%s' % (prefix, name))
        else:
            entry = index.get('%s:%s' % (kind, name)) or index.get(name)
            number = entry[0] if entry else None
            # The prefix says what the author called it; the source says what
            # it is. `\cref{lem:norm}` on a label sitting inside an equation
            # printed `정리 3` into a book with no theorems in it.
            #
            # Only where the two are structurally different. An appendix is a
            # section as far as the counter is concerned, so `section` is the
            # generic bucket and not better information: overriding on it
            # turned every `부록 A.10` into `A.10절`.
            if entry and entry[1] in ('equation', 'algorithm') \
                    and entry[1] in words and entry[1] != slot:
                slot = entry[1]
        if number is None:
            return None
        template = formats.get(slot, '{label} {number}')
        return template.format(label=words[slot], number=number)

    def xref_sub(m):
        parts = _xref_parts(m.group(1).lower(), m.group(2).strip())
        rendered = [render_xref(k, n) for k, n in parts]
        # Every label or none. A half-resolved list prints one number beside
        # one raw `tab:x`, which reads as a defect in the number too -- the
        # rule the citation path above keeps, for the same reason.
        if not rendered or any(r is None for r in rendered):
            stats['xrefs_missed'] += 1
            return m.group(0)
        # Counted per label, because that is what lands on the page: one
        # `\Cref{tab:a,tab:b}` puts two numbers in front of the reader.
        stats['xrefs'] += len(rendered)
        # Joined with a comma, which needs no vocabulary. cleveref writes
        # "Tables 4 and 5" in English, but the conjunction is a different
        # word in every language this builds and no language config carries
        # one; the citation path a few lines up joins with a comma for the
        # same reason.
        out = ', '.join(rendered)
        # The translator's own closing word, if the pattern took one. Drop it
        # only where the reference this emits already ends in it; otherwise it
        # belonged to the sentence and goes back untouched.
        closer = m.group(3) if m.re.groups >= 3 else None
        if closer and not out.endswith(closer):
            out += closer
        return out

    # Whatever the template puts around the number is what a translator writes
    # around the placeholder. Korean's closing label stays with the
    # particle-aware pass below, which has carried it across five books.
    lead_affix, trail_affix = template_affixes(formats, words)
    if lang_cfg.get('particle_agreement') is True:
        trail_affix = []
    xref_re = _xref_regex(list(words.values()) + lead_affix, trail_affix)
    if floats or index:
        md_text = xref_re.sub(xref_sub, md_text)
    else:
        stats['xrefs_missed'] = len(xref_re.findall(md_text))

    md_text, keyed = resolve_unprefixed_references(
        md_text, index, words, formats,
        lead_words=lang_cfg.get('theorem_words')
        or _DEFAULT_LANG_CONFIG.get('theorem_words'))
    stats['xrefs'] += keyed

    md_text, bare = resolve_bare_float_labels(md_text, temp_dir, words,
                                              formats)
    stats['xrefs'] += bare
    md_text, stats['doubled'] = drop_doubled_labels(md_text, words, formats,
                                                    lang_cfg)
    md_text, stats['particles'] = fix_particles(md_text, lang_cfg)
    return md_text, stats


# Which Korean particle follows depends on how the PRECEDING SYLLABLE is
# pronounced, and the translator never saw the number: it wrote a particle
# after "(fig:dual_scale)" and this pass then substituted "그림 1" in front of
# it. Twelve of those shipped -- "그림 1를", "표 9은" -- and a Korean reader
# stops at every one, because 1 is read 일 and ends in a consonant.
_DIGIT_HAS_CODA = {'0': True,    # 영
                   '1': True,    # 일
                   '2': False,   # 이
                   '3': True,    # 삼
                   '4': False,   # 사
                   '5': False,   # 오
                   '6': True,    # 육
                   '7': True,    # 칠
                   '8': True,    # 팔
                   '9': False}   # 구
# 으로/로 is the one pair that does not follow the coda rule: a final ㄹ takes
# 로, like 물로 and 서울로. 일, 칠 and 팔 all end in ㄹ, so "8로" is correct
# and "8으로" -- which this pass produced on its first outing -- is not.
_DIGIT_ENDS_IN_RIEUL = {'1', '7', '8'}
# (after a consonant, after a vowel)
_PARTICLE_PAIRS = (('을', '를'), ('은', '는'), ('과', '와'), ('이', '가'),
                   ('으로', '로'))
_NUMBERED_REF_RE = re.compile(
    r'(\d+(?:\.\d+)*)\s*(으로|을|를|은|는|과|와|이|가|로)(?![가-힣])')


# A particle can stand between the doubled label and the next word, so the
# second "절" is not always followed by whitespace. Longest forms first: the
# alternation is tried in order and "에" would otherwise win over "에서는".
_KO_PARTICLES = ('으로', '에서는', '에서', '에는', '에', '의', '을', '를', '은',
                 '는', '과', '와', '이', '가', '로', '도', '만', '부터', '까지')


def resolve_bare_float_labels(md_text, temp_dir, words, formats):
    r"""`(table-mixtral)` -> `표 9`. Returns (text, count).

    A cross-reference is recognised by its prefix -- `(tab:x)`, `(fig:y)`.
    AlphaQ labels one of its tables `\label{table-mixtral}`, with no prefix
    at all, so nothing matched it: the raw label printed to the reader where
    `표 9` belongs, and the pointer to table 9 went with it.

    Two guards, because these pages are full of parenthesised English. Only
    a label attached to a float is eligible — the same paper has a section
    labelled `HT-SR`, which is also how it introduces the acronym. And only
    where a space precedes the bracket, which a gloss never has:
    `Self-Regularization(HT-SR)` has none, `그리고 (table-mixtral)에서` does.
    """
    known = {}
    for unit in read_float_units(temp_dir):
        if unit.get('number') is None:
            continue
        slot = 'figure' if str(unit.get('kind')).startswith('figure') \
            else 'table'
        for label in unit.get('labels') or ():
            known.setdefault(label, (slot, unit['number']))
    if not known:
        return md_text, 0
    pattern = re.compile(r'(?<=\s)\((%s)\)' % '|'.join(
        sorted((re.escape(k) for k in known), key=len, reverse=True)))

    def sub(m):
        slot, number = known[m.group(1)]
        template = formats.get(slot, '{label} {number}')
        return template.format(label=words[slot], number=number)

    return pattern.subn(sub, md_text)


def drop_abbreviated_label(md_text, label):
    r"""`l'éq. Équation (3)` -> `l'Équation (3)`. Returns (text, n).

    The doubling `drop_doubled_labels` already knew about is the SAME word
    twice, which is what happens when the translator writes the label the
    resolver is about to write. A translator who abbreviates instead leaves
    two forms that do not match each other, so nothing fired: French, German
    and Spanish shipped nine of `l'éq. Équation (3)`, `Gl. Gleichung (3)` and
    `la Ec. Ecuación (5)` between them.

    An abbreviation is a prefix of the word it abbreviates, so it is derived
    rather than listed, and a language nobody has run yet is covered. The
    prefix test is also what keeps an ordinary abbreviation in front of a
    reference safe: `cf. Ecuación (3)` and `vs. Tabla 1` are not prefixes of
    what follows them and are left alone.
    """
    lowered = label.lower()
    pattern = re.compile(
        r'(?<![^\W\d_])([^\W\d_]{2,12})\.[ \t]*(?=' + re.escape(label)
        + r'\s*\(?\s*[A-Za-z]?\d)', re.UNICODE)
    count = [0]

    def strip(match):
        if lowered.startswith(match.group(1).lower()):
            count[0] += 1
            return ''
        return match.group(0)

    return pattern.sub(strip, md_text), count[0]


def drop_doubled_labels(md_text, words, formats, lang_cfg=None):
    r"""`4.1절 절과` -> `4.1절과`. Returns (text, n).

    Same wound as the particle fix below. The translator wrote its own '절'
    after the placeholder, never having seen that this pass would substitute
    a reference which already ends in one, and CafeQ shipped "4.1절 절과 4.2
    절 절에서는".

    A prefix label doubles too, and the note that once stood here said it
    could not. The source writes `Figure (Figure_teaser)`, the resolver
    replaces the parenthesised key alone, and the label word the translator
    put in front of it survives: VLA-Adapter shipped `그림 그림 1` and `표 표
    2` twenty times over. The old assumption held only while translators left
    that word in English, where the two forms did not match each other.
    """
    lang_cfg = lang_cfg or {}
    total = 0
    tail = r'(?!\w)'
    if lang_cfg.get('particle_agreement') is True:
        tail = r'(?=(?:%s)?(?!\w))' % '|'.join(_KO_PARTICLES)
    for slot, label in words.items():
        template = formats.get(slot, '{label} {number}')
        head, _sep, after = template.partition('{number}')
        esc = re.escape(label)
        if '{label}' in after:
            # Suffix style: `4.1절 절과` -> `4.1절과`.
            pattern = re.compile(r'(\d[\d.]*' + esc + r')\s*' + esc + tail)
        elif '{label}' in head:
            # Prefix style: `그림 그림 1` -> `그림 1`. Anchored on the number,
            # so a sentence that merely repeats the word is left alone.
            #
            # The number can carry an appendix letter. Requiring a bare digit
            # was the first attempt and it collapsed every body reference
            # while missing every appendix one: sixteen `그림 그림 A1` and
            # `표 표 C1` reached the finished book while the check that had
            # just been written reported zero.
            # The number can also be parenthesised. An equation reference is
            # written `式 (3)`, not `式 3`, so this rule could never see the
            # doubling in one: Chinese printed `那么式 式 (3)` and `针对式 式
            # (5)` with every count reporting zero.
            #
            # Those two are only reachable here, and not at the absorbing
            # stage, because Chinese leaves no space between words: the
            # translator's own 式 sits inside 那么式, and `_xref_regex`
            # deliberately refuses to take a label out of the middle of a
            # word -- the same guard that stops 수식 being split at 식.
            #
            # The residual risk is the mirror of that guard: a Chinese word
            # ending in 式 (模式, 方式, 形式) standing immediately before a
            # reference would lose the label rather than the duplicate. The
            # two shapes are identical in a script with no word boundaries,
            # so this cannot tell them apart; it chooses the visible defect
            # over the invisible one, since a bare `(3)` still reads as an
            # equation reference and `式 式 (3)` reads as nothing.
            pattern = re.compile(esc + r'\s+(' + esc
                                 + r'\s*[（(]?\s*[A-Za-z]?\d)')
            md_text, n = pattern.subn(r'\1', md_text)
            total += n
            md_text, n = drop_abbreviated_label(md_text, label)
            total += n
            continue
        else:
            continue
        md_text, n = pattern.subn(r'\1', md_text)
        total += n
    return md_text, total


def fix_particles(md_text, lang_cfg=None):
    """Make the particle after a resolved number agree with it. (text, n)."""
    if (lang_cfg or {}).get('particle_agreement') is not True:
        return md_text, 0
    count = [0]

    def swap(m):
        digit = m.group(1).rstrip('.').split('.')[-1][-1]
        coda = _DIGIT_HAS_CODA.get(digit)
        if coda is None:
            return m.group(0)
        for after_c, after_v in _PARTICLE_PAIRS:
            if m.group(2) in (after_c, after_v):
                takes_consonant_form = coda
                if after_c == '으로' and digit in _DIGIT_ENDS_IN_RIEUL:
                    takes_consonant_form = False
                want = after_c if takes_consonant_form else after_v
                if want != m.group(2):
                    count[0] += 1
                return m.group(1) + want
        return m.group(0)

    return _NUMBERED_REF_RE.sub(swap, md_text), count[0]


# =============================================================================
# Displayed equation numbers
# =============================================================================
#
# The cross-reference pass resolves "(eq:ilp)" to the number the paper prints,
# so the body says "식 (5)" -- and the equation itself carried no number, which
# left the reader nothing to match it against.
#
# Which display blocks are numbered is not a guess: LaTeX numbers a math
# environment unless it is starred, and `\nonumber` removes a row's number
# inside align. Counted that way, all three papers agree exactly with the
# `(N)` markers printed in their own PDFs (SINQ 7, CafeQ 5, AlphaQ 27).

_DISPLAY_MATH_BLOCK_RE = re.compile(r'\$\$(.*?)\$\$', re.DOTALL)
# Longest name first: `align` would otherwise match the opening of `alignat`
# and, failing on the brace, leave the engine to find it by backtracking.
_MATH_ENV_OPEN_RE = re.compile(
    r'\\begin\{(IEEEeqnarray|alignat|equation|align|gather|multline'
    r'|eqnarray|flalign|empheq|dmath)(\*?)\}')
# `empheq` names the environment it numbers as an ARGUMENT rather than
# opening it, so a pattern hunting `\begin{align}` cannot see it and the
# block counted zero. `\begin{empheq}[box=\fbox]{align}` is an align.
_EMPHEQ_ARG_RE = re.compile(r'^\s*(?:\[[^\]]*\])?\s*\{([A-Za-z]+)(\*?)\}')
# Environments LaTeX numbers ROW BY ROW. The rest take one number for the
# whole block: `equation`, and `multline`, which is a single equation broken
# across lines for width and carries one number however many `\\` it holds.
#
# `gather` and `alignat` were not on this list. `gather` fell to the one-per-
# block branch and `alignat` was not in the pattern at all, so a three-line
# gather counted 1 where the paper prints 3 and an alignat counted 0. That
# does not stay local: `source_probe` compares this count against the `(N)`
# markers in the paper's own PDF, so every equation after the miscount is off
# by the difference and every `\ref` to them points at the wrong one.
#
# Found by feeding each environment to this function directly, after
# `corpus_census digest` reported alignat and flalign as NEVER SEEN. Never
# seen is never tested, and one paper in the corpus already uses gather.
_ROW_NUMBERED = ('align', 'alignat', 'eqnarray', 'flalign', 'gather',
                 'IEEEeqnarray')


def _numbers_for_block(body):
    r"""How many numbers LaTeX would print for this display block.

    Rows are counted inside the environment that owns them, and by
    `latex_rows`, not by `body.count('\\\\')`. Counting the token across
    the whole block read a nested `cases` or `substack` as extra rows of
    the `align` holding it: three numbers where LaTeX prints two, and both
    shapes are ordinary in a machine learning paper. Per K175 that error
    does not stay local -- every equation after it is off by the
    difference, and every `\ref` into them lands on the wrong one.
    """
    total = 0
    for m in _MATH_ENV_OPEN_RE.finditer(body):
        env, star = m.group(1), m.group(2)
        if star:
            continue
        inner = latex_rows.env_body(body, m.end(), env)
        if env == 'empheq':
            arg = _EMPHEQ_ARG_RE.match(inner)
            if not arg:
                total += 1        # a box round something; one is the safe read
                continue
            if arg.group(2):      # `{align*}`: empheq prints no number either
                continue
            env, inner = arg.group(1), inner[arg.end():]
        if env in _ROW_NUMBERED:
            rows = len(latex_rows.split_rows(inner))
            total += max(0, rows
                         - len(re.findall(r'\\(?:nonumber|notag)', inner)))
        else:
            total += 1
    return total


def flat_equation_numbers(temp_dir):
    r"""The number strings the paper issues, in order, or None.

    Only for a paper whose equation counter is scoped to something — Shor 1995
    prints `(2.1)`. Derived from flat.tex because that is where the section
    structure is: the merged markdown has headings but no reliable mapping back
    to the source's own section numbering, and re-deriving it there would be a
    second, disagreeing implementation of the same thing.

    Returns None when the paper numbers flat, so nothing changes for it.
    """
    flat = os.path.join(temp_dir or '', 'flat.tex')
    if not temp_dir or not os.path.isfile(flat):
        return None
    try:
        with open(flat, 'r', encoding='utf-8', errors='replace') as fh:
            tex = strip_tex_comments(fh.read())
    except OSError:
        return None
    # The class counts too. `build_label_index` and `float_units` were taught
    # this and THIS reader was not, so an amsart paper -- which scopes the
    # equation counter to the section without saying so anywhere -- came back
    # None here and had its equations numbered flat, 1, 2, 3, where its own
    # pages print (2.1). The same shape of drift as K179, one file over.
    parents = read_counter_parents(tex)
    for counter, parent in (read_class_conventions(tex).get('parents')
                            or {}).items():
        parents.setdefault(counter, parent)
    if parents.get('equation') != 'section':
        return None

    numbers, head, count = [], '', 0
    # The appendix branch is LAST so groups 1 and 2 keep their positions --
    # the star and the environment are read by number a few lines down.
    # Without it this walk counted sections straight through `\appendix` and
    # issued 8.1 to 8.9 for equations 2609.04930 prints as A.1 and B.1. The
    # fourth reader of the same fact, after `build_label_index`,
    # `float_units` and the class table (K180, K185).
    token = re.compile(r'\\(?:sub)*section(\*?)\s*\{'
                       r'|\\begin\{(' + '|'.join(_NUMBERED_MATH_ENVS) +
                       r')\}'
                       r'|\\(appendix(?![a-zA-Z])'
                       r'|begin\s*\{append(?:ix|ices)\})')
    depth0 = 0
    in_appendix = False
    for m in token.finditer(tex):
        if m.group(3):
            in_appendix, depth0, head, count = True, 0, '', 0
        elif m.group(2):
            count += 1
            numbers.append('%s.%d' % (head, count) if head else str(count))
        elif not m.group(1) and m.group(0).count('sub') == 0:
            depth0 += 1
            head = (chr(ord('A') + depth0 - 1) if in_appendix
                    else str(depth0))
            count = 0
    return numbers or None


def equation_numbers(md_text, strings=None):
    """[(start, end, number_or_None)] for every `$$...$$` block, in order.

    None means the block is unnumbered -- a starred environment, or plain
    display math the source never numbered. A block that would take more than
    one number (an align whose rows are each numbered) is left unlabelled but
    still advances the counter, so every later equation keeps the number the
    original gives it.

    `strings` overrides the flat 1..N counting with the numbers the source
    actually prints. It is ignored unless it has exactly one entry per number
    this text issues: a length mismatch means the two views disagree about how
    many numbers exist, and guessing which is right would misnumber the whole
    book silently.
    """
    out, counter = [], 0
    blocks = []
    for m in _DISPLAY_MATH_BLOCK_RE.finditer(md_text):
        wanted = _numbers_for_block(m.group(1))
        blocks.append((m.start(), m.end(), wanted))
        counter += wanted
    if strings is not None and len(strings) != counter:
        strings = None

    counter = 0
    for start, end, wanted in blocks:
        if wanted == 1:
            counter += 1
            label = (strings[counter - 1] if strings else counter)
            out.append((start, end, label))
        else:
            counter += wanted
            out.append((start, end, None))
    return out


def tag_equations_for_markdown(md_text, temp_dir=None):
    """Put `\\qquad(N)` inside each numbered formula. Returns (text, count).

    For the DOCX path only: pandoc builds book.docx straight from the markdown
    and never sees the HTML the other formats are styled through.
    """
    marks = [m for m in equation_numbers(md_text, flat_equation_numbers(
        temp_dir)) if m[2] is not None]
    if not marks:
        return md_text, 0
    pieces, cursor = [], 0
    for start, end, number in marks:
        body = md_text[start + 2:end - 2]
        closing = re.search(r'(\s*\\end\{[a-zA-Z*]+\}\s*)+$', body)
        # `%s`, not `%d`: a section-scoped number is `2.1`.
        tag = '\\qquad(%s)' % number
        if closing:
            body = body[:closing.start()] + tag + body[closing.start():]
        else:
            body = body + tag
        pieces.append(md_text[cursor:start])
        pieces.append('$$' + body + '$$')
        cursor = end
    pieces.append(md_text[cursor:])
    return ''.join(pieces), len(marks)


_BLOCK_MATH_TAG_RE = re.compile(r'<math\b(?=[^>]*\bdisplay="block")')


def tag_equations_in_html(html, md_text, temp_dir=None):
    """Mark each numbered <math display="block"> with its number.

    pandoc emits one block-level <math> per `$$` block, in document order, so
    the mapping is positional. The stylesheet turns the attribute into a
    flush-right label; nothing is added to the text itself, so a copy-paste of
    the formula stays clean.
    """
    numbers = [n for _s, _e, n in
               equation_numbers(md_text, flat_equation_numbers(temp_dir))]
    if not any(n is not None for n in numbers):
        return html, 0

    pieces, cursor, index, tagged = [], 0, 0, 0
    for m in _BLOCK_MATH_TAG_RE.finditer(html):
        number = numbers[index] if index < len(numbers) else None
        index += 1
        pieces.append(html[cursor:m.end()])
        if number is not None:
            pieces.append(' data-eqno="(%s)"' % number)
            tagged += 1
        cursor = m.end()
    pieces.append(html[cursor:])
    return ''.join(pieces), tagged

# KNOWLEDGE.md — findings log

Hard-won facts about this pipeline that **code cannot enforce on its own**.

Read this when output looks wrong. Append to it when you find something new
(see [Maintenance protocol](#maintenance-protocol) — it is Step 9 of SKILL.md,
not an optional chore).

Anything already enforced by a passing test is deliberately kept to one line
here; the test is the real record. This file is for the *reasoning*, the
*measurement method*, and the things a test can never assert.

---

## Symptom index

| If you see… | Entry |
|---|---|
| Content present in `output.md` but missing from the PDF | [K1](#k1), [K3](#k3) |
| A build step prints "OK" while output is visibly wrong | [K1](#k1), [K16](#k16) |
| PDF is enormous (megabytes per page) | [K2](#k2) |
| CJK text is not selectable / searchable in the PDF | [K2](#k2) |
| A translated chunk's table lost its rows | [K3](#k3) |
| Headings, tables or code render at phone size in print | [K4](#k4) |
| A print CSS rule is simply ignored | [K5](#k5) |
| Chromium exits 0 and produces no PDF | [K6](#k6) |
| Browser/binary detection accepts something that cannot work | [K7](#k7) |
| Page size comes out Letter when A4 was asked for | [K8](#k8) |
| Every paper is titled after its own first section | [K9](#k9) |
| `[@key]` or `(fig:x)` printed literally | [K10](#k10) |
| Short CJK headings never resolve in a page lookup | [K11](#k11) |
| Measured margins disagree with the CSS by ~1mm | [K12](#k12) |
| Deciding body size / measure / leading for CJK print | [K13](#k13) |
| Section breaks eat a lot of paper | [K14](#k14) |
| A literal `</span>` or `</mi>` appears on the page | [K15](#k15) |
| Abstract or keywords missing from the output | [K17](#k17) |
| An IEEE macro printed as literal code | [K18](#k18) |
| A word rendered in math italic | [K19](#k19) |
| Section letters off by one | [K20](#k20) |
| Wondering whether to go 2-column for CJK | [K21](#k21) |
| One caption of many not picked up | [K22](#k22) |
| Images or tables missing from DOCX but fine in PDF | [K23](#k23) |
| A logged mistake happening again | [K24](#k24) |
| A green gate while the output is wrong | [K25](#k25), [K16](#k16) |
| Section numbers wrong, or missing where the original has them | [K26](#k26), [K29](#k29) |
| A table row torn mid-token | [K27](#k27) |
| A whole formula printed as its LaTeX source | [K28](#k28) |
| Build stops after book.html; no DOCX/EPUB/PDF | [K30](#k30) |
| A multi-panel figure lost panels, or figure numbers drift | [K31](#k31) |
| Counting LaTeX leftovers gives an implausible number | [K32](#k32) |
| "See Tab. 표 16" — the reference word twice | [K33](#k33) |
| About to translate a paper for the first time | [K34](#k34) |
| A table cell shows the wrong text, or a row is short | [K35](#k35), [K27](#k27) |
| A heading reads as its own glyph plus its LaTeX | [K36](#k36) |
| A reference to an appendix or section will not resolve | [K37](#k37) |
| The reference list appears twice, or has no heading | [K38](#k38) |
| Numbering refuses after a change that added a heading | [K39](#k39) |
| Body is translated but tables are still in English | [K40](#k40) |
| A table shows the wrong caption, or none | [K41](#k41) |
| A sidecar edit does not reach the PDF | [K42](#k42) |
| A reference label printed twice ("식 식 (5)") | [K43](#k43) |
| Rows of a multi-line equation touch | [K44](#k44) |
| A translated term reads as ordinary words | [K45](#k45) |
| A reference says "식 (5)" but no equation is numbered | [K46](#k46) |
| A figure's caption and the sentence pointing at it disagree | [K47](#k47) |
| A figure is missing and it is not a tikz plot | [K48](#k48) |
| A figure shows the wrong plot, or the same plot twice | [K48](#k48) |
| A table's cells split in the middle of a formula | [K49](#k49) |
| A repaired chunk gets re-translated on the next run | [K50](#k50) |
| A check is green and the book is still wrong | [K51](#k51) |
| A table renders as one column of text with `|` in it | [K52](#k52) |
| A table has empty columns after every row | [K53](#k53) |
| A group label column is blank in every row | [K53](#k53) |
| A page holds one picture and nothing else | [K54](#k54) |
| A unit in brackets renders as nothing | [K55](#k55) |
| The DOCX is missing tables the PDF has | [K56](#k56) |
| Every check passes and the book is still wrong | [K57](#k57) |
| A particle disagrees with the number in front of it | [K58](#k58) |
| A sentence in the book makes no sense, and nor does the original | [K59](#k59) |
| Clicking the floating TOC does nothing | [K60](#k60) |
| A fix I just added made something else wrong | [K61](#k61) |
| A table caption carries no number | [K62](#k62) |
| Display equations print at the left margin | [K63](#k63) |
| A table has no line under its header | [K64](#k64) |
| Rows in a table run together with no grouping | [K65](#k65) |
| A whole table is replaced by the word [TABLE] | [K66](#k66) |
| A table looks right in the PDF and plain in the EPUB | [K67](#k67) |
| A caption check passes on a book with no captions | [K68](#k68) |
| A Word table loses its header after a page break | [K69](#k69) |
| A sub-agent says it translated the chunk | [K70](#k70) |
| One chunk renders a term differently from every other | [K76](#k76) |
| A table's numbers changed while it was being translated | [K71](#k71) |
| The translation is fluent but a term reads oddly | [K72](#k72) |
| A reference in the text is hard to spot | [K73](#k73) |
| Clicking a table reference does nothing | [K80](#k80) |
| A figure has no number but the text cites one | [K81](#k81) |
| A raw `@citationkey` is printed | [K82](#k82) |
| A table lost a value or a column span | [K83](#k83) |
| A table row's numbers are gone and its label is still there | [K84](#k84) |
| A formula prints `^{}` or an italic runs from one formula to another | [K85](#k85) |
| A table's group column is empty and its rows repeat identically | [K86](#k86) |
| A footnote marker has nothing explaining it | [K87](#k87) |
| Paragraphs between two tables are missing from the book | [K88](#k88) |
| A table cell lost its citation, its header or its colour | [K89](#k89) |
| A heading breaks across lines, or a matrix overlaps itself | [K90](#k90) |
| The book has citations but no reference list | [K91](#k91) |
| The references heading sits inside the reference list | [K92](#k92) |
| A figure's caption explains a panel it is not under | [K93](#k93) |
| A figure lost its number and its caption reads as prose | [K94](#k94) |
| The title page carries no author | [K95](#k95) |
| Markup meant to be invisible prints to the reader | [K96](#k96) |
| Every count agrees and the content is still gone | [K97](#k97) |
| Markup of a shape the scan was never told about | [K98](#k98) |
| A table nested inside a cell of another table | [K99](#k99) |
| A formula refused over something that is not maths | [K100](#k100) |
| A guard that tells "ours" from a folder name | [K101](#k101) |
| Table numbers run one high and the last has none | [K102](#k102) |
| A figure reaches the page with no caption | [K103](#k103) |
| The front matter is translated and never printed | [K104](#k104) |
| The arXiv source has no LaTeX in it | [K105](#k105) |
| pandoc dies on a macro definition and takes the paper | [K106](#k106) |
| Reference entries are dispatched for translation | [K107](#k107) |
| A chunk fails a check for following its instructions | [K108](#k108) |
| A formula or a heading prints as raw source | [K109](#k109) |
| A whole appendix or acknowledgement is missing | [K110](#k110) |
| A table is in the source and in no scan's results | [K111](#k111) |
| A chunk fails for leaving code alone | [K112](#k112) |
| Theorem numbers are wrong, or off by a constant | [K113](#k113) |
| Cross-references print the label key instead of a number | [K114](#k114) |
| A formula prints as source and the command is not standard LaTeX | [K115](#k115) |
| A passage comes back half translated, half raw | [K116](#k116) |
| The whole reference list prints as raw LaTeX | [K117](#k117) |
| A math pass is written correctly and never fires | [K118](#k118) |
| The book numbers equations 1..N and the paper prints 2.1 | [K119](#k119) |
| Every citation prints as `[@key]` with no number | [K120](#k120) |
| A collaboration paper's own macros have no definitions | [K121](#k121) |
| A table cell is empty and the source clearly has text in it | [K122](#k122) |
| The author's affiliation is missing and nothing reported it | [K123](#k123) |
| The build warns about unrendered math that is on the page | [K124](#k124) |
| An evidence quote is rejected and looks identical to the source | [K125](#k125) |
| A contents row prints with no page number beside it | [K126](#k126) |
| The probe counts far more equations than the paper prints | [K127](#k127) |
| The build refuses to number sections over a heading count | [K128](#k128) |
| An evidence quote fails and the agent says it copied it | [K129](#k129) |
| Every theorem number in the book is one the paper never prints | [K130](#k130) |
| The paper says 5.44 and the book says 44 | [K131](#k131) |
| A formula prints as source over the paper's own one-character shorthand | [K132](#k132) |
| Removing a stray command broke the formulas beside it | [K133](#k133) |
| Pseudocode prints `\right\rangle` where it means an indent | [K134](#k134) |
| A paper's own abbreviation prints as `\ie` in the finished book | [K135](#k135) |
| A formula with a table in it prints as source | [K136](#k136) |
| A caption says `\subref{...}` beside the panel it means | [K137](#k137) |
| An `\icml` author block loses a name or prints a key | [K138](#k138) |
| The book's author line reads "Unknown Author" | [K139](#k139) |
| A rewrite silently skips every macro in one stretch of prose | [K140](#k140) |
| A macro defined with `\let` still prints its own name | [K141](#k141) |
| A float is in output.md but not in the book | [K78](#k78) |
| A term lost its English between two versions | [K79](#k79) |
| A label is printed twice: "3.2절 절을" | [K77](#k77) |
| A reference list is not detected, or prose is treated as one | [K74](#k74) |
| Translation is slow and expensive on a paper that looks small | [K75](#k75) |

---

## The diagnostic chain

**This pipeline's characteristic failure is the silent drop.** Content does not
error out or render as garbage — it just is not there. So when something is
missing, bisect the artifact chain and find the first stage where it is gone.
Each of these files survives a build in `<temp_dir>`:

| # | Artifact | Produced by | What it proves |
|---|---|---|---|
| 1 | `chunkNNNN.md` | `convert.py` | ingestion worked |
| 2 | `output_chunkNNNN.md` | translator sub-agent | translation kept the structure |
| 3 | `output.md` | `merge_and_build` merge | merge + placeholder restore worked |
| 4 | `prepared.md` | refs + markdown tables | the DOCX source: citations, sections, markdown tables |
| 5 | `pandoc_input.md` | refs + HTML tables | the HTML/PDF/EPUB source: same, tables as HTML |
| 6 | `output.html` | pandoc | markdown → HTML survived |
| 7 | `book_doc.html` | template + `add_print_toc_to_ebook` | template + TOC applied |
| 8 | `book.pdf` | `chromium_pdf` | rendering + pagination |

```bash
# Which stage lost it? Pick a distinctive string and walk the chain.
for f in output.md prepared.md pandoc_input.md output.html book_doc.html; do
  printf '%-18s %s\n' "$f" "$(grep -c '111M' "$f" 2>/dev/null)"
done
python -c "import pymupdf,sys; d=pymupdf.open('book.pdf'); \
print('pdf', sum('111M' in p.get_text('text') for p in d))"
```

Then measure the result rather than eyeballing it:

```bash
python tests/layout_probe.py --strict            # geometry, fonts, overflow
python tests/layout_probe.py --stress --strict   # pagination: long table / math / code
python tests/layout_probe.py --measure-only <pdf>
python tests/format_probe.py <temp_dir> --strict # DOCX/EPUB/PDF carry the same content
```

---

## Entries

### K1
**Raw LaTeX tables vanish on the HTML path.** pandoc's markdown reader parses
`\begin{tabular}` (and any `\begin{table*}` float around it) as a *raw LaTeX
block*, and a raw block only survives into its own output format. On the HTML
path it is dropped with no warning. Feeding the whole float to
`pandoc -f latex -t html` does not help either — pandoc returns rc=0 and an
empty document for a `table*` float. The bare tabular converts fine, so the
float wrapper must be *replaced* (leaving `\begin{table*}` in place makes it
open a raw block that swallows the injected HTML) and `\caption{}` rendered
separately.
*Status: LOCKED — `RawLatexTableTests`. Measured: 5 tables, 89 of 109 math spans.*

### K2
**Never put a variable font in a CJK stack.** Chromium's PDF writer cannot
subset-embed one; it falls back to **one Type3 font object per glyph**. Text
stays extractable but the file explodes and the glyphs stop being real text.
Measured on one page of Korean: `Noto Serif KR` (VF) → 258 KB / 55 Type3
objects; `HCR Batang` (static) → 33 KB / 0. Check with `page.get_fonts(full=True)`
— `Type3` anywhere in the list means this happened.
To tell VF from static without rendering: a variable font has an `fvar` table.
*Status: LOCKED — `test_ko_stack_lists_no_variable_font`. Environment-specific:
which faces are installed varies per machine.*

### K3
**A shell heredoc / `printf` / `echo` collapses `\\` to `\`.** This silently
strips every row separator out of a LaTeX `tabular` (and mangles `\text`,
`\frac`, `\right` into control characters). The text still looks complete, so
nothing downstream notices. It hit a real translation run, and then hit the
author of the fix four more times while writing it.
**Write files with a file-writing tool or Python, never through the shell.**
*Status: GUARDED — `_validate_chunk_latex` fails the merge and names the chunk;
`LatexStructureGuardTests`. The guard deliberately does not compare raw
backslash counts, because the translation prompt allows deleting line-ending
backslashes.*

### K4
**An unscoped `max-width` media query fires while printing.** Chromium's print
layout sets the initial containing block to the *page area*: A4 with 18mm side
margins is 174mm = **657.6 CSS px**, which is under 768px. So a
`@media (max-width: 768px)` block matches and quietly drops headings, tables
and code to phone sizes. No A4 margin escapes this — even 15mm gives 680px.
Scope every responsive block to `@media screen and (...)`.
*Status: LOCKED — `test_responsive_blocks_are_scoped_to_screen`.*

### K5
**The print block must come last in the stylesheet.** At equal specificity the
later rule wins. The `@media print` block used to sit *before* the
math/figure/table rules, which silently overrode it.
*Status: LOCKED — `test_ebook_template_print_block_is_last`.*

### K6
**`--user-data-dir` is load-bearing for headless Chrome.** Without a distinct
profile, launching `chrome.exe` while the user's Chrome is running hands the
command line to that browser and **exits 0 having produced nothing**. Combined
with the fact that `--print-to-pdf` always exits 0, the exit code carries no
information at all — post-conditions are the only real check.
*Status: LOCKED — `test_user_data_dir_is_the_given_profile_dir`,
`test_fails_when_exit_zero_but_no_file`.*

### K7
**Do not probe a browser with `--version` on Windows.** A running Chrome
intercepts the command line, prints "opening in existing browser session" and
exits 0 without a version string — so the probe validates binaries that cannot
render and rejects nothing. Use `os.path.isfile`.
*Status: LOCKED — `test_does_not_probe_with_version`.*

### K8
**`chrome --headless --print-to-pdf` DOES honour `@page { size / margin }`.**
This is worth knowing because the CDP `Page.printToPDF` API does *not*, unless
`preferCSSPageSize: true`. Verified by rendering and reading `page.rect`:
594.96 × 841.92 pt = 209.9 × 297.0 mm. Default paper is Letter, so a missing
`@page` is how you get Letter output.
Chromium implements **no `@page` margin boxes** and no `target-counter()`, which
is why folios are stamped by PyMuPDF and TOC page numbers need a two-pass
render.
*Status: measured 2026-08-20, Chrome 149. Re-verify after a major Chrome bump.*

### K9
**arXiv PDFs routinely ship an empty `/Title`.** Any "first `#` heading"
fallback therefore names every paper after its own Introduction. The LaTeX
`\title{}` in `flat.tex` is authoritative and always available on the arXiv path.
*Status: LOCKED — `LatexTitleTests`.*

### K10
**A paper with a precompiled `.bbl` and no `.bib` leaves `[@key]` unresolved** —
citeproc has nothing to read. But the inlined `\bibitem` list *is* the
numbering, and `flat.tex` keeps every `\label` in float order, so both citations
and `(fig:x)` / `(tab:x)` resolve deterministically. No guessing from filenames.
Resolve nothing rather than guess: a wrong figure number is worse than a visible
unresolved marker.
*Status: LOCKED — `ReferenceResolutionTests`.*

### K11
**Short CJK headings defeat a naive text search.** Korean section names are
routinely two characters (서론, 방법, 실험, 결론). A minimum-length filter drops
them; searching for them blindly matches prose. Match against *heading-sized*
lines instead — collect span sizes, take the modal body size, and consider only
lines above ~1.12× it.
*Status: in `chromium_pdf._heading_index`. Behavioural, not unit-testable
without a rendered PDF.*

### K12
**PyMuPDF block bboxes are glyph EM boxes, not ink.** A heading with tight
`line-height` reports a top margin ~1mm smaller than what actually prints,
because the font ascent overshoots its own line box. For "does this look right
on paper", rasterise and scan for non-white pixels. `layout_probe` reports both
and uses ink for pass/fail — except the bottom margin, where the stamped folio
lives by design, so that one comes from the line boxes.

### K13
**Korean print typography, for A4.** Aim for **35–45 Hangul per line**; beyond
that the eye loses the line. Hangul advance in a typical face is ~0.966 em, not
1.0 — the measure arithmetic depends on it. Korean needs *looser* leading than
Latin: syllable blocks fill ~0.95 em of ink with no ascender/descender rhythm,
and many CJK faces already have a ~1.44 em natural line box, so `line-height:
1.5` is nearly set solid. Current default: 11.5pt / 1.75 / 18mm sides → 44.4
chars per line, 36 lines per page (both confirmed by measurement).
**Do not justify.** Chromium implements no `text-justify`, and hyphenation
cannot fire under `lang="ko"`, so all slack lands in word spaces — a wrapped
long Latin term can open a 4× river. Ragged right has no such failure mode.
Use `word-break: keep-all` with `overflow-wrap: break-word` (not `anywhere` —
`anywhere` shreds English headers and measurements mid-token in table cells).

### K14
**In this pipeline `h1` is every top-level section, not a chapter.** A paper's
Introduction / Method / Experiments are all `h1`, so `break-before: page` on
`h1` cost 4 extra pages on a 17-page paper and left ~4.7 pages of trailing
whitespace (vs ~0.9 without). Hence `section_break` defaults to **off**.
*Status: `layout.PRINT_PROFILES`. Measure before assuming a heading level means
what its name suggests.*

### K15
**A bare backslash inside injected HTML eats the next `<`.** The markdown reader
still applies backslash escapes inside a raw HTML block, so `<mi>\</mi>` became
a literal `</mi>` on the page. Two causes worth knowing: pass `--mathml` to
fragment conversions (without it pandoc emits raw TeX inside a span), and escape
backslashes as `&#92;` in anything injected — MathML keeps the original TeX in
`<annotation>`, so the block is full of them.
*Status: LOCKED — `test_backslashes_are_escaped_in_injected_html`.*

### K16
**A fidelity gate that counts the wrong thing is worse than none.** The table
check counted only *markdown* tables, so it printed "1 table, OK" while five
raw-LaTeX tables were being dropped. When adding a gate, ask what it does *not*
count.

### K17
**pandoc silently drops any LaTeX environment it treats as metadata.**
`\begin{abstract}` goes into document metadata, and converting to markdown
without `--standalone` discards it -- so every arXiv paper lost its abstract,
1500+ characters of the most-read part, with no warning and no gap in the
output to notice. `\begin{IEEEkeywords}` goes the same way. Rewrite them into
`\section*{...}` before conversion so they stay content. Starred, because a
numbered Abstract makes the Introduction section II.
*Status: LOCKED — `FrontMatterTests`.*

### K18
**`\IEEEPARstart{T}{raining}` is a word, not decoration.** IEEE's drop-cap
macro splits the first letter from the rest, so passing it through untouched
loses a real word from the first sentence and prints the macro as code.
Multi-line commands need brace-balanced removal too: `\markboth{...}` wraps
across two lines, and dropping only its first line left `FEB 2025}` stranded
mid-page.
*Status: LOCKED — `LatexLeftoverTests`.*

### K19
**`\[x\]` in generated markdown is an escaped bracket, not display math.**
pandoc's markdown *writer* escapes a literal `[object]` as `\[object\]`; the
*reader* then sees `\[...\]` and, with `tex_math_single_backslash` enabled,
re-reads it as display math -- so the word printed in math italic. Unescape
only when the content is plainly not math; this paper uses `$...$` exclusively,
so nothing real was at risk.
*Status: LOCKED — `test_escaped_brackets_stop_being_display_math`.*

### K20
**Strip LaTeX comments before reading structure out of a `.tex`.** This paper
has a `%\subsection{...}` the authors commented out. Counting it consumes a
letter and shifts every heading after it, so "D." silently becomes the wrong
section. The same applies to floats. And when the reconstructed ladder does not
line up 1:1 with the translation, label *nothing* — a heading numbered D that
is really E is worse than an unnumbered one.
*Status: LOCKED — `SectionNumberingTests`.*

### K21
**A 2-column Korean translation of a 2-column paper is not possible on A4.**
Hangul advance is ~0.966 em against ~0.5 em for Latin, so a column that holds
45 English characters holds 21 Hangul — half the 35–45 comfort band. Reaching
35 in an 84 mm column needs ~7 pt type. Restore *navigability* instead: the
original's section numbering (I./A./1)) plus the English heading in
parentheses lets a reader find the same section in the source.

### K22
**Do not infer document structure from formatting.** Nine of ten captions
arrived as `**Bold lead-in.** rest` because their LaTeX opened with
`\textbf{}`; the tenth did not, and a bold-based detector dropped it. Whether a
float has a caption is a fact recorded in the source — read `flat.tex` and look
it up. Same lesson as K10: resolve from the source or not at all.
*Status: LOCKED — `CaptionSourceLookupTests`.*

### K23
**Raw HTML survives the HTML path and nothing else.** pandoc drops it when
writing DOCX, so anything injected as HTML silently disappears there. This bit
twice in one session: figure captions as `<figure>` emptied book.docx of all
ten images (5.4MB -> 25KB), and tables as `<table>` left it with **zero**
tables while every check printed OK — the table gate reads the HTML. Prefer a
native markdown construct (`implicit_figures`, pipe tables) so every writer
sees real structure; inject HTML only where the HTML path alone needs it, and
build the other path its own copy.
*Status: LOCKED — `tests/format_probe.py` checks tables and images in DOCX,
EPUB and PDF; verified against the reintroduced bug.*

### K24
**Writing a finding down does not stop it happening.** K3 (shell heredocs eat
backslashes) was already in this log, with a merge-time guard — and it still
fired four more times in one session, destroying a test fixture outright,
because the guard sits at *merge* and the mistake is made at *authoring*. A
lesson only holds where the mistake is made: put the check in the authoring
step, or remove the sharp edge. Treat a repeat of a logged finding as evidence
that the mechanism is in the wrong place, not that someone forgot.

### K25
**Verify each output format, not the one you happened to look at.** The layout
probe measures the PDF, thoroughly — and that is exactly why two DOCX
regressions shipped unnoticed. A gate that covers one artifact reads as
coverage. When adding a check, ask which artifacts it does *not* look at
(see K16 for the same mistake at the level of what a check counts).

### K26
**Section numbering belongs to the document class, so it cannot be derived from
the .tex — read it off the source PDF.** Four papers, four answers: IEEEtran
prints `I.` / `A.` / `1)`, ICML's article prints `1.` / `2.1.` / `2.1.1.`
(appendix `A`, `A.1`), and CafeQ and AlphaQ print no heading numbers at all
while their body still says "Section 4.1" — the class hides the number, `\ref`
still returns the counter. The hard-coded IEEE ladder mislabelled all 41 of
SINQ's headings. `config.txt` records the input PDF; match each heading title
against it and use whatever prefix the page shows, `''` included.
*Status: LOCKED — `SectionNumberingTests` in tests/test_merge_and_build.py.*

### K27
**Strip presentation-only LaTeX before pandoc WRITES the markdown, not after.**
`\cellcolor` does not merely print as literal text. pandoc emits wide tables as
*simple tables*, whose columns are the positions of the dashes in the ruler
line; a cell carrying `` `\cellcolor{customblue!30}` `` overruns that ruler, and
reading it back splits the row at the ruler column instead — inside the
command, tearing it in half (`\cellcolor{cus` | `tomblue!30}`). Cleaning it
downstream cannot help: the damage is in the layout. Watch for macro
*definitions* too — SINQ has `\newcommand{\ours}[1]{\cellcolor{...}#1}`, two
definitions that pandoc expanded into 326 occurrences.
*Status: GUARDED — `sanitize_tex` in arxiv_backend.py, applied to the copy
handed to pandoc; flat.tex keeps the original as the fidelity reference.*

### K28
**pandoc's TeX reader implements none of the pre-LaTeX2e font switches and
fails the WHOLE formula on one.** `{\rm max}` does not degrade to "max": the
entire `$...$` fails to parse and reaches the page as literal source. CafeQ:
20 occurrences, 13 unrendered formulas, 90 visible backslash-commands.
Rewrite to `\mathrm{...}` (or to the bare operator, since `\mathrm{\min}` is
not valid TeX either).
*Status: LOCKED — `normalize_math_commands` tests.*

### K29
**`\paragraph` and `\subparagraph` are heading rungs.** pandoc turns them into
`####`, so a reader that counts only `\section`/`\subsection` comes up short
and the 1:1 ladder check refuses to number anything. This silently disabled
section numbering on all three of SINQ (42 vs 45), CafeQ (17 vs 25) and AlphaQ
(33 vs 39). They take no number of their own — every class here leaves them
below `secnumdepth` — but they occupy a rung.
*Status: LOCKED — `read_tex_headings` tests.*

### K30
**A `re.sub` replacement built from document text is a template, not a
literal.** A heading carrying math (`$\ell_2$`) put a backslash into the
generated TOC, and `re.error: bad escape \e` killed the build *after*
book.html was written and *before* the DOCX, EPUB and PDF existed. Two of three
papers produced no PDF at all. Always pass a callable. This is the second time
this exact bug has appeared in this file (see K24: fixing it in one call site
does not stop it in another).
*Status: GUARDED — every `re.sub` with a computed replacement in scripts/ now
takes a callable; audited 2026-08-20.*

### K31
**One image is not one figure.** A multi-panel float is ONE figure with panels
(a)(b)(c). Treating each image as its own figure made the caption-finder take
the *next panel's image line* as the current panel's caption and fold it into
the alt text — two of SINQ's thirteen images vanished from every output — and
consumed three figure numbers for one float, so every later figure was numbered
too high. Map panels to floats by FILENAME, never by position: SINQ has 17
`\includegraphics` and 13 image files, because tikz pictures and unresolved
graphics leave nothing behind.
*Status: LOCKED — `figure_panels` tests; figure numbers verified against the
source PDFs (14 checked, 0 mismatches).*

### K32
**Counting reader-visible LaTeX means stripping `<annotation>` first.**
`--mathml` keeps the TeX source of every formula in
`<annotation encoding="application/x-tex">`. Counting `\begin{` in the raw HTML
reported 28 defects for AlphaQ, which actually had zero — they were correctly
rendered equations. Strip annotations, then tags, then count. Also remember
`<style>` content survives tag-stripping, so CSS comments mentioning a LaTeX
command show up as false positives.

### K33
**Resolving a reference has to absorb the word in front of it.** `\ref` leaves
the word the author typed ("See Tab.~\ref{tab:x}") and `\cref` generates it, so
pandoc emits nothing ("in ( (eq:y))"). Substituting only the label gives
"See Tab. 표 16" in the first case and "( (1))" in the second. Match word and
reference together and emit the target language's own. Watch the regex: an
optional leading word plus `\(` lets the OUTER bracket of "(Sec. (sec:x))" be
taken for the reference's own, capturing "(sec:x" as the label.
*Status: LOCKED — `CrossReferenceSubstitutionTests`.*

### K34
**Dry-run the build on UNtranslated chunks before spending any translation
effort.** Copy each `chunkNNNN.md` to `output_chunkNNNN.md` verbatim and run
`merge_and_build`. Every structural defect — numbering, floats, tables, math,
cross-references, crashes — shows up in minutes, against source text you can
still read, and none of it costs a re-translation. K26 through K33 were all
found this way, before a single chunk was translated.

### K35
**A pandoc *simple* table cannot survive translation into CJK.** Its columns
are character positions in the ruler line, so a translator must choose between
readable Korean and byte-exact padding — and CafeQ's header row was already two
columns out of step with its own rule in the SOURCE, so faithfully reproducing
it printed "적함수" for "목적함수". Emit pipe tables instead: add
`-simple_tables-multiline_tables+pipe_tables` to the markdown writer, and every
cell boundary becomes an explicit `|` that nothing about width can move.
*Status: set in `arxiv_backend._WRITER`; measured 2026-08-20, pandoc 3.10.2.*

### K36
**Strip `<annotation>` anywhere heading HTML becomes plain text.** `--mathml`
carries each formula's TeX source in
`<annotation encoding="application/x-tex">` for copy-paste. Removing tags alone
leaves the rendered glyph AND its source, so a heading with math in it reads
`γ\gamma의 데이터 없는 기본값` in the TOC, the PDF bookmarks and the print TOC —
three separate call sites, all making the same mistake. The same blind spot
inflates any count of "leftover LaTeX" (K32).
*Status: LOCKED — `_ANNOTATION_RE` in merge_and_build.py and chromium_pdf.py.*

### K37
**A `\label` after `\end{figure}` names the enclosing section, not the float.**
LaTeX scopes a float's `\refstepcounter` to the float. AlphaQ writes
`\subsection{...}` `\begin{figure}...\end{figure}` `\label{app:hill-derivation}`
and the paper prints "Appendix A.3" for it. Suspending the section context on
`\begin` and never restoring it left the reference unresolved and printing raw
mid-sentence. Suspend on `\begin`, restore on `\end`.
*Status: LOCKED — `test_a_label_after_a_float_names_the_enclosing_section`.*

### K38
**A paper can carry two reference lists.** SINQ inlines its precompiled `.bbl`
in main.tex AND ships the `.bib` that citeproc reads, so both rendered — 29
entries printed twice. CafeQ ships no `.bib`, so its inlined list is the only
one there is and must be kept. The deciding fact is the one arxiv_backend
itself uses to choose citeproc: does the source contain a `.bib`? The unpacked
source stays in the temp dir, so this is answerable at merge time without
re-ingesting. Separately, citeproc's list arrives with no heading, because
`strip_pandoc_divs` removes the `::: {#refs}` wrapper it came in.
*Status: LOCKED — `BibliographyTests`.*

### K39
**Adding a heading changes the heading count.** Inserting "References" over the
rendered list before `number_sections` ran made the ladder 46 against flat.tex's
45, and numbering refused — correctly, for a reason that did not exist until
the step before. Anything that adds or removes a heading belongs AFTER the
ladder has been matched.

### K40
**A ⟦T####⟧ placeholder hides the table's caption and headers from the
translator.** The math guard wraps the whole `\begin{table*}` float so no
backslash can be damaged, and the caption and column headers go with it. SINQ
shipped 14 tables still in English inside an otherwise Korean book, AlphaQ nine
more, and nothing complained: every other check counts tables, images and
values, all of which were correct. Whether a paper is affected depends only on
how its floats are written, so check rather than assume:
`python tests/format_probe.py <temp_dir> --lang ko`. The pass that fixes it is
SKILL.md Step 4.6; the better answer — keeping `\caption{}` outside the
placeholder so it travels with the prose — is not yet done.
*Status: GUARDED — `check_table_language` in tests/format_probe.py.*

### K41
**`\resizebox` around a tabular makes pandoc throw the float's caption away.**
pandoc understands `\begin{table}` and tries to build a Table element; it
cannot parse `\resizebox`, so it emits the bare tabular as a raw block and
discards the `\caption`. `\begin{table*}` is not a standard environment, passes
through whole, and keeps its caption — so whether a paper silently loses
captions is decided by which of the two its authors used. AlphaQ lost six that
way, and one surviving table then displayed a neighbour's caption. Unwrapping
`\resizebox` before pandoc reads the source fixes it and, as a bonus, lets the
table come out as a real pipe table with its caption and label attached. The
print stylesheet already shrinks wide tables, so nothing is lost.
*Status: LOCKED — `ResizeboxTests` in tests/test_arxiv_backend.py.*

### K42
**Editing a `.math.json` sidecar does not invalidate `output.md`.** The merge
step is keyed on the mtimes of the `output_chunk*.md` files, so translating a
placeheld table's caption in its sidecar changes nothing until the merge is
forced. `--force-html` is not enough — it regenerates the HTML from the stale
`output.md`. Delete `output.md` and rebuild. Symptom: the sidecar reads Korean,
`format_probe --lang ko` reports it translated, and the PDF still shows English.

### K43
**Absorb the TARGET language's reference word, not just the English one.**
`\ref` leaves the word the author typed and `\cref` generates it, so the
substitution swallows "Tab." and "Eq." — but the translator writes the Korean
one, and that survived beside the emitted label: "식 식 (5)을 풀면", "표 표 12",
"부록 부록 A.1". 36 of them across three papers, and no check noticed because
the reference itself had resolved correctly. Build the lead pattern from the
language config's own labels, with a `(?<!\w)` guard so a compound like
"수식" is not split at "식".
*Status: LOCKED — `CrossReferenceSubstitutionTests`.*

### K44
**MathML Core has no `rowspacing`, so the rows of an `aligned` block touch.**
Measured 15.0pt and 18.0pt apart for 12pt math — a three-line equation reads as
one block. Chromium ignores `line-height` on `<mtr>`; what works is
`border-collapse: separate; border-spacing: 0 0.45em` (measured: 20.2/23.3pt).
Scope it with the child combinator — `math[display="block"] > semantics >
mtable` — because a matrix is an `<mtable>` too, nested inside an `<mrow>`
between its fences, and it should keep its tight rows (measured unchanged).
*Status: LOCKED — `test_multi_row_equations_get_row_spacing`; measured
2026-08-20, Chrome 149.*

### K45
**A translated term a reader cannot map back to its English is worse than the
English.** "두꺼운 꼬리" reads as ordinary words; "두꺼운 꼬리(heavy-tailed)" does
not. Gloss on first use only, and only for terms whose Korean is not
self-evident — glossing 비트 폭 or 퍼플렉시티 is noise. Measure rather than guess
which ones need it: count each glossary rendering and check whether the English
ever appears within ~40 characters of any occurrence. Watch for the same
English term rendered two ways in one paper (AlphaQ had 멱법칙 and 거듭제곱 법칙
for *power law*) — the per-chunk translators cannot see each other.

### K46
**Number the displayed equations, or the resolved references point at nothing.**
Once `(eq:ilp)` becomes "식 (5)", the equation has to show "(5)". What is
numbered is not a judgement call — LaTeX numbers a math environment unless it
is starred, and `\nonumber` drops a row's number inside `align` — and counted
that way all three papers matched the `(N)` markers printed in their own PDFs
exactly (7 / 5 / 27). Check that before labelling anything. Two render paths,
because they share nothing: HTML/PDF/EPUB take a `data-eqno` attribute the
stylesheet sets flush right (x=531 against a 544pt margin), while DOCX, built
by pandoc from prepared.md, takes it inside the formula after `\qquad`. Inside
the math on the HTML path it lands mid-column (x=177) and sticks to any copy.
*Status: LOCKED — `EquationNumberTests`; placement verified against flat.tex by
content, 0 mismatches.*

### K47
**LaTeX numbers a float when `\caption` runs — not when the environment opens.**
Counting `\begin{figure}` instead is wrong twice over, and both shipped. A
commented-out float numbers nothing: SINQ hides two behind `%` and every figure
after the first was one too high. One float can also carry two numbers: AlphaQ
puts two `minipage`s with their own `\caption` inside one `table*`, so every
later table was two too low. It stayed invisible because the caption side of
the pipeline stripped comments and the cross-reference side did not — the
caption under the plot read "그림 6" while the sentence pointing at it read
"그림 7", and each looked right on its own. `float_units()` is now the single
reader both sides use; a `\caption` inside a `subfigure` is a subcaption and
numbers nothing.
*Status: LOCKED — `ReferenceResolutionTests`; verified against all three source
PDFs, 0 disagreements.*

### K48
**pandoc reads a fixed set of figure constructs; anything else is dropped in
silence.** `resolve_images` only rewrites images pandoc already emitted, so a
construct pandoc has no reader for takes its `\includegraphics` down with it —
caption still printed, plot gone, no warning. Three did this: `\subfloat`
(subfig) cost SINQ its Figures 4 and 5; `\begin{SCfigure}` (sidecap) cost
CafeQ its Figure 1; and `\includegraphics[page=N]` on a multi-page figure PDF
lost the page number with the option list, so CafeQ's Figure 3 showed page 1
three times — one wrong plot and one duplicate, which is worse than a gap
because it looks like a figure. All three are unwrapped or rewritten at ingest
now. Count figures against the original PDF before believing a missing one is
tikz.
*Status: LOCKED — `FigureSurvivalTests`, `GraphicPageTests`, `GraphicStemTests`.*

### K49
**A position-delimited table cannot survive placeholder restoration.** pandoc's
simple and multiline tables mark columns by character position, and a cell
holds `⟦M0093⟧` while the chunk is translated but real LaTeX after the merge
restores it. The columns then fall wherever they like: a header cell came out
reading `w$ Wiki2 ↓\downarrow`, split through the middle of a math span, and
another lost its first three characters (`**B**` → `*B**`). The writer emits
`+pipe_tables-simple_tables-multiline_tables` for exactly this reason; the
damage is only visible in the built HTML, so check header cells there for a
stray `$`, `\cmd` or `**` rather than trusting the markdown.
*Status: GUARDED — writer flags in `arxiv_backend._WRITER`; 0/39 damaged
headers across the three books after repair.*

### K50
**A source chunk's hash is what decides re-translation, so repairing one in
place has to re-hash it.** Patch a chunk and leave `manifest.json` alone and
the next run quietly re-translates it — paying again for text that was already
right, and discarding any review done on it. After any in-place repair: re-hash
the entry, `run_state.py record` it, then confirm `run_state.py plan` reports
an empty `translation_chunk_ids` before rebuilding. The same reasoning makes
the glossary something to settle *before* a run: every edited term
re-translates each chunk that uses it.
*Status: GUARDED — `run_state.py plan` reports it; nothing enforces the order.*

### K51
**Every check here compares the build against itself, except one.** Section,
figure, equation and cross-reference numbers are all reconstructed from
`flat.tex`, and a reconstruction can be perfectly self-consistent and wholly
wrong: an early version numbered SINQ's headings `I. / A. / 1)` because that
is what IEEEtran does, while the paper prints `1. / 2.1.` — 41 headings
labelled confidently, every other probe green. `source_probe.py` reads the
numbers the original PDF actually prints and compares. It found K47 after the
books had already been built, verified, and reported as correct.
*Status: LOCKED — `tests/source_probe.py`; `ProbeContextTests` covers the
context matching, which is where its false positives came from.*

### K52
**pandoc measures a grid or simple table by DISPLAY width, so translating one
into a wide script breaks it.** A Hangul syllable is two columns. Pad a cell to
the same *character* count -- what a sub-agent naturally does -- and the row
runs 59 display columns against a 54-wide border, so the `|` stop meeting the
`+`; pandoc abandons the table and emits one cell per line with the pipes left
in as text. Nothing notices, because it is still a `<table>` with rows and
cells: table counts, image counts and value probes all pass while the reader
sees `방법 | UNIFORM | ...` as prose. CafeQ shipped three that way and its
all-ASCII table was fine, which is the tell. `_WRITER` now disables grid tables
too, leaving pipe tables, which have no alignment rule to drift; the cost is
that a column span flattens into its first column.
*Status: LOCKED — `CollapsedTableTests` + the format probe's collapsed check.*

### K53
**pandoc rewrites a raw table's shape on the way out, twice over.** It expands
`*{9}{r}` when reading, then emits the ORIGINAL spec plus the expansion --
`{l l l*{9}{r}rrrrrrrrr}`, 21 columns where the paper has 12. Ten of SINQ's
nineteen tables rendered with nine empty columns after every row, the numbers
squeezed into half the page, and every count still tallied. Separately it drops
`\rotatebox{90}{..}` and `\multirow{4}{*}{..}` whole, argument included, so the
label a narrow column carries disappears. Both are handled at ingest now, and a
book already converted keeps its tables as raw LaTeX in the math sidecars, so
both repair there without touching prose. Check column counts against the
tabular preamble, not against each other.
*Status: LOCKED — `ColumnSpecTests`, `BoxedLabelTests`; SINQ 10 ragged -> 0.*

### K54
**A figure panel drawn at full text width cannot share a page with anything.**
Measured: a panel fills about 125mm against a 257mm text block, so two never
fit and every panel of a multi-panel float got its own page. SINQ ran 36 pages
of which seven held one picture and fourteen characters, the three panels of
one figure three pages apart and useless as a comparison. Panels are now sized
by how many the float has -- the largest width that still fits one page: 80%
for two, 55% for three, 38% beyond. SINQ came to 31 pages, one sparse page
left. That remainder is inherent: each panel is its own unbreakable block, so
text above pushes the last one over, and closing it would mean one HTML block
per float, which is what empties the DOCX (K1).
*Status: LOCKED — `PanelWidthTests`; 38% of 174mm is 66mm, wider than the
~40mm the same panels get in the printed original.*

### K55
**Our own reader turns an escaped bracket back into display maths.** pandoc's
markdown writer escapes a literal `[` as `\[`, and PANDOC_FROM carries
tex_math_single_backslash, so `\[..\]` is read back as a formula. SINQ's
`\textbf{Overhead [\%]}` -- the units of a column -- became a display formula
holding one `%`, which renders as nothing: the header read "오버헤드" and
stopped. Neither side is wrong on its own, which is why it survived three
builds and two sweeps. The guard is now content-based: a formula carries a
command, an operator, a relation, a subscript or a Greek letter, and a unit in
brackets carries none of those.
*Status: LOCKED — `EscapedBracketTests`, and `unbracket` accepts `%`/`°`.*

### K56
**`pandoc -t markdown` picks the table style itself, and its choice can lose
the table.** The DOCX path renders each raw LaTeX table to markdown, because
pandoc drops raw HTML when writing DOCX (K1). For anything wide or spanned the
plain writer chooses a SIMPLE table -- columns by character position, no `|`
anywhere -- which `_is_markdown_table` cannot recognise, so the table fell
through to plain text. Nine of AlphaQ's twelve tables and one of SINQ's
nineteen were prose in the Word file while every count agreed with itself,
because the HTML path had all of them. Pin the writer to pipe tables and turn
the `::: table*` div off with it.
*Status: LOCKED — `FragmentWriterTests`; AlphaQ DOCX 3 -> 12 tables,
181 -> 201 equations.*

### K57
**Nothing in this pipeline fails; it disagrees.** Every defect shipped so far
lived at a boundary between two tools that were each correct. pandoc escapes a
literal `[` as `\[`, our reader reads `\[..\]` as maths (K55); pandoc lays a
grid table out by display width while a translator pads by character count
(K52); pandoc expands `*{9}{r}` and re-emits it beside the expansion (K53).
None logged anything, because none had a problem. The corollary is about
checks: counting agrees with itself. When nine of twelve tables fell out of
the Word file, the table count, the image count and the value probes all
passed -- the HTML had all twelve, and three is not zero (K56). A count is
evidence only against something the same code path did not produce.
*Status: measured over three reviews of three books; the ordering it implies
is in AGENTS.md, "How this pipeline breaks".*

### K58
**Resolving a reference changes the sentence after the translator has left.**
Korean picks a particle by how the preceding syllable is pronounced, and the
sub-agent wrote one after `(fig:dual_scale)` -- it never saw the number this
pass would substitute in front of it. Twelve shipped: "그림 1를", "표 9은",
"그림 9과". A Korean reader stops at every one, because 1 is read 일 and ends
in a consonant. No probe saw it: the reference resolved, the number is right,
the markup is valid. The fix belongs where the substitution happens, not in
the translation prompt -- the translator cannot know. Only `ko` turns it on.
*Status: LOCKED — `ParticleAgreementTests`; 12 -> 0 across three books. The
key is declared for every language so the config stays answerable, and a test
checks it is declared ONCE: a duplicate silently wins and turns it off.*

### K59
**Papers ship broken sentences, and the translation takes the blame.** CafeQ's
published PDF reads "...particularly in the attention modules. which in
contrast, aims to quantize an already-trained model" -- a relative clause with
no antecedent, evidently the tail of a deleted sentence. Translate it
faithfully and the Korean has a pronoun pointing at nothing; repair it quietly
and the book says something the paper does not. Do both: translate faithfully
and add `*[역주: …]*` right after, naming the problem as the original's.
`dry_run.py` reports these before translation starts, which is the only moment
the choice is cheap. Detect only RELATIVE pronouns opening a sentence --
"While", "Since" and "Because" open one perfectly well, and including them
buried the single real hit under fifteen false ones.
*Status: LOCKED — `SourceSanityTests`; 1 real instance in three papers.*

### K60
**Every link in the web TOC was dead, on all three books.** The generator built
`<h2>text</h2>` and str.replace()-d it to add an id, but pandoc writes
`<h2 id="slug">`, so the string never matched and no anchor was ever created --
while the sidebar happily linked to `#heading-1`, `#heading-2` and so on. The
one heading it did rewrite was the sidebar's own `<h3>목차</h3>`, which has no
attributes. Nothing noticed because the file exists, the TOC renders, and the
links look fine until clicked. It now reuses the anchor a heading already has
and only invents one when there is none.
*Status: LOCKED — `WebTocAnchorTests`; 123 links across three books, 0 dead.*

### K61
**A fix landed on Tuesday is a defect on Wednesday unless something re-reads
it.** The particle pass (K58) turned a correct "8로" into "8으로" on its first
outing: 으로/로 is the one pair that does not follow the coda rule, because a
final ㄹ takes 로 -- and 일, 칠, 팔 all end in ㄹ. It shipped. The empty-span
rule, added the same day, destroyed a ``double-backtick span`` and rewrote
inside fenced code. Both were found by feeding the new code its own edge cases
and DIFFING what it changed on real text, which is the check that turns a
plausible rule into a verified one. Do that before rebuilding, not after.
*Status: LOCKED — `ParticleAgreementTests`, `EmptyCodeSpanTests`.*

### K62
**Number the table captions too, and take the caption from the right half of
the float.** Figures carried a number and tables did not, so the body said
"표 5에서 보듯이" over a caption with nothing to match -- the gap equations had
before K46. Do it on the merged markdown: that is the last point where a raw
LaTeX table still has its `\caption{}` and a pandoc table still has its `: `
line, so one pass covers both output paths. Walk CAPTIONS, not tables: AlphaQ
puts two minipages with their own caption inside one `table*` (K47), and
walking tables stamped both badges onto the first. The same float exposed a
second bug -- `_extract_caption` returned the float's FIRST caption for both
tabulars, so table 3's text was nowhere in the book. Each tabular takes the
caption above it.
*Status: LOCKED — `TableCaptionNumberTests`, `FloatCaptionOwnershipTests`;
19/8/12 captions numbered 1..N, checked against each source PDF.*

### K63
**`text-align: center` does not centre a display formula.** On a block
`<math>` it centres the inline content around the formula, not the formula, so
every display equation printed hard against the left margin -- x=51 on a page
whose centre is 297, in a stylesheet that had said `text-align: center` all
along. Measured across four candidates: `width: fit-content` + `margin: auto`
centres but shrink-wraps the element, which drags the equation number in from
the margin (330 instead of 531); `text-align: -webkit-center` centres the
paragraph and not the maths. `display: flex; justify-content: center` centres
the formula AND keeps the element full width, so `right: 0` still lands in the
margin. Pad BOTH sides for the number, or the formula sits 17pt left.
*Status: LOCKED — `DisplayMathCenteringTests`; 39 numbered equations, worst
|offset| 42pt against 212pt before.*

### K64
**Deleting `\cmidrule` cost the table its structure, not just a line.** It was
stripped because pandoc leaves its argument behind, so "4-6" printed in a cell.
But pandoc also uses a rule to find where a header ends: with them gone, SINQ's
main results table and three of AlphaQ's produced NO `<thead>` -- no rule under
the header, no header repeated across a page break, not one cell a `<th>`. Nine
numeric columns under nothing, and no check looks at rules. Two fixes: count
the header rows off the LaTeX (first `\midrule` with a row above it) and
promote them in the HTML, which works for every shape and for books already
converted; and at ingest keep a `\cmidrule` AFTER the header as a `\midrule`,
since that one separates row groups. CSS underlines a column group from its
`colspan`.
*Status: LOCKED — `TableHeaderPromotionTests`, `TableRuleTests`; 19/19.*

### K65
**A paper marks its row groups three ways and pandoc renders none of them.** A
rule between models, mere `\addlinespace` between the bit budgets nested inside
each one, and a `\midrule` above the Average block at the foot. AlphaQ's Table 1
uses the first two and its bit groups ran together; CafeQ's per-task table uses
the third and four averages followed sixteen benchmarks with nothing between.
Space cannot survive a one-row-tall HTML cell, so the softer boundary becomes a
lighter rule -- solid between models, hairline between bit groups -- keeping the
hierarchy, which was the point. The summary block is found in the HTML instead:
a table pandoc could convert took the markdown path, and pipe syntax carries no
rule. Scoped to the last third of a long table it fires once across three
papers, exactly where the source rules.
*Status: LOCKED — `SoftGroupRuleTests`, `SummaryRowRuleTests`.*

### K66
**Turning a table format off does not make a table safe; it makes it vanish.**
Grid tables mark columns by character position and pandoc lays them out by
DISPLAY width, so a Hangul cell collapses one (K52). Disabling `grid_tables`
looked like the fix and cost CafeQ a whole results table: it is pandoc's
only format for a spanning multi-deck header, and without it pandoc writes
the literal text `[TABLE]` in its place. Leave it on and convert at MERGE
time, once the translator is done and nothing can drift further -- reading
cells from the `|` separators, never from column positions, which are
exactly what has gone wrong by then. A row-spanning table has no pipe
equivalent, so copy it verbatim in ONE piece: bailing out line by line let
the scan re-enter mid-table and eat the borders it had just spared.
*Status: LOCKED — `GridTableConversionTests`; 8/8 CafeQ tables, 0 collapsed.*

### K67
**A stylesheet can be correct for one format and absent from the other two.**
Every table rule -- header underline, column-group underline, the two weights
of body rule -- was declared inside `@media print`. The PDF was right, and
that is the file that gets looked at. An e-reader never applies a print
sheet, so the EPUB showed a flat grid; worse, Calibre found no active rule
for `.rule-above` and deleted the class from the markup, so the built book
had zero of them and nothing in it recorded that anything was lost. Declare
structure in the base sheet and let the print block override; a background
fill is not a substitute, because print is designed never to rely on one.
Check a format by opening THAT format: `book_doc.html` had all 20 rules
while the EPUB beside it had none.
*Status: LOCKED — `TemplateRuleTests`; EPUB 29 hard / 26 soft / 54 header.*

### K68
**Count the thing only the builder writes, never the thing a reader says.**
The caption check matched `표\s*\d+` and deduplicated -- which also matches
every cross-reference in the prose. CafeQ's 19 hits collapsed to 8 distinct
numbers, exactly the caption count, so it printed 8 of 8; deleting a caption
outright did not move it, because the prose still mentioned that table. Only
`number_table_captions()` writes the full badge `표 5 (Table 5)`, so that is
the anchor, built from the same `table_label` the builder uses. Never
deduplicate: the duplicate IS the finding when a caption is stamped twice.
With an English target the badge is only "Table 5", which is also how the
prose refers to it -- no anchor exists, and the check says so rather than
report a number it cannot stand behind. Break a new check five ways first.
*Status: LOCKED — `CaptionNumberTests`; 5 injected faults, 5 caught.*

### K69
**pandoc marks one Word header row, or none.**
`<w:tblHeader/>` is what makes Word repeat a header after a page break, and
pandoc sets it only where it found a single header row. Every table with a
two-deck spanning header -- 13 of SINQ's 19, and precisely the tables a
reader most needs labelled -- broke across a page in Word with bare numbers
below the fold, while the ebook built from the same `table_structures()` plan
had it right. `mark_docx_header_rows()` marks the rest after pandoc has
written the file, in schema order (`w:tblHeader` follows `w:trHeight`, and
Word rejects the whole document if trPr children are out of order). It never
unmarks: where the source is silent, pandoc's answer stands.
*Status: LOCKED — `DocxHeaderRowTests`; 19/19, 8/8, 12/12 full depth.*

### K70
**A sub-agent reports success by finishing, and so does a broken one.**
Nothing asked whether a translated chunk was in the target language. The two
checks that existed ran at the MERGE -- placeholders and image refs -- hours
after every chunk had been paid for, and `run_state record` only asked
whether the file was non-blank. `verify_chunk.py` compares the output against
the source, the glossary the agent was handed, and the chunk it was told to
quote from; never against its own account. Calibrated on three reviewed
books, 40 chunks, 0 false positives, and every check proven by breaking a
real chunk twenty ways. That is how `check_neighbor_leak` was found reading
`previous`/`next` instead of `prev_excerpt`/`next_excerpt`: incapable of
finding anything, and passing everything, until a test demanded a catch.
*Status: LOCKED — `test_verify_chunk.py`, both directions.*

### K71
**Translation changes words. Anything else it changed is a defect.**
Step 4.6 has agents edit raw LaTeX in place, then asked them to confirm their
own `&` and `\\` counts -- the same report from an agent that miscounted as
from one that did not. The invariant is exact: the multiset of numbers, the
row count, the `&` count per row and every `\multicolumn` span must survive
a translation untouched, while captions, header cells and `\textbf{}`
wrappers may change freely. `verify_tables.py snapshot` must run BEFORE the
agents and `check` after; check refuses without a snapshot, because a
baseline rebuilt from the edited files is not one. Proven by corrupting a
real SINQ table four ways, with a legitimate rewording left silent.
*Status: LOCKED — `test_verify_tables.py`, 15 tests both directions.*

### K72
**A glossary that omits the hard words has not deferred the decision, it has
distributed it.** AlphaQ's held 79 terms and none of its statistics
vocabulary, so fifteen sub-agents each chose 절단/섭동/정식화 alone: the book
said 절단 멱법칙 and 절단된 멱법칙 on different pages, and used 적합 for
"fit", "suitable" and "overfit" at once. Everything passed -- placeholders
intact, counts equal, prose fluent. Three treatments, decided per term and
recorded: settled Korean kept (꼬리, 고윳값, 우도 -- do NOT over-English),
stiff calques reworded (정식화 -> 정의), rare renderings left in English
(perturbation, truncated power law, surrogate). Two rules are not taste: one
word may not carry two senses, one term may not have two spellings.
*Status: LOCKED — `test_term_consistency.py`; drift fails, homographs
report only (they cannot prove a collision without sentence alignment).*

### K73
**A reference nobody can see is a reference nobody follows.**
Every 그림 N, 표 N and 식 (N) was black body text: the book carried 48 link
annotations -- its contents page and ten URLs -- against the source
preprint's 332, and a reader scanning for the figure under discussion had
nothing to catch the eye. Anchor the targets, then link the prose, and
only where the target is certain: figures, tables and numbered equations
resolve exactly, while citations and appendix subsections have no anchor
to resolve to and get colour alone -- a citation pointing at the wrong
paper is worse than one pointing nowhere. Two ordering traps: the pass
must run AFTER equation numbering (it ran before and anchored none of 27),
and a caption is a label, not a reference.
*Status: LOCKED — `test_xref_links.py`; 0 unlinked prose refs, #001473.*

### K74
**A bibliography arrives in three shapes and only one of them is delimited.**
`\begin{thebibliography}` (SINQ, CafeQ) is exact -- inside it every line is a
reference whatever shape it has, including "Tom Brown, Benjamin Mann" author
lines that no surname pattern matches. A `## References` heading is reliable
when present. AlphaQ has NEITHER: citeproc emitted bare paragraphs and the
heading is added later, during the build. Any check written against one form
silently misses the others, and the ones it misses are whole papers. Two
shapes also read as citations without being any: a footnote (`[^2]: … Martin
et al. 2021`) and a sentence opening on a connective ("Second, AlphaQ relies
on … Mahoney 2019") both carry a year and an author-comma-capital.
*Status: LOCKED — `test_convert_bibliography.py` covers all three shapes;
`ReferenceExemptionTests` covers the two false ones.*

### K75
**A third of what the translators were given came back unchanged.**
Measured on three papers: the reference list was 27%, 32% and 34% of the
characters handed to the sub-agents, and it is kept in the original language
by decision, so all of it was paid for twice -- once to send, once to receive.
It was also the LARGEST chunk in two of the three (CafeQ: 25,296 characters,
a third of the paper in one chunk), so it set the wall-clock floor as well:
no scheduling change can help a batch that waits on it. For scale, the build
stage is 22.3 s and all four verification probes together are ~1 s, so the
cost of a run is essentially the agent calls and nothing else.
*Status: measured 2026-08-25 on SINQ, CafeQ, AlphaQ.*

### K76
**A hyphenated compound and its spaced form are one term; `re.escape`
says they are two.** The glossary held `power law`; AlphaQ writes
`power-law mapping`; the matcher escaped the source verbatim, so
chunk0010's term table came out with ZERO rows for it. That sub-agent,
never shown the canonical rendering, wrote 거듭제곱 법칙 while every other
chunk said 멱법칙 -- and sub-agents cannot see each other, so nothing
local was wrong. The same trap waits on bit-width, heavy-tailed,
zero-shot and every compound in this field, and on U+00A0, which arXiv
puts between a name and its year. Space, hyphen and non-breaking space
are one separator between the words of a term -- flexible, never
optional: `power law` must not match `powerlaw`.
*Status: LOCKED — `SeparatorFlexibleMatchingTests`; 0 rows -> 1.*

### K77
**In Korean, a check that stops at `(?![가-힣])` stops at the common case.**
`check_doubled_labels` refused any label followed by a Hangul syllable, to
avoid matching 표 inside 표현/표시/표준. But Korean attaches a particle to
almost every noun, so `3.2절 절을 따라` — the reference already carries its
label and the translator added another — was invisible, and the probe
reported zero doubled labels on a build that had one. The guard is still
needed; it just needs the other branch: the second label may be followed by
a PARTICLE, and by nothing else. Any check written against Korean text has
this shape of hole, because the thing you want to exclude and the thing you
want to allow both look like "more Hangul".
*Status: LOCKED — `DoubledLabelTests`; 8 particles, 3 look-alike words.*

### K78
**pandoc deletes a raw LaTeX block on the HTML path, and no count notices.**
`⟦T####⟧` restores a float verbatim into the markdown. The pipeline converts
`tabular` itself, so tables survive; everything else goes to pandoc as raw
TeX, which pandoc emits only for LaTeX output. Every `algorithm` float this
pipeline handled was deleted between output.md and book.html while the build
reported success: the checks count tables, images, equations and captions,
and nothing counted the float. Two papers shipped without the algorithm that
is the point of the paper. A check that counts what it knows about cannot
see what it does not; its replacement asks the artifact whether each
raw-LaTeX block still has prose on the page.
*Status: LOCKED — `test_algorithm_float.py`, 30 tests; fires on both real
books before the fix, silent on all three after.*

### K79
**A check with a ceiling and no floor moves the book one way.**
`check_glosses` failed a term glossed three times; nothing asked whether a
term was glossed at all. Between two versions the term tables grew from ~74
to ~128 entries, sub-agents stopped annotating terms the table had already
decided for them, and three books lost about half their `한글(English)`
first-use annotations. Every probe stayed green: the only gloss number
printed was a collision count, and it went down. A reader caught it. When a
check bounds something from one side, print the other side too — even where,
as here, no threshold is defensible and the honest output is a count to
compare against the last build.
*Status: LOCKED — `test_gloss_first_use.py`; prompt floor, merge dedupe,
`check_gloss_coverage` reporting a count rather than a ratio.*

### K80
**A float that carries its own `\label{}` never got the number anchor.**
The label arrives as the element's HTML id, an element holds one id, and
`_add_id` returns a tag that already has one untouched — so no `tab-N` was
created, while every reference had already been rewritten to `#tab-N`. A
dead in-page link does not error, does not print, and changes no count: six
of CafeQ's eight tables and five of SINQ's nineteen shipped that way, in the
first build as well as the second, and the only reason it surfaced at all
was that a v1-vs-v2 diff put the link totals side by side. The id stays
where the source put it; the number goes on the caption, which is inside the
float and where the reader lands.
*Status: LOCKED — `test_anchor_targets.py`; every announced target must be
an id that exists in the document.*

### K81
**An image was not a figure because something followed it on the same line.**
The pattern required the line to end at the closing parenthesis, and CafeQ's
figure 1 arrived as ``![image](…png) `{-2em}`{=latex}`` — a spacing directive
the source parked there. So the float was never recognised: no number, no
printed label, no anchor, and its caption left behind as ordinary prose,
while three cross-references went on saying "그림 1". The previous build of
the same paper kept all three, because there the directive happened to land
on the next line. When a pattern anchors on "nothing else on this line",
ask what the converter is entitled to put there.
*Status: LOCKED — `test_figure_spacing_span.py`; a trailing brace-wrapped raw
span is allowed in, one carrying real content is not.*

### K82
**The resolver matched `[@key]` and the reader was shown `@key`.**
`\citep{}` comes out of pandoc bracketed, `\citet{}` comes out BARE — the
author's name is meant to carry the sentence — and the substitution pattern
only saw the bracketed form. So every author-in-text citation printed a raw
bibtex key: CafeQ shipped five, one of them standing beside a citation that
had rendered perfectly, in a build where all 61 labels had been harvested
from the paper's own `.bbl` and were sitting in the map the resolver held.
Nothing failed and no count moved; one pattern was narrower than its input.
A split `\citep{A, B}` also arrives as `@A [@B]`, so the two halves are
rejoined rather than printed as two brackets in a row.
*Status: LOCKED — `test_citation_intext.py`; bare and bracketed forms, the
in-parenthesis case, and email / unknown-key / escaped-`@` safety.*

### K83
**Two checks looked at the tables and neither looked at the paper.**
`source_probe` does read the original — and counts NUMBERING: section,
figure, equation and reference numbers, not one cell. `verify_tables`
compares each table against a snapshot of OUR OWN files, so a value the
conversion dropped before the snapshot was taken is recorded as correct and
passes forever. CafeQ shipped twelve values short in table 1 and six in
table 5, its group headers over the wrong columns, and both checks green.
Every table defect here was found by a person reading the page.
*Status: LOCKED — `tests/table_probe.py` asks what neither asked: does the
built table still say what the source `tabular` says? Fires on all three
pre-fix books, 9/34/10 findings, each matching the hand audits.*

---

### K84
**`\mathbf` is math-mode only, and a `tabular` cell is text mode.**
`normalize_math_commands` modernised every `{\bf ...}` in the document. In
CafeQ's table 4 that turned `{\bf 46.6}` into `\mathbf{46.6}`, the renderer
could not parse the cell, and the row — three numbers the paper reports —
was dropped while the build printed `8 converted, 0 failed`. v1 shipped
those numbers and v3 did not. Scoping the rewrite to math document-wide is
not available either: that needs `$` to pair, and in CafeQ's prose five
Korean sentences parse as formulas. The line is drawn at the raw table,
which this module can find exactly. The pass had no test at all.
*Status: LOCKED — `tests/test_math_font_scope.py`, both directions.*

---

### K85
**pandoc reads markdown inside raw HTML, and a formula is full of `*`.**
`markdown_in_html_blocks` is on by default. The raw-LaTeX tables are emitted
as finished HTML with MathML inside, so a literal `*` in one formula paired
with the next one down the table and spliced an `<em>` through the middle of
both. CafeQ's table 3 printed `45.6^{}` where the paper prints `45.6*`, and
the asterisk its own caption explains was gone. Five formulas in CafeQ, one
each in SINQ and AlphaQ. Every count balanced: 225 asked for, 225 delivered.
Nothing in these blocks is markdown, so the parsing has nothing to do but
damage.
*Status: LOCKED — reader flag off, and `find_spliced_math` fails the build.
`tests/test_math_splice.py`.*

---

### K86
**A band label is written as one box inside another, and one pass misses it.**
`unwrap_rotatebox` handled `\rotatebox` alone and `\multirow` alone. SINQ
writes all 32 of its labels nested — `\multirow{4}{*}{\rotatebox{90}{...}}` —
and a single pass took the outer call, then stepped the cursor past the whole
group, so the inner one started behind the cursor and was skipped. pandoc
then dropped it with its body. Nine of nineteen tables lost their group
column: table 1 printed the same four method rows twice with nothing saying
which block was 3-bit and which was 4-bit.
*Status: LOCKED — the unwrap runs to a fixed point;
`tests/test_rotatebox_nesting.py`.*

---

### K87
**`threeparttable` is two commands pandoc has no reader for, and it eats both.**
`\tnote{$\dagger$}` marks a row; `tablenotes` says what the mark means.
pandoc drops each call with its body, so SINQ's tables carried 17 daggers in
the source and 4 on the page, and all four note blocks were missing
entirely — a marker with nothing anywhere explaining it. The float span is
replaced wholesale by the rendered table, so anything in the float that is
not the tabular or the caption is simply not carried over.
*Status: LOCKED — `\tnote` becomes a superscript and the notes are emitted
under the table, deduped per float.*

---

### K88
**A float span that reaches too far does not mislabel — it deletes.**
The expander writes `md[cursor:start]`, then the table, then sets cursor to
`stop`. `_widen_to_float` searched back 4000 characters for a `\begin{table}`
without testing whether that float had already closed, found the PREVIOUS
one, then searched forward and found the NEXT one's `\end`. SINQ's table 5
came back with a span 22,038 characters wide, and the prose inside it was
skipped: 316 Korean words gone from SINQ, 194 from AlphaQ. Every table was
still counted and every number was still in its cell. CafeQ, whose spans
never overlapped, lost nothing — which is what pinned the cause down.
*Status: LOCKED — `tests/test_float_span.py`; the loss measured at zero on
all three books by running the expander step alone.*

---

### K89
**A protected float is carried verbatim, so every pass that mends the body
skips it.** The float is kept exactly as flat.tex wrote it, which is what
saves its table from pandoc — and also means the citation resolver, the
leftover-command pass and the colour rewrite never see inside. Three things
were being deleted there, none of them counted: `\citep{}` (CafeQ's table 6
lost all sixteen sources it exists to record), `\text{PQE}` (table 7 printed
no header over the column it is sorted by), and `{\color{red} 17.14}` (SINQ's
captions tell the reader to look for red; twelve marked values printed
black). Anything the body gets, the float has to be given again explicitly.
*Status: LOCKED — `tests/test_table_fragments.py`; red now matches the
original exactly, 12 values, no more and no fewer.*

---

### K90
**Math that is display where it should be inline breaks the line it is on.**
Two of them. `Constraints on $\tx$` expands to `$\ensuremath{M}$`, and
wrapping that body in dollars again gives `$$M$$` — pandoc emits a centred
block, and one heading printed across three lines with a lone `M` in the
middle of the page. Separately, a matrix written inline gets Chromium's
compact style and its rows close to 7.5pt at 12.1pt type, so a 2×2 overlaps
itself and a worked example cannot be read. Neither is a missing element;
both are elements laid out as the wrong kind of box, which no count can see.
*Status: LOCKED — `tests/test_heading_math.py`; matrix rows measured
7.5pt → 14.2pt, against 12.7pt for the display form.*

---

### K91
**A whole reference list can go missing, and a test can hold the door open.**
Where the source inlines its own `.bbl` and ships no `.bib`, nothing else
renders the references — and the code kept the `thebibliography` environment
exactly as it was, which hands pandoc raw LaTeX on the HTML path. All 61 of
CafeQ's entries reached output.md and none reached the book: 19 in-text
citations pointed at a list that was not there, and no check counts a
reference. A test asserted precisely that behaviour, docstring naming CafeQ,
so the suite was green the whole time. `\newblock` compounds it — pandoc
takes the group after it as an argument, so `{FrameQuant}: Flexible…` prints
as `: Flexible…`, the method's name gone from its own title.
*Status: LOCKED — the entries are rendered here; `tests/test_merge_and_build.py`
now asserts the list reaches the page, and 61 of 61 do.*

---

### K92
**Walking a list backwards, one odd entry ends the walk.**
The heading over a citeproc bibliography is placed by finding where the run
of entries begins — walked back from the last one while the blank lines
between entries stayed regular. One long preprint entry carrying a blank
line inside it stopped the walk at once, so of AlphaQ's 52 references the
run kept one: `참고문헌` printed between the last two entries, six pages
after the list began, and the contents page sent the reader there. The edge
of a list is a heading or a paragraph of prose — not a count of blank lines.
*Status: LOCKED — heading and first entry now share a page in both books
that have a rendered list.*

---

### K93
**One float, one caption — and no width on the panels.**
A multi-panel figure arrives as one image per paragraph, so the markdown
reader makes every panel its own `<figure>`. The float's caption then prints
under whichever panel carried it in the source: SINQ's figure 2 explained
panel (a) from beneath panel (c), a page later. Group the panels in a fenced
div and close it with the caption. The second half matters as much: an
inline `width:33%` on a panel image is 33% of that panel's OWN box, so the
row never divides and each panel takes a line to itself — one float spread
down a whole page. Drop the width and let the row share itself out.
*Status: LOCKED — read on the page for all three books; SINQ went from 33
pages to 29 and lost all three of its near-empty pages.*

---

### K94
**Three symptoms, one residue on the image line.**
CafeQ printed `{-2em}` in monospace, its figure 1 carried no `그림 1` label,
and its caption read as ordinary prose. One cause: `\vspace*{-2em}` survives
as a raw inline at the end of the image line, an earlier pass takes only its
`{=latex}` marker, and the figure formatter — widened to tolerate a trailing
RAW span — stops recognising the line as an image at all. Page geometry with
nothing in it to read costs far more where it sits than what it prints.
*Status: LOCKED — the label, the caption and the leak all come back
together when the whole span goes.*

---

### K95
**The book named no one.**
All three title pages went from the title straight to the abstract. The
authors were known the entire time: `apply_template_to_html` wrote them into
a `<meta name="author">` and nothing ever laid them out, because the template
spends `$title$` on `<head>` alone. A paper that does not say who wrote it is
not a paper — and the data was already in hand, so there was nothing to
weigh. The fix is a byline after the title's `<h1>`, before the TOC is added.
*Status: LOCKED — byline on the title page of all three books.*

---

### K96
**A lookbehind cannot see across a slice boundary.**
A `{=latex}` orphaned by a lost code span is markup with nothing left to
mark, and dropping it is right. `` `<!-- -->`{=html} `` is load-bearing --
pandoc puts it between `$\times$` and `7B` so a closing `$` before a digit
still reads as maths -- and the two are told apart ONLY by the character in
front. The rule went into the pass that clears empty spans, which runs on
the slices BETWEEN code regions: a slice can begin at `{=html}` with the
backtick that owns it in the previous slice, so the lookbehind saw a string
start and stripped a live marker. The comment became an ordinary code span,
which pandoc escapes, and printed 21 times in AlphaQ.
*Status: LOCKED — the orphan rule runs on the whole text before any slicing;
`tests/test_raw_inline_markers.py` holds both shapes apart.*

---

### K97
**A check built from our own output cannot see a shared absence.**
Every probe here compared two artifacts this pipeline made — our snapshot
against our output, the spans in our markdown against the `<math>` in our
HTML. Those find a disagreement between stages and nothing else. CafeQ
shipped 61 references in `output.md` and none in the book while every count
agreed with every other, because no count was about references: the defect
was not a disagreement but a blind spot every stage shared. A check has to
start somewhere the pipeline did not write. `flat.tex` says how many floats
there are, how many `\bibitem`, whether an author is named — and asking
whether any of it reached the page needs nobody to have named the check.
*Status: LOCKED — `tests/inventory_probe.py`. Calibrated on the pre-fix
books: 4/2/1 findings there, silent on all three fixed ones.*

---

### K98
**A list of what has gone wrong is always one build behind.**
The page scan grew an entry per accident — `{=latex}`, `{-2em}`, `:::`,
`(tab:x)`, `??`, `↩︎` — and then `<!-- -->` printed 21 times in AlphaQ while
it called the book clean, because nobody had met that shape. A reader found
it. Ask what a sentence is made of instead: Hangul, letters, digits and
ordinary punctuation, never `{ } < > \ $ & | ^ ~`. One of those ALONE is
content — the bars of a norm, the braces of a set, the `&` between two
authors — and attached to anything else it is markup. Name the exceptions,
not the offences.
*Status: LOCKED — `tests/leak_probe.py`: silent on all three fixed books,
firing on the pre-fix ones.*

---

### K99
**A cell can be a table, and the first `\end{tabular}` is not the last.**
A multi-line header is written as a `tabular` inside a cell, so scanning for
the first end cuts the outer table off inside that cell. Three of DeeR-VLA's
tables arrived as fragments pandoc could not read and its eleven tables were
counted as fourteen. Three papers of the same shape had never nested one, so
nothing had tested it. Match ends by depth — and note the scan breaks out of
its loop when an end cannot be found, so one unbalanced `\begin` would cost
every table after it.
*Status: LOCKED — `tests/test_nested_and_math.py`; 11/11 convert, and the
three older books are unchanged.*

---

### K100
**Most "unsupported maths" is not maths.**
texmath refused all eight of DeeR-VLA's equations. Seven were refused over
`\setlength\abovedisplayskip{3pt}` — a spacing directive written inside the
display with nothing in it to read. The eighth used `\sideset`, which is
real notation, and even that had an equivalent the supported subset can
say: `\sideset{}{_X}\sum` is `\sum\nolimits_{X}`, which the same equation
already used further along. The boundary is not where a command is
unimplemented; it is where no equivalent exists, and that is much smaller.
Remove the whole LINE of a spacing command — the command alone leaves a
blank line, that ends the display block, and the `$$` print anyway.
*Status: LOCKED — 8/8 render; `tests/test_nested_and_math.py`.*

---

### K101
**A guard that recognises "ours" by a folder name.**
The figure resolver skipped any reference starting `images/`, meaning
"already extracted". DeeR-VLA keeps its own figures in a folder of that
name, so all seven were taken for finished work: none was extracted, the
refs still pointed inside `arxiv_src`, and the build stopped. What marks a
reference as ours is the `figNNNN_` name the resolver writes. The same
afternoon gave a second of the kind: chunking emitted a zero-byte chunk,
which sends a sub-agent to translate a blank file and then fails the merge
with the blank it hands back.
*Status: LOCKED — `tests/test_conversion_edges.py`; 7/7 figures extracted.*

---

### K102
**A caption the author commented out is still a caption to a scanner.**
`float_units` takes comment-stripped text, so the side that COUNTS floats was
never fooled. The side that NUMBERS them reads the merged markdown, where the
raw floats must survive byte for byte and the comments come with them.
DeeR-VLA keeps an older caption commented out above the live one: its first
table took two numbers, every later table moved one on, and the eleventh ran
off the end of the list with no badge — while the count of tables and the
count of numbers agreed at eleven throughout (K57). Any pass reading merged
markdown for LaTeX structure needs `_in_latex_comment`, not an assumption.
*Status: LOCKED — `tests/test_commented_captions.py`; a no-op on the four
books that comment nothing out.*

---

### K103
**Two ways a figure arrives with no caption, and where each must be fixed.**
`\captionsetup{font={...}}` prints nothing, so it looks harmless — but it
stands between the image and its caption, and the formatter looks exactly one
paragraph ahead. Six of DeeR-VLA's seven figures lost their caption to it.
Removing it at merge time is enough, because nothing about it is translated.
`\captionof{figure}{...}` is the other, and it is NOT the same: pandoc has no
reader for it, so the caption survives only as a raw inline — a code span,
which is the one thing a translator is told not to touch. Repair it late and
the caption reaches a Korean page in English. It has to be renamed to
`\caption` before chunking, inside floats, where the two are equivalent.
*Status: LOCKED — figure captions 1/7 → 7/7; the rename is a no-op on the
other four books.*

---

### K104
**A note nothing references is dropped without a word.**
An IEEE paper carries its front matter in `\thanks`, and pandoc reads each as
a footnote whose REFERENCE sits in the title block — which the backend drops
on purpose, since title and authors come from the metadata. TinyVLA
translated 1271 characters of dates, affiliations, funding and DOI, and
printed none of it. Move an unreferenced definition ahead of the first
heading rather than leaving it to be dropped; a referenced one is a working
footnote and must stay where it is.
Measured alongside: of 21 post-header `\cmidrule` spans in the corpus, 16
skip only the row-label column and 5 are genuinely narrow. Full-width is
right for the 16 and overstates the 5 — left as it is, deliberately.
*Status: LOCKED — `tests/test_orphan_footnotes.py`; fires on TinyVLA only.*

---

### K105
**Not every arXiv "source" contains LaTeX.**
Adam's is 298 bytes whose whole body is `\includepdf{...}` — a finished PDF
in a LaTeX envelope. GW150914's is a PDF outright. Of ten well-cited papers,
two had no source to translate, so this is a normal shape and not an
accident. The backend converted the envelope to 43 characters and printed
"Conversion completed successfully!". The trap underneath is that `input.md`
is REUSED: written once, that 43-character document is picked up by every
later run as already converted. Refuse before writing it, and name the cause.
And `--backend arxiv` must not fall back — an explicit backend is a choice
about what the book will contain.
*Status: LOCKED — `tests/test_source_shapes.py`.*

---

### K106
**A macro definition pandoc cannot read stops the whole conversion.**
Not the macro — the CONVERSION. Three shapes, each of which cost a paper:
`\newcolumntype{x}[1]{>{\centering}p{#1pt}}` (ResNet, which then fell to the
calibre path with every equation gone), `\def\tablenote#1 #2\par{...}` with
TeX's delimited parameter text (Planck), and `\def \< {\langle}`, a control
SYMBOL, which is how a maths paper shortens notation. Drop the definitions:
this pipeline renders tables itself and never needed the column formatting,
and the uses survive as raw commands pandoc leaves alone. Column-type uses
must be rewritten with them (`x{20}` → `c`) or the column count stops
matching the rows. `\def\vect#1{...}` — plain parameters — is left alone;
pandoc expands those, and that is how a paper's shorthands reach the page.
*Status: LOCKED — `tests/test_source_shapes.py`.*

---

### K107
**Half the bibliography was being translated.**
A reference chunk gets its output written at conversion time, so no sub-agent
is dispatched and no entry is translated. The run that earns that exemption
ended on every second `\bibitem` and reopened on the next, because the escape
meaning "prose again" tests block density and a lone entry is not dense. The
segments alternated: 20 of Attention's 41 entries and 25 of ResNet's 51 lost
the exemption and went out to be translated. It also multiplied the chunk
count — 9 became 49, 11 became 61 — so it read as a cost problem while it was
a correctness one. A block holding a `\bibitem` is not prose, whatever its
density says.
*Status: LOCKED — `tests/test_bibliography_run.py`; 49 → 9 chunks.*

---

### K108
**Two ways a check punished a translation for obeying its instructions.**
`_INLINE_CODE_RE` stopped at a newline, so the LNCS `\institute{...}` block —
one code span pandoc wraps over four lines — was not stripped, and
`untranslated_block` counted fourteen English words the translator had
correctly left alone. And `target_language` measures a script ratio, which a
chunk of author-affiliation footnotes cannot pass: GAN's were four names, four
institutions and a short Korean predicate each, everything translatable
translated, 23%. Drop capitalised tokens the SOURCE spells identically — a
name is Latin by right — while untranslated prose, being lower-case, keeps the
ratio collapsing on the case the check exists for.
*Status: LOCKED — verified against a genuinely untranslated chunk; the four
earlier books are unchanged.*

---

### K109
**A formula and a heading, each reaching the page as source.**
`\cal{A}` is a legacy font switch CALLED with a braced argument, and the
group-form rule for `{\rm x}` does not match it: no `{` before, no space
after. texmath refuses the whole formula, so GAN's definition of a
subderivative printed as raw TeX twice. Add the call form, and `cal` to the
map. Separately, `resolve_references` runs BEFORE `number_sections`, and the
bilingual gloss is lifted from the original heading afterwards — so the
Korean half of "알고리즘 1의 수렴 (Convergence of Algorithm {alg:AGF})" had its
reference resolved and the gloss kept the raw label. A gloss exists so a
reader can match the heading to the paper; strip references out of it.
*Status: LOCKED — GAN: 13 leaked tokens → 0, raw `$` spans 2 → 0.*

---

### K110
**A wrapper with no reader swallows everything inside it, and reports as one.**
`\begin{appendices}` and NeurIPS's `\begin{ack}` have no pandoc reader, so the
whole environment becomes ONE raw block: its `\includegraphics` are never
resolved into `images/`, its lists and listings never convert, and the HTML
writer drops the lot. Neural ODE lost its entire appendix that way — six
figures and every formula in it — and the fidelity check reported it as
"1 raw LaTeX block". The count is of BLOCKS, not of content, so the largest
loss in the book looked like its smallest finding. Strip such wrappers in the
BACKEND, before figures are resolved: fixing it at merge time recovers the
prose and leaves the images behind.
*Status: LOCKED — figures 76 → 82, protected spans 221 → 246.*

---

### K111
**The starred variant is a different string, not a special case.**
`\begin{tabular}` is not a substring of `\begin{tabular*}`, so a scan written
with `str.find` on the plain spelling misses the starred one completely.
BERT's GLUE results table is a `tabular*`: no scan found it, nothing converted
it, and it reached the page as nothing at all. The same applies to
`\end{tabular*}` when matching ends by depth. Anywhere this pipeline searches
for an environment by name, it must accept `\*?` — that is what the corpus
census's shape names are FOR, and `tabular*` had been sitting in it unmatched.
*Status: LOCKED — BERT: 7 tables → 8, maths 91/93 → 93/93.*

---

### K112
**Verbatim is three shapes, and a check that knows one fails the other two.**
Latin text inside a code listing or a plot definition is the correct answer,
and `verify_chunk` was stripping only fenced markdown blocks. It therefore
failed three chunks for obeying: a Python listing put one at 21% Korean, and
a pgfplots `table[x=timestep,…] {plot_data/….csv}` read as eighteen
untranslated words — the glossary check then demanded `timestep` be
translated, though it is a CSV COLUMN NAME and rendering it would break the
figure. The three shapes are: fenced blocks, raw LaTeX verbatim environments
(`lstlisting`, `tikzpicture`, `verbatim`, `minted`), and markdown's INDENTED
code block, which is what pandoc turns a `lstlisting` into.
*Status: LOCKED — 3 chunks failed → 0; the six finished books are unchanged.*

---

### K113
**A hardcoded environment list is a guess; `\newtheorem` is the answer.**
`build_label_index` counted only seven environment names it had been told
about. Vershynin declares `example`, `fact`, `observation`, `conjecture`,
`remarks` and `definition-notag` as well, and five of them appear in the body —
so the shared counter silently skipped them. 52 of 59 labels came out with the
wrong number and 225 of 274 body references would have printed one. Nothing
errored: every number still looked like a number. The document states its own
vocabulary; read the declarations. `\newtheorem*` takes no number, `[shared]`
names the counter to share, and an environment declared with its own counter
restarts at 1 mid-paper. ~~Ignore `[within]`.~~ See [K130](#k130).
*Status: LOCKED — wrong-numbered references 225 → 0.*

---

### K114
**A label's prefix is the author's naming habit; requiring one loses every
reference.** `build_label_index` already knew this and derived a label's kind
from what encloses it. The RESOLVER did not: it recognised a reference only by
a `thm:`/`sec:` prefix inside the parentheses. Vershynin writes
`\label{Bai-Yin}`, so not one of his 364 references was seen — the reader met
`정리 (deviation from 1)` where the paper says ~~Lemma 44~~ Lemma 5.44 (K131:
258 of its references are dotted and none is plain). Match the label KEYS
themselves, which are known exactly. Two cautions: a declaration site
(`**정리 32** (Gaussian).`) uses the same key and must not be rewritten, and
theorem-likes share one counter, so the index knows the number but not whether
this one is a Lemma — keep the word the translator wrote.
*Status: LOCKED — 0 → 362 resolved, 0 missed.*

---

### K115
**The paper's own shorthand is not LaTeX texmath knows.**
`\def \< {\langle}` is ordinary preamble shorthand, and `\<` appears in 56 of
randmat's formulas. texmath has never heard of it, so all 56 printed as source.
`arxiv_backend` had been collecting these definitions into `math_macros.tex`
since the day it was written — and nothing ever read the file back. Expand
zero-argument definitions into the math at merge time, which is safe precisely
because the translator never saw any of it: every formula travelled as a
placeholder. Expand only zero-argument forms; one taking `#1` needs a real
macro expander. Two more directives cost whole displays the same way:
`\qedhere` and `\notag` print nothing and have no reader.
*Status: LOCKED — randmat unrendered spans 55 → 3, then 0 leaks.*

---

### K116
**`$` nested inside `\text{}` is legal, and every rule here forbade it.**
`\textnormal{}` switches to TEXT mode, so an author who wants a symbol back
writes `$...$` again: Neural ODE has
`$p(\textnormal{event at time $t$}| \dots)$`. Every inline rule in math_guard
excluded `$` from a span, so the formula closed at the inner `$` and the
dollars paired off BY ONE from there — the same desynchronisation the subscript
rule was written for, in a different shape. The chunk agent was handed half a
formula welded to the prose after it, and the passage came back part
translated, part raw. A brace-aware rule placed ahead of the general one fixes
it; verify the blast radius first — across ten papers it fired 1651 times and
changed exactly one span.
*Status: LOCKED — bare `$` left in chunks: 0.*

---

### K117
**One unreadable entry costs the whole reference list.**
`expand_thebibliography` converts every entry in ONE pandoc call and falls back
to raw LaTeX text when that call returns nothing. BERT has 56 entries; two of
them wrap a line between a command and its argument (`\href\n  {url} {text}`),
which pandoc refuses — a SPACE there converts, a newline does not. So all 56
printed as raw LaTeX, and the reader lost a formatted bibliography over two
line breaks. Two repairs, and the second matters more: close the gap, and
convert entry by entry when the batch call disagrees with the entry count, so
a bad entry costs only itself. Any all-or-nothing conversion in this pipeline
deserves the same treatment.
*Status: LOCKED — BERT leaks 91 → 26, entries rendered 0 → 56.*

---

### K118
**A pass that runs before the pass it depends on never fires.**
`\text{\mathtt{x}}` is refused by texmath while `\mathtt{x}` renders, so the
unwrap is right — and it did nothing, because BERT writes `\text{\tt {x}}` and
`\tt` only becomes `\mathtt` later, in `normalize_math_commands`. The unwrap
sat in `rewrite_text_fonts_in_math`, ahead of it, and never saw the shape it
was looking for. The rule tested correct in isolation and changed nothing in
the build; the PDF came out byte-identical, which is the tell. When a
verified-correct rule has no effect, check what the text looks like AT THAT
POINT rather than at the point you sampled it.
*Status: LOCKED — BERT leaks 26 → 2 once moved after the legacy font pass.*

---

### K119
**A counter scoped to a section is ours to reproduce, not a limit to accept.**
Shor 1995 prints `(2.1)` and `Table 3.1`: its preamble resets equation, figure
and table at each section and redefines `\the...` to carry `\thesection`.
Nothing read either signal, so all 29 references named a number the paper does
not print — and K113's "pandoc numbers flat" was nearly quoted to excuse it.
That covers theorem-likes only; an equation or float number is stamped by THIS
pipeline (K46, K62), so it was ours all along. Nor is it a LaTeX interpreter:
one fact per counter, said five ways at most, and only two of 18 papers say
anything. Four sites must agree — label index, `float_units`, equation tagger,
link regexes — and missing the last makes every reference a dead anchor (K80).
*Status: LOCKED — source_probe 0/29 → 29/0 against the original PDF.*

---

### K120
**`\bibitem`'s optional label is not optional in practice.**
`build_bibitem_numbers` read `\bibitem{key}`. natbib and plainnat write
`\bibitem[Adleman 1994]{Adle}`, so in a file holding 75 of them it found ZERO
keys, every one of Shor's 30 citations resolved to nothing, and `[@Knut]`
printed on the page where a number belongs. Nothing errored — an unresolved
citation is left visible on purpose, and the count said "30 had no target",
which reads as a source problem rather than a reader that cannot see.
`_BIBITEM_LABEL_RE` elsewhere in the same module already accepts the labelled
form: the lesson had been learned once and not carried across, which is K114's
shape exactly. Accept `\bibitem\s*(?:\[[^\]]*\])?\s*\{key\}`.
*Status: LOCKED — citations resolved 0 → 30.*

---

### K121
**A collaboration keeps its macros in a `.sty`, which the flattener never
follows.** ATLAS ships `atlasphysics.sty` beside the paper — 292 definitions,
including every macro in the 256 formulas that print as source. `\input` is
inlined; a local `\usepackage` is not. Collecting them was tried and MEASURED
WORSE, 256 refused formulas becoming 272, for two reasons no wider pattern
fixes: the collector is line-anchored and a `.sty` definition wraps
(`\def\GeV{\ifmmode {...}\else` continues, so what is captured does not
balance), and the bodies that do parse are `\ifmmode` conditionals texmath
cannot read either. Half a package is worse than none — it swaps one
unreadable name for another. A real fix needs balanced multi-line collection
AND the maths branch of each conditional.
*Status: REVERTED to baseline (256) — the finding stands, the fix does not.*

---

### K122
**`\makecell` and `\thead` empty the cell they exist to format.**
Both put a line break inside ONE table cell. pandoc has no reader for either
and drops the command TOGETHER WITH its argument, so the cell renders as
`<td></td>` — measured directly, and PaLM writes 92 of them. It is K110's
swallow at cell scale, and invisible to every check that counts tables rather
than reading their contents: the table is present, the row count is right, the
words are gone. Joining the lines with a space keeps every word and loses only
the break, which is typesetting. Consume the optional argument too —
`\makecell[l]{...}` empties the cell exactly as the bare form does.
*Status: LOCKED — `tests/test_table_cells.py`.*

---

### K123
**`\address` and `\institute` are dropped with the affiliation inside them.**
pandoc has no reader for either, so the command goes and the prose goes with
it. Maynard's five-line address at Centre de recherches mathématiques appears
once in `flat.tex` and zero times in `input.md`, in any chunk, and in
`output.md` — no raw token, no count out of balance, nothing to notice (K110).
Its neighbours fail the opposite way: `\email` and `\bibliographystyle` are
passed THROUGH and stand on the page as literal LaTeX. One rule cannot serve
both, and the order matters — in U-Net `\email` nests inside `\institute{}`,
so deleting it strands the `,\\ WWW home page:` that follows. Unwrap all three
outermost-first; drop only the directives.
*Status: LOCKED — `tests/test_front_matter.py`.*

---

### K124
**A check that reads its own output back reports work as damage.**
`check_math_fidelity` counted leftover `$...$` across the whole page, and
MathML keeps the original TeX in `<annotation encoding="application/x-tex">`.
Maynard's `\text{for infinitely many $n$ all of $n+h_1$, …}` puts four real
pairs in one annotation, so the build warned that four formulas reached the
page unrendered while that display was on the page, every glyph correct. The
cost is not the noise: a genuine leak reports the same number and reads the
same, so for any paper nesting math in text the check could no longer tell
source-on-the-page from rendered-and-described.
*Status: LOCKED — `tests/test_math_fidelity_annotation.py`.*

---

### K125
**`meta_evidence` rejected a quote for a character the pipeline itself made.**
pandoc's reader smartens quotes and `_WRITER` ends in `-smart`, so the writer
never turns them back: the chunk says `Zhang’s` where `flat.tex` says
`Zhang's`. An agent copying the author faithfully fails a check whose whole
purpose is to catch text that was NOT copied — 166 right, one invisible
apostrophe wrong, and the price is a re-translation. Fold U+2013, U+2014 and
the four curly quotes on both sides; not the ellipsis, which the corpus shows
pandoc never makes in prose. It cannot excuse a bad quote: over all 246 metas
the four real failures keep their prefixes to the character — 52/127, 23/111,
12/47 twice — folded or not. ~~An earlier count said 1055 exact, 0 absent~~:
that glob saw 131 of 246 and excluded the book whose quotes fail (K129, H37).
*Status: LOCKED — `tests/test_meta_evidence_typography.py`.*

---

### K126
**A heading with maths in it cannot be found by its own text.**
MathML sets `$y$` from the Mathematical Alphanumeric Symbols block, so the page
carries U+1D466 while the heading read back out of the HTML carries an ASCII
`y`. The two never compare equal, and shortening the probe cannot help — every
prefix starts with the character that differs. Maynard's three maths headings
were the three contents rows printed with a blank where the page number goes,
and the three bookmarks missing from the outline. The build said
`Print TOC: 8/11 page number(s) resolved`, which reads as a statistic rather
than a defect, and that is why it stood. NFKC folds the block back to letters.
*Status: LOCKED — `tests/test_toc_math_headings.py`.*

---

### K127
**A `\\` inside `\substack{}` is not a row of an align block.**
`source_probe` modelled rows as `body.count('\\\\') + 1`, and Maynard writes 74
`\substack{a\\b}` plus three nested `cases`. The probe claimed 167 numbered
equations about a paper that prints 106 and failed a book whose numbering was
never in question — K124's shape again, a check reading structure it should
have skipped. Rows break only at brace depth zero and environment depth zero.
That took 167 to 121; the remaining fifteen were all inside K128's `comment`
blocks, and the last one was `(6.15)`, which shares a line with its equation
and so was never extracted. Counted properly: 106 against 106.
*Status: LOCKED — `tests/test_align_rows.py`, `tests/test_printed_equations.py`.*

---

### K128
**A section the author commented out counts as one the translation lost.**
`\begin{comment}...\end{comment}` hides its contents as completely as a `%`
does, and `strip_tex_comments` only knew about `%`. Maynard leaves a 54-line
block holding `\section{Motivation}`, two theorems and fifteen numbered
equations, so the heading list came back 11 against the translation's 10 and
the build printed "refusing to guess" and shipped the whole book WITHOUT
section numbers — over a section the author had already deleted. Every caller
of `strip_tex_comments` reads flat.tex to learn structure and none of them
produces shipped content, so that is the right place to drop it.
*Status: LOCKED — `tests/test_comment_environment.py`.*

---

### K129
**Every `meta_evidence` failure the corpus has is markup, not memory.**
Four quotes across the whole store fail, all TinyVLA (2409.12514v5), and none
is a reconstructed sentence: two dropped an injected token that was part of the
chunk text — `⟦C0021⟧` and a `[@citekey]` bracket — and two are the SAME quote,
where the agent wrote `$\rightarrow$` into JSON without escaping the backslash,
so `\r` decoded to a carriage return and left `$ ightarrow$`. The intended text
matched byte for byte. ~~R2 read these as quotes retyped from memory~~ and the
guidance it produced — "whitespace is the only thing forgiven" — addresses
none of the three causes. The brief is the place to fix them: keep injected
placeholders and citekeys inside the quote or cut short of them, and never put
a backslash in a JSON string you have not escaped.
*Status: measured 2026-09-02 over 246 metas in 21 temp dirs; see REFEREE.md R5.*

---

### K130
**"pandoc numbers it, so it is out of reach" was about pandoc, not the book.**
`**정리 1**` is characters in `output.md`, and the build rewrites that line as
routine — `number_sections` and `resolve_references` already do. K113 waved
`[within]` away on that reasoning; K119 had caught the same reasoning once and
carved theorem-likes out anyway. Worse, `_NEWTHEOREM_RE` captured only the
LEADING optional argument, so `[section]` was never ignored — it was invisible,
and the test pinning the claim asserted a group that was always None. Maynard:
35 references disagreed with the paper and none agreed. Both halves have to
move together; fixing references alone leaves prose saying 정리 1.1 over a
declaration saying 정리 1. Free catch: `\newtheorem*` prints no number and
pandoc invents one — six in Maynard that no check could see.
*Status: LOCKED — `tests/test_theorem_statements.py`; 0 agree → 34 of 35.*

---

### K131
**One chapter of a book, shipped alone, still numbers everything `5.x`.**
randmat is `\documentclass{book}` with `\setcounter{chapter}{5}` before its
first section and no `\chapter{}` at all. Its own text writes "Theorem 5.39",
"Section 5.4.3", "(5.25)" — 258 dotted references, not one plain — and the
pipeline had nothing that could produce the `5`, so every number came out flat
and all 157 disagreed. The prefix is in the SOURCE, not only in the PDF. Apply
it only when the counter is set and never advanced: a document that really
uses `\chapter{}` has a prefix that moves, and pinning it would be worse than
leaving it flat.
*Status: LOCKED — `tests/test_fixed_chapter_prefix.py`; 0 agree → 157 of 157.*

---

### K132
**"Not defined in this document" is the wrong test for "readable".**
The alias rule drops a macro whose body is a single command not itself defined
here — written for `\let\gev\GeV`, which swaps one unreadable name for another.
`\def \< {\langle}` has exactly that shape and points at a command texmath
knows perfectly well, so the rule deleted the definition it exists to protect:
randmat printed 48 formulas as source over `\<` and `\>`. Nine papers lose
macros to it and 17 of the 22 distinct targets render. Shape cannot separate
the two cases and only the target can, so ask pandoc — one batched call,
cached; when pandoc is absent every answer is False and the old, conservative
behaviour returns.
*Status: LOCKED — `tests/test_math_macros.py`; randmat 48 unrendered → 0.*

---

### K133
**Removing a command from a raw inline leaves a code-span delimiter.**
pandoc hands `\index{...}` through as `` `\index{Condition number}` ``. Dropping
the command the ordinary way leaves an empty pair of backticks, and an empty
pair opens a code span that runs to the next one — swallowing the `$` on either
side. randmat's 79 markers went from printing as literal text to taking 29
formulas down with them, a repair that broke more than it fixed.
`arxiv_backend.strip_latex_cruft` already knew this (`_EMPTY_CODE_RE`); the
span has to go with the command. Dropping the terms is a REDUCTION — the paper
has an index, the book does not — so the build says so rather than letting one
more loss pass unremarked (K110).
*Status: LOCKED — `tests/test_index_terms.py`.*

---

### K134
**Inside `tabbing`, `\>` is a tab stop, and pandoc expands it anyway.**
The environment rebinds `\>`, `\=`, `\<`, `` \` `` and `\'` for its own length.
Shor's preamble says exactly why he had to work around that —
`\newcommand{\tab}{\>}` with the comment "making tabbing environments
accessible despite ket notation", then `\renewcommand{\>}{\right\rangle}`. Our
conversion knows no scope, so all 29 tabs in his three algorithm listings
became `\right\rangle` and the pseudocode shipped reading
`\right\rangle for {\it i} = 0 to {\it l}`. Only a REDEFINED tab command can be
damaged, which is the guard; one paper in the corpus trips it. Four spaces is
what `unwrap_tabbing` makes of a stop anyway.
*Status: LOCKED — `tests/test_tabbing_tabs.py`.*

---

### K135
**The paper's own shorthand, resolved from the `.sty` it ships.**
A `.sty` is never `\input`, so pandoc never sees the definition and the name
reaches the book: resnet printed `\ie` mid-sentence 5 times where its PDF
prints "i.e." 5 times. Handing pandoc the definitions is WORSE, measured —
dtrt.sty's real `\parhead` made it emit nothing for 13 headings, and
`\onedot`'s `\futurelet` came out `*i.e*..`. `scripts/paper_macros.py` resolves
instead, refusing on machinery, on a discarded argument, and on what pandoc
reads better — `\cite`, `\url`, `\newblock`, Shor's `\tab` (a tabbing STOP;
deleting it flattens three listings). One definition per conditional branch is
settled by the PRINTED paper: spectre's 14 author notes go, its PDF having 0.
*Status: done 2026-09-02. 1418 calls, 17 papers, no prose word lost.*

---

### K136
**"A lone trailing backslash is never valid LaTeX" — it is: `\ `.**
`math_guard`'s row-separator repair restores a `\\` that pandoc's reader
truncated to `\`, and its pattern allowed whitespace before the newline on
that written justification. The control space is exactly that shape, and Shor
writes `R_j \ = \ ` before an `array`. The repair made it a row separator
inside an `equation`, texmath refused, and both his gate-transition tables
printed as source in a shipped book. Bisected: the stray `\\` was the sole
cause — `\\*[.5ex]` renders. Corpus-wide the loose form matched two spans and
both were this; the narrow form (nothing between backslash and newline) keeps
all thirteen real repairs in the same paper. A claim of provable safety in a
docstring is still a claim.
*Status: LOCKED — `tests/test_row_separator_repair.py`; Shor 21 unrendered → 0.*

---

### K137
**A panel takes its letter from `\caption`, not from its position.**
Two faults in one caption. `build_subfigure_letters` scanned only `figure`,
while `_label_token_re` in the same file already accepts
`SC|wrap|sideways|long|floating` — so Neural ODE's `wrapfigure` yielded no
panels and all three `\subref` printed as LaTeX beside the plots they point
at. Lettering by position then gave the last panel `d`: `subcaption` steps the
sub-counter on `\caption`, and the third of the four panels is a legend with
none. The paper prints (a) (b) (c), read out of its own PDF. Both halves are
the same lesson — a float scanner that knows fewer spellings than its
neighbour, and a counter modelled by position instead of by what advances it.
*Status: LOCKED — `tests/test_panel_letters.py`; 3 unresolved → 3 resolved.*

---

### K138
**The content is in a different argument for each `\icml` command.**
`\icmlauthor{#1}{#2}` sets `\mbox{\bf #1}` and reads #2 as affiliation KEYS;
`\icmlaffiliation{#1}{#2}` keys on #1 and stores #2 — read out of
`icml2026.sty`, because backwards an affiliation key prints where a name
belongs. Anything without exactly two arguments is refused, and the enclosing
`icmlauthorlist` goes with them (K110).
~~SINQ's authors appear zero times in its own book.~~ **Wrong, and the mistake
is the lesson:** that was counted in `output.md` — the BODY — while the
pipeline routes authors to the METADATA, which is why `\twocolumn[...]` is
dropped. SINQ's PDF prints "Lorenz K. Müller" and its EPUB `dc:creator` carries
all six. Measure the artefact, not the intermediate.
*Status: LOCKED — `tests/test_icml_front_matter.py`.*

---

### K139
**Eight books say "Unknown Author" about papers that name everybody.**
The title page takes the author from the source PDF's metadata, and arXiv's
GenPDF routinely leaves `/Author` empty; the names are in flat.tex either way.
An author BLOCK is free-form LaTeX with a convention per class, so this reads
the simple forms and REFUSES the rest — refusing costs nothing, the page keeps
saying what it says today. The refusal has to be ALL-OR-NOTHING: dropping only
the fragments that would not parse printed seven of Attention's eight authors
(`{\L}ukasz Kaiser`) and seven of GAN's eight (a dagger on Sherjil Ozair), and
a list missing someone is as wrong as one naming the wrong person and harder to
notice. Accepted and checked name-by-name against the source PDFs: ddpm, gpt3,
higgs_atlas, maynard, palm, planck, randmat, shor, unet, SINQ.
*Status: LOCKED — `tests/test_latex_authors.py`.*

---

### K140
**An offset measured in one string, applied to another, lines up by luck.**
`paper_macros` protects each definition site so a rewrite cannot turn
`\newcommand{\etal}{et~al.\ }` into `\newcommand{et al. }{...}` — and it used
the span recorded when the definition was READ, out of whichever `.sty` or
`.tex` it came from, to index the document being rewritten. In the pipeline
those two are the same string, so every span landed and nothing looked wrong.
Where they differ the span covers an arbitrary stretch of prose, and every
macro inside it is skipped without a word — invisible in exactly the way
K110's swallow is. A position belongs to the text it was found in; find it
again in the target.
*Status: LOCKED — `tests/test_paper_macros.py`.*

---

### K141
**`\let\foo\bar` defines a macro with no body, and nothing here reads it.**
`paper_macros.read_definitions` recognises `\newcommand`, `\renewcommand`,
`\providecommand`, `\DeclareRobustCommand` and `\def` — every form that ends
in a `{body}` it can resolve. `\let` binds one NAME to another and has no body
at all, so the macro is never collected and its name goes on printing at the
reader, which is the defect K135 exists for. The census now says how often:
16 of 24 papers ship a `\let` in a style file, 9 use one in the document.
Not attempted, and the precedent is a caution — `read_math_macros` already
follows `\let` and needed an alias rule, because following one to a name
nobody defined swaps an unreadable token for a different unreadable token.
*Status: open, measured 2026-09-03. Classified `gap` in `test_source_lint.py`.*

---

## Environment notes

Facts that depend on this machine, not on the pipeline. Re-check on a new host.

- Korean faces that embed cleanly (static, 0 Type3): **HCR Batang** (함초롬바탕,
  serif, ships with Hancom Office), NanumBarunGothic, Hancom Gothic,
  NanumGothic, Malgun Gothic. Batang and Gulim embed but have no bold face.
- Korean faces that **fail** (variable): Noto Serif KR, Noto Sans KR.
- Latin partner faces present: Noto Serif / Noto Sans (with real italic + bold),
  Cambria Math (the only face with an OpenType `MATH` table on stock Windows).
- Monospace: Consolas is installed; **Fira Code and Monaco are not**. DotumChe
  covers Hangul in code at a matching fixed advance.
- Font stacks are resolved **per character**, so a Latin-only face listed first
  captures Latin while CJK falls through — that is what gives embedded English
  real italics when the CJK face has none.

### Tooling on this machine

Neither pandoc nor Calibre is on PATH. The scripts find them anyway
(`resolve_pandoc` checks `%LOCALAPPDATA%\Pandoc`, `find_calibre_convert`
checks `C:\Program Files\Calibre2`), so a build works — but a command you type
yourself needs them exported first, and forgetting that looks exactly like
"pandoc is missing" when it is installed:

```bash
export PATH="$PATH:<pandoc dir>:<calibre dir>"   # neither is on PATH by default on Windows
PY="<python 3.8+ executable>"   # `python scripts/doctor.py` finds all of these
```

- python 3.12: `%LOCALAPPDATA%\Programs\Python\Python312\python.exe`
- Chrome 149: `C:\Program Files\Google\Chrome\Application\chrome.exe`
- pip packages present: PyMuPDF, python-docx, lxml, Markdown, pypandoc.
  **beautifulsoup4 is NOT installed**, so `add_toc` takes its regex path.

## Run book — a new paper start to finish

```bash
# 1. Ingest. --allow-network is what enables the arXiv LaTeX backend, which is
#    the only path that keeps equations, figures and captions intact.
$PY scripts/convert.py "<paper>.pdf" --olang ko --allow-network \
    --temp-root "<output_dir>"

# 2. Glossary. Sample ~5 chunks, write glossary.json by hand (v2 schema), then:
$PY scripts/glossary.py count-frequencies "<temp_dir>"
$PY scripts/run_state.py plan "<temp_dir>"

# 2.5 DRY RUN -- build the paper with NOTHING translated (K34). Do not skip
#     this. Structural defects are all decided before translation, and after
#     it a re-convert moves every chunk boundary, so the fix costs a whole
#     re-translation and loses any review already done on the prose.
$PY tests/dry_run.py "<temp_dir>" --lang ko

# 3. Translate. One sub-agent per chunk, batched at the concurrency limit.
#    A chunk that is the paper's bibliography (\begin{thebibliography}) is
#    copied through verbatim: author names and paper titles must stay in the
#    original, and it is the most backslash-dense text in the document.
#    Each agent runs glossary.py print-terms-for-chunk and chunk_context.py
#    itself. Tell every one of them: write the output file with a file tool or
#    Python, NEVER a shell heredoc (K3).

# 4. Merge state + glossary, once per batch.
$PY scripts/run_state.py record "<temp_dir>" chunk0001 ...
$PY scripts/merge_meta.py prepare-merge "<temp_dir>" > prep.json
# resolve the decisions, then pipe them back:
$PY scripts/merge_meta.py apply-merge "<temp_dir>" < apply.json

# 5. Build.
$PY scripts/merge_and_build.py --temp-dir "<temp_dir>" \
    --title "<translated title>" --author "<author>" --lang ko \
    --print-profile a4-book

# 6. Verify — all of them. Each sees something the others cannot.
$PY -m unittest discover -s tests -p 'test_*.py'
$PY tests/layout_probe.py --strict            # is the page what was asked for
$PY tests/layout_probe.py --stress --strict   # pagination under load
$PY tests/format_probe.py "<temp_dir>" --lang ko --strict   # docx == epub == pdf
$PY tests/source_probe.py "<temp_dir>" --strict             # == the ORIGINAL
$PY tests/consistency_probe.py "<temp_dir>" --lang ko --strict  # the words

# 7. Copy the finished files where the user reads them. The --export-name
#    aliases are written INSIDE the temp dir; a rebuild will not refresh a
#    copy you made elsewhere, and a stale one looks exactly like a fresh one.
```

Repairing a book that is already translated: patch the source chunk and the
translated chunk together, re-hash `manifest.json`, `run_state.py record` the
chunk, and confirm `run_state.py plan` is empty before rebuilding (K50).

Conventions in use: work dirs and finished copies both under one output
directory, named `<Paper>_ko.{pdf,docx,epub,html,md}`.
`--print-profile` only takes effect together with `--force-html` or
`--build-only`, because HTML regeneration is keyed on output.md's mtime.

A pristine copy of the skill as it was before this work is in the session
scratchpad as `translate-book.backup`.
---

## Maintenance protocol

**Trigger.** SKILL.md Step 9. Before reporting results, if you diagnosed
something that is not already here, add an entry. If you found nothing new, do
nothing — an empty diff is a fine outcome.

**What belongs here**
- Behaviour of an external tool that surprised you (pandoc, Chromium, Calibre,
  PyMuPDF), with the measurement that proved it.
- A judgement call and the numbers behind it.
- Anything environment-dependent.

**What does not**
- Anything a test now enforces — write the test instead, and leave one line here
  pointing at it.
- Restatements of what the code plainly does.

**Entry format**

```markdown
### K<next number>
**One-sentence claim in bold.** What actually happens and why, in a few lines.
Include the measurement or the command that proves it.
*Status: LOCKED — <test name>. | GUARDED — <what catches it>. | measured <date>, <tool version>.*
```

**Rules that keep this file useful**
1. Add a row to the symptom index. An entry nobody can find is not knowledge.
2. Numbers are never reused. K7 stays K7 even if it is superseded — append
   `*Superseded by K<n>.*` rather than renumbering.
3. **When a finding becomes LOCKED by a test, compress its entry to the claim
   plus the test name.** The test is the record; this file keeps the *why*.
4. Keep entries under ~10 lines. If one needs more, it wants to be code.
5. Findings that turn out to be wrong get struck through, not deleted — the
   wrong turn is itself useful. Say what replaced it.
6. Re-verify anything marked `measured <date>` after a major version bump of the
   tool it names.

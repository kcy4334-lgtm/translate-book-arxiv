# AGENTS.md

## Project

translate-book is a Codex Skill that translates books (PDF/DOCX/EPUB) into any language using parallel subagents. Published on GitHub as `kcy4334-lgtm/translate-book-arxiv`.
A fork of [deusyu/translate-book](https://github.com/deusyu/translate-book); upstream also publishes on ClawHub, this fork does not.

## Structure

- `SKILL.md`: Skill definition, the orchestration logic that Codex / OpenClaw follows
- `KNOWLEDGE.md`: findings log: tool behaviour that surprised us, with the
  measurement that proved it. Read on unexpected output; append per SKILL.md
  Step 9. Anything a test now enforces is one line here pointing at the test
- `scripts/convert.py`: PDF/DOCX/EPUB → Markdown chunks (via Calibre HTMLZ)
- `scripts/manifest.py`: SHA-256 chunk tracking and merge validation
- `scripts/glossary.py`: Term-consistency glossary; per-chunk term tables injected into sub-agent prompts
- `scripts/chunk_context.py`: Read-only previous/next chunk excerpts injected into sub-agent prompts
- `scripts/meta.py`: Per-chunk sub-agent observation file schema
- `scripts/merge_meta.py`: Merges sub-agent observations into the canonical glossary as each chunk lands
- `scripts/run_state.py`: Selective re-translation planner and run_state.json recorder
- `scripts/repair.py`: In-place fixes for a book that is already translated: `sidecar` rewrites the raw LaTeX tables held in `chunk*.math.json`, `rehash` refreshes `manifest.json` after a chunk was edited by hand. Re-converting instead would move every chunk boundary and cost a full re-translation
- `scripts/arxiv_backend.py`: arXiv LaTeX source → Markdown; every ingest-side fix for constructs pandoc cannot read lives here
- `scripts/merge_and_build.py`: Merge translated chunks → HTML/DOCX/EPUB/PDF
- `scripts/layout.py`: Language font tables and print profiles (page size, margins, body size); the single source of truth both merge_and_build.py and calibre_html_publish.py read
- `scripts/chromium_pdf.py`: Headless-Chromium PDF renderer and PyMuPDF page-number stamping
- `scripts/calibre_html_publish.py`: Calibre format conversion wrapper (EPUB, and DOCX fallback)
- `scripts/template.html`, `scripts/template_ebook.html`: HTML templates

## How this pipeline breaks

Worth reading before adding a check, because it says where to point one.

**Nothing here fails. It disagrees.** Every defect this project has shipped
lived at a boundary between two tools that were each behaving correctly.
pandoc's markdown writer escapes a literal `[` as `\[`; our reader treats
`\[..\]` as display maths, both right, and a column's units rendered as
nothing. pandoc lays a grid table out by display width; a translator pads to
the same character count, both reasonable, and the table collapsed into
prose. pandoc expands `*{9}{r}` when reading and re-emits it beside the
expansion, internally consistent, and a 12-column table became 21. No
component logged a problem in any of these, because none had one.

**Counting agrees with itself.** When nine of twelve tables fell out of the
Word file, the table count, the image count and the value probes all passed:
the HTML had all twelve, and three is not zero. A count is only evidence when
it is compared against something that was not produced by the same code path,
the other formats, or the original PDF.

So checks are worth most in this order:

1. **Against the source PDF** (`source_probe`), the one reference that cannot
   have drifted. It caught a numbering scheme that was wholly self-consistent
   and wholly wrong.
2. **Between the formats** (`format_probe`): DOCX against the ebook HTML.
   Neither is authoritative; the disagreement is the signal.
3. **Inside the artifact** (`consistency_probe`, `layout_probe`), open the
   built file and look at what a reader sees, not at what was emitted.

A check that reads only the thing it is checking will pass on a broken book.

**A table format you turn off does not become safe; it becomes absent.**
`grid_tables` is the only writer format pandoc has for a spanning multi-deck
header. Disabling it because grid layout is width-fragile made pandoc write the
literal string `[TABLE]` instead, and a whole results table left the book with
every count still passing. Formats that are unsafe get *repaired at the merge*,
where the translator is finished and nothing can drift further, never removed
from the writer.


## Testing changes

Use a small file for quick checks, or the checked-in baseline book for the repository's full-pipeline test.

Quick smoke test:

```bash
python3 scripts/convert.py /path/to/small.pdf --olang zh
# then run translation via the skill
python3 scripts/merge_and_build.py --temp-dir <name>_temp --title "test"
```

Full baseline test:

```bash
mkdir -p tests/.artifacts
cd tests/.artifacts
python3 ../../scripts/convert.py ../baselines/standard-alice/standard-alice.epub --olang zh
# then run translation via the skill
python3 ../../scripts/merge_and_build.py --temp-dir standard-alice_temp --title "test"
```

Verify: all output_chunk*.md files exist, manifest validation passes, output formats generate.

### Print layout

`python tests/layout_probe.py` builds `tests/fixtures/layout_ko.md` straight
through the build stage and measures the resulting PDF: page size, the four
margins from actual ink, modal body size, measured leading, embedded font
names, lines per page, characters per line and right-margin overflow. Add
`--strict` for a non-zero exit on drift, `--keep` to leave the artifacts in
`tests/.artifacts/`. It needs PyMuPDF, pandoc and a browser, so it is
deliberately not named `test_*.py` and CI never collects it.

A Type3 font in the probe's font list means a variable font failed to
subset-embed, replace it with a static face in `layout.LANG_CONFIG`.

### Output formats

`python tests/format_probe.py <temp_dir> --strict` opens book.docx,
book.epub and book.pdf and counts the tables, images and table values each
actually carries. Run it after any change to how content is injected: raw
HTML survives the HTML path alone, and a `<table>` or `<figure>` that looks
right in the PDF can leave the DOCX empty with every other check green.

`python tests/layout_probe.py --stress` uses a second fixture built for
pagination only: a 45-row table, a display equation positioned to land on a
page break, and a code block longer than a page. It reports which pages each
spans and whether the table header repeated, the equation stayed whole, and
every code line survived. Body-size and leading checks are skipped there,
that fixture is deliberately mostly table and code, so its modal glyph size
is not the body size.

### Against the original paper

`python tests/source_probe.py <temp_dir> --strict` compares the section,
figure, table, equation and cross-reference numbers against the numbers the
**source PDF** prints, located through `config.txt`. Everything else in the
suite checks the build against itself; this is the only check with an outside
reference, and it is the one that catches a numbering scheme that is wholly
self-consistent and wholly wrong. It reads `flat.tex` and the PDF only, never
the translation, so it gives the same answer before and after translating.

### Against the reader

`python tests/consistency_probe.py <temp_dir> --lang ko --strict` looks for
what a reader would trip over and no format check can see: LaTeX that reached
the page as literal text, unresolved `(sec:x)` markers, doubled reference
labels, one term glossed two ways, one English term rendered two ways, and
per-chunk invariants against the untranslated source. Term drift is structural
here (one sub-agent per chunk, none able to see the others) so it is a
standing check, not a one-off.

### Before translating

`python tests/dry_run.py <temp_dir> --lang ko` stages the untranslated chunks
as their own translations in `<temp_dir>_dryrun`, builds, and runs the source
and format probes. The real temp dir is untouched. Use it whenever the ingest
or build path changes: it exercises the whole pipeline on a real paper without
an API call, and every structural defect is decided before translation anyway.

### Table edits

`python scripts/verify_tables.py snapshot <temp_dir>` before the caption
sub-agents run, `check <temp_dir> --strict` after. Translation changes words;
the multiset of numbers, the row count, the `&` count per row and every
`\multicolumn` span must survive it untouched. `check` refuses to answer
without a snapshot, because a baseline rebuilt from the edited files is not a
baseline.

### Is this machine able to build the same book

`python scripts/doctor.py --strict` resolves pandoc, Chromium, Calibre and
PyMuPDF the same way the pipeline does, and reports the fonts separately: a
missing face is not cosmetic, the fallback has different metrics and the page
count changes. It reports what is installed; `tests/layout_probe.py --strict`
is what proves the output.

### Reviewing a finished book

The probes cover what is worth automating. Three sweeps of a finished book
found the rest by opening the artifacts, and these are the axes that paid:

| axis | what to do | what it found |
|---|---|---|
| floats | count figures and tables against the source PDF | 4 figures missing, 12 tables the wrong width |
| tables | read the built HTML's header cells | 4 collapsed into prose, 1 row label gone |
| maths | look for `<math>` that renders empty, `<merror>`, a stray `$` | a column's units drawn as nothing |
| formats | DOCX against the ebook HTML, not against zero | 9 tables missing from Word |
| pages | characters per page; a page with an image and nothing else | 7 near-empty pages, panels split |
| prose | paragraphs with no Hangul; length against the source chunk | (clean, all were the reference list) |
| ingest | re-convert one paper and dry-run it | proved the ingest fixes actually fire |

The last row is the one to remember: a fix to `sanitize_tex` is not tested by
rebuilding a book that was converted before it. Re-convert something.

## The two logs

`KNOWLEDGE.md` records how the tools behave, the surprise and the measurement
that proved it, numbered `K<n>`. `KNOWHOW.md` records how to work, the
practice, and the incident that shows what skipping it cost, numbered `H<n>`.
Before changing anything here, read KNOWHOW's "Which document, for which task"
table; it says which of these documents to open for the change you are making.
`tests/test_knowhow.py` keeps the two from drifting into each other.

## Conventions

- Only `chunk*.md` naming, no `page*` legacy support
- SKILL.md frontmatter must stay single-line per field (OpenClaw parser requirement)
- Script paths in SKILL.md use `{baseDir}` not hardcoded paths
- Subagent instructions in SKILL.md must be platform-neutral (work on Codex, OpenClaw, Codex)
- Checked-in baseline inputs live under `tests/baselines/<book-id>/`; generated full-pipeline outputs live under `tests/.artifacts/`
- There is ONE README. Upstream keeps a Chinese one; this fork dropped it rather than carry a translation nobody here can review; it would go stale on the first edit, and a stale translation is worse than none
- Releases follow `.claude/commands/release.md`: `git push origin main`, then `git tag vX.Y.Z && git push --tags`. Do not skip the git tag; it's the only version anchor in the repo. ClawHub publishing is upstream's, not this fork's

## Do not

- Do not put language font data or page geometry anywhere but `scripts/layout.py`; it used to be duplicated across two modules that had already drifted
- Do not list a variable font (`Noto Serif KR`, `Noto Sans KR`) in a CJK stack; Chromium cannot subset-embed one and emits a Type3 object per glyph instead
- Do not reintroduce `page*` file support; it was intentionally removed
- Do not hardcode `~/.Codex/skills/` paths in SKILL.md, use `{baseDir}`
- Do not put platform-specific tool names (Agent, sessions_spawn) in `allowed-tools` as the only option, keep the whitelist cross-platform
- Do not infer table structure from the rendered HTML. Header depth and body rules are read from `flat.tex` by `table_structures()` and applied by document order, so they are identical whether the table reached the page as raw LaTeX or as a pandoc-converted markdown table. Guessing from cell contents is what the Average/평균 heuristic is for, and it runs only when the source has no rules at all
- Do not centre a display `<math>` with `text-align` (Chromium's MathML Core ignores it on a block element), and do not reach for `display: flex` either: a formula wider than the flex container loses its FIRST CHILD outright, which cost equation (3) of VLA-Adapter its left-hand side with nothing on the page to show it (K151). Centre the inner `<semantics>` box with `width: fit-content; margin: 0 auto`, which keeps the `<math>` element full width so the `::after` equation number still lands in the margin
- Do not accept a sub-agent's report as evidence that its work is correct. Run `scripts/verify_chunk.py` on the file it wrote: a chunk that came back in the wrong language, lost a paragraph, or quoted evidence that is not in the source reports success exactly the way a correct one does
- Do not declare table or figure STRUCTURE inside `@media print`. The PDF is the file that gets looked at, so a print-only rule reads as working while the EPUB and the web page go without it -- and Calibre deletes a class that no active rule matches, so the EPUB loses the markup too, not just the styling
- Do not disable a pandoc table format to avoid a layout bug (see "How this pipeline breaks")
- Do not add mtime-based incremental rebuild for HTML/format generation, the current skip logic is intentionally simple (existence check). Metadata/template changes require manual cleanup. This is documented in the README.

## Cursor Cloud specific instructions

### Environment

- Python 3.12+ is pre-installed; no version manager needed.
- System dependencies (Calibre, Pandoc) and pip packages (pypandoc, beautifulsoup4) are installed by the update script.
- Unit tests only依赖 Python stdlib（不需要 pip 包或外部二进制，直接 `python3 -m unittest discover` 即可运行）。

### Running tests

- **Unit tests (CI-equivalent):** `python3 -m unittest discover -s tests -p 'test_*.py' -v`: runs from repo root, no setup needed.
- **Compile check:** `python3 -m compileall scripts tests`

### Full pipeline integration test

Run from `tests/.artifacts/` to keep generated files out of the repo root:

```bash
mkdir -p tests/.artifacts && cd tests/.artifacts
python3 ../../scripts/convert.py ../baselines/standard-alice/standard-alice.epub --olang zh
# Create mock output_chunk*.md files (copy source chunks) since actual translation requires LLM subagents
for f in standard-alice_temp/chunk*.md; do cp "$f" "standard-alice_temp/output_$(basename $f)"; done
python3 ../../scripts/merge_and_build.py --temp-dir standard-alice_temp --title "test"
```

### Known issues

- Ubuntu's Calibre 7.6.0 package has an EPUB generation bug (bytes/str mismatch in `container.py`). DOCX and PDF generation work fine. This is a distro packaging issue, not a codebase bug.
- `pypandoc` installs its CLI script to `~/.local/bin` which may not be on PATH, but the Python library import works regardless.

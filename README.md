# Translate Book: arXiv

An agent skill for Codex, Claude Code, and OpenClaw that turns an arXiv paper into a translated, printable book, reading the paper's **LaTeX source**, so the equations, figures, tables and the paper's own numbering survive the trip. PDF, DOCX and EPUB inputs are supported too, through Calibre.

Translating a paper from its PDF means translating what a PDF reader can recover from it, and a formula is the first thing that does not survive: `pdftohtml` scatters every equation into positioned text spans, and no flag brings it back. This skill fetches the LaTeX the authors actually wrote.

Target language is a flag: `zh`, `en`, `ja`, `ko`, `fr`, `de`, `es` and extensible. Korean is what it is measured against, and the print layout ships with Korean typography already tuned.

> Lineage: [claude_translater](https://github.com/wizlijun/claude_translater) inspired [deusyu/translate-book](https://github.com/deusyu/translate-book), which restructured the workflow as an agent skill: subagents translating chunks in parallel, manifest-driven integrity checks, resumable runs, and multi-format output in one pipeline.

> Forked from [deusyu/translate-book](https://github.com/deusyu/translate-book). This fork develops the arXiv
> LaTeX-source path: the numbering read from the paper itself, the
> macro and float handling, and the knowledge, know-how and referee logs
> that ship with it.

---

## How It Works

```
arXiv paper (PDF)                    │  any other book (PDF/DOCX/EPUB)
  │  detected from the page-1 stamp   │
  ▼                                   ▼
Fetch /e-print → flatten the LaTeX    Calibre ebook-convert → HTMLZ → HTML
  │  the paper's own macros resolved from the .sty files it ships
  │  equation, theorem, section and float numbers read from the source
  │  figures rasterised from the original vector PDFs, captions attached
  ▼                                   ▼
Markdown, with $...$ math intact  ←───┘
  │
  ▼
Split into chunks (chunk0001.md, chunk0002.md, ...)
  │  manifest.json tracks chunk hashes
  │  the reference list becomes its own chunk and is copied, not translated
  ▼
Parallel subagents (work queue, 8 in flight by default)
  │  each subagent: read 1 chunk → translate → write output_chunk*.md
  │  each chunk is verified, recorded and merged as it lands
  ▼
Validate (manifest hash check, 1:1 source↔output match)
  │
  ▼
Merge → Pandoc → HTML (with TOC) → pandoc DOCX / Calibre EPUB / Chromium PDF
```

Each chunk gets its own independent subagent with a fresh context window. This prevents context accumulation and output truncation that happen when translating a full book in a single session.

## Features

- **Numbers come from the paper**: equation, theorem, section, float and subfigure numbers are reconstructed from the LaTeX source and checked against the original PDF by `tests/source_probe.py`, not against the build's own output
- **The paper's own shorthand is resolved**: a `.sty` is never `\input`, so pandoc never sees `\ie` or `\parhead` and the name prints at the reader. `scripts/paper_macros.py` reads the definitions the paper ships and expands them, refusing rather than guessing when it cannot, 4,099 calls across the 21 papers in the corpus, and a word-level diff of the produced markdown on six of them shows nothing lost but the macro names themselves
- **Refusals are reported, never silent**: every macro it declines is named with its reason at conversion time
- **Parallel subagents**: a work queue keeps 8 translators in flight, each with isolated context; the next chunk starts the moment a slot frees
- **The reference list is never translated**; it is split into its own chunk and copied verbatim. Measured at 27–34% of a paper's characters, and usually its largest chunk
- **Every chunk is checked before it counts**: `scripts/verify_chunk.py` compares each sub-agent's output against its source, the glossary it was handed, and the chunk it was told to quote from
- **Resumable + selective re-translation**: chunk-level resume, with `run_state.json` tracking glossary-sensitive re-translation
- **Neighbor context**: each chunk can see short read-only excerpts from adjacent chunks for pronoun and entity resolution
- **Manifest validation**: SHA-256 hash tracking prevents stale or corrupt outputs from being merged
- **Multi-format output**: HTML (with floating TOC), DOCX, EPUB, PDF
- **Optional output controls**: explicit EPUB cover, custom temp root, and user-facing export aliases
- **Multi-language**: zh, en, ja, ko, fr, de, es (extensible)
- **PDF/DOCX/EPUB input**: Calibre handles the conversion heavy lifting
- **It grows**: four advisor sub-agents and three logs ship with the skill, and a census of every LaTeX shape the corpus has met answers "has this ever been seen?" with a number instead of a guess. See [Growing the skill](#growing-the-skill)

## What this fork develops

Upstream translates books with parallel sub-agents. This fork puts the work
into the one input where the conversion itself is lossy (an arXiv paper)
and into making the skill cheaper to work on next month than this month.

| | |
|---|---|
| **Numbers read from the paper** | Equation, theorem, section, float and subfigure numbers reconstructed from `flat.tex` and checked against the source PDF by `tests/source_probe.py`, not against the build's own output |
| **`scripts/paper_macros.py`** | The paper's own `\newcommand`s resolved from the `.sty` files it ships. 4,099 calls across the 21 papers in the corpus |
| **Refusal over guessing** | It declines on TeX machinery, on a discarded argument, and on anything pandoc reads better, and names every refusal at conversion time instead of leaving it silent |
| **Print path** | Headless Chromium against a real `@page` box (A4, 18/18/22/18 mm, 11.5 pt), page numbers stamped afterwards because Chrome implements no margin boxes. `scripts/layout.py` is the single source of page geometry and fonts |
| **Growth stores that ship** | `KNOWLEDGE.md` 143 entries, `KNOWHOW.md` 38, `REFEREE.md` 6, and a census of every LaTeX shape the corpus has met across 24 papers |
| **Four advisor sub-agents** | old-man, question-monster, fast-finder, referee; see below |
| **The census as an oracle** | `tests/test_source_lint.py` fails when the corpus has met a construct nobody has classified |
| **Tests** | 1,567, stdlib only, run in CI |

## Growing the skill

Every paper is a new shape. A pipeline that meets one it has not seen either
learns from it or meets it again next month at the same price. Four things
ship with this skill so that the second time is cheaper than the first.

| | what it holds |
|---|---|
| `KNOWLEDGE.md` | What a tool actually did, with the measurement that proved it. 143 entries |
| `KNOWHOW.md` | What a way of working cost, so it is not paid twice. 38 entries |
| `REFEREE.md` | Whether a repeated failure belongs to a tool, a briefing, or a role. 6 entries |
| `corpus/shapes.json` | Every LaTeX construct each paper carried, written by the build itself. 24 papers |

The census is the part that is easy to underrate. It answers *"has this ever
been seen?"* with a number, and, more usefully, it names what has **never**
been seen, so a pattern that has never met a real example says so instead of
being trusted.

Four advisor sub-agents read those stores rather than guessing:

- **old-man**: before you conclude a paper does not contain something, or write a pattern whose match decides presence
- **question-monster**: after you conclude something is impossible; it hands back candidates to test
- **fast-finder**: instead of reading the logs; returns the few entries that bear on the question
- **referee**: once a whole run is gated; separates a tool fault from a briefing fault from a role's

`tests/test_source_lint.py` turns the census into an oracle: a construct the
corpus has met but nobody has classified fails the test suite. New shapes have
to be dealt with before they ship, not after a reader finds them.

### What that looks like in practice

One loop, from a single working session:

1. `\ie` was found printing mid-sentence in a finished Korean book, five times, where the paper's own PDF prints "i.e." five times.
2. Fixed by resolving the paper's macros from the `.sty` it ships (`scripts/paper_macros.py`).
3. **old-man** was then asked what a pattern like that would miss, and found two more: a display opened by a macro (`\newcommand{\be}{\begin{equation}}`) that a `\begin`-hunting regex cannot see, and a name bound to `\hspace` that looks exactly like an abbreviation; resolving it would have deleted a listing's indentation.
4. **question-monster** found a third: an odd `$` inside an `\ifmmode` body had destroyed `$`-parity for the rest of one paper, and 73 rewrites were landing *inside* its formulas.
5. All three fixed, recorded, and **the census taught to count their shapes**, so the next paper carrying one is caught by a test, not by a two-hour consultation.

## Prerequisites

New to this skill, or setting it up on a machine that didn't build it? See
**[INSTALL.md](INSTALL.md)** for step-by-step placement and verification.

Run `python scripts/doctor.py --strict` before anything else. It reports what
is installed and what is not, using the same resolvers the pipeline uses, and
exits non-zero when something required is absent.

- **Agent runtime**: Codex, Claude Code, or OpenClaw, installed and ready to run skills
- **Python 3.8+**
- **Pandoc**: every markdown/HTML conversion goes through it ([download](https://pandoc.org/))
- **Chromium, Chrome, or Edge**: the PDF is printed by headless Chromium. Set
  `TRANSLATE_BOOK_CHROME` if yours is somewhere the finder does not look
- **Calibre**: `ebook-convert`, for EPUB and the calibre ingest backend
  ([download](https://calibre-ebook.com/))
- **PyMuPDF** (`pip install pymupdf`): page numbers are stamped with it, and
  every probe that reads a PDF needs it
- `pypandoc` (`pip install pypandoc`): used by the conversion path
- `beautifulsoup4`: optional, better table-of-contents generation

**Fonts decide whether you get the same pages.** The layout is measured
against a specific set, and a missing face is not cosmetic: the fallback has
different metrics, the lines break elsewhere, and the page count changes.

| target | install |
|---|---|
| Korean body and headings | Noto Serif KR, Noto Sans KR ([Google Fonts](https://fonts.google.com/noto)) |
| formulas | any font with an OpenType MATH table: Cambria Math ships with Office; [STIX Two Math](https://www.stixfonts.org/) is the free alternative |

To prove a machine produces the same output rather than assuming it, build a
real PDF and measure it:

```bash
python tests/layout_probe.py --strict
python -m unittest discover -s tests -p "test_*.py"
```

## Quick Start

### 1. Install the skill

#### Codex

```bash
npx skills add kcy4334-lgtm/translate-book-arxiv -a codex -g
```

Or install it manually:

```bash
mkdir -p ~/.agents/skills
git clone https://github.com/kcy4334-lgtm/translate-book-arxiv.git ~/.agents/skills/translate-book
```

Restart Codex if the newly installed skill does not appear.

#### Claude Code

```bash
npx skills add kcy4334-lgtm/translate-book-arxiv -a claude-code -g
```

Or install it manually:

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/kcy4334-lgtm/translate-book-arxiv.git ~/.claude/skills/translate-book
```

#### OpenClaw

```bash
openclaw skills install @kcy4334-lgtm/translate-book-arxiv
```

### 2. Translate a book

#### Codex

In the Codex CLI or IDE extension, enter:

```text
$translate-book Translate /path/to/book.pdf into Chinese.
```

Codex can also select the skill automatically when your request matches its description.

#### Claude Code and OpenClaw

Ask the agent:

```text
translate /path/to/book.pdf to Chinese
```

In Claude Code, you can also use the slash command:

```text
/translate-book translate /path/to/book.pdf to Japanese
```

The skill handles the full pipeline automatically: convert, chunk, translate in parallel, validate, merge, and build all output formats.

### 3. Find your outputs

All files are in `{book_name}_temp/`:

| File | Description |
|------|-------------|
| `output.md` | Merged translated Markdown |
| `book.html` | Web version with floating TOC |
| `book.docx` | Word document |
| `book.epub` | E-book |
| `book.pdf` | Print-ready PDF |

## Repository Test Assets

- Checked-in baseline inputs live under `tests/baselines/<book-id>/`.
- Generated full-pipeline outputs live under `tests/.artifacts/` and should not be committed.
- Because `scripts/convert.py` writes `{book_name}_temp/` under the current working directory, run repository baseline tests from inside `tests/.artifacts/` to keep generated files out of the repo root.

### Full-Pipeline Baseline Example

```bash
mkdir -p tests/.artifacts
cd tests/.artifacts
python3 ../../scripts/convert.py ../baselines/standard-alice/standard-alice.epub --olang zh
# then run translation via the skill
python3 ../../scripts/merge_and_build.py --temp-dir standard-alice_temp --title "test"
```

## Feedback and Contributions

Please open a detailed GitHub issue instead of starting with a pull request. A change here has to be checked against the orchestration rules in `SKILL.md`, the chunk and manifest contracts, the baseline assets, and the release flow, and those only hold together when one person reads them side by side.

Pull requests are not the preferred contribution path and may be closed in favor of an issue. If you already have a patch, include the idea, key diff, failing case, or verification notes in the issue; the maintainer may rework or split the implementation before merging.

A useful issue should include:

- Current behavior and expected behavior
- Input format and environment, such as PDF/DOCX/EPUB, OS, Python, Calibre, and Pandoc versions
- Minimal reproduction steps or a small public-domain sample when possible
- Logs, screenshots, or generated file names that show the failure

## Pipeline Details

### Step 1: Convert

```bash
python3 scripts/convert.py /path/to/book.pdf --olang zh
```

Calibre converts the input to HTMLZ, which is extracted and converted to Markdown, then split into chunks (~6000 chars each). A `manifest.json` records the SHA-256 hash of each source chunk for later validation, and a `source_fingerprint.json` ties the temp dir to the exact source bytes it was built from; re-running against a replaced source file aborts instead of silently reusing stale chunks. Temp dirs created before fingerprinting are adopted with a warning on first re-run.

By default the working directory is `{book_name}_temp/` under the current directory. Use `--temp-root /path/to/work` to keep the same leaf directory name under a different parent.

### Step 1.5: Glossary (term consistency across chunks)

Each chunk is translated by a fresh-context sub-agent, which means the same proper noun can drift across multiple translations on a 100-chunk book. To fix this, the skill builds a glossary before translation:

1. Sample 5 chunks (first, last, 3 evenly-spaced middle).
2. Extract proper nouns and recurring domain terms; pick canonical translations.
3. Write `<temp_dir>/glossary.json` (hand-editable schema below).
4. Run `python3 scripts/glossary.py count-frequencies <temp_dir>` to populate per-term frequencies (ASCII terms use word-boundary regex so `cat` doesn't match `category`; CJK terms use substring; single-CJK-char terms are rejected; aliases count toward the term they belong to).
5. For each chunk, the orchestrator calls `python3 scripts/glossary.py print-terms-for-chunk <temp_dir> chunkNNNN.md` and injects the resulting 3-column (`原文 | 别名 | 译文`) markdown table into that chunk's prompt as a hard constraint. Term selection = (terms whose source OR any alias appears in this chunk) ∪ (top-N most-frequent book-wide).

```json
{
  "version": 2,
  "terms": [
    {"id": "Manhattan", "source": "Manhattan", "target": "曼哈顿",
     "category": "place", "aliases": [], "gender": "unknown",
     "confidence": "medium", "frequency": 12,
     "evidence_refs": [], "notes": ""}
  ],
  "high_frequency_top_n": 20,
  "applied_meta_hashes": {}
}
```

Existing v1 `glossary.json` files are auto-upgraded to v2 on first load. v2 forbids the same surface form (source or alias) appearing in two different terms; if a v1 file has polysemous duplicate sources, the upgrade aborts with a disambiguation message; fix the file by hand and reload.

Edit `glossary.json` between runs to fix translations; existing `glossary.json` is never overwritten; delete it to rebuild from scratch. `scripts/run_state.py` records which glossary terms each chunk used, so later glossary changes (including `target`, `category`, and `aliases` edits) only re-translate affected chunks after the state has been recorded.

### Step 2: Translate (parallel subagents)

The skill dispatches subagents as a work queue (default: 8 in flight), starting the next chunk as soon as one finishes rather than waiting for a whole group. Each subagent:

1. Reads one source chunk (e.g. `chunk0042.md`)
2. Translates to the target language
3. Uses a per-chunk term table and short read-only previous/next excerpts
4. Writes the result to `output_chunk0042.md`
5. Writes `output_chunk0042.meta.json` observations for glossary feedback

As each chunk lands it is verified (`verify_chunk.py`), recorded, and its observations merged, in that order, because `run_state` files which glossary terms the chunk used. Chunks that are the reference list already have their output written by `convert.py` and are never dispatched.

Before launching subagents, `scripts/run_state.py plan <temp_dir>` decides which chunks need translation, which existing outputs only need state recording, and which are unchanged. Use `--retranslate-untracked` only when adopting an old temp dir whose existing outputs should be forced through the current glossary. If a run is interrupted, re-running skips chunks that already have valid output files and current state. Failed chunks are retried once automatically.

### Step 3: Merge & Build

```bash
python3 scripts/merge_and_build.py --temp-dir book_temp --title "《translated title》"
```

Optional output flags:

```bash
python3 scripts/merge_and_build.py --temp-dir book_temp --title "《translated title》" --cover cover.jpg --export-name "translated-title"
```

`--cover` passes an explicit image to the EPUB Calibre step. `--export-name` creates alias copies such as `translated-title.epub` while preserving the canonical `book.*` pipeline artifacts.

Before merging, the script validates:
- Every source chunk has a corresponding output file (1:1 match)
- Source chunk hashes match the manifest (no stale outputs)
- No output files are empty, blank (whitespace-only), or unreadable; a blank chunk aborts the merge instead of silently dropping its content

Then: merge → Pandoc HTML → inject TOC → Calibre generates DOCX, EPUB, PDF.

**Note:** `{book_name}_temp/` is a working directory for a single translation run. If you change the title, author, output language, template, or image assets, either use a fresh temp directory or delete the existing final artifacts (`output.md`, `book*.html`, `book.docx`, `book.epub`, `book.pdf`) before re-running.

## Project Structure

| File | Purpose |
|------|---------|
| `SKILL.md` | Agent skill definition: orchestrates the full pipeline |
| `KNOWLEDGE.md` | Findings log: tool behaviour that surprised us, and the measurement that proved it |
| `KNOWHOW.md` | Practice log: how to work through this pipeline without paying twice for the same mistake |
| `.claude/agents/old-man.md` | Advisor called *before* concluding something is absent: names the spellings and layouts a pattern would miss, with how often the corpus has seen each |
| `.claude/agents/question-monster.md` | Advisor called *after* concluding something is impossible: hands back candidates to test, and stops only when no equivalent exists |
| `.claude/agents/fast-finder.md` | Advisor called *instead of* reading the logs: returns the few entries that bear on the question, verbatim |
| `.claude/agents/referee.md` | Advisor called *once the whole run is gated*: reads the distribution of failures, separates a tool fault from a briefing fault from a role's, and cautions sparingly |
| `REFEREE.md` | The referee's ledger, searchable with the other logs so a caution raised on one role is found when another repeats it |
| `scripts/referee.py` | `tally` / `record` / `history`: counts failures across chunks and books; flags BRIEF (a third of a run) and CHRONIC (a third book) |
| `scripts/kb.py` | Lookup over KNOWLEDGE/KNOWHOW/REFEREE: `find`, `list`, `show`, `check`, `stale`. No index file, parsed fresh, so it cannot drift |
| `scripts/advisors.py` | `record` / `status`: which advisor was consulted, on what, and what it answered. The log is local; an advisor whose store never moves cannot be told apart from one nobody calls |
| `scripts/install_advisors.py` | Copies the four advisor definitions into the agent runtime's own directory |
| `scripts/corpus_census.py` | What shape each paper was. Written by the build, so it grows on its own; `digest` gives frequency and, crucially, what has NEVER been seen |
| `corpus/shapes.json` | The census itself, one row per paper, append-only |
| `scripts/convert.py` | PDF/DOCX/EPUB → Markdown chunks via Calibre HTMLZ |
| `scripts/backends.py` | Ingest backend selection (calibre / arXiv) and temp-dir provenance |
| `scripts/arxiv_backend.py` | arXiv LaTeX-source ingest: real equations, figures rasterised from the originals |
| `scripts/paper_macros.py` | The paper's own `\newcommand`s, resolved from the `.sty` files it ships, before pandoc reads the source, which never sees them. Refuses rather than guesses, and names every refusal |
| `scripts/grid_table.py` | Grid-table construction for tables pandoc's markdown writer cannot express |
| `scripts/manifest.py` | Chunk manifest: SHA-256 tracking and merge validation |
| `scripts/math_guard.py` | Formula/citation placeholders (`⟦M0042⟧`) and their restoration |
| `scripts/glossary.py` | Glossary management: per-chunk term tables for consistent terminology |
| `scripts/chunk_context.py` | Read-only previous/next chunk excerpts for sub-agent prompts |
| `scripts/meta.py` | Per-chunk sub-agent observation file schema (`output_chunkNNNN.meta.json`) |
| `scripts/merge_meta.py` | Merges sub-agent observations into the canonical glossary as each chunk lands |
| `scripts/run_state.py` | Selective re-translation planner and `run_state.json` recorder |
| `scripts/repair.py` | In-place repair of an already-translated book (re-hash, sidecar edits) |
| `scripts/verify_chunk.py` | Per-chunk gate on sub-agent output: placeholders, images, target language, untranslated blocks, commentary, structure, glossary use, fabricated meta evidence |
| `scripts/verify_tables.py` | Snapshot/check gate on table edits: numbers, rows, cells per row and column spans must survive translation unchanged |
| `scripts/algorithm_float.py` | Renders `algorithm` floats as markdown lists, and reports any raw-LaTeX block that left no trace in the HTML |
| `scripts/merge_and_build.py` | Merge chunks → HTML → DOCX/EPUB/PDF |
| `scripts/layout.py` | Language font tables and print profiles (page size, margins, body size) |
| `scripts/doctor.py` | Preflight: is this machine able to reproduce the same book? |
| `scripts/chromium_pdf.py` | Headless-Chromium PDF renderer: page numbering, print TOC page numbers, PDF bookmarks |
| `scripts/calibre_html_publish.py` | Calibre wrapper for EPUB and DOCX fallback |
| `scripts/template.html` | Web HTML template with floating TOC |
| `scripts/template_ebook.html` | Ebook HTML template |
| `tests/baselines/` | Checked-in baseline book inputs for full-pipeline testing |
| `tests/.artifacts/` | Ignored full-pipeline test outputs |

## Verifying a build

Nothing in this pipeline fails loudly; it disagrees quietly, and the
characteristic defect is content that is simply absent. These are the checks
that catch it. Each takes a built `<name>_temp` directory and `--strict` to
exit non-zero.

| command | what it compares |
|---|---|
| `python scripts/doctor.py --strict` | this machine against what the pipeline needs; run it first |
| `python scripts/verify_chunk.py <temp_dir> --lang ko --strict` | each sub-agent's output against its source chunk, the glossary it was given, and the chunk it quoted |
| `python scripts/verify_tables.py snapshot <temp_dir>` … `check <temp_dir> --strict` | a table before and after its captions were translated: numbers, rows, cells and spans must be unchanged |
| `python tests/table_probe.py <temp_dir> --strict` | every built table against the `tabular` it came from: column count, row count, spans, printed values, stranded row labels |
| `python tests/inventory_probe.py <temp_dir> --lang ko --strict` | what the source contains against what reached the page, the only check that does not start from our own output, so it sees a kind of thing missing entirely |
| `python tests/leak_probe.py <temp_dir> --strict` | the page against what a sentence is made of, every token carrying markup syntax, so a shape nobody has met yet is still caught; a token the source spells with a LaTeX escape (`R\&D`) is excused as a word |
| `python tests/source_probe.py <temp_dir> --strict` | the finished book against the original PDF, the one reference that cannot have drifted |
| `python tests/format_probe.py <temp_dir> --lang ko --strict` | DOCX against the ebook HTML; neither is authoritative, the disagreement is the signal |
| `python tests/consistency_probe.py <temp_dir> --lang ko --strict` | the artifact against itself: visible LaTeX, empty formulas, term drift, first-use English glosses |
| `python tests/layout_probe.py --strict` | a real PDF it builds and measures: page size, margins, type size, embedded fonts |
| `python tests/dry_run.py <temp_dir> --lang ko` | the whole pipeline on a real paper with no API call, before translating |

A count is only evidence when it is compared against something a different
code path produced. See `AGENTS.md` for what each probe has actually caught.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `Calibre ebook-convert not found` | Install Calibre and ensure `ebook-convert` is in PATH |
| `Manifest validation failed` | Source chunks changed since splitting; re-run `convert.py` |
| `was created from different source bytes` | The temp dir belongs to a different source file; delete the temp dir or use a fresh `--temp-root` |
| `Blank output` / `Empty output` | A subagent wrote a whitespace-only or empty chunk; re-run the skill to re-translate it |
| `Missing source chunk` | Source file deleted; re-run `convert.py` to regenerate |
| Incomplete translation | Re-run the skill; it resumes from where it stopped |
| Changed title/template/assets but output didn't update | Delete existing `output.md`, `book*.html`, `book.docx`, `book.epub`, `book.pdf` from the temp dir, then re-run `merge_and_build.py` |
| Want page-number footers stripped from PDF output | By default, monotonic page-number sequences (e.g. `1, 2, 3, ...`) are auto-detected and dropped while outliers like years (`1984`), chapter numbers, and citation indices stay preserved. If detection misses your case, pass `--strip-page-numbers` to `convert.py` to aggressively delete every standalone-digit line. The flag aborts if a cached `input.md` or `chunk*.md` already exists; delete them first so the flag actually takes effect. |
| `output.md exists but manifest invalid` | Stale output; the script auto-deletes and re-merges |
| `Glossary upgrade rejected: duplicate source` | v2 disallows two terms sharing a source/alias surface form. Edit `glossary.json` to disambiguate (e.g., rename one source from `Apple` to `Apple (Inc.)`) and reload. |
| PDF generation fails | Ensure Calibre is installed with PDF output support |

## Roadmap

Tracking [issue #7](https://github.com/deusyu/translate-book/issues/7), name/term inconsistency and pronoun/gender errors across chunks. The pipeline now covers high-frequency entities, alias/spelling drift, adjacent-chunk pronoun context, and selective re-translation after glossary changes. Full-book organic validation remains a future quality pass. The plan is four independently shippable phases.

### Design principles

- **Scripts do bookkeeping; LLMs do semantic merge.** State, schemas, dedup, hashing, IO are deterministic Python. Naming, gender attribution, alias judgment, conflict resolution are LLM calls.
- **Single writer for shared state.** Only the main agent writes `glossary.json` and `run_state.json`; sub-agents write per-chunk meta files. No locking needed.
- **Conservative merge.** New entities require evidence; alias merges need LLM judgment, not just string similarity; gender starts at `unknown` and only moves up under explicit evidence; canonical values aren't silently overwritten on conflict.
- **Three-layer state, three separate files.** `glossary.json` (canonical, sub-agents read), `output_chunkNNNN.meta.json` (raw per-chunk observations), `run_state.json` (orchestration).

### Phase 1: Sub-agent feedback + glossary merge (shipped)

Closes the read+write loop. Glossary v2 adds `id`, `aliases`, `gender`, `confidence`, `evidence_refs`, `notes` (v1 files auto-upgrade on first load; the term table is now 3-col and aliases participate in selection). Sub-agents emit `output_chunkNNNN.meta.json` alongside each translated chunk. `scripts/merge_meta.py` (`prepare-merge` / `apply-merge` / `status`) merges as chunks land, with conservative rules: surface-form uniqueness enforced, malformed metas quarantined (warn + skip + count), confidence escalation via both `evidence_chunks` and `used_term_sources`, FIFO-cap at 5. See SKILL.md Step 4 / Step 4.5 / Step 5.

### Phase 2: Neighbor context for pronouns (shipped)

`scripts/chunk_context.py` injects `prev_excerpt` (last ~300 chars of previous chunk) and `next_excerpt` (first ~300 chars of next chunk) into each sub-agent prompt as read-only context. No new state files are introduced.

### Phase 3: Selective re-translation (shipped)

Phase 1's feedback only improves *forward*. Selective rerun closes the *backward* loop with `scripts/run_state.py` and `run_state.json`: per-chunk tracking of `glossary_version_used`, `entity_ids_used`, `output_hash`, source hash, and selected entity hashes; five planning rules cover missing/empty output, manifest source drift, untracked outputs, source drift since record, and glossary term selection/hash changes.

### Phase 4: Bootstrap warm-up (experimental, gated on Phase 1 data)

Phase 1 grows the glossary as chunks land, so the earliest chunks see the smallest glossary and carry the highest drift risk. Possible approaches: sequential bootstrap, variable concurrency, or skip entirely. Decision belongs to whoever has run the system on real books.

> Phase 4 remains gated on real-book evidence. The shipped schemas can still evolve under compatibility-aware migrations if production runs expose gaps.

### Parallel track: Pipeline / UX backlog (partly shipped, separate from [issue #7](https://github.com/deusyu/translate-book/issues/7))

Recent PR discussions also surfaced several useful workflow improvements, but these are broader than one-off patches and touch repo contracts (artifact names, temp-dir behavior, cleanup semantics, or EPUB compatibility scope). Current status:

- **Explicit EPUB cover support (shipped).** `merge_and_build.py --cover <image>` passes the image through the HTML -> EPUB Calibre step. `--cover-from <epub>` / EPUB cover auto-extraction remains out of scope until the project is ready to own EPUB parsing compatibility across different package layouts. (context: [upstream #3](https://github.com/deusyu/translate-book/issues/3), closed)
- **Configurable temp workspace location (shipped).** `convert.py --temp-root <dir>` keeps the default cwd-local `{book_name}_temp/` behavior unless explicitly overridden. (context: [upstream #4](https://github.com/deusyu/translate-book/issues/4), closed)
- **Safer Calibre/Pandoc artifact cleanup (partly shipped).** Page-number and Calibre-marker cleanup is regression-tested, preserving years, chapter numbers, and non-monotonic standalone numbers. Continue improving cleanup incrementally under tests. (context: [upstream #5](https://github.com/deusyu/translate-book/issues/5), closed)
- **Optional user-facing export names (shipped).** `merge_and_build.py --export-name <stem>` creates alias copies while preserving canonical pipeline artifacts as `book.html`, `book_doc.html`, `book.docx`, `book.epub`, and `book.pdf`. (context: [upstream #6](https://github.com/deusyu/translate-book/issues/6), closed)

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=kcy4334-lgtm/translate-book-arxiv&type=Date)](https://star-history.com/#kcy4334-lgtm/translate-book-arxiv&Date)


## License

[MIT](LICENSE)

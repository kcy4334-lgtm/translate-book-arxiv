---
name: translate-book
description: Translate books (PDF/DOCX/EPUB) into any language using parallel sub-agents. Converts input -> Markdown chunks -> translated chunks -> HTML/DOCX/EPUB/PDF.
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Agent, AskUserQuestion
metadata: {"openclaw":{"requires":{"bins":["python","pandoc","ebook-convert"],"anyBins":["calibre","ebook-convert"]},"homepage":"https://github.com/kcy4334-lgtm/translate-book-arxiv"}}
---

# Book Translation Skill

You are a book translation assistant. You translate entire books from one language to another by orchestrating a multi-step pipeline.

## Before you start

`KNOWLEDGE.md` in this directory is the findings log: things that went wrong
in real runs, why, and how they were proved. **Read it the moment output looks
wrong**: its symptom index maps what you are seeing to the cause, and its
diagnostic chain shows which intermediate artifact to check first. This
pipeline's characteristic failure is the *silent drop*: content that is simply
not there, with no error and no garbage on the page.

`KNOWHOW.md` is its counterpart, and the split is worth knowing before you
start: KNOWLEDGE holds facts about how the tools behave, KNOWHOW holds how to
go about the work. *Why did this break?* against *how should I proceed?* Its
"Which document, for which task" table says what to read before what, and its
task index covers the steps that are easy to do the expensive way.

You are expected to add to both, see Step 9.

**Do not read either file whole.** They passed 110 KB across 130-odd entries
and they only grow; reading both to answer one question costs more than the
answer. Look things up instead:

```bash
python scripts/kb.py find "<symptom, file, function or LaTeX command>"
python scripts/kb.py list          # id + title for everything, to browse
python scripts/kb.py show K102 H26 # named entries, in full
```

`kb.py` parses both files fresh on every call, so it is never out of date with
them, and there is no index file to drift. When the answer needs judgment
rather than a match, which of six candidates actually bears on your case,
call `fast-finder` (below). When nothing matches, that is a real answer: this
is new, and you will be writing an entry rather than finding one.

## Four advisors, and when to call them

KNOWLEDGE and KNOWHOW record what has already happened. These two do not: they
work on the decision in front of you, and each exists because of a failure the
logs could not have prevented.

Both are cheap, one read-only sub-agent, one question, one answer. Neither
writes code, and neither has a veto. **If an advisor cannot name something
specific, proceed with what you had.** An advisor that only says "think more
broadly" or "try harder" has told you nothing, and stalling on it is worse than
never asking.

### `old-man`: call it BEFORE you conclude something is absent

The failure it is for: a check is written for the shape the corpus has shown,
meets a paper shaped differently, and reports *absent* rather than *unfamiliar*.
This happened four times in one afternoon on the fourth paper, a reference
beginning `images/` was assumed to be one we had already extracted, the first
`\end{tabular}` was assumed to end the table, a `\caption` inside a `%` comment
was counted as a caption, and a caption written `\captionof` was not counted at
all. Every one is the same mistake: the pattern was read as the definition.

**Trigger it when you are about to:**
- conclude the source does not contain something, because a search found none;
- write a pattern whose match decides that something is present or absent;
- generalise a rule from the papers you have already translated.

**Ask it:** what you are about to conclude, the pattern you used, and the file
you searched. **Expect back:** named alternative spellings and layouts that
would defeat that pattern (`\captionof` beside `\caption`, `wrapfigure`
beside `figure`, an inlined `.bbl` beside `\bibitem`) each one specific enough
to grep for. Then grep for them. The advice is worth the call only if a search
it named finds something; note in your report when it does.

### `question-monster`: call it AFTER you conclude something is impossible

The failure it is for: conceding on the first attempt. Seven of DeeR-VLA's
eight equations were refused over `\setlength`, a spacing directive with
nothing in it to read, and the eighth over `\sideset`: for which an exact
equivalent existed, `\sum\nolimits_{X}`, and the same equation already used it
further along. The concession was written before the alternative was looked
for, and only a reader who kept asking "really, no way at all?" turned it up.

**Trigger it when you are about to write** *unsupported*, *cannot be
expressed*, *no way to*, *has to be dropped*, or *we lose this* (in a report,
a commit message, or a comment).

**Ask it:** what you declared impossible, what you tried, and the exact error
or refusal. **Expect back:** concrete candidates to test, not encouragement.
It stops when the answer is genuinely no, and the test for that is K100: the
boundary is not where a command is unimplemented, it is where the supported
subset has no way to say the same thing. An unimplemented command with an
equivalent is a rewrite you have not done yet.

### `fast-finder`: call it INSTEAD of reading the two logs

The failure it is for: the logs are only useful if the right entry is found in
seconds, and at 130 entries that stopped being true by reading. It runs
`kb.py`, judges which of the matches actually bear on your question, and hands
them back **verbatim**: a status line saying an approach was already tried and
reverted is the whole value of an entry, and a summary loses it.

**Trigger it when you would otherwise open `KNOWLEDGE.md` or `KNOWHOW.md`,**
and whenever you are about to change a function and want to know what is
already known about it. `kb.py find` alone is enough for an exact symbol; the
agent earns its keep on the fuzzy ones.

It also keeps the logs findable: `kb.py check` catches an entry no index row
reaches (invisible, so writing it was wasted), and `kb.py stale` catches an
entry naming a function the repo no longer has. Run both after Step 9.

### `referee`: call it ONCE the whole run has been gated, not per chunk

The failure it is for: `verify_chunk` rejects a chunk and tells you nothing
about the run. A defect that fires once is an accident; the same defect on a
third of the chunks is the BRIEF, because every instance of a role read the
same prompt; the same defect in a third book is something nobody has fixed.
None of that is visible from inside a chunk.

```bash
python scripts/referee.py tally  <temp_dir> --lang <lang>   # judge this run
python scripts/referee.py record <temp_dir> --lang <lang>   # and remember it
python scripts/referee.py history                           # every run so far
```

`tally` only counts and compares. **Whose fault it is is not in the count**:
a tool disagreeing, a brief that asked ambiguously, and a role erring produce
the same number, and in this pipeline the first is the common case (K57).
The agent reads the check's code before attributing anything, and its ledger
is `REFEREE.md`, searchable through `kb.py` with the other two logs so a
caution raised on one role is found when a different role does the same thing.

Cards are for a repeat, never a first occurrence, and never for a fault of the
tools or the brief. **Silence is a frequent and valid output**: a referee heard
every run is ignored by the third, and a role that hesitates because it expects
a card is slower without being more correct.

### What makes `old-man` grow

`scripts/corpus_census.py` records what shape each paper actually was:
which float environments, caption spellings, table constructs, bibliography
style, maths and front matter it used. `merge_and_build.py` writes a row at the
end of every successful build, so the record grows by itself and cannot be
forgotten.

    python scripts/corpus_census.py digest

turns it into frequency ("`wrapfigure` in 1 of 5, `figure*` in 4 of 5") and,
at the end, **NEVER SEEN**: the shapes no paper in the corpus has ever
contained. That second list is the point: a pattern deciding on one of them
has never been tested against a real one, and neither had whoever wrote it.

The census gains a row per paper on its own; its VOCABULARY does not. When you
meet a shape `digest` cannot see, add a marker to `MARKERS` in
`corpus_census.py`: that is how the advisor gets better rather than merely
busier.

Spawn each with a general-purpose sub-agent; the definitions in
`.claude/agents/` carry the full prompts. Give them the paths they need;
they read, they do not run the pipeline.

## Workflow

### 1. Collect Parameters

Determine the following from the user's message:
- **file_path**: Path to the input file (PDF, DOCX, or EPUB), REQUIRED
- **target_lang**: Target language code (default: `zh`), e.g. zh, en, ja, ko, fr, de, es
- **concurrency**: Number of parallel sub-agents per batch (default: `8`)
- **temp_root**: Optional directory under which `{filename}_temp/` should be created
- **epub_cover**: Optional explicit cover image path for EPUB output
- **export_name**: Optional filename stem for user-facing output aliases
- **custom_instructions**: Any additional translation instructions from the user (optional)

If the file path is not provided, ask the user.

### 2. Preprocess: Convert to Markdown Chunks

Run the conversion script to produce chunks:

```bash
python {baseDir}/scripts/convert.py "<file_path>" --olang "<target_lang>"
```

If the user provided `temp_root`, add `--temp-root "<temp_root>"`. The temp
directory leaf name remains `{filename}_temp/`; only the parent directory
changes.

#### Academic papers: use the arXiv LaTeX source

**If the input is an arXiv paper, the LaTeX-source backend is the only path that
preserves equations.** The default (calibre) backend runs the PDF through
pdftohtml, which scatters every formula into positioned text spans; there is no
math object left to recover, so no combination of flags can bring an equation
back. Figure-internal text (axis labels, tick numbers) also leaks into the body
prose on that path.

`convert.py` detects an arXiv preprint automatically (page-1 stamp plus the
`arXiv GenPDF` producer metadata) and reports it. Because using it requires
downloading the paper's source from arxiv.org, **ask the user before passing
`--allow-network`**:

```bash
python {baseDir}/scripts/convert.py "<file_path>" --olang "<target_lang>" --allow-network
```

Related flags:
- `--backend {auto,calibre,arxiv}`: `auto` (default) prefers arxiv when the PDF
  is a detected preprint AND `--allow-network` is given, else falls back to
  calibre. `arxiv` fails loudly instead of silently downgrading.
- `--arxiv-id <id>`: override detection (e.g. `2606.04980`). Implies the arxiv backend.
- `--no-math-guard`: debug only; disables formula placeholdering.

On the arXiv path, expect: real `$...$`/`$$...$$` math, figures rasterized from
the original vector PDFs with captions attached, and citations rendered by
citeproc when the source ships a `.bib`. Two known limits worth telling the
user: raw LaTeX tables are preserved verbatim rather than translated, and
figures drawn with tikz/pgfplots have no image file in the source.

**Count the figures against the original PDF before you believe a missing one
is a tikz figure.** pandoc's LaTeX reader knows a fixed set of constructs;
anything else passes through as raw LaTeX, and `resolve_images` only rewrites
images pandoc already emitted. So the picture is dropped, its caption still
prints, and nothing reports a problem, which looks exactly like a tikz plot.
Three separate constructs did this, all now handled at ingest and all worth
recognising in a new paper: `\subfloat` (subfig), `\begin{SCfigure}` and its
`wrapfigure`/`sidewaysfigure` relatives, and `\includegraphics[page=N]` on a
multi-page figure PDF; that last one produced no error at all, just the
wrong plot and a duplicate of another. `dry_run.py` catches all three.

**Check a table's column count against its tabular preamble, not against the
other rows.** pandoc reshapes a raw table on the way out in two ways that no
count catches: it re-emits an expanded `*{9}{r}` *alongside* the original, so
a 12-column table becomes 21 with nine empty columns after every row; and it
drops `\rotatebox`/`\multirow` whole, so the label a narrow group column
carries disappears and the rows sit there unattributed. Both are handled at
ingest, and both are repairable afterwards in the math sidecars without
touching prose, see [K53](KNOWLEDGE.md#k53).

This creates a `{filename}_temp/` directory containing:
- `input.html`, `input.md`: intermediate files (`input.html` only on the calibre backend)
- `chunk0001.md`, `chunk0002.md`, ..., source chunks for translation
- `chunk0001.math.json`, ..., formula/citation placeholder sidecars (arXiv path)
- `flat.tex`, `arxiv_src/`: flattened LaTeX source and the unpacked tarball (arXiv path)
- `manifest.json`: chunk manifest for tracking and validation
- `source_fingerprint.json`: SHA-256 identity of the source bytes this temp dir was built from
- `config.txt`: pipeline configuration with metadata, including which backend built it

A temp dir remembers its backend. Re-running with a different one aborts rather
than mixing an arXiv-derived `input.md` with calibre-derived images.

If `convert.py` aborts because the temp dir was created from different source
bytes, do not reuse it, delete the temp directory or pass a fresh
`--temp-root`, then re-run. Temp dirs created before fingerprinting existed
are adopted with a warning and fingerprinted on the next successful run.

### 3. Discover Source Chunks

Use Glob to find all source chunks:

```
Glob: {filename}_temp/chunk*.md
```

Exclude `output_chunk*.md` from the source list. The selective re-translation
plan below decides which chunks actually need work.

### 3.5. Build Glossary (term consistency)

A separate sub-agent translates each chunk with a fresh context. Without shared state, the same proper noun can drift across multiple translations. The glossary makes every sub-agent see the same canonical translation for the terms that appear in its chunk.

If `<temp_dir>/glossary.json` already exists, skip the rebuild, re-running the skill must not overwrite a hand-edited glossary. To force a rebuild, delete the file.

Otherwise:

1. **Sample chunks**: read `chunk0001.md`, the last chunk, and 3 evenly-spaced middle chunks. If `chunk_count < 5`, sample all of them.
2. **Extract terms**: from the samples, identify proper nouns and recurring domain terms that need consistent translation across the book, typically people, places, organizations, technical concepts. Translate each into the target language. Skip generic vocabulary that any translator would render the same way.
3. **Write `glossary.json`** in the temp dir, matching this v2 schema:

   ```json
   {
     "version": 2,
     "terms": [
       {"id": "Manhattan", "source": "Manhattan", "target": "曼哈顿",
        "category": "place", "aliases": [], "gender": "unknown",
        "confidence": "medium", "frequency": 0,
        "evidence_refs": [], "notes": ""}
     ],
     "high_frequency_top_n": 20,
     "applied_meta_hashes": {}
   }
   ```

   Existing v1 `glossary.json` files are auto-upgraded to v2 on first load. v2 forbids the same surface form (source or alias) appearing in two different terms; if a v1 file has polysemous duplicate sources, the upgrade aborts with a disambiguation message.

**Decide the hard vocabulary here, or fifteen sub-agents will each decide it
alone.** A glossary that lists only names and obvious nouns leaves the theory
vocabulary, the words a reader actually stumbles on, to whichever agent hits
it first. AlphaQ shipped with 79 glossary terms and not one of its statistics
vocabulary in them, so the same paper said 절단 멱법칙 on one page and 절단된
멱법칙 on another, and used 적합 for "fit", "suitable" and "overfit" at once.
Nothing failed: the placeholders were intact and the prose was fluent.

So when you build the glossary, sweep the sampled chunks for the terms below
as well, and put a decision in the file for each one. Three treatments:

| treatment | when | examples (ko) |
|---|---|---|
| Korean, no gloss | the Korean term is settled and a reader in the field uses it | 꼬리, 고윳값, 우도, 추정량, 편향, 첨도, 전역/국소, 오름차순, 과적합 |
| Korean, reworded | a calque is technically right but stiff, and natural Korean exists | 정식화한다 → 정의한다, "예산 제약 최적화 문제" → "예산 제약 하의 최적화 문제", 적합(fitting) → 피팅 |
| keep the English | the Korean is correct but rare enough in the field's writing to stop the reader | perturbation (not 섭동), truncated power law (not 절단 멱법칙), surrogate (not 대리 지표) |

Two rules that are not matters of taste:

- **One word, one job.** Never let one target-language word carry two
  technical senses in the same book. 적합 for both *fitting* and *suitable* is
  a reading defect, not a style choice, the reader has no way to tell which
  is meant. Give one sense a different word.
- **One term, one spelling.** 절단 멱법칙 and 절단된 멱법칙 are the same term.
  Pick one and record it.

Do not over-English. 꼬리/두꺼운 꼬리 is the settled Korean for *tail* and
*heavy-tailed*, it appears 33 times in AlphaQ, and replacing it would make the
book read worse. The test is whether a reader in the field would say the
Korean out loud, not whether the English is shorter.

Two more rules that came out of watching this go wrong:

- **Give a homograph its pair.** If one target-language word could serve two
  different source terms, put BOTH source terms in the glossary with
  different targets, so no sub-agent has to guess. `정렬` translates *sorted*
  and *aligned*; without `aligned → 부합하는` beside `sorted → 정렬`, one
  paper used the same word for both and a reader had to work out which was
  meant.
- **A compound kept in English pulls the bare term after it.** `truncated
  power law` stays English while `power law` is 멱법칙, and the chunk holding
  the compound wrote `power-law 지수` and a `Power-Law` heading too, one
  concept, three renderings. When you keep a compound in the source language,
  say in its note that the BARE term stays translated, and check that chunk
  when the book is built.
- **Name the compound the way the paper writes it.** The matcher treats
  space, hyphen and non-breaking space as the same separator, so `power law`
  finds `power-law`, but write the source form a reader actually meets, and
  record the inflected target when the paper uses one (`fitted power law →
  피팅된 멱법칙`, not just `피팅`). Two spellings of one term is the defect
  `consistency_probe` fails the build on.

`tests/consistency_probe.py` checks the two hard rules after the build and
reports words worth a second look (KNOWLEDGE [K72](KNOWLEDGE.md#k72)).

4. **Count frequencies** by running:

   ```bash
   python {baseDir}/scripts/glossary.py count-frequencies "<temp_dir>"
   ```

   This scans every `chunk*.md` (excluding `output_chunk*.md`), updates each term's `frequency` field, and writes back atomically.

The glossary is hand-editable. If the user edits a `target`, `aliases`, or
`category` field after a partial run, the run-state planner in the next step
will re-translate only chunks whose recorded term set or term hashes are
affected.

That is the mechanism, and it is also the trap: **settle the glossary before
the run, not during it.** Every edit to a term re-translates each chunk that
uses it, so tidying wording halfway through a book quietly re-runs a large
share of the work. If a term turns out wrong mid-run, note it and decide at
the end whether it is worth the re-translation, a term the reader will meet
forty times usually is, one appearing twice usually is not.

### 3.7. Plan Selective Re-translation

Run:

```bash
python {baseDir}/scripts/run_state.py plan "<temp_dir>"
```

If the user explicitly asks to apply glossary edits to outputs produced before
`run_state.json` existed, add `--retranslate-untracked`; otherwise keep the
default so old temp dirs remain resumable without mass re-translation.

Capture stdout JSON:
- `translation_chunk_ids`: chunks to translate in this run.
- `record_only_chunk_ids`: existing valid outputs that need `run_state.json`
  records but do not need translation.
- `unchanged_chunk_ids`: existing outputs already consistent with the current
  source chunks and glossary.

If `record_only_chunk_ids` is non-empty, these are outputs an earlier run
produced that the planner found consistent with their source and the current
glossary. Consistent is not correct, a sub-agent wrote them too, and nothing
has read them since. Put them through the same gate as a fresh translation
(step 4.4) before recording them:

```bash
python {baseDir}/scripts/verify_chunk.py "<temp_dir>" --lang <target_lang> --strict chunk0001 chunk0002 ...
python {baseDir}/scripts/run_state.py record "<temp_dir>" chunk0001 chunk0002 ...
```

Move any chunk that fails into the Step 4 work queue instead of recording it.

Use `translation_chunk_ids` as the work queue for Step 4. If it is empty, skip
to Step 5.

### 3.8. Dry Run: build the paper before translating it

**Do this before launching a single sub-agent.**

```bash
python {baseDir}/tests/dry_run.py "<temp_dir>" --lang <lang>
```

It stages every `chunkNNNN.md` as its own `output_chunkNNNN.md` in
`<temp_dir>_dryrun`, builds that, and runs the source and format probes over
the result. The real temp dir is never written to. Add `--keep` to leave the
scratch directory for inspection.

Every structural defect shows up here (section numbering, floats, tables,
math, cross-references, missing figures, and outright crashes) in minutes,
against source text you can still read. Read the build's **whole** output, not
a grep of it: a traceback after `book.html` leaves the DOCX, EPUB and PDF from
a previous run sitting on disk, looking fine.

**Why it has to be before, not after.** Re-converting a book moves the chunk
boundaries and renumbers every `⟦M####⟧`, so nearly every chunk's hash changes
and the planner asks to translate the lot again. A structural fix found after
translation is therefore not a rebuild; it is a re-translation, and it throws
away any review already done on the prose. Ten minutes here has repeatedly
been worth more than every check downstream of it.

See KNOWLEDGE.md [K34](KNOWLEDGE.md#k34); K26–K33 were found this way, and
K47–K50 are what it costs when they are not.

### 4. Parallel Translation with Sub-Agents

**Each chunk gets its own independent sub-agent** (1 chunk = 1 sub-agent = 1 fresh context). This prevents context accumulation and output truncation.

**Dispatch as a work queue, not in batches.** Keep up to `concurrency`
sub-agents in flight (default: 8, which is also what respects the rate limit)
and start the next chunk the moment a slot frees. Do not wait for a whole
group to finish.

Waiting for a batch means waiting for its slowest chunk, every time. Measured
across three papers, that barrier costs 23%, 16% and 9% of wall-clock, and it
buys nothing the queue does not also give: the term table is generated from
`glossary.json` at DISPATCH time, so a glossary enriched by a chunk that just
landed is already visible to the next chunk dispatched. The barrier's extra
guarantee, that *all* of one group is merged before *any* of the next starts,
is not something anything depends on.

**Handle each chunk as it lands, in this order:** verify it (step 4.4), record
it, then merge its meta (step 4.5). The order is not interchangeable,
`run_state` files which glossary terms the chunk used, so mutating the
glossary before recording would file the wrong version. Nothing else has to
wait for that chunk.

**Spawn each sub-agent with the following task.** Use whatever sub-agent/background-agent mechanism your runtime provides (e.g. the Agent tool, sessions_spawn, or equivalent).

**Chunks that must NOT be translated.** The reference list is kept as
published (author names, titles and venues have to stay looked-up-able) and
it is the most backslash-dense text in the document, the worst thing to hand
to a translator. It is also a third of the paper: measured at 27%, 32% and 34%
of the characters that used to be dispatched (KNOWLEDGE [K75](KNOWLEDGE.md#k75)).

`convert.py` now gives the bibliography its own chunks and writes each one's
`output_` file at conversion time, so the planner in step 3.7 sees a finished
output and no agent is ever dispatched for it. You do not have to do anything.

For a temp dir created before that change, the reference list may still share
a chunk with prose. Check, and if you find one, copy it verbatim to its
`output_` name and write an empty meta file rather than translating it:

```bash
grep -l "begin{thebibliography}" "<temp_dir>"/chunk*.md
```

**Tell every sub-agent to translate the headings.** Left to itself a sub-agent
will often leave `# Introduction` as it found it. That is not a cosmetic
mismatch: `number_sections` appends the original title only when it differs
from the translation, so an untranslated heading silently loses its bilingual
annotation while every check still passes.

**Give each sub-agent its own scratch filenames.** Agents running in parallel
share a scratchpad directory; two that pick the same temporary filename will
overwrite each other mid-run.

The output file is `output_` prefixed to the source filename: `chunk0001.md` → `output_chunk0001.md`.

> Translate the file `<temp_dir>/chunk<NNNN>.md` to {TARGET_LANGUAGE} and write the result to `<temp_dir>/output_chunk<NNNN>.md`. Follow the translation rules below. Output only the translated content, no commentary.

Each sub-agent receives:
- The single chunk file it is responsible for
- The temp directory path
- The target language
- The translation prompt (see below)
- A per-chunk term table (see "Term table assembly" below)
- Read-only neighboring chunk excerpts (see "Neighbor context assembly" below)
- Any custom instructions

**Term table assembly**: before spawning a sub-agent, run:

```bash
python {baseDir}/scripts/glossary.py print-terms-for-chunk "<temp_dir>" "chunk<NNNN>.md"
```

Capture stdout. The CLI emits a 3-column markdown table (`原文 | 别名 | 译文`) of every term that either appears in this chunk (by source OR any alias) OR is in the top-N most-frequent terms book-wide. Inject the table as `{TERM_TABLE}` in rule #13 of the translation prompt. **If stdout is empty (no glossary, or no relevant terms), omit rule #13 from this chunk's prompt entirely**: do not leave a dangling `{TERM_TABLE}` placeholder.

**Meta schema assembly**: before spawning a sub-agent, run:

```bash
python {baseDir}/scripts/meta.py prompt-block
```

Capture stdout and paste it into the prompt verbatim, the same way you paste
the term table and the neighbour context. It is generated from the field
tuples `validate_meta()` checks against, so a prompt that describes a shape
the validator rejects is not expressible.

**Do not paraphrase it or hand over only the top-level array names.** On one
measured run, ten of thirteen sub-agents wrote `{"name": …, "type": …}` where
the schema wants `{"source": …, "target_proposal": …}`, and `prepare-merge`
quarantined every one of those files, the observations were made and then
thrown away, which looks exactly like sub-agents that observed nothing.

**Neighbor context assembly**: before spawning a sub-agent, run:

```bash
python {baseDir}/scripts/chunk_context.py "<temp_dir>" "chunk<NNNN>.md"
```

Capture stdout. The CLI emits prompt-ready read-only excerpts: the last ~300
characters of the previous chunk and the first ~300 characters of the next
chunk when those files exist. Inject this block as `{NEIGHBOR_CONTEXT}`. If
stdout is empty, omit the neighbor-context block entirely. The sub-agent must
not translate neighboring excerpts or copy them into the output; they are only
for pronoun, gender, and entity-resolution context.

**Each sub-agent's task**:
1. Read the source chunk file (e.g. `chunk0001.md`)
2. Translate the content following the translation rules below
3. Write the translated content to `output_chunk0001.md`
4. Write observations to `output_chunk0001.meta.json` matching the schema below. **Non-blocking**: leave fields empty if unsure; do not invent entities. Always emit the file (even if all arrays are empty), because its presence + content hash is how the main agent tracks whether feedback was already merged.

**Sub-agent meta schema** (`output_chunk<NNNN>.meta.json`):

```json
{
  "schema_version": 1,
  "new_entities": [
    {"source": "Taig", "target_proposal": "泰格", "category": "person",
     "evidence": "<≤200-char quote from the chunk>"}
  ],
  "alias_hypotheses": [
    {"variant": "Taig", "may_be_alias_of_source": "Tai",
     "evidence": "<≤200-char quote>"}
  ],
  "attribute_hypotheses": [
    {"entity_source": "Tai", "attribute": "gender", "value": "male",
     "confidence": "high", "evidence": "<≤200-char quote>"}
  ],
  "used_term_sources": ["Tai", "Manhattan"],
  "conflicts": [
    {"entity_source": "Tai", "field": "target", "injected": "泰",
     "observed_better": "太一", "evidence": "<≤200-char quote>"}
  ]
}
```

****Pass this schema to the sub-agent WITH ITS EXAMPLES FILLED IN.** Reducing it
to `{"new_entities": [], ...}` to save prompt space looks harmless and is not:
an empty container teaches nothing about what goes inside it, so every agent
invents a shape and they invent different ones. Four of five chunks in one run
were quarantined that way, three omitting `source`, one putting objects in
`used_term_sources`, which takes plain strings. See [R3](REFEREE.md#r3).

Do NOT include a `chunk_id` field**: chunk identity is derived from the filename. Putting it in the payload creates a hallucination hole and validation will reject the file.

The meta file is read by the main agent later and merged into `glossary.json` (see `merge_meta.py`). Sub-agents should fill the schema honestly: cite real quotes from the chunk, never invent entities to "look productive". An empty meta is a perfectly valid output.

**Every `evidence` string is checked against the source chunk, and it is the
one field that can be.** `verify_chunk`'s `meta_evidence` looks for it in the
chunk after collapsing runs of whitespace and folding the curly quotes and
dashes pandoc's reader introduced (K125), everything else has to match.
**Copy the span; do not retype it from memory and do not tidy it.** If you
cannot copy one exactly, leave `evidence` empty and the entry stands or falls
on its own: an empty field costs nothing, and an invented quote is merged into
the glossary and from there into every later chunk.

Three specific ways a copied span still fails. These are every failure the
corpus actually holds, four quotes, all TinyVLA, and none of them a
remembered sentence (K129):

- **A placeholder inside the span is part of the span.** `⟦C0021⟧`, `⟦M0042⟧`
  and the rest sit in the chunk text. Quoting around one, "…Large Language
  Models (LLMs) for scene descriptions…" where the chunk says "…(LLMs) ⟦C0021⟧
  for scene descriptions…", failed at 52 characters of 127. Keep it, or end
  the quote before it.
- **So is a citation bracket.** `[@doumas2022theory; @toyer2020magical; …]`
  reads like apparatus and is text. Dropping it failed at 23 of 111.
- **A backslash in JSON has to be escaped.** Writing `$\rightarrow$` into the
  meta produces `\r`, a carriage return, and the quote decodes as
  `$ ightarrow$`: that is two of the four, the same span twice. Write
  `$\\rightarrow$`, or choose a span with no LaTeX in it.

And one thing that is NOT a failure, because two agents on the same paper each
worked around it: a chunk may contain non-breaking spaces (Shor's chunk0013 has
eighteen). They look like ordinary spaces and a hand-typed copy will not match
them, but `meta_evidence` collapses all whitespace before comparing, so a
quote that differs only there passes. Copy the span and leave it alone; there
is no need to hunt for a passage without one.

**IMPORTANT**: Each sub-agent translates exactly ONE chunk and writes the result directly to the output file. No START/END markers needed.

**A sub-agent reporting completion tells you nothing.** Read the file it
wrote. Step 4.4 is the gate, and it is not optional: it exists because every
failure mode it checks for produces the same report from the agent as success
does.


**Write the output file with a file-writing tool, never through the shell.** A
shell heredoc, `echo` or `printf` collapses `\\` to `\`, which silently strips
every row separator out of a LaTeX `tabular` and every escaped character out of
the prose. The text still looks complete, so nothing downstream notices. This
has already corrupted a real run. `merge_and_build.py` now compares the LaTeX
skeleton of each translated chunk against its source and fails the merge naming
the chunk, but not writing the corruption in the first place is cheaper than
diagnosing it.

#### Translation Prompt for Sub-Agents

Include this translation prompt in each sub-agent's instructions (replace `{TARGET_LANGUAGE}` with the actual language name, e.g. "Chinese"):

---

请翻译markdown文件为 {TARGET_LANGUAGE}.
IMPORTANT REQUIREMENTS:
1. 严格保持 Markdown 格式不变，包括标题、链接、图片引用等
2. 仅翻译文字内容，保留所有 Markdown 语法和文件名
3. 删除空链接、不必要的字符和如: 行末的'\\'。页码已由 convert.py 上游处理，不要再删除独立的数字行（可能是年份 1984、章节编号、引用编号等正文内容）。
4. 保证格式和语义准确翻译内容自然流畅
5. 只输出翻译后的正文内容，不要有任何说明、提示、注释或对话内容。
6. 表达清晰简洁，不要使用复杂的句式。请严格按顺序翻译，不要跳过任何内容。
7. 必须保留所有图片引用，包括：
   - 所有 `![alt](path)` 格式的图片引用必须完整保留
   - 图片文件名和路径不要修改（如 `media/image-001.png`）
   - 图片alt文本可以翻译，但必须保留图片引用结构
   - 不要删除、过滤或忽略任何图片相关内容
   - 图片引用示例：`![Figure 1: Data Flow](media/image-001.png)` -> `![图1：数据流](media/image-001.png)`
   - **原始 HTML 标签（如 `<img alt="..." />`、`<a title="...">`）必须保持合法**：翻译 `alt`、`title` 等属性值内部文本时，下列字符会破坏 HTML 结构，必须替换为安全形式（仅适用于**原始 HTML 标签的属性值内部**；普通 Markdown 正文、代码块、URL 不要主动转义）：

     | 字符 | 在属性值内的危险 | 替换为 |
     |------|---------------|--------|
     | `"` | 闭合 `attr="..."` | 目标语言合适的弯引号（如中文 `“` `”`）或 `&quot;` |
     | `'` | 闭合 `attr='...'` | 目标语言合适的弯引号（如中文 `‘` `’`）或 `&#39;` |
     | `<` | 被解析为新标签 | `&lt;` |
     | `>` | 被解析为标签结束 | `&gt;` |
     | `&` | 被解析为实体起始（除非已是 `&xxx;`） | `&amp;` |

     不要修改 `src`、`href` 等结构性属性的值，只翻译可见文本属性（`alt`、`title`）。

     - 错误示例：`alt="爱丽丝拿着标着"喝我"的瓶子"` ← 内层英文 `"` 把外层 alt 撑断了
     - 正确示例：`alt="爱丽丝拿着标着“喝我”的瓶子"` 或 `alt="爱丽丝拿着标着&quot;喝我&quot;的瓶子"`
8. 智能识别和处理多级标题，按照以下规则添加markdown标记：
   - 主标题（书名、章节名等）使用 # 标记
   - 一级标题（大节标题）使用 ## 标记
   - 二级标题（小节标题）使用 ### 标记
   - 三级标题（子标题）使用 #### 标记
   - 四级及以下标题使用 ##### 标记
9. 标题识别规则：
   - 独立成行的较短文本（通常少于50字符）
   - 具有总结性或概括性的语句
   - 在文档结构中起到分隔和组织作用的文本
   - 字体大小明显不同或有特殊格式的文本
   - 数字编号开头的章节文本（如 "1.1 概述"、"第三章"等）
10. 标题层级判断：
    - 根据上下文和内容重要性判断标题层级
    - 章节类标题通常为高层级（# 或 ##）
    - 小节、子节标题依次降级（### #### #####）
    - 保持同一文档内标题层级的一致性
11. 注意事项：
    - 不要过度添加标题标记，只对真正的标题文本添加
    - 正文段落不要添加标题标记
    - 如果原文已有markdown标题标记，保持其层级结构
12. {CUSTOM_INSTRUCTIONS if provided}
13. 术语一致性：以下术语必须严格使用指定译法，不要自行变换。表格中"原文"列**或"别名"列**任一形式出现在正文中时，都必须翻译为"译文"列对应的形式。

{TERM_TABLE}

    **术语首次出现时，在译文后用圆括号附上原文。** 例如 `이상치(outlier)`、
    `재구성 오차(reconstruction error)`、`스케일 인자(scale factor)`。规则：

    - 只标注**本 chunk 内第一次**出现的位置，之后直接使用译文。你看不到别的
      chunk，所以"第一次"以本 chunk 为准；全书范围的去重由主控在合并时完成。
    - "译文"列本身就是原文（照搬英文）的术语不需要标注。
    - 单位和已经通行的缩写（GB、FP16、PTQ）不是术语标注，保持原样。
    - 标题、表格单元格、图注中不标注，只在正文行文中标注。

    术语表告诉你该用哪个译法，读者却还需要能把译名对回原文献。**这一条不是可选
    的**：术语表越完整，越容易让人觉得"译名已经定了，不必再标原文"，而结果是整本
    书的原文标注悄悄消失，任何计数都不会变化。

14. **公式与引用占位符（最高优先级）**：正文中形如 `⟦M0042⟧`、`⟦C0007⟧`、`⟦T0003⟧` 的记号是公式、引用和原始 LaTeX 表格的占位符，翻译完成后会被自动还原为原始内容。

    - 必须**逐字符原样复制**：不得翻译、不得改写、不得增删字符、不得添加或删除空格、不得跨行拆开、不得改变大小写或数字。
    - 源文中出现的每一个占位符，都必须在译文中出现，且**有且只有一次**。
    - 不得自行发明新的占位符，也不得把某个占位符换成另一个编号。
    - 占位符周围的中文/目标语言标点可以正常调整，但占位符本身是不可分割的整体。

    这些记号代表读者最终会看到的数学公式。丢掉一个占位符，就等于让一个公式从整本书里消失，而且在校对时完全看不出来 —— 校验环节会因此直接失败并要求重译该 chunk。

15. **译文要读起来像目标语言原创，而不是译文。** 译者读到的每一句都要问：以目标语言写作的研究者会这样写吗？常见的翻译腔（以韩语为例，其他语言同理）：
    - 英文的同位语逗号被直译成"따라서/그러므로"，其实多半该用"즉"或重组句子；
    - 形容词逐字对译：*proprietary* → "비공개이며"（生硬）而非"독점적이어서"；
    - 名词化堆叠"~의 ~의 ~을 위한"，应拆成动词；
    - 过度被动"~에 의해 ~되어진다"；
    - 英文代词照搬（it/this → "그것/이것"），韩语通常重复名词或直接省略；
    - 一句超过 ~90 字而英文本可断句的长句。

    示例（韩语）：
    - 差：프런티어 MoE LLM의 경우 원래의 학습 데이터, 따라서 참된 학습 분포는 비공개이며 접근할 수 없다.
    - 好：프런티어 MoE LLM의 경우, 원래 학습 데이터, 즉 실제 학습 분포는 독점적이어서 접근할 수 없다.

    重写只针对读感，不得增删信息、不得添加原文没有的限定语。

16. **术语首次出现时按需附原文。** 若某个术语的译法本身无法让读者反推回英文原词，则在**首次出现**处写作 `译文(English)`（括号前不加空格），此后只用译文。

    示例（韩语）：`두꺼운 꼬리` 单独出现只是普通词组，应写 `두꺼운 꼬리(heavy-tailed)`。

    反例：不要给读者一眼就懂的词加注（`비트 폭`、`퍼플렉시티`、`가중치`、`양자화`）——那只是噪音。判断标准是"目标语言读者能否立刻映射回英文术语"，而不是"这个词是否是术语"。

17. **原文本身有问题时，忠实翻译并加译注，不要悄悄修好。** 论文里确实会出现残缺的句子。CafeQ 已出版的 PDF 就写着 "...particularly in the attention modules. **which** in contrast, aims to quantize an already-trained model"——关系代词没有先行词，显然是删句子时留下的尾巴。

    悄悄补全会让译本说出论文没说的话；原样照译则会让读者以为是译者漏了内容。两者都不可取。正确做法是照译，并在紧随其后加一条简短译注，说明问题出在原文：

    ```
    이와 대조적으로, 이는 … 목표로 한다. *[역주: 원문이 이 자리에서
    "which in contrast, aims to…"로 시작한다. 선행사가 되는 문장이 원문에
    없어, 무엇과 대조되는지는 원 논문에서도 드러나지 않는다.]*
    ```

    译注用 `*[역주: …]*`（斜体方括号）——纯 markdown，四种输出格式都能保留，且与正文明显区分。只在读者会因此停下来怀疑译文时才加；不要为了展示细心而滥用。

    `dry_run.py` 在翻译开始前就会报出这类句子，正是为了让你有机会这样处理，而不是事后被追问。

邻居上下文（只读，不要翻译，不要写入输出，只用于判断代词、性别、别名和跨 chunk 指代；为空则省略）:

{NEIGHBOR_CONTEXT}

markdown文件正文:

---

### 4.4. Check the Work Before You Record It

**A sub-agent's report is not evidence. The file it wrote is.**

An agent that skipped a paragraph, pasted its neighbour's context, answered in
English, or invented the quote it offered as evidence reports exactly what a
correct one reports: it finishes. Every one of those has to be found by
reading the artefact, and none of them is found by asking again.

Run this on every chunk in the batch, before recording anything:

```bash
python {baseDir}/scripts/verify_chunk.py "<temp_dir>" --lang <target_lang> --strict chunk0001 chunk0002 ...
```

It compares the output against the source chunk, the glossary the agent was
handed, and the chunk it was told to quote from, never against the agent's
account of its own work. Add `--json` to consume the report programmatically,
`--quiet` to print only failures.

What it fails on, all of it proven by fault injection rather than by reasoning:

| check | what it caught |
|---|---|
| `placeholders` | a formula dropped, duplicated, or invented (`⟦M0042⟧`) |
| `images` | an image reference gone |
| `untranslated` | the output is the source, byte for byte |
| `target_language` | the chunk came back in the source language |
| `untranslated_block` | one paragraph never translated |
| `commentary` | "Here is the translation:", a closing note, the whole file fenced |
| `fences` | an unclosed code fence |
| `structure` | table rows lost |
| `length` | a translation a fifth the length of its source |
| `neighbor_leak` | the read-only neighbour excerpt pasted into the output |
| `glossary` | a term left in the source language that the glossary translates |
| `meta_evidence` | a quote offered as evidence that is not in the chunk |

Warnings (`heading`, `list item`, extra images, missing meta) do not fail a
chunk; read them and decide.

**When a chunk fails, re-translate it, do not patch it yourself and do not
argue with the agent.** Re-dispatch that one chunk with the findings quoted
verbatim in the prompt, because the finding names the defect and a bare "try
again" does not:

> Your previous translation of `chunk0007.md` was rejected by an automatic
> check. Fix exactly these and rewrite the whole file:
> - [placeholders] 1 placeholder dropped by the translator: ⟦M0031⟧
> - [untranslated_block] 22 consecutive source-language words with no ko:
>   "We evaluate the proposed method on a range of standard benchmarks"

Then run the verifier again on that chunk. Two rejected attempts is the limit:
after the second, stop and report the chunk to the user with the findings
rather than lowering the bar. Record a chunk in `run_state.json` only once it
passes.

The false-positive rate is not a matter of opinion: the checks are calibrated
against three fully reviewed books, 40 chunks, at zero failures, and every
check above is proven to fire by breaking a real chunk (KNOWLEDGE
[K70](KNOWLEDGE.md#k70)). If a check fires on work you have read and believe
is correct, that is a bug in the checker, fix the checker, and say what the
false positive was. Do not skip the gate for a chunk.

Things the verifier deliberately accepts, so do not "fix" them:

- the reference list in the original language (that is the decision),
- Latin model and benchmark names in Korean prose,
- an unresolved `(app:some_label)`: the merge turns it into "Appendix A.1"
  from `flat.tex`.

### 4.5. Merge Sub-Agent Meta Into Glossary (as each chunk lands)

Each sub-agent emitted an `output_chunk<NNNN>.meta.json` alongside its
translated chunk. As each chunk lands and passes step 4.4, record it while the
glossary is still the one that chunk was given, then merge its observations
into the canonical glossary, so the next chunk dispatched sees the enriched
one. Running this per chunk rather than per batch is what lets the work queue
keep dispatching; the two subprocess calls take well under a second.

You may also let a few completions accumulate and merge them together. What
must not change is the order within a chunk: record before merge.

1. Record the chunks that PASSED step 4.4, and only those, before mutating the glossary:

   ```bash
   python {baseDir}/scripts/run_state.py record "<temp_dir>" chunk0001 chunk0002 ...
   ```

   If this fails, fix the missing/empty output or state error before continuing.

2. Run prepare-merge:

   ```bash
   python {baseDir}/scripts/merge_meta.py prepare-merge "<temp_dir>"
   ```

   Capture stdout JSON. It contains four arrays:
   - `auto_apply`: new entities with no glossary collision and unanimous (target, category) across all proposing chunks.
   - `decisions_needed`: items requiring main-agent judgment. Each has `id`, `kind`, an `options` array, and the data needed to pick. Kinds:
     - `alias`: `{variant, candidate_source, evidence}`. Choices: `yes_alias` / `no_separate_entity` / `skip`.
     - `conflict`: `{entity_source, field, current, proposed, evidence}`. Choices: `keep_current` / `accept_proposed` / `record_in_notes`.
     - `new_entity_existing_alias`: sub-agents propose `proposed_source` as a new entity, but it's already someone's alias. `{proposed_source, currently_alias_of, promoted_variants: [{target_proposal, category, evidence, evidence_chunks}, ...]}`. Choices: one `use_variant_N` per distinct (target, category) promotion variant (promote `proposed_source` to standalone with that target+category, removing it from the host's aliases) / `keep_as_alias` / `skip`.
     - `existing_entity_conflict`: sub-agents proposed a (target, category) for `entity_source` that differs from the canonical. Multiple distinct differing proposals all get exposed. `{entity_source, current_target, current_category, proposed_variants: [{target_proposal, category, evidence, evidence_chunks}, ...]}`. Choices: `keep_current` / one `use_variant_N` per competing proposal (overwrites both target AND category, stamps the prior values into notes) / `record_in_notes` (canonical unchanged; every proposed variant gets logged to notes).
     - `alias_or_new_entity`: `variant` has multiple competing options that can't all coexist under v2's surface-form uniqueness rule. Triggered when (a) `variant` was proposed both as a new standalone entity AND as an alias of one or more candidates, OR (b) `variant` was proposed as an alias of two or more different candidates with no standalone competitor. `{variant, alias_candidates: [{candidate_source, evidence, evidence_chunks}, ...], standalone_variants: [{target_proposal, category, evidence, evidence_chunks}, ...]}`. Choices: one `use_alias_N` per candidate (attach as alias of that candidate), one `use_standalone_N` per competing standalone proposal (add as standalone with that target+category), or `skip`.
     - `conflicting_new_entity_proposals`: `{source, variants: [{target_proposal, category, evidence, evidence_chunks}, ...]}`. Choices: `use_variant_0`, `use_variant_1`, ..., `skip`.
   - `consumed_chunk_ids`: every meta file scanned this round (regardless of whether it produced a finding). These hashes get recorded in `applied_meta_hashes` on apply.
   - `malformed_meta_chunk_ids`: meta files that failed validation. Quarantined: not consumed, not crashing the run. Surface them in your batch progress.

3. **If `consumed_chunk_ids` is empty** → nothing was scanned; skip to Step 5.

4. **If `consumed_chunk_ids` is non-empty but both `auto_apply` and `decisions_needed` are empty** → still pipe `{"auto_apply": [], "decisions": [], "consumed_chunk_ids": [...]}` into `apply-merge` so the hashes get recorded. **Skipping this is the bug**: no-op metas would re-scan forever otherwise.

5. **Otherwise, resolve each decision**:
   - Read its evidence quotes inline.
   - Pick one option from its `options` array.
   - Build a `decisions` entry that round-trips the original decision plus your choice. The entry MUST include the original `kind` and (for `conflicting_new_entity_proposals`) the `variants` array, so apply-merge can validate and act:

     ```json
     {"id": "d1", "kind": "alias", "variant": "Taig", "candidate_source": "Tai", "choice": "yes_alias"}
     ```

6. Pipe the decisions JSON into apply-merge:

   ```bash
   echo '{"auto_apply": [...], "decisions": [...], "consumed_chunk_ids": [...]}' \
     | python {baseDir}/scripts/merge_meta.py apply-merge "<temp_dir>"
   ```

   Surface the summary JSON (`auto_applied`, `decisions_resolved`, `consumed_chunks`, `errors`) in your batch progress message.

   **apply-merge is transactional.** If any decision is malformed (wrong choice for kind, missing fields, references a non-existent entity), the entire batch aborts with a non-zero exit and stderr details, no glossary mutation, no hashes recorded. On non-zero exit, fix the offending decision and re-pipe; `prepare-merge` will surface the same proposals because nothing was consumed.

   **Decision order in the input list is not significant.** `apply-merge` internally dispatches entity-creating decisions before alias-attaching ones, so `yes_alias` decisions whose candidate is created by another decision in the same batch (a `use_standalone_N`, `use_variant_N`, or `promote_to_separate_entity`) succeed regardless of the order you pass them in. Alias chains (e.g. `Taighi → Taig` where `Taig → Tai` is also a pending alias decision) resolve via a fixed-point loop within the alias-attacher pass; you don't need to topo-sort or sequence chained aliases manually.

On a fresh run after a previous interrupted batch, `prepare-merge` will pick up any meta files left behind. Don't manually delete them.

### 4.6. Translate Table Captions and Headers

**The chunk translation does not cover tables.** A LaTeX table float is
protected behind a `⟦T####⟧` placeholder so the math guard can guarantee its
backslashes survive, and its `\caption{}` and column headers are inside that
placeholder, so no translator ever sees them. The book comes out translated
with its tables still in the source language, and every existing check passes,
because they count tables, images and values and those are all correct.

Find out whether this paper is affected:

```bash
python {baseDir}/tests/format_probe.py "<temp_dir>" --lang <target_lang>
```

If it reports untranslated captions, run one sub-agent per file that holds
tables (`chunkNNNN.math.json` for placeheld floats, `output_chunkNNNN.md` for
inline ones) and have each translate:

- the body of `\caption{...}` (and its optional `[...]` argument),
- column header cells that are ordinary words (Method, Model, Bits, Budget,
  Avg., Total Time (s) …),
- rotated or small-caps row-group labels,
- prose inside `\begin{tablenotes}`.

and leave untouched: every number, every model/benchmark/method name, all LaTeX
structure (`&` and `\\` counts, `\multicolumn`/`\multirow` arguments, column
specs, rules), and `\cite{}`/`\label{}` keys.

Tell each agent to edit with a Python script, `json` for the sidecars, never
a shell heredoc.

**Take the baseline before they start, and check it yourself afterwards.** An
agent that dropped an `&` or retyped a number reports exactly what a careful
one reports, and nothing else in the pipeline would notice: the table is
present, the caption is Korean, every count agrees, and the reader gets a
number that was never in the paper.

```bash
python {baseDir}/scripts/verify_tables.py snapshot "<temp_dir>"     # BEFORE
#   ... the table sub-agents run ...
python {baseDir}/scripts/verify_tables.py check "<temp_dir>" --strict
```

The check requires the snapshot and refuses to answer without one, because a
baseline reconstructed from the edited files is not a baseline. It allows any
change to WORDS (captions, header cells, `\textbf{}` wrappers, notes) and
fails on a changed number, a changed row count, a changed `&` count in any
row, or a changed `\multicolumn`/`\multirow` span. Re-translate any table it
rejects from the snapshot copy under `<temp_dir>/.table_snapshot/`.

**An `algorithm` float needs the same pass, and used to need more.** Its
`\caption{}` is invisible to the translators for the same reason, and so is
the prose inside `\Comment{}` and on the `\Require`/`\Ensure` lines, that is
the pseudocode a reader actually reads. `verify_tables.py` cannot guard it:
the float holds no `tabular`, so the snapshot records ZERO tables for a file
that has an algorithm in it. Check the sidecar directly. The float itself now
reaches the page (`algorithm_float.py` rewrites it as a numbered markdown
list before pandoc sees it) but until this run every book silently lost it
(KNOWLEDGE.md [K78](KNOWLEDGE.md#k78)).

Then re-run the format probe; it must report zero untranslated captions.

A sidecar edit does not invalidate `output.md`: the merge is keyed on the
`output_chunk*.md` mtimes, and `--force-html` only regenerates the HTML from
the stale merge. **Delete `output.md`** before rebuilding, or the sidecar will
read Korean while the PDF still shows English (KNOWLEDGE.md [K42](KNOWLEDGE.md#k42)).

### 4.7. Tables and Equations Are Finished by the Build: Do Not Hand-Patch

Everything below happens inside `merge_and_build.py` on every run. It is
described here so you recognise the output as intended and do not "fix" a book
by editing HTML, and so you know what to look at if a paper comes out wrong.

**Table captions get a number.** `float_units()` numbers floats by counting
`\caption` calls in `flat.tex`: calls, not environments, because one
`table*` can hold two. `number_table_captions()` then prefixes each caption
with `표 N (Table N)` in the target language's form. A tabular takes the
nearest caption **above** it, not the float's first one.

**Table rules come from the source, not from a guess.** `table_structures()`
reads `flat.tex` and, per table in document order, records how many rows are
header (`\toprule` … `\midrule`) and where the body rules fall:
`\midrule`/`\cmidrule` hard, `\addlinespace` and `\\[Npt]` soft.
`apply_table_structure()` promotes those header rows to `<thead>` (so they
repeat on every page) and marks body rows `rule-above` / `rule-above-soft`.
This runs whether the table reached the page as raw LaTeX or as a
pandoc-converted markdown table. Only when the source has no rules at all does
a heuristic add one above a trailing Average/평균 block.

**Word repeats the header too.** pandoc sets `<w:tblHeader/>` only when it
found exactly one header row, so a two-deck header never repeated after a page
break in Word. `mark_docx_header_rows()` marks the remaining rows from the
same plan once pandoc has written the file.

**References are coloured, and linked where the target is certain.**
`link_cross_references()` gives every figure, table and numbered equation an
id, then turns 그림 N / 표 N / 식 (N) in the prose into anchors pointing at
them. The colour is `#001473`, measured off the source preprint, which draws
its own 332 links in exactly that. A caption is a LABEL, not a reference, so
captions stay plain -- linking "그림 1 (Fig. 1)" to the figure it sits under
is a link to itself.

Citations and 부록 A.8 get the colour but no link, deliberately. The
bibliography arrives as raw `\bibitem` text with no per-entry anchor and the
appendix subsections have no headings to anchor to, so a link would have to
guess -- and a citation pointing at the wrong paper is worse than one that
points nowhere. The pass runs on the body HTML AFTER `tag_equations_in_html`,
because until then "식 (7)" has nothing to point at; the DOCX path never sees
it and keeps plain text.

**Grid tables are converted at merge time, not turned off.** See
KNOWLEDGE.md [K66](KNOWLEDGE.md#k66), disabling `grid_tables` makes pandoc
write the literal text `[TABLE]` and lose the table entirely.

**Display equations are centred** by giving the inner `<semantics>` box
`width: fit-content` and `margin: 0 auto`. Not by `text-align`, which Chromium
ignores on a block `<math>`, and no longer by `display: flex`: a formula wider
than the flex container loses its FIRST CHILD outright, which cost equation (3)
of VLA-Adapter its left-hand side with nothing on the page to show it
([K151](KNOWLEDGE.md#k151)). The `<math>` element stays full width either way,
so a right-margin `(N)` number still lands in the margin.

Check the result in the built HTML, not in the markdown:

```bash
python {baseDir}/tests/format_probe.py "<temp_dir>" --lang <target_lang> --strict
```

Every table must have a `<thead>`; the probe says how many do. A table with
none means `header_row_count()` found no rule to stop at, read that table in
`flat.tex` before touching anything else. A cell containing `+---` or `===`
means a grid table survived conversion: that is a bug in
`grid_tables_to_pipe()`, not something to patch in the output.

### 5. Verify Completeness and Retry

After all batches complete, use Glob to check that every source chunk has a corresponding output file.

If any are missing, retry them, each missing chunk as its own sub-agent. Maximum 2 attempts per chunk (initial + 1 retry).

Then run the per-chunk gate over the whole book, not only over the last batch.
A chunk can pass on its own and still be wrong about the book: a term the
glossary gained in batch 3 was not in the table batch 1 was handed.

```bash
python {baseDir}/scripts/verify_chunk.py "<temp_dir>" --lang <target_lang> --strict --quiet
```

Every chunk must pass before you merge. A book built on a chunk that failed
this gate cannot be repaired cheaply afterwards: re-converting moves every
chunk boundary and renumbers every `⟦M####⟧`, which discards the whole
translation and every review of it.

Also read `manifest.json` and verify:
- Every chunk id has a corresponding output file
- No output file is empty (0 bytes) or blank (whitespace-only)

Then run the meta-merge observability snapshot:

```bash
python {baseDir}/scripts/merge_meta.py status "<temp_dir>"
```

Then look at the run as a whole, which no per-chunk gate can:

```bash
python {baseDir}/scripts/referee.py tally  "<temp_dir>" --lang <target_lang>
python {baseDir}/scripts/referee.py record "<temp_dir>" --lang <target_lang>
```

`record` is what makes the referee grow, without it, every book is the first
book. If `tally` raises BRIEF or CHRONIC, hand it to the `referee` agent
before re-dispatching anything: re-translating a chunk cannot fix a prompt,
and doing it three times is how a briefing fault gets mistaken for bad luck.

Also run the selective re-translation state snapshot:

```bash
python {baseDir}/scripts/run_state.py status "<temp_dir>"
```

Surface a one-line summary in the verification report:

> Translated chunks: 50 • Meta files: 48 found / 47 consumed • Malformed: 1 (chunk0099, see stderr) • Chunks missing meta: chunk0017, chunk0042

Severity rules (none of these fail the run, meta is non-blocking):

- `unmerged_meta_files > 0` after Step 4.5 ran → bug, flag prominently. Resume should have caught this.
- `malformed_meta_files > 0` → sub-agent emitted invalid meta; print chunk_ids and a "fix the file by hand and re-run if you want this chunk's feedback merged" note.
- `meta_files_found < translated_chunks` → sub-agent-compliance issue (some chunks didn't emit meta at all). Print missing chunk_ids.

Report any chunks that failed translation after retry.

### 6. Translate Book Title

Read `config.txt` from the temp directory to get the `original_title` field.

Translate the title to the target language. For Chinese, wrap in 书名号: `《translated_title》`.

### 7. Post-process — Merge and Build

Run the build script with the translated title:

```bash
python {baseDir}/scripts/merge_and_build.py --temp-dir "<temp_dir>" --title "<translated_title>" --cleanup
```

If the user provided `epub_cover`, add `--cover "<epub_cover>"`. If the user
provided `export_name`, add `--export-name "<export_name>"`.

The `--cleanup` flag removes intermediate files (chunks, input.html, etc.) after a fully successful build. If the user asked to keep intermediates, omit `--cleanup`. The `chunk*.math.json` sidecars are deliberately kept so a later re-merge can still restore formulas.

The script reads `output_lang` from `config.txt` automatically. Optional overrides: `--lang`, `--author`.

Other flags:
- `--build-only`: skip the merge and build straight from an existing `output.md`.
  Needed for a temp dir already cleaned with `--cleanup`, where the chunks are gone.
- `--force-html`: regenerate HTML even when `book_doc.html` looks newer than `output.md`.
- `--docx-engine {pandoc,calibre}`: default `pandoc`, which produces native
  editable Word equations (OMML). Calibre's DOCX writer has no math support and
  drops every formula, so only use `calibre` if the pandoc output has a problem.
- `--pdf-engine {chromium,calibre}`: default `chromium`, which renders through
  the local Chrome/Edge print engine and honours the `@page` print CSS, so page
  size and margins are what the profile says. Calibre honours neither and was
  silently producing US Letter pages with 25.4mm margins on every side; keep
  `calibre` only as a fallback when no browser is available.
- `--print-profile {a4-book,a4-large,a4-dense,letter-book}`: default `a4-book`
  (A4, 18/18/22/18mm, 11.5pt body, 1.75 leading). Changing it **requires
  `--force-html`**, because HTML regeneration is keyed on `output.md`'s mtime
  and the geometry is baked into `book_doc.html` at template time.
- `--math {mathml,none}`: default `mathml`: offline math with no JavaScript and
  no external requests, which is also what survives into EPUB and PDF.
- `--allow-degraded-html`: last resort. Without pandoc and without the
  `markdown` package the build now **fails loudly** instead of silently falling
  back to a regex converter that cannot render tables at all. Prefer installing
  pandoc or running `python -m pip install markdown`.

The build refuses to continue when a check fails, rather than shipping a quietly
broken book: markdown **or raw-LaTeX** tables that did not become `<table>`, math
present in `output.md` but absent from the HTML, image references that do not
resolve, a math placeholder that a translator dropped, a translated chunk whose
LaTeX skeleton no longer matches its source, or a display equation still printing
underneath its own number at the smallest size tried.

Five things are repaired automatically on the way through, and reported:

- **Raw LaTeX tables.** The arXiv backend keeps tables as
  `\resizebox{..}{\begin{tabular}...}`, often inside a `\begin{table*}` float.
  pandoc's markdown reader treats those as raw LaTeX blocks and drops them on the
  HTML path *without warning*, so each one is converted separately with
  `pandoc -f latex -t html` and spliced back in, caption and all.
- **Citations.** A paper that ships a precompiled `.bbl` rather than a `.bib` has
  nothing for citeproc to read, so `[@key]` markers printed verbatim. They are
  numbered against the inlined `\bibitem` list. A key with no entry is left alone
  rather than given a wrong number.
- **Cross-references.** `(fig:x)` / `(tab:x)` are resolved to `Figure N` / `Table N`
  (localised per language) using the `\label` order in `flat.tex`. A `\ref` inside
  a protected table float is resolved too, number only, from the label index
  rather than from the key (K154).
- **Shaded rows.** `\rowcolor` is how a results table says which rows are the
  authors' own. It used to be stripped as presentation-only along with
  `\cellcolor`, and the paper's own numbers printed like every baseline's.
  The band is put back from the protected float, and NOT put back at all when
  the source and rendered row counts disagree: shading the wrong line credits
  somebody else's result to the authors (K158).
- **Equation width.** A formula as wide as the text column shares ink with its
  own flush-right number, and no stylesheet prevents it: MathML compresses its
  spacing into the box instead of shrinking to fit. `equation_fit` renders,
  measures the PDF it just rendered, steps the offending equations down one
  size and renders again. A book with no collision costs the single render the
  build was already doing. Do not try to decide the size from an equation laid
  out on its own; it does not reproduce the book's layout (K152).

`output.md` itself is never rewritten by any of these; it stays the faithful
merged translation. The resolved copy is written to `prepared.md`.

This produces in the temp directory:
- `output.md`: merged translated markdown (placeholders restored to real LaTeX)
- `book.html`: web version with floating TOC
- `book_doc.html`: ebook version
- `book.docx`: via pandoc, with editable equations
- `book.epub`: via Calibre (requires Calibre)
- `book.pdf`: via headless Chromium, laid out by the `@page` rule and the
  print stylesheet in `template_ebook.html`. Page numbers are stamped into the
  bottom margin by PyMuPDF afterwards, because Chromium implements no `@page`
  margin boxes. Falls back with `--pdf-engine calibre`.

### 7.5. Source-Fidelity Audit: dispatch a reader who holds both books

**Run this on every paper, every time. It is not optional and it is not a
formality.** Every table and figure defect this pipeline has ever shipped was
found by a person reading the finished page beside the original, never by a
check. The probes count what they were taught to count; an omission is by
definition the thing nobody counted.

Run `tests/table_probe.py` first: it is cheap and it catches what is
countable, a lost `\multicolumn` span, a column that vanished, a value in
the source `tabular` that is not on the page, a body row carrying numbers
with no label. Fix what it finds before spending an agent.

Then dispatch **one sub-agent per paper** to do what no probe can. Give each:

- the built PDF and the ORIGINAL PDF (`ref_paper/<name>.pdf`),
- `output.md`, `flat.tex`, and the `chunk*.math.json` sidecars,
- a scratch directory of its own, and filenames prefixed with the paper.

Tell it to **render both pages and read them as images** (PyMuPDF
`page.get_pixmap(matrix=fitz.Matrix(2,2)).save(path)`) not to compare text
dumps. Position is the whole point: a header that sits over the wrong column
extracts identically to one that sits over the right column.

Ask for, per table and per algorithm float: the original page, the translated
page, and either "matches" or a numbered list of concrete differences, each
quoting the original cell text and the translated cell text. Then: column
counts, row counts, group-header spans, row labels, footnote marks and
`tablenotes`, superscripts still attached to their numbers, colour or bold
that a caption refers to, and any cell squeezed until it cannot be read.

Require the agent to say what it could NOT verify. An audit that reports
only findings is indistinguishable from one that stopped early.

Then check its claims yourself against the files. That is the point of
asking for quotes and page numbers rather than a verdict.

#### 7.5b. Then read the whole book, page by page

The audit above is scoped to tables and floats, and whatever it is not
looking at goes unseen. A table-only pass signed off three books that were
between them missing an entire 61-entry reference list, printing `{=latex}`
in the body, carrying the `참고문헌` heading six pages inside its own list,
and naming no authors on any title page. Every one of those was found by
someone looking at pages.

Dispatch **one sub-agent per paper** to render EVERY page at
`fitz.Matrix(2, 2)` and read the images, not text dumps; a heading sitting
on top of a figure extracts perfectly. Ask for a line per page ("p7: clean"
or "p7: <what is wrong>"), then findings ranked by reader impact, then what
it could NOT verify.

Run the probes alongside, plus a scan of the built PDF for markup that
reached the reader: `\command`, `$`, `:::`, `{=latex}`, `{-2em}`, `(tab:x)`,
`[@key]`, `??`, HTML tags, `<!--`, and the `↩︎` of a footnote backlink. Those
cost nothing and catch what an eye loses across ninety pages.

Keep adding to that list. Every entry on it is there because a build printed
it and the scan of the day did not name it: `<!-- -->` printed twenty-one
times in AlphaQ while a scan looking for seven other shapes reported the book
clean. A reader found it in a figure caption.

#### 7.5c. Check the original before you change anything

A finding is a lead, not a verdict. Of the last four on one review's list,
three needed no change: the headings carry no numbers because the PAPERS
carry none, a unit prints italic because the source writes `96$tps$`, and a
rule reported missing was present in all 39 tables. Acting on the report
alone would have produced three deviations dressed as repairs.

So for each finding, open the original and ask what it actually does. Change
only where the book and the paper disagree. This is also how you catch your
own regressions: it is what turned up `부록 A.10` printing as `A.10절` after
a fix made an hour earlier. See [H23](KNOWHOW.md#h23).

### 8. Report Results

Tell the user:
- Where the output files are located
- How many chunks were translated
- The translated title
- List generated output files with sizes
- Any format generation failures

Report what the build actually said. If a check reported a shortfall (tables
that did not convert, citations with no target, TOC entries whose page could not
be resolved) say so with the numbers rather than rounding it up to "done".

### 9. Record What You Learned

Two logs, and the first decision is which one a finding belongs in:

| the finding is… | it goes in | its number |
|---|---|---|
| a tool behaved in a way that surprised you | `KNOWLEDGE.md` | `K<n>` |
| your way of working cost you rework | `KNOWHOW.md` | `H<n>` |

*Why did this break?* is knowledge. *How should I proceed?* is knowhow. One
incident can produce an entry in each (the pandoc behaviour in one, the
practice that would have caught it sooner in the other) but never the same
entry twice.

**Only if it is not already there.** An empty diff is a fine outcome; most
runs should produce one.

Add a KNOWLEDGE entry when you hit any of these:

- An external tool (pandoc, Chromium, Calibre, PyMuPDF) behaved in a way that
  surprised you, and you have the measurement that proved it.
- A fidelity check passed while the output was wrong, or failed while it was
  right.
- You made a judgement call with numbers behind it (a size, a margin, a
  threshold) that the next run would otherwise re-derive.
- Something turned out to depend on this machine, an installed font, a tool
  version, a path.

Follow the entry format and the rules in KNOWLEDGE.md's *Maintenance protocol*.
Two of them matter most: **add a row to the symptom index**, because an entry
nobody can find is not knowledge; and if you fixed the problem in code, **write
the test and compress the entry to one line pointing at it**: the test is the
record, the log keeps the *why*.

Add a KNOWHOW entry when the run taught you something about the METHOD:

- You repeated a step you could have got right the first time, and can say
  what would have prevented it.
- You found which document, check, or ordering has to come before which.
- A practice paid off that is not obvious from the code, and you have the
  incident to prove it, not just the opinion.

Every KNOWHOW entry carries a `*Cost when skipped:*` line naming the real
incident. A practice with no incident behind it is a preference, and
preferences belong in AGENTS.md's conventions. Generic programming advice
belongs in neither.

If a fix is worth enforcing rather than remembering, put it in code and tests
instead. The verification gate is:

```bash
python -m compileall scripts tests
python -m unittest discover -s tests -p 'test_*.py'
python tests/layout_probe.py --strict
python tests/layout_probe.py --stress --strict
python tests/format_probe.py <temp_dir> --lang <lang> --strict
python tests/source_probe.py <temp_dir> --strict
python tests/table_probe.py <temp_dir> --lang <lang> --strict
python tests/inventory_probe.py <temp_dir> --lang <lang> --strict
python tests/leak_probe.py <temp_dir> --strict
python tests/consistency_probe.py <temp_dir> --lang <lang> --strict
```

Each looks at something the others cannot see, so none of them is redundant:

| probe | question it answers |
|---|---|
| `layout_probe` | Is the page the size and type the profile asked for? |
| `format_probe` | Do DOCX, EPUB and PDF all carry the same tables and images? |
| `source_probe` | Do our numbers say what the **original paper** prints? |
| `table_probe` | Does each table still say what the **source `tabular`** says? |
| `inventory_probe` | Is any KIND of thing the paper contains missing from the page entirely? |
| `leak_probe` | Is anything on the page markup rather than words? |
| `consistency_probe` | Would a reader trip over the words? |

`leak_probe` is the other half of that inversion. Scanning for `{=latex}`,
`{-2em}`, `:::` and the rest is a list of things that have already gone
wrong, so it is always one build behind: `<!-- -->` printed twenty-one times
in AlphaQ while a scan looking for seven other shapes called the book clean,
and a reader found it. This one asks what a sentence is made of instead --
Hangul, letters, digits, ordinary punctuation -- and reports every token
carrying `{ } < > \ $ & | ^ ~`. A lone one of those is rendered content (the
bars of a norm, the braces of a set, the `&` between two authors); attached
to anything else it is markup. The one other exception the probe grants is
declared by the paper itself: a token the source spells with a LaTeX escape,
`R\&D`, `pick\&place`, `50\%`: is a word, because a column separator is
written bare and only `flat.tex` still shows the difference. Name a new
exception here when you meet a real one; do not go back to naming offences.

`inventory_probe` is the one that does not start from our own output. Every
other check compares two artifacts this pipeline made, so it can only find a
disagreement between stages, and it is blind, by construction, to what is
absent from every stage at once. CafeQ shipped 61 references in `output.md`
and none in the book while every count agreed with every other, because
nothing counted references. Reading `flat.tex` and asking "the source has
figures / a bibliography / an author, did any of it reach the page?" needs
nobody to have thought of the check first. It reports only TOTAL absence:
a count in LaTeX and a count in HTML do not line up, and treating that
difference as a shortfall is how a check earns a reputation for crying wolf.

`table_probe` exists because nothing compared a table's CONTENT to the source.
`source_probe` reads the original and counts NUMBERING (section, figure,
equation, reference numbers) not one cell. `verify_tables` compares each
table against a snapshot of OUR OWN files, so when a conversion drops a value
before the snapshot is taken, the snapshot records the damage and the check
passes forever. CafeQ shipped with twelve values missing from table 1 and six
from table 5 while the prose went on citing them, and both checks were green.
Every table defect in this project was found by a person reading the page.

`source_probe` is the one that compares against ground truth rather than
against ourselves. Section numbers, figure numbers, equation numbers and
cross-reference values are all reconstructed from `flat.tex`, and a
reconstruction can be perfectly self-consistent and still wrong: an early
version numbered SINQ's headings `I. / A. / 1)` because that is what IEEEtran
does, while the paper prints `1. / 2.1.`. Forty-one headings were labelled
confidently and wrongly, and every other check was green.

`format_probe` is not optional. The layout probe measures the PDF and only the
PDF, and twice that has let a DOCX regression through: raw HTML survives the
HTML path alone, so a change that looks right in print can empty the Word file
of every table or image without a single check complaining.

### 10. Repairing a book that is already translated

Sometimes a structural defect is only found after the prose is done and
reviewed. Re-converting is the wrong instinct: it moves every chunk boundary
and renumbers every `⟦M####⟧`, so the planner asks to re-translate almost
everything and the review is lost with it. Repair the artifacts in place.

1. **Back up** `chunk*.md`, `output_chunk*.md` and `manifest.json` first.
   Nothing here is under version control.
2. **If the defect is in a raw LaTeX table**, it never went near a translator;
those are restored verbatim from `chunk*.math.json` at merge, so it can
   be fixed without touching prose at all:

   ```bash
   python {baseDir}/scripts/repair.py sidecar "<temp_dir>"            # dry run
   python {baseDir}/scripts/repair.py sidecar "<temp_dir>" --apply
   ```

   This undoes the column spec pandoc emitted twice and lifts labels out of
   `\rotatebox`/`\multirow`. It is how SINQ went from ten ragged tables to
   none with nothing re-translated.
3. **Otherwise patch the source chunk and the translated chunk together.** The
   build comes from the output chunks, but the validators compare each output
   chunk against its source, images, math placeholders and LaTeX skeleton
   must still match, so an edit to one is an edit to both.
4. **Re-hash and re-record** every source chunk you touched:

   ```bash
   python {baseDir}/scripts/repair.py rehash "<temp_dir>"
   python {baseDir}/scripts/run_state.py record "<temp_dir>" chunk0005 ...
   ```

   The source hash is how the pipeline decides a chunk needs translating
   again. Skip this and the next run silently re-translates a chunk that was
   already right, paying for it, and discarding the review.
5. **Confirm nothing is queued** before rebuilding:
   `python {baseDir}/scripts/run_state.py plan "<temp_dir>"` must report an
   empty `translation_chunk_ids`.
6. **Touch the output chunks, then rebuild** with `--force-html`. The merge is
   keyed on their mtime, so editing only a sidecar or a source chunk leaves
   `output.md` stale and the rebuild silently uses the old text.
7. Run the whole gate above.

The export aliases (`--export-name`) are written **inside** the temp dir. If
you also keep copies somewhere the user reads, they are yours to refresh, a
rebuild will not touch them, and a stale copy next to a fresh `book.pdf` looks
exactly like a successful build.

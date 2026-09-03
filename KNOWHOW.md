# KNOWHOW.md: working practice

How to do this work thoroughly, efficiently, and without paying for the same
mistake twice.

**This file is not KNOWLEDGE.md.** The split is deliberate:

| | KNOWLEDGE.md | KNOWHOW.md |
|---|---|---|
| holds | facts about how the tools actually behave | how to go about the work |
| example | "pandoc drops a raw LaTeX block whole on the HTML path" | "anything holding a backslash goes through a file, never a heredoc" |
| you read it | when the output looks wrong | before you start, and when you are about to repeat a step |
| an entry answers | *why did this break?* | *how should I proceed?* |

A finding about a tool goes there. A finding about the method goes here.

---

## Which document, for which task

| about to… | read first |
|---|---|
| translate a paper end to end | `SKILL.md`, Steps 1–10 in order |
| work out why output looks wrong | `KNOWLEDGE.md` symptom index |
| change ingest or build code | `AGENTS.md` "How this pipeline breaks", then its "Do not" list |
| add or change a check | [H2](#h2), [H3](#h3) |
| edit a book that is already translated | [H8](#h8) |
| dispatch sub-agents | [H9](#h9), and `SKILL.md` Step 4.4 |
| set the skill up on another machine | `INSTALL.md`, then `scripts/doctor.py` |
| call the work finished | [H10](#h10), [H15](#h15) |

## Task index

| when you are about to… | entry |
|---|---|
| write a file containing backslashes, regexes, or LaTeX | [H1](#h1) |
| add a check and believe its output | [H2](#h2) |
| make a check fail a build | [H3](#h3) |
| apply the same edit in many places | [H4](#h4) |
| copy a look or a value from a reference | [H5](#h5) |
| insert a new pass into the pipeline | [H6](#h6) |
| add a function to an existing module | [H7](#h7) |
| fix something in a finished book | [H8](#h8) |
| accept work done by a sub-agent | [H9](#h9) |
| say that a task is done | [H10](#h10), [H15](#h15) |
| hand the skill to someone else | [H11](#h11) |
| choose between defensible alternatives | [H12](#h12) |
| trust that the docs describe the code | [H13](#h13) |
| apply a change to a whole class of things | [H14](#h14) |
| exempt part of an artifact from a check | [H16](#h16) |
| believe a feature works because the tests are green | [H17](#h17) |
| tell a sub-agent to reproduce an exact format | [H18](#h18) |
| run many sub-agents that write scratch files | [H19](#h19) |
| write a check that polices a prompt | [H20](#h20) |
| change a rule the sub-agents follow | [H21](#h21) |
| measure a suspected content loss | [H22](#h22) |
| act on a review's findings | [H23](#h23) |
| widen a rule to a case it was not written for | [H24](#h24) |
| a check reports a problem but seems to name nothing | [H25](#h25) |
| read a probe's verdict on a build you did not just make | [H26](#h26) |
| conclude something is absent, or that it cannot be done | [H27](#h27) |
| harden a check against the papers you happen to have | [H28](#h28) |
| read a count of findings as a measure of what was lost | [H29](#h29) |
| trust a probe you wrote a minute ago | [H30](#h30) |
| repair a resolver before the counter it reads from | [H31](#h31) |
| trust a check that has never failed | [H32](#h32) |
| wait for a check to fire when the agents already objected | [H33](#h33) |
| read the commonest leaked token as the cause | [H34](#h34) |
| choose the next paper by its field or its fame | [H35](#h35) |
| probe a stage with bare pandoc instead of the pipeline's flags | [H36](#h36) |
| treat a check firing as proof the check is working | [H37](#h37) |
| accept a package default when two definitions compete | [H38](#h38) |

---

## Entries

### H1
**Anything holding a backslash goes through a file, never a shell heredoc,
and never a `re.sub` replacement string.**
A heredoc turns `\t` into a tab, `\b` into a backspace and `\a` into a bell
before Python ever sees it, so a regex or a LaTeX example arrives silently
corrupted and the file still parses. `re.sub`'s REPLACEMENT argument processes
the same escapes: fixing a mangled `\b` with `re.sub(..., GOOD, ...)` mangles
it again. Write the script with the Write tool, and substitute with a lambda
(`re.sub(pat, lambda _m: GOOD, s)`). Then prove it: count control characters
in the file you just wrote, and print the line back.
*Cost when skipped: four recurrences in one session, `_LABEL_RE` silently
became `\(?<BS>[a-z]...` and matched nothing, and SKILL.md documented
`` `<TAB>oprule` `` for a week. See KNOWLEDGE K3/K24 for the mechanism.*

### H2
**Calibrate a new check in both directions before you believe a word of it.**
Run it on work you have already reviewed and require silence; then break that
same work deliberately, name in advance which check must fire, and require it.
One direction alone proves nothing: a check that has only ever passed and a
check that cannot fail look identical from the outside.
*Cost when skipped: `check_neighbor_leak` read `previous`/`next` where the
provider writes `prev_excerpt`/`next_excerpt`. It was incapable of finding
anything, passed every book it was ever run on, and only a test that demanded
a catch exposed it. The false-positive half matters just as much: the same
term checks fired 8 times on three reviewed books, every one the bibliography,
which is kept in the original language by decision.*

### H3
**A check that cannot prove its claim reports; it does not fail a build.**
State the limit in the message, and pin it with a test so nobody promotes it
later. A hard failure people cannot act on teaches them to pass `--no-strict`,
and then the checks that CAN prove their claims stop being read too.
*Cost when skipped: `check_homographs` compares the source for two senses
against the output for one word, which finds a word worth reading but cannot
tell a real collision from a paper that merely contains both English words.
Left as a failure it would have failed every statistics paper forever.*

### H4
**Locate before you edit, and make a batch of edits all-or-nothing.**
Search for each target string first and confirm which file and how many
occurrences; then assert that count at edit time; then collect every edit in
memory and write only after all of them matched. A partially applied batch is
far worse than a failed one, because the failure is now spread across files.
*Cost when skipped: nothing; this is why. Two batches this session named the
wrong chunk (a term edit and a drift fix) and both stopped dead with zero
files touched, which a `sed` loop would have half-applied.*

### H5
**Measure what you are benchmarking against; do not eyeball it.**
"Match the original" is only actionable once you have the number. Open the
reference and extract the actual value, the colour, the count, the geometry.
*Cost when skipped: the reference colour for cross-references is `#001473`
and the original preprint carries 332 link annotations. Both came from opening
`ref_paper/AlphaQ.pdf` with PyMuPDF; guessing "blue" would have produced a
different document and no target to verify against.*

### H6
**Find where a new pass sits in the pipeline before you write it.**
List the stages it depends on and confirm each one has already run. A pass in
the wrong position does not crash; it processes an earlier version of the
data and reports a confident, wrong number.
*Cost when skipped: the cross-reference pass ran at HTML step 4 and equations
are numbered at step 6, so it anchored 0 of 27 equations and every "식 (7)"
stayed plain, while the log said it had linked 22 references.*

### H7
**Write in the module's conventions, not your own.**
Before adding a function, read a neighbouring one: how it opens files, names
its regexes, returns its stats. Convention-matching is not aesthetics; it is
how you inherit the module's already-solved problems.
*Cost when skipped: `merge_and_build.py` has no `io` import and reads with a
plain `open()`. A new function using `io.open()` killed the build with a
NameError the moment it was reached.*

### H8
**A book that is already translated is repaired in place. Never re-convert.**
Re-conversion moves every chunk boundary and renumbers every `⟦M####⟧`, which
throws away the whole translation and every review of it. The procedure is:
edit `output_chunk*.md` → `verify_chunk.py --strict` → `run_state.py record`
→ confirm `plan` reports translate=0 → delete `book.{docx,epub,pdf}` →
rebuild with `--force-html` → re-export. Editing a sidecar does NOT invalidate
`output.md` (KNOWLEDGE K42), delete it, or touch the chunk files.
*Cost when skipped: the whole translation, and every correction made to it.*

### H9
**A sub-agent reports success by finishing, and so does a broken one.**
Never accept the report; read the file it wrote. `SKILL.md` Step 4.4 is the
gate and it is not optional. When a chunk fails, re-dispatch it with the
findings quoted verbatim, a bare "try again" names nothing. Two rejected
attempts is the limit; then stop and report, rather than lowering the bar.
*Cost when skipped: nothing asked whether a translated chunk was even in the
target language. An agent that skipped a paragraph, pasted its neighbour's
read-only context, or invented the quote it offered as evidence produced
exactly the same report as a correct one.*

### H10
**Finish with the whole gate, in this order, every time.**
`rm -rf __pycache__` → `compileall -W error::SyntaxWarning` → `unittest
discover` → `layout_probe --strict` and `--stress --strict` → per book:
`source_probe`, `format_probe`, `consistency_probe`, `verify_chunk`. Run it
even when the change looks cosmetic; a CSS edit is how the EPUB lost its table
rules. Report the numbers, not the word "passed".
*Cost when skipped: a stale `book.html` from a previous run once made a broken
build look like a green one, the crash had left the old file in place.*

### H11
**Ship a package by unpacking it somewhere else and running it there.**
An archive that builds is not an archive that works. Extract to a fresh path
and, in that copy, compile, run the tests, run `doctor.py`, and build a real
PDF and measure it. Absolute paths and missing files show up there and nowhere
earlier. Say plainly what does NOT travel: the external tools, the fonts that
decide the page count, and the fact that the prose itself is model output and
will not be word-for-word reproducible.
*Cost when skipped: a confident "yes it will work on your machine" that is
false for anyone without Noto Serif KR.*

### H12
**When the choice is defensible either way, ask, but bring a recommendation
and the evidence for it.**
Do not present a neutral menu; say which you would pick and why, put it first,
and show the concrete before/after. Reserve the question for choices that are
genuinely the user's (taste, audience, priorities). Everything decidable from
the code or the source paper, decide yourself.
*Cost when skipped: either churn (implementing the wrong reading of "make the
terms better") or a menu that pushes the work back onto the user.*

### H13
**Sweep the docs against the code mechanically, not from memory.**
Grep every script and every check against the documents that claim to list
them. Documentation drift is invisible from the inside: you remember writing
it, so you do not look.
*Cost when skipped: five scripts were missing from README's structure table (
including `doctor.py`, which the Prerequisites section tells the reader to run
first) and the probes appeared only in the contributor document, so anyone
who received the package could not learn that they exist.*

### H14
**Verify each instance before applying a change to a whole class.**
When asked to fix "this kind of thing", collect every instance with its
context and judge them one at a time. Some will already be right, and saying
so with evidence is part of the job.
*Cost when skipped: asked to reconsider Korean renderings of technical terms,
the mechanical answer was to English them all. But 꼬리/두꺼운 꼬리 is the
settled Korean for tail/heavy-tailed, it appears 33 times in one paper, and
changing it would have made the book read worse. Three terms needed English,
four needed better Korean, and six were already correct.*

### H15
**Read the artifact as its reader before you call it done.**
Open the PDF and read it as a researcher would: where do you stop, re-read, or
reach for the original? The probes cover what is worth automating and nothing
else. Every defect class this project checks for mechanically was found this
way first.
*Cost when skipped: the checks stay pointed at what already broke. Reading
found the broken table, the 적합 collision, and the invisible references,
none of which any count would ever have flagged.*

### H16
**Exempt items, not regions. A boundary you have to guess turns the check off
for everything behind it.**
When part of an artifact is legitimately exempt, decide it per line, per row,
per element -- something you can point at. "Everything after X" is only as
good as X, and X is usually a guess. Where an exact delimiter exists, use it
and say why it is exact.
*Cost when skipped: the reference exemption was a POSITION, found by scanning
for citation density. In a chunk of prose followed by a long reference list
that position is line 0, so AlphaQ's entire "Limitation" section, its
footnotes and two of SINQ's appendix sections were exempt from the language
checks. Feeding that chunk back as 100% English produced zero findings.*

### H17
**A green suite proves the fixtures agree with the code, not that the feature
works.** Both came out of your head. Before believing a new feature, run it
against real input and assert on what it PRODUCED -- a count, a separation, a
difference from before. Then break it deliberately and require the tests to
notice; a test that cannot fail is decoration. Never let a helper swallow its
own failure (`except Exception: return False`), because that converts a broken
feature into a working pipeline that quietly does nothing.
*Cost when skipped: the bibliography splitter assumed a structural block was a
dict when it is a `(text, kind)` tuple. The accessor returned '' for every
block, nothing ever matched, and it compiled cleanly and passed every test
while doing absolutely nothing. A probe against the three real papers found it
in one run; a swallowed import then hid the same shape a second time.*

### H18
**Anything a sub-agent must reproduce exactly is generated and pasted,
never described.**
If a format has to match byte for byte -- a schema, a table, a token set
-- emit it from the code that validates it and paste that output into
the prompt. Description invites paraphrase, and paraphrase of a machine
format is corruption. Build the generator from the validator's own
constants so the two cannot disagree.
*Cost when skipped: the meta schema was the one prompt block left to
memory while the term table and neighbour context were generated. Ten of
thirteen sub-agents wrote `{"name": …}` for `{"source": …}` and
prepare-merge quarantined every one -- observations made, then thrown
away, and indistinguishable from sub-agents that observed nothing.*

### H19
**Parallel sub-agents share one scratchpad; name every file for its task.**
Nine agents ran at once and overwrote each other's `edit.py`, `dump.py` and
`inspect.py`. The last is worse than a collision: `python <dir>/x.py` puts
`<dir>` first on `sys.path`, so a scratch file named after a stdlib module
breaks every tool run from there, PyMuPDF died inside `inspect.signature`.
Prefix each agent's filenames with the chunk it owns, and run your own tools
with `python -P`, but `-P` drops the script's OWN directory too, so use it
only where nothing imports a sibling.
*Cost when skipped: two dead-end debugging rounds mid-run, and a broken
measurement that looked like a corrupt PDF.*

### H20
**Calibrate a guard against the instructions it polices, not your memory.**
The caption agents were told they MAY translate column headers and
tablenotes, which live outside `\caption{}`, then met a guard that failed
any change outside the caption. Four correct edits came back as defects. A
guard stricter than its own brief spends the reviewer's attention on
non-findings and teaches them to skip its output, which is how a real
finding gets missed. Write the check from the prompt text; when the two
disagree, decide which is wrong before changing either.
*Cost when skipped: four false FAILs on correct work, and a guard rewritten
in the middle of a nine-agent run.*

### H21
**A rule and the check that polices it are ONE change, never two.**
Adding "gloss a term's English on first use" to the prompt made
`부합하도록(aligned)` correct, and `check_glossary`, which flags a source
term appearing in the output, failed three chunks that had followed the new
rule exactly. Same shape as [H20](#h20) from the other side: there the guard
was stricter than the brief, here the brief moved and the guard did not.
Before shipping a prompt change, grep the checks for the thing it now makes
legal. And when two places must agree on a judgement, "is this a gloss or a
unit?", have one import the other's predicate instead of writing it twice.
*Cost when skipped: three chunks marked for re-translation while being
correct, and the second of two hours spent proving the translator was right.*
---

### H22
**Run the measurement on a book you believe is fine before believing it.**
Hunting a suspected content loss, I reduced page and source to a stream of
Hangul with everything else stripped and looked for the source's windows in
the page. It reported 42 of 60 sentences missing, and reported losses in a
region I had no reason to doubt, because stripping tags and numbers glues
Hangul from neighbouring table cells into strings that exist nowhere. I told
the user "심각한 것을 발견했습니다" on the strength of it. The loss was real, but
what proved it was running the expander step alone across all three books:
CafeQ lost 0 words and had 0 overlapping float spans, SINQ lost 316 with 7.
The control is what turns a number into a cause.
*Cost when skipped: one alarming claim retracted, and an hour spent on a
measurement that could not have distinguished a defect from an artefact.*
---

### H23
**Check what the original does before calling anything a defect.**
Three of the last four items on a review's list needed no change at all. The
headings carry no numbers because the PAPERS carry none, their own bodies
say "Section 4.1" against unnumbered headings, so numbering ours would
invent structure the source does not have. A unit prints italic because the
source writes `96$tps$`. A rule reported missing from SINQ's table 7 is
present: a census of all 39 tables found no rule missing anywhere. Acting on
the report alone would have produced three changes, each a deviation dressed
as a repair. And the checking is what turned up a real regression of my own.
*Cost when skipped: edits that move a book further from its source while
looking like fixes, and the real defect still standing.*
---

### H24
**Write the narrow case into the condition, or the rule widens by itself.**
`\cref{lem:norm}` printed `정리 3` for a label sitting inside an equation, so
I let the recorded kind win over the prefix. An appendix is a section as far
as the counter is concerned, and every `부록 A.10` became `A.10절`, eleven of
them, in a book I had just verified. The rule was written for ONE shape: a
prefix naming something structurally different from what it is attached to.
Saying so in the condition, override only to `equation` or `algorithm`,
keeps it that shape. Same failure as [H20](#h20) seen from the other side.
*Cost when skipped: a fix for one reference that silently broke eleven.*
---

### H25
**Run the tool itself before concluding it will not tell you.**
A check reported "1 raw LaTeX block lost" and, as far as I could see, named
nothing, so I spent a round on two fingerprint faults that were real and
were not this one. The check had been naming it all along, one line per lost
float; the wrapper I was running it through echoes only selected lines of its
child's output. Calling `merge_and_build.py` directly printed the name at
once, and the name was the answer. A wrapper is not the tool: when a tool
seems to be withholding, the first move is to run it unwrapped.
*Cost when skipped: a round of correct fixes aimed at the wrong defect, with
the real one still standing at the end of it.*
---

### H26
**Rebuild before you believe a probe's verdict on an old temp dir.**
`leak_probe` reported one leak each in AlphaQ, CafeQ and TinyVLA: an
unresolved label, a spacing directive, an empty code span. All three are
shapes the current code removes. The books were not defective; their
`book_doc.html` was months of fixes old, and the probe was reading it
faithfully. One rebuild took all three to zero. A probe reads an ARTIFACT,
never the code that would produce it now, so its verdict is only as fresh as
the file, and a stale one costs a hunt for a defect that is already fixed.
*Cost when skipped: three defects investigated that no longer existed, and
very nearly three "fixes" for them.*
---

### H27
**Four failures these documents cannot prevent, and the advisors for them.**
See SKILL.md, "Four advisors". `old-man` runs BEFORE you conclude something is
absent, and argues from the corpus census rather than recollection.
`question-monster` runs AFTER you write *unsupported*, checks the record for
an approach already reverted, and hands back a candidate to test, never
encouragement. `fast-finder` replaces reading the logs, which past 130 entries
costs more than the answer, and returns entries verbatim: a status line saying
an approach was tried and reverted is the value, and a summary loses it.
`referee` reads the run rather than the chunk, and separates a tool
disagreement from a briefing fault from a role's before cautioning anyone.
None has a veto; an advisor with nothing specific to say means proceed.
*Cost when skipped: `\captionof` counted as no caption at all, and `\sideset`
called impossible while its equivalent sat two lines below it.*
---

### H28
**Widen the corpus before hardening the code.**
Ten well-cited papers of deliberately different shape went through the front
end in one sitting and produced five defects, three of which stopped a paper
dead, and one of which had been quietly translating half of every
bibliography. Three papers had hidden all five for weeks. The corpus was not
small in pages; it was narrow in KIND, and every check written against it
inherited that narrowness. Pick the next papers for the shapes they carry,
not for their subject: `corpus_census.py digest` ends with what the corpus
has NEVER seen, and that list is the shopping list.
*Cost when skipped: checks that agree with each other because they were all
written from the same three examples.*
---

### H29
**A count of findings is not a measure of what was lost.**
The fidelity check reported "1 raw LaTeX block" for Neural ODE, and one line
of output reads as a small problem. It was the entire appendix: six figures,
every formula in it, a proof, a code listing. A wrapper environment with no
reader makes ALL of its contents a single block, so the largest loss in the
book arrives looking like its smallest finding, while a paper with three
harmless leftovers reports three. Read what a finding CONTAINS before ranking
it against the others; the number in the message is a count of containers.
*Cost when skipped: an appendix triaged last because it was one line, behind
two false positives that were three.*

---

### H30
**A probe is evidence only after you have checked the probe.**
Twice in one session a throwaway probe returned a confident wrong answer.
Stripping tags with `<[^>]+>` read the template's own long HTML comments as
page text, so pipeline documentation appeared to be inside the Neural ODE
book; the next version read MathML `<annotation>` elements, which carry a
formula's LaTeX for copy-paste and no reader ever sees, as leaked markup. Both
inflated the count and pointed at the wrong region. Before believing a
measurement, check it against something already trusted: `leak_probe` reports
0 for four books using that same template, and it strips both. Prefer
importing the shipped function to writing a third stripper.
*Cost when skipped: two rounds spent on a region that was never broken.*

---

### H31
**Repair the counter before the thing that reads it.**
The cross-reference resolver printed nothing, which looked like the whole bug.
It was the second half: the label index feeding it was ALSO wrong, by a
constant, because a hardcoded environment list skipped five environments the
paper declared. Had the resolver been fixed alone, 225 references would have
started printing confidently wrong numbers instead of visibly raw keys, and a
wrong number is invisible, where a raw key is not. When a lookup produces
nothing, verify what it would have produced before you make it produce it.
*Cost when skipped: turning a visible failure into a silent one.*

---

### H32
**A check that has never failed has not been checked.**
Three source-level lints passed on their first run, which proved nothing. Made
to fail on purpose -- by copying the tree and reintroducing each historical
defect -- two of the three turned out to be broken. One flagged its own
comment: the note quoting the bad idiom to explain it read as the offence. The
other was blind, because its write-detector forbade commas and parentheses in
the path expression and every real write is
`open(os.path.join(temp_dir, 'name.tex'), 'w')` -- an unseen write is never
checked, so the very case it was written for passed. Reintroduce the defect
and watch the check go red before believing it.
*Cost when skipped: a green suite that enforces nothing.*

---

### H33
**Agents querying a rule is the same evidence as a check firing, and earlier.**
The referee's briefing-fault threshold counts CHECK failures: a defect on a
third of a run is the brief, not the agents. Nothing counts what the agents
SAY. On randmat five translators independently flagged one rule as probably
wrong before any check fired, and the rule was right for a reason the brief
never gave, the objection was the brief failing to explain itself. Five of
twenty-eight is under the line by count and past it by signal, since each
instance is a fresh context reaching that conclusion alone. Treat n independent
queries as n chunks failing one check, and fix it as R2 did: state WHY.
*Cost when skipped: a rule re-litigated by every agent on every paper, and a
check later failing chunks for obeying it.*

---

### H34
**The commonest leaked token is what the broken block CONTAINS, not what broke
it.** `leak_probe` ranks by frequency, so its top row is whatever the failed
formula uses most. Shor's list opened with `\\*[.5ex]` six times and I reported
that as the cause; pandoc renders every variant of it. The real blockers were
`\linebreak`, `\atop` and a `\multicolumn` inside an array, one occurrence
each, far down the list. One unreadable command costs the WHOLE formula, so
the leaked tokens are that formula's entire vocabulary and the culprit is
buried in it by definition. Rank by what makes a refused block render.
*Cost when skipped: a wrong cause reported with confidence, and a fix aimed at
a construct that was never broken.*

---

### H35
**Choose the next paper by measuring its source, not by its field.**
The census names constructs no paper has exercised, and the cheap way to cover
one is to fetch candidate sources and count before a single agent is spent.
Seventeen papers were surveyed that way for zero translation agents, and the
guesses they replaced were poor: three physics papers picked for their wide
tables held no `sidewaysfigure` at all, and only one of four number-theory
papers had the `\substack` all four were chosen for. A survey is a download
and a regex; translating a paper is thirty agents. Record the misses too,
"this construct is not where I assumed" is what stops the next wrong guess.
*Cost when skipped: agents spent on a paper that exercises nothing new, and
the construct still untested afterwards.*
---

### H36
**Probe a stage with the flags the pipeline gives it, not with bare pandoc.**
Reader and writer extensions can cancel each other. Asked with a plain
`-t markdown`, pandoc reported that its `smart` pass introduces nothing,
because the markdown writer un-smartens on the way out. `_WRITER` ends in
`-smart`, so in this pipeline the reader's curly quotes survive, which was the
whole effect under investigation. Import the spec (`arxiv_backend._WRITER`,
`merge_and_build._MATH_SPAN_RE`) into the probe instead of retyping an
approximation of it, and name in the docstring which stage you are measuring.
*Cost when skipped: a confident "pandoc introduces nothing" that was the exact
opposite of the truth, the fourth stage-mismatch measurement in one run,
after `\thead`, the sideways floats, and the raw-span count.*
---

### H37
**Before crediting a check with a catch, count what it has ever caught, over
the whole store, and print the denominator.**
Glob the artefacts the check reads, run its own predicate, bucket the failures
by cause. It answers "is this chronic" with a number instead of a feeling.
The denominator is the part that bites: `output/batch*/*_temp/` looked like the
corpus and was 131 of 246 metas in 8 of 21 temp dirs, and the dirs it missed
held every failure there has ever been. That sweep reported "0 invented quotes"
about a corpus from which the invented quotes had been excluded, and the number
was stated as decisive. Count the artefacts first and say how many; if the
count is not the one you expected, the glob is wrong before the finding is.
*Cost when skipped: a corpus-wide claim that was an artefact of a wildcard,
offered as the evidence for changing a check (K125, K129).*
---

### H38
**When the source cannot say which of two definitions ran, ask the printed
paper, with a phrase, gathered where the text actually enters.**
The candidates make opposite predictions about whether an argument reaches the
page, and the artefact refutes one. Three things decide whether it works.
Evidence must be a CONTIGUOUS multi-word phrase: asking whether a few of the
words each occur somewhere answers yes for almost any English sentence, and one
call whose entire argument was "processors" turned a clear verdict into a mixed
one. The samples come through the WRAPPERS, spectre never calls
`\dtcolornote` in its body, so the evidence sits at `\paul`. And the verdict
must be inherited by a wrapper that only passes its argument along, or the
caller is refused anyway.
*Cost when skipped: fourteen of the authors' private editing notes printed in a
finished book, under a package default the paper itself had switched off.*
---

## Maintenance protocol

**Trigger.** `SKILL.md` Step 9, alongside the KNOWLEDGE entry. Ask which of
the two files a finding belongs in: *did a tool surprise me* (KNOWLEDGE) or
*did my way of working cost me* (here). A finding can produce an entry in
both, but never the same entry twice.

**What belongs here**
- A practice that would have prevented rework, with the incident that proves it.
- A routing rule: which document or check to consult for which task.
- An ordering that matters (what to read, run, or confirm before what).

**What does not**
- Facts about tool behaviour; those are KNOWLEDGE.
- Anything a test now enforces, write the test, and keep one line here.
- Generic advice that is true of all programming. If it would fit in any
  project unchanged, it is not knowhow, it is filler.

**Entry format**

```markdown
### H<next number>
**The practice, as one instruction in bold.**
How to carry it out, concretely enough to follow.
*Cost when skipped: the specific incident, so the rule keeps its reason.*
```

**Rules that keep this file useful**
1. Add a row to the task index. An entry nobody can find is not knowhow.
2. Numbers are never reused, the same as KNOWLEDGE.
3. Every entry carries a real cost line. A practice with no incident behind it
   is a preference, and preferences belong in AGENTS.md's conventions.
4. Keep entries under ~14 lines.
5. When a practice becomes enforced by code or a test, compress the entry to
   the instruction plus the enforcement, and say where it lives.

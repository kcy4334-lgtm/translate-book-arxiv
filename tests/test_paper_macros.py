# -*- coding: utf-8 -*-
r"""The paper's own shorthand printed at the reader.

resnet's finished Korean book contains `\ie` five times in the middle of
sentences, where the paper prints "i.e." — confirmed both ways: the source PDF
has "i.e." exactly five times and "e.g." four, matching the five `\ie` and four
`\eg` left in `output.md`. spectre prints `\parhead{...}` over thirteen run-in
headings, and `\dtcolornote[Paul]{red}{NeedReference}` — the authors' own
margin notes — twelve times.

The cause is structural: a `.sty` is never `\input`, so `flatten_tex` does not
inline it, pandoc never sees the definition, and an unknown control sequence
survives `+raw_tex` verbatim.

Handing pandoc the definitions instead was measured and is worse. Inlining
dtrt.sty's real `\parhead` made pandoc emit NOTHING for
`\parhead{Exploiting Speculative Execution}` — thirteen headings deleted, K110
again — and cvpr.sty's `\onedot` is `\futurelet` lookahead, which pandoc cannot
evaluate, so it emitted both branches and printed `*i.e*..`.

So the expansion is done here, and the tests below are mostly about what it
REFUSES. Every refusal leaves the token exactly as it prints today; a wrong
expansion deletes an author's sentence and nothing counts the loss.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import paper_macros as pm  # noqa: E402


def defs_of(*texts):
    return pm.read_definitions([('t%d.sty' % i, t)
                                for i, t in enumerate(texts)])


CVPR = (r'\makeatletter'
        '\n' r'\DeclareRobustCommand\onedot{\futurelet\@let@token\@onedot}'
        '\n' r'\def\@onedot{\ifx\@let@token.\else.\null\fi\xspace}'
        '\n' r'\def\eg{\emph{e.g}\onedot} \def\ie{\emph{i.e}\onedot}'
        '\n' r'\def\etal{\emph{et al}\onedot}'
        '\n' r'\makeatother')


class DefinitionsAreReadInEveryFormAPaperUses(unittest.TestCase):
    def test_newcommand_with_braces(self):
        d = defs_of(r'\newcommand{\methodname}{TinyVLA}')
        self.assertEqual(d['methodname'][0].body, 'TinyVLA')
        self.assertEqual(d['methodname'][0].arity, 0)

    def test_newcommand_without_braces(self):
        d = defs_of(r'\newcommand\newcite{\citet}')
        self.assertEqual(d['newcite'][0].body, r'\citet')

    def test_arity_and_optional_argument(self):
        d = defs_of(r'\newcommand{\answerYes}[1][]{\textcolor{blue}{[Yes] #1}}')
        self.assertEqual(d['answerYes'][0].arity, 1)
        self.assertTrue(d['answerYes'][0].optional)

    def test_plain_tex_def_with_parameters(self):
        d = defs_of(r'\def\pair#1#2{#1 and #2}')
        self.assertEqual(d['pair'][0].arity, 2)

    def test_a_commented_out_definition_is_not_read(self):
        # spectre carries `%\newcommand{\ie}{\textit{i.e.},\ }` above the live
        # code. Reading it would give a second, different body and refuse the
        # macro for a conflict that exists only in a comment.
        d = defs_of('%' + r'\newcommand{\ie}{\textit{i.e.},\ }')
        self.assertNotIn('ie', d)


class TheAbbreviationPeriodIsResolved(unittest.TestCase):
    def test_ie_gets_exactly_one_period(self):
        body, why = pm.resolve('ie', defs_of(CVPR))
        self.assertIsNone(why)
        self.assertEqual(body, r'\emph{i.e}.')

    def test_the_whole_cvpr_family_resolves(self):
        d = defs_of(CVPR)
        for name, want in (('eg', r'\emph{e.g}.'), ('etal', r'\emph{et al}.')):
            self.assertEqual(pm.resolve(name, d)[0], want)

    def test_the_idiom_is_recognised_by_shape_not_by_name(self):
        # A paper is free to bind `\onedot` to something else entirely.
        other = (r'\newcommand{\onedot}{!!}' '\n'
                 r'\newcommand{\@onedot}{!!}' '\n'
                 r'\def\ie{\emph{i.e}\onedot}')
        body, why = pm.resolve('ie', defs_of(other))
        self.assertEqual(body, r'\emph{i.e}!!')


class ARefusalIsBetterThanAGuess(unittest.TestCase):
    def test_two_different_definitions_are_refused(self):
        # dtrt.sty defines \dtcolornote once to print a margin note and once to
        # print nothing, in the two branches of \ifdt@notes. The default at
        # line 127 is notes-ON, and choosing it would be choosing wrong: the
        # paper is built `camera` and its PDF contains "NeedReference" 0 times.
        d = defs_of(r'\newcommand{\dtcolornote}[3][]{\textbf{#3}}',
                    r'\newcommand{\dtcolornote}[3][]{\ignorespaces}')
        body, why = pm.resolve('dtcolornote', d)
        self.assertIsNone(body)
        self.assertIn('different definitions', why)

    def test_a_macro_that_discards_its_argument_is_refused(self):
        # bert's `\eat[1]{\ignorespaces}`. Expanding it deletes whatever the
        # author wrote inside, and no count downstream can see the loss.
        body, why = pm.resolve('eat', defs_of(r'\newcommand{\eat}[1]{\ignorespaces}'))
        self.assertIsNone(body)
        self.assertIn('discarded', why)

    def test_remaining_tex_machinery_is_refused(self):
        d = defs_of(r'\newcommand{\pick}{\ifdraft A\else B\fi}')
        self.assertIsNone(pm.resolve('pick', d)[0])

    def test_an_unresolved_command_is_refused(self):
        d = defs_of(r'\newcommand{\R}{\mathbb{R}}')
        body, why = pm.resolve('R', d)
        self.assertIsNone(body)
        self.assertIn('mathbb', why)

    def test_recursion_terminates(self):
        d = defs_of(r'\newcommand{\a}{\b}' '\n' r'\newcommand{\b}{\a}')
        self.assertIsNone(pm.resolve('a', d)[0])


class WhatPandocAlreadyReadsIsLeftAlone(unittest.TestCase):
    def test_a_redefined_cite_is_not_rewritten(self):
        # naaclhlt2019.sty makes \cite mean \citep. Rewriting 119 calls across
        # bert and SINQ would route citations -- placeholdered, mapped, then
        # rendered by citeproc -- through a textual substitution instead.
        d = defs_of(r'\newcommand{\cite}{\citep}')
        self.assertIsNone(pm.resolve('cite', d)[0])

    def test_a_redefined_url_is_not_rewritten(self):
        # The paper makes it \texttt{#1}; pandoc's reader makes it a link.
        d = defs_of(r'\newcommand{\url}[1]{\texttt{#1}}')
        self.assertIsNone(pm.resolve('url', d)[0])

    def test_newblock_is_not_deleted(self):
        # It resolves to nothing, being glue. Deleting all 115 of them runs
        # adjacent reference fields together.
        d = defs_of(r'\newcommand{\newblock}{\hskip .11em plus .33em minus -.07em}')
        self.assertIsNone(pm.resolve('newblock', d)[0])

    def test_a_tabbing_control_is_not_deleted(self):
        # Shor's `\newcommand{\tab}{\>}`, used 29 times to indent three
        # algorithm listings. `neutralize_tabbing_tabs` turns those tab stops
        # into the four-space steps that made the printed pseudocode match the
        # paper; resolving \tab to nothing first deletes all of it.
        body, why = pm.resolve('tab', defs_of(r'\newcommand{\tab}{\>}'))
        self.assertIsNone(body)
        self.assertIn('tabbing', why)


class AWrapperKeepsWhatItPrints(unittest.TestCase):
    def test_parhead_becomes_bold_and_keeps_its_argument(self):
        d = defs_of(
            r'\def\dt@MaybeAddPunct#1{#1\ifdt@Punct\else.\fi}' '\n'
            r'\def\dt@ignorespacesandimplicitepars{\begingroup\catcode13=10'
            r'\@ifnextchar\relax{\endgroup}{\endgroup}}' '\n'
            r'\newcommand{\parhead}[1]{\smallskip \noindent '
            r'{\bfseries\boldmath\ignorespaces \dt@MaybeAddPunct{#1}}'
            r'\hskip 0.9em plus 0.3em minus 0.3em '
            r'\dt@ignorespacesandimplicitepars}')
        body, why = pm.resolve('parhead', d)
        self.assertIsNone(why)
        self.assertIn('#1', body)
        self.assertIn(r'\textbf', body)

    def test_a_body_of_pure_grouping_prints_nothing(self):
        d = defs_of(r'\def\quiet{\begingroup\catcode13=10\endgroup}')
        self.assertEqual(pm.resolve('quiet', d), ('', None))

    def test_a_size_switch_does_not_make_a_macro_unresolvable(self):
        # bert's \bertbase is `BERT$_{\small \textsc{BASE}}$\xspace`, and the
        # class defines \small in terms of itself. Following that reported
        # "recursive definition" and refused the macro.
        d = defs_of(r'\newcommand{\small}{\@setfontsize\small\@ixpt}' '\n'
                    r'\newcommand{\bertbase}{BERT$_{\small \textsc{BASE}}$\xspace}')
        body, why = pm.resolve('bertbase', d)
        self.assertIsNone(why)
        self.assertIn('BERT', body)


class TheTrailingSpaceIsLoadBearing(unittest.TestCase):
    def test_an_escaped_space_survives(self):
        # `\newcommand{\etal}{et~al.\ }` relies on it, because LaTeX eats the
        # space after a control word. Strip it and the next word is welded on;
        # strip only the space and a lone trailing backslash is left, which
        # K136 records as valid LaTeX that no check rejects.
        body, why = pm.resolve('etal', defs_of(r'\newcommand{\etal}{et~al.\ }'))
        self.assertIsNone(why)
        self.assertTrue(body.endswith(' '), repr(body))
        self.assertFalse(body.rstrip().endswith('\\'), repr(body))


class OnlyTheProseIsRewritten(unittest.TestCase):
    def setUp(self):
        self.src = [('a.sty', r'\newcommand{\ie}{i.e.}')]

    def rewrite(self, body):
        tex = r'\begin{document}' '\n' + body + '\n' r'\end{document}'
        out, rep = pm.expand_in_source(tex, self.src)
        return out, rep

    def test_prose_is_rewritten(self):
        out, rep = self.rewrite(r'the residual, \ie, the difference')
        self.assertIn('the residual, i.e., the difference', out)
        self.assertEqual(rep['expanded']['ie'], 1)

    def test_maths_is_left_alone(self):
        # Inside `$...$` the same name is texmath's business, and
        # `check_math_fidelity` compares those formulas against the source.
        out, _ = self.rewrite(r'see $\ie{}$ here')
        self.assertIn(r'$\ie{}$', out)

    def test_display_maths_is_left_alone(self):
        out, _ = self.rewrite('$$\n' r'\ie' '\n$$')
        self.assertIn(r'\ie', out)

    def test_verbatim_is_left_alone(self):
        out, _ = self.rewrite(r'\begin{verbatim}' '\n' r'\ie' '\n'
                              r'\end{verbatim}')
        self.assertIn(r'\ie', out)

    def test_the_preamble_is_left_alone(self):
        tex = (r'\newcommand{\ie}{i.e.}' '\n' r'\begin{document}' '\n'
               r'x \ie y' '\n' r'\end{document}')
        out, _ = pm.expand_in_source(tex, [('flat.tex', tex)])
        self.assertIn(r'\newcommand{\ie}{i.e.}', out)
        self.assertIn('x i.e. y', out)

    def test_a_longer_name_is_not_matched_inside_a_longer_one(self):
        src = [('a.sty', r'\newcommand{\eta}{H}' '\n'
                         r'\newcommand{\etaX}{HX}')]
        tex = r'\begin{document}' '\n' r'\etaX' '\n' r'\end{document}'
        out, rep = pm.expand_in_source(tex, src)
        self.assertIn('HX', out)
        self.assertNotIn('HXX', out)

    def test_a_call_with_too_few_arguments_is_left_alone(self):
        src = [('a.sty', r'\newcommand{\pair}[2]{#1-#2}')]
        tex = r'\begin{document}' '\n' r'\pair{a}' '\n' r'\end{document}'
        out, rep = pm.expand_in_source(tex, src)
        self.assertIn(r'\pair{a}', out)
        self.assertEqual(rep['expanded'], {})

    def test_arguments_are_substituted_in_order(self):
        src = [('a.sty', r'\newcommand{\pair}[2]{#1-#2}')]
        tex = r'\begin{document}' '\n' r'\pair{a}{b}' '\n' r'\end{document}'
        out, _ = pm.expand_in_source(tex, src)
        self.assertIn('a-b', out)

    def test_an_absent_optional_argument_uses_the_default(self):
        src = [('a.sty', r'\newcommand{\answerYes}[1][]{[Yes] #1}')]
        tex = r'\begin{document}' '\n' r'\answerYes{}' '\n' r'\end{document}'
        out, _ = pm.expand_in_source(tex, src)
        self.assertIn('[Yes]', out)

    def test_a_refusal_is_reported_rather_than_swallowed(self):
        src = [('a.sty', r'\newcommand{\note}[3][]{\textbf{#3}}' '\n'
                         r'\newcommand{\note}[3][]{\ignorespaces}')]
        tex = r'\begin{document}' '\n' r'\note[a]{b}{c}' '\n' r'\end{document}'
        out, rep = pm.expand_in_source(tex, src)
        self.assertIn('note', rep['refused'])
        self.assertIn(r'\note[a]{b}{c}', out)


class AnOddDollarInAMacroBodyIsNotADocumentDelimiter(unittest.TestCase):
    r"""planck defines `\Hunit` as `\ifmmode ...$\else ...\fi` — an odd number
    of `$`, which TeX balances through the conditional and a regex cannot.

    Paired on the raw source, that stray `$` opened a span that closed on the
    first `$` in the body, and every `$` after it paired inverted: 328 spans
    that contained a blank line, which no formula does. The cost was 73
    rewrites landing INSIDE planck's formulas. Every other paper in the corpus
    measured 0, so only a whole-corpus sweep could show it.

    Both directions matter, and the test asserts both: prose outside the real
    formula must still be rewritten, and the real formula must not be.
    """

    SRC = [('a.sty',
            r'\newcommand{\unit}{\ifmmode \mathrm{km}$\else km\fi}' '\n'
            r'\newcommand{\tag}{TAG}')]

    def test_prose_before_the_first_formula_is_still_rewritten(self):
        tex = (r'\begin{document}' '\n'
               r'first \tag here and a formula $a \tag b$ end' '\n'
               r'\end{document}')
        out, rep = pm.expand_in_source(tex, self.SRC)
        self.assertIn('first TAG here', out)
        self.assertEqual(rep['expanded'].get('tag'), 1)

    def test_the_real_formula_is_left_alone(self):
        tex = (r'\begin{document}' '\n'
               r'first \tag here and a formula $a \tag b$ end' '\n'
               r'\end{document}')
        out, _ = pm.expand_in_source(tex, self.SRC)
        self.assertIn(r'$a \tag b$', out)

    def test_no_span_swallows_a_paragraph_break(self):
        tex = (r'\begin{document}' '\n'
               r'one $x$ two' '\n\n' r'three $y$ four' '\n'
               r'\end{document}')
        defs = pm.read_definitions(self.SRC)
        for start, end in pm._protected_spans(tex, defs):
            self.assertNotIn('\n\n', tex[start:end],
                             'a span reaching across a blank line is not a '
                             'formula: %r' % tex[start:end])


class ThePrintedPaperSettlesAConditionalDefinition(unittest.TestCase):
    r"""dtrt.sty defines `\dtcolornote` once to print an author's margin note
    and once to print nothing, in the two branches of `\ifdt@notes`. Reading
    the source cannot choose: the branch is selected by a package option, and
    the DEFAULT at line 127 is notes-on, which is the wrong one — spectre is
    built `camera` and its PDF contains "NeedReference" zero times.

    So the artefact is asked instead. One candidate prints its argument and
    the other discards it; whichever prediction the paper contradicts is out.
    """

    NOTE = (r'\newcommand{\note}[3][]{\textbf{#3}}' '\n'
            r'\newcommand{\note}[3][]{\ignorespaces}')
    CALL = (r'\begin{document}' '\n'
            r'buffer overflow \note[Paul]{red}{a citation is needed here}'
            ' and more text\n' r'\end{document}')

    def test_a_note_absent_from_the_paper_selects_the_silent_branch(self):
        paper = 'buffer overflow and more text'
        out, rep = pm.expand_in_source(self.CALL, [('d.sty', self.NOTE)],
                                       paper_text=paper)
        self.assertEqual(rep.get('decided', {}).get('note'), 'd.sty')
        self.assertNotIn('citation is needed', out)
        self.assertIn('buffer overflow', out)

    def test_a_note_the_paper_prints_selects_the_printing_branch(self):
        paper = 'buffer overflow a citation is needed here and more text'
        out, rep = pm.expand_in_source(self.CALL, [('d.sty', self.NOTE)],
                                       paper_text=paper)
        self.assertEqual(rep.get('decided', {}).get('note'), 'd.sty')
        self.assertIn('citation is needed here', out)

    def test_without_the_paper_it_stays_refused(self):
        out, rep = pm.expand_in_source(self.CALL, [('d.sty', self.NOTE)])
        self.assertIn('note', rep['refused'])
        self.assertIn(r'\note[Paul]{red}', out)

    def test_a_wrapper_inherits_the_verdict(self):
        # spectre never calls \dtcolornote in the body; all fourteen notes
        # arrive through `\newcommand{\paul}[1]{\dtcolornote[Paul]{red}{#1}}`.
        src = [('d.sty', self.NOTE),
               ('flat.tex', r'\newcommand{\paul}[1]{\note[Paul]{red}{#1}}')]
        tex = (r'\begin{document}' '\n'
               r'overflow \paul{a citation is needed here} and more'
               '\n' r'\end{document}')
        out, rep = pm.expand_in_source(tex, src, paper_text='overflow and more')
        self.assertNotIn('citation is needed', out)
        self.assertNotIn(r'\paul', out)

    def test_one_common_word_is_not_evidence(self):
        # `\yval` is called with "processors", which occurs in spectre for
        # reasons unrelated to the macro. Counting that as a hit turned a clear
        # verdict into a mixed one and refused the macro.
        tex = (r'\begin{document}' '\n' r'x \note[a]{red}{processors}'
               '\n' r'\end{document}')
        out, rep = pm.expand_in_source(tex, [('d.sty', self.NOTE)],
                                       paper_text='the processors are fast')
        self.assertIn('note', rep['refused'])

    def test_mixed_evidence_refuses(self):
        tex = (r'\begin{document}' '\n'
               r'\note[a]{red}{alpha beta gamma delta}'
               r'\note[a]{red}{epsilon zeta eta theta}'
               '\n' r'\end{document}')
        out, rep = pm.expand_in_source(
            tex, [('d.sty', self.NOTE)],
            paper_text='alpha beta gamma delta is printed but not the other')
        self.assertIn('note', rep['refused'])


if __name__ == '__main__':
    unittest.main()

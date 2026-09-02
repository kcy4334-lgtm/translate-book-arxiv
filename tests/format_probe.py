#!/usr/bin/env python3
"""
format_probe.py - Check that DOCX and EPUB actually carry what the PDF does.

Not named test_*.py: it needs a built temp dir, so `unittest discover` must not
collect it.

    python tests/format_probe.py <temp_dir> [--strict]

Why this exists: the layout probe measures the PDF, and only the PDF. Twice in
one session a change that looked equivalent broke a *different* output path and
nothing noticed --

  * figure captions injected as raw HTML: pandoc drops raw HTML when writing
    DOCX, so all ten images vanished and book.docx fell from 5.4MB to 25KB.
  * tables injected as raw HTML: book.docx shipped with ZERO tables while every
    check printed OK, because the table fidelity gate reads the HTML.

Raw HTML survives the HTML path alone. Anything injected has to be verified in
each format that is supposed to carry it, not inferred from the one you looked
at.
"""

import argparse
import glob
import html as _html_lib
import json
import os
import re
import sys
import zipfile


# --- untranslated table furniture -------------------------------------------
#
# A table float behind a ⟦T####⟧ placeholder never reaches a translator: the
# math guard hides it so no backslash can be damaged, and the caption and
# column headers go along with it. SINQ shipped 14 tables whose captions were
# still English inside an otherwise Korean book, and every other check passed
# -- they count tables, images and values, and those were all correct.

_SCRIPT_RANGES = {
    'ko': (0xAC00, 0xD7A3),
    'ja': (0x3040, 0x30FF),
    'zh': (0x4E00, 0x9FFF),
}
_TABULAR_RE = re.compile(r'\\begin\{(tabular|tabularx|longtable|array)\*?\}')
_CAPTION_RE = re.compile(r'\\caption\s*(?:\[[^\]]*\])?\s*\{')


def _balanced(text, open_at):
    depth = 0
    for i in range(open_at, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return i + 1
    return -1


def _unescape(text):
    return _html_lib.unescape(text)


def _in_target_script(text, lang):
    lo, hi = _SCRIPT_RANGES.get(lang, (0, 0))
    if not hi:
        return True                       # latin target: nothing to check
    return any(lo <= ord(ch) <= hi for ch in text)


def _float_sources(temp_dir):
    """[(where, latex)] for every LaTeX table, wherever it is stored."""
    out = []
    for path in sorted(glob.glob(os.path.join(temp_dir, 'output_chunk*.md'))):
        text = _read(path)
        if _TABULAR_RE.search(text):
            out.append((os.path.basename(path), text))
    for path in sorted(glob.glob(os.path.join(temp_dir, 'chunk*.math.json'))):
        try:
            data = json.loads(_read(path))
        except ValueError:
            continue
        for span in data.get('spans') or []:
            latex = span.get('latex') or ''
            if _TABULAR_RE.search(latex):
                out.append(('%s %s' % (os.path.basename(path),
                                       span.get('token', '?')), latex))
    return out


def _read(path):
    with open(path, encoding='utf-8', errors='replace') as fh:
        return fh.read()


_THEAD_RE = re.compile(r'<thead\b')
_TABLE_EL_RE = re.compile(r'<table(?:\s[^>]*)?>.*?</table>', re.DOTALL)


def _ebook_body(temp_dir):
    """The built ebook HTML with style and script blocks taken out."""
    path = os.path.join(temp_dir, "book_doc.html")
    if not os.path.isfile(path):
        return None
    return _STYLE_RE.sub(" ", _read(path))



def check_docx_header_depth(temp_dir):
    """Word's repeated header rows against the header the source declares.

    pandoc marks one header row or none. A table whose header is two decks
    deep -- the spanning kind, the one a reader most needs repeated -- came
    out of Word with its numbers unlabelled from page two, while the ebook
    built from the same data had it right. Two formats disagreeing about the
    same table is the only evidence in this project that cannot be produced
    by one code path agreeing with itself.
    """
    docx = os.path.join(temp_dir, "book.docx")
    flat = os.path.join(temp_dir, "flat.tex")
    if not os.path.isfile(docx) or not os.path.isfile(flat):
        return None
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.join(os.path.dirname(here), "scripts"))
    try:
        import merge_and_build as mb
        import zipfile
        plans = mb.table_structures(temp_dir)
        with zipfile.ZipFile(docx) as zf:
            doc = zf.read("word/document.xml").decode("utf-8", "replace")
    except Exception:
        return None
    tables = re.findall(r"<w:tbl>.*?</w:tbl>", doc, re.DOTALL)
    if not plans or len(tables) != len(plans):
        return None
    short = sum(1 for plan, tbl in zip(plans, tables)
                if (plan.get("header") or 0) > tbl.count("tblHeader"))
    return short, len(tables)


def check_table_headers(body):
    """(tables, how many carry a <thead>).

    A header left in the body does not repeat when the table breaks across a
    page, so from page two the reader is looking at unlabelled numbers.
    Nothing else in this file would notice: the table is there, its cells are
    there, and every count comes out right.
    """
    tables = _TABLE_EL_RE.findall(body)
    return len(tables), sum(1 for t in tables if _THEAD_RE.search(t))


def check_caption_numbers(temp_dir, body, lang):
    """Numbered table captions in the book, against captions in flat.tex.

    check_table_language() reads LaTeX, so for a book whose tables all became
    markdown it examines nothing and prints "0 still in the source language",
    which reads like a pass. This counts the finished captions instead, and
    compares them with what the source says should be there.
    """
    flat = os.path.join(temp_dir, "flat.tex")
    if not os.path.isfile(flat):
        return None
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.join(os.path.dirname(here), "scripts"))
    try:
        import merge_and_build as mb
        label = mb.get_lang_config(lang).get("table_label")
    except Exception:
        return None
    if not label:
        return None
    if label == "Table":
        return None        # "Table 5" is also how the prose refers to it
    want = [u for u in mb.float_units(_read(flat))
            if u["kind"] == "table" and u["number"]]
    badge = re.compile(r"%s\s*(\d+)\s*\(\s*Table\s*(\d+)\s*\)"
                       % re.escape(label))
    found, untranslated, disagree = [], [], []
    for m in badge.finditer(body):
        here, original = int(m.group(1)), int(m.group(2))
        found.append(here)
        if here != original:
            disagree.append("%s %d is labelled Table %d" % (label, here, original))
        text = _caption_text(body, m.end())
        if len(text) >= 16 and not _in_target_script(text, lang):
            untranslated.append("%s %d: %s" % (label, here, text[:56]))
    return len(want), found, untranslated, disagree


_CAPTION_END_RE = re.compile(
    r"</p>|</caption>|</figcaption>|</td>|</th>|</div>|</li>|<table\b")


def _caption_text(body, at):
    """The caption's own words: from the badge to the end of its block.

    Bounded deliberately. A fixed window of N characters spills into the
    paragraph below, and one Hangul syllable anywhere in that window is
    enough to make an English caption look translated.
    """
    end = _CAPTION_END_RE.search(body, at, at + 1200)
    chunk = body[at:end.start()] if end else body[at:at + 400]
    return " ".join(_unescape(_TAG_RE.sub(" ", chunk)).split())


def check_table_language(temp_dir, lang):
    """(translated, untranslated, [examples]) for table captions."""
    done, missing, examples = 0, 0, []
    for where, latex in _float_sources(temp_dir):
        for m in _CAPTION_RE.finditer(latex):
            close = _balanced(latex, latex.index('{', m.end() - 1))
            if close < 0:
                continue
            body = latex[latex.index('{', m.end() - 1) + 1:close - 1]
            if len(body.strip()) < 12:
                continue
            if _in_target_script(body, lang):
                done += 1
            else:
                missing += 1
                if len(examples) < 4:
                    examples.append('%s: %s' % (where, ' '.join(body.split())[:64]))
    return done, missing, examples


_CELL_RE = re.compile(r'<t[hd][^>]*>(.*?)</t[hd]>', re.DOTALL)
_TAG_RE = re.compile(r'<[^>]+>')
# What a table's own markup looks like when it did not become a table. Two
# separators, not one: `|W|` is an ordinary norm and shows up in real cells.
_MARKUP_IN_CELL_RE = re.compile(r'\|[^|]*\|[^|]*\||\+[-=:]{3,}\+|^\s*[-=]{3,}\s')


def check_collapsed_tables(temp_dir):
    """Tables that stayed text, counted from the built HTML.

    pandoc lays out grid and simple tables by DISPLAY width, where a Hangul
    syllable is two columns. Translate a cell and the separators no longer
    meet the rule, so pandoc abandons the table and emits one cell per line
    with the pipes still in it. It is still a `<table>` with rows and cells,
    so every count this probe already made came out right while the reader
    saw `방법 | UNIFORM | RANDOM | ...` as a single run of text.
    """
    html = os.path.join(temp_dir, 'book_doc.html')
    if not os.path.isfile(html):
        return 0, []
    text = _read(html)
    bad, examples = 0, []
    for table in re.findall(r'<table.*?</table>', text, re.DOTALL):
        for cell in _CELL_RE.findall(table):
            body = _TAG_RE.sub('', cell).strip()
            if _MARKUP_IN_CELL_RE.search(body):
                bad += 1
                if len(examples) < 4:
                    examples.append(re.sub(r'\s+', ' ', body)[:70])
                break
    return bad, examples


def _docx(path):
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
        media = [n for n in z.namelist() if n.startswith("word/media/")]
    return {
        "tables": xml.count("<w:tbl>"),
        "images": len(media),
        "equations": len(re.findall(r"<m:oMath[ >]", xml)),
        "headings": len(re.findall(r'w:val="Heading[1-9]"', xml)),
        "text": re.sub(r"<[^>]+>", " ", xml),
    }


def _epub(path):
    with zipfile.ZipFile(path) as z:
        html = "".join(
            z.read(n).decode("utf-8", "replace")
            for n in z.namelist() if n.lower().endswith((".xhtml", ".html")))
        media = [n for n in z.namelist()
                 if n.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".svg"))]
    return {
        "tables": html.count("<table"),
        "images": len(media),
        "equations": len(re.findall(r"<math\b", html)),
        "text": re.sub(r"<[^>]+>", " ", html),
    }


_STYLE_RE = re.compile(r"<style\b.*?</style>|<script\b.*?</script>",
                       re.DOTALL | re.IGNORECASE)

# A writer may legitimately merge or split a few things -- a DOCX renders some
# inline maths as text, an EPUB splits a table. Losing a third of them is a
# dropped feature. AlphaQ's Word file had 3 of 12 tables (0.25) and 181 of 203
# equations (0.89): the first is the bug, the second is ordinary drift.
_PARITY_FLOOR = 0.67


def short_of_reference(have, want):
    """Is this format missing so much that a feature must have been dropped?"""
    if have is None or not want:
        return False
    return have < want * _PARITY_FLOOR


def _ebook_html(temp_dir):
    """What the build itself validated, as the reference every format meets.

    Comparing each format against zero is what let nine of AlphaQ's twelve
    tables sit in the Word file as plain text: three is not zero, so nothing
    complained, and the HTML had all twelve so every other count agreed with
    itself. The formats have to be compared against EACH OTHER.
    """
    path = os.path.join(temp_dir, "book_doc.html")
    if not os.path.isfile(path):
        return None
    body = _STYLE_RE.sub(" ", _read(path))
    return {
        "tables": len(re.findall(r"<table(?:\s[^>]*)?>", body)),
        "images": len(re.findall(r"<img\b", body)),
        "equations": len(re.findall(r"<math\b", body)),
        "headings": len(re.findall(r"<h[1-6][ >]", body)),
    }


def _pdf(path):
    import pymupdf
    doc = pymupdf.open(path)
    try:
        text = "".join(p.get_text("text") for p in doc)
        images = sum(len(doc[i].get_images(full=True)) for i in range(doc.page_count))
        return {"tables": None, "images": images, "text": text, "pages": doc.page_count}
    finally:
        doc.close()


def probe(temp_dir, strict=False, lang=None):
    """Compare the three formats against the merged markdown they came from."""
    md_path = os.path.join(temp_dir, "output.md")
    if not os.path.isfile(md_path):
        print("ERROR: no output.md in %s" % temp_dir)
        return 1
    with open(md_path, encoding="utf-8") as fh:
        md = fh.read()

    want_images = len(set(re.findall(r"!\[[^\]]*\]\(([^)]+)\)", md)))
    want_tables = md.count(r"\begin{tabular}") + len(
        [1 for i, line in enumerate(md.splitlines())
         if i and re.match(r"^[ \t]*\|?[ \t]*:?-{3,}", line)])

    # Distinctive strings that only live inside tables, taken from the source.
    cells = re.findall(r"(?<![\w.])(\d{1,3}\.\d)(?![\w.])", md)
    probes = sorted(set(cells))[:6]

    formats = {}
    broken = []
    for name, fn, ext in (("docx", _docx, ".docx"),
                          ("epub", _epub, ".epub"),
                          ("pdf", _pdf, ".pdf")):
        path = os.path.join(temp_dir, "book" + ext)
        if not os.path.isfile(path):
            print("  %-5s MISSING" % name)
            broken.append("%s was never produced" % name)
            continue
        try:
            formats[name] = fn(path)
        except Exception as e:                                  # noqa: BLE001
            print("  %-5s unreadable: %s" % (name, e))
            broken.append("%s could not be opened (%s)" % (name, e))

    print("merged markdown: %d image ref(s), ~%d table(s)" % (want_images, want_tables))
    print()
    print("%-6s %8s %8s %10s  %s" % ("format", "tables", "images", "size KB", "table values found"))
    print("-" * 68)
    # A format that is absent is the loudest possible failure: it means the
    # build stopped early. Reporting PASS because there was nothing to check
    # is how two of these papers shipped with no PDF at all.
    fails = list(broken)
    for name, data in formats.items():
        size = os.path.getsize(os.path.join(temp_dir, "book." + name)) / 1024
        found = sum(1 for p in probes if p in data["text"])
        shown = "-" if data["tables"] is None else data["tables"]
        print("%-6s %8s %8d %10.0f  %d/%d" %
              (name, shown, data["images"], size, found, len(probes)))

        if data["images"] < want_images:
            fails.append("%s carries %d of %d images" %
                         (name, data["images"], want_images))
        if probes and found == 0:
            fails.append("%s contains none of the table values %s" % (name, probes))
        if data["tables"] == 0 and want_tables:
            fails.append("%s has no tables at all, but the source has ~%d"
                         % (name, want_tables))

    # --- do the formats agree with each other? ---------------------------
    ref = _ebook_html(temp_dir)
    if ref:
        print()
        print("against the ebook HTML (%d table, %d image, %d equation, "
              "%d heading)" % (ref["tables"], ref["images"], ref["equations"],
                               ref["headings"]))
        for name, data in formats.items():
            for what in ("tables", "images", "equations"):
                if short_of_reference(data.get(what), ref[what]):
                    fails.append("%s carries %d of the %d %s the ebook HTML has"
                                 % (name, data[what], ref[what], what))
        docx = formats.get("docx")
        if docx and ref["headings"] and not docx.get("headings"):
            fails.append("book.docx has no Heading styles, so Word shows no "
                         "outline for it")

    collapsed, examples = check_collapsed_tables(temp_dir)
    if collapsed:
        print()
        print("collapsed table(s): %d" % collapsed)
        for line in examples:
            print("   - " + line)
        fails.append("%d table(s) collapsed: the markup is sitting in the "
                     "cells as text" % collapsed)

    depth = check_docx_header_depth(temp_dir)
    if depth:
        short, total = depth
        print()
        print("Word header rows: %d of %d table(s) repeat their full header"
              % (total - short, total))
        if short:
            fails.append("%d Word table(s) repeat fewer header rows than the "
                         "source has, so the header stops after a page break"
                         % short)

    body = _ebook_body(temp_dir)
    if body is not None:
        total, headed = check_table_headers(body)
        print()
        print("table headers: %d of %d table(s) carry a <thead>"
              % (headed, total))
        if headed < total:
            print("   - %d table(s) have no header row, so nothing repeats "
                  "when they break across a page" % (total - headed))

    if lang and body is not None:
        counted = check_caption_numbers(temp_dir, body, lang)
        if counted:
            want, seen, untranslated, disagree = counted
            print("table captions numbered: %d in the source, %d in the book"
                  % (want, len(seen)))
            for line in untranslated[:4] + disagree[:4]:
                print("   - " + line)
            if untranslated:
                fails.append("%d numbered table caption(s) are still in the "
                             "source language" % len(untranslated))
            if disagree:
                fails.append("%d table caption(s) carry two different numbers"
                             % len(disagree))
            if len(seen) != want:
                fails.append("the source has %d numbered table caption(s), "
                             "the book shows %d" % (want, len(seen)))
            elif sorted(seen) != list(range(1, want + 1)):
                fails.append("table caption numbers are not 1..%d: %s"
                             % (want, sorted(seen)[:12]))

    if lang:
        done, missing, examples = check_table_language(temp_dir, lang)
        print()
        print("table captions in %s: %d translated, %d still in the source language"
              % (lang, done, missing))
        for line in examples:
            print("   - " + line)
        if missing:
            fails.append("%d table caption(s) never reached a translator "
                         "(they sit behind a placeholder)" % missing)

    print()
    if fails:
        print("FAIL:")
        for f in fails:
            print("  - " + f)
        return 1 if strict else 0
    print("PASS: %s carry their tables and images"
          % ', '.join(sorted(formats)))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("temp_dir", help="a built <name>_temp directory")
    ap.add_argument("--strict", action="store_true",
                    help="exit non-zero when a format is missing content")
    ap.add_argument("--lang",
                    help="target language code; checks that table captions "
                         "were actually translated (ko, ja, zh)")
    args = ap.parse_args()
    sys.exit(probe(args.temp_dir, args.strict, args.lang))


if __name__ == "__main__":
    main()

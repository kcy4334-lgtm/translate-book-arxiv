import contextlib
import io
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import chromium_pdf  # noqa: E402
import layout  # noqa: E402

# A stub that clears verify_pdf's size and magic checks.
STUB_PDF = b"%PDF-1.4\n" + b"\0" * 4096


class BuildChromeArgvTests(unittest.TestCase):
    """The argv IS the contract; these are pure and need no mocking."""

    def argv(self, **kw):
        with tempfile.TemporaryDirectory() as d:
            html = Path(d) / "in.html"
            html.write_text("<html></html>", encoding="utf-8")
            return chromium_pdf.build_chrome_argv(
                "chrome.exe", str(html), str(Path(d) / "out.pdf"),
                str(Path(d) / "prof"), **kw)

    def test_print_to_pdf_path_is_absolute(self):
        flag = [a for a in self.argv() if a.startswith("--print-to-pdf=")][0]
        self.assertTrue(os.path.isabs(flag.split("=", 1)[1]))

    def test_input_is_a_file_uri_and_is_last(self):
        argv = self.argv()
        self.assertTrue(argv[-1].startswith("file:///"), argv[-1])
        self.assertNotIn("\\", argv[-1])

    def test_headless_and_no_header_footer_present(self):
        argv = self.argv()
        self.assertIn("--headless", argv)
        self.assertIn("--no-pdf-header-footer", argv)
        # Old headless was removed in Chrome 132 and now errors.
        self.assertNotIn("--headless=old", argv)

    def test_user_data_dir_is_the_given_profile_dir(self):
        """Regression lock. Without a distinct profile, a running Chrome
        swallows the command line and exits 0 having produced nothing."""
        argv = self.argv()
        flags = [a for a in argv if a.startswith("--user-data-dir=")]
        self.assertEqual(len(flags), 1)
        self.assertTrue(flags[0].split("=", 1)[1].endswith("prof"))

    def test_virtual_time_budget_is_threaded_through(self):
        self.assertIn("--virtual-time-budget=4200", self.argv(virtual_time_ms=4200))

    def test_no_sandbox_is_opt_in(self):
        self.assertNotIn("--no-sandbox", self.argv())
        self.assertIn("--no-sandbox", self.argv(no_sandbox=True))


class FindChromiumTests(unittest.TestCase):
    def setUp(self):
        chromium_pdf._CHROMIUM_CACHE.clear()

    def tearDown(self):
        chromium_pdf._CHROMIUM_CACHE.clear()

    def test_env_override_wins(self):
        with mock.patch.dict(os.environ, {"TRANSLATE_BOOK_CHROME": "/x/chrome"}), \
             mock.patch.object(chromium_pdf.os.path, "isfile",
                               side_effect=lambda p: p == "/x/chrome"), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(chromium_pdf.find_chromium(), "/x/chrome")

    def test_returns_none_and_caches_the_miss(self):
        with mock.patch.object(chromium_pdf.os.path, "isfile", return_value=False) as isfile, \
             mock.patch.object(chromium_pdf.shutil, "which", return_value=None):
            self.assertIsNone(chromium_pdf.find_chromium())
            calls = isfile.call_count
            self.assertIsNone(chromium_pdf.find_chromium())
            self.assertEqual(isfile.call_count, calls, "second call re-probed")

    def test_does_not_probe_with_version(self):
        """A running Chrome answers --version with exit 0 and no version
        string, so a probe would validate binaries that cannot render."""
        with mock.patch.object(chromium_pdf.os.path, "isfile", return_value=False), \
             mock.patch.object(chromium_pdf.shutil, "which", return_value=None), \
             mock.patch.object(chromium_pdf.subprocess, "run") as run:
            chromium_pdf.find_chromium()
            run.assert_not_called()


class VerifyPdfTests(unittest.TestCase):
    """Only the stdlib layer, which is why verify_pdf runs it before importing
    pymupdf -- CI has no pip packages."""

    def test_missing_file(self):
        ok, detail = chromium_pdf.verify_pdf("/definitely/not/here.pdf")
        self.assertFalse(ok)
        self.assertIn("no file", detail)

    def test_too_small(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.pdf"
            p.write_bytes(b"%PDF-1.4")
            ok, detail = chromium_pdf.verify_pdf(str(p))
            self.assertFalse(ok)
            self.assertIn("too small", detail)

    def test_bad_magic(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.pdf"
            p.write_bytes(b"<html>" + b"\0" * 4096)
            ok, detail = chromium_pdf.verify_pdf(str(p))
            self.assertFalse(ok)
            self.assertIn("magic", detail)


class HtmlToPdfTests(unittest.TestCase):
    def setUp(self):
        chromium_pdf._CHROMIUM_CACHE.clear()

    def _run(self, fake_run, **kw):
        """Drive html_to_pdf with a mocked browser. Returns (ok, stdout, argv)."""
        seen = {}

        def spy(cmd, **kwargs):
            seen["argv"] = cmd
            return fake_run(cmd, **kwargs)

        buf = io.StringIO()
        with tempfile.TemporaryDirectory() as d:
            html = Path(d) / "book_doc.html"
            html.write_text("<html><body>x</body></html>", encoding="utf-8")
            self._out = Path(d) / "book.pdf"
            with mock.patch.object(chromium_pdf, "find_chromium", return_value="chrome.exe"), \
                 mock.patch.object(chromium_pdf.subprocess, "run", side_effect=spy), \
                 mock.patch.object(chromium_pdf, "stamp_page_numbers", return_value=1), \
                 mock.patch.object(chromium_pdf, "verify_pdf",
                                   side_effect=_stdlib_only_verify), \
                 contextlib.redirect_stdout(buf):
                ok = chromium_pdf.html_to_pdf(str(html), str(self._out), **kw)
        return ok, buf.getvalue(), seen.get("argv")

    def test_invokes_chromium_and_succeeds(self):
        def fake_run(cmd, **kw):
            out = [a for a in cmd if a.startswith("--print-to-pdf=")][0].split("=", 1)[1]
            Path(out).write_bytes(STUB_PDF)
            return mock.Mock(returncode=0, stdout="", stderr="")

        ok, out, argv = self._run(fake_run)
        self.assertTrue(ok, out)
        self.assertEqual(argv[0], "chrome.exe")
        self.assertIn("--headless", argv)

    def test_fails_when_chromium_missing(self):
        buf = io.StringIO()
        with tempfile.TemporaryDirectory() as d:
            html = Path(d) / "a.html"
            html.write_text("<html></html>", encoding="utf-8")
            with mock.patch.object(chromium_pdf, "find_chromium", return_value=None), \
                 contextlib.redirect_stdout(buf):
                ok = chromium_pdf.html_to_pdf(str(html), str(Path(d) / "a.pdf"))
        self.assertFalse(ok)
        self.assertIn("ERROR", buf.getvalue())

    def test_fails_when_exit_zero_but_no_file(self):
        """The whole reason this module exists: --print-to-pdf always exits 0."""
        def fake_run(cmd, **kw):
            return mock.Mock(returncode=0, stdout="", stderr="")

        ok, out, _ = self._run(fake_run)
        self.assertFalse(ok)
        self.assertIn("no usable PDF", out)

    def test_fails_when_file_is_a_stub(self):
        def fake_run(cmd, **kw):
            out = [a for a in cmd if a.startswith("--print-to-pdf=")][0].split("=", 1)[1]
            Path(out).write_bytes(b"%PDF-1.4")
            return mock.Mock(returncode=0, stdout="", stderr="")

        ok, out, _ = self._run(fake_run)
        self.assertFalse(ok)

    def test_fails_on_timeout(self):
        def fake_run(cmd, **kw):
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=1)

        ok, out, _ = self._run(fake_run, timeout=1)
        self.assertFalse(ok)
        self.assertIn("timed out", out)

    def test_profile_dir_does_not_survive(self):
        holder = {}

        def fake_run(cmd, **kw):
            flag = [a for a in cmd if a.startswith("--user-data-dir=")][0]
            holder["dir"] = flag.split("=", 1)[1]
            out = [a for a in cmd if a.startswith("--print-to-pdf=")][0].split("=", 1)[1]
            Path(out).write_bytes(STUB_PDF)
            return mock.Mock(returncode=0, stdout="", stderr="")

        ok, out, _ = self._run(fake_run)
        self.assertTrue(ok, out)
        self.assertFalse(os.path.exists(holder["dir"]))


def _stdlib_only_verify(path, **kw):
    """verify_pdf without the pymupdf half, so these tests need no pip deps."""
    if not os.path.isfile(path):
        return False, "Chromium wrote no file at all"
    if os.path.getsize(path) < 1024:
        return False, "file is too small to be a real PDF"
    with open(path, "rb") as fh:
        if fh.read(5) != b"%PDF-":
            return False, "file does not start with the %PDF- magic"
    return True, ""


@unittest.skipUnless(os.environ.get("TRANSLATE_BOOK_SLOW_TESTS"),
                     "slow: set TRANSLATE_BOOK_SLOW_TESTS=1")
class ChromiumIntegrationTests(unittest.TestCase):
    """Really launches a browser. Double-gated so neither CI nor a casual
    `unittest discover` ever runs it."""

    def setUp(self):
        if not chromium_pdf.find_chromium():
            self.skipTest("no Chromium/Chrome available")
        try:
            import pymupdf  # noqa: F401
        except ImportError:
            self.skipTest("pymupdf not installed")

    def test_renders_a4_with_the_requested_geometry(self):
        import pymupdf
        cfg = layout.get_print_profile("a4-book")
        html_text = (
            "<!doctype html><html lang='ko'><head><meta charset='utf-8'><style>"
            "@page { size: %s; margin: %s; }"
            "</style></head><body><p>레이아웃 검증</p></body></html>"
            % (cfg["page_size"], layout.page_margin_css(cfg))
        )
        with tempfile.TemporaryDirectory() as d:
            html = Path(d) / "a.html"
            html.write_text(html_text, encoding="utf-8")
            pdf = Path(d) / "a.pdf"
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                ok = chromium_pdf.html_to_pdf(str(html), str(pdf), lang="ko",
                                              profile=cfg, page_numbers=False)
            self.assertTrue(ok, buf.getvalue())
            doc = pymupdf.open(pdf)
            try:
                rect = doc[0].rect
                self.assertAlmostEqual(rect.width * 25.4 / 72, 210.0, delta=0.6)
                self.assertAlmostEqual(rect.height * 25.4 / 72, 297.0, delta=0.6)
            finally:
                doc.close()


class PrintTocResolutionTests(unittest.TestCase):
    """Page numbers are filled in after a measuring render, so the parsing and
    substitution have to be exactly reversible."""

    HTML = (
        '<html><body>'
        '<nav class="print-toc"><h1 class="print-toc-title">\ubaa9\ucc28</h1>'
        '<ul class="print-toc-list">'
        '<li class="toc-l1"><a href="#sec-2"><span class="toc-text">First</span>'
        '<span class="toc-dots"></span>'
        '<span class="toc-page" data-toc="0">\u00a7\u00a70\u00a7\u00a7</span></a></li>'
        '<li class="toc-l2"><a href="#sec-3"><span class="toc-text">Sub</span>'
        '<span class="toc-dots"></span>'
        '<span class="toc-page" data-toc="1">\u00a7\u00a71\u00a7\u00a7</span></a></li>'
        '</ul></nav>'
        '<h1 id="sec-1" class="title">Doc Title</h1>'
        '<h1 id="sec-2">First</h1><h2 id="sec-3">Sub</h2>'
        '</body></html>'
    )

    def test_parses_entries_in_order(self):
        self.assertEqual(chromium_pdf.parse_toc_entries(self.HTML),
                         [(0, "sec-2"), (1, "sec-3")])

    def test_parses_headings_and_skips_the_document_title(self):
        heads = chromium_pdf.parse_headings(self.HTML)
        self.assertEqual(heads, {"sec-2": (1, "First"), "sec-3": (2, "Sub")})

    def test_headings_exclude_the_toc_nav_itself(self):
        """The nav repeats every title; counting those would map each entry to
        the TOC page."""
        self.assertNotIn("\ubaa9\ucc28",
                         [t for _l, t in chromium_pdf.parse_headings(self.HTML).values()])

    def test_applies_page_numbers(self):
        out = chromium_pdf.apply_toc_pages(self.HTML, {0: 7, 1: 9})
        self.assertIn(">7<", out)
        self.assertIn(">9<", out)
        self.assertNotIn("\u00a7\u00a7", out)

    def test_unresolved_entries_become_blank_not_sentinel(self):
        out = chromium_pdf.apply_toc_pages(self.HTML, {0: 7})
        self.assertNotIn("\u00a7\u00a7", out)
        self.assertIn(">7<", out)

    def test_no_toc_means_no_entries(self):
        self.assertEqual(chromium_pdf.parse_toc_entries("<html><body><p>x</p></body></html>"), [])

    def test_plain_text_unescapes_and_collapses(self):
        self.assertEqual(chromium_pdf._plain_text("<b>A</b>&amp;\n  B"), "A& B")


if __name__ == "__main__":
    unittest.main()

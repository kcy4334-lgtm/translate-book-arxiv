import inspect
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import calibre_html_publish  # noqa: E402

import layout  # noqa: E402

class ConvertHtmlWithCalibreTests(unittest.TestCase):
    def test_builds_expected_epub_command(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_html = Path(temp_dir) / "input.html"
            output_file = Path(temp_dir) / "output.epub"
            input_html.write_text("<html><head><title>Book</title></head></html>", encoding="utf-8")

            def fake_run(cmd, capture_output, text, timeout, **kwargs):
                output_file.write_text("epub", encoding="utf-8")
                return mock.Mock(returncode=0, stderr="")

            with mock.patch.object(
                calibre_html_publish, "find_calibre_convert", return_value="/usr/bin/ebook-convert"
            ), mock.patch.object(
                calibre_html_publish, "extract_html_metadata", return_value=("Book", "Author")
            ), mock.patch.object(
                calibre_html_publish.subprocess, "run", side_effect=fake_run
            ) as run_mock:
                ok = calibre_html_publish.convert_html_with_calibre(
                    str(input_html), str(output_file), "epub", timeout=12, lang="ja"
                )

            self.assertTrue(ok)
            cmd = run_mock.call_args.args[0]
            self.assertEqual(cmd[0], "/usr/bin/ebook-convert")
            self.assertEqual(cmd[1], str(input_html))
            self.assertEqual(cmd[2], str(output_file))
            self.assertIn("--title", cmd)
            self.assertIn("--authors", cmd)
            self.assertIn("--language", cmd)
            self.assertIn("ja", cmd)
            self.assertIn("--epub-version", cmd)
            self.assertIn("3", cmd)
            self.assertNotIn("--disable-font-rescaling", cmd)

    @unittest.skipUnless(
        "cover" in inspect.signature(calibre_html_publish.convert_html_with_calibre).parameters,
        "cover parameter unavailable",
    )
    def test_includes_cover_argument_when_requested(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_html = Path(temp_dir) / "input.html"
            output_file = Path(temp_dir) / "output.epub"
            cover_file = Path(temp_dir) / "cover.jpg"
            input_html.write_text("<html><head><title>Book</title></head></html>", encoding="utf-8")
            cover_file.write_text("img", encoding="utf-8")

            def fake_run(cmd, capture_output, text, timeout, **kwargs):
                output_file.write_text("epub", encoding="utf-8")
                return mock.Mock(returncode=0, stderr="")

            with mock.patch.object(
                calibre_html_publish, "find_calibre_convert", return_value="/usr/bin/ebook-convert"
            ), mock.patch.object(
                calibre_html_publish, "extract_html_metadata", return_value=("Book", "Author")
            ), mock.patch.object(
                calibre_html_publish.subprocess, "run", side_effect=fake_run
            ) as run_mock:
                ok = calibre_html_publish.convert_html_with_calibre(
                    str(input_html),
                    str(output_file),
                    "epub",
                    timeout=12,
                    lang="ja",
                    cover=str(cover_file),
                )

            self.assertTrue(ok)
            cmd = run_mock.call_args.args[0]
            self.assertIn("--cover", cmd)
            self.assertIn(str(cover_file), cmd)


class StyleInjectionTests(unittest.TestCase):
    """The injected block used to land BEFORE the template's own <style>, so
    every rule in it lost the cascade and silently did nothing."""

    def _prepare(self, html):
        with tempfile.TemporaryDirectory() as temp_dir:
            src = Path(temp_dir) / "in.html"
            src.write_text(html, encoding="utf-8")
            work = calibre_html_publish.prepare_html_for_conversion(
                str(src), temp_dir, lang="ko"
            )
            return Path(work).read_text(encoding="utf-8")

    def test_injected_style_lands_after_the_template_style(self):
        out = self._prepare(
            "<html><head><style>BASETEMPLATE</style></head><body>x</body></html>"
        )
        self.assertLess(out.index("BASETEMPLATE"), out.index("font-family"))
        self.assertLess(out.index("font-family"), out.index("</head>"))

    def test_injected_css_sets_no_type_metrics(self):
        """Making a dead stylesheet effective must not silently resize EPUB."""
        out = self._prepare("<html><head></head><body>x</body></html>")
        head = out[: out.index("</head>")]
        self.assertNotIn("font-size", head)
        self.assertNotIn("line-height", head)

    def test_font_family_for_ko_comes_from_layout(self):
        self.assertEqual(
            calibre_html_publish._get_font_family_for_lang("ko"),
            layout.get_lang_config("ko")["font_family_ebook"],
        )

    def test_lang_attr_values_resolve(self):
        """This module is handed 'zh-CN'; LANG_CONFIG is keyed on 'zh'."""
        self.assertEqual(
            calibre_html_publish._get_pdf_font_for_lang("zh-CN"),
            layout.get_lang_config("zh")["pdf_font"],
        )


if __name__ == "__main__":
    unittest.main()

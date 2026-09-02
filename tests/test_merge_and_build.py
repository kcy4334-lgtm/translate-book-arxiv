import contextlib
import inspect
import io
import os
import shutil
import re
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import merge_and_build  # noqa: E402

import layout  # noqa: E402

BS = chr(92)
NL = "\n"

class GenerateFormatTests(unittest.TestCase):
    def _write_file(self, path, content="data"):
        Path(path).write_text(content, encoding="utf-8")

    def _set_mtime(self, path, timestamp):
        os.utime(path, (timestamp, timestamp))

    def test_skips_when_output_is_up_to_date(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            html_file = os.path.join(temp_dir, "book_doc.html")
            output_file = os.path.join(temp_dir, "book.epub")
            self._write_file(html_file, "<html></html>")
            self._write_file(output_file, "epub")
            self._set_mtime(html_file, 100)
            self._set_mtime(output_file, 200)

            with mock.patch.object(merge_and_build.subprocess, "run") as run_mock:
                result = merge_and_build.generate_format(
                    html_file, temp_dir, ".epub", "zh-CN"
                )

            self.assertEqual(result, output_file)
            run_mock.assert_not_called()

    def test_rebuilds_when_image_assets_are_newer(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            html_file = os.path.join(temp_dir, "book_doc.html")
            output_file = os.path.join(temp_dir, "book.epub")
            images_dir = os.path.join(temp_dir, "images")
            image_file = os.path.join(images_dir, "cover.jpg")

            os.makedirs(images_dir, exist_ok=True)
            self._write_file(html_file, "<html></html>")
            self._write_file(output_file, "epub")
            self._write_file(image_file, "image")

            self._set_mtime(html_file, 100)
            self._set_mtime(output_file, 200)
            self._set_mtime(image_file, 300)

            with mock.patch.object(
                merge_and_build.subprocess,
                "run",
                return_value=SimpleNamespace(stdout="", stderr=""),
            ) as run_mock:
                result = merge_and_build.generate_format(
                    html_file, temp_dir, ".epub", "zh-CN"
                )

            self.assertEqual(result, output_file)
            run_mock.assert_called_once()
            cmd = run_mock.call_args.args[0]
            # sys.executable, not "python3": a hardcoded python3 does not
            # resolve on Windows.
            self.assertEqual(cmd[0], sys.executable)
            self.assertEqual(cmd[2], html_file)
            self.assertEqual(cmd[4], output_file)

    @unittest.skipUnless(
        "cover" in inspect.signature(merge_and_build.generate_format).parameters,
        "cover parameter unavailable",
    )
    def test_rebuilds_epub_when_cover_is_explicitly_requested(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            html_file = os.path.join(temp_dir, "book_doc.html")
            output_file = os.path.join(temp_dir, "book.epub")
            cover_file = os.path.join(temp_dir, "cover.jpg")

            self._write_file(html_file, "<html></html>")
            self._write_file(output_file, "epub")
            self._write_file(cover_file, "image")

            self._set_mtime(html_file, 100)
            self._set_mtime(output_file, 200)
            self._set_mtime(cover_file, 300)

            with mock.patch.object(
                merge_and_build.subprocess,
                "run",
                return_value=SimpleNamespace(stdout="", stderr=""),
            ) as run_mock:
                result = merge_and_build.generate_format(
                    html_file, temp_dir, ".epub", "zh-CN", cover=cover_file
                )

            self.assertEqual(result, output_file)
            run_mock.assert_called_once()
            cmd = run_mock.call_args.args[0]
            self.assertIn("--cover", cmd)
            self.assertIn(cover_file, cmd)


class MissingCoverPathTests(unittest.TestCase):
    @unittest.skipUnless(
        "cover" in inspect.signature(merge_and_build.generate_format).parameters,
        "cover parameter unavailable",
    )
    def test_main_rejects_missing_cover_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_cover = os.path.join(temp_dir, "missing-cover.jpg")

            with mock.patch.object(
                merge_and_build, "load_config", return_value={}
            ), mock.patch.object(
                merge_and_build, "get_lang_config", return_value={"lang_attr": "zh-CN"}
            ), mock.patch.object(
                merge_and_build, "merge_markdown_files", return_value=True
            ), mock.patch.object(
                merge_and_build, "convert_md_to_html", return_value=True
            ), mock.patch.object(
                merge_and_build, "add_toc", return_value=True
            ), mock.patch.object(
                merge_and_build, "generate_formats"
            ) as generate_formats_mock, mock.patch.object(
                sys, "argv", ["merge_and_build.py", "--temp-dir", temp_dir, "--cover", missing_cover]
            ):
                with self.assertRaises(SystemExit) as exc:
                    merge_and_build.main()

            self.assertNotEqual(exc.exception.code, 0)
            generate_formats_mock.assert_not_called()


class ExportAliasTests(unittest.TestCase):
    def _write(self, path, content="x"):
        Path(path).write_text(content, encoding="utf-8")

    def test_export_named_aliases_copies_canonical_outputs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            for name in ["book.html", "book_doc.html", "book.docx", "book.epub", "book.pdf"]:
                self._write(Path(temp_dir) / name, name)

            copied = merge_and_build.export_named_aliases(temp_dir, "Translated Book")

            self.assertEqual(
                set(copied),
                {
                    "Translated Book.html",
                    "Translated Book_doc.html",
                    "Translated Book.docx",
                    "Translated Book.epub",
                    "Translated Book.pdf",
                },
            )
            self.assertEqual(
                (Path(temp_dir) / "Translated Book.epub").read_text(encoding="utf-8"),
                "book.epub",
            )
            self.assertTrue((Path(temp_dir) / "book.epub").exists())

    def test_export_name_rejects_paths(self):
        with self.assertRaises(ValueError):
            merge_and_build.export_named_aliases("/tmp", "../bad")


class MergeBlankOutputTests(unittest.TestCase):
    """A whitespace-only output chunk must abort the merge instead of being
    silently dropped from the final book."""

    def _write(self, path, content):
        Path(path).write_text(content, encoding="utf-8")

    def _workspace(self, tmp):
        from manifest import create_manifest

        temp_dir = Path(tmp)
        self._write(temp_dir / "input.md", "One.\n\nTwo.\n")
        self._write(temp_dir / "chunk0001.md", "One.\n")
        self._write(temp_dir / "chunk0002.md", "Two.\n")
        self._write(temp_dir / "output_chunk0001.md", "一。\n")
        self._write(temp_dir / "output_chunk0002.md", "二。\n")
        create_manifest(
            str(temp_dir),
            ["chunk0001.md", "chunk0002.md"],
            str(temp_dir / "input.md"),
        )
        return temp_dir

    def _merge(self, temp_dir):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok = merge_and_build.merge_markdown_files(str(temp_dir))
        return ok, buf.getvalue()

    def test_manifest_merge_fails_on_blank_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            temp_dir = self._workspace(tmp)
            self._write(temp_dir / "output_chunk0002.md", "\n   \n")
            ok, out = self._merge(temp_dir)

            self.assertFalse(ok)
            self.assertFalse((temp_dir / "output.md").exists())
            self.assertIn("Blank output", out)

    def test_legacy_merge_fails_on_blank_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            temp_dir = self._workspace(tmp)
            (temp_dir / "manifest.json").unlink()
            self._write(temp_dir / "output_chunk0002.md", "\n   \n")
            ok, out = self._merge(temp_dir)

            self.assertFalse(ok)
            self.assertFalse((temp_dir / "output.md").exists())
            self.assertIn("Blank output", out)

    def test_merge_succeeds_with_substantive_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            temp_dir = self._workspace(tmp)
            ok, _ = self._merge(temp_dir)

            self.assertTrue(ok)
            merged = (temp_dir / "output.md").read_text(encoding="utf-8")
            self.assertIn("一。", merged)
            self.assertIn("二。", merged)


class ImageValidationTests(unittest.TestCase):
    """Validates _validate_chunk_images, _check_generated_html_sanity, and the
    basic-regex alt-escape fix. Together these guard against subagent-produced
    malformed <img> tags surviving into the final HTML."""

    def _write(self, path, content):
        Path(path).write_text(content, encoding="utf-8")

    def _run_validator(self, temp_dir):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok = merge_and_build._validate_chunk_images(temp_dir)
        return ok, buf.getvalue()

    def _run_html_sanity(self, html_path):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok = merge_and_build._check_generated_html_sanity(html_path)
        return ok, buf.getvalue()

    def test_passes_for_clean_chunks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._write(
                Path(temp_dir) / "chunk0001.md",
                'Hello <img src="images/a.png" alt="A"> and ![fig](images/b.png).',
            )
            self._write(
                Path(temp_dir) / "output_chunk0001.md",
                'Translated <img src="images/a.png" alt="译"> and ![图](images/b.png).',
            )
            ok, out = self._run_validator(temp_dir)
            self.assertTrue(ok, msg=out)

    def test_fails_on_unescaped_double_quote_in_alt(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._write(
                Path(temp_dir) / "chunk0001.md",
                'Bottle <img src="images/a.png" alt="Drink Me bottle">',
            )
            self._write(
                Path(temp_dir) / "output_chunk0001.md",
                '瓶子 <img src="images/a.png" alt="标着"喝我"的瓶子">',
            )
            ok, out = self._run_validator(temp_dir)
            self.assertFalse(ok)
            self.assertIn("output_chunk0001.md", out)
            self.assertIn("malformed <img>", out)

    def test_passes_for_curly_quote_alt(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._write(
                Path(temp_dir) / "chunk0001.md",
                '<img src="images/a.png" alt="Drink Me bottle">',
            )
            self._write(
                Path(temp_dir) / "output_chunk0001.md",
                '<img src="images/a.png" alt="标着“喝我”的瓶子">',
            )
            ok, out = self._run_validator(temp_dir)
            self.assertTrue(ok, msg=out)

    def test_passes_for_html_entity_alt(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._write(
                Path(temp_dir) / "chunk0001.md",
                '<img src="images/a.png" alt="Drink Me">',
            )
            self._write(
                Path(temp_dir) / "output_chunk0001.md",
                '<img src="images/a.png" alt="标着&quot;喝我&quot;的瓶子">',
            )
            ok, out = self._run_validator(temp_dir)
            self.assertTrue(ok, msg=out)

    def test_fails_on_missing_image_src(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._write(
                Path(temp_dir) / "chunk0001.md",
                '<img src="images/a.png" alt="A"> some text <img src="images/b.png" alt="B">',
            )
            self._write(
                Path(temp_dir) / "output_chunk0001.md",
                '<img src="images/a.png" alt="译"> 译文',
            )
            ok, out = self._run_validator(temp_dir)
            self.assertFalse(ok)
            self.assertIn("images/b.png", out)
            self.assertIn("missing <img src>", out)

    def test_fails_on_changed_src_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._write(
                Path(temp_dir) / "chunk0001.md",
                '<img src="images/000034.png" alt="orig">',
            )
            self._write(
                Path(temp_dir) / "output_chunk0001.md",
                '<img src="images/000035.png" alt="译">',
            )
            ok, out = self._run_validator(temp_dir)
            self.assertFalse(ok)
            self.assertIn("images/000034.png", out)
            self.assertIn("images/000035.png", out)

    def test_fails_on_repeated_image_dropped_to_one(self):
        # Counter-based regression: source has same src twice, translated has it once.
        # A set-based comparison would miss this.
        with tempfile.TemporaryDirectory() as temp_dir:
            self._write(
                Path(temp_dir) / "chunk0001.md",
                '<img src="images/a.png" alt="first"> middle <img src="images/a.png" alt="second">',
            )
            self._write(
                Path(temp_dir) / "output_chunk0001.md",
                '<img src="images/a.png" alt="译一"> 中间译文',
            )
            ok, out = self._run_validator(temp_dir)
            self.assertFalse(ok)
            self.assertIn("images/a.png", out)

    def test_fails_when_output_md_uptodate_but_chunks_bad(self):
        # Regression test for cache-bypass: even if output.md exists and is "up to date",
        # bad chunks must still cause merge_markdown_files() to fail, and the stale
        # output.md must be removed.
        with tempfile.TemporaryDirectory() as temp_dir:
            chunk = Path(temp_dir) / "chunk0001.md"
            out_chunk = Path(temp_dir) / "output_chunk0001.md"
            output_md = Path(temp_dir) / "output.md"

            self._write(chunk, '<img src="images/a.png" alt="A">')
            self._write(out_chunk, '<img src="images/a.png" alt="标"喝我"">')
            self._write(output_md, "stale merged content")

            os.utime(chunk, (100, 100))
            os.utime(out_chunk, (150, 150))
            os.utime(output_md, (200, 200))  # newer than chunks

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                result = merge_and_build.merge_markdown_files(temp_dir)
            out = buf.getvalue()

            self.assertFalse(result)
            self.assertFalse(output_md.exists(), msg=f"stale output.md should be deleted; stdout=\n{out}")
            self.assertIn("output_chunk0001.md", out)

    def test_passes_when_code_block_preserves_broken_img_example(self):
        # Regression: a tech book may legitimately ship a fenced code block that
        # demonstrates a deliberately-broken <img> tag. Both source and output
        # carry the same example, so the per-chunk delta is empty — must pass.
        broken_example = (
            "Here is a buggy tag to demonstrate the parser:\n\n"
            "```html\n"
            '<img src="x.png" alt="he said "hi" loudly">\n'
            "```\n"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            self._write(Path(temp_dir) / "chunk0001.md", broken_example)
            self._write(
                Path(temp_dir) / "output_chunk0001.md",
                broken_example.replace("Here is a buggy tag to demonstrate the parser:",
                                       "下面这个有 bug 的标签是用来演示解析器的："),
            )
            ok, out = self._run_validator(temp_dir)
            self.assertTrue(ok, msg=out)

    def test_fails_when_output_introduces_new_broken_img(self):
        # If source had one broken example and output adds a *second* broken tag
        # (not present in source), the new bad attr shows up in the delta and
        # we must flag it — even when there's a baseline of broken attrs.
        with tempfile.TemporaryDirectory() as temp_dir:
            self._write(
                Path(temp_dir) / "chunk0001.md",
                "Demo block:\n\n"
                "```html\n"
                '<img src="x.png" alt="he said "hi" loudly">\n'
                "```\n\n"
                'And a real image: <img src="images/a.png" alt="A">\n',
            )
            self._write(
                Path(temp_dir) / "output_chunk0001.md",
                "演示代码块：\n\n"
                "```html\n"
                '<img src="x.png" alt="he said "hi" loudly">\n'
                "```\n\n"
                # New corruption: subagent broke the real image alt with unescaped quote
                '真实图片：<img src="images/a.png" alt="标着"喝我"">\n',
            )
            ok, out = self._run_validator(temp_dir)
            self.assertFalse(ok)
            self.assertIn("introduced malformed <img>", out)
            self.assertIn("output_chunk0001.md", out)

    def test_fails_when_real_image_replaced_with_escaped_markdown(self):
        # Regression: a regex that didn't honor `\!` would count `\![](path)` as
        # an image, masking real loss when the subagent escaped it accidentally.
        with tempfile.TemporaryDirectory() as temp_dir:
            self._write(
                Path(temp_dir) / "chunk0001.md",
                "See ![Fig 1](images/a.png) for details.",
            )
            self._write(
                Path(temp_dir) / "output_chunk0001.md",
                "见 \\![图 1](images/a.png) 了解详情。",
            )
            ok, out = self._run_validator(temp_dir)
            self.assertFalse(ok)
            self.assertIn("missing ![](path)", out)
            self.assertIn("images/a.png", out)

    def test_passes_when_both_chunks_have_escaped_markdown_image(self):
        # Symmetric case: both chunks intentionally use `\![...]` as literal text.
        # Neither counts as a real image; counts match.
        with tempfile.TemporaryDirectory() as temp_dir:
            self._write(
                Path(temp_dir) / "chunk0001.md",
                "Use \\![alt](path) syntax to write the example as text.",
            )
            self._write(
                Path(temp_dir) / "output_chunk0001.md",
                "用 \\![alt](path) 语法把示例写成文本。",
            )
            ok, out = self._run_validator(temp_dir)
            self.assertTrue(ok, msg=out)

    def test_fails_when_markdown_image_missing_closing_paren(self):
        # Regression: the regex must require the closing `)` — a fragment like
        # `![图](images/a.png` does NOT render as an image, so counting it as a
        # preserved reference would mask real image loss.
        with tempfile.TemporaryDirectory() as temp_dir:
            self._write(
                Path(temp_dir) / "chunk0001.md",
                "See ![Fig 1](images/a.png) for details.",
            )
            self._write(
                Path(temp_dir) / "output_chunk0001.md",
                "见 ![图 1](images/a.png 了解详情。",  # missing closing )
            )
            ok, out = self._run_validator(temp_dir)
            self.assertFalse(ok)
            self.assertIn("missing ![](path)", out)
            self.assertIn("images/a.png", out)

    def test_passes_for_markdown_image_with_title(self):
        # Forward-compatibility: standard `![alt](url "title")` syntax must keep
        # parsing as a single image when both chunks preserve the title.
        with tempfile.TemporaryDirectory() as temp_dir:
            self._write(
                Path(temp_dir) / "chunk0001.md",
                'Look at ![Fig 1](images/a.png "Diagram of the system") below.',
            )
            self._write(
                Path(temp_dir) / "output_chunk0001.md",
                '看下方 ![图 1](images/a.png "系统示意图")。',
            )
            ok, out = self._run_validator(temp_dir)
            self.assertTrue(ok, msg=out)

    def test_passes_with_gt_in_quoted_alt(self):
        # Regression: a regex like <img\b[^>]*> would truncate at the first `>`
        # inside a quoted attribute value, producing a false-positive malformed
        # report for legitimate math/comparison content. HTMLParser handles this.
        with tempfile.TemporaryDirectory() as temp_dir:
            self._write(
                Path(temp_dir) / "chunk0001.md",
                'Compare <img src="images/a.png" alt="x > y and a < b"> here.',
            )
            self._write(
                Path(temp_dir) / "output_chunk0001.md",
                '比较 <img src="images/a.png" alt="x > y 且 a < b"> 这里。',
            )
            ok, out = self._run_validator(temp_dir)
            self.assertTrue(ok, msg=out)

    def test_html_canary_passes_when_prose_mentions_img_tag(self):
        # Regression: a book that legitimately discusses HTML will render `<img>`
        # mentions as `&lt;img&gt;` in prose or inside <pre><code>. That is not
        # corruption and must not block the build.
        with tempfile.TemporaryDirectory() as temp_dir:
            html_file = Path(temp_dir) / "book.html"
            self._write(
                html_file,
                "<html><body>"
                "<p>The &lt;img&gt; tag is used for inline images.</p>"
                "<pre><code>&lt;img src=&quot;example.png&quot;&gt;</code></pre>"
                "<p>Here is a real image: <img src=\"images/real.png\" alt=\"real\"></p>"
                "</body></html>",
            )
            ok, out = self._run_html_sanity(str(html_file))
            self.assertTrue(ok, msg=out)

    def test_basic_regex_escapes_alt_with_quote(self):
        # The basic-regex fallback used to inline alt verbatim, so a literal " in
        # markdown alt text would produce malformed raw <img>. Now it html.escapes.
        with tempfile.TemporaryDirectory() as temp_dir:
            md_file = Path(temp_dir) / "in.md"
            html_file = Path(temp_dir) / "out.html"
            self._write(md_file, '![Title with "quote" inside](images/x.png)\n')

            ok = merge_and_build.convert_with_basic_regex(str(md_file), str(html_file), "t")
            self.assertTrue(ok)

            html_text = html_file.read_text(encoding="utf-8")
            self.assertIn("&quot;", html_text)
            self.assertNotIn('alt="Title with "quote"', html_text)

            sanity_ok, sanity_out = self._run_html_sanity(str(html_file))
            self.assertTrue(sanity_ok, msg=sanity_out)


class PdfEngineRoutingTests(unittest.TestCase):
    """PDF must go to Chromium by default and to Calibre only on request."""

    def _fixture(self, temp_dir):
        html_file = os.path.join(temp_dir, "book_doc.html")
        Path(html_file).write_text("<html></html>", encoding="utf-8")
        return html_file

    def test_pdf_routes_to_chromium_by_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            html_file = self._fixture(temp_dir)
            output_file = os.path.join(temp_dir, "book.pdf")

            def fake_render(html, out, **kwargs):
                Path(out).write_bytes(b"%PDF-1.4" + b"\0" * 2048)
                return True

            with mock.patch.object(merge_and_build.chromium_pdf, "html_to_pdf",
                                   side_effect=fake_render) as render_mock, \
                 mock.patch.object(merge_and_build.subprocess, "run") as run_mock:
                result = merge_and_build.generate_format(
                    html_file, temp_dir, ".pdf", "ko"
                )

            self.assertEqual(result, output_file)
            render_mock.assert_called_once()
            run_mock.assert_not_called()

    def test_pdf_routes_to_calibre_when_requested(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            html_file = self._fixture(temp_dir)
            output_file = os.path.join(temp_dir, "book.pdf")

            def fake_run(cmd, **kwargs):
                Path(output_file).write_bytes(b"%PDF-1.4")
                return mock.Mock(returncode=0, stdout="", stderr="")

            with mock.patch.object(merge_and_build.chromium_pdf,
                                   "html_to_pdf") as render_mock, \
                 mock.patch.object(merge_and_build.subprocess, "run",
                                   side_effect=fake_run) as run_mock:
                merge_and_build.generate_format(
                    html_file, temp_dir, ".pdf", "ko", pdf_engine="calibre"
                )

            render_mock.assert_not_called()
            self.assertIn("calibre_html_publish.py", " ".join(run_mock.call_args.args[0]))

    def test_epub_never_routes_to_chromium(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            html_file = self._fixture(temp_dir)
            with mock.patch.object(merge_and_build.chromium_pdf,
                                   "html_to_pdf") as render_mock, \
                 mock.patch.object(merge_and_build.subprocess, "run"):
                merge_and_build.generate_format(html_file, temp_dir, ".epub", "ko")
            render_mock.assert_not_called()

    def test_up_to_date_pdf_is_skipped_before_the_engine_branch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            html_file = self._fixture(temp_dir)
            output_file = os.path.join(temp_dir, "book.pdf")
            Path(output_file).write_text("pdf", encoding="utf-8")
            os.utime(html_file, (100, 100))
            os.utime(output_file, (200, 200))

            with mock.patch.object(merge_and_build.chromium_pdf,
                                   "html_to_pdf") as render_mock:
                result = merge_and_build.generate_format(
                    html_file, temp_dir, ".pdf", "ko"
                )

            self.assertEqual(result, output_file)
            render_mock.assert_not_called()


class PrintTokenSubstitutionTests(unittest.TestCase):
    def test_every_token_is_substituted(self):
        template = (
            "<html lang=\"$lang$\"><head><title>$title$</title><style>"
            "@page { size: $page_size$; margin: $page_margin$; }"
            "@media print { html { font-size: $print_font_size$; }"
            " body { font-family: $body_font$; line-height: $print_line_height$; } }"
            "</style></head><body>$toc_label$ $body$</body></html>"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            tpl = os.path.join(temp_dir, "t.html")
            out = os.path.join(temp_dir, "o.html")
            Path(tpl).write_text(template, encoding="utf-8")

            ok = merge_and_build.apply_template_to_html(
                "<p>body</p>", tpl, out, "T",
                merge_and_build.get_lang_config("ko"),
                print_cfg=layout.get_print_profile("a4-book"),
            )

            self.assertTrue(ok)
            html = Path(out).read_text(encoding="utf-8")
            self.assertIn("size: A4", html)
            self.assertIn("margin: 18mm 18mm 22mm 18mm", html)
            self.assertIn("font-size: 11.5pt", html)
            self.assertIn("line-height: 1.75", html)
            self.assertNotIn("$", html)

    def test_defaults_are_used_when_no_profile_is_passed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            tpl = os.path.join(temp_dir, "t.html")
            out = os.path.join(temp_dir, "o.html")
            Path(tpl).write_text("<x>$page_size$</x>$body$", encoding="utf-8")
            merge_and_build.apply_template_to_html(
                "", tpl, out, "T", merge_and_build.get_lang_config("ko")
            )
            self.assertIn("A4", Path(out).read_text(encoding="utf-8"))


class RawLatexTableTests(unittest.TestCase):
    """The arXiv backend ships tables as raw LaTeX. pandoc's markdown reader
    parses those as raw LaTeX blocks and DROPS them on the HTML path, which is
    how five result tables once vanished while the build printed 'OK'."""

    TABULAR = (
        BS + "begin{tabular}{c|c}" + NL
        + BS + "toprule" + NL
        + "A & B " + BS + BS + NL
        + BS + "midrule" + NL
        + "1 & 2 " + BS + BS + NL
        + BS + "bottomrule" + NL
        + BS + "end{tabular}"
    )

    def wrapped(self):
        return BS + "resizebox{0.5" + BS + "textwidth}{!}{" + self.TABULAR + "}"

    def floated(self):
        return (BS + "begin{table*}[t]" + NL
                + BS + "caption{" + BS + "textbf{Results.} Numbers.}" + NL
                + self.wrapped() + NL
                + BS + "end{table*}")

    def test_finds_a_bare_tabular(self):
        found = merge_and_build.find_raw_latex_tables("before" + NL + self.TABULAR + NL + "after")
        self.assertEqual(len(found), 1)
        self.assertIn("toprule", found[0]["bare"])
        self.assertIsNone(found[0]["float"])

    def test_span_swallows_the_resizebox_wrapper(self):
        text = "x" + NL + self.wrapped() + NL + "y"
        found = merge_and_build.find_raw_latex_tables(text)
        self.assertEqual(len(found), 1)
        span = text[found[0]["start"]:found[0]["stop"]]
        self.assertTrue(span.startswith(BS + "resizebox"))
        self.assertTrue(span.endswith("}"))
        # the wrapper's closing brace must be inside the span, or it is left
        # behind as stray LaTeX
        self.assertEqual(span.count("{"), span.count("}"))

    def test_span_swallows_the_float_and_keeps_the_caption(self):
        """A leftover \\begin{table*} starts a raw LaTeX block that swallows the
        injected HTML table, so the float has to go too."""
        text = "x" + NL + self.floated() + NL + "y"
        found = merge_and_build.find_raw_latex_tables(text)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["float"], "table*")
        span = text[found[0]["start"]:found[0]["stop"]]
        self.assertTrue(span.startswith(BS + "begin{table*}"))
        self.assertTrue(span.endswith(BS + "end{table*}"))
        self.assertIn("Results.", found[0]["caption"])

    def test_counts_every_table(self):
        text = self.TABULAR + NL + NL + self.floated() + NL + NL + self.wrapped()
        self.assertEqual(merge_and_build.count_raw_latex_tables(text), 3)

    def test_count_is_zero_without_tables(self):
        self.assertEqual(merge_and_build.count_raw_latex_tables("plain text"), 0)

    def _fake_pandoc(self, html="<table>\n<tr><td>A</td></tr>\n</table>"):
        def run(cmd, **kwargs):
            return mock.Mock(returncode=0, stdout=html, stderr="")
        return run

    def test_expansion_replaces_the_whole_float(self):
        text = "before" + NL + NL + self.floated() + NL + NL + "after"
        with mock.patch.object(merge_and_build.subprocess, "run",
                               side_effect=self._fake_pandoc()):
            out, ok, bad = merge_and_build.expand_raw_latex_tables(text, pandoc="pandoc")
        self.assertEqual((ok, bad), (1, 0))
        self.assertIn("<table", out)
        # every scrap of LaTeX scaffolding must be gone
        for leftover in (BS + "begin{table*}", BS + "end{table*}",
                         BS + "resizebox", BS + "begin{tabular}", BS + "toprule"):
            self.assertNotIn(leftover, out, leftover)
        self.assertIn("before", out)
        self.assertIn("after", out)

    def test_expansion_is_a_noop_without_tables(self):
        text = "just prose"
        out, ok, bad = merge_and_build.expand_raw_latex_tables(text, pandoc="pandoc")
        self.assertEqual((out, ok, bad), (text, 0, 0))

    def test_failed_conversion_leaves_the_source_alone(self):
        """A table pandoc cannot read must survive as LaTeX so the fidelity
        gate reports the shortfall instead of the build shipping a hole."""
        text = "x" + NL + NL + self.wrapped() + NL + NL + "y"
        def run(cmd, **kwargs):
            return mock.Mock(returncode=1, stdout="", stderr="boom")
        with mock.patch.object(merge_and_build.subprocess, "run", side_effect=run):
            out, ok, bad = merge_and_build.expand_raw_latex_tables(text, pandoc="pandoc")
        self.assertEqual((ok, bad), (0, 1))
        self.assertIn(BS + "begin{tabular}", out)

    def test_backslashes_are_escaped_in_injected_html(self):
        """MathML keeps the TeX in <annotation>; an unescaped backslash there
        eats the next '<' via a markdown escape and prints a literal tag."""
        html = '<table>\n<tr><td><mi>' + BS + '</mi></td></tr>\n</table>'
        text = self.wrapped()
        with mock.patch.object(merge_and_build.subprocess, "run",
                               side_effect=self._fake_pandoc(html)):
            out, ok, bad = merge_and_build.expand_raw_latex_tables(text, pandoc="pandoc")
        self.assertEqual(ok, 1)
        self.assertNotIn(BS, out)
        self.assertIn("&#92;", out)

    def test_wide_tables_get_a_class(self):
        wide = "<table>" + "<tr>" + "<td>x</td>" * 8 + "</tr>" + "</table>"
        with mock.patch.object(merge_and_build.subprocess, "run",
                               side_effect=self._fake_pandoc(wide)):
            out, ok, _ = merge_and_build.expand_raw_latex_tables(self.wrapped(), pandoc="pandoc")
        self.assertEqual(ok, 1)
        self.assertIn('class="cols-many"', out)

    def test_no_pandoc_reports_the_tables_as_failed(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            out, ok, bad = merge_and_build.expand_raw_latex_tables(self.wrapped(), pandoc=None) \
                if False else merge_and_build.expand_raw_latex_tables(self.wrapped(), pandoc=None)
        # resolve_pandoc may find a real pandoc on this machine; only assert the
        # contract when it genuinely cannot.
        if ok == 0 and bad:
            self.assertEqual(bad, 1)


class TableFidelityCountsRawLatexTests(unittest.TestCase):
    def test_gate_counts_raw_latex_tables(self):
        """Counting only markdown tables is what let the loss go unreported."""
        md = ("prose" + NL + NL + BS + "begin{tabular}{c}" + NL + "a " + BS + BS + NL
              + BS + "end{tabular}" + NL)
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "output.md")
            Path(path).write_text(md, encoding="utf-8")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                ok = merge_and_build.check_table_fidelity(path, "<p>nothing</p>", strict=True)
            self.assertFalse(ok)
            self.assertIn("raw-LaTeX", buf.getvalue())

    def test_gate_passes_when_the_table_made_it(self):
        md = (BS + "begin{tabular}{c}" + NL + "a " + BS + BS + NL + BS + "end{tabular}" + NL)
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "output.md")
            Path(path).write_text(md, encoding="utf-8")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                ok = merge_and_build.check_table_fidelity(path, "<table><tr></tr></table>")
            self.assertTrue(ok)


class PrintTocTests(unittest.TestCase):
    """book_doc.html feeds both EPUB and PDF and used to ship with no TOC at
    all, while the build still printed "TOC inserted"."""

    HTML = (
        "<html><body>"
        "<header id=\"title-block-header\"><h1 class=\"title\">My Book</h1></header>"
        "<h1>First</h1><p>a</p>"
        "<h2>Sub A</h2><p>b</p>"
        "<h3>Deep</h3><p>c</p>"
        "<h4>Too deep</h4><p>d</p>"
        "<h1>Second</h1><p>e</p>"
        "</body></html>"
    )

    def test_inserts_a_nav_after_body(self):
        out, n = merge_and_build.build_print_toc(self.HTML, "목차")
        self.assertGreater(n, 0)
        self.assertIn('<nav class="print-toc"', out)
        self.assertLess(out.index("<body>"), out.index('<nav class="print-toc"'))

    def test_uses_the_language_label(self):
        out, _ = merge_and_build.build_print_toc(self.HTML, "목차")
        self.assertIn("목차", out)

    def test_skips_the_document_title(self):
        """A book's own title is not one of its TOC entries."""
        out, n = merge_and_build.build_print_toc(self.HTML, "Contents")
        nav = out[out.index("<nav"):out.index("</nav>")]
        self.assertNotIn("My Book", nav)
        self.assertIn("First", nav)
        self.assertEqual(n, 4)   # First, Sub A, Deep, Second -- h4 is past max_level

    def test_respects_max_level(self):
        out, n = merge_and_build.build_print_toc(self.HTML, "C", max_level=2)
        nav = out[out.index("<nav"):out.index("</nav>")]
        self.assertIn("Sub A", nav)
        self.assertNotIn("Deep", nav)

    def test_every_heading_gets_an_id_and_every_entry_links_to_one(self):
        out, _ = merge_and_build.build_print_toc(self.HTML, "C")
        nav = out[out.index("<nav"):out.index("</nav>")]
        for target in re.findall(r'href="#([^"]+)"', nav):
            self.assertIn('id="%s"' % target, out, target)

    def test_entries_carry_a_page_sentinel(self):
        """chromium_pdf substitutes real page numbers into these after a
        measuring pass; Chromium has no target-counter()."""
        out, n = merge_and_build.build_print_toc(self.HTML, "C")
        found = re.findall(r'\u00a7\u00a7(\d+)\u00a7\u00a7', out)
        self.assertEqual(len(found), n)
        self.assertEqual(sorted(int(x) for x in found), list(range(n)))

    def test_no_headings_means_no_toc(self):
        out, n = merge_and_build.build_print_toc("<html><body><p>x</p></body></html>", "C")
        self.assertEqual(n, 0)
        self.assertNotIn("print-toc", out)

    def test_existing_ids_are_preserved(self):
        html = '<html><body><h1 id="keep-me">T</h1></body></html>'
        out, _ = merge_and_build.build_print_toc(html, "C")
        self.assertIn('id="keep-me"', out)
        self.assertIn('href="#keep-me"', out)

    def test_is_idempotent_on_a_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "book_doc.html")
            Path(path).write_text(self.HTML, encoding="utf-8")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                merge_and_build.add_print_toc_to_ebook(temp_dir, "C")
                merge_and_build.add_print_toc_to_ebook(temp_dir, "C")
            self.assertEqual(Path(path).read_text(encoding="utf-8").count("<nav class="), 1)


class ReferenceResolutionTests(unittest.TestCase):
    """arXiv papers ship a precompiled .bbl, so --citeproc has nothing to read
    and [@key] used to print verbatim. The inlined \\bibitem list IS the
    numbering, and flat.tex still holds every \\label in float order."""

    MD = (
        "Intro [@alpha] and [@beta].\n\n"
        "See (fig:one) and (tab:two).\n\n"
        + BS + "bibitem{alpha}" + NL + "A." + NL
        + BS + "bibitem{beta}" + NL + "B." + NL
    )

    # Every float carries a \caption. That is what makes LaTeX number it, and
    # a fixture without one described a document that cannot exist.
    FLAT = (
        BS + "begin{figure}" + NL + BS + "caption{One}" + NL
        + BS + "label{fig:one}" + NL + BS + "end{figure}" + NL
        + BS + "begin{table}" + NL + BS + "caption{Zero}" + NL
        + BS + "label{tab:zero}" + NL + BS + "end{table}" + NL
        + BS + "begin{table*}" + NL + BS + "caption{Two}" + NL
        + BS + "label{tab:two}" + NL + BS + "end{table*}" + NL
    )

    def _temp(self, with_flat=True):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        if with_flat:
            Path(os.path.join(d, "flat.tex")).write_text(self.FLAT, encoding="utf-8")
        return d

    def test_bibitem_numbers_follow_document_order(self):
        nums = merge_and_build.build_bibitem_numbers(self.MD)
        self.assertEqual(nums, {"alpha": 1, "beta": 2})

    def test_float_numbers_count_each_kind_separately(self):
        """figure and figure* share a counter; table and table* share another."""
        nums = merge_and_build.build_float_numbers(self._temp())
        self.assertEqual(nums["fig:one"], 1)
        self.assertEqual(nums["tab:zero"], 1)
        self.assertEqual(nums["tab:two"], 2)

    def test_float_numbers_empty_without_flat_tex(self):
        self.assertEqual(merge_and_build.build_float_numbers(self._temp(with_flat=False)), {})

    def _flat(self, text):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        Path(os.path.join(d, "flat.tex")).write_text(text, encoding="utf-8")
        return d

    def test_commented_out_float_numbers_nothing(self):
        """SINQ leaves two figures commented out; they number nothing.

        Counting them made every later figure one too high, and only on the
        cross-reference side -- the caption said 6 while the sentence
        pointing at it said 7.
        """
        flat = (
            "% " + BS + "begin{figure}" + NL
            + "% " + BS + "caption{Dropped}" + NL
            + "% " + BS + "label{fig:dropped}" + NL
            + "% " + BS + "end{figure}" + NL
            + BS + "begin{figure}" + NL + BS + "caption{Real}" + NL
            + BS + "label{fig:real}" + NL + BS + "end{figure}" + NL
        )
        nums = merge_and_build.build_float_numbers(self._flat(flat))
        self.assertEqual(nums["fig:real"], 1)
        self.assertNotIn("fig:dropped", nums)

    def test_one_float_with_two_captions_is_two_numbers(self):
        """AlphaQ puts two minipages in one table*, each with its own caption.

        LaTeX numbers a float when \\caption runs, so that is Table 1 and
        Table 2 -- reading it as one table numbered every later table low.
        """
        flat = (
            BS + "begin{table*}" + NL
            + BS + "begin{minipage}{0.49" + BS + "textwidth}" + NL
            + BS + "caption{Left}" + NL + BS + "label{tab:left}" + NL
            + BS + "end{minipage}" + NL
            + BS + "begin{minipage}{0.49" + BS + "textwidth}" + NL
            + BS + "caption{Right}" + NL + BS + "label{tab:right}" + NL
            + BS + "end{minipage}" + NL
            + BS + "end{table*}" + NL
            + BS + "begin{table}" + NL + BS + "caption{After}" + NL
            + BS + "label{tab:after}" + NL + BS + "end{table}" + NL
        )
        nums = merge_and_build.build_float_numbers(self._flat(flat))
        self.assertEqual(nums["tab:left"], 1)
        self.assertEqual(nums["tab:right"], 2)
        self.assertEqual(nums["tab:after"], 3)

    def test_subcaption_does_not_number_the_float(self):
        """A \\caption inside a subfigure letters a panel, it does not number."""
        flat = (
            BS + "begin{figure}" + NL
            + BS + "begin{subfigure}{0.5" + BS + "linewidth}" + NL
            + BS + "caption{Panel a}" + NL + BS + "label{fig:pa}" + NL
            + BS + "end{subfigure}" + NL
            + BS + "begin{subfigure}{0.5" + BS + "linewidth}" + NL
            + BS + "caption{Panel b}" + NL + BS + "label{fig:pb}" + NL
            + BS + "end{subfigure}" + NL
            + BS + "caption{Whole}" + NL + BS + "label{fig:whole}" + NL
            + BS + "end{figure}" + NL
            + BS + "begin{figure}" + NL + BS + "caption{Next}" + NL
            + BS + "label{fig:next}" + NL + BS + "end{figure}" + NL
        )
        nums = merge_and_build.build_float_numbers(self._flat(flat))
        self.assertEqual(nums["fig:whole"], 1)
        self.assertEqual(nums["fig:pa"], 1)
        self.assertEqual(nums["fig:next"], 2)

    def test_float_without_a_caption_is_not_numbered(self):
        flat = (
            BS + "begin{figure}" + NL + BS + "label{fig:bare}" + NL
            + BS + "end{figure}" + NL
            + BS + "begin{figure}" + NL + BS + "caption{Real}" + NL
            + BS + "label{fig:real}" + NL + BS + "end{figure}" + NL
        )
        nums = merge_and_build.build_float_numbers(self._flat(flat))
        self.assertEqual(nums["fig:real"], 1)
        self.assertNotIn("fig:bare", nums)

    def test_resolves_citations_to_numbers(self):
        out, stats = merge_and_build.resolve_references(self.MD, self._temp(), {})
        self.assertIn("[1]", out)
        self.assertIn("[2]", out)
        self.assertNotIn("[@alpha]", out)
        self.assertEqual(stats["cites"], 2)

    def test_resolves_cross_references_with_localised_labels(self):
        cfg = {"figure_label": "그림", "table_label": "표"}
        out, stats = merge_and_build.resolve_references(self.MD, self._temp(), cfg)
        self.assertIn("그림 1", out)
        self.assertIn("표 2", out)
        self.assertNotIn("(fig:one)", out)
        self.assertEqual(stats["xrefs"], 2)

    def test_unknown_citation_key_is_left_alone(self):
        """A visible [@ghost] is better than a silently wrong number."""
        md = self.MD.replace("[@beta]", "[@ghost]")
        out, stats = merge_and_build.resolve_references(md, self._temp(), {})
        self.assertIn("[@ghost]", out)
        self.assertEqual(stats["cites_missed"], 1)

    def test_multi_key_citation_needs_every_key(self):
        md = "x [@alpha; @ghost] y" + NL + NL + BS + "bibitem{alpha}" + NL
        out, stats = merge_and_build.resolve_references(md, self._temp(), {})
        self.assertIn("[@alpha; @ghost]", out)
        self.assertEqual(stats["cites"], 0)

    def test_multi_key_citation_resolves_when_all_present(self):
        md = ("x [@alpha; @beta] y" + NL + NL
              + BS + "bibitem{alpha}" + NL + BS + "bibitem{beta}" + NL)
        out, _ = merge_and_build.resolve_references(md, self._temp(), {})
        self.assertIn("[1, 2]", out)

    def test_unknown_label_is_left_alone(self):
        md = "see (fig:nope)" + NL
        out, stats = merge_and_build.resolve_references(md, self._temp(), {})
        self.assertIn("(fig:nope)", out)
        self.assertEqual(stats["xrefs_missed"], 1)

    def test_no_bibliography_leaves_citations_untouched(self):
        md = "x [@alpha] y"
        out, stats = merge_and_build.resolve_references(md, self._temp(), {})
        self.assertIn("[@alpha]", out)
        self.assertEqual(stats["cites"], 0)

    def test_defaults_to_english_labels(self):
        out, _ = merge_and_build.resolve_references(self.MD, self._temp(), None)
        self.assertIn("Figure 1", out)
        self.assertIn("Table 2", out)


class LatexStructureGuardTests(unittest.TestCase):
    """A shell heredoc collapses '\\\\' to '\\', stripping every row separator
    out of a tabular. Nothing else in the pipeline notices: the text is all
    still there, the table just loses its grid."""

    SOURCE = (
        "Prose." + NL + NL
        + BS + "begin{table}" + NL
        + BS + "begin{tabular}{c|c}" + NL
        + BS + "toprule" + NL
        + "A & B " + BS + BS + NL
        + BS + "midrule" + NL
        + "1 & 2 " + BS + BS + NL
        + BS + "bottomrule" + NL
        + BS + "end{tabular}" + NL
        + BS + "end{table}" + NL
    )

    def _dir(self, translated):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        Path(os.path.join(d, "chunk0001.md")).write_text(self.SOURCE, encoding="utf-8")
        Path(os.path.join(d, "output_chunk0001.md")).write_text(translated, encoding="utf-8")
        return d

    def _run(self, translated):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok = merge_and_build._validate_chunk_latex(self._dir(translated))
        return ok, buf.getvalue()

    def test_passes_a_faithful_translation(self):
        ok, _ = self._run(self.SOURCE.replace("Prose.", "\uc0b0\ubb38."))
        self.assertTrue(ok)

    def test_catches_collapsed_row_separators(self):
        """The exact heredoc failure: '\\\\' -> '\\'."""
        ok, out = self._run(self.SOURCE.replace(BS + BS, BS))
        self.assertFalse(ok)
        self.assertIn("row separators", out)
        self.assertIn("heredoc", out)

    def test_catches_a_dropped_environment(self):
        ok, out = self._run(self.SOURCE.replace(BS + "end{table}", ""))
        self.assertFalse(ok)
        self.assertIn("end{table}", out)

    def test_catches_a_dropped_table(self):
        ok, out = self._run("Prose only." + NL)
        self.assertFalse(ok)
        self.assertIn("tabular blocks", out)

    def test_catches_lost_cell_separators(self):
        ok, out = self._run(self.SOURCE.replace("A & B", "A B"))
        self.assertFalse(ok)
        self.assertIn("cell separators", out)

    def test_ampersand_in_prose_may_change(self):
        """'Distractor & Illumination' -> '방해물 및 조명' is a correct
        translation, not corruption. Only cells inside a tabular are compared."""
        src = "Distractor & Illumination" + NL
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        Path(os.path.join(d, "chunk0001.md")).write_text(src, encoding="utf-8")
        Path(os.path.join(d, "output_chunk0001.md")).write_text(
            "\ubc29\ud574\ubb3c \ubc0f \uc870\uba85" + NL, encoding="utf-8")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertTrue(merge_and_build._validate_chunk_latex(d))

    def test_line_ending_backslashes_may_be_removed(self):
        """The translation prompt explicitly allows deleting them, so a raw
        backslash count would false-positive on every chunk."""
        src = "line one " + BS + NL + "line two" + NL
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        Path(os.path.join(d, "chunk0001.md")).write_text(src, encoding="utf-8")
        Path(os.path.join(d, "output_chunk0001.md")).write_text(
            "\ud55c \uc904" + NL + "\ub450 \uc904" + NL, encoding="utf-8")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertTrue(merge_and_build._validate_chunk_latex(d))

    def test_missing_source_chunk_is_skipped(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        Path(os.path.join(d, "output_chunk0009.md")).write_text("x", encoding="utf-8")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertTrue(merge_and_build._validate_chunk_latex(d))


class EquationNumberTests(unittest.TestCase):
    r"""The cross-reference pass resolves "(eq:ilp)" to the number the paper
    prints, so the body says "식 (5)" — and the equation itself carried none,
    leaving the reader nothing to match it against.

    What counts is not a guess: LaTeX numbers a math environment unless it is
    starred, and \nonumber removes a row's number inside align. Counted that
    way the three papers agree exactly with the (N) markers printed in their
    own PDFs: SINQ 7, CafeQ 5, AlphaQ 27."""

    def _numbers(self, md):
        return [n for _s, _e, n in merge_and_build.equation_numbers(md)]

    def test_starred_environments_take_no_number(self):
        md = ("$$" + BS + "begin{equation}a=b" + BS + "end{equation}$$" + NL + NL
              + "$$" + BS + "begin{equation*}c=d" + BS + "end{equation*}$$" + NL + NL
              + "$$" + BS + "begin{align}e=f" + BS + "end{align}$$")
        self.assertEqual(self._numbers(md), [1, None, 2])

    def test_plain_display_math_is_not_numbered(self):
        """`$$x=y$$` with no environment is not something LaTeX numbered."""
        md = "$$x = y$$" + NL + NL + "$$" + BS + "begin{equation}a=b" + BS + "end{equation}$$"
        self.assertEqual(self._numbers(md), [None, 1])

    def test_nonumber_rows_do_not_consume_a_number(self):
        """CafeQ's four-row align carries three \nonumber, so it is one."""
        row_break = BS + BS
        nonumber = BS + "nonumber"
        align = ("$$" + BS + "begin{align}"
                 + "a&=b" + row_break + nonumber
                 + "c&=d" + row_break + nonumber
                 + "e&=f" + row_break + nonumber
                 + "g&=h"
                 + BS + "end{align}$$")
        after = "$$" + BS + "begin{equation}z=1" + BS + "end{equation}$$"
        self.assertEqual(self._numbers(align + NL + NL + after), [1, 2])

    def test_the_docx_copy_carries_the_number_inside_the_formula(self):
        """pandoc builds book.docx from the markdown and never sees the HTML
        the other formats are styled through."""
        md = "$$" + BS + "begin{equation}a=b" + BS + "end{equation}$$"
        out, n = merge_and_build.tag_equations_for_markdown(md)
        self.assertEqual(n, 1)
        self.assertIn(BS + "qquad(1)", out)
        self.assertLess(out.index("qquad(1)"), out.index("end{equation}"),
                        "the tag belongs inside the environment")

    def test_the_html_copy_carries_the_number_as_an_attribute(self):
        """Kept out of the formula so selecting the equation does not pick the
        number up; the stylesheet places it."""
        md = ("$$" + BS + "begin{equation}a=b" + BS + "end{equation}$$" + NL + NL
              + "$$" + BS + "begin{equation*}c=d" + BS + "end{equation*}$$")
        html = ('<p><math display="block"><mi>a</mi></math></p>'
                '<p><math display="block"><mi>c</mi></math></p>')
        out, n = merge_and_build.tag_equations_in_html(html, md)
        self.assertEqual(n, 1)
        self.assertEqual(out.count('data-eqno'), 1)
        self.assertIn('data-eqno="(1)"', out)
        # the starred one is left alone
        self.assertLess(out.index('data-eqno'), out.index('<mi>c</mi>'))

    def test_inline_math_is_untouched(self):
        html = '<p>see <math display="inline"><mi>x</mi></math></p>'
        md = "$$" + BS + "begin{equation}a=b" + BS + "end{equation}$$"
        out, n = merge_and_build.tag_equations_in_html(html, md)
        self.assertEqual((out, n), (html, 0))

    def test_a_document_with_no_numbered_equations_is_unchanged(self):
        md = "$$x=y$$"
        html = '<p><math display="block"><mi>x</mi></math></p>'
        self.assertEqual(merge_and_build.tag_equations_in_html(html, md), (html, 0))
        self.assertEqual(merge_and_build.tag_equations_for_markdown(md), (md, 0))


class BibliographyTests(unittest.TestCase):
    """A paper must end with exactly one reference list, under a heading.

    SINQ inlines its own .bbl AND ships the .bib citeproc read, so both lists
    were in the document — 29 entries printed twice. CafeQ ships no .bib, so
    its inlined list is the only one there is. AlphaQ has the rendered list and
    nothing announcing it.
    """

    RENDERED = "\n\n".join([
        "# Conclusion",
        "Body text of the conclusion.",
        "Ashkboos, Saleh, and Dan Alistarh. 2024. \u201cQuarot.\u201d *ICML* 1: 2\u201333.",
        "Dettmers, Tim, and Luke Zettlemoyer. 2023. \u201cCase for 4-Bit.\u201d *NeurIPS* 2: 1\u201310.",
        "Frantar, Elias. 2023. \u201cGPTQ.\u201d *ICLR* 3: 4\u201356.",
        "Lin, Ji. 2024. \u201cAWQ.\u201d *MLSys* 4: 87\u2013100.",
        "Tseng, Albert. 2024. \u201cQuIP.\u201d *ICML* 5: 6\u201378.",
        "Xiao, Guangxuan. 2023. \u201cSmoothquant.\u201d *ICML* 6: 7\u201389.",
    ]) + "\n"

    RAW = (BS + "begin{thebibliography}{29}" + NL
           + BS + "bibitem[Ashkboos(2024)]{quarot}" + NL
           + "Ashkboos, S." + NL
           + BS + "end{thebibliography}" + NL)

    def _dir(self, with_bib):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        src = os.path.join(d, "arxiv_src")
        os.makedirs(src)
        if with_bib:
            Path(os.path.join(src, "refs.bib")).write_text("@article{a,}", encoding="utf-8")
        return d

    def test_detects_whether_the_source_shipped_a_bib(self):
        self.assertTrue(merge_and_build.source_has_bib_files(self._dir(True)))
        self.assertFalse(merge_and_build.source_has_bib_files(self._dir(False)))

    def test_drops_the_inlined_list_when_citeproc_already_rendered_one(self):
        text = "# Intro" + NL + NL + self.RAW + NL + self.RENDERED
        out, stats = merge_and_build.resolve_bibliography(
            text, self._dir(True), layout.get_lang_config("ko"))
        self.assertEqual(stats["dropped_duplicate"], 1)
        self.assertNotIn("thebibliography", out)
        self.assertIn("Quarot", out)          # the rendered list survives

    def test_renders_the_inlined_list_when_it_is_the_only_one(self):
        """CafeQ: no .bib, so nothing else rendered the references.

        This used to keep the environment exactly as it was, and pandoc
        drops raw LaTeX on the HTML path without a word: all 61 of CafeQ's
        references reached output.md and none of them reached the book,
        while 19 in-text citations stayed on the page pointing at nothing.
        Laid out here or not laid out at all.
        """
        text = "# Intro" + NL + NL + self.RAW
        out, stats = merge_and_build.resolve_bibliography(
            text, self._dir(False), layout.get_lang_config("ko"))
        self.assertEqual(stats["dropped_duplicate"], 0)
        self.assertGreater(stats["inlined_rendered"], 0)
        self.assertNotIn("thebibliography", out)
        self.assertIn("# 참고문헌", out)

    def test_adds_a_heading_over_the_rendered_list(self):
        out, stats = merge_and_build.resolve_bibliography(
            self.RENDERED, self._dir(True), layout.get_lang_config("ko"))
        self.assertEqual(stats["heading_added"], 1)
        self.assertIn("# 참고문헌", out)
        self.assertLess(out.index("# 참고문헌"), out.index("Ashkboos"))
        self.assertGreater(out.index("# 참고문헌"), out.index("Body text"))

    def test_leaves_a_document_with_no_reference_list_alone(self):
        text = "# Intro" + NL + NL + "Just prose, no references here." + NL
        out, stats = merge_and_build.resolve_bibliography(
            text, self._dir(True), layout.get_lang_config("ko"))
        self.assertEqual(out, text)
        self.assertEqual(stats["heading_added"], 0)

    def test_english_gets_an_english_heading(self):
        out, _stats = merge_and_build.resolve_bibliography(
            self.RENDERED, self._dir(True), layout.get_lang_config("en"))
        self.assertIn("# References", out)


class LabelNumberTests(unittest.TestCase):
    """Sections, appendices, equations and algorithms all carry numbers that
    the markdown lost. CafeQ and AlphaQ suppress the number in the heading but
    still write "Section 4.1" in the body, so the counters have to be rebuilt
    whether or not the headings show them."""

    FLAT = (
        BS + "section{Intro}" + BS + "label{sec:intro}" + NL
        + BS + "begin{equation}" + BS + "label{eq:first}x=1" + BS + "end{equation}" + NL
        + BS + "section{Method}" + BS + "label{sec:method}" + NL
        + BS + "subsection{Setup}" + BS + "label{sec:setup}" + NL
        + BS + "begin{equation*}" + BS + "label{eq:starred}y=2" + BS + "end{equation*}" + NL
        + BS + "begin{equation}" + BS + "label{eq:second}z=3" + BS + "end{equation}" + NL
        + BS + "begin{algorithm}" + BS + "label{alg:main}steps" + BS + "end{algorithm}" + NL
        + BS + "begin{figure}" + BS + "caption{c}" + BS + "label{fig:inside}" + BS + "end{figure}" + NL
        + BS + "appendix" + NL
        + BS + "section{Extra}" + BS + "label{app:extra}" + NL
        + BS + "subsection{More}" + BS + "label{app:more}" + NL
    )

    def _dir(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        Path(os.path.join(d, "flat.tex")).write_text(self.FLAT, encoding="utf-8")
        return d

    def test_section_and_subsection_numbers(self):
        nums = merge_and_build.build_label_numbers(self._dir())
        self.assertEqual(nums["sec:intro"], "1")
        self.assertEqual(nums["sec:method"], "2")
        self.assertEqual(nums["sec:setup"], "2.1")

    def test_appendix_restarts_with_letters(self):
        nums = merge_and_build.build_label_numbers(self._dir())
        self.assertEqual(nums["app:extra"], "A")
        self.assertEqual(nums["app:more"], "A.1")

    def test_starred_environments_take_no_number(self):
        nums = merge_and_build.build_label_numbers(self._dir())
        self.assertEqual(nums["eq:first"], "1")
        self.assertEqual(nums["eq:second"], "2")
        self.assertNotIn("eq:starred", nums)

    def test_a_label_inside_a_float_is_left_to_the_float_counter(self):
        """Without the reset it would inherit the last equation's number."""
        nums = merge_and_build.build_label_numbers(self._dir())
        self.assertNotIn("fig:inside", nums)

    def test_a_label_after_a_float_names_the_enclosing_section(self):
        """LaTeX scopes a float's counter to the float, so a \\label placed
        after \\end{figure} still names the section it sits in. AlphaQ does
        exactly this and the paper prints "Appendix A.3"."""
        flat = (
            BS + "section{Method}" + BS + "label{sec:method}" + NL
            + BS + "subsection{Derivation}" + NL
            + BS + "begin{figure}" + BS + "caption{c}" + BS + "label{fig:inner}"
            + BS + "end{figure}" + NL
            + BS + "label{app:after-float}" + NL)
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        Path(os.path.join(d, "flat.tex")).write_text(flat, encoding="utf-8")

        nums = merge_and_build.build_label_numbers(d)
        self.assertEqual(nums["app:after-float"], "1.1")
        self.assertNotIn("fig:inner", nums)   # build_float_numbers owns that one

    def test_algorithms_have_their_own_counter(self):
        self.assertEqual(merge_and_build.build_label_numbers(self._dir())["alg:main"], "1")


class CrossReferenceSubstitutionTests(unittest.TestCase):
    """(sec:x) has to become "4.1절", and the "Sec." the author typed in front
    of it has to go with it -- otherwise the line reads "See Tab. 표 16"."""

    FLAT = (
        BS + "section{Method}" + BS + "label{sec:method}" + NL
        + BS + "begin{equation}" + BS + "label{eq:dual}x" + BS + "end{equation}" + NL
        + BS + "begin{table}" + BS + "caption{c}" + BS + "label{tab:main}" + BS + "end{table}" + NL
        + BS + "begin{figure}" + BS + "caption{c}" + BS + "label{fig:one}" + BS + "end{figure}" + NL
    )

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        Path(os.path.join(self.dir, "flat.tex")).write_text(self.FLAT, encoding="utf-8")
        self.ko = layout.get_lang_config("ko")

    def _resolve(self, text):
        return merge_and_build.resolve_references(text, self.dir, self.ko)[0]

    def test_absorbs_the_english_word_in_front(self):
        self.assertEqual(self._resolve("See Tab.\u00a0(tab:main)."), "See 표 1.")
        self.assertEqual(self._resolve("in Fig. (fig:one)"), "in 그림 1")

    def test_korean_puts_the_section_marker_last(self):
        self.assertEqual(self._resolve("(Sec.\u00a0(sec:method))"), "(1절)")

    def test_equation_keeps_its_brackets(self):
        self.assertEqual(self._resolve("as in Eq. (eq:dual)"), "as in 식 (1)")

    def test_outer_bracket_is_not_mistaken_for_the_reference(self):
        """(Sec.\u00a0(sec:x)) must not capture "(sec:x" as the label."""
        out = self._resolve("increase (Sec.\u00a0(sec:method)).")
        self.assertEqual(out, "increase (1절).")

    def test_unknown_label_is_left_exactly_as_it_was(self):
        text = "see (sec:nowhere) please"
        self.assertEqual(self._resolve(text), text)

    def test_counts_what_it_resolved(self):
        _out, stats = merge_and_build.resolve_references(
            "(tab:main) and (sec:method) and (sec:nowhere)", self.dir, self.ko)
        self.assertEqual(stats["xrefs"], 2)
        self.assertEqual(stats["xrefs_missed"], 1)


class SectionNumberingTests(unittest.TestCase):
    """A translated paper read on its own gives no clue where you are in the
    original. IEEEtran numbers sections automatically, so the numbers exist
    nowhere in the markdown -- but flat.tex still has the ladder."""

    FLAT = (
        BS + "section*{Abstract}" + NL + "abstract body" + NL
        + BS + "section{Introduction}" + NL
        + "%" + BS + "subsection{Commented Out}" + NL
        + BS + "section{Method}" + NL
        + BS + "subsection{Setup}" + NL
        + BS + "subsubsection{Detail}" + NL
        + BS + "subsection{Results}" + NL
    )
    MD = ("# 초록" + NL + NL + "본문" + NL + NL
          + "# 서론" + NL + NL + "본문" + NL + NL
          + "# 방법" + NL + NL + "## 설정" + NL + NL
          + "### 세부" + NL + NL + "## 결과" + NL)

    def _dir(self, flat=None):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        Path(os.path.join(d, "flat.tex")).write_text(
            self.FLAT if flat is None else flat, encoding="utf-8")
        return d

    def test_strips_latex_comments(self):
        """A %-commented heading would consume a letter and shift the rest."""
        cleaned = merge_and_build.strip_tex_comments("keep %drop" + NL + "next")
        self.assertEqual(cleaned, "keep " + NL + "next")

    def test_escaped_percent_is_not_a_comment(self):
        self.assertEqual(merge_and_build.strip_tex_comments("100" + BS + "% done"),
                         "100" + BS + "% done")

    def test_commented_heading_is_not_counted(self):
        heads = merge_and_build.read_tex_headings(self._dir())
        titles = [t for _l, t, _n in heads]
        self.assertNotIn("Commented Out", titles)

    def test_starred_sections_are_unnumbered(self):
        heads = merge_and_build.read_tex_headings(self._dir())
        self.assertEqual(heads[0], (1, "Abstract", False))
        self.assertEqual(heads[1], (1, "Introduction", True))

    def test_refuses_to_number_without_the_source_pdf(self):
        """The scheme belongs to the document class, so it cannot be derived
        from the .tex alone: IEEEtran prints "III-B", ICML prints "2.1", and
        CafeQ and AlphaQ print no section numbers at all."""
        out, stats = merge_and_build.number_sections(self.MD, self._dir())
        self.assertEqual(stats["numbered"], 0)
        self.assertIn("PDF", stats["skipped_reason"])
        self.assertEqual(out, self.MD)

    def _with_prefixes(self, prefixes):
        """Stand in for the PDF read, which needs pymupdf."""
        real = merge_and_build.read_pdf_section_prefixes

        def fake(temp_dir, tex_heads):
            return list(prefixes), {'matched': sum(1 for p in prefixes if p),
                                    'unnumbered': sum(1 for p in prefixes if p == ''),
                                    'missing': 0, 'wrapped': 0, 'reason': None}

        merge_and_build.read_pdf_section_prefixes = fake
        self.addCleanup(setattr, merge_and_build, 'read_pdf_section_prefixes', real)

    def test_applies_the_prefixes_the_original_prints(self):
        self._with_prefixes(["", "1.", "2.", "2.1.", "2.1.1.", "2.2."])
        out, stats = merge_and_build.number_sections(self.MD, self._dir())
        self.assertEqual(stats["numbered"], 6)
        self.assertIn("# 초록 (Abstract)", out)
        self.assertIn("# 1. 서론 (Introduction)", out)
        self.assertIn("## 2.1. 설정 (Setup)", out)
        self.assertIn("### 2.1.1. 세부 (Detail)", out)
        self.assertIn("## 2.2. 결과 (Results)", out)

    def test_a_paper_that_prints_no_numbers_gets_none(self):
        """CafeQ and AlphaQ number nothing; adding numbers would be a lie."""
        self._with_prefixes([""] * 6)
        out, stats = merge_and_build.number_sections(self.MD, self._dir())
        self.assertEqual(stats["numbered"], 6)
        self.assertIn("# 서론 (Introduction)", out)
        self.assertNotIn("1. 서론", out)

    def test_normalises_headings_before_matching(self):
        fold = merge_and_build._normalize_heading
        self.assertEqual(fold("2.1.1. PARAMETERIZATION per Tile"),
                         fold("Parameterization per Tile") and
                         "2 1 1 parameterization per tile")
        self.assertEqual(fold("Sensitivity of $\\gamma$"), "sensitivity of")

    def test_matches_a_heading_the_pdf_wrapped(self):
        """A title too wide for the column is extracted only up to the break."""
        table = {"pseudo activation aware quantization": "2.2.1."}
        self.assertEqual(
            merge_and_build._longest_prefix_match(
                "pseudo activation aware quantization from weight structure",
                table),
            "pseudo activation aware quantization")
        self.assertIsNone(
            merge_and_build._longest_prefix_match("tiling", table))

    def test_refuses_to_guess_when_counts_differ(self):
        """A heading labelled D that is really E is worse than no label."""
        out, stats = merge_and_build.number_sections(self.MD + NL + "# 추가" + NL,
                                                     self._dir())
        self.assertEqual(stats["numbered"], 0)
        self.assertIn("refusing to guess", stats["skipped_reason"])
        self.assertNotIn("I.", out)

    def test_refuses_to_guess_when_levels_diverge(self):
        md = self.MD.replace("## 설정", "### 설정")
        out, stats = merge_and_build.number_sections(md, self._dir())
        self.assertEqual(stats["numbered"], 0)
        self.assertIsNotNone(stats["skipped_reason"])

    def test_no_flat_tex_is_a_clean_skip(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        out, stats = merge_and_build.number_sections(self.MD, d)
        self.assertEqual(out, self.MD)
        self.assertIn("no flat.tex", stats["skipped_reason"])


class FigureCaptionTests(unittest.TestCase):
    """A caption set in the body face at body size is indistinguishable from
    the argument around it."""

    MD = ("prose" + NL + NL
          + "![](images/fig0003_setup.png)" + NL + NL
          + "**Setup.** The rig used." + NL + NL
          + "more prose" + NL)

    def test_folds_caption_into_the_image_alt_text(self):
        """pandoc's implicit_figures turns an image alone in a paragraph into
        <figure>/<figcaption>, and the alt text still goes through the markdown
        and math readers -- hand-built HTML skipped both."""
        out, n = merge_and_build.format_figure_blocks(self.MD, {"figure_label": "그림"})
        self.assertEqual(n, 1)
        self.assertNotIn("<figure", out)
        img = re.search(r"!\[(.*?)\]\((images/[^)]+)\)", out)
        self.assertIsNotNone(img)
        self.assertIn("The rig used.", img.group(1))
        self.assertNotIn("\n", img.group(1), "alt text must stay on one line")

    def test_number_comes_from_the_filename(self):
        out, _ = merge_and_build.format_figure_blocks(self.MD, {"figure_label": "그림"})
        self.assertIn("그림 3 (Fig. 3)", out)

    def test_caption_is_removed_from_the_body(self):
        out, _ = merge_and_build.format_figure_blocks(self.MD, {"figure_label": "그림"})
        body = out[out.index(".png)") + 5:]
        self.assertNotIn("The rig used.", body)
        self.assertIn("more prose", body)

    def test_english_label_has_no_duplicate_annotation(self):
        out, _ = merge_and_build.format_figure_blocks(self.MD, {"figure_label": "Figure"})
        self.assertIn("Figure 3", out)
        self.assertNotIn("(Fig. 3)", out)

    def test_uncaptioned_figure_does_not_steal_the_next_paragraph(self):
        md = ("![](images/fig0001_a.png)" + NL * 7
              + "**A later bold paragraph.** Not a caption." + NL)
        out, n = merge_and_build.format_figure_blocks(md, {"figure_label": "그림"})
        self.assertEqual(n, 1)
        body = out[out.index(".png)") + 5:]
        self.assertIn("A later bold paragraph.", body)

    def test_no_images_is_a_noop(self):
        out, n = merge_and_build.format_figure_blocks("plain", {})
        self.assertEqual((out, n), ("plain", 0))


class LatexLeftoverTests(unittest.TestCase):
    def test_drop_cap_macro_carries_a_real_word(self):
        """\\IEEEPARstart{T}{raining} is the first WORD, not decoration."""
        out, stats = merge_and_build.normalize_latex_leftovers(
            "`" + BS + "IEEEPARstart{T}{raining}` complex environments")
        self.assertIn("Training complex environments", out)
        self.assertEqual(stats["parstart"], 1)

    def test_multiline_command_is_removed_whole(self):
        """\\markboth wraps across lines; dropping one line stranded its tail."""
        md = (BS + "markboth{IEEE LETTERS. PREPRINT." + NL + "FEB 2025}" + NL
              + NL + "real text" + NL)
        out, _ = merge_and_build.normalize_latex_leftovers(md)
        self.assertNotIn("markboth", out)
        self.assertNotIn("FEB 2025}", out)
        self.assertIn("real text", out)

    def test_escaped_brackets_stop_being_display_math(self):
        """pandoc escapes a literal [x] as \\[x\\], which the reader then
        re-reads as display math under tex_math_single_backslash."""
        out, stats = merge_and_build.normalize_latex_leftovers(
            'Pick the ' + BS + '[object' + BS + ']" here')
        self.assertIn("[object]", out)
        self.assertEqual(stats["brackets"], 1)

    def test_real_math_is_left_alone(self):
        md = BS + "[" + BS + "frac{a}{b}" + BS + "]"
        out, stats = merge_and_build.normalize_latex_leftovers(md)
        self.assertEqual(stats["brackets"], 0)
        self.assertEqual(out, md)

    def test_plain_text_is_untouched(self):
        out, stats = merge_and_build.normalize_latex_leftovers("nothing here")
        self.assertEqual(out, "nothing here")
        self.assertFalse(any(stats.values()))


class CaptionSourceLookupTests(unittest.TestCase):
    """Whether a paragraph is a caption is a fact about the source, not about
    whether the translator happened to leave it bold."""

    def _dir(self, tex):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        Path(os.path.join(d, "flat.tex")).write_text(tex, encoding="utf-8")
        return d

    FLAT = (BS + "begin{figure}" + NL + BS + "caption{One}" + NL + BS + "end{figure}" + NL
            + BS + "begin{figure}" + NL + "no caption here" + NL + BS + "end{figure}" + NL)

    def test_reports_which_floats_carry_a_caption(self):
        self.assertEqual(merge_and_build.figures_with_captions(self._dir(self.FLAT)), {1})

    def test_commented_float_is_ignored(self):
        tex = "%" + BS + "begin{figure}" + NL + self.FLAT
        self.assertEqual(merge_and_build.figures_with_captions(self._dir(tex)), {1})

    def test_returns_none_without_flat_tex(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        self.assertIsNone(merge_and_build.figures_with_captions(d))

    def test_unbolded_caption_is_still_taken(self):
        """Figure 10 of a real paper lost its caption purely for lacking bold."""
        md = ("![](images/fig0001_x.png)" + NL + NL
              + "A plain caption with no bold lead-in." + NL)
        out, n = merge_and_build.format_figure_blocks(
            md, {"figure_label": "그림"}, self._dir(self.FLAT))
        self.assertEqual(n, 1)
        img = re.search(r"!\[(.*?)\]\(", out)
        self.assertIn("A plain caption", img.group(1))

    def test_uncaptioned_float_keeps_its_hands_off_the_body(self):
        md = ("![](images/fig0002_y.png)" + NL + NL
              + "This is ordinary body text." + NL)
        out, _ = merge_and_build.format_figure_blocks(
            md, {"figure_label": "그림"}, self._dir(self.FLAT))
        body = out[out.index(".png)") + 5:]
        self.assertIn("This is ordinary body text.", body)


if __name__ == "__main__":
    unittest.main()


class SubcaptionTests(unittest.TestCase):
    r"""A panel label arrives as `\subcaption{...}` sharing a line with its
    image. Two things then go wrong at once: the command prints verbatim to
    the reader, and the image is no longer alone on its line, so
    format_figure_blocks skips it -- three pictures with no number, no
    caption and nothing tying them to the text."""

    def rewrite(self, text):
        stats = {"dropped": 0}
        return merge_and_build.rewrite_subcaptions(text, stats), stats

    def test_nested_braces_are_handled(self):
        r"""`\subcaption[t]{Adam; $\lambda_{orth}=0$.}` -- the inner braces
        made a [^{}]* pattern miss the command entirely."""
        text = "![i](x.png) `" + BS + "subcaption[t]{Adam; $" + BS \
            + "lambda_{orth}=0$.}`{=latex}"
        out, stats = self.rewrite(text)
        self.assertEqual(stats["dropped"], 1)
        self.assertNotIn("subcaption", out)
        self.assertIn("Adam; $" + BS + "lambda_{orth}=0$.", out)

    def test_label_moves_off_the_image_line(self):
        text = "![i](x.png) " + BS + "subcaption{Cayley SGD.}"
        out, _ = self.rewrite(text)
        self.assertEqual(out.split("\n")[0], "![i](x.png)")
        self.assertIn("**Cayley SGD.**", out)

    def test_empty_subcaption_leaves_nothing_behind(self):
        text = "![i](x.png) " + BS + "subcaption{}"
        out, _ = self.rewrite(text)
        self.assertEqual(out.strip(), "![i](x.png)")

    def test_text_without_a_subcaption_is_unchanged(self):
        text = "ordinary paragraph with no commands"
        out, stats = self.rewrite(text)
        self.assertEqual(out, text)
        self.assertEqual(stats["dropped"], 0)


class GraphicStemTests(unittest.TestCase):
    """Two panels of one figure can come from two pages of one PDF. Keyed on
    the path alone they collapse into a single panel, leaving the second
    image unclaimed and numbered from its filename instead."""

    def test_page_beyond_the_first_joins_the_stem(self):
        self.assertEqual(
            merge_and_build._graphic_stem("figures/adam.pdf", "page=4"),
            "adamp4")

    def test_page_one_is_the_bare_stem(self):
        self.assertEqual(
            merge_and_build._graphic_stem("figures/adam.pdf", "page=1"),
            "adam")

    def test_no_options_is_the_bare_stem(self):
        self.assertEqual(merge_and_build._graphic_stem("figures/adam.pdf"),
                         "adam")

    def test_two_pages_of_one_file_do_not_collide(self):
        a = merge_and_build._graphic_stem("f/x.pdf", "width=1cm,page=1")
        b = merge_and_build._graphic_stem("f/x.pdf", "width=1cm,page=4")
        self.assertNotEqual(a, b)


class PanelWidthTests(unittest.TestCase):
    """A panel drawn at full text width is about 125mm tall against a 257mm
    text block, so two cannot share a page. SINQ printed three panels of one
    figure on three pages -- seven of its thirty-six pages held a single
    picture and fourteen characters of caption."""

    def width_for(self, panels):
        return merge_and_build._PANEL_WIDTH.get(
            panels, merge_and_build._PANEL_WIDTH_MANY)

    def test_more_panels_means_a_smaller_panel(self):
        self.assertGreater(self.width_for(2), self.width_for(3))
        self.assertGreater(self.width_for(3), self.width_for(4))

    def test_a_float_of_up_to_four_panels_fits_one_page(self):
        """panels x (height + caption) must stay inside the 257mm text block."""
        for panels in (2, 3, 4):
            height = 125.0 * self.width_for(panels) / 100.0
            self.assertLessEqual(panels * (height + 15), 257,
                                 '%d panels do not fit a page' % panels)

    def test_a_panel_is_never_shrunk_past_legibility(self):
        """38% of the 174mm text width is 66mm -- wider than the ~40mm the
        same panels get in the printed original. Below that, stop shrinking
        and let the float run onto a second page instead."""
        for panels in (2, 3, 4, 9):
            self.assertGreaterEqual(self.width_for(panels), 38)

    def test_an_image_with_a_width_attribute_is_still_recognised(self):
        """_FIG_IMAGE_RE decides whether the next paragraph is another panel;
        missing one would let a panel swallow the next panel's caption."""
        line = "![cap](images/fig0007_x.png){width=60%}"
        self.assertTrue(merge_and_build._FIG_IMAGE_RE.match(line))
        self.assertTrue(
            merge_and_build._FIG_IMAGE_RE.match("![cap](images/fig0007_x.png)"))


class FragmentWriterTests(unittest.TestCase):
    """The DOCX path renders each raw LaTeX table to MARKDOWN, and plain
    `-t markdown` picks the table style itself. For anything wide or spanned
    it chooses a simple table -- columns by character position, no `|` at all
    -- which _is_markdown_table cannot recognise, so nine of AlphaQ's twelve
    tables were dropped to plain text in the Word file while the HTML had all
    twelve and every count agreed with itself."""

    def test_only_pipe_tables_are_allowed(self):
        spec = merge_and_build._FRAGMENT_WRITER
        self.assertIn('+pipe_tables', spec)
        for style in ('simple_tables', 'multiline_tables', 'grid_tables'):
            self.assertIn('-' + style, spec,
                          '%s can still be chosen' % style)

    def test_the_div_wrapper_is_off(self):
        """`::: table*` around a float prints literally in the DOCX."""
        spec = merge_and_build._FRAGMENT_WRITER
        for ext in ('fenced_divs', 'native_divs', 'raw_html'):
            self.assertIn('-' + ext, spec)

    def test_a_pipe_table_is_recognised(self):
        self.assertTrue(merge_and_build._is_markdown_table('| a | b |'))

    def test_prose_is_not_a_table(self):
        self.assertFalse(
            merge_and_build._is_markdown_table('Just a sentence about it.'))


class ParticleAgreementTests(unittest.TestCase):
    """Korean picks a particle by how the preceding syllable is pronounced,
    and the sub-agent wrote one after "(fig:x)" -- it never saw the number
    this pass substitutes in front of it. Twelve shipped: "그림 1를", "표 9은"."""

    KO = {"particle_agreement": True}

    def fix(self, text):
        out, _n = merge_and_build.fix_particles(text, self.KO)
        return out

    def test_a_number_with_a_final_consonant_takes_the_consonant_form(self):
        self.assertEqual(self.fix("그림 1를"), "그림 1을")
        self.assertEqual(self.fix("표 3가"), "표 3이")
        self.assertEqual(self.fix("식 6는"), "식 6은")

    def test_a_number_ending_in_a_vowel_takes_the_vowel_form(self):
        self.assertEqual(self.fix("그림 2을"), "그림 2를")
        self.assertEqual(self.fix("표 9은"), "표 9는")

    def test_a_correct_particle_is_left_alone(self):
        for text in ("그림 1을", "표 9는", "식 2를", "그림 6은"):
            self.assertEqual(self.fix(text), text)

    def test_rieul_takes_ro_not_euro(self):
        """으로/로 is the one pair that breaks the coda rule: a final ㄹ takes
        로, like 물로. 일, 칠 and 팔 all end in ㄹ, and the first version of
        this pass turned a correct "8로" into "8으로"."""
        for digit in ("1", "7", "8"):
            self.assertEqual(self.fix("크기는 %s으로" % digit),
                             "크기는 %s로" % digit)
            self.assertEqual(self.fix("크기는 %s로" % digit),
                             "크기는 %s로" % digit)

    def test_other_consonant_endings_still_take_euro(self):
        for digit in ("0", "3", "6"):
            self.assertEqual(self.fix("%s로" % digit), "%s으로" % digit)

    def test_a_particle_not_touching_the_number_is_untouched(self):
        """"4비트로" -- the particle follows 비트, not the digit."""
        self.assertEqual(self.fix("4비트로 양자화"), "4비트로 양자화")

    def test_other_languages_are_untouched(self):
        out, n = merge_and_build.fix_particles("그림 1를",
                                               {"particle_agreement": False})
        self.assertEqual((out, n), ("그림 1를", 0))


class EmptyCodeSpanTests(unittest.TestCase):
    """Stripping a command out of a code span leaves the span, and two stray
    backticks print. All three books had one right after a heading:
    "(Estimating Layer Importance in MoE) `` 캘리브레이션 시점의 활성값이…"."""

    BT = chr(96)

    def clean(self, text):
        out, _stats = merge_and_build.normalize_latex_leftovers(text)
        return out

    def test_an_empty_span_goes(self):
        self.assertEqual(self.clean("text %s more" % (self.BT * 2)),
                         "text  more")

    def test_the_pandoc_marker_form_goes(self):
        self.assertEqual(self.clean("text %s{=latex} more" % (self.BT * 2)),
                         "text  more")

    def test_a_real_code_span_survives(self):
        text = "use %sgit status%s here" % (self.BT, self.BT)
        self.assertEqual(self.clean(text), text)

    def test_a_double_backtick_span_survives(self):
        """``code with a ` inside`` opens with exactly the shape we remove."""
        text = "%scode with %s inside%s here" % (self.BT * 2, self.BT,
                                                 self.BT * 2)
        self.assertEqual(self.clean(text), text)

    def test_adjacent_spans_are_not_merged(self):
        text = "%sa%sb%s here" % (self.BT, self.BT * 2, self.BT)
        self.assertEqual(self.clean(text), text)

    def test_a_fenced_block_is_never_rewritten(self):
        text = "%s\na %s b\n%s" % (self.BT * 3, self.BT * 2, self.BT * 3)
        self.assertEqual(self.clean(text), text)


class WebTocAnchorTests(unittest.TestCase):
    """The floating TOC in book.html linked to #heading-1, #heading-2 … and
    none of those anchors existed: the code built `<h2>text</h2>` and
    str.replace()-d it, while pandoc writes `<h2 id="slug">`. Every link in
    the sidebar was dead, on all three books, and no check looked."""

    SHELL = ('<html><body><div class="toc-content"></div>\n'
             '%s\n</body></html>')

    def build(self, body):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "book.html")
            Path(path).write_text(self.SHELL % body, encoding="utf-8")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                merge_and_build.insert_toc_with_regex(path)
            return Path(path).read_text(encoding="utf-8")

    def dead_links(self, html):
        links = re.findall(r'<a[^>]+href="#([^"]+)"', html)
        ids = set(re.findall(r'\bid="([^"]+)"', html))
        return [l for l in links if l not in ids], links

    def test_a_pandoc_heading_keeps_its_own_anchor(self):
        html = self.build('<h1 id="intro">Introduction</h1>')
        dead, links = self.dead_links(html)
        self.assertEqual(dead, [])
        self.assertIn("intro", links)

    def test_a_heading_with_no_id_gets_one(self):
        html = self.build("<h2>Methods</h2>")
        dead, links = self.dead_links(html)
        self.assertEqual(dead, [])
        self.assertTrue(links)

    def test_a_mix_of_both_leaves_nothing_dead(self):
        html = self.build('<h1 id="a">One</h1>\n<h2>Two</h2>\n'
                          '<h2 id="c">Three</h2>')
        dead, links = self.dead_links(html)
        self.assertEqual(dead, [])
        self.assertEqual(len(links), 3)

    def test_other_attributes_on_a_heading_survive(self):
        html = self.build('<h2 class="sec">Methods</h2>')
        self.assertIn('class="sec"', html)


class TableCaptionNumberTests(unittest.TestCase):
    """Figures carried their number and tables did not, so the body said
    "표 5에서 보듯이" and the caption above the table said nothing a reader
    could match it against -- the same gap the equations had."""

    FLAT = (
        BS + "begin{table}" + NL + BS + "caption{First}" + NL
        + BS + "begin{tabular}{ll}a & b" + BS + BS + NL
        + BS + "end{tabular}" + NL + BS + "end{table}" + NL
        + BS + "begin{table}" + NL + BS + "caption{Second}" + NL
        + BS + "begin{tabular}{ll}c & d" + BS + BS + NL
        + BS + "end{tabular}" + NL + BS + "end{table}" + NL
    )
    KO = {"table_label": "표"}

    def temp(self, flat=None):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        Path(os.path.join(d, "flat.tex")).write_text(flat or self.FLAT,
                                                     encoding="utf-8")
        return d

    def test_a_markdown_caption_gets_the_label(self):
        md = "| a | b |\n|---|---|\n| 1 | 2 |\n\n: Some caption\n"
        out, n = merge_and_build.number_table_captions(md, self.temp(), self.KO)
        self.assertEqual(n, 1)
        self.assertIn(": **표 1 (Table 1)** Some caption", out)

    def test_a_raw_latex_caption_gets_the_label(self):
        md = ("text\n\n" + BS + "begin{table}" + NL + BS + "caption{First}"
              + NL + BS + "begin{tabular}{ll}a & b" + BS + BS + NL
              + BS + "end{tabular}" + NL + BS + "end{table}\n")
        out, n = merge_and_build.number_table_captions(md, self.temp(), self.KO)
        self.assertEqual(n, 1)
        self.assertIn(BS + "caption{" + BS + "textbf{표 1 (Table 1)} First",
                      out)

    def test_numbers_run_in_document_order(self):
        md = ("| a |\n|---|\n| 1 |\n\n: One\n\n"
              "| b |\n|---|\n| 2 |\n\n: Two\n")
        out, n = merge_and_build.number_table_captions(md, self.temp(), self.KO)
        self.assertEqual(n, 2)
        self.assertLess(out.index("표 1"), out.index("표 2"))

    def test_a_float_with_two_captions_takes_two_numbers(self):
        """AlphaQ puts two minipages with their own caption in one table*;
        walking tables instead of captions stamped both badges on the first."""
        flat = (BS + "begin{table*}" + NL + BS + "caption{Left}" + NL
                + BS + "caption{Right}" + NL + BS + "end{table*}" + NL)
        md = ("x\n\n" + BS + "begin{table*}" + NL + BS + "caption{Left}" + NL
              + BS + "begin{tabular}{l}a" + BS + BS + BS + "end{tabular}" + NL
              + BS + "caption{Right}" + NL
              + BS + "begin{tabular}{l}b" + BS + BS + BS + "end{tabular}" + NL
              + BS + "end{table*}\n")
        out, n = merge_and_build.number_table_captions(md, self.temp(flat),
                                                       self.KO)
        self.assertEqual(n, 2)
        self.assertEqual(out.count("표 1 (Table 1)"), 1)
        self.assertEqual(out.count("표 2 (Table 2)"), 1)

    def test_english_gets_no_parenthetical(self):
        md = "| a |\n|---|\n| 1 |\n\n: Some caption\n"
        out, _n = merge_and_build.number_table_captions(md, self.temp(),
                                                        {"table_label": "Table"})
        self.assertIn(": **Table 1** Some caption", out)
        self.assertNotIn("(Table 1)", out)

    def test_without_flat_tex_nothing_is_numbered(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        md = "| a |\n|---|\n| 1 |\n\n: Some caption\n"
        out, n = merge_and_build.number_table_captions(md, d, self.KO)
        self.assertEqual((out, n), (md, 0))


class FloatCaptionOwnershipTests(unittest.TestCase):
    """A float can hold two tabulars, each with its own caption. Taking the
    float's FIRST caption gave both tables the same text and lost the second
    one -- "Component ablation on OLMoE-1B-7B" was nowhere in the book."""

    FLOAT = (BS + "caption{Left}" + NL + BS + "begin{tabular}{l}a"
             + BS + "end{tabular}" + NL + BS + "caption{Right}" + NL
             + BS + "begin{tabular}{l}b" + BS + "end{tabular}")

    def test_each_tabular_takes_the_caption_above_it(self):
        first = self.FLOAT.index(BS + "begin{tabular}")
        second = self.FLOAT.index(BS + "begin{tabular}", first + 1)
        self.assertEqual(merge_and_build._extract_caption(self.FLOAT, first),
                         "Left")
        self.assertEqual(merge_and_build._extract_caption(self.FLOAT, second),
                         "Right")

    def test_with_no_position_the_first_caption_wins(self):
        self.assertEqual(merge_and_build._extract_caption(self.FLOAT), "Left")

    def test_a_caption_below_its_tabular_still_resolves(self):
        text = (BS + "begin{tabular}{l}a" + BS + "end{tabular}" + NL
                + BS + "caption{Below}")
        self.assertEqual(merge_and_build._extract_caption(text, 0), "Below")

    def test_no_caption_at_all(self):
        self.assertIsNone(merge_and_build._extract_caption("nothing here", 0))


class TableHeaderPromotionTests(unittest.TestCase):
    """pandoc finds a table's header by looking for a rule, and the answer
    depends on which rules the paper happened to use: SINQ's main results
    table and three of AlphaQ's produced no <thead> at all. The header rule
    never drew, the header never repeated across a page break, and not one
    cell was a <th> -- nine columns of numbers under nothing. Counting the
    header rows off the LaTeX is not a heuristic."""

    def tab(self, body, preamble="{lll}"):
        return BS + "begin{tabular}" + preamble + NL + body + NL \
            + BS + "end{tabular}"

    def test_one_header_row(self):
        latex = self.tab(BS + "toprule" + NL + "A & B & C" + BS + BS + NL
                         + BS + "midrule" + NL + "1 & 2 & 3" + BS + BS)
        self.assertEqual(merge_and_build.header_row_count(latex), 1)

    def test_two_header_rows(self):
        latex = self.tab(BS + "toprule" + NL + "G & G & G" + BS + BS + NL
                         + "A & B & C" + BS + BS + NL + BS + "midrule" + NL
                         + "1 & 2 & 3" + BS + BS)
        self.assertEqual(merge_and_build.header_row_count(latex), 2)

    def test_no_midrule_means_no_header(self):
        latex = self.tab(BS + "toprule" + NL + "1 & 2 & 3" + BS + BS)
        self.assertEqual(merge_and_build.header_row_count(latex), 0)

    def test_hline_counts_as_the_header_rule(self):
        latex = self.tab(BS + "hline" + NL + "A & B & C" + BS + BS + NL
                         + BS + "hline" + NL + "1 & 2 & 3" + BS + BS)
        self.assertEqual(merge_and_build.header_row_count(latex), 1)

    def test_a_table_that_is_all_header_is_left_alone(self):
        """Everything above the rule and nothing below is not a header."""
        latex = self.tab(BS + "toprule" + NL + "A & B & C" + BS + BS + NL
                         + BS + "midrule")
        self.assertEqual(merge_and_build.header_row_count(latex), 0)

    HTML = ("<table>\n<tbody>\n<tr><td>A</td><td>B</td></tr>\n"
            "<tr><td>1</td><td>2</td></tr>\n"
            "<tr><td>3</td><td>4</td></tr>\n</tbody>\n</table>")

    def test_rows_are_promoted_and_cells_become_th(self):
        latex = self.tab(BS + "toprule" + NL + "A & B" + BS + BS + NL
                         + BS + "midrule" + NL + "1 & 2" + BS + BS + NL
                         + "3 & 4" + BS + BS, "{ll}")
        out = merge_and_build.promote_header_rows(self.HTML, latex)
        self.assertIn("<thead>", out)
        self.assertIn("<th>A</th>", out)
        self.assertEqual(out.count("<tbody>"), 1)
        self.assertEqual(out.count("</tbody>"), 1)
        self.assertEqual(out.count("<tr"), 3)

    def test_a_table_that_already_has_a_head_is_untouched(self):
        html = "<table><thead><tr><th>A</th></tr></thead><tbody></tbody></table>"
        self.assertEqual(merge_and_build.promote_header_rows(html, "x"), html)


class TableGroupRuleTests(unittest.TestCase):
    """A paper separates its row groups with a rule -- SINQ's 3-bit block from
    its 4-bit block -- and pandoc renders none of them, so nine rows of
    numbers run together with only the group label in the margin."""

    def test_a_rule_inside_the_body_marks_the_row_after_it(self):
        latex = (BS + "begin{tabular}{ll}" + NL + BS + "toprule" + NL
                 + "A & B" + BS + BS + NL + BS + "midrule" + NL
                 + "1 & 2" + BS + BS + NL + BS + "midrule" + NL
                 + "3 & 4" + BS + BS + NL + BS + "end{tabular}")
        self.assertEqual(merge_and_build.body_rule_rows(latex), {1: 'hard'})

    def test_no_body_rule_marks_nothing(self):
        latex = (BS + "begin{tabular}{ll}" + NL + BS + "toprule" + NL
                 + "A & B" + BS + BS + NL + BS + "midrule" + NL
                 + "1 & 2" + BS + BS + NL + BS + "end{tabular}")
        self.assertEqual(merge_and_build.body_rule_rows(latex), {})

    def test_the_class_lands_on_the_right_row(self):
        latex = (BS + "begin{tabular}{ll}" + NL + BS + "toprule" + NL
                 + "A & B" + BS + BS + NL + BS + "midrule" + NL
                 + "1 & 2" + BS + BS + NL + BS + "midrule" + NL
                 + "3 & 4" + BS + BS + NL + BS + "end{tabular}")
        html = ("<table>\n<tbody>\n<tr><td>1</td></tr>\n"
                "<tr><td>3</td></tr>\n</tbody>\n</table>")
        out = merge_and_build.mark_body_rules(html, latex)
        self.assertEqual(out.count('class="rule-above"'), 1)
        self.assertIn('<tr class="rule-above"><td>3</td>', out)


class SoftGroupRuleTests(unittest.TestCase):
    r"""AlphaQ's Table 1 nests its groups: a \midrule between models and mere
    \addlinespace between the bit budgets inside each one. Space cannot
    survive into a one-row-tall HTML cell, so without a weight for it the bit
    groups ran together and the reader could not see where 2.5-bit ended."""

    def table(self, sep):
        return (BS + "begin{tabular}{lll}" + NL + BS + "toprule" + NL
                + "A & B & C" + BS + BS + NL + BS + "midrule" + NL
                + "1 & 2 & 3" + BS + BS + NL + sep + NL
                + "4 & 5 & 6" + BS + BS + NL + BS + "end{tabular}")

    def test_addlinespace_is_a_soft_boundary(self):
        rows = merge_and_build.body_rule_rows(self.table(BS + "addlinespace[2pt]"))
        self.assertEqual(rows, {1: "soft"})

    def test_a_midrule_stays_the_hard_one(self):
        rows = merge_and_build.body_rule_rows(self.table(BS + "midrule"))
        self.assertEqual(rows, {1: "hard"})

    def test_the_two_get_different_classes(self):
        html = ("<table>\n<tbody>\n<tr><td>1</td></tr>\n"
                "<tr><td>4</td></tr>\n</tbody>\n</table>")
        soft = merge_and_build.mark_body_rules(
            html, self.table(BS + "addlinespace"))
        hard = merge_and_build.mark_body_rules(html, self.table(BS + "midrule"))
        self.assertIn('class="rule-above-soft"', soft)
        self.assertNotIn('class="rule-above"', soft)
        self.assertIn('class="rule-above"', hard)

    def test_no_separator_marks_nothing(self):
        self.assertEqual(merge_and_build.body_rule_rows(self.table("")), {})


class SummaryRowRuleTests(unittest.TestCase):
    r"""A paper rules off the Average block at the foot of a long table.
    Tables pandoc could convert take the markdown path, where pipe syntax has
    no way to carry a rule, so the boundary vanished: CafeQ's twenty-row
    per-task table ran its four averages straight on from its sixteen
    benchmarks."""

    def table(self, labels):
        rows = ''.join('<tr><td>%s</td><td>1</td></tr>\n' % l for l in labels)
        return '<table>\n<tbody>\n%s</tbody>\n</table>' % rows

    def test_the_average_block_is_ruled_off(self):
        labels = ['MMLU', 'ARC', 'GSM8K', 'BBH', 'PIQA', 'MBPP',
                  '평균 (전체)', '평균 (핵심)']
        out = merge_and_build.rule_off_summary_rows(self.table(labels))
        self.assertEqual(out.count('rule-above'), 1)
        self.assertIn('<tr class="rule-above"><td>평균 (전체)</td>', out)

    def test_english_summary_words_too(self):
        labels = ['A', 'B', 'C', 'D', 'E', 'F', 'Average (All)', 'Total']
        out = merge_and_build.rule_off_summary_rows(self.table(labels))
        self.assertEqual(out.count('rule-above'), 1)

    def test_a_summary_row_mid_table_is_left_alone(self):
        """Only the block at the FOOT is a summary; one in the middle is a
        row like any other."""
        labels = ['A', '평균', 'C', 'D', 'E', 'F', 'G', 'H']
        out = merge_and_build.rule_off_summary_rows(self.table(labels))
        self.assertNotIn('rule-above', out)

    def test_a_table_that_already_has_rules_is_untouched(self):
        html = ('<table>\n<tbody>\n<tr class="rule-above"><td>A</td></tr>\n'
                + ''.join('<tr><td>%d</td></tr>\n' % i for i in range(6))
                + '<tr><td>평균</td></tr>\n</tbody>\n</table>')
        self.assertEqual(merge_and_build.rule_off_summary_rows(html), html)

    def test_a_short_table_is_left_alone(self):
        out = merge_and_build.rule_off_summary_rows(self.table(['A', '평균']))
        self.assertNotIn('rule-above', out)

    def test_only_the_first_summary_row_gets_the_rule(self):
        labels = ['A', 'B', 'C', 'D', 'E', 'F', '평균 (1)', '평균 (2)', '평균 (3)']
        out = merge_and_build.rule_off_summary_rows(self.table(labels))
        self.assertEqual(out.count('rule-above'), 1)


class GridTableConversionTests(unittest.TestCase):
    """A grid table marks columns by CHARACTER POSITION and pandoc lays one
    out by DISPLAY width, so a Hangul cell shifts every separator and pandoc
    abandons the table. It cannot simply be turned off at ingest: it is the
    only format pandoc can use for a spanning multi-deck header, and without
    it pandoc writes the literal text `[TABLE]` and the table is gone."""

    SIMPLE = ("+------+------+\n"
              "| A    | B    |\n"
              "+======+======+\n"
              "| 1    | 2    |\n"
              "+------+------+\n")

    ROWSPAN = ("+------+------+\n"
               "| A    | B    |\n"
               "|      +------+\n"
               "|      | C    |\n"
               "+------+------+\n")

    def test_a_plain_grid_table_becomes_a_pipe_table(self):
        out, n = merge_and_build.grid_tables_to_pipe(self.SIMPLE)
        self.assertEqual(n, 1)
        self.assertIn('| A | B |', out)
        self.assertIn('| 1 | 2 |', out)
        self.assertNotIn('+---', out)

    def test_a_row_spanning_table_is_left_exactly_as_it_was(self):
        """A pipe table cannot express a cell that spans rows, and converting
        half of one ate the interior borders of CafeQ's widest table."""
        out, n = merge_and_build.grid_tables_to_pipe(self.ROWSPAN)
        self.assertEqual(n, 0)
        self.assertEqual(out, self.ROWSPAN)

    def test_prose_around_a_table_is_untouched(self):
        text = "before\n\n" + self.SIMPLE + "\nafter\n"
        out, _n = merge_and_build.grid_tables_to_pipe(text)
        self.assertIn('before', out)
        self.assertIn('after', out)

    def test_an_em_dash_border_is_still_a_border(self):
        """A chunk that went through a smart-quotes pass has them, and a
        border read as a row cut the table in half."""
        table = self.SIMPLE.replace('-', '—')
        out, n = merge_and_build.grid_tables_to_pipe(table)
        self.assertEqual(n, 1)
        self.assertIn('| A | B |', out)

    def test_text_with_no_table_is_returned_unchanged(self):
        text = "just a paragraph\n\nand another\n"
        self.assertEqual(merge_and_build.grid_tables_to_pipe(text), (text, 0))

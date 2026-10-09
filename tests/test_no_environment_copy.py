# -*- coding: utf-8 -*-
"""No shipped script hands a copy of the user's environment to anything.

Anthropic's directory scanned v0.4.8 and warned that the plugin "reads a
credential from the user's environment and could send it to a server",
naming merge_and_build.py. What it found was `{**os.environ, ...}`, built
only to add PYTHONIOENCODING for calibre_html_publish.py, which already sets
its own output to UTF-8. Reading a named variable to find a program
(`os.environ.get('PANDOC_PATH')`) is fine; copying the whole environment is
not, because nothing here needs it.
"""
import ast
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def is_os_environ(node):
    return (isinstance(node, ast.Attribute) and node.attr == "environ"
            and isinstance(node.value, ast.Name) and node.value.id == "os")


def environment_copies(tree):
    """Lines that copy os.environ whole, or pass an env= to a call."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict) and any(
                k is None and is_os_environ(v) for k, v in zip(node.keys, node.values)):
            yield node.lineno, "{**os.environ}"
        elif isinstance(node, ast.Call):
            if any(kw.arg == "env" for kw in node.keywords):
                yield node.lineno, "env= passed to a call"
            func = node.func
            if isinstance(func, ast.Name) and func.id == "dict" and node.args \
                    and is_os_environ(node.args[0]):
                yield node.lineno, "dict(os.environ)"
            if isinstance(func, ast.Attribute) and func.attr == "copy" \
                    and is_os_environ(func.value):
                yield node.lineno, "os.environ.copy()"


class NoScriptCopiesTheEnvironment(unittest.TestCase):
    def test_no_script_copies_or_passes_the_environment(self):
        found = []
        for path in sorted(SCRIPTS.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
            found += ["%s:%d: %s" % (path.name, n, what)
                      for n, what in environment_copies(tree)]
        self.assertEqual(found, [])

    def test_it_would_see_the_copy_v0_4_8_shipped(self):
        tree = ast.parse("env = {**os.environ, 'PYTHONIOENCODING': 'utf-8'}\n"
                         "subprocess.run(cmd, env=env)\n"
                         "fa, fb, env = widen(text)\n")
        self.assertEqual([n for n, _ in environment_copies(tree)], [1, 2])

    def test_the_epub_child_still_sets_its_own_output_to_utf8(self):
        text = (SCRIPTS / "calibre_html_publish.py").read_text(encoding="utf-8")
        self.assertIn("reconfigure(encoding='utf-8'", text)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Tests for todo_comment_checker — standard library unittest only."""

import ast
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SRC = ROOT / "src" / "todo_comment_checker.py"

sys.path.insert(0, str(ROOT / "src"))
import todo_comment_checker as tcc  # noqa: E402


def run_cli(*args, stdin_text=None):
    """Run the checker as a subprocess. Returns (exit, stdout, stderr)."""
    proc = subprocess.run(
        [sys.executable, str(SRC), *args],
        input=stdin_text,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    return proc.returncode, proc.stdout, proc.stderr


class TestFindMarkersInLine(unittest.TestCase):
    def setUp(self):
        self.pattern = tcc.marker_pattern(tcc.MARKERS)

    def check(self, line):
        return tcc.find_markers_in_line(line, self.pattern)

    def test_hash_comment(self):
        self.assertEqual(
            self.check("# TODO: fix this"),
            [{"marker": "TODO", "text": "TODO: fix this"}],
        )

    def test_slash_comment(self):
        self.assertEqual(
            self.check("// FIXME: wrong answer"),
            [{"marker": "FIXME", "text": "FIXME: wrong answer"}],
        )

    def test_code_then_comment(self):
        self.assertEqual(
            self.check("x = 1  # TODO: use the real value"),
            [{"marker": "TODO", "text": "TODO: use the real value"}],
        )

    def test_block_comment_open(self):
        self.assertEqual(
            self.check("/* XXX: remove this */"),
            [{"marker": "XXX", "text": "XXX: remove this */"}],
        )

    def test_block_comment_continuation(self):
        self.assertEqual(
            self.check(" * TODO: still inside the block"),
            [{"marker": "TODO", "text": "TODO: still inside the block"}],
        )

    def test_html_comment(self):
        self.assertEqual(
            self.check("<!-- TODO: alt text -->"),
            [{"marker": "TODO", "text": "TODO: alt text -->"}],
        )

    def test_dash_comment(self):
        self.assertEqual(
            self.check("-- FIXME: broken query"),
            [{"marker": "FIXME", "text": "FIXME: broken query"}],
        )

    def test_marker_first_word(self):
        self.assertEqual(
            self.check("TODO: buy milk"),
            [{"marker": "TODO", "text": "TODO: buy milk"}],
        )

    def test_marker_first_word_indented(self):
        self.assertEqual(
            self.check("   XXX check this"),
            [{"marker": "XXX", "text": "XXX check this"}],
        )

    def test_lowercase_marker(self):
        self.assertEqual(
            self.check("# todo: lowercase still counts"),
            [{"marker": "TODO", "text": "todo: lowercase still counts"}],
        )

    def test_string_is_not_a_comment(self):
        self.assertEqual(self.check('x = "a todo list for later"'), [])

    def test_filename_in_comment_is_not_a_marker(self):
        self.assertEqual(self.check("# see todo.py for the list"), [])
        self.assertEqual(self.check("# the fix is in todo.txt"), [])

    def test_flag_line_is_not_a_comment(self):
        self.assertEqual(self.check("cmd --limit 3 examples/todo.py"), [])

    def test_multiplication_is_not_a_comment(self):
        self.assertEqual(self.check("x = 2 * todo"), [])

    def test_string_then_real_comment(self):
        self.assertEqual(
            self.check('x = "todo"  # TODO: real one'),
            [{"marker": "TODO", "text": "TODO: real one"}],
        )

    def test_word_boundary(self):
        self.assertEqual(self.check("# TODOS: not a marker"), [])
        self.assertEqual(self.check("# methodology note"), [])

    def test_no_marker(self):
        self.assertEqual(self.check("x = 1  # just a note"), [])

    def test_two_markers_one_line(self):
        found = self.check("# TODO: one thing, FIXME: another")
        self.assertEqual([hit["marker"] for hit in found], ["TODO", "FIXME"])


class TestCheckText(unittest.TestCase):
    def setUp(self):
        self.pattern = tcc.marker_pattern(tcc.MARKERS)

    def test_line_numbers(self):
        text = "clean line\n# TODO: first\nclean\n// FIXME: second\n"
        found = tcc.check_text(text, self.pattern)
        self.assertEqual(
            [(hit["line"], hit["marker"]) for hit in found],
            [(2, "TODO"), (4, "FIXME")],
        )

    def test_empty_text(self):
        self.assertEqual(tcc.check_text("", self.pattern), [])


class TestMarkersAndLimit(unittest.TestCase):
    def test_parse_markers_subset(self):
        self.assertEqual(tcc.parse_markers("TODO,FIXME"), ("TODO", "FIXME"))

    def test_parse_markers_lowercase_and_duplicates(self):
        self.assertEqual(tcc.parse_markers("todo, TODO, xxx"), ("TODO", "XXX"))

    def test_parse_markers_unknown(self):
        with self.assertRaises(tcc.InputError):
            tcc.parse_markers("TODO,HACK")

    def test_parse_markers_empty(self):
        with self.assertRaises(tcc.InputError):
            tcc.parse_markers("")

    def test_parse_limit_ok(self):
        self.assertEqual(tcc.parse_limit("3"), 3)

    def test_parse_limit_bad(self):
        for bad in ("-1", "1.5", "many"):
            with self.assertRaises(tcc.InputError):
                tcc.parse_limit(bad)


class TestCliFiles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, text):
        path = self.dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return str(path)

    def test_clean_file_passes(self):
        path = self.write("clean.py", "x = 1  # nothing here\n")
        code, out, err = run_cli(path)
        self.assertEqual(code, 0)
        self.assertIn("OK", out)
        self.assertNotIn("FAIL", out)

    def test_marked_file_fails(self):
        path = self.write("todo.py", "x = 1\n# TODO: fix it\n")
        code, out, err = run_cli(path)
        self.assertEqual(code, 1)
        self.assertIn(f"FAIL {path}:2: TODO: fix it", out)
        self.assertIn("over the limit of 0", out)

    def test_limit_allows_some(self):
        path = self.write("todo.py", "# TODO: one\n# FIXME: two\n")
        code, _, _ = run_cli("--limit", "2", path)
        self.assertEqual(code, 0)
        code, _, _ = run_cli("--limit", "1", path)
        self.assertEqual(code, 1)

    def test_markers_flag(self):
        path = self.write("todo.py", "# TODO: one\n# FIXME: two\n")
        code, out, _ = run_cli("--markers", "TODO", path)
        self.assertEqual(code, 1)
        self.assertIn("TODO", out)
        self.assertNotIn("FIXME", out)

    def test_string_not_flagged(self):
        path = self.write("s.py", 'note = "a todo list"\n')
        code, out, _ = run_cli(path)
        self.assertEqual(code, 0)

    def test_folder_recursive(self):
        self.write("a.py", "# TODO: top\n")
        self.write("sub/b.py", "# FIXME: deep\n")
        code, out, _ = run_cli(str(self.dir))
        self.assertEqual(code, 1)
        self.assertIn("a.py:1", out)
        self.assertIn("b.py:1", out)

    def test_folder_no_recursive(self):
        self.write("a.py", "# TODO: top\n")
        self.write("sub/b.py", "# FIXME: deep\n")
        code, out, _ = run_cli("--no-recursive", str(self.dir))
        self.assertEqual(code, 1)
        self.assertIn("a.py:1", out)
        self.assertNotIn("b.py", out)

    def test_exclude(self):
        self.write("a.py", "# TODO: keep\n")
        self.write("skip.py", "# TODO: skipped\n")
        code, out, _ = run_cli("--exclude", "skip.py", str(self.dir))
        self.assertEqual(code, 1)
        self.assertIn("a.py", out)
        self.assertNotIn("skip.py", out)

    def test_git_folder_skipped(self):
        self.write(".git/hooks/hook.py", "# TODO: in a hook\n")
        self.write("a.py", "x = 1\n")
        code, out, _ = run_cli(str(self.dir))
        self.assertEqual(code, 0)

    def test_binary_skipped(self):
        path = self.dir / "blob.bin"
        path.write_bytes(b"\x00\x01\x02TODO\x00")
        code, out, _ = run_cli(str(path))
        self.assertEqual(code, 0)
        self.assertIn("SKIP", out)

    def test_non_utf8_skipped(self):
        path = self.dir / "bad.txt"
        path.write_bytes(b"# TODO: \xff\xfe broken\n")
        code, out, _ = run_cli(str(path))
        self.assertEqual(code, 0)
        self.assertIn("SKIP", out)

    def test_missing_file(self):
        code, _, err = run_cli(str(self.dir / "nope.py"))
        self.assertEqual(code, 2)
        self.assertIn("no such file", err)

    def test_bad_limit(self):
        path = self.write("a.py", "x = 1\n")
        code, _, err = run_cli("--limit", "-1", path)
        self.assertEqual(code, 2)

    def test_bad_marker(self):
        path = self.write("a.py", "x = 1\n")
        code, _, err = run_cli("--markers", "HACK", path)
        self.assertEqual(code, 2)

    def test_bad_flag(self):
        code, _, _ = run_cli("--nope")
        self.assertEqual(code, 2)

    def test_stdin(self):
        code, out, _ = run_cli("--stdin", stdin_text="# TODO: from stdin\n")
        self.assertEqual(code, 1)
        self.assertIn("FAIL <stdin>:1: TODO: from stdin", out)

    def test_no_paths_reads_stdin(self):
        code, out, _ = run_cli(stdin_text="x = 1\n")
        self.assertEqual(code, 0)

    def test_stdin_and_paths_is_error(self):
        code, _, err = run_cli("--stdin", "a.py")
        self.assertEqual(code, 2)

    def test_json(self):
        path = self.write("todo.py", "# TODO: one\n# FIXME: two\n")
        code, out, err = run_cli("--json", path)
        self.assertEqual(code, 1)
        payload = json.loads(out)
        self.assertEqual(payload["summary"]["found"], 2)
        self.assertTrue(payload["summary"]["over_limit"])
        self.assertEqual(payload["files"][0]["findings"][0]["marker"], "TODO")
        self.assertIn("over the limit", err)

    def test_json_clean(self):
        path = self.write("clean.py", "x = 1\n")
        code, out, err = run_cli("--json", path)
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["summary"]["found"], 0)

    def test_version(self):
        code, out, _ = run_cli("--version")
        self.assertEqual(code, 0)
        self.assertIn("1.0.0", out)

    def test_input_files_unchanged(self):
        path = self.write("todo.py", "# TODO: one\n")
        before = Path(path).read_bytes()
        run_cli(path)
        self.assertEqual(Path(path).read_bytes(), before)

    def test_empty_folder(self):
        code, out, _ = run_cli(str(self.dir))
        self.assertEqual(code, 0)
        self.assertIn("OK", out)


class TestBundledExamples(unittest.TestCase):
    def test_sample_output_matches_fresh_run(self):
        proc = subprocess.run(
            ["sh", "examples/run-example.sh"],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        self.assertEqual(proc.returncode, 0)
        expected = (ROOT / "examples" / "sample-output.txt").read_text()
        self.assertEqual(proc.stdout + proc.stderr, expected)

    def test_readme_quoted_outputs(self):
        readme = (ROOT / "README.md").read_text()
        code, out, _ = run_cli("examples/clean.py")
        self.assertEqual(code, 0)
        self.assertIn("OK — 1 file(s) checked, no markers over the limit.", readme)
        code, out, _ = run_cli("examples/todo.py")
        self.assertEqual(code, 1)
        self.assertIn("FAIL examples/todo.py:5: TODO: retry three times before giving up", readme)
        self.assertIn("Checked 1 file(s), 3 marker(s) in 1 file(s)", readme)

    def test_example_script_exits_zero(self):
        proc = subprocess.run(
            ["sh", "examples/run-example.sh"],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        self.assertEqual(proc.returncode, 0)


class TestHygiene(unittest.TestCase):
    """Placeholder and secret scans.

    The words TODO, FIXME, and XXX are this tool's own job, so they
    appear by design in the source (the marker list), the tests, the
    examples, and the README (which describes the job). The scan below
    therefore allows those words only in that allow-list, and forbids
    them everywhere else. Placeholder phrases ("coming soon", "lorem")
    are forbidden everywhere.
    """

    ALLOWED_MARKER_FILES = {
        ROOT / "src" / "todo_comment_checker.py",
        ROOT / "tests" / "test_todo_comment_checker.py",
        ROOT / "README.md",
    }

    def test_no_placeholder_phrases(self):
        bad = []
        for path in ROOT.rglob("*"):
            if ".git" in path.parts or "__pycache__" in path.parts:
                continue
            if HERE in path.parents:
                continue
            if not path.is_file():
                continue
            text = path.read_text(errors="ignore").lower()
            for phrase in ("coming soon", "lorem"):
                if phrase in text:
                    bad.append(f"{path}: {phrase}")
        self.assertEqual(bad, [])

    def test_marker_words_only_where_they_belong(self):
        bad = []
        for path in ROOT.rglob("*"):
            if ".git" in path.parts or "__pycache__" in path.parts:
                continue
            if not path.is_file():
                continue
            if path in self.ALLOWED_MARKER_FILES:
                continue
            if path.parent == ROOT / "examples":
                continue
            text = path.read_text(errors="ignore")
            for word in ("TODO", "FIXME", "XXX"):
                if word in text:
                    bad.append(f"{path}: {word}")
        self.assertEqual(bad, [])

    def test_no_absolute_local_paths(self):
        bad = []
        for path in ROOT.rglob("*"):
            if ".git" in path.parts or "__pycache__" in path.parts:
                continue
            if HERE in path.parents:
                continue
            if not path.is_file():
                continue
            text = path.read_text(errors="ignore")
            for prefix in ("/home/", "/tmp/"):
                if prefix in text:
                    bad.append(f"{path}: {prefix}")
        self.assertEqual(bad, [])

    def test_stdlib_only(self):
        tree = ast.parse((ROOT / "src" / "todo_comment_checker.py").read_text())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        allowed = {"argparse", "fnmatch", "json", "re", "sys", "pathlib"}
        self.assertEqual(imported - allowed, set())

    def test_gitignore_lists_env_first(self):
        lines = (ROOT / ".gitignore").read_text().splitlines()
        self.assertEqual(lines[0], ".env")

    def test_no_secrets(self):
        bad = []
        for path in ROOT.rglob("*"):
            if ".git" in path.parts or "__pycache__" in path.parts:
                continue
            if HERE in path.parents:
                continue
            if not path.is_file():
                continue
            text = path.read_text(errors="ignore")
            for token in ("API_KEY=", "api_key", "password="):
                if token in text:
                    bad.append(f"{path}: {token}")
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()

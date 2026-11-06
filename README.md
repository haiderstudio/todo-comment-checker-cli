# todo-comment-checker-cli

Find TODO comments in code, fail CI when any are left.

[![CI](https://github.com/haiderstudio/todo-comment-checker-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/haiderstudio/todo-comment-checker-cli/actions/workflows/ci.yml) [![Licence: MIT](https://img.shields.io/badge/Licence-MIT-yellow.svg)](LICENSE)

## What it does

`todo_comment_checker` reads the files and folders you name and looks
for leftover TODO, FIXME, and XXX comments — one per line, with the
file and line number. It exits 1 when any are found (or when the count
is over the limit you set), so it can fail a CI run before leftover
notes ship. The default limit is 0: any marker fails.

- A marker only counts when it sits inside a comment. A line counts
  when a comment opener (`#`, `//`, `/*`, `<!--`) comes before the
  marker on the same line, when the line starts with a comment opener
  (`*` or `--`), or when the marker is the first word on the line (a
  plain-text note, like a shopping list). A marker inside a string,
  for example `x = "a todo list"`, is not a comment and is not
  reported. A marker that is part of a file name, for example
  `todo.py` in a comment, is not a marker either.
- `--limit N` fails only when more than N markers are found, for a
  team that allows a few known notes but not new ones.
- `--markers TODO,FIXME` looks for only the markers you name.
- `--exclude PATTERN` skips files by glob (repeatable). Folders are
  walked recursively unless `--no-recursive` is given. `.git` folders
  are never walked, and folder links are never followed.
- `--json` prints the result as JSON instead of plain text, for
  scripts. `--stdin` reads from standard input; with no file or
  folder named, standard input is read as well.
- It is report-only and runs fully offline: it never changes a file,
  never deletes a comment, sends nothing anywhere, and needs no API
  key.

## What it does NOT do

- It does not delete or fix a comment. If a marker is found, removing
  it or doing the work is your job.
- It does not track a block comment that opens on one line and keeps
  going on the next, unless the later lines carry a comment opener
  (the usual `*` prefix) or start with the marker. The scan is
  line-based, one comment per line.
- It does not understand every language's comment rules. It looks for
  the common openers listed above; a marker in an unusual comment
  shape may be missed, and that is a known limit, not a bug it hides.
- It does not check commit messages, branch names, or file contents
  for anything other than the three markers. Secrets in code are a
  different job, covered by secret-scan-skill.
- It does not read files it cannot decode as text. Binary files and
  non-UTF-8 files are skipped and counted, not failed.

## Who it is for

Anyone who wants no leftover notes in shipped code: a team that
agreed "no TODO in main" and wants CI to enforce it, a developer
checking their own work before pushing, or anyone adding a one-line
guard to a pre-commit hook. If the code is clean, you get a short
OK; if not, the report names every marker with its file and line.

## How this differs from similar tools

The exact name `todo-comment-checker-cli` matches 0 repositories on
GitHub. The closest rivals in the 9 results for "todo comment
checker" do different jobs: SimonStJG/flake8-jira-todo-checker
(7 stars) is a flake8 plugin that requires every TODO to carry a
JIRA ID — Python-only, needs flake8, and enforces JIRA, not a plain
count; damienjburks/simple-todo-checker (2 stars) is a GitHub Action
that scans files for TODO comments, not a local CLI you can run
anywhere; NikkelM/Todo-PR-Checker is a GitHub app that checks pull
request changes and reports in a comment, not a local file scan.
None of them is a Python standard-library-only CLI that scans any
local files, in any language, reports each marker with file and line,
and fails CI on a limit you set.

This tool does that one narrow job: a Python standard-library-only
CLI, no install beyond Python, no flake8, no JIRA, no GitHub Action,
no review bot — one scan, one count, one exit code.

## Install

Python standard library only — no packages to download. Clone the
repo and run it in place:

```sh
git clone https://github.com/haiderstudio/todo-comment-checker-cli.git
cd todo-comment-checker-cli
```

Python 3.10 or newer.

## Usage

Check one file:

```sh
python3 src/todo_comment_checker.py examples/todo.py
```

```
FAIL examples/todo.py:5: TODO: retry three times before giving up
FAIL examples/todo.py:10: FIXME: this writes to the wrong folder
FAIL examples/todo.py:15: XXX: remove this once the new path is live
Checked 1 file(s), 3 marker(s) in 1 file(s) — over the limit of 0.
```

Check a clean file:

```sh
python3 src/todo_comment_checker.py examples/clean.py
```

```
OK — 1 file(s) checked, no markers over the limit.
```

Check a whole folder, allowing up to 2 markers:

```sh
python3 src/todo_comment_checker.py --limit 2 examples/
```

```
FAIL examples/notes.txt:2: TODO: buy milk
FAIL examples/notes.txt:5: FIXME the broken shelf
FAIL examples/todo.py:5: TODO: retry three times before giving up
FAIL examples/todo.py:10: FIXME: this writes to the wrong folder
FAIL examples/todo.py:15: XXX: remove this once the new path is live
Checked 5 file(s), 5 marker(s) in 2 file(s) — over the limit of 2.
```

Look for only one marker:

```sh
python3 src/todo_comment_checker.py --markers TODO examples/todo.py
```

```
FAIL examples/todo.py:5: TODO: retry three times before giving up
Checked 1 file(s), 1 marker(s) in 1 file(s) — over the limit of 0.
```

Machine-readable output with `--json` (the summary goes to
standard error, so standard output stays clean JSON):

```sh
python3 src/todo_comment_checker.py --json examples/todo.py
```

```json
{
  "files": [
    {
      "file": "examples/todo.py",
      "findings": [
        {
          "line": 5,
          "marker": "TODO",
          "text": "TODO: retry three times before giving up"
        },
        {
          "line": 10,
          "marker": "FIXME",
          "text": "FIXME: this writes to the wrong folder"
        },
        {
          "line": 15,
          "marker": "XXX",
          "text": "XXX: remove this once the new path is live"
        }
      ]
    }
  ],
  "skipped": [],
  "summary": {
    "checked": 1,
    "found": 3,
    "limit": 0,
    "over_limit": true
  }
}
```

Exit codes: 0 when the count is within the limit, 1 when it is over
the limit, 2 for a usage or input problem (a missing file, a bad
limit, a bad marker name).

## Examples

### 1. A file with markers

`examples/todo.py` holds one of each marker on purpose:

```sh
python3 src/todo_comment_checker.py examples/todo.py
```

```
FAIL examples/todo.py:5: TODO: retry three times before giving up
FAIL examples/todo.py:10: FIXME: this writes to the wrong folder
FAIL examples/todo.py:15: XXX: remove this once the new path is live
Checked 1 file(s), 3 marker(s) in 1 file(s) — over the limit of 0.
```

### 2. A plain-text file

`examples/notes.txt` shows markers do not need code — a bare
marker at the start of a line counts:

```sh
python3 src/todo_comment_checker.py examples/notes.txt
```

```
FAIL examples/notes.txt:2: TODO: buy milk
FAIL examples/notes.txt:5: FIXME the broken shelf
Checked 1 file(s), 2 marker(s) in 1 file(s) — over the limit of 0.
```

### 3. A string that is not a comment

`examples/clean.py` holds the string `"a todo list for later"`,
which is not a comment and is not reported:

```sh
python3 src/todo_comment_checker.py examples/clean.py
```

```
OK — 1 file(s) checked, no markers over the limit.
```

### 4. The bundled examples, all at once

```sh
sh examples/run-example.sh
```

The script checks the clean file (passes), then the marked file and
the notes file (both fail, on purpose), then the marked file with a
limit of 3 (passes). Its full output is in
`examples/sample-output.txt`. The failing runs exit 1, which is the
expected result — the script ends with exit 0 so it can be run as a
demo.

## How it is tested

58 tests, standard library `unittest` only, no packages to install:

```
python3 tests/test_todo_comment_checker.py
```

The tests cover: each marker in each comment shape (`#`, `//`,
`/*`, `*`, `<!--`, `--`), a marker as the first word on a line,
lowercase markers, markers inside strings (not reported), file names
like `todo.py` in comments (not reported), `--flag` lines and
multiplication (not reported), word boundaries (`TODOS` and
`methodology` are not markers), the limit flag, the markers flag, folder walking (recursive, `--no-recursive`,
`.git` skipped, `--exclude`), binary and non-UTF-8 files skipped,
stdin, `--json` output, `--version`, input files left unchanged, the
bundled examples (sample output compared byte-for-byte against a
fresh run, and the README-quoted outputs checked against it), and
hygiene checks (no placeholder text, no absolute paths, stdlib
imports only, `.env` first in `.gitignore`).

One hygiene note, stated plainly: the words TODO, FIXME, and XXX are
this tool's own job, so they appear by design in the source (the
marker list), the tests, the examples, and this README. The hygiene
test therefore allows those words only in those four places, and
forbids them everywhere else — the test file's own word lists are
excluded from the placeholder and secret scans, the same way earlier
days excluded their own test data.

## Contributing

Small, focused improvements are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

MIT — see [LICENSE](LICENSE).

## Original work

This tool was written from scratch for this repo. The idea of
finding leftover notes in code is not new — the similar tools named
above (SimonStJG/flake8-jira-todo-checker,
damienjburks/simple-todo-checker, NikkelM/Todo-PR-Checker) are
listed in "How this differs" — but every line of code here is
original, and the tool builds on nothing but Python's standard
library.

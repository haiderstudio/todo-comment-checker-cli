#!/usr/bin/env python3
"""Find TODO comments in code, fail CI when any are left.

Run: python3 src/todo_comment_checker.py src/
     python3 src/todo_comment_checker.py --limit 2 src/ tests/
     python3 src/todo_comment_checker.py --markers TODO,FIXME app.py
     cat file.py | python3 src/todo_comment_checker.py

The tool reads the files and folders you name and looks for leftover
TODO, FIXME, and XXX comments — one per line, with the file and line
number. It exits 1 when any are found (or when the count is over the
limit you set with --limit), so it can fail a CI run before leftover
notes ship. The default limit is 0: any marker fails.

A marker only counts when it sits inside a comment. A line counts
when a comment opener (#, //, /*, <!--) comes before the marker on
the same line, when the line starts with a comment opener (* or --),
or when the marker is the first word on the line (a plain-text note,
like a TODO list). A marker inside a string, for example
x = "a todo list", is not a comment and is not reported. A marker
that is part of a file name, for example todo.py in a comment, is
not a marker either. The scan is line-based: it does not track a
block comment that opens on one line and keeps going on the next,
unless the later lines carry a comment opener (the usual * prefix)
or start with the marker.

It is report-only: it never changes a file, never deletes a comment,
sends nothing anywhere, and needs no API key. It runs fully offline.

Exit codes: 0 when the count is within the limit, 1 when it is over
the limit, 2 for a usage or input problem (a missing file, a bad
limit, a bad marker name).

Python standard library only.
"""

import argparse
import fnmatch
import json
import re
import sys
from pathlib import Path

VERSION = "1.0.0"
DEFAULT_LIMIT = 0
MARKERS = ("TODO", "FIXME", "XXX")
# Openers that count anywhere before the marker on the line.
OPENERS_ANYWHERE = ("#", "//", "/*", "<!--")
# Openers that count only at the start of the line: a * mid-line is
# usually multiplication, and -- mid-line is usually a flag.
OPENERS_LINE_START = ("*", "--")


class InputError(Exception):
    """A problem with the input (missing file, bad flag value)."""


def marker_pattern(markers):
    """A regex matching any of the markers as a whole word."""
    return re.compile(r"\b(" + "|".join(re.escape(m) for m in markers) + r")\b", re.IGNORECASE)


def find_markers_in_line(line, pattern):
    """Find the markers on one line that sit inside a comment.

    Returns a list of dicts, one per marker found:
    {"marker": str, "text": str} — marker in upper case, text is the
    rest of the line from the marker onward, stripped.
    """
    found = []
    starts_with_comment = line.lstrip().startswith(OPENERS_LINE_START)
    for match in pattern.finditer(line):
        end = match.end()
        # A marker followed by "." and a letter is part of a file
        # name (todo.py), not a marker.
        if end + 1 < len(line) and line[end] == "." and line[end + 1].isalpha():
            continue
        before = line[: match.start()]
        if before.strip() == "":
            counts = True
        elif starts_with_comment:
            counts = True
        else:
            counts = any(opener in before for opener in OPENERS_ANYWHERE)
        if counts:
            found.append(
                {"marker": match.group(1).upper(), "text": line[match.start() :].strip()}
            )
    return found


def check_text(text, pattern):
    """Check one file's text. Returns a list of findings, one per marker:
    {"line": int, "marker": str, "text": str}."""
    findings = []
    for number, line in enumerate(text.splitlines(), start=1):
        for hit in find_markers_in_line(line, pattern):
            findings.append({"line": number, "marker": hit["marker"], "text": hit["text"]})
    return findings


def read_file(path):
    """Read a file as text. Returns (text, skipped) — skipped is True
    when the file cannot be read as text (binary, or not UTF-8)."""
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None, True
    if b"\x00" in data:
        return None, True
    try:
        return data.decode("utf-8"), False
    except UnicodeDecodeError:
        return None, True


def collect_files(paths, recursive, exclude):
    """Collect the files to check from files and folders.

    Folders are walked recursively unless --no-recursive is given.
    .git folders are never walked, and folder links are never
    followed, so a link cycle cannot loop the check. Files matching
    an --exclude glob (by name or by path) are skipped.
    Returns a sorted list of Path objects.
    """
    found = []
    for raw in paths:
        path = Path(raw)
        if path.is_file():
            found.append(path)
        elif path.is_dir():
            if recursive:
                for item in sorted(path.rglob("*")):
                    if ".git" in item.parts:
                        continue
                    if item.is_symlink() and item.is_dir():
                        continue
                    if item.is_file():
                        found.append(item)
            else:
                for item in sorted(path.iterdir()):
                    if item.is_file():
                        found.append(item)
        else:
            raise InputError(f"no such file or folder: {raw}")
    kept = []
    for path in found:
        name = path.name
        full = str(path)
        if any(fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(full, pat) for pat in exclude):
            continue
        kept.append(path)
    return sorted(set(kept))


def check_files(files, pattern):
    """Check a list of files. Returns (results, skipped) where results
    is a list of {"file": str, "findings": [...]} for every file, and
    skipped is a list of files that could not be read as text."""
    results = []
    skipped = []
    for path in files:
        text, was_skipped = read_file(path)
        if was_skipped:
            skipped.append(str(path))
            continue
        results.append({"file": str(path), "findings": check_text(text, pattern)})
    return results, skipped


def parse_markers(value):
    """Parse --markers VALUE (comma-separated) into upper-case names.
    Raises InputError on an unknown marker."""
    names = [name.strip().upper() for name in value.split(",") if name.strip()]
    if not names:
        raise InputError("no markers given in --markers")
    bad = [name for name in names if name not in MARKERS]
    if bad:
        raise InputError(f"unknown marker(s): {', '.join(bad)} (use TODO, FIXME, XXX)")
    seen = []
    for name in names:
        if name not in seen:
            seen.append(name)
    return tuple(seen)


def parse_limit(value):
    """Parse --limit VALUE into a non-negative integer."""
    try:
        number = int(value)
    except ValueError:
        raise InputError(f"bad limit '{value}' — use a whole number, 0 or more")
    if number < 0:
        raise InputError(f"bad limit '{value}' — use a whole number, 0 or more")
    return number


def parse_args(argv):
    """Parse the command line. Returns (args, error) — error is a
    message string, or None when parsing worked."""
    parser = argparse.ArgumentParser(
        prog="todo_comment_checker",
        description="Find TODO comments in code, fail CI when any are left.",
    )
    parser.add_argument("paths", nargs="*", help="files or folders to check")
    parser.add_argument(
        "--limit",
        default=str(DEFAULT_LIMIT),
        help="fail only when more than this many markers are found (default 0)",
    )
    parser.add_argument(
        "--markers",
        default=",".join(MARKERS),
        help="comma-separated markers to look for: TODO, FIXME, XXX (default all three)",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="PATTERN",
        help="skip files matching this glob (repeatable)",
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="when a folder is given, check only its top level",
    )
    parser.add_argument(
        "--stdin", action="store_true", help="read from standard input instead of files"
    )
    parser.add_argument("--json", action="store_true", help="print the result as JSON")
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return None, exc.code
    try:
        args.limit = parse_limit(args.limit)
        args.markers = parse_markers(args.markers)
    except InputError as exc:
        return None, str(exc)
    if args.stdin and args.paths:
        return None, "use --stdin on its own, without file or folder paths"
    return args, None


def run(argv):
    """Run the checker. Returns an exit code: 0 within the limit,
    1 over the limit, 2 for a usage or input problem."""
    args, error = parse_args(argv)
    if error is not None:
        if isinstance(error, int):
            return error
        print(f"error: {error}", file=sys.stderr)
        return 2

    pattern = marker_pattern(args.markers)

    if args.stdin:
        text = sys.stdin.read()
        results = [{"file": "<stdin>", "findings": check_text(text, pattern)}]
        skipped = []
        checked = 1
    else:
        if not args.paths:
            text = sys.stdin.read()
            results = [{"file": "<stdin>", "findings": check_text(text, pattern)}]
            skipped = []
            checked = 1
        else:
            try:
                files = collect_files(args.paths, not args.no_recursive, args.exclude)
            except InputError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            results, skipped = check_files(files, pattern)
            checked = len(results) + len(skipped)

    total = sum(len(item["findings"]) for item in results)
    over = total > args.limit

    if args.json:
        payload = {
            "files": results,
            "skipped": skipped,
            "summary": {
                "checked": checked,
                "found": total,
                "limit": args.limit,
                "over_limit": over,
            },
        }
        print(json.dumps(payload, indent=2))
        if over:
            files_with = sum(1 for item in results if item["findings"])
            print(
                f"Checked {checked} file(s), {total} marker(s) in {files_with} file(s) — "
                f"over the limit of {args.limit}.",
                file=sys.stderr,
            )
        else:
            print(
                f"OK — {checked} file(s) checked, no markers over the limit.",
                file=sys.stderr,
            )
    else:
        for item in results:
            for hit in item["findings"]:
                print(f"FAIL {item['file']}:{hit['line']}: {hit['text']}")
        for name in skipped:
            print(f"SKIP {name}: not readable as text")
        # Plain mode prints the summary on standard output, after the
        # findings, so a merged capture reads in order. JSON mode keeps
        # the summary on standard error so standard output stays clean.
        if over:
            files_with = sum(1 for item in results if item["findings"])
            print(
                f"Checked {checked} file(s), {total} marker(s) in {files_with} file(s) — "
                f"over the limit of {args.limit}."
            )
        else:
            print(f"OK — {checked} file(s) checked, no markers over the limit.")
    return 1 if over else 0


def main():
    """Entry point."""
    sys.exit(run(sys.argv[1:]))


if __name__ == "__main__":
    main()

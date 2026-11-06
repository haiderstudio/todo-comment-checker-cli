#!/bin/sh
# Run the checker on the bundled examples.
# Run from the repo root: sh examples/run-example.sh
# The todo.py and notes.txt runs exit 1 because they hold markers on
# purpose — that is the expected result here.
set -e
cd "$(dirname "$0")/.."
echo "--- clean file ---"
python3 src/todo_comment_checker.py examples/clean.py
echo "--- file with markers ---"
python3 src/todo_comment_checker.py examples/todo.py || true
echo "--- plain-text notes ---"
python3 src/todo_comment_checker.py examples/notes.txt || true
echo "--- same file, limit 3 ---"
python3 src/todo_comment_checker.py --limit 3 examples/todo.py

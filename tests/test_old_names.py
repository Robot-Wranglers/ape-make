"""Pins retired builtin names out of the tracked sources.

The persistent builtins became the kept-state operations, so no tracked file calls
`.persistent`; test_namespace.py names it on purpose, to pin that the grammar leaves it
unregistered.
"""

import re
import subprocess
from pathlib import Path

here = Path(__file__).resolve()
allowed = {here, here.parent / "test_namespace.py"}


def test_no_tracked_source_calls_the_old_name():
  root = here.parents[1]
  tracked = subprocess.run(["git", "-C", str(root), "ls-files"], capture_output=True, text=True, check=True).stdout.split()
  old = re.compile(r"\.persistent\b")
  hits = []
  for name in tracked:
    path = root / name
    if path in allowed or not path.is_file():
      continue
    try:
      text = path.read_text()
    except UnicodeDecodeError:
      continue
    hits += [f"{name}:{i}" for i, line in enumerate(text.splitlines(), 1) if old.search(line)]
  assert hits == [], hits

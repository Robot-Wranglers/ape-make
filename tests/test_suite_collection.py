"""Pins that the whole suite collects as one directory.

A conftest under a subdirectory must not shadow the suite's own conftest or deselect the
suite's tests, so a run over the tests directory collects every file without an error and
selects tests to run. The perf cells under tests/perf run by their path, never by recursion.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

TESTS = Path(__file__).resolve().parent


def test_the_whole_directory_collects_without_errors_and_selects_tests():
  r = subprocess.run([sys.executable, "-m", "pytest", str(TESTS), "--collect-only", "-q", "-p", "no:cacheprovider"],
                     cwd=TESTS.parent, capture_output=True, text=True, timeout=120, env=os.environ)
  out = r.stdout + r.stderr
  assert r.returncode == 0, out[-3000:]
  assert "error" not in out.splitlines()[-1], out[-3000:]
  selected = re.search(r"(\d+)(?:/\d+)? tests? collected", out)
  assert selected and int(selected.group(1)) > 0, out[-3000:]
  assert "tests/perf/" not in out, out[-3000:]

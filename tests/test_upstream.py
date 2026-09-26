"""Runs GNU make's own regression suite against the artifact and pins the pass counts.

Upstream's perl runner drives the suite under src/make-<version>/tests; it checks stock
make, so the prelude is skipped through `AMK_NO_PRELUDE`, and amk is not expected to pass
all of it. The baseline in fixtures/make-suite.txt holds `name passed/total` per script,
and a run regresses when any script passes fewer. The log lands in build/make-suite.log
and the summary in build/make-suite.txt; copy the summary over the baseline to accept a change.
"""

import os
import re
import shutil
import subprocess

import pytest
from conftest import AMK_DIR, HERE

BASELINE = HERE / "fixtures" / "make-suite.txt"
LOG = AMK_DIR / "build" / "make-suite.log"
SUMMARY = AMK_DIR / "build" / "make-suite.txt"

RESULT = re.compile(
  r"^(\S+/\S+) \.{3,}.*?(?:ok\s+\((\d+) passed\)|FAILED \((\d+)/(\d+) passed\)|N/A)",
  re.M | re.S,
)


def parse(log):
  """Script name to (passed, total); a script the build leaves out is (None, None)."""
  out = {}
  for name, ok, passed, total in RESULT.findall(log):
    if ok:
      out[name] = (int(ok), int(ok))
    elif total:
      out[name] = (int(passed), int(total))
    else:
      out[name] = (None, None)
  return out


def render(results):
  return "".join(
    f"{name} {'n/a' if p is None else f'{p}/{t}'}\n" for name, (p, t) in sorted(results.items())
  )


@pytest.mark.upstream
def test_upstream_suite_does_not_regress(amk, tmp_path):
  src = next(AMK_DIR.glob("src/make-*"), None)
  if src is None or not (src / "tests" / "run_make_tests.pl").exists():
    pytest.skip("no patched make source under src/ (run make patch in via/amk)")
  if not shutil.which("perl"):
    pytest.skip("the upstream suite needs perl")
  # The driver resets the environment to its own whitelist, so the switch rides in a wrapper that also names itself as MAKE.
  wrapper = tmp_path / amk.name
  wrapper.write_text(f'#!/bin/sh\nexport AMK_NO_PRELUDE=1 MAKE="$0"\nexec "{amk}" "$@"\n')
  wrapper.chmod(0o755)
  r = subprocess.run(
    ["perl", "./run_make_tests.pl", "-srcdir", str(src), "-make", str(wrapper)],
    cwd=src / "tests", capture_output=True, text=True, timeout=3600,
  )
  LOG.parent.mkdir(exist_ok=True)
  LOG.write_text(r.stdout + r.stderr)
  got = parse(r.stdout)
  assert got, f"no results parsed from the runner: {r.stderr[-800:]}"
  SUMMARY.write_text(render(got))
  if not BASELINE.exists():
    pytest.fail(f"no baseline at {BASELINE}; review {SUMMARY} and copy it there")
  want = parse_summary(BASELINE.read_text())
  worse = {
    name: (want[name][0], got[name][0])
    for name in want
    if name in got and want[name][0] is not None and (got[name][0] or 0) < want[name][0]
  }
  missing = sorted(set(want) - set(got))
  assert not worse and not missing, (
    "upstream suite regressed; see build/make-suite.log\n"
    + "".join(f"  {n}: baseline {a} passed, now {b}\n" for n, (a, b) in sorted(worse.items()))
    + "".join(f"  {n}: no longer reported\n" for n in missing)
  )


def parse_summary(text):
  out = {}
  for line in text.split("\n"):
    if not line.strip():
      continue
    name, score = line.split()
    out[name] = (None, None) if score == "n/a" else tuple(int(x) for x in score.split("/"))
  return out

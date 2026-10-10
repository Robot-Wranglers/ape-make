"""Pins the tuple space demo.

Four workers in four languages take candidates from one sqlite workspace under -j4 through
one atomic pattern match, a shell worker on the call channel and three engine workers
through amk.call. Pinned: the primes are right, every candidate is taken exactly once, the
work spreads over more than one worker, and no file is written.
"""

import re

import pytest

from conftest import sh

REPO = __import__("pathlib").Path(__file__).resolve().parent.parent
DEMO = REPO / "demos" / "tuple-space.mk"
PRIMES = [n for n in range(2, 61) if all(n % d for d in range(2, int(n ** 0.5) + 1))]


@pytest.mark.engines("sqlite", "awk", "lua", "micropy", "js")
def test_four_workers_share_one_space_atomically(amk, tmp_path):
  r = sh(amk, ["-j4", "-f", str(DEMO)], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  primes = [int(x) for x in re.search(r"primes: (.*)", r.stdout).group(1).split()]
  assert primes == PRIMES, r.stdout
  assert "left: 0" in r.stdout, r.stdout
  who = re.findall(r'"who":"(\w+)","n":(\d+)', r.stdout)
  assert sum(int(n) for _, n in who) == len(PRIMES), r.stdout
  assert len(who) > 1, r.stdout
  assert not [p for p in tmp_path.iterdir()], list(tmp_path.iterdir())


@pytest.mark.engines("sqlite")
def test_a_take_on_an_empty_space_answers_nothing(amk, tmp_path):
  mk = tmp_path / "empty.mk"
  mk.write_text("\n".join([
    "SHELL := bash",
    f"include {DEMO}",
    "probe:",
    "\t@${ts.sh} ; t=$$(ts inp '[\"nothing\",\"_\"]') ; echo \"got=[$$t] st=$$?\"",
    "",
  ]))
  r = sh(amk, ["-f", str(mk), "probe"], cwd=tmp_path, timeout=60)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "got=[] st=0" in r.stdout, r.stdout + r.stderr

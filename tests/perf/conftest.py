"""The engine's own perf cells: a program run bare by the binary, timed over a few reps,
with the function profile of one further run as its counts.

Every test here carries the perf marker without naming it, so the gate leaves this
directory out. `bench.file(path)` runs a program in place and `bench.run(body, goal)` one
the test wrote; each answers the output and one `Observation`, recorded as a json line in
`tests/.perf-results/perf.jsonl`. `AMK_PERF_REPS=3` makes a record worth comparing.
"""

import importlib.util
import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pytest

# The suite's own conftest, by path, since this file shadows its name on the import path.
_spec = importlib.util.spec_from_file_location("amk_conftest", Path(__file__).resolve().parents[1] / "conftest.py")
_suite = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_suite)
AMK_DIR, sh = _suite.AMK_DIR, _suite.sh

RESULTS = AMK_DIR / "tests" / ".perf-results"
HEADER = re.compile(r"^# amk profile pid=\d+ wall=(\d+\.\d+)s names=\d+$", re.M)
ROW = re.compile(r"^\s*(\d+\.\d+)\s+(\d+\.\d+)\s+(\d+)\s+(\S+) (\S+)$", re.M)


def pytest_collection_modifyitems(config, items):
  for item in items:
    item.add_marker(pytest.mark.perf)


@dataclass
class Observation:
  """One cell's measurement: who ran it, what it ran, and what the run cost."""
  test: str
  goal: str
  count: int
  tags: dict
  reps: int
  best_s: float
  wall_s: float
  calls: dict = field(default_factory=dict)
  totals: dict = field(default_factory=dict)

  def record(self):
    return {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **self.__dict__}

  def name(self):
    tags = "".join(f" {k}={v}" for k, v in sorted(self.tags.items()))
    return f"{self.test} goal={self.goal} count={self.count}{tags}"

  def line(self):
    return f"[bench] {self.name()} best={self.best_s:.3f}s reps={self.reps} calls={sum(self.calls.values())}"


@dataclass
class Result:
  stdout: str
  stderr: str
  returncode: int
  observation: Observation

  def __post_init__(self):
    self.ok = self.returncode == 0


def profile(text):
  """Calls and total milliseconds by `kind name`, summed over every table in the file, one per process."""
  calls, totals = {}, {}
  for _, t, c, kind, name in ROW.findall(text):
    key = f"{kind} {name}"
    calls[key] = calls.get(key, 0) + int(c)
    totals[key] = totals.get(key, 0.0) + float(t)
  return calls, totals


@pytest.fixture
def bench(amk, tmp_path, request):
  reps = int(os.environ.get("AMK_PERF_REPS") or 1)
  test = f"{Path(request.node.fspath).name}::{request.node.originalname or request.node.name}"
  params = getattr(request.node, "callspec", None)
  tags = {k: v for k, v in (params.params.items() if params else ()) if isinstance(v, (str, int, float, bool))}

  def _cell(path, goal, count, cwd):
    args = ["-f", str(path), *([goal] if goal else [])]
    times = []
    for _ in range(reps):
      t0 = time.perf_counter()
      r = sh(amk, args, cwd=cwd, timeout=600)
      times.append(time.perf_counter() - t0)
      assert r.returncode == 0, f"{path.name} {goal or ''} failed\n{(r.stdout + r.stderr)[-2000:]}"
    log = tmp_path / f"profile{len(times)}.txt"
    p = sh(amk, args, cwd=cwd, env={"AMK_PROFILE": str(log)}, timeout=600)
    text = log.read_text() if log.exists() else ""
    calls, totals = profile(text)
    wall = HEADER.search(text)
    o = Observation(test=test, goal=goal or "", count=count, tags={**tags, **({"file": path.stem} if cwd != tmp_path else {})},
                    reps=reps, best_s=min(times), wall_s=float(wall.group(1)) if wall else min(times),
                    calls=calls, totals=totals)
    RESULTS.mkdir(exist_ok=True)
    with (RESULTS / "perf.jsonl").open("a") as out:
      out.write(json.dumps(o.record()) + "\n")
    print(o.line())
    return Result(r.stdout, r.stderr + p.stderr, r.returncode, o)

  class Bench:
    def run(self, body, goal=None, count=0):
      src = tmp_path / "program.amk"
      src.write_text(body if body.endswith("\n") else body + "\n")
      return _cell(src, goal, count, tmp_path)

    def file(self, path, goal=None, count=0):
      path = Path(path)
      return _cell(path, goal, count, path.parent)

  return Bench()

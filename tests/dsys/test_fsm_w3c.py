"""Runs the W3C scxml conformance core groups through lxsc and through the fsm lowering.

The corpus is tests/fixtures/w3c/core.json, written by `make -C via/amk w3c`. lxsc runs each
document with its own harness: started, stepped until both queues are empty, passing when the
final state pass is active. The lowering loads each document as a .scxml file and is classified
as lowered or refused by the construct named in the refusal. The tally is the pin, so a construct
newly lowered moves a count; agreement with lxsc on what lowers waits on the runner.
"""

import json
import re
from collections import Counter
from pathlib import Path

import pytest

from conftest import sh

CORPUS = Path(__file__).resolve().parents[1] / "fixtures" / "w3c" / "core.json"
pytestmark = pytest.mark.engines("lua", "jq")

HARNESS = [
  "@lua.target", "define harness",
  '  local m = require("lxsc"):parse(amk.var["doc"])',
  "  m:start{data={tonumber=tonumber}}",
  "  function m:elapsed() local last = self._delayedSend[#self._delayedSend]; return last and last.expires + 1 or 0 end",
  "  local steps = 0",
  "  repeat m:step(); steps = steps + 1 until steps > 1000 or (#m._internalQueue == 0 and #m._externalQueue == 0)",
  '  print("LXSC " .. (m:activeStateIds().pass and "pass" or "fail") .. " " .. table.concat(m:activeAtomicIds(), ","))',
  "endef",
]

# lxsc's implementation report: 178 failed on its datamodel, 422 needs invoke; the rest of these groups passed.
LXSC_NOT_PASSING = {"test178", "test422"}


def corpus():
  if not CORPUS.exists():
    pytest.skip("no corpus; run make -C via/amk w3c")
  return json.loads(CORPUS.read_text())


def reason(stderr):
  for pattern, name in [
    (r"(\w+) is outside the subset", None),
    (r"does not meet schema/fsm.json", "schema"),
    (r"guard .* is not lowered|guarded alternatives|is an expression, not a name|needs an unguarded alternative", "guard"),
    (r"invoke inside a parallel", "invoke"),
    (r"nested final", "nested final"),
    (r"is a wildcard", "wildcard"),
    (r"Cannot iterate|null \(null\)", "crash"),
    (r"target \S+ is no state", "target"),
    (r"a parallel state inside", "nested parallel"),
    (r"final states", "finals"),
    (r"targets, not 1|initial \S+ \S+.* is no state", "targets"),
    (r"initial names no state|is no state", "initial"),
    (r"lxsc.lua:\d+:", "lxsc"),
  ]:
    m = re.search(pattern, stderr)
    if m:
      return name or m[1]
  return "other"


def run(amk, tmp_path, name, doc, lowering):
  lines = ["load dsys/fsm", "define doc", doc, "endef"] + HARNESS
  if lowering:
    (tmp_path / f"{name}.scxml").write_text(doc)
    lines += [f"load {tmp_path}/{name}.scxml"]
  lines += ["show: harness", "\t@true", ""]
  mk = tmp_path / f"{name}.mk"
  mk.write_text("\n".join(lines))
  return sh(amk, ["-s", "-f", str(mk), "show"], cwd=tmp_path, timeout=120)


def test_lxsc_passes_the_core_groups_as_its_report_says(amk, tmp_path):
  results = {}
  for name, t in corpus().items():
    if t["manual"]:
      continue
    r = run(amk, tmp_path, name, t["scxml"], lowering=False)
    line = next((ln for ln in r.stdout.splitlines() if ln.startswith("LXSC ")), f"LXSC crash {r.stderr[-200:]}")
    results[name] = line.split()[1]
  failing = sorted(n for n, v in results.items() if v != "pass")
  assert failing == sorted(LXSC_NOT_PASSING & set(results)), results


def test_the_lowering_takes_what_it_lowers_and_names_what_it_refuses(amk, tmp_path):
  outcomes = {}
  for name, t in corpus().items():
    r = run(amk, tmp_path, name, t["scxml"], lowering=True)
    outcomes[name] = "lowered" if r.returncode == 0 else reason(r.stderr)
    if outcomes[name] == "other":
      outcomes[name] = "other: " + (r.stderr.strip().splitlines() or [""])[-1][-160:]
  tally = Counter(v.split(":")[0] for v in outcomes.values())
  assert "other" not in tally, {n: v for n, v in outcomes.items() if v.startswith("other")}
  assert tally["lowered"] >= 0 and sum(tally.values()) == len(corpus()), tally
  print("w3c core:", dict(tally))

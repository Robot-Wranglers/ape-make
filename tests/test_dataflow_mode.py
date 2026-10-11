"""Pins the dataflow mode, and the make behaviour it is built on.

The premises pass today. A dependent stays up to date when its prerequisite's recipe ran but put
the old mtime back, which is how early cutoff avoids a freshness patch, and an imported target
is phony, so a file of its name never satisfies it. The rest waits on the mode: a failed value
moves aside with its stderr, a file that existed before a failed recipe survives, identical
output stops downstream, a body edit reruns its value, and the record lists declared inputs only.
"""

import json
import os
import time

import pytest

from conftest import sh

pending = pytest.mark.xfail(strict=True, reason="fa05d9d073: the dataflow mode")


def build(amk, tmp_path, text, goal, env=None):
  (tmp_path / "df.mk").write_text(text + "\n")
  return sh(amk, ["-s", "-f", "df.mk", goal], cwd=tmp_path, env=env, timeout=120)


def counted(name):
  return f"local f = io.open('{name}.count', 'a') f:write('x\\n') f:close()"


def count(tmp_path, name):
  path = tmp_path / f"{name}.count"
  return len(path.read_text().splitlines()) if path.exists() else 0


def test_a_restored_mtime_does_not_rerun_a_dependent(amk, tmp_path):
  text = "\n".join([
    "mid: src",
    "\ttouch -r mid mid.ref; printf same > mid; touch -r mid.ref mid",
    "out: mid",
    "\techo ran >> out.log; cp mid out",
  ])
  for name, age in (("mid", 300), ("out", 200), ("src", 100)):
    (tmp_path / name).write_text("same")
    stamp = time.time() - age
    os.utime(tmp_path / name, (stamp, stamp))
  r = build(amk, tmp_path, text, "out")
  assert r.returncode == 0, r.stdout + r.stderr
  assert (tmp_path / "mid.ref").exists(), "the prerequisite's recipe did not run"
  assert not (tmp_path / "out.log").exists(), "the dependent reran on a restored mtime"


@pytest.mark.engines("lua")
def test_a_file_of_an_imported_targets_name_never_satisfies_it(amk, tmp_path):
  text = "\n".join([
    "@lua.import.target",
    "define listing",
    counted("listing"),
    "print('fresh')",
    "endef",
  ])
  (tmp_path / "listing").write_text("stale\n")
  r = build(amk, tmp_path, text, "listing")
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "fresh", r.stdout
  assert count(tmp_path, "listing") == 1


@pending
@pytest.mark.engines("lua")
def test_a_failed_value_is_moved_aside_with_its_stderr(amk, tmp_path):
  text = "\n".join([
    "$(amk.mode dataflow)",
    "amk.dataflow_dir := values",
    "@lua.import.target",
    "define up",
    "print('partial')",
    "io.stderr:write('why it failed\\n')",
    "error('boom')",
    "endef",
    "@lua.import.target",
    "define down",
    counted("down"),
    "print('got [@up@]')",
    "endef",
  ])
  r = build(amk, tmp_path, text, "down")
  assert r.returncode != 0, r.stdout
  values = tmp_path / "values"
  assert not (values / "up").exists(), "the failed value was left in place"
  assert (values / "up.failed").read_text().startswith("partial")
  assert "why it failed" in (values / "up.err").read_text()
  assert count(tmp_path, "down") == 0, "the downstream ran on a failed upstream"


@pending
def test_a_failed_recipe_keeps_a_file_that_existed_before(amk, tmp_path):
  text = "\n".join([
    "$(amk.mode dataflow)",
    "page.md:",
    "\tprintf half > $@; false",
    "made.md:",
    "\tprintf half > $@; false",
  ])
  (tmp_path / "page.md").write_text("hand-written\n")
  assert build(amk, tmp_path, text, "page.md").returncode != 0
  assert (tmp_path / "page.md").read_text() == "hand-written\n"
  assert build(amk, tmp_path, text, "made.md").returncode != 0
  assert not (tmp_path / "made.md").exists(), "a file the run created survived its failure"


@pending
@pytest.mark.engines("lua")
def test_identical_output_stops_downstream(amk, tmp_path):
  text = "\n".join([
    "$(amk.mode dataflow)",
    "amk.dataflow_dir := values",
    "input.txt: ;",
    "@lua.import.target",
    "define parity",
    "print(tonumber(io.open('input.txt'):read('a')) % 2)",
    "endef",
    "parity: input.txt",
    "@lua.import.target",
    "define report",
    counted("report"),
    "print('parity @parity@')",
    "endef",
  ])
  (tmp_path / "input.txt").write_text("3")
  assert build(amk, tmp_path, text, "report").returncode == 0
  time.sleep(1.1)
  (tmp_path / "input.txt").write_text("5")
  r = build(amk, tmp_path, text, "report")
  assert r.returncode == 0, r.stdout + r.stderr
  assert count(tmp_path, "report") == 1, "an identical upstream value reran its dependent"


@pending
@pytest.mark.engines("awk")
def test_a_body_edit_reruns_its_value(amk, tmp_path):
  def text(n):
    return "\n".join([
      "$(amk.mode dataflow)",
      "amk.dataflow_dir := values",
      "@awk.import.target",
      "define base",
      f"BEGIN {{ print {n} }}",
      "endef",
      "@awk.import.target",
      "define show",
      "BEGIN { print @base@ }",
      "endef",
    ])
  assert build(amk, tmp_path, text(1), "show").stdout.strip() == "1"
  r = build(amk, tmp_path, text(2), "show")
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "2", "a kept value survived a change to its program"


@pending
@pytest.mark.engines("lua")
def test_the_record_lists_declared_inputs_only(amk, tmp_path):
  text = "\n".join([
    "$(amk.mode dataflow)",
    "amk.dataflow_dir := values",
    "extra.txt: ;",
    "@lua.import.target",
    "define seed",
    "print(3)",
    "endef",
    "@lua.import.target",
    "define total",
    "print(@seed@ + tonumber(amk.var.bonus))",
    "endef",
    "total: extra.txt",
    "bonus := 4",
    "@lua.import.target",
    "define show",
    "print('@total@')",
    "endef",
  ])
  (tmp_path / "extra.txt").write_text("")
  r = build(amk, tmp_path, text, "show")
  assert r.returncode == 0, r.stdout + r.stderr
  record = json.loads((tmp_path / "values" / "total.json").read_text())
  inputs = json.dumps(record)
  assert "seed" in inputs and "extra.txt" in inputs, record
  assert "bonus" not in inputs, "a variable the program read itself was recorded as an input"

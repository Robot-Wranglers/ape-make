"""Pins a failed engine call as a failure of the call that made it.

Pinned per engine: a one-shot call, an argv call, an exec in main or in a namespace, and an
import that raises stop the run at the expansion with the makefile's line; through amk.call
they raise in the caller; and a status the engine answers, such as jq's exit-status option,
does not stop make.
"""

import pytest

from conftest import sh

# Each engine's failing program, for a one-shot call and for an exec or import.
one_shot = {
  "lua": 'error("boom")',
  "s7": "(car 1)",
  "micropy": 'raise ValueError("boom")',
  "js": 'throw new Error("boom")',
  "jq": 'error("boom"), 1',
  "sqlite": "SELECT * FROM nope",
  "awk": "BEGIN { exit 3 }",
}
argv = {
  "awk": "-v x=1, BEGIN { exit 3 }",
  "jq": '-n, error("boom")',
  "sqlite": ":memory:, SELECT * FROM nope",
}
state = {k: one_shot[k] for k in ("lua", "s7", "micropy", "js")}
spaces = ("lua", "s7", "js")


def run(amk, tmp_path, lines):
  mk = tmp_path / "f.mk"
  mk.write_text("\n".join(lines + ["all:", "\t@echo ran", ""]))
  return sh(amk, ["-s", "-f", str(mk)], timeout=120)


def stopped(r, line, call):
  assert r.returncode != 0, r.stdout + r.stderr
  assert f"f.mk:{line}: *** {call}" in r.stderr, r.stderr
  assert "exited with status" in r.stderr, r.stderr
  assert "after" not in r.stdout and "ran" not in r.stdout, r.stdout


@pytest.mark.parametrize("engine", sorted(one_shot))
def test_a_failed_one_shot_call_stops_make(amk, engines, tmp_path, engine):
  if engine not in engines:
    pytest.skip(f"needs {engine}")
  r = run(amk, tmp_path, [f"x := $({engine} {one_shot[engine]})", "$(info after)"])
  stopped(r, 1, f"{engine}: {engine} exited with status")


@pytest.mark.parametrize("engine", sorted(argv))
def test_a_failed_argv_call_stops_make(amk, engines, tmp_path, engine):
  if engine not in engines:
    pytest.skip(f"needs {engine}")
  r = run(amk, tmp_path, [f"x := $({engine}.argv {argv[engine]})", "$(info after)"])
  stopped(r, 1, f"{engine}.argv: {engine} exited with status")


@pytest.mark.parametrize("engine", sorted(state))
@pytest.mark.parametrize("op", ["exec", "import"])
def test_a_failed_exec_or_import_in_main_stops_make(amk, engines, tmp_path, engine, op):
  if engine not in engines:
    pytest.skip(f"needs {engine}")
  r = run(amk, tmp_path, [f"x := $({engine}.{op} {state[engine]})", "$(info after)"])
  stopped(r, 1, f"{engine}.{op}: {engine} {op} exited with status")


@pytest.mark.parametrize("engine", spaces)
def test_a_failed_exec_through_a_handle_stops_make(amk, engines, tmp_path, engine):
  if engine not in engines:
    pytest.skip(f"needs {engine}")
  r = run(amk, tmp_path, [f"$({engine}.ns.create w)", f"x := $(w.exec {state[engine]})", "$(info after)"])
  stopped(r, 2, f"w.exec: {engine} exec exited with status")


@pytest.mark.parametrize("callee", ["s7", "sqlite"])
def test_a_failed_call_through_amk_call_raises_in_the_caller(amk, engines, tmp_path, callee):
  if callee not in engines or "lua" not in engines:
    pytest.skip(f"needs {callee} and lua")
  lines = ["define prog",
           f'  local ok, e = pcall(amk.call, "{callee}", {one_shot[callee]!r})',
           '  print(ok and "answered" or ("raised " .. e))',
           "endef",
           "$(info $(lua.exec* prog))"]
  r = run(amk, tmp_path, lines)
  assert r.returncode == 0, r.stdout + r.stderr
  assert f"raised amk.call: {callee}: {callee} exited with status" in r.stdout, r.stdout
  assert "ran" in r.stdout, r.stdout


@pytest.mark.engines("jq", "lua")
def test_a_call_that_succeeds_still_answers(amk, tmp_path):
  r = run(amk, tmp_path, ['x := $(jq -e .a, {"a": false})',
                          "y := $(lua print(41 + 1))",
                          "z := $(lua.exec x = 1)",
                          "$(info after x=[$(x)] y=[$(y)] z=[$(z)])"])
  assert r.returncode == 0, r.stdout + r.stderr
  assert "after x=[false] y=[42] z=[]" in r.stdout, r.stdout
  assert "ran" in r.stdout, r.stdout

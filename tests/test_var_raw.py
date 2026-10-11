"""Pins amk.var.raw: a guest reads a variable's text as stored and writes one recursive, in every engine with a handle.

Pinned: a read returns the value unexpanded and runs nothing in it, an unknown name reads as
the engine's undefined, a write from a one-shot call defines a recursive variable that expands
when make reads it, and amk.var keeps its expanded read and literal write beside it.
"""

import pytest

from conftest import sh

engines = ["lua", "micropy", "s7", "js"]

read = {
  "lua": "print(amk.var.raw[{name}])",
  "micropy": "import amk\nprint(amk.var.raw[{name}])",
  "s7": "(display ((amk-var 'raw) {name}))",
  "js": "print(amk.var.raw[{name}]);",
}

write = {
  "lua": "amk.var.raw[{name}] = {value}",
  "micropy": "import amk\namk.var.raw[{name}] = {value}",
  "s7": "(set! ((amk-var 'raw) {name}) {value})",
  "js": "amk.var.raw[{name}] = {value};",
}

undefined = {"lua": "nil", "micropy": "None", "s7": "#f", "js": "undefined"}

every_engine = [pytest.param(e, marks=pytest.mark.engines(e), id=e) for e in engines]

stored = "cost: $5 and $(words a b) and $$"


def build(amk, tmp_path, lines):
  (tmp_path / "raw.mk").write_text("\n".join(lines + [""]))
  r = sh(amk, ["-s", "-f", "raw.mk"], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  return r.stdout


def prog(name, body):
  return [f"define {name}", body, "endef"]


@pytest.mark.parametrize("engine", every_engine)
def test_a_read_returns_the_text_as_stored(amk, tmp_path, engine):
  out = build(amk, tmp_path, [
    "define t", stored, "endef",
    *prog("p", read[engine].format(name='"t"')),
    f"$(info [$({engine}* p)])",
    "all:", "\ttrue",
  ])
  assert f"[{stored}]" in out, out


@pytest.mark.parametrize("engine", every_engine)
def test_a_read_runs_nothing_in_the_value(amk, tmp_path, engine):
  build(amk, tmp_path, [
    "t = $(shell touch ran)",
    *prog("p", read[engine].format(name='"t"')),
    f"$(info [$({engine}* p)])",
    "all:", "\ttrue",
  ])
  assert not (tmp_path / "ran").exists()


@pytest.mark.parametrize("engine", every_engine)
def test_an_unknown_name_reads_as_undefined(amk, tmp_path, engine):
  out = build(amk, tmp_path, [
    *prog("p", read[engine].format(name='"never.seen"')),
    f"$(info [$({engine}* p)])",
    "all:", "\ttrue",
  ])
  assert f"[{undefined[engine]}]" in out, out


@pytest.mark.parametrize("engine", every_engine)
def test_a_write_defines_a_recursive_variable(amk, tmp_path, engine):
  out = build(amk, tmp_path, [
    "flag = on",
    *prog("p", write[engine].format(name='"w"', value='"$(flag)"')),
    f"$(if $({engine}* p),)",
    "flag = off",
    "$(info [$(w)] [$(value w)] [$(flavor w)])",
    "all:", "\ttrue",
  ])
  assert "[off] [$(flag)] [recursive]" in out, out


@pytest.mark.engines("lua")
def test_var_keeps_its_expanded_read_and_literal_write(amk, tmp_path):
  out = build(amk, tmp_path, [
    "flag = on",
    "t = [$(flag)]",
    *prog("p", 'print(amk.var.t, amk.var.raw.t)\namk.var.v = "$(flag)"'),
    "$(info $(lua* p))",
    "$(info [$(value v)] [$(flavor v)])",
    "all:", "\ttrue",
  ])
  assert "[on]\t[$(flag)]" in out, out
  assert "[$(flag)] [simple]" in out, out

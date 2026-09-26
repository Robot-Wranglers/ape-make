"""Pins the define for an engine.

`define.<engine> name` through `endef` stores an ordinary define of that name and enters a
phony target of the same name that hands the body to the engine and prints what comes back.
Pinned: the target prints the body's output, the define is still a plain variable, a file of
the target's name does not stop it, the name is expanded, and an unknown engine is an error.
"""

import pytest

from conftest import sh

makefile = "\n".join([
  "define.lua greet",
  "print('hello from ' .. _VERSION)",
  "endef",
  "define.s7 answer",
  "(display (* 6 7))",
  "endef",
  "$(info body=[$(greet)])",
  "all: greet answer",
  "",
])

prefixed = "\n".join([
  "kind := lua",
  "define.lua $(kind)-hello",
  "print('hi')",
  "endef",
  "",
])

unknown = "\n".join([
  "define.cobol run",
  "DISPLAY 'no'.",
  "endef",
  "",
])


@pytest.mark.engines("lua", "s7")
def test_the_target_runs_the_body_and_the_define_stays_a_variable(amk, tmp_path):
  mk = tmp_path / "define.mk"
  mk.write_text(makefile)
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "hello from Lua 5.4" in r.stdout, r.stdout
  assert "42" in r.stdout, r.stdout
  assert "body=[print('hello from ' .. _VERSION)]" in r.stdout, r.stdout


@pytest.mark.engines("lua")
def test_the_target_is_phony(amk, tmp_path):
  mk = tmp_path / "define.mk"
  mk.write_text(makefile)
  (tmp_path / "greet").write_text("a file with the target's name\n")
  r = sh(amk, ["-s", "-f", str(mk), "greet"], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "hello from Lua 5.4" in r.stdout, r.stdout


@pytest.mark.engines("lua")
def test_the_name_is_expanded(amk, tmp_path):
  mk = tmp_path / "define.mk"
  mk.write_text(prefixed)
  r = sh(amk, ["-s", "-f", str(mk), "lua-hello"], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "hi", r.stdout


def test_a_word_that_names_no_engine_is_an_error(amk, tmp_path):
  mk = tmp_path / "define.mk"
  mk.write_text(unknown)
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode != 0
  assert "'define.cobol' names no engine" in r.stderr, r.stderr

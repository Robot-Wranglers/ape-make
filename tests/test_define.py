"""Pins the import target and the at line.

`@<engine>.import.target` above `define name` through `endef` keeps the define and enters a
phony target of the same name that hands the body to the engine and prints what comes back.
Pinned: the target prints the body's output, the define is still a plain variable, a file of
the target's name does not stop it, the name is expanded, the builtin works without the at
line, and an at line naming no builtin is left to make.
"""

import pytest

from conftest import sh

makefile = "\n".join([
  "@lua.import.target",
  "define greet",
  "print('hello from ' .. _VERSION)",
  "endef",
  "@s7.import.target",
  "define answer",
  "(display (* 6 7))",
  "endef",
  "$(info body=[$(greet)])",
  "all: greet answer",
  "",
])

prefixed = "\n".join([
  "kind := lua",
  "@lua.import.target",
  "define $(kind)-hello",
  "print('hi')",
  "endef",
  "",
])

literal = "\n".join([
  "$(lua.import.target hi,print('hi from a literal'))",
  "",
])

unknown = "\n".join([
  "@cobol.import.target",
  "define run",
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


@pytest.mark.engines("lua")
def test_the_builtin_works_without_the_at_line(amk, tmp_path):
  mk = tmp_path / "define.mk"
  mk.write_text(literal)
  r = sh(amk, ["-s", "-f", str(mk), "hi"], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "hi from a literal", r.stdout


def test_an_at_line_naming_no_builtin_is_left_to_make(amk, tmp_path):
  mk = tmp_path / "define.mk"
  mk.write_text(unknown)
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode != 0
  assert "missing separator" in r.stderr, r.stderr

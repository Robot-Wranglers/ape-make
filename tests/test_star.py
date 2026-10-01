"""Pins the star forms, where any argument may name a variable.

An argument that names a defined variable is replaced by its unexpanded value, and any
other is literal text, in either slot. The program's value is dedented and the input's
passes as it is. With no argument naming a variable the twin is the base builtin, and an
argv form has no star twin.
"""

import pytest

from conftest import sh

makefile = "\n".join([
  "define prog",
  "  print('hi ' .. amk.input)",
  "endef",
  "define shout",
  "  print(string.upper(amk.input))",
  "endef",
  "data := there",
  "block := $(lua.persistent print('  a\\n    b'))",
  "both := $(lua.persistent* prog,data)",
  "prog-lit := $(lua.persistent* prog,folks)",
  "lit-input := $(lua.persistent* print(amk.input .. '!'),data)",
  "neither := $(lua.persistent* print(amk.input .. '?'),nobody)",
  "no-input := $(lua.persistent* print('alone'))",
  "blanks := $(lua.persistent* prog, data )",
  "raw := $(lua.persistent* print('[' .. amk.input .. ']'),block)",
  "dedented := $(lua.persistent* shout,data)",
  "argv := [$(lua.argv* x)]",
  "$(info both=[$(both)])",
  "$(info prog-lit=[$(prog-lit)])",
  "$(info lit-input=[$(lit-input)])",
  "$(info neither=[$(neither)])",
  "$(info no-input=[$(no-input)])",
  "$(info blanks=[$(blanks)])",
  "$(info raw=$(raw))",
  "$(info dedented=[$(dedented)])",
  "$(info argv=$(argv))",
  "all: ; @:",
  "",
])

ragged = "\n".join([
  "define prog",
  "    print('a')",
  "  print('b')",
  "endef",
  "x := $(lua.persistent* prog)",
  "all: ; @:",
  "",
])


@pytest.fixture(scope="module")
def run(amk, tmp_path_factory):
  mk = tmp_path_factory.mktemp("star") / "star.mk"
  mk.write_text(makefile)
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  return r.stdout.splitlines()


@pytest.mark.engines("lua")
@pytest.mark.parametrize("line", [
  "both=[hi there]",
  "prog-lit=[hi folks]",
  "lit-input=[there!]",
  "blanks=[hi there]",
  "dedented=[THERE]",
], ids=["program-and-input", "program-only", "input-only", "blanks-trimmed", "program-dedented"])
def test_a_slot_naming_a_variable_takes_its_value(run, line):
  assert line in run, run


@pytest.mark.engines("lua")
@pytest.mark.parametrize("line", [
  "neither=[nobody?]",
  "no-input=[alone]",
], ids=["two-literals", "one-literal"])
def test_with_no_variable_named_the_twin_is_the_base_builtin(run, line):
  assert line in run, run


@pytest.mark.engines("lua")
def test_the_input_is_not_dedented(run):
  i = run.index("raw=[  a")
  assert run[i + 1] == "    b]", run


@pytest.mark.engines("lua")
def test_an_argv_form_has_no_star_twin(run):
  assert "argv=[]" in run, run


@pytest.mark.engines("lua")
def test_a_ragged_program_variable_is_fatal(amk, tmp_path):
  mk = tmp_path / "ragged.mk"
  mk.write_text(ragged)
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode != 0, r.stdout
  assert "lua.persistent* prog: inconsistent indentation" in r.stderr, r.stderr

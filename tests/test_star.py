"""Pins the star forms.

Every argument of `$(<builtin>* ...)` that names a variable becomes that variable's
dedented, unexpanded value, and any other passes as written. Pinned: dollars and commas
reach the engine intact, input and argv options follow the same rule, `.import*`,
`.exec*` and `.import.target*` keep their base semantics, and a ragged indent is fatal.
"""

import pytest

from conftest import sh

literal = {
  "lua": 'print("cost: $(x), a, b")',
  "s7": '(display "cost: $(x), a, b")',
  "micropy": 'print("cost: $(x), a, b")',
  "js": 'console.log("cost: $(x), a, b")',
}

imports = {
  "lua": "x = 41 + 1",
  "s7": "(define x 42)",
  "micropy": "x = 41 + 1",
  "js": "var x = 41 + 1;",
}

counter = "\n".join([
  "define words",
  "the quick brown fox",
  "jumps over the lazy dog",
  "endef",
  "define lua.count",
  "  local n = 0",
  "  for line in io.lines() do",
  '    for _ in line:gmatch("%S+") do n = n + 1 end',
  "  end",
  "  print(n)",
  "endef",
  "$(info inline=[$(lua $(lua.count),$(words))])",
  "$(info named=[$(lua* lua.count, words)])",
  "$(info literal=[$(lua* lua.count,one two)])",
  "all:",
  "\ttrue",
  "",
])


def body(name, text, indent="    "):
  return "\n".join([f"define {name}", *(indent + ln for ln in text.splitlines()), "endef"])


def run(amk, tmp_path, text):
  mk = tmp_path / "star.mk"
  mk.write_text(text + "\nall:\n\ttrue\n")
  return sh(amk, ["-s", "-f", str(mk)], timeout=120)


@pytest.mark.parametrize("engine", literal.keys())
def test_the_body_reaches_the_engine_unexpanded_and_dedented(amk, engines, tmp_path, engine):
  if engine not in engines:
    pytest.skip(f"this amk carries no {engine}")
  r = run(amk, tmp_path, body("prog", literal[engine]) + f"\n$(info [$({engine}* prog)])")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[cost: $(x), a, b]" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("lua")
def test_the_input_is_a_variable_when_it_names_one_and_text_otherwise(amk, tmp_path):
  mk = tmp_path / "star.mk"
  mk.write_text(counter)
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "inline=[9]" in r.stdout, r.stdout
  assert "named=[9]" in r.stdout, r.stdout
  assert "literal=[2]" in r.stdout, r.stdout


@pytest.mark.engines("jq")
def test_jq_takes_its_input_after_the_name(amk, tmp_path):
  r = run(amk, tmp_path, body("prog", ".a + 1") + '\n$(info [$(jq* prog,{"a":41})])')
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[42]" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("jq")
def test_jq_argv_star_keeps_options_and_reads_program_and_input(amk, tmp_path):
  text = "\n".join([body("prog", ".name"), 'doc := {"name":"amk"}', "$(info [$(jq.argv* -r, prog, doc)])"])
  r = run(amk, tmp_path, text)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[amk]" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("awk")
def test_awk_argv_star_reads_options_and_program(amk, tmp_path):
  text = "\n".join([body("prog", "BEGIN { print msg }"), "opts := -v 'msg=hello world'", "$(info [$(awk.argv* opts, prog)])"])
  r = run(amk, tmp_path, text)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[hello world]" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("awk")
def test_awk_runs_a_program_with_a_comma(amk, tmp_path):
  r = run(amk, tmp_path, body("prog", 'BEGIN { print "awk says, hi" }') + "\n$(info [$(awk* prog)])")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[awk says, hi]" in r.stdout, r.stdout + r.stderr


@pytest.mark.parametrize("engine", imports.keys())
def test_import_star_imports_the_globals(amk, engines, tmp_path, engine):
  if engine not in engines:
    pytest.skip(f"this amk carries no {engine}")
  r = run(amk, tmp_path, body("chunk", imports[engine]) + f"\nnames := $({engine}.import* chunk)\n$(info [$(names)]=[$(x)])")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[x]=[42]" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("lua")
def test_persistent_star_keeps_its_state(amk, tmp_path):
  text = body("setup", "seen = 7") + "\n$(lua.exec* setup)\n$(info [$(lua.exec print(seen))])"
  r = run(amk, tmp_path, text)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[7]" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("lua")
def test_import_target_star_takes_name_and_body_from_one_variable(amk, tmp_path):
  mk = tmp_path / "star.mk"
  mk.write_text(body("greet", "print('hi from greet')") + "\n$(lua.import.target* greet)\n")
  r = sh(amk, ["-s", "-f", str(mk), "greet"], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "hi from greet", r.stdout + r.stderr


@pytest.mark.engines("lua")
def test_import_target_star_takes_a_literal_name_and_a_body_variable(amk, tmp_path):
  mk = tmp_path / "star.mk"
  mk.write_text(body("prog", "print('hi from hello')") + "\n$(lua.import.target* hello, prog)\n")
  r = sh(amk, ["-s", "-f", str(mk), "hello"], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "hi from hello", r.stdout + r.stderr


def test_dedent_star_reads_a_variable_or_dedents_text(amk, tmp_path):
  text = body("text", "a\n  b") + "\n$(info star=[$(amk.dedent* text)])\n$(info val=[$(amk.val.dedent text)])\n$(info lit=[$(amk.dedent*   plain words)])"
  r = run(amk, tmp_path, text)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "star=[a\n  b]" in r.stdout, r.stdout
  assert "val=[a\n  b]" in r.stdout, r.stdout
  assert "lit=[plain words]" in r.stdout, r.stdout


@pytest.mark.engines("lua")
def test_a_name_with_no_variable_is_program_text(amk, tmp_path):
  r = run(amk, tmp_path, "$(info [$(lua* print('literal'))])")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[literal]" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("lua")
def test_a_ragged_indent_is_fatal(amk, tmp_path):
  text = "define ragged\n    print(1)\n  print(2)\nendef\n$(info [$(lua* ragged)])"
  r = run(amk, tmp_path, text)
  assert r.returncode != 0, r.stdout
  assert "lua* ragged: inconsistent indentation" in r.stderr, r.stderr

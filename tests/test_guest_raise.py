"""Pins a guest function that raises as a failure of the call, carried to whoever made it.

Pinned for a function defined in each of lua, js, micropy and s7: through amk.call it
raises in the caller with the callee's message, through amk.acall it rejects, through make
the run stops at the expansion with the message and the makefile's line, and a function
returning nothing still answers empty and succeeds. The caller is always another engine's
state than the callee's.
"""

import pytest

from conftest import sh

ENGINES = ["lua", "js", "micropy", "s7"]
pytestmark = pytest.mark.engines(*ENGINES)

# Each engine's import: a function that raises with "<engine> boom", and one returning nothing.
fns = {
  "lua": ["@lua.import", "define lua.fns",
          '  function lua_boom(x) error("lua boom") end',
          "  function lua_none(x) end", "endef"],
  "js": ["@js.import", "define js.fns",
         '  function js_boom(x) { throw new Error("js boom"); }',
         "  function js_none(x) { }", "endef"],
  "micropy": ["@micropy.import", "define micropy.fns",
              "  def micropy_boom(x):", '      raise ValueError("micropy boom")',
              "  def micropy_none(x):", "      pass", "endef"],
  "s7": ["@s7.import", "define s7.fns",
         '  (define (s7_boom x) (error (quote boom) "s7 boom"))',
         "  (define (s7_none x) #<unspecified>)", "endef"],
}

# A caller in another engine: amk.call caught and printed.
caller = {
  "lua": ["define prog", '  local ok, e = pcall(amk.call, "{name}", "1")',
          '  print(ok and ("answered [" .. e .. "]") or ("raised " .. e))', "endef",
          "$(info $(lua.exec* prog))"],
  "micropy": ["define prog", "  import amk", "  try:", '      print("answered [%s]" % amk.call("{name}", "1"))',
              "  except Exception as e:", '      print("raised %s" % e)', "endef",
              "$(info $(micropy.exec* prog))"],
}

acall = ["define prog",
         '  try {{ print(`resolved [${{await amk.acall("{name}", "1")}}]`); }}',
         '  catch (e) {{ print(`rejected ${{e.message}}`); }}', "endef",
         "$(info $(js.exec* prog))"]


def run(amk, tmp_path, lines):
  mk = tmp_path / "f.mk"
  mk.write_text("\n".join(lines + ["all:", "\t@true", ""]))
  return sh(amk, ["-s", "-f", str(mk)], timeout=120)


def via_call(amk, tmp_path, engine, name):
  who = "micropy" if engine == "lua" else "lua"
  lines = fns[engine] + [line.format(name=name) for line in caller[who]]
  return run(amk, tmp_path, lines)


@pytest.mark.parametrize("engine", ENGINES)
def test_a_raise_through_amk_call_raises_in_the_caller(amk, tmp_path, engine):
  r = via_call(amk, tmp_path, engine, f"{engine}_boom")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "raised " in r.stdout and f"{engine}_boom" in r.stdout and f"{engine} boom" in r.stdout, r.stdout
  assert "answered" not in r.stdout, r.stdout


@pytest.mark.parametrize("engine", ENGINES)
def test_a_function_returning_nothing_answers_empty(amk, tmp_path, engine):
  r = via_call(amk, tmp_path, engine, f"{engine}_none")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "answered []" in r.stdout, r.stdout


@pytest.mark.parametrize("engine", ENGINES)
def test_a_raise_through_amk_acall_rejects(amk, tmp_path, engine):
  r = run(amk, tmp_path, fns[engine] + [line.format(name=f"{engine}_boom") for line in acall])
  assert r.returncode == 0, r.stdout + r.stderr
  assert "rejected " in r.stdout and f"{engine} boom" in r.stdout, r.stdout
  assert "resolved" not in r.stdout, r.stdout


@pytest.mark.parametrize("engine", ENGINES)
def test_a_raise_through_make_stops_at_the_expansion(amk, tmp_path, engine):
  lines = fns[engine] + [f"$(info [$({engine}_boom 1)])"]
  r = run(amk, tmp_path, lines)
  assert r.returncode != 0, r.stdout + r.stderr
  assert f"f.mk:{len(lines)}:" in r.stderr and f"{engine} boom" in r.stderr, r.stderr
  assert "[]" not in r.stdout, r.stdout

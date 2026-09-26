"""Pins amk.call: a guest calls a make function or macro with values, never parsed or expanded.

Pinned in every engine with a handle: a macro and a builtin both get each value whole, a
builtin that expands its own arguments reads back what was written, values past a
builtin's last argument join it as the parser would, too few or an unknown name raise in
the guest, and amk.fxns? takes its engines as several arguments.
"""

import json

import pytest

from conftest import sh

engines = ["lua", "s7", "micropy", "js"]

call = {
  "lua": "print(amk.call({args}))",
  "s7": "(display (amk-call {args}))",
  "micropy": "print(amk.call({args}))",
  "js": "print(amk.call({args}))",
}

catch = {
  "lua": "local ok, e = pcall(amk.call, {args}); print(e)",
  "s7": "(catch #t (lambda () (amk-call {args})) (lambda (type info) (display info)))",
  "micropy": "try:\n  amk.call({args})\nexcept Exception as e:\n  print(e)",
  "js": "try {{ amk.call({args}); }} catch (e) {{ print(e.message); }}",
}


def literals(engine, values):
  return (" " if engine == "s7" else ", ").join(json.dumps(v) for v in values)


def run(amk, tmp_path, engine, template, values):
  body = template[engine].format(args=literals(engine, values))
  mk = tmp_path / "call.mk"
  mk.write_text("\n".join([
    "pair = [$1|$2]",
    "@js.import",
    "define js.methods",
    '  function shout(s) { return s.toUpperCase() + "!"; }',
    "endef",
    "define prog",
    body,
    "endef",
    f"$(info [$({engine}* prog)])",
    "all:",
    "\ttrue",
    "",
  ]))
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  return r.stdout


every_engine = [pytest.param(e, marks=pytest.mark.engines(e, "js"), id=e) for e in engines]

cases = {
  "a macro gets each value whole": (["pair", "x,y", "$(shell echo pwned)"], "[x,y|$(shell echo pwned)]"),
  "a builtin gets commas whole": (["subst", ",", ";", "a,b"], "a;b"),
  "a builtin that expands its arguments reads back the value": (["if", "", "no", "$(shell echo pwned)"], "$(shell echo pwned)"),
  "values past the last argument join it": (["word", "2", "a b", "c"], "b,c"),
  "an imported function from another engine": (["shout", "a,$(b)"], "A,$(B)!"),
}


@pytest.mark.parametrize("engine", every_engine)
@pytest.mark.parametrize("values,want", cases.values(), ids=cases.keys())
def test_amk_call_passes_values_whole(amk, tmp_path, engine, values, want):
  assert f"[{want}]" in run(amk, tmp_path, engine, call, values)


errors = {
  "too few arguments": (["subst", "a"], "'subst' takes at least 3 arguments, and got 1"),
  "an unknown name": (["nope.fn"], "no function or variable named 'nope.fn'"),
}


@pytest.mark.parametrize("engine", every_engine)
@pytest.mark.parametrize("values,message", errors.values(), ids=errors.keys())
def test_amk_call_raises_in_the_guest(amk, tmp_path, engine, values, message):
  assert message in run(amk, tmp_path, engine, catch, values)


@pytest.mark.engines("lua", "js")
def test_fxns_takes_engines_as_several_arguments(amk, tmp_path):
  mk = tmp_path / "fxns.mk"
  mk.write_text("\n".join([
    "@lua.import",
    "define lua.methods",
    "  function add(a, b) return a + b end",
    "endef",
    "@js.import",
    "define js.methods",
    '  function shout(s) { return s + "!"; }',
    "endef",
    "$(info commas=[$(amk.fxns? lua, js)] spaces=[$(amk.fxns? lua js)])",
    "all:",
    "\ttrue",
    "",
  ]))
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "commas=[add shout] spaces=[add shout]" in r.stdout, r.stdout

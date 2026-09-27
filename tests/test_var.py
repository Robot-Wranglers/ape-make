"""Pins the guest handle, the same four calls in every engine.

A read answers the variable expanded as a reference would be, and the engine's own
nothing for a name make has never seen. Expand runs text through make. A write defines
a simple variable with the literal text, and eval reads makefile syntax; from a forked
guest both land once the call returns. Under the engine flag every call refuses.
"""

import pytest

from conftest import sh

# Per engine: the call that prints a variable, that prints an expansion, that writes, and what an undefined read prints.
engines = {
  "micropy": dict(
    read="$(micropy import amk; print(amk.var.{name}))",
    item='$(micropy import amk; print(amk.var["{name}"]))',
    expand='$(micropy import amk; print(amk.expand("{text}")))',
    write='$(micropy import amk; amk.var.{name} = "{value}"; amk.eval("{text}"))',
    none="None",
    flag=["--micropy", "import amk\ntry:\n  amk.var.CC\nexcept RuntimeError as e:\n  print(e)"],
  ),
  "lua": dict(
    read="$(lua print(amk.var.{name}))",
    item='$(lua print(amk.var["{name}"]))',
    expand='$(lua print(amk.expand("{text}")))',
    write='$(lua amk.var.{name} = "{value}"; amk.eval("{text}"))',
    none="nil",
    flag=["--lua", "print(pcall(function () return amk.var.CC end))"],
  ),
  "s7": dict(
    read="$(s7 (display (amk-var '{name})))",
    item='$(s7 (display (amk-var "{name}")))',
    expand='$(s7 (display (amk-expand "{text}")))',
    write='$(s7 (set! (amk-var \'{name}) "{value}") (amk-eval "{text}"))',
    none="#f",
    flag=["--s7", "(display (catch #t (lambda () (amk-var 'CC)) (lambda args (cadr args))))"],
  ),
  "js": dict(
    read="$(js print(amk.var.{name}))",
    item='$(js print(amk.var["{name}"]))',
    expand='$(js print(amk.expand("{text}")))',
    write='$(js amk.var.{name} = "{value}"; amk.eval("{text}"))',
    none="undefined",
    flag=["--js", "try { amk.var.CC } catch (e) { print(e.message) }"],
  ),
}


def makefile(engine):
  e = engines[engine]
  return "\n".join([
    "CC := clang",
    "rec = $(CC)-x",
    "empty :=",
    "dotted.name := dot",
    "simple := " + e["read"].format(name="CC"),
    "recur := " + e["read"].format(name="rec"),
    "dotted := " + e["item"].format(name="dotted.name"),
    "blank := [" + e["read"].format(name="empty") + "]",
    "undef := " + e["read"].format(name="nope"),
    "expanded := " + e["expand"].format(text="$$(CC)/$$(rec)/$$(words a b c)"),
    "wrote := " + e["write"].format(name="guestvar", value="from guest", text="derived = $$(guestvar)!"),
    "$(info simple=[$(simple)] recur=[$(recur)] dotted=[$(dotted)] blank=[$(blank)] undef=[$(undef)] expanded=[$(expanded)])",
    "$(info set=[$(guestvar)] derived=[$(derived)] flavor=[$(flavor guestvar)] origin=[$(origin guestvar)])",
    "all:",
    "\ttrue",
    "",
  ])


@pytest.mark.parametrize("engine", sorted(engines))
def test_reads_writes_and_expands(amk, tmp_path, request, engine):
  if engine not in request.getfixturevalue("engines"):
    pytest.skip(f"no {engine} in this build")
  mk = tmp_path / f"var-{engine}.mk"
  mk.write_text(makefile(engine))
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "simple=[clang]" in r.stdout, r.stdout + r.stderr
  assert "recur=[clang-x]" in r.stdout, r.stdout
  assert "dotted=[dot]" in r.stdout, r.stdout
  assert "blank=[[]]" in r.stdout, r.stdout
  assert "undef=[%s]" % engines[engine]["none"] in r.stdout, r.stdout
  assert "expanded=[clang/clang-x/3]" in r.stdout, r.stdout
  assert "set=[from guest] derived=[from guest!] flavor=[simple] origin=[file]" in r.stdout, r.stdout + r.stderr


@pytest.mark.parametrize("engine", sorted(engines))
def test_flag_form_has_no_database(amk, request, engine):
  if engine not in request.getfixturevalue("engines"):
    pytest.skip(f"no {engine} in this build")
  r = sh(amk, engines[engine]["flag"], timeout=60)
  assert "no make database" in r.stdout + r.stderr, r.stdout + r.stderr


@pytest.mark.engines("lua")
def test_persistent_writes_land_at_once(amk, tmp_path):
  """In the persistent state there is no fork, so a write is visible to the same chunk's expand."""
  mk = tmp_path / "persist-var.mk"
  mk.write_text("\n".join([
    'both := $(lua.persistent amk.var.now = "here"; print(amk.expand("$$(now)")))',
    "$(info both=[$(both)] after=[$(now)])",
    "all:",
    "\ttrue",
    "",
  ]))
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "both=[here] after=[here]" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("lua")
def test_func_defines_a_make_function(amk, tmp_path):
  """A function defined from the persistent state is callable as a make function, nested and redefined included; a one-shot call refuses."""
  mk = tmp_path / "func.mk"
  mk.write_text("\n".join([
    '$(lua.persistent amk.func("shout", function(s) return s:upper() end))',
    '$(lua.persistent amk.func("glue", function(...) return table.concat({...}, "+") end))',
    '$(lua.persistent amk.func("none", function() end))',
    '$(lua.persistent amk.func("boom", function() error("kaput") end))',
    "$(info shout=[$(shout hello)] glue=[$(glue a,b,c)] nested=[$(shout $(glue x,y))] none=[$(none x)] boom=[$(boom x)])",
    '$(lua.persistent amk.func("shout", function(s) return s .. "!" end))',
    "$(info again=[$(shout hello)])",
    'oneshot := $(lua amk.func("x", print))',
    'taken := $(lua.persistent amk.func("join", print))',
    "$(info join=[$(join a b,1 2)])",
    "all:",
    "\ttrue",
    "",
  ]))
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "shout=[HELLO] glue=[a+b+c] nested=[X+Y] none=[] boom=[]" in r.stdout, r.stdout + r.stderr
  assert "kaput" in r.stderr, r.stderr
  assert "again=[hello!]" in r.stdout, r.stdout
  assert "only from lua.persistent" in r.stderr, r.stderr
  assert "join is a make function already" in r.stderr, r.stderr
  assert "join=[a1 b2]" in r.stdout, r.stdout


@pytest.mark.engines("micropy")
def test_micropy_func_defines_a_make_function(amk, tmp_path):
  mk = tmp_path / "func-py.mk"
  mk.write_text("\n".join([
    '$(micropy.persistent import amk; amk.func("shout", lambda s: s.upper()))',
    '$(micropy.persistent import amk; amk.func("glue", lambda *a: "+".join(a)))',
    '$(micropy.persistent import amk; amk.func("none", lambda s: None))',
    '$(micropy.persistent import amk; amk.func("count", lambda *a: len(a)))',
    '$(micropy.persistent import amk; amk.func("boom", lambda s: 1 / 0))',
    "$(info shout=[$(shout hello)] glue=[$(glue a,b,c)] nested=[$(shout $(glue x,y))] none=[$(none x)] count=[$(count a,b)] boom=[$(boom x)])",
    '$(micropy.persistent import amk; amk.func("shout", lambda s: s + "!"))',
    "$(info again=[$(shout hello)])",
    'oneshot := $(micropy import amk; amk.func("x", print))',
    'taken := $(micropy.persistent import amk; amk.func("join", print))',
    "all:",
    "\ttrue",
    "",
  ]))
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "shout=[HELLO] glue=[a+b+c] nested=[X+Y] none=[] count=[2] boom=[]" in r.stdout, r.stdout + r.stderr
  assert "ZeroDivisionError" in r.stderr, r.stderr
  assert "again=[hello!]" in r.stdout, r.stdout
  assert "only from micropy.persistent" in r.stderr, r.stderr
  assert "join is a make function already" in r.stderr, r.stderr


# An export chunk per engine: strings, a list, both booleans, a nested dict, a private name, a module, and a function.
exports = {
  "lua": dict(
    chunk=" ".join([
      'cc = "clang"',
      'flags = {"-O2", "-Wall"}',
      "debug = true",
      "quiet = false",
      'targets = {lib = "core c", app = {name = "app", tags = "ui"}}',
      "_private = 1",
      "function title(s) return s:upper() end",
    ]),
    again='cc = "gcc"',
    order="cc debug flags quiet targets.app.name targets.app.tags targets.lib title",
  ),
  "micropy": dict(
    chunk="; ".join([
      'cc = "clang"',
      'flags = ["-O2", "-Wall"]',
      "debug = True",
      "quiet = False",
      'targets = {"lib": "core c", "app": {"name": "app", "tags": "ui"}}',
      "_private = 1",
      "import os",
      "title = lambda s: s.upper()",
    ]),
    again='cc = "gcc"',
    order="cc debug flags quiet targets.app.name targets.app.tags targets.lib title",
  ),
  "js": dict(
    chunk="; ".join([
      'var cc = "clang"',
      'var flags = ["-O2", "-Wall"]',
      "var debug = true",
      "var quiet = false",
      'var targets = {lib: "core c", app: {name: "app", tags: "ui"}}',
      "var _private = 1",
      "function title(s) { return s.toUpperCase() }",
    ]),
    again='cc = "gcc"',
    order="cc debug flags quiet targets.app.name targets.app.tags targets.lib title",
  ),
}


@pytest.mark.parametrize("engine", sorted(exports))
def test_export_makes_functions_and_variables(amk, tmp_path, request, engine):
  if engine not in request.getfixturevalue("engines"):
    pytest.skip(f"no {engine} in this build")
  e = exports[engine]
  mk = tmp_path / f"export-{engine}.mk"
  mk.write_text("\n".join([
    "define chunk",
    e["chunk"],
    "endef",
    "names := $(%s.export $(value chunk))" % engine,
    "$(info names=[$(names)])",
    "$(info cc=[$(cc)] flags=[$(flags)] debug=[$(debug)] quiet=[$(quiet)] quiet.origin=[$(origin quiet)])",
    "$(info lib=[$(targets.lib)] app=[$(targets.app.name)/$(targets.app.tags)] title=[$(title hello)])",
    "$(info private=[$(origin _private)] os=[$(origin os)] targets=[$(origin targets)])",
    "again := $(%s.export %s)" % (engine, e["again"]),
    "$(info again=[$(again)] cc=[$(cc)])",
    "all:",
    "\ttrue",
    "",
  ]))
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "names=[%s]" % e["order"] in r.stdout, r.stdout + r.stderr
  assert "cc=[clang] flags=[-O2 -Wall] debug=[true] quiet=[] quiet.origin=[file]" in r.stdout, r.stdout
  assert "lib=[core c] app=[app/ui] title=[HELLO]" in r.stdout, r.stdout
  assert "private=[undefined] os=[undefined] targets=[undefined]" in r.stdout, r.stdout
  assert "again=[cc] cc=[gcc]" in r.stdout, r.stdout


@pytest.mark.engines("js")
def test_js_func_defines_a_make_function(amk, tmp_path):
  mk = tmp_path / "func-js.mk"
  mk.write_text("\n".join([
    '$(js.persistent amk.func("shout", s => s.toUpperCase()))',
    '$(js.persistent amk.func("glue", (...a) => a.join("+")))',
    '$(js.persistent amk.func("none", s => undefined))',
    '$(js.persistent amk.func("boom", s => { throw new Error("kaput") }))',
    "$(info shout=[$(shout hello)] glue=[$(glue a,b,c)] nested=[$(shout $(glue x,y))] none=[$(none x)] boom=[$(boom x)])",
    '$(js.persistent amk.func("shout", s => s + "!"))',
    "$(info again=[$(shout hello)])",
    'oneshot := $(js amk.func("x", print))',
    'taken := $(js.persistent amk.func("join", print))',
    "all:",
    "\ttrue",
    "",
  ]))
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "shout=[HELLO] glue=[a+b+c] nested=[X+Y] none=[] boom=[]" in r.stdout, r.stdout + r.stderr
  assert "kaput" in r.stderr, r.stderr
  assert "again=[hello!]" in r.stdout, r.stdout
  assert "only from js.persistent" in r.stderr, r.stderr
  assert "join is a make function already" in r.stderr, r.stderr


@pytest.mark.parametrize("engine,chunk", [
  ("lua", "n = #amk.input"),
  ("micropy", "n = len(amk.input)"),
  ("js", "var n = amk.input.length"),
])
def test_export_takes_input(amk, tmp_path, request, engine, chunk):
  if engine not in request.getfixturevalue("engines"):
    pytest.skip(f"no {engine} in this build")
  mk = tmp_path / f"export-input-{engine}.mk"
  mk.write_text("\n".join([
    "names := $(%s.export %s,ab cd)" % (engine, chunk),
    "$(info names=[$(names)] n=[$(n)])",
    "all:",
    "\ttrue",
    "",
  ]))
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "names=[n] n=[5]" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("micropy")
def test_export_refuses_a_key_make_cannot_spell(amk, tmp_path):
  mk = tmp_path / "export-key.mk"
  mk.write_text("\n".join([
    'names := $(micropy.export bad = {"a b": 1})',
    "$(info names=[$(names)])",
    "all:",
    "\ttrue",
    "",
  ]))
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert "names=[]" in r.stdout, r.stdout + r.stderr
  assert "bad has a key make cannot spell: a b" in r.stderr, r.stderr


@pytest.mark.engines("micropy")
def test_amk_is_bound_without_an_import(amk, tmp_path):
  mk = tmp_path / "bound.mk"
  mk.write_text("\n".join([
    "CC := clang",
    "seen := $(micropy.persistent print(amk.var.CC))",
    "$(info seen=[$(seen)])",
    "all:",
    "\ttrue",
    "",
  ]))
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "seen=[clang]" in r.stdout, r.stdout


@pytest.mark.engines("micropy")
def test_a_command_line_override_still_wins(amk, tmp_path):
  mk = tmp_path / "override.mk"
  mk.write_text("\n".join([
    '$(micropy import amk; amk.var.CC = "guest")',
    "$(info cc=[$(CC)])",
    "all:",
    "\ttrue",
    "",
  ]))
  r = sh(amk, ["-s", "-f", str(mk), "CC=cli"], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "cc=[cli]" in r.stdout, r.stdout

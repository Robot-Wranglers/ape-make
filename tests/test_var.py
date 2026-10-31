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
    flag=["--micropy", "import amk\ntry:\n  amk.var.var1\nexcept RuntimeError as e:\n  print(e)"],
  ),
  "lua": dict(
    read="$(lua print(amk.var.{name}))",
    item='$(lua print(amk.var["{name}"]))',
    expand='$(lua print(amk.expand("{text}")))',
    write='$(lua amk.var.{name} = "{value}"; amk.eval("{text}"))',
    none="nil",
    flag=["--lua", "print(pcall(function () return amk.var.var1 end))"],
  ),
  "s7": dict(
    read="$(s7 (display (amk-var '{name})))",
    item='$(s7 (display (amk-var "{name}")))',
    expand='$(s7 (display (amk-expand "{text}")))',
    write='$(s7 (set! (amk-var \'{name}) "{value}") (amk-eval "{text}"))',
    none="#f",
    flag=["--s7", "(display (catch #t (lambda () (amk-var 'var1)) (lambda args (cadr args))))"],
  ),
  "js": dict(
    read="$(js print(amk.var.{name}))",
    item='$(js print(amk.var["{name}"]))',
    expand='$(js print(amk.expand("{text}")))',
    write='$(js amk.var.{name} = "{value}"; amk.eval("{text}"))',
    none="undefined",
    flag=["--js", "try { amk.var.var1 } catch (e) { print(e.message) }"],
  ),
}


def makefile(engine):
  e = engines[engine]
  return "\n".join([
    "var1 := value1",
    "rec = $(var1)-x",
    "empty :=",
    "dotted.name := dot",
    "simple := " + e["read"].format(name="var1"),
    "recur := " + e["read"].format(name="rec"),
    "dotted := " + e["item"].format(name="dotted.name"),
    "blank := [" + e["read"].format(name="empty") + "]",
    "undef := " + e["read"].format(name="nope"),
    "expanded := " + e["expand"].format(text="$$(var1)/$$(rec)/$$(words a b c)"),
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
  assert "simple=[value1]" in r.stdout, r.stdout + r.stderr
  assert "recur=[value1-x]" in r.stdout, r.stdout
  assert "dotted=[dot]" in r.stdout, r.stdout
  assert "blank=[[]]" in r.stdout, r.stdout
  assert "undef=[%s]" % engines[engine]["none"] in r.stdout, r.stdout
  assert "expanded=[value1/value1-x/3]" in r.stdout, r.stdout
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
    'both := $(lua.exec amk.var.now = "here"; print(amk.expand("$$(now)")))',
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
  """A function defined from the persistent state is callable as a make function, nested and redefined included."""
  mk = tmp_path / "func.mk"
  mk.write_text("\n".join([
    '$(lua.exec amk.func("shout", function(s) return s:upper() end))',
    '$(lua.exec amk.func("glue", function(...) return table.concat({...}, "+") end))',
    '$(lua.exec amk.func("none", function() end))',
    "$(info shout=[$(shout hello)] glue=[$(glue a,b,c)] nested=[$(shout $(glue x,y))] none=[$(none x)])",
    '$(lua.exec amk.func("shout", function(s) return s .. "!" end))',
    "$(info again=[$(shout hello)])",
    "all:",
    "\ttrue",
    "",
  ]))
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "shout=[HELLO] glue=[a+b+c] nested=[X+Y] none=[]" in r.stdout, r.stdout + r.stderr
  assert "again=[hello!]" in r.stdout, r.stdout


# Each engine's two refusals of amk.func: a one-shot call, whose state ends with it, and a name make has already.
func_refusals = [
  ("lua", 'x := $(lua amk.func("x", print))', "only from lua.exec"),
  ("lua", 'x := $(lua.exec amk.func("join", print))', "join is a make function already"),
  ("micropy", 'x := $(micropy import amk; amk.func("x", print))', "only from micropy.exec"),
  ("micropy", 'x := $(micropy.exec import amk; amk.func("join", print))', "join is a make function already"),
  ("js", 'x := $(js amk.func("x", print))', "only from js.exec"),
  ("js", 'x := $(js.exec amk.func("join", print))', "join is a make function already"),
  ("s7", "x := $(s7 (amk-func 'x display))", "only from s7.exec"),
  ("s7", "x := $(s7.exec (amk-func 'join display))", "is a make function already"),
]


@pytest.mark.parametrize("engine,line,message", func_refusals)
def test_a_refused_func_stops_make(amk, tmp_path, request, engine, line, message):
  if engine not in request.getfixturevalue("engines"):
    pytest.skip(f"no {engine} in this build")
  mk = tmp_path / "refuse.mk"
  mk.write_text("\n".join([line, "$(info after join=[$(join a b,1 2)])", "all:", "\ttrue", ""]))
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode != 0, r.stdout + r.stderr
  assert message in r.stderr, r.stderr
  assert "refuse.mk:1: ***" in r.stderr, r.stderr
  assert "after" not in r.stdout, r.stdout


@pytest.mark.engines("micropy")
def test_micropy_func_defines_a_make_function(amk, tmp_path):
  mk = tmp_path / "func-py.mk"
  mk.write_text("\n".join([
    '$(micropy.exec import amk; amk.func("shout", lambda s: s.upper()))',
    '$(micropy.exec import amk; amk.func("glue", lambda *a: "+".join(a)))',
    '$(micropy.exec import amk; amk.func("none", lambda s: None))',
    '$(micropy.exec import amk; amk.func("count", lambda *a: len(a)))',
    "$(info shout=[$(shout hello)] glue=[$(glue a,b,c)] nested=[$(shout $(glue x,y))] none=[$(none x)] count=[$(count a,b)])",
    '$(micropy.exec import amk; amk.func("shout", lambda s: s + "!"))',
    "$(info again=[$(shout hello)])",
    "all:",
    "\ttrue",
    "",
  ]))
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "shout=[HELLO] glue=[a+b+c] nested=[X+Y] none=[] count=[2]" in r.stdout, r.stdout + r.stderr
  assert "again=[hello!]" in r.stdout, r.stdout


# An export chunk per engine: strings, a list, both booleans, a nested dict, a private name, a module, and a function.
exports = {
  "lua": dict(
    chunk=" ".join([
      'var1 = "value1"',
      'flags = {"-O2", "-Wall"}',
      "debug = true",
      "quiet = false",
      'targets = {lib = "core c", app = {name = "app", tags = "ui"}}',
      "_private = 1",
      "function title(s) return s:upper() end",
    ]),
    again='var1 = "value2"',
    order="debug flags quiet targets.app.name targets.app.tags targets.lib title var1",
  ),
  "micropy": dict(
    chunk="; ".join([
      'var1 = "value1"',
      'flags = ["-O2", "-Wall"]',
      "debug = True",
      "quiet = False",
      'targets = {"lib": "core c", "app": {"name": "app", "tags": "ui"}}',
      "_private = 1",
      "import os",
      "title = lambda s: s.upper()",
    ]),
    again='var1 = "value2"',
    order="debug flags quiet targets.app.name targets.app.tags targets.lib title var1",
  ),
  "s7": dict(
    chunk=" ".join([
      '(define var1 "value1")',
      '(define flags (list "-O2" "-Wall"))',
      "(define debug #t)",
      "(define quiet #f)",
      '(define targets (hash-table \'lib "core c" \'app (hash-table \'name "app" \'tags "ui")))',
      "(define _private 1)",
      "(define (title s) (string-upcase s))",
    ]),
    again='(set! var1 "value2")',
    order="debug flags quiet targets.app.name targets.app.tags targets.lib title var1",
  ),
  "js": dict(
    chunk="; ".join([
      'var var1 = "value1"',
      'var flags = ["-O2", "-Wall"]',
      "var debug = true",
      "var quiet = false",
      'var targets = {lib: "core c", app: {name: "app", tags: "ui"}}',
      "var _private = 1",
      "function title(s) { return s.toUpperCase() }",
    ]),
    again='var1 = "value2"',
    order="debug flags quiet targets.app.name targets.app.tags targets.lib title var1",
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
    "names := $(%s.import $(value chunk))" % engine,
    "$(info names=[$(names)])",
    "$(info var1=[$(var1)] flags=[$(flags)] debug=[$(debug)] quiet=[$(quiet)] quiet.origin=[$(origin quiet)])",
    "$(info lib=[$(targets.lib)] app=[$(targets.app.name)/$(targets.app.tags)] title=[$(title hello)])",
    "$(info private=[$(origin _private)] os=[$(origin os)] targets=[$(origin targets)])",
    "again := $(%s.import %s)" % (engine, e["again"]),
    "$(info again=[$(again)] var1=[$(var1)])",
    "all:",
    "\ttrue",
    "",
  ]))
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "names=[%s]" % e["order"] in r.stdout, r.stdout + r.stderr
  assert "var1=[value1] flags=[-O2 -Wall] debug=[true] quiet=[] quiet.origin=[file]" in r.stdout, r.stdout
  assert "lib=[core c] app=[app/ui] title=[HELLO]" in r.stdout, r.stdout
  assert "private=[undefined] os=[undefined] targets=[undefined]" in r.stdout, r.stdout
  assert "again=[var1] var1=[value2]" in r.stdout, r.stdout


@pytest.mark.engines("js")
def test_js_func_defines_a_make_function(amk, tmp_path):
  mk = tmp_path / "func-js.mk"
  mk.write_text("\n".join([
    '$(js.exec amk.func("shout", s => s.toUpperCase()))',
    '$(js.exec amk.func("glue", (...a) => a.join("+")))',
    '$(js.exec amk.func("none", s => undefined))',
    "$(info shout=[$(shout hello)] glue=[$(glue a,b,c)] nested=[$(shout $(glue x,y))] none=[$(none x)])",
    '$(js.exec amk.func("shout", s => s + "!"))',
    "$(info again=[$(shout hello)])",
    "all:",
    "\ttrue",
    "",
  ]))
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "shout=[HELLO] glue=[a+b+c] nested=[X+Y] none=[]" in r.stdout, r.stdout + r.stderr
  assert "again=[hello!]" in r.stdout, r.stdout


@pytest.mark.parametrize("engine,chunk", [
  ("lua", "n = #amk.var.data"),
  ("micropy", "n = len(amk.var.data)"),
  ("js", "var n = amk.var.data.length"),
  ("s7", "(define n (length (amk-var 'data)))"),
])
def test_export_reads_a_variable(amk, tmp_path, request, engine, chunk):
  if engine not in request.getfixturevalue("engines"):
    pytest.skip(f"no {engine} in this build")
  mk = tmp_path / f"export-input-{engine}.mk"
  mk.write_text("\n".join([
    "data := ab cd",
    "names := $(%s.import %s)" % (engine, chunk),
    "$(info names=[$(names)] n=[$(n)])",
    "all:",
    "\ttrue",
    "",
  ]))
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "names=[n] n=[5]" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("s7")
def test_s7_func_defines_a_make_function(amk, tmp_path):
  mk = tmp_path / "func-s7.mk"
  mk.write_text("\n".join([
    "$(s7.exec (amk-func 'shout string-upcase))",
    "$(s7.exec (amk-func 'glue (lambda args (format #f \"~{~A~^+~}\" args))))",
    "$(s7.exec (amk-func 'none (lambda (s) #f)))",
    "$(info shout=[$(shout hello)] glue=[$(glue a,b,c)] nested=[$(shout $(glue x,y))] none=[$(none x)])",
    "$(s7.exec (amk-func 'shout (lambda (s) (string-append s \"!\"))))",
    "$(info again=[$(shout hello)])",
    "all:",
    "\ttrue",
    "",
  ]))
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "shout=[HELLO] glue=[a+b+c] nested=[X+Y] none=[]" in r.stdout, r.stdout + r.stderr
  assert "again=[hello!]" in r.stdout, r.stdout


@pytest.mark.engines("micropy")
def test_export_refuses_a_key_make_cannot_spell(amk, tmp_path):
  mk = tmp_path / "export-key.mk"
  mk.write_text("\n".join([
    'names := $(micropy.import bad = {"a b": 1})',
    "$(info names=[$(names)])",
    "all:",
    "\ttrue",
    "",
  ]))
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode != 0, r.stdout + r.stderr
  assert "bad has a key make cannot spell: a b" in r.stderr, r.stderr
  assert "export-key.mk:1: *** micropy.import: micropy import exited with status" in r.stderr, r.stderr
  assert "names=[" not in r.stdout, r.stdout


@pytest.mark.engines("micropy")
def test_amk_is_bound_without_an_import(amk, tmp_path):
  mk = tmp_path / "bound.mk"
  mk.write_text("\n".join([
    "var1 := value1",
    "seen := $(micropy.exec print(amk.var.var1))",
    "$(info seen=[$(seen)])",
    "all:",
    "\ttrue",
    "",
  ]))
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "seen=[value1]" in r.stdout, r.stdout


@pytest.mark.engines("micropy")
def test_a_command_line_override_still_wins(amk, tmp_path):
  mk = tmp_path / "override.mk"
  mk.write_text("\n".join([
    '$(micropy import amk; amk.var.var1 = "guest")',
    "$(info var1=[$(var1)])",
    "all:",
    "\ttrue",
    "",
  ]))
  r = sh(amk, ["-s", "-f", str(mk), "var1=cli"], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "var1=[cli]" in r.stdout, r.stdout

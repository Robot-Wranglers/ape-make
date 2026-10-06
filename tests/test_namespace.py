"""Pins engine namespaces.

`$(<name>.<op> program)` runs an operation in main, with one argument so the program keeps
its commas; `$(<name>.ns ns, op[, program])` runs it in a namespace that `create` made, along
with a handle `ns.op` and its star twin per operation.
"""

import re
import subprocess
from pathlib import Path

import pytest

from conftest import sh

main_ops = "\n".join([
  "seed := $(lua.exec x = 40)",
  "sum := $(lua.exec local a, b = 1, 2 print(a + b + x))",
  "pushed := $(jq.update [1] + [2])",
  "split := $(jq.update ., [9])",
  "len := $(jq.get length)",
  "$(info sum=[$(sum)] split=[$(split)] len=[$(len)])",
  "all:",
  "\ttrue",
  "",
])

handles = "\n".join([
  "$(jq.ns stack, create)",
  "$(jq.ns stack, create)",
  "seed := $(stack.update [1] + [2] + [3])",
  "top := $(stack.update .[:-1], .[-1])",
  "left := $(stack.get .)",
  "via.ns := $(jq.ns stack, get, length)",
  "main := $(jq.get .)",
  "$(jq.ns cfg, create)",
  "loaded := $(cfg.load {\"a\": 1})",
  "a := $(cfg.get .a)",
  "pop.prog := .[:-1], .[-1]",
  "popped := $(stack.update* pop.prog)",
  "stack := wrong",
  "len.prog := length",
  "starred := $(jq.ns* stack, get, len.prog)",
  "@stack.update",
  "define push3",
  "  . + [3]",
  "endef",
  "$(info top=[$(top)] left=[$(left)] via.ns=[$(via.ns)] main=[$(main)] a=[$(a)] popped=[$(popped)] starred=[$(starred)] after=[$(stack.get .)])",
  "all:",
  "\ttrue",
  "",
])

unregistered = "\n".join([
  "$(info exec=[$(jq.exec .)] import=[$(jq.import .)] take=[$(jq.take .)] dump=[$(jq.dump .)] filter=[$(jq.filter .)] get=[$(lua.get .)] persistent=[$(lua.persistent x = 1)])",
  "all:",
  "\ttrue",
  "",
])


@pytest.mark.engines("lua", "jq")
def test_an_op_runs_in_main_and_keeps_its_commas(amk, tmp_path):
  mk = tmp_path / "main.mk"
  mk.write_text(main_ops)
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "sum=[43]" in r.stdout, r.stdout
  assert "split=[[9]]" in r.stdout, r.stdout
  assert "len=[2]" in r.stdout, r.stdout


@pytest.mark.engines("jq")
def test_handles_reach_their_own_namespace(amk, tmp_path):
  mk = tmp_path / "handles.mk"
  mk.write_text(handles)
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "top=[3] left=[[1,2]] via.ns=[2]" in r.stdout, r.stdout
  assert "main=[null]" in r.stdout, r.stdout
  assert "a=[1]" in r.stdout, r.stdout
  assert "popped=[2]" in r.stdout, r.stdout
  assert "starred=[1]" in r.stdout, r.stdout
  assert "after=[[1,3]]" in r.stdout, r.stdout


@pytest.mark.engines("lua", "jq")
def test_the_grammar_leaves_these_names_unregistered(amk, tmp_path):
  mk = tmp_path / "unregistered.mk"
  mk.write_text(unregistered)
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "exec=[] import=[] take=[] dump=[] filter=[] get=[] persistent=[]" in r.stdout, r.stdout


languages = {
  "lua": [
    "seed := $(lua.exec x = 1)",
    "seed.work := $(work.exec x = 2)",
    "$(work.exec amk.func(\"tag\", function(s) return s .. x end))",
    "imported := $(work.import y = 5)",
    "$(lua.exec amk.on.goals = function(e) io.stderr:write(\"main-hook\\n\") end)",
    "$(work.exec amk.on.goals = function(e) io.stderr:write(\"work-hook\\n\") end)",
    "show := main=[$(lua.exec print(x))] work=[$(work.exec print(x))]",
  ],
  "s7": [
    "seed := $(s7.exec (define x 1))",
    "seed.work := $(work.exec (define x 2))",
    "$(work.exec (amk-func 'tag (lambda (s) (string-append s (number->string x)))))",
    "imported := $(work.import (define y 5))",
    "$(s7.exec (set! (amk-on 'goals) (lambda (e) (display \"main-hook\"))))",
    "$(work.exec (set! (amk-on 'goals) (lambda (e) (display \"work-hook\"))))",
    "show := main=[$(s7.exec (display x))] work=[$(work.exec (display x))]",
  ],
  "js": [
    "seed := $(js.exec var x = 1)",
    "seed.work := $(work.exec var x = 2)",
    "$(work.exec amk.func(\"tag\", s => s + x))",
    "imported := $(work.import var y = 5)",
    "$(js.exec amk.on.goals = e => print(\"main-hook\"))",
    "$(work.exec amk.on.goals = e => print(\"work-hook\"))",
    "show := main=[$(js.exec print(x))] work=[$(work.exec print(x))]",
  ],
}


@pytest.mark.parametrize("engine", sorted(languages))
def test_a_language_namespace_keeps_its_own_state(amk, engines, tmp_path, engine):
  if engine not in engines:
    pytest.skip(f"this amk carries no {engine}")
  mk = tmp_path / "lang.mk"
  mk.write_text("\n".join([f"$({engine}.ns work, create)"] + languages[engine] + [
    "$(info $(show) tag=[$(tag a)] imported=[$(imported)] y=[$(y)])",
    "all:",
    "\ttrue",
    "",
  ]))
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "main=[1] work=[2]" in r.stdout, r.stdout
  assert "tag=[a2]" in r.stdout, r.stdout
  assert "imported=[y] y=[5]" in r.stdout, r.stdout
  assert "main-hook" in r.stderr and "work-hook" not in r.stderr, r.stderr


@pytest.mark.engines("lua", "jq", "micropy")
@pytest.mark.parametrize("line, message", [
  ("x := $(jq.ns , get, .)", 'namespace "" is not a name'),
  ("x := $(jq.ns a b, get, .)", 'namespace "a b" is not a name'),
  ("x := $(jq.ns nope, get, .)", "namespace nope was never created"),
  ("x := $(jq.ns s, x = 1)", 'expected an op, got "x = 1"'),
  ("$(jq.ns s, create)\nx := $(jq.ns s, get)", "get: no program"),
  ("$(jq.ns s, create)\nx := $(jq.ns s, take, .)", 'expected an op, got "take"'),
  ("$(jq.ns s, create, .)", "expected a backing, one of run, owned PATH, shared PATH"),
  ("$(lua.ns s, create, run)", "create takes no program"),
  ("$(jq.ns w, create)\n$(lua.ns w, create)", "namespace w belongs to jq"),
  ("$(jq.ns jq, create)", "jq.get is a make function already"),
  ("$(micropy.ns w, create)", "create is not supported for micropy"),
])
def test_a_bad_namespace_call_is_fatal(amk, tmp_path, line, message):
  mk = tmp_path / "bad.mk"
  mk.write_text(line + "\nall:\n\ttrue\n")
  r = sh(amk, ["-s", "-f", str(mk)], timeout=60)
  assert r.returncode != 0, r.stdout + r.stderr
  assert message in r.stderr, r.stderr


def test_no_tracked_source_calls_the_old_name():
  root = Path(__file__).resolve().parents[1]
  tracked = subprocess.run(["git", "-C", str(root), "ls-files"], capture_output=True, text=True, check=True).stdout.split()
  old = re.compile(r"\.persistent\b")
  hits = []
  for name in tracked:
    path = root / name
    if path == Path(__file__).resolve() or not path.is_file():
      continue
    try:
      text = path.read_text()
    except UnicodeDecodeError:
      continue
    hits += [f"{name}:{i}" for i, line in enumerate(text.splitlines(), 1) if old.search(line)]
  assert hits == [], hits

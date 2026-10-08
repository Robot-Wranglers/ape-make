"""The conformance suite's engines and dialects.

The engines come from the binary's own `--list-engines`, so a new engine joins every contract
it claims. A dialect is the few programs a contract needs, in one engine's language; the
contracts never name an engine.
"""

import json

from conftest import _binary, sh

AMK_OPS_ALL = ["exec", "import", "get", "update", "load"]
OPS = {"state": ["exec", "import"], "workspace": ["get", "update", "load"], None: []}


def list_engines():
  """Each engine as --list-engines describes it; empty when no binary is built."""
  binary = _binary()
  if not binary.exists():
    return []
  r = sh(binary, ["--list-engines"], timeout=60)
  return json.loads(r.stdout)["engines"]


def spellings(engine):
  """Every name the engine answers to: its own, then its aliases."""
  return [engine["name"]] + engine["aliases"]


def parametrize(metafunc, interface=None):
  """Parametrize the test's engine argument over the engines with that interface, or over every engine; a test that also takes a spelling runs once per name each engine answers to."""
  rows = [e for e in list_engines() if interface is None or e["interface"] == interface]
  if "spelling" in metafunc.fixturenames:
    pairs = [(e, s) for e in rows for s in spellings(e)]
    metafunc.parametrize("engine,spelling", pairs, ids=[f"{e['name']}-{s}" for e, s in pairs])
  elif "engine" in metafunc.fixturenames:
    metafunc.parametrize("engine", rows, ids=[e["name"] for e in rows])


def run(amk, tmp_path, lines, recipe=(), env=None):
  """A makefile of the given lines and one recipe, run once; the result of the run."""
  mk = tmp_path / "probe.mk"
  body = ["SHELL := bash"] + list(lines) + ["all:"] + ["\t@" + r for r in recipe] + ["\t@true", ""]
  mk.write_text("\n".join(body))
  return sh(amk, ["-s", "-f", str(mk), "all"], cwd=tmp_path, env=env, timeout=120)


# A workspace dialect: seed is a text load takes; read prints before over the seed and after over write's result; broken is a text load must refuse; multi prints two lines.
WORKSPACE = {
  "jq": {
    "seed": '{"n": 1}',
    "read": ".n",
    "before": "1",
    "write": ".n = 2",
    "after": "2",
    "broken": '{"n": ',
    "multi": ".n, .n",
    "filter": (".n", '{"n": 5}', "5"),
  },
  "sqlite": {
    "seed": "CREATE TABLE t(n); INSERT INTO t VALUES(1);",
    "read": "SELECT n FROM t",
    "before": '{"n":1}',
    "write": "UPDATE t SET n = 2",
    "after": '{"n":2}',
    "broken": "CREATE TABLE u(k); INSERT INTO nowhere VALUES(1);",
    "multi": "SELECT 1 AS a UNION ALL SELECT 2",
  },
}

# A state dialect: set then show prints 42; lib defines cf_echo, which appends a bang, and cf_v, which holds seven; read prints the make variable cf_var; hook prints hooked on goals. None for an engine whose program is a module and a call rather than text; test_wasm.py pins that one.
STATE = {
  "lua": {
    "set": "x = 41",
    "show": "print(x + 1)",
    "lib": "function cf_echo(s) return s .. '!' end\ncf_v = 'seven'",
    "read": "print(amk.var.cf_var)",
    "hook": "amk.on.goals = function(e) print('hooked') end",
  },
  "s7": {
    "set": "(define x 41)",
    "show": "(display (+ x 1))",
    "lib": "(define (cf_echo s) (string-append s \"!\"))\n(define cf_v \"seven\")",
    "read": "(display (amk-var 'cf_var))",
    "hook": "(set! (amk-on 'goals) (lambda (e) (display \"hooked\")))",
  },
  "micropy": {
    "set": "x = 41",
    "show": "print(x + 1)",
    "lib": "def cf_echo(s):\n  return s + '!'\ncf_v = 'seven'",
    "read": "import amk\nprint(amk.var.cf_var)",
    "hook": "import amk\namk.on['goals'] = lambda e: print('hooked')",
  },
  "js": {
    "set": "var x = 41;",
    "show": "print(x + 1);",
    "lib": "function cf_echo(s) { return s + '!'; }\nvar cf_v = 'seven';",
    "read": "print(amk.var.cf_var);",
    "hook": "amk.on.goals = function(e) { print('hooked'); };",
  },
  "wasm": None,
}

# A command-line dialect: a program that prints hi, with the input the builtin passes, the flags a target takes, and the arguments the engine's own command line takes to print hi; None for an engine whose program is not text.
CLI = {
  "awk": {"prog": 'BEGIN { print "hi" }', "args": ['BEGIN { print "hi" }']},
  "jq": {"prog": '"hi"', "input": "null", "flags": "--null-input", "args": ["--null-input", '"hi"']},
  "lua": {"prog": 'print("hi")', "args": ['print("hi")']},
  "s7": {"prog": '(display "hi")', "args": ['(display "hi")']},
  "micropy": {"prog": 'print("hi")', "args": ['print("hi")']},
  "js": {"prog": 'print("hi")', "args": ['print("hi")']},
  "sqlite": {"prog": "SELECT 'hi' AS x;", "args": ["--", "SELECT 'hi' AS x;"]},
  "wasm": None,
}

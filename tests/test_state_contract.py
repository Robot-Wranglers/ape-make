"""The state contract, for every engine whose interface is state.

exec keeps what it leaves, import lifts a function and a variable into make and records
them, the handle reads a make variable, a listed hook hears the goals, init runs before the
parse, and create makes a separate namespace or, for a single-state engine, is refused.
"""

import pytest

from conformance import STATE, parametrize, run


def pytest_generate_tests(metafunc):
  parametrize(metafunc, "state")


@pytest.fixture(autouse=True)
def _needs_a_dialect(engine):
  """An engine whose program is not text has no dialect here; its own file pins it."""
  if STATE[engine["name"]] is None:
    pytest.skip(f"{engine['name']} takes a module and a call, not program text")


def _define(name, body):
  return [f"define {name}"] + ["  " + line for line in body.splitlines()] + ["endef"]


def test_exec_keeps_what_it_leaves(amk, tmp_path, engine):
  e, d = engine["name"], STATE[engine["name"]]
  r = run(amk, tmp_path, [f"x := $({e}.exec {d['set']})", f"$(info show=$({e}.exec {d['show']}))"])
  assert r.returncode == 0, r.stdout + r.stderr
  assert "show=42" in r.stdout, r.stdout + r.stderr


def test_import_lifts_a_function_and_a_variable(amk, tmp_path, engine):
  e, d = engine["name"], STATE[engine["name"]]
  r = run(amk, tmp_path, [f"@{e}.import"] + _define("cf.lib", d["lib"]) + [
    "$(info echo=$(cf_echo hi) v=$(cf_v))",
    f"$(info fxns=$({e}.__fxns__) vars=$({e}.__vars__))",
  ])
  assert r.returncode == 0, r.stdout + r.stderr
  assert "echo=hi! v=seven" in r.stdout, r.stdout + r.stderr
  assert "cf_echo" in r.stdout.split("fxns=")[1].split(" vars=")[0], r.stdout
  assert "cf_v" in r.stdout.split("vars=")[1], r.stdout


def test_the_handle_reads_a_make_variable(amk, tmp_path, engine):
  e, d = engine["name"], STATE[engine["name"]]
  r = run(amk, tmp_path, ["cf_var := hello", f"$(info read=$({e}.exec {d['read']}))"] if "\n" not in d["read"]
          else ["cf_var := hello"] + _define("cf.read", d["read"]) + [f"$(info read=$({e}.exec* cf.read))"])
  assert r.returncode == 0, r.stdout + r.stderr
  assert "read=hello" in r.stdout, r.stdout + r.stderr


def test_a_listed_hook_hears_the_goals(amk, tmp_path, engine):
  e, d = engine["name"], STATE[engine["name"]]
  if not engine["capabilities"]["hook"]:
    return
  lines = ["cf.hook := $(" + f"{e}.exec {d['hook']})"] if "\n" not in d["hook"] \
    else _define("cf.hook.body", d["hook"]) + [f"cf.hook := $({e}.exec* cf.hook.body)"]
  r = run(amk, tmp_path, lines)
  assert r.returncode == 0, r.stdout + r.stderr
  assert (r.stdout + r.stderr).count("hooked") == 1, r.stdout + r.stderr


def test_init_runs_before_the_parse(amk, tmp_path, engine):
  e, d = engine["name"], STATE[engine["name"]]
  r = run(amk, tmp_path, [f"$(info show=$({e}.exec {d['show']}))"], env={f"AMK_{e.upper()}_INIT": d["set"]})
  assert r.returncode == 0, r.stdout + r.stderr
  assert "show=42" in r.stdout, r.stdout + r.stderr


def test_create_makes_a_separate_namespace(amk, tmp_path, engine):
  e, d = engine["name"], STATE[engine["name"]]
  r = run(amk, tmp_path, [f"$({e}.ns W, create)", f"x := $(W.exec {d['set']})", f"$(info show=$(W.exec {d['show']}))"])
  if engine["namespaces"] == "main":
    assert r.returncode != 0, r.stdout + r.stderr
    assert f"create is not supported for {e}" in r.stderr, r.stderr
    return
  assert r.returncode == 0, r.stdout + r.stderr
  assert "show=42" in r.stdout, r.stdout + r.stderr

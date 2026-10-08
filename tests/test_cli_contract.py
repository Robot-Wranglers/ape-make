"""The command-line and refusal contracts, for every engine and every name it answers to.

An engine and each of its aliases run a program through the builtin, as an imported
target, as the binary's name, and as a flag, and reach the same kept state. Every builtin
outside an engine's interface stops make naming the engine; so does an init chunk for an
engine without the state interface. Every engine the build lists has a dialect.
"""

import pytest

from conformance import AMK_OPS_ALL, CLI, OPS, STATE, WORKSPACE, list_engines, parametrize, run
from conftest import sh


def pytest_generate_tests(metafunc):
  parametrize(metafunc)


def test_every_engine_has_a_dialect(engine):
  assert engine["name"] in CLI, f"no command-line dialect for {engine['name']}"
  if engine["interface"] == "state":
    assert engine["name"] in STATE, f"no state dialect for {engine['name']}"
  if engine["interface"] == "workspace":
    assert engine["name"] in WORKSPACE, f"no workspace dialect for {engine['name']}"


def test_the_builtin_runs_a_program(amk, tmp_path, engine, spelling):
  d = CLI.get(engine["name"])
  if d is None:
    pytest.skip(f"{engine['name']} takes no program text")
  call = d["prog"] + (f",{d['input']}" if "input" in d else "")
  r = run(amk, tmp_path, [f"$(info out=$({spelling} {call}))"])
  assert r.returncode == 0, r.stdout + r.stderr
  assert "out=" in r.stdout and "hi" in r.stdout.split("out=")[1], r.stdout + r.stderr


def test_the_command_line_answers_to_every_name(amk, tmp_path, engine, spelling):
  d = CLI.get(engine["name"])
  if d is None:
    pytest.skip(f"{engine['name']} takes no program text")
  link = tmp_path / spelling
  link.symlink_to(amk)
  for binary, args in [(link, d["args"]), (amk, [f"--{spelling}"] + d["args"])]:
    r = sh(binary, args, cwd=tmp_path, timeout=120)
    assert r.returncode == 0, f"{binary} {args}: " + r.stdout + r.stderr
    assert "hi" in r.stdout, f"{binary} {args}: " + r.stdout + r.stderr


def test_an_alias_reaches_the_same_kept_state(amk, tmp_path, engine, spelling):
  e = engine["name"]
  if spelling == e or engine["interface"] is None:
    return
  if engine["interface"] == "state":
    d = STATE[e]
    if d is None:
      pytest.skip(f"{e} takes a module and a call, not program text")
    lines = [f"x := $({e}.exec {d['set']})", f"$(info show=$({spelling}.exec {d['show']}))"]
    want = "show=42"
  else:
    d = WORKSPACE[e]
    lines = [f"$({spelling}.ns W, create)", f"$(W.load {d['seed']})", f"$(info read=$({spelling}.ns W, get, {d['read']}))"]
    want = f"read={d['before']}"
  r = run(amk, tmp_path, lines)
  assert r.returncode == 0, r.stdout + r.stderr
  assert want in r.stdout, r.stdout + r.stderr


def test_an_imported_target_runs_its_program(amk, tmp_path, engine, spelling):
  d = CLI.get(engine["name"])
  if d is None:
    pytest.skip(f"{engine['name']} takes no program text")
  mk = tmp_path / "target.mk"
  at = f"@{spelling}.import.target" + (f" {d['flags']}" if "flags" in d else "")
  mk.write_text("\n".join([at, "define cf.hi", f"  {d['prog']}", "endef", ""]))
  r = sh(amk, ["-s", "-f", str(mk), "cf.hi"], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "hi" in r.stdout, r.stdout + r.stderr


def test_every_operation_outside_the_interface_refuses(amk, tmp_path, engine, spelling):
  e, own = engine["name"], OPS[engine["interface"]]
  for op in [o for o in AMK_OPS_ALL if o not in own and o != "import"]:
    r = run(amk, tmp_path, [f"x := $({spelling}.{op} 1)"])
    assert r.returncode != 0, f"{e}.{op}: " + r.stdout + r.stderr
    assert f"{e} has no" in r.stderr, f"{e}.{op}: " + r.stderr


def test_an_engine_without_kept_state_refuses_ns_and_import(amk, tmp_path, engine):
  e = engine["name"]
  if engine["interface"] is not None:
    return
  for line in [f"$({e}.ns W, create)", f"$({e}.import W, 1)"]:
    r = run(amk, tmp_path, [line])
    assert r.returncode != 0, line + r.stdout + r.stderr
    assert f"{e} has no state or workspace interface" in r.stderr, line + r.stderr


def test_a_handle_outside_the_interface_is_not_made(amk, tmp_path, engine):
  e, own = engine["name"], OPS[engine["interface"]]
  if engine["namespaces"] != "many":
    return
  for op in [o for o in AMK_OPS_ALL if o not in own]:
    r = run(amk, tmp_path, [
      f"$({e}.ns W, create)", "mine = own:$(1)", f"$(amk.fxn! W.{op}, mine)",
      f"$(info $(W.{op} 1))",
    ])
    assert r.returncode == 0, f"W.{op}: " + r.stdout + r.stderr
    assert "own:1" in r.stdout, f"W.{op}: " + r.stdout + r.stderr


def test_an_init_chunk_without_the_state_interface_refuses(amk, tmp_path, engine):
  e = engine["name"]
  if engine["interface"] == "state":
    return
  r = run(amk, tmp_path, [], env={f"AMK_{e.upper()}_INIT": "1"})
  assert r.returncode != 0, r.stdout + r.stderr
  assert f"{e} has no init" in r.stderr, r.stderr


def test_a_channel_filter_without_a_filter_member_refuses_by_name(amk, tmp_path, engine):
  e = engine["name"]
  if engine["capabilities"]["filter"]:
    return
  r = run(amk, tmp_path, [], [f"source amk.sh; st=0; printf '1\\n' | amk.filter {e} x || st=$$?; echo \"st=$$st\""])
  assert "st=2" in r.stdout, r.stdout + r.stderr
  assert f"filter: {e} has no filter" in r.stderr, r.stderr


def test_a_channel_filter_without_an_engine_is_refused(amk, tmp_path):
  r = run(amk, tmp_path, [], ["source amk.sh; st=0; amk.ask 'filter 0 .' || st=$$?; echo \"st=$$st\""])
  assert "st=2" in r.stdout, r.stdout + r.stderr
  assert "filter names its engine first" in r.stderr, r.stderr


def test_every_name_carries_the_version(amk, tmp_path, engine, spelling):
  r = run(amk, tmp_path, [f"$(info version=$({spelling}.__version__))"])
  assert r.returncode == 0, r.stdout + r.stderr
  assert f"version={engine['version']}" in r.stdout, r.stdout + r.stderr


def test_the_list_names_every_built_engine(engines):
  assert sorted(e["name"] for e in list_engines()) == sorted(engines)


def test_the_list_matches_the_interface(engine):
  caps, iface = engine["capabilities"], engine["interface"]
  assert caps["exec"] == caps["import_lift"] == caps["guest_handle"] == (iface == "state"), engine
  assert caps["get"] == caps["update"] == caps["load"] == caps["dump"] == caps["channel"] == (iface == "workspace"), engine
  assert (engine["namespaces"] is None) == (iface is None), engine
  assert engine["language"] and engine["implementation"] and engine["version"], engine

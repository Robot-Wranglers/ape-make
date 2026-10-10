"""The workspace contract, for every engine whose interface is workspace.

get leaves the state as it was, update keeps its change, load is all or nothing, dump then
load round-trips, import seeds as create and load do, an owned backing carries the state to
another make, the channel answers as the handles do, output is lines, and namespaces are
separate.
"""

from conformance import WORKSPACE, parametrize, run


def pytest_generate_tests(metafunc):
  parametrize(metafunc, "workspace")


def _d(engine):
  return engine["name"], WORKSPACE[engine["name"]]


def _dump(*names):
  return [f"source amk.sh; echo \"{n}=[$$(amk.call 'dump {n}' | tr '\\n' ' ')]\"" for n in names]


def _dumps(stdout):
  return dict(line.split("=", 1) for line in stdout.splitlines() if "=[" in line)


def test_get_leaves_the_state(amk, tmp_path, engine):
  e, d = _d(engine)
  r = run(amk, tmp_path, [
    f"$({e}.ns A, create)", f"$({e}.ns B, create)",
    f"$(A.load {d['seed']})", f"$(B.load {d['seed']})",
    f"x := $(B.get {d['read']})",
  ], _dump("A", "B"))
  assert r.returncode == 0, r.stdout + r.stderr
  dumps = _dumps(r.stdout)
  assert dumps["A"] == dumps["B"], r.stdout


def test_update_keeps_its_change(amk, tmp_path, engine):
  e, d = _d(engine)
  r = run(amk, tmp_path, [
    f"$({e}.ns W, create)", f"$(W.load {d['seed']})",
    f"x := $(W.update {d['write']})",
    f"$(info read=$(W.get {d['read']}))",
  ])
  assert r.returncode == 0, r.stdout + r.stderr
  assert f"read={d['after']}" in r.stdout, r.stdout + r.stderr


def test_load_is_all_or_nothing(amk, tmp_path, engine):
  e, d = _d(engine)
  r = run(amk, tmp_path, [
    f"$({e}.ns W, create)", f"$({e}.ns R, create)",
    f"$(W.load {d['seed']})", f"$(R.load {d['seed']})",
    f"$(W.load {d['broken']})",
  ], _dump("W", "R"))
  dumps = _dumps(r.stdout)
  assert dumps["W"] == dumps["R"], r.stdout + r.stderr


def test_dump_then_load_round_trips(amk, tmp_path, engine):
  e, d = _d(engine)
  saved = tmp_path / "saved.txt"
  r = run(amk, tmp_path, [
    f"$({e}.ns A, create)", f"$({e}.ns B, create)",
    f"$(A.load {d['seed']})", f"x := $(A.update {d['write']})",
  ], [f"source amk.sh; amk.call 'dump A' > {saved}; amk.call 'load B {saved}'"] + _dump("A", "B"))
  assert r.returncode == 0, r.stdout + r.stderr
  dumps = _dumps(r.stdout)
  assert dumps["A"] == dumps["B"], r.stdout


def test_import_seeds_as_create_and_load_do(amk, tmp_path, engine):
  e, d = _d(engine)
  r = run(amk, tmp_path, [
    f"$({e}.import I, {d['seed']})",
    f"$({e}.ns R, create)", f"$(R.load {d['seed']})",
    f"$(info read=$(I.get {d['read']}))",
  ], _dump("I", "R"))
  assert r.returncode == 0, r.stdout + r.stderr
  assert f"read={d['before']}" in r.stdout, r.stdout + r.stderr
  dumps = _dumps(r.stdout)
  assert dumps["I"] == dumps["R"], r.stdout


def test_an_owned_backing_carries_the_state_to_another_make(amk, tmp_path, engine):
  e, d = _d(engine)
  back = tmp_path / "owned.txt"
  first = run(amk, tmp_path, [
    f"$({e}.ns O, create, owned {back})", f"$(O.load {d['seed']})", f"x := $(O.update {d['write']})",
  ])
  assert first.returncode == 0, first.stdout + first.stderr
  second = run(amk, tmp_path, [
    f"$({e}.ns O, create, owned {back})", f"$(info read=$(O.get {d['read']}))",
  ])
  assert f"read={d['after']}" in second.stdout, second.stdout + second.stderr


def test_the_channel_answers_as_the_handles_do(amk, tmp_path, engine):
  e, d = _d(engine)
  r = run(amk, tmp_path, [
    f"$({e}.ns W, create)", f"$(W.load {d['seed']})",
    f"$(info handle=[$(W.get {d['read']})])",
  ], [f"source amk.sh; echo \"channel=[$$(amk.ns get W -- '{d['read']}')]\""])
  assert r.returncode == 0, r.stdout + r.stderr
  assert f"handle=[{d['before']}]" in r.stdout, r.stdout
  assert f"channel=[{d['before']}]" in r.stdout, r.stdout


def test_output_is_lines(amk, tmp_path, engine):
  e, d = _d(engine)
  r = run(amk, tmp_path, [
    f"$({e}.ns W, create)", f"$(W.load {d['seed']})",
  ], [f"source amk.sh; echo \"lines=$$(amk.ns get W -- '{d['multi']}' | wc -l | tr -d ' ')\""])
  assert r.returncode == 0, r.stdout + r.stderr
  assert "lines=2" in r.stdout, r.stdout


def test_namespaces_are_separate(amk, tmp_path, engine):
  e, d = _d(engine)
  r = run(amk, tmp_path, [
    f"$({e}.ns A, create)", f"$({e}.ns B, create)",
    f"$(A.load {d['seed']})", f"$(B.load {d['seed']})", f"x := $(B.update {d['write']})",
    f"$(info a=$(A.get {d['read']}) b=$(B.get {d['read']}))",
  ])
  assert r.returncode == 0, r.stdout + r.stderr
  assert f"a={d['before']} b={d['after']}" in r.stdout, r.stdout


def test_a_listed_filter_runs_the_plain_form(amk, tmp_path, engine):
  e, d = _d(engine)
  if not engine["capabilities"]["filter"]:
    return
  prog, text, out = d["filter"]
  r = run(amk, tmp_path, [f"$(info out=$({e} {prog},{text}))"])
  assert r.returncode == 0, r.stdout + r.stderr
  assert f"out={out}" in r.stdout, r.stdout


def test_a_listed_filter_answers_on_the_channel(amk, tmp_path, engine):
  e, d = _d(engine)
  if not engine["capabilities"]["filter"]:
    return
  prog, text, out = d["filter"]
  r = run(amk, tmp_path, [], [f"source amk.sh; echo \"out=$$(printf '%s\\n' '{text}' | amk.filter {e} '{prog}')\""])
  assert r.returncode == 0, r.stdout + r.stderr
  assert f"out={out}" in r.stdout, r.stdout + r.stderr

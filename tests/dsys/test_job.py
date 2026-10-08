"""Pins jobs: `lib/dsys/job.amk`, the host handle's job verbs under amk.job.

A spawn enters the job table and a finished wait leaves it; a peek keeps the record for
the wait that takes it; any answers the first of a set and keeps the rest; all answers a
set in its order; a job knows its own pid and its spawner's, and mails from make.
"""

import json

import pytest

from conftest import sh

JOBS = "\n".join([
  "fast:", "\t@true",
  "slow:", "\t@sleep 1",
  "talk:", "\t@true $(amk.job.send a  b)",
  "kin:", "\t@true $(amk.job.send $(amk.job.self) $(amk.job.parent))",
  "nap:", "\t@sleep 5",
])


def run(amk, tmp_path, *steps, head=""):
  """Each step a recipe line printing name=value, single-quoted so a record keeps its quotes."""
  recipe = "".join(f"\t@echo '{s}'\n" for s in steps)
  mk = tmp_path / "job.mk"
  mk.write_text(f"load dsys/job\n{head}{JOBS}\nall:\n{recipe}")
  r = sh(amk, ["-s", "-f", str(mk), "all"], cwd=tmp_path, timeout=60)
  assert r.returncode == 0, r.stderr
  assert "warning" not in r.stderr, r.stderr
  return dict(line.split("=", 1) for line in r.stdout.splitlines())


def test_the_table_holds_a_job_from_spawn_until_its_wait(amk, tmp_path):
  out = run(amk, tmp_path,
    "pid=$(eval p := $(amk.goal.spawn fast))$(p)",
    "live=$(amk.job.list)",
    "rec=$(amk.job.wait $(p))",
    "after=[$(amk.job.list)]")
  assert out["live"] == out["pid"]
  assert json.loads(out["rec"])["status"] == "success"
  assert out["after"] == "[]"


def test_each_noun_spawns_its_own_kind_and_job_spawn_dispatches_on_it(amk, tmp_path):
  out = run(amk, tmp_path,
    "goal=$(amk.job.wait $(amk.goal.spawn talk))",
    "goals=$(amk.job.wait $(amk.goals.spawn fast talk))",
    "kind=$(amk.job.wait $(amk.job.spawn goal=talk))",
    "kinds=$(amk.job.wait $(amk.job.spawn goals=fast talk))",
    "sync=$(amk.goals talk)",
    "after=[$(amk.job.list)]")
  for k in ("goal", "goals", "kind", "kinds", "sync"):
    assert json.loads(out[k])["mail"] == "a  b", k
  assert out["after"] == "[]"


def test_a_record_names_its_kind_and_a_call_flags_its_value_without_carrying_it(amk, tmp_path):
  out = run(amk, tmp_path, head="big = $(foreach i,$(shell seq 20000),word$(i))\ngreet = hello $(1)\n", *(
    "goal=$(amk.job.wait $(amk.goal.spawn fast))",
    "goals=$(amk.job.wait $(amk.goals.spawn fast fast))",
    "c=$(eval c := $(amk.job.spawn call=greet, world))$(c)",
    "crec=$(amk.job.wait $(c))",
    "value=$(amk.job.value $(c))",
    "again=[$(amk.job.value $(c))]",
    "b=$(eval b := $(amk.call.spawn big))$(b)",
    "brec=$(amk.job.wait $(b))",
    "bsize=$(words $(amk.job.value $(b)))"))
  goal, goals, crec, brec = (json.loads(out[k]) for k in ("goal", "goals", "crec", "brec"))
  assert (goal["kind"], goals["kind"], crec["kind"], brec["kind"]) == ("goal", "goals", "call", "call")
  assert "value" not in goal and "value" not in goals
  assert crec["value"] is True and brec["value"] is True and crec["status"] == "success"
  assert out["value"] == "hello world" and out["again"] == "[]"
  assert out["bsize"] == "20000" and "word" not in out["brec"]


@pytest.mark.parametrize("line,message", [
  ("$(amk.job.spawn fast)", "amk.job.spawn: give kind=name, one of goal=.. goals=.. call=..; got 'fast'"),
  ("$(amk.job.spawn nope=x)", "amk.job.spawn: give kind=name, one of goal=.. goals=.. call=..; got 'nope=x'"),
  ("$(amk.goal.spawn fast talk)", "amk.goal.spawn: one goal, got 'fast talk'; use amk.goals.spawn for a list"),
])
def test_a_spawn_without_a_kind_or_with_two_goals_is_refused(amk, tmp_path, line, message):
  mk = tmp_path / "job.mk"
  mk.write_text(f"load dsys/job\n{JOBS}\nall:\n\t@echo '{line}'\n")
  r = sh(amk, ["-s", "-f", str(mk), "all"], cwd=tmp_path, timeout=60)
  assert r.returncode != 0 and message in r.stderr, r.stderr


def test_a_peek_keeps_the_record_for_the_wait(amk, tmp_path):
  out = run(amk, tmp_path,
    "early=[$(eval p := $(amk.goal.spawn slow))$(amk.job.peek $(p))]",
    "peek=$(shell sleep 2)$(amk.job.peek $(p))",
    "again=$(amk.job.peek $(p))",
    "wait=$(amk.job.wait $(p))",
    "gone=[$(amk.job.peek $(p))]")
  assert out["early"] == "[]"
  assert out["peek"] == out["again"] == out["wait"]
  assert json.loads(out["wait"])["status"] == "success"
  assert out["gone"] == "[]"


def test_any_answers_the_first_of_its_set_and_keeps_a_job_outside_it(amk, tmp_path):
  out = run(amk, tmp_path,
    "o=$(eval o := $(amk.goal.spawn fast))$(o)",
    "s=$(eval s := $(amk.goal.spawn slow))$(s)",
    "any=$(amk.job.any $(s))",
    "other=$(amk.job.wait $(o))")
  assert json.loads(out["any"])["pid"] == int(out["s"])
  assert json.loads(out["other"])["pid"] == int(out["o"])


def test_any_without_blocking_answers_empty_while_the_set_runs(amk, tmp_path):
  out = run(amk, tmp_path,
    "now=[$(eval s := $(amk.goal.spawn slow))$(amk.job.any $(s), 0)]",
    "later=$(amk.job.any $(s))")
  assert out["now"] == "[]"
  assert json.loads(out["later"])["status"] == "success"


def test_all_answers_every_record_in_the_order_of_its_set(amk, tmp_path):
  out = run(amk, tmp_path,
    "a=$(eval a := $(amk.goal.spawn slow))$(a)",
    "b=$(eval b := $(amk.goal.spawn fast))$(b)",
    "recs=$(amk.job.all $(a) $(b))")
  assert [x["pid"] for x in json.loads(out["recs"])] == [int(out["a"]), int(out["b"])]


def test_a_job_mails_from_make_and_knows_itself_and_its_spawner(amk, tmp_path):
  out = run(amk, tmp_path,
    "talk=$(amk.job.wait $(amk.goal.spawn talk))",
    "k=$(eval k := $(amk.goal.spawn kin))$(k)",
    "kin=$(amk.job.wait $(k))",
    "self=$(amk.job.self)",
    "top=[$(amk.job.parent)][$(amk.job.send x)]")
  assert json.loads(out["talk"])["mail"] == "a  b"
  assert json.loads(out["kin"])["mail"] == f"{out['k']} {out['self']}"
  assert out["top"] == "[][]"


def test_a_stopped_job_stays_in_the_table_until_it_finishes(amk, tmp_path):
  out = run(amk, tmp_path,
    "p=$(eval p := $(amk.goal.spawn nap))$(p)",
    "stop=$(amk.job.stop $(p))",
    "rec=$(amk.job.wait $(p))",
    "live=$(amk.job.list)",
    "kill=$(amk.job.kill $(p))$(amk.job.resume $(p))",
    "end=$(amk.job.wait $(p))",
    "after=[$(amk.job.list)]")
  assert json.loads(out["rec"])["status"] == "stopped"
  assert out["live"] == out["p"]
  assert json.loads(out["end"])["status"] == "signal"
  assert out["after"] == "[]"


@pytest.mark.engines("lua")
def test_a_guest_reads_its_own_pid_and_a_second_nonblocking_wait_is_empty(amk, tmp_path):
  out = run(amk, tmp_path,
    "self=$(amk.job.self)",
    "lua=$(lua.exec print(amk.job.self()))",
    "again=[$(lua.exec local p = amk.goal.spawn('fast') amk.job.wait(p) io.write(amk.job.wait(p, '0')))]")
  assert out["lua"] == out["self"] != ""
  assert out["again"] == "[]"


@pytest.mark.parametrize("engine,line", [
  ("lua", "$(lua.exec print(amk.job.wait(amk.goal.spawn('fast'))))"),
  ("micropy", "$(micropy.exec import amk; print(amk.job.wait(amk.goal.spawn('fast'))))"),
  ("js", "$(js.exec print(amk.job.wait(amk.goal.spawn('fast'))))"),
])
def test_a_guest_reaches_the_verbs_as_fields_of_amk_job(amk, tmp_path, engines, engine, line):
  if engine not in engines:
    pytest.skip(f"no {engine} in this build")
  out = run(amk, tmp_path, f"rec={line}")
  assert json.loads(out["rec"])["status"] == "success"

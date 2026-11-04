"""Pins workflows: `lib/dsys/workflow.amk`, a task graph compiled by workflow.jq to a net dsys/petri runs.

The compiler is a jq library of definitions, so it is pinned whole against the worked
example of its rules, by its definitions alone through include, by its refusals, and end
to end through @workflow.dag on the success and the failure path.
"""

import json
import re
import time

import pytest

from conftest import sh

pytestmark = pytest.mark.engines("jq")

RELEASE = {
  "tasks": {
    "checkout": {"run": "checkout"},
    "test": {"run": "test", "needs": ["checkout"], "over": {"data": ["lua", "js", "micropy"]}, "pool": "runners"},
    "package": {"run": "package", "needs": ["test"]},
    "publish": {"run": "publish", "needs": ["package"]},
    "notify": {"run": "notify", "needs": ["package"], "when": "failed"},
  }
}

GOLDEN = {
  "places": {
    "checkout.ready": ["success"], "checkout.to.test": [], "test.items": [], "test.results": [],
    "test.to.package": [], "package.to.publish": [], "package.to.notify": [],
    "publish.end": [], "notify.end": [],
  },
  "transitions": [
    "checkout", "checkout.skip", "test.split", "test", "test.join", "test.skip",
    "package", "package.skip", "publish", "publish.skip", "notify", "notify.skip",
  ],
  "arcs": [
    ["checkout.ready", "checkout"], ["checkout", "checkout.to.test"],
    ["checkout.ready", "checkout.skip"], ["checkout.skip", "checkout.to.test"],
    ["checkout.to.test", "test.split"], ["test.split", "test.items", 3],
    ["test.items", "test"], ["runners", "test"], ["test", "test.results"], ["test", "runners"],
    ["test.results", "test.join", 3], ["test.join", "test.to.package"],
    ["checkout.to.test", "test.skip"], ["test.skip", "test.to.package"],
    ["test.to.package", "package"], ["package", "package.to.publish"], ["package", "package.to.notify"],
    ["test.to.package", "package.skip"],
    ["package.skip", "package.to.publish"], ["package.skip", "package.to.notify"],
    ["package.to.publish", "publish"], ["publish", "publish.end"],
    ["package.to.publish", "publish.skip"], ["publish.skip", "publish.end"],
    ["package.to.notify", "notify"], ["notify", "notify.end"],
    ["package.to.notify", "notify.skip"], ["notify.skip", "notify.end"],
  ],
  "amk": {
    "backend": "petri",
    "steps": {
      **{t: {"run": t, "kind": "agoal.maybe"} for t in ["checkout", "package", "publish", "notify"]},
      "test": {"run": "test", "kind": "agoal.maybe", "bind": {"test.item": "$$(workflow.test.token)"}},
    },
    "guard": {
      "checkout": "all success", "checkout.skip": "not all success",
      "test.split": "all success", "test.skip": "not all success",
      "package": "all success", "package.skip": "not all success",
      "publish": "all success", "publish.skip": "not all success",
      "notify": "any failed", "notify.skip": "not any failed",
    },
    "label": {
      "checkout": "outcome", "checkout.skip": "skipped",
      "test.split": {"items": ["lua", "js", "micropy"]},
      "test": "outcome", "test.join": "merge", "test.skip": "skipped",
      "package": "outcome", "package.skip": "skipped",
      "publish": "outcome", "publish.skip": "skipped",
      "notify": "outcome", "notify.skip": "skipped",
    },
    "pools": {"runners": "runners"},
    "final": {"publish.end": 1, "notify.end": 1},
  },
}


def jq(amk, tmp_path, program, value, lib="workflow"):
  """One jq call with a library of lib/dsys included, its stdout and stderr."""
  mk = tmp_path / "jq.mk"
  mk.write_text("\n".join([
    f"$(info $(jq.argv -c -L /zip/lib/dsys,include \"{lib}\"; {program},{json.dumps(value)}))",
    "all:", "\t@true", "",
  ]))
  return sh(amk, ["-s", "-f", str(mk)], cwd=tmp_path, timeout=120)


def test_the_release_workflow_compiles_to_the_worked_example(amk, tmp_path):
  r = jq(amk, tmp_path, "compile", RELEASE)
  assert r.returncode == 0, r.stdout + r.stderr
  net = json.loads(r.stdout)
  assert net["places"] == GOLDEN["places"]
  assert net["transitions"] == GOLDEN["transitions"]
  assert sorted(map(json.dumps, net["arcs"])) == sorted(map(json.dumps, GOLDEN["arcs"]))
  assert net["amk"] == GOLDEN["amk"]


def test_topo_puts_needs_first_and_keeps_declaration_order(amk, tmp_path):
  wf = {"tasks": {"c": {"needs": ["a", "b"]}, "b": {"needs": ["a"]}, "a": {}, "d": {}}}
  r = jq(amk, tmp_path, "normalize | .order", wf)
  assert r.returncode == 0, r.stdout + r.stderr
  assert json.loads(r.stdout) == ["a", "d", "b", "c"]


def test_a_task_fragment_stands_alone(amk, tmp_path):
  wf = {"tasks": {"a": {"run": "x"}, "b": {"needs": ["a"], "when": "done"}}}
  r = jq(amk, tmp_path, "normalize | fragment(\"b\")", wf)
  assert r.returncode == 0, r.stdout + r.stderr
  assert json.loads(r.stdout) == {
    "places": {"b.end": []}, "transitions": ["b"],
    "arcs": [["a.to.b", "b"], ["b", "b.end"]],
    "amk": {"label": {"b": "outcome"}, "guard": {}},
  }


@pytest.mark.parametrize("wf,want", [
  ({"tasks": {"a": {"needs": ["z"]}}}, "a: needs z, which is no task"),
  ({"tasks": {"a": {"needs": ["b"]}, "b": {"needs": ["a"]}}}, "a: is on a cycle in needs"),
])
def test_a_malformed_workflow_is_refused(amk, tmp_path, wf, want):
  r = jq(amk, tmp_path, "compile", wf)
  assert r.returncode != 0 and want in r.stderr, r.stderr


PARITY = {
  "channels": {"numbers": ["1", "2", "3"], "evens": [], "odds": []},
  "processes": {
    "split": {"run": "split", "reads": ["numbers"], "writes": ["evens", "odds"]},
    "even": {"run": "even", "reads": ["evens"]},
    "odd": {"run": "odd", "reads": ["odds"]},
  },
}


IDLE = {"split.idle": 1, "even.idle": 1, "odd.idle": 1}


def test_a_kahn_network_compiles_to_an_open_net_with_reads_as_arcs(amk, tmp_path):
  r = jq(amk, tmp_path, "kahn", PARITY, lib="kahn")
  assert r.returncode == 0, r.stdout + r.stderr
  net = json.loads(r.stdout)
  assert net["places"] == {**PARITY["channels"], **IDLE}
  assert net["transitions"] == ["split", "even", "odd"]
  assert net["arcs"] == [["numbers", "split"], ["evens", "even"], ["odds", "odd"],
    ["split.idle", "split"], ["split", "split.idle"], ["even.idle", "even"], ["even", "even.idle"],
    ["odd.idle", "odd"], ["odd", "odd.idle"]]
  assert {s["kind"] for s in net["amk"]["steps"].values()} == {"agoal"}
  assert net["amk"]["strategy"] == "open" and "final" not in net["amk"]
  r = jq(amk, tmp_path, "kahn | .amk.final", {**PARITY, "final": {}}, lib="kahn")
  assert r.returncode == 0 and json.loads(r.stdout) == IDLE, r.stdout + r.stderr


@pytest.mark.parametrize("change,want", [
  ({"also": {"run": "x", "reads": ["evens"]}}, "evens: has 2 readers, not 1"),
  ({"spill": {"run": "x", "reads": ["numbers"], "writes": ["nowhere"]}}, "spill: names nowhere, which is no channel"),
])
def test_a_kahn_network_that_could_lose_determinism_is_refused(amk, tmp_path, change, want):
  wf = {**PARITY, "processes": {**PARITY["processes"], **change}}
  r = jq(amk, tmp_path, "kahn", wf, lib="kahn")
  assert r.returncode != 0 and want in r.stderr, r.stderr


def test_a_channel_named_like_a_control_place_is_refused(amk, tmp_path):
  wf = {**PARITY, "channels": {**PARITY["channels"], "even.idle": []}}
  r = jq(amk, tmp_path, "kahn", wf, lib="kahn")
  assert r.returncode != 0 and "even.idle: is a channel and the control place of process even" in r.stderr, r.stderr


@pytest.mark.engines("lua", "jq")
def test_load_kahn_makes_kahn_usable_without_workflow(amk, tmp_path):
  mk = tmp_path / "kahn.mk"
  mk.write_text("\n".join([
    "load dsys/kahn",
    "$(if $(filter undefined,$(origin workflow.dag_star)),,$(error workflow came along))",
    "@kahn", "define parity", json.dumps(PARITY), "endef",
    "@lua.target", "define split",
    '  local n = tonumber(amk.var["parity.split.token"])',
    '  amk.pool.produce("parity." .. (n % 2 == 0 and "evens" or "odds"), tostring(n))',
    "endef",
    "even:", "\t@echo 'even $(parity.even.token)'",
    "odd:", "\t@echo 'odd $(parity.odd.token)'",
    "show: parity.__main__", "\t@echo '[$(parity.marking )]'", "",
  ]))
  r = sh(amk, ["-s", "-f", str(mk), "show"], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  lines = r.stdout.splitlines()
  assert [l for l in lines if l.startswith("odd ")] == ["odd 1", "odd 3"], r.stdout
  assert [l for l in lines if l.startswith("even ")] == ["even 2"], r.stdout
  assert ("[numbers=0 evens=0 odds=0 split.idle=1 even.idle=1 odd.idle=1"
    " split.busy=0 even.busy=0 odd.busy=0]") in lines, r.stdout


@pytest.mark.engines("jq")
def test_kahn_and_workflow_register_as_stacked_engines_over_jq(amk, tmp_path):
  mk = tmp_path / "engines.mk"
  mk.write_text("\n".join([
    "load dsys/kahn", "load dsys/workflow",
    "$(info [$(filter petri kahn workflow.dag,$(amk.engines))] $(amk.engine.ext.kahn)/$(amk.engine.ext.workflow)"
    " $(amk.engine.kahn.guest)/$(amk.engine.workflow.dag.guest))", "all:", "\t@true", "",
  ]))
  r = sh(amk, ["-s", "-f", str(mk)], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[petri kahn workflow.dag] kahn/workflow.dag jq/jq" in r.stdout, r.stdout


@pytest.mark.engines("lua", "jq")
def test_a_created_kahn_network_is_joined_by_procs_and_versioned(amk, tmp_path):
  mk = tmp_path / "kahn.mk"
  mk.write_text("\n".join([
    "load dsys/kahn", "load dsys/workflow",
    'fb.src := {"channels": {"c": ["1", "2"]}, "processes": {}}',
    "$(kahn.create fb, $(fb.src))",
    "v0 := $(kahn.version fb)",
    "@fb.proc/lua (c)", "define p", '  print("p " .. amk.var["fb.p.token"])', "endef",
    "$(workflow.dag.create wf)",
    "show: fb.__main__",
    "\t@echo '[$(filter kahn workflow.dag,$(amk.data.engines))] moved=$(if $(filter $(v0),$(fb.version)),no,yes)"
    " [$(fb.trace)] [$(wf.exec .tasks | length)]'", "",
  ]))
  r = sh(amk, ["-s", "-f", str(mk), "show"], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "p 1\np 2\n[kahn workflow.dag] moved=yes [p p] [0]" in r.stdout, r.stdout


@pytest.mark.engines("jq")
def test_a_kahn_net_binds_its_source_and_library_to_exec(amk, tmp_path):
  mk = tmp_path / "kahn.mk"
  mk.write_text("\n".join([
    "load dsys/kahn", "@kahn", "define parity", json.dumps(PARITY), "endef",
    "$(info src=$(parity.exec $$source.processes | keys | length)"
    " net=$(parity.exec $$source | kahn::net | .arcs | length)"
    " ch=$(parity.exec $$marking.numbers))", "all:", "\t@true", "",
  ]))
  r = sh(amk, ["-s", "-f", str(mk)], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "src=3 net=9 ch=3" in r.stdout, r.stdout


@pytest.mark.engines("jq")
@pytest.mark.parametrize("deco,body,want", [
  ("workflow", {"tasks": {}}, "Property tasks: Less than minProperties 1"),
  ("workflow", {"tasks": {"a": {}}, "jobs": {}}, "Additional property 'jobs' not allowed"),
  ("workflow", {"tasks": {"A.b": {}}}, "Property tasks: Property name 'A.b': Does not match pattern ^[a-z0-9_-]+$"),
  ("workflow", {"tasks": {"a": {"over": {"data": ["two words"]}}}},
   "Property tasks: Additional property a: Property over: Property data: Does not match pattern ^\\S{1,31}$"),
  ("workflow", {"tasks": {"a": {"over": ["b"]}}},
   "Property tasks: Additional property a: Property over: "),
  ("workflow", {"tasks": {"a": {"over": {"data": ["b"], "targets": ["c"]}}}},
   "Property tasks: Additional property a: Property over: "),
  ("kahn", {"channels": {"a": []}, "processes": {"idle": {"run": "x"}}},
   "Property processes: Additional property idle: Missing required: reads"),
  ("workflow", {"tasks": {"a": {"retries": 2}}},
   "Property tasks: Additional property a: Additional property 'retries' not allowed"),
  ("workflow", {"tasks": {"a": {"when": "always"}}},
   'Property tasks: Additional property a: Property when: Value "always" not in enum; one of "success" "failed" "done"'),
  ("workflow", {"tasks": {"a": {"over": {"data": []}}}},
   "Property tasks: Additional property a: Property over: Property data: Less than minItems 1"),
  ("kahn", {"channels": {"a": []}, "processes": {"p": {"run": "x", "reads": ["a"], "retries": 1}}},
   "Property processes: Additional property p: Additional property 'retries' not allowed"),
  ("kahn", {"channels": {"a": []}, "processes": {"p": {"run": "x", "reads": []}}},
   "Property processes: Additional property p: Property reads: Less than minItems 1"),
  ("kahn", {"channels": {"a": []}, "processes": {"P.q": {"run": "x", "reads": ["a"]}}},
   "Property processes: Property name 'P.q': Does not match pattern ^[a-z0-9_-]+$"),
])
def test_a_decorated_body_is_checked_against_its_schema(amk, tmp_path, deco, body, want):
  mk = tmp_path / "net.mk"
  at = "workflow.dag" if deco == "workflow" else deco
  mk.write_text("\n".join([f"load dsys/{deco}", f"@{at}", "define net", json.dumps(body), "endef", ""]))
  r = sh(amk, ["-s", "-f", str(mk)], cwd=tmp_path, timeout=120)
  assert r.returncode != 0, r.stdout + r.stderr
  assert f"net: does not meet schema/{deco}.json: {want}" in r.stderr, r.stderr


@pytest.mark.engines("jq", "lua", "sqlite")
def test_a_late_process_is_checked_against_the_network_schema(amk, tmp_path):
  mk = tmp_path / "net.mk"
  mk.write_text("\n".join([
    "load dsys/kahn",
    "@kahn", "define net", '{ "channels": { "a": ["1"], "b": [] } }', "endef",
    "@net.proc/lua (a > b)", "define Bad.Name", '  print("p")', "endef", "",
  ]))
  r = sh(amk, ["-s", "-f", str(mk)], cwd=tmp_path, timeout=120)
  assert r.returncode != 0, r.stdout + r.stderr
  assert ("Bad.Name: does not meet schema/kahn.json: Property processes: "
          "Property name 'Bad.Name': Does not match pattern ^[a-z0-9_-]+$") in r.stderr, r.stderr


def release(test_body="@echo 'test $(test.item)'",package_body="@echo package"):
  return "\n".join([
    "load dsys/workflow",
    "$(amk.pool runners, 2)",
    "@workflow.dag", "define release", json.dumps(RELEASE), "endef",
    "checkout:", "\t@echo checkout",
    "test:", f"\t{test_body}",
    "package:", f"\t{package_body}",
    "publish:", "\t@echo publish",
    "notify:", "\t@echo notify",
    "show: release.__main__", "\t@echo '[$(release.states )]'",
    "",
  ])


def run(amk, tmp_path, body):
  mk = tmp_path / "wf.mk"
  mk.write_text(body)
  return sh(amk, ["-s", "-f", str(mk), "show"], cwd=tmp_path, timeout=120)


def test_the_release_runs_publish_and_skips_notify(amk, tmp_path):
  r = run(amk, tmp_path, release())
  assert r.returncode == 0, r.stdout + r.stderr
  assert re.search(r"checkout\ntest lua\ntest js\ntest micropy\npackage\npublish\n", r.stdout), r.stdout
  assert "test.join=success" in r.stdout and "publish=success" in r.stdout, r.stdout
  assert "notify.skip=skipped" in r.stdout and "notify=pending" in r.stdout, r.stdout


def test_a_failed_test_skips_everything_after_it_notify_included(amk, tmp_path):
  r = run(amk, tmp_path, release(test_body="@test '$(test.item)' != js"))
  assert r.returncode == 0, r.stdout + r.stderr
  for want in ["test.join=failed", "package.skip=skipped", "publish.skip=skipped", "notify.skip=skipped"]:
    assert want in r.stdout, r.stdout


def test_a_failed_package_skips_publish_and_runs_notify(amk, tmp_path):
  r = run(amk, tmp_path, release(package_body="@exit 1"))
  assert r.returncode == 0, r.stdout + r.stderr
  for want in ["package=failed", "publish.skip=skipped", "notify=success"]:
    assert want in r.stdout, r.stdout
  assert "notify\n" in r.stdout and "publish\n" not in r.stdout, r.stdout


def test_over_targets_hands_each_instance_its_targets_value(amk, tmp_path):
  wf = {"tasks": {
    "square": {"run": "each", "over": {"targets": ["b1", "b2"]}},
    "gather": {"run": "gather", "needs": ["square"]},
  }}
  mk = tmp_path / "wf.mk"
  mk.write_text("\n".join([
    "load dsys/workflow",
    "@workflow.dag", "define ingest", json.dumps(wf), "endef",
    "b1:", "\t@echo 1 2", "b2:", "\t@echo 3 4",
    "each:", "\t@echo 'each $(each.item)'",
    "gather:", "\t@echo gather",
    "show: ingest.__main__", "\t@echo '[$(ingest.state gather)]'", "",
  ]))
  r = sh(amk, ["-s", "-f", str(mk), "show"], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert sorted(re.findall(r"^each .*$", r.stdout, re.M)) == ["each 1 2", "each 3 4"], r.stdout
  assert "gather\n[success]" in r.stdout, r.stdout


def test_a_task_as_a_target_runs_it_and_all_it_needs_and_nothing_after(amk, tmp_path):
  mk = tmp_path / "wf.mk"
  mk.write_text(release())
  r = sh(amk, ["-s", "-f", str(mk), "release.package"], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert re.search(r"checkout\n(test \w+\n){3}package\n$", r.stdout), r.stdout
  assert "publish" not in r.stdout and "notify" not in r.stdout, r.stdout


def test_tasks_with_no_order_between_them_run_at_once_and_a_pool_of_one_runs_them_in_turn(amk, tmp_path):
  def took(pool):
    wf = {"tasks": {t: {"run": "nap", **pool} for t in ["a", "b", "c"]}}
    body = "\n".join([
      "load dsys/workflow", "$(amk.pool one, 1)",
      "@workflow.dag", "define w", json.dumps(wf), "endef",
      "nap:", "\t@sleep 1",
      "show: w.__main__", "\t@echo '[$(w.states )]'", "",
    ])
    t0 = time.monotonic()
    r = run(amk, tmp_path, body)
    assert r.returncode == 0, r.stdout + r.stderr
    assert all(f"{t}=success" in r.stdout for t in "abc"), r.stdout
    return time.monotonic() - t0
  assert took({}) < 2.5
  assert took({"pool": "one"}) >= 3

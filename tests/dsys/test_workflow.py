"""Pins workflows: `lib/dsys/workflow.amk`, a task graph compiled by workflow.jq to a net dsys/petri runs.

The compiler is a jq library of definitions, so it is pinned whole against the worked
example of its rules, by its definitions alone through include, by its refusals, and end
to end through @workflow on the success and the failure path.
"""

import json
import re

import pytest

from conftest import sh

pytestmark = pytest.mark.engines("jq")

RELEASE = {
  "tasks": {
    "checkout": {"run": "checkout"},
    "test": {"run": "test", "needs": ["checkout"], "over": ["lua", "js", "micropy"], "pool": "runners"},
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
    "steps": {t: {"run": t, "kind": "goal.maybe"} for t in ["checkout", "test", "package", "publish", "notify"]},
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


def test_a_kahn_network_compiles_to_an_open_net_with_reads_as_arcs(amk, tmp_path):
  r = jq(amk, tmp_path, "kahn", PARITY, lib="kahn")
  assert r.returncode == 0, r.stdout + r.stderr
  net = json.loads(r.stdout)
  assert net["places"] == PARITY["channels"]
  assert net["transitions"] == ["split", "even", "odd"]
  assert net["arcs"] == [["numbers", "split"], ["evens", "even"], ["odds", "odd"]]
  assert net["amk"]["strategy"] == "open" and "final" not in net["amk"]
  r = jq(amk, tmp_path, "kahn | .amk.final", {**PARITY, "final": {}}, lib="kahn")
  assert r.returncode == 0 and json.loads(r.stdout) == {}, r.stdout + r.stderr


@pytest.mark.parametrize("change,want", [
  ({"also": {"run": "x", "reads": ["evens"]}}, "evens: has 2 readers, not 1"),
  ({"spill": {"run": "x", "reads": ["numbers"], "writes": ["nowhere"]}}, "spill: names nowhere, which is no channel"),
])
def test_a_kahn_network_that_could_lose_determinism_is_refused(amk, tmp_path, change, want):
  wf = {**PARITY, "processes": {**PARITY["processes"], **change}}
  r = jq(amk, tmp_path, "kahn", wf, lib="kahn")
  assert r.returncode != 0 and want in r.stderr, r.stderr


@pytest.mark.engines("lua", "jq")
def test_load_kahn_makes_kahn_usable_without_workflow(amk, tmp_path):
  mk = tmp_path / "kahn.mk"
  mk.write_text("\n".join([
    "load dsys/kahn",
    "$(if $(filter undefined,$(origin workflow_star)),,$(error workflow came along))",
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
  assert "even 2\nodd 1\nodd 3\n[numbers=0 evens=0 odds=0]" in r.stdout, r.stdout


@pytest.mark.engines("jq")
def test_kahn_and_workflow_register_as_stacked_engines_over_jq(amk, tmp_path):
  mk = tmp_path / "engines.mk"
  mk.write_text("\n".join([
    "load dsys/kahn", "load dsys/workflow",
    "$(info [$(filter petri kahn workflow,$(amk.engines))] $(amk.engine.ext.kahn)/$(amk.engine.ext.workflow)"
    " $(amk.engine.kahn.guest)/$(amk.engine.workflow.guest))", "all:", "\t@true", "",
  ]))
  r = sh(amk, ["-s", "-f", str(mk)], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[petri kahn workflow] kahn/workflow jq/jq" in r.stdout, r.stdout


@pytest.mark.engines("lua", "jq")
def test_a_created_kahn_network_is_joined_by_procs_and_versioned(amk, tmp_path):
  mk = tmp_path / "kahn.mk"
  mk.write_text("\n".join([
    "load dsys/kahn", "load dsys/workflow",
    'fb.src := {"channels": {"c": ["1", "2"]}, "processes": {}}',
    "$(kahn.create fb, $(fb.src))",
    "v0 := $(kahn.version fb)",
    "@fb.proc/lua (c)", "define p", '  print("p " .. amk.var["fb.p.token"])', "endef",
    "$(workflow.create wf)",
    "show: fb.__main__",
    "\t@echo '[$(filter kahn workflow,$(amk.data.engines))] moved=$(if $(filter $(v0),$(fb.version)),no,yes)"
    " [$(fb.trace)] [$(wf.exec .tasks | length)]'", "",
  ]))
  r = sh(amk, ["-s", "-f", str(mk), "show"], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "p 1\np 2\n[kahn workflow] moved=yes [p p] [0]" in r.stdout, r.stdout


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
  assert "src=3 net=3 ch=3" in r.stdout, r.stdout


@pytest.mark.engines("jq")
@pytest.mark.parametrize("deco,body,want", [
  ("workflow", {"tasks": {}}, "Property tasks: Less than minProperties 1"),
  ("workflow", {"tasks": {"a": {}}, "jobs": {}}, "Additional property 'jobs' not allowed"),
  ("workflow", {"tasks": {"A.b": {}}}, "Property tasks: Property name 'A.b': Does not match pattern ^[a-z0-9_-]+$"),
  ("workflow", {"tasks": {"a": {"over": ["two words"]}}},
   "Property tasks: Additional property a: Property over: Does not match pattern ^\\S{1,31}$"),
  ("kahn", {"channels": {"a": []}, "processes": {"idle": {"run": "x"}}},
   "Property processes: Additional property idle: Missing required: reads"),
  ("workflow", {"tasks": {"a": {"retries": 2}}},
   "Property tasks: Additional property a: Additional property 'retries' not allowed"),
  ("workflow", {"tasks": {"a": {"when": "always"}}},
   'Property tasks: Additional property a: Property when: Value "always" not in enum; one of "success" "failed" "done"'),
  ("workflow", {"tasks": {"a": {"over": []}}},
   "Property tasks: Additional property a: Property over: Less than minItems 1"),
  ("kahn", {"channels": {"a": []}, "processes": {"p": {"run": "x", "reads": ["a"], "retries": 1}}},
   "Property processes: Additional property p: Additional property 'retries' not allowed"),
  ("kahn", {"channels": {"a": []}, "processes": {"p": {"run": "x", "reads": []}}},
   "Property processes: Additional property p: Property reads: Less than minItems 1"),
  ("kahn", {"channels": {"a": []}, "processes": {"P.q": {"run": "x", "reads": ["a"]}}},
   "Property processes: Property name 'P.q': Does not match pattern ^[a-z0-9_-]+$"),
])
def test_a_decorated_body_is_checked_against_its_schema(amk, tmp_path, deco, body, want):
  mk = tmp_path / "net.mk"
  mk.write_text("\n".join([f"load dsys/{deco}", f"@{deco}", "define net", json.dumps(body), "endef", ""]))
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


def release(test_body="@echo 'test $(release.test.token)'", package_body="@echo package"):
  return "\n".join([
    "load dsys/workflow",
    "$(amk.pool runners, 2)",
    "@workflow", "define release", json.dumps(RELEASE), "endef",
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
  r = run(amk, tmp_path, release(test_body="@test '$(release.test.token)' != js"))
  assert r.returncode == 0, r.stdout + r.stderr
  for want in ["test.join=failed", "package.skip=skipped", "publish.skip=skipped", "notify.skip=skipped"]:
    assert want in r.stdout, r.stdout


def test_a_failed_package_skips_publish_and_runs_notify(amk, tmp_path):
  r = run(amk, tmp_path, release(package_body="@exit 1"))
  assert r.returncode == 0, r.stdout + r.stderr
  for want in ["package=failed", "publish.skip=skipped", "notify=success"]:
    assert want in r.stdout, r.stdout
  assert "notify\n" in r.stdout and "publish\n" not in r.stdout, r.stdout

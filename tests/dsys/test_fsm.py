"""Pins state machines: `lib/dsys/fsm.amk`, an xstate machine config lowered to a net.

A config under @fsm is normalized to the definition xstate serializes, checked against
xstate's own machine schema, and compiled to a net: a place per state holding the machine's
one token, an open place per event the environment feeds, a transition per entry under on or
always. Pinned: the door's definition passes the schema, a chain runs its events to its final
state, always fires without an event and first, the subset refuses the rest, the engine row.
"""

import json
import time

import pytest

from conftest import sh

pytestmark = pytest.mark.engines("jq")

DOOR = {
  "id": "door", "initial": "locked",
  "states": {
    "locked": {"entry": "bolt", "on": {"unlock": "closed"}},
    "closed": {"entry": "latch", "on": {"pull": "checking", "lock": "locked"}},
    "checking": {"invoke": {"src": "hinge", "onDone": [
      {"guard": "jammed", "target": "closed"}, {"guard": "snapped", "target": "broken"}, {"target": "open"}]}},
    "open": {"entry": "swing", "on": {"push": "closed"}},
    "broken": {"type": "final"},
  },
}

CHAIN = {
  "id": "chain", "initial": "a",
  "states": {
    "a": {"on": {"x": "b"}}, "b": {"on": {"y": "c", "x": "b"}}, "c": {"on": {"z": "done"}},
    "done": {"type": "final"},
  },
}


def run(amk, tmp_path, lines, goal="all"):
  mk = tmp_path / "fsm.mk"
  mk.write_text("\n".join(["load dsys/fsm", *lines, "all:", "\t@true", ""]))
  return sh(amk, ["-s", "-f", str(mk), goal], cwd=tmp_path, timeout=120)


def test_the_door_normalizes_to_a_definition_the_xstate_schema_accepts(amk, tmp_path):
  r = run(amk, tmp_path, [
    "load io/json", "define door", json.dumps(DOOR), "endef",
    "prog := include \"fsm\"; include \"schema\"; normalize as $$d"
    " | ($$d | schema_errors($$s[0]) | length), ($$d.states.checking.on | keys)",
    "$(info $(jq.argv -c -L $(fsm._lib) -L $(json._lib)"
    " --slurpfile s $(fsm._lib)/schema/xstate.machine.json,$(prog),$(amk.val.json5 door)))",
  ])
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.split() == ["0", '["done.invoke.0.door.checking"]'], r.stdout


def test_a_chain_of_states_runs_its_events_to_its_final_state(amk, tmp_path):
  r = run(amk, tmp_path, [
    "@fsm", "define m", json.dumps(CHAIN), "endef",
    "$(amk.pool.produce m.ev.x)", "$(amk.pool.produce m.ev.y)", "$(amk.pool.produce m.ev.z)",
    "show: m.__main__", "\t@echo '[$(m.trace)] [$(m.marking )]'",
  ], "show")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[a.x b.y c.z] [a=0 b=0 c=0 done=1 ev.x=0 ev.y=0 ev.z=0]" in r.stdout, r.stdout


ALWAYS = {
  "id": "m", "initial": "a",
  "states": {
    "a": {"on": {"x": "b"}}, "b": {"always": "c"}, "c": {"on": {"y": "d"}, "always": [{"target": "e"}]},
    "d": {"type": "final"}, "e": {"on": {"z": "d"}},
  },
}


def test_an_always_transition_needs_no_event_and_outranks_one(amk, tmp_path):
  r = run(amk, tmp_path, [
    "@fsm", "define m", json.dumps(ALWAYS), "endef",
    "$(amk.pool.produce m.ev.x)", "$(amk.pool.produce m.ev.z)",
    "show: m.__main__", "\t@echo '[$(m.trace)] [$(m.marking )]'",
  ], "show")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[a.x b.always c.always e.z] [a=0 b=0 c=0 d=1 e=0 ev.x=0 ev.y=0 ev.z=0]" in r.stdout, r.stdout


def test_a_targetless_transition_consumes_its_event_and_stays(amk, tmp_path):
  m = {"id": "m", "initial": "a", "states": {
    "a": {"on": {"tick": {}, "go": "b"}}, "b": {"type": "final"}}}
  r = run(amk, tmp_path, [
    "@fsm", "define m", json.dumps(m), "endef", "$(amk.pool.produce m.ev.tick)",
    "$(info S1 $(m.step ) $(m.marking ))", "$(amk.pool.produce m.ev.go)", "$(info S2 $(m.step ) $(m.marking ))",
  ])
  assert r.returncode == 0, r.stdout + r.stderr
  assert "S1 a.tick a=1 b=0 ev.go=0 ev.tick=0" in r.stdout and "S2 a.go a=0 b=1" in r.stdout, r.stdout


WILD = {"id": "m", "initial": "a", "states": {
  "a": {"on": {"x": "named", "foo.*": "under", "*": "any"}},
  "named": {"type": "final"}, "under": {"type": "final"}, "any": {"type": "final"}}}


@pytest.mark.parametrize("event,place", [("x", "named"), ("foo.bar", "under"), ("foo", "any"), ("zzz", "any")])
def test_a_wildcard_takes_the_events_no_descriptor_names_by_the_closest_match(amk, tmp_path, event, place):
  r = run(amk, tmp_path, [
    "@fsm", "define m", json.dumps(WILD), "endef", f"$(m.send {event})",
    "$(info S $(m.step ) $(m.marking ))",
  ])
  assert r.returncode == 0, r.stdout + r.stderr
  assert f"{place}=1" in r.stdout and "=1 " in r.stdout and "ev.foo._=0" in r.stdout and "ev._=0" in r.stdout, r.stdout


DONE = {"id": "m", "initial": "s0", "states": {
  "s0": {"initial": "a", "onDone": "pass", "on": {"quit": "fail"},
         "states": {"a": {"on": {"x": "f", "y": "f2"}}, "f": {"type": "final"}, "f2": {"type": "final"}}},
  "pass": {"type": "final"}, "fail": {"type": "final"}}}


def test_a_nested_final_raises_done_for_its_parent_to_take(amk, tmp_path):
  r = run(amk, tmp_path, [
    "@fsm", "define m", json.dumps(DONE), "endef", "$(m.send x)",
    "show: m.__main__", "\t@echo '[$(m.trace)] [$(m.marking )]'",
  ], "show")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[s0.a.x s0.f.done.state.s0] [" in r.stdout and " pass=1 " in r.stdout, r.stdout


ACTIONS = [
  "bolt:", "\t@echo 'bolted on [$(door.event)]'",
  "latch:", "\t@echo 'latched on [$(door.event)]'",
  "unlatch:", "\t@echo 'unlatched on [$(door.event)]'",
  "swing:", "\t@echo 'swung on [$(door.event)]'",
  "hinge:", "\t@echo $(word $(words x $(filter checking.invoke,$(door.trace))),jam ok snap)",
  "jammed = $(filter jam,$(door.checking.output))",
  "snapped:", "\t@test \"$(door.checking.output)\" = snap",
]


def test_the_door_runs_its_actions_its_service_and_its_guards(amk, tmp_path):
  """The guards: jammed is a variable answering by its value, snapped a target by its exit status."""
  r = run(amk, tmp_path, [
    "@fsm", "define door", json.dumps(DOOR), "endef", *ACTIONS,
    *[f"$(door.send {e})" for e in ["unlock", "pull", "pull", "push", "pull"]],
    "show: door.__main__", "\t@echo 'state: $(door.state ) trace: $(door.trace)'",
  ], "show")
  assert r.returncode == 0, r.stdout + r.stderr
  want = ["bolted on []", "latched on [unlock]", "jam", "latched on [done.invoke.0.door.checking]", "ok",
          "swung on [done.invoke.0.door.checking]", "latched on [push]", "snap"]
  assert [ln for ln in r.stdout.splitlines() if ln in want] == want, r.stdout
  assert [ln for ln in r.stdout.splitlines() if ln.strip().isdigit()] == [], r.stdout
  assert r.stderr.count("Error 1") == 1, r.stderr
  state = r.stdout.rstrip().splitlines()[-1]
  done = "checking.done.invoke.0.door.checking"
  assert state.startswith(f"state: broken trace: locked.unlock closed.pull checking.invoke {done} "), state
  assert f" {done}.1 " in state and f" {done}.3 " in state, state
  assert state.endswith(f"{done}.2"), state


def test_a_machine_with_no_id_binds_its_event_under_its_name_and_a_final_runs_its_entry(amk, tmp_path):
  m = {"initial": "a", "states": {
    "a": {"on": {"go": "b"}}, "b": {"type": "final", "entry": "arrive"}}}
  r = run(amk, tmp_path, [
    "@fsm", "define m", json.dumps(m), "endef",
    "arrive:", "\t@echo 'arrived on [$(m.event)]'",
    "$(m.send go)",
    "show: m.__main__", "\t@echo '[$(m.trace)]'",
  ], "show")
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.splitlines()[-2:] == ["arrived on [go]", "[a.go]"], r.stdout


def test_each_top_level_final_state_is_an_acceptance_marking(amk, tmp_path):
  m = {"id": "m", "initial": "a", "states": {
    "a": {"on": {"ok": "pass", "no": "fail"}}, "pass": {"type": "final"}, "fail": {"type": "final"}}}
  r = run(amk, tmp_path, [
    "@fsm", "define m", json.dumps(m), "endef", "$(amk.pool.produce m.ev.no)",
    "show: m.__main__", "\t@echo '[$(m.trace)] [$(m.marking )]'",
  ], "show")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[a.no] [a=0 pass=0 fail=1 ev.no=0 ev.ok=0]" in r.stdout, r.stdout


def test_a_compound_state_inherits_its_transitions_and_enters_its_initial(amk, tmp_path):
  config = {
    "id": "m", "initial": "shut",
    "states": {
      "shut": {"initial": "locked", "on": {"alarm": "broken"},
               "states": {"locked": {"on": {"unlock": "unlocked"}},
                          "unlocked": {"on": {"lock": "locked", "open": "#m.open"}}}},
      "open": {"on": {"close": "shut"}},
      "broken": {"type": "final"},
    },
  }
  r = run(amk, tmp_path, [
    "@fsm", "define m", json.dumps(config), "endef",
    "$(amk.pool.produce m.ev.unlock)", "$(info step1 $(m.step ))",
    "$(amk.pool.produce m.ev.open)", "$(info step2 $(m.step ))",
    "$(amk.pool.produce m.ev.close)", "$(info step3 $(m.step ) $(m.marking shut.locked))",
    "$(amk.pool.produce m.ev.alarm)", "$(info step4 $(m.step ))",
    "show: m.__main__", "\t@echo '[$(m.trace)] [$(m.marking broken)]'",
  ], "show")
  assert r.returncode == 0, r.stdout + r.stderr
  for want in ["step1 shut.locked.unlock", "step2 shut.unlocked.open", "step3 open.close 1",
               "step4 shut.locked.alarm", "[shut.locked.unlock shut.unlocked.open open.close shut.locked.alarm] [1]"]:
    assert want in r.stdout, r.stdout


def test_a_parallel_state_holds_a_token_per_region_and_leaves_as_one(amk, tmp_path):
  config = {
    "id": "m", "initial": "run",
    "states": {
      "run": {"type": "parallel", "on": {"stop": "halt"},
              "states": {"light": {"initial": "off", "states": {"off": {"on": {"toggle": "on"}}, "on": {"on": {"toggle": "off"}}}},
                         "door": {"initial": "closed", "states": {"closed": {"on": {"open": "opened"}}, "opened": {"on": {"close": "closed"}}}}}},
      "halt": {"type": "final"},
    },
  }
  r = run(amk, tmp_path, [
    "@fsm", "define m", json.dumps(config), "endef",
    "$(info start $(m.marking run.light.off) $(m.marking run.door.closed))",
    "$(amk.pool.produce m.ev.toggle)", "$(info step1 $(m.step ))",
    "$(amk.pool.produce m.ev.open)", "$(info step2 $(m.step ) $(m.marking run.light.on) $(m.marking run.door.opened))",
    "$(amk.pool.produce m.ev.stop)", "$(info step3 $(m.step ))",
    "show: m.__main__", "\t@echo '[$(m.trace)] [$(m.marking )]'",
  ], "show")
  assert r.returncode == 0, r.stdout + r.stderr
  for want in ["start 1 1", "step1 run.off-closed.toggle", "step2 run.on-closed.open 1 1", "step3 run.on-opened.stop",
               "halt=1", "run.light.on=0", "run.door.opened=0"]:
    assert want in r.stdout, r.stdout


REGIONS = {
  "id": "m", "initial": ["#m.p.r.b", "#m.p.s.d"],
  "states": {
    "p": {"type": "parallel", "on": {"reset": {"target": ["#m.p.r.a", "#m.p.s.c"]}}, "states": {
      "r": {"initial": "a", "states": {
        "a": {"on": {"go": "b"}},
        "b": {"on": {"ask": [{"guard": "@p.s.d", "target": "#m.pass"}, {"target": "#m.fail"}]}}}},
      "s": {"initial": "c", "states": {"c": {"on": {"go": "d"}}, "d": {}}}}},
    "pass": {"type": "final"}, "fail": {"type": "final"},
  },
}


def test_initials_and_targets_name_one_leaf_per_region_and_guards_read_the_configuration(amk, tmp_path):
  """A deep initial lands in both regions; reset is a two-target transition; the In guard reads the sibling region."""
  r = run(amk, tmp_path, [
    "@fsm", "define m", json.dumps(REGIONS), "endef",
    "$(info start $(m.state ))",
    "$(m.send reset)", "$(info S1 $(m.step ) $(m.state ))",
    "$(m.send go)", "$(info S2 $(m.step ) $(m.state ))",
    "$(m.send ask)", "$(info S3 $(m.step ) $(m.step ) $(m.state ))",
    "$(info picks $(m.net ))",
  ])
  assert r.returncode == 0, r.stdout + r.stderr
  for want in ["start p.r.b p.s.d", "S1 p.b-d.reset p.r.a p.s.c", "S2 p.a-c.go p.r.b p.s.d", "S3 p.b-d.ask p.b-d.ask.1 pass"]:
    assert want in r.stdout, r.stdout
  net = json.loads(r.stdout.split("picks ", 1)[1].splitlines()[0])
  assert net["fsm"]["pickers"] == {"m.p.b-c.ask.pick": [["@p.s.d", "-"]], "m.p.b-d.ask.pick": [["@p.s.d", "-"]]}, net["fsm"]
  assert net["amk"]["steps"]["p.b-d.ask"]["bind"] == {"m.config": "p,p.r,p.r.b,p.s,p.s.d"}, net["amk"]["steps"]


def test_a_service_inside_a_parallel_state_is_a_position_of_its_region(amk, tmp_path):
  m = {"id": "m", "initial": "p", "states": {
    "p": {"type": "parallel", "on": {"quit": "fail"}, "states": {
      "r": {"initial": "c", "states": {"c": {"invoke": {"src": "svc", "onDone": [
        {"guard": "@p.s.e", "target": "#m.pass"}, {"target": "#m.fail"}]}}}},
      "s": {"initial": "d", "states": {"d": {"on": {"go": "e"}}, "e": {}}}}},
    "pass": {"type": "final"}, "fail": {"type": "final"}}}
  r = run(amk, tmp_path, [
    "@fsm", "define m", json.dumps(m), "endef", "svc:", "\t@echo served",
    "$(m.send go)",
    "show: m.__main__", "\t@echo 'state: $(m.state ) trace: $(m.trace)'",
  ], "show")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "served" in r.stdout, r.stdout
  assert "state: pass trace: p.r.c.invoke p.c.invoked-d.go p.c.invoked-e.done.invoke.0.m.p.r.c p.c.invoked-e.done.invoke.0.m.p.r.c.1" in r.stdout, r.stdout


def test_services_in_two_regions_overlap(amk, tmp_path):
  m = {"id": "m", "initial": "p", "states": {
    "p": {"type": "parallel", "onDone": "end", "states": {
      "r": {"initial": "a", "states": {"a": {"invoke": {"src": "nap1", "onDone": "x"}}, "x": {"type": "final"}}},
      "s": {"initial": "b", "states": {"b": {"invoke": {"src": "nap2", "onDone": "y"}}, "y": {"type": "final"}}}}},
    "end": {"type": "final"}}}
  t0 = time.monotonic()
  r = run(amk, tmp_path, ["@fsm", "define m", json.dumps(m), "endef",
    "nap1 nap2:", "\t@sleep 3", "show: m.__main__", "\t@echo 'state: $(m.state )'"], "show")
  took = time.monotonic() - t0
  assert r.returncode == 0, r.stdout + r.stderr
  assert "state: end" in r.stdout, r.stdout
  assert took < 5.5, took


def child(name, src):
  return ["@fsm", f"define {name}", json.dumps({"id": name, "initial": "a", "states": {
    "a": {"invoke": {"src": src, "onDone": "z"}}, "z": {"type": "final"}}}), "endef"]


def test_a_machine_invokes_another_machine_in_place(amk, tmp_path):
  r = run(amk, tmp_path, [*child("c", "work"), "work:", "\t@echo worked", *child("sup", "c.__main__"),
    "show: sup.__main__", "\t@echo 'state: $(sup.state )'"], "show")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "worked" in r.stdout and "state: z" in r.stdout, r.stdout


def test_regions_invoke_machines_at_once_and_one_machine_twice(amk, tmp_path):
  m = {"id": "sup", "initial": "p", "states": {
    "p": {"type": "parallel", "onDone": "end", "states": {
      r: {"initial": "a", "states": {"a": {"invoke": {"src": src, "onDone": "x"}}, "x": {"type": "final"}}}
      for r, src in [("r", "c1.__main__"), ("s", "c2.__main__"), ("t", "c1.__main__")]}},
    "end": {"type": "final"}}}
  t0 = time.monotonic()
  r = run(amk, tmp_path, [*child("c1", "nap1"), *child("c2", "nap2"), "nap1 nap2:", "\t@sleep 3; echo $@",
    "@fsm", "define sup", json.dumps(m), "endef", "show: sup.__main__", "\t@echo 'state: $(sup.state )'"], "show")
  took = time.monotonic() - t0
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.count("nap1") == 2 and "nap2" in r.stdout, r.stdout
  assert "state: end" in r.stdout, r.stdout
  assert took < 5.5, took


KID = ["@fsm", "define kid", json.dumps({"id": "kid", "initial": "a", "states": {
  "a": {"on": {"go": "b"}}, "b": {"type": "final", "entry": "arrived"}}}), "endef",
  "arrived:", "\t@echo arrived $(kid.instance)"]


def test_a_job_beside_a_supervisor_sends_to_its_running_child(amk, tmp_path):
  sup = {"id": "sup", "initial": "calling", "states": {
    "calling": {"invoke": {"src": "kid.__main__", "onDone": "done"}}, "done": {"type": "final"}}}
  r = run(amk, tmp_path, [*KID, "@fsm", "define sup", json.dumps(sup), "endef",
    "nap:", "\t@sleep 1", "tell: nap", "\t@echo tells $(kid.send go)",
    "spawn:", "\t@echo spawned $(amk.goal.spawn tell)",
    "show: spawn sup.__main__", "\t@echo 'state: $(sup.state )'"], "show")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "arrived 0.sup.calling" in r.stdout and "state: done" in r.stdout, r.stdout


def test_two_instances_of_one_machine_each_take_their_own_event(amk, tmp_path):
  sup = {"id": "sup", "initial": "p", "states": {
    "p": {"type": "parallel", "onDone": "end", "states": {
      reg: {"initial": "a", "states": {"a": {"invoke": {"src": "kid.__main__", "onDone": "x"}}, "x": {"type": "final"}}}
      for reg in ["r", "s"]}},
    "end": {"type": "final"}}}
  r = run(amk, tmp_path, [*KID, "@fsm", "define sup", json.dumps(sup), "endef",
    "nap:", "\t@sleep 1", "tell.s: nap", "\t@echo $(fsm.send 0.sup.p.s.a, go)",
    "nap.again: tell.s", "\t@sleep 1", "tell.r: nap.again", "\t@echo $(fsm.send 0.sup.p.r.a, go)",
    "spawn:", "\t@echo spawned $(amk.goal.spawn tell.r)",
    "show: spawn sup.__main__", "\t@echo 'state: $(sup.state )'"], "show")
  assert r.returncode == 0, r.stdout + r.stderr
  arrivals = [l for l in r.stdout.splitlines() if l.startswith("arrived")]
  assert arrivals == ["arrived 0.sup.p.s.a", "arrived 0.sup.p.r.a"], r.stdout
  assert "state: end" in r.stdout, r.stdout


def test_a_send_to_a_machine_with_several_instances_is_refused(amk, tmp_path):
  sup = {"id": "sup", "initial": "p", "states": {
    "p": {"type": "parallel", "states": {
      reg: {"initial": "a", "states": {"a": {"invoke": {"src": "kid.__main__"}}}} for reg in ["r", "s"]}}}}
  r = run(amk, tmp_path, [*KID, "@fsm", "define sup", json.dumps(sup), "endef", "$(kid.send go)"])
  assert r.returncode != 0, r.stdout
  assert "kid: a token for ev.go is ambiguous among instances 0.sup.p.r.a 0.sup.p.s.a" in r.stderr, r.stderr


def test_a_region_of_a_supervisor_steers_the_child_another_region_invokes(amk, tmp_path):
  sup = {"id": "sup", "initial": "p", "states": {
    "p": {"type": "parallel", "onDone": "end", "states": {
      "r": {"initial": "a", "states": {"a": {"invoke": {"src": "kid.__main__", "onDone": "x"}}, "x": {"type": "final"}}},
      "s": {"initial": "a", "states": {"a": {"invoke": {"src": "teller", "onDone": "x"}}, "x": {"type": "final"}}}}},
    "end": {"type": "final"}}}
  r = run(amk, tmp_path, [*KID, "@fsm", "define sup", json.dumps(sup), "endef",
    "nap:", "\t@sleep 1",
    "teller: nap", "\t@echo tells $(kid.send go)",
    "show: sup.__main__", "\t@echo 'state: $(sup.state )'"], "show")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "arrived 0.sup.p.r.a" in r.stdout and "state: end" in r.stdout, r.stdout


def test_a_child_machine_sends_to_its_parent_while_both_run(amk, tmp_path):
  kid = {"id": "kid", "initial": "a", "states": {"a": {"entry": "ping", "always": "b"}, "b": {"type": "final"}}}
  sup = {"id": "sup", "initial": "calling", "states": {
    "calling": {"invoke": {"src": "kid.__main__", "onDone": "waiting"}},
    "waiting": {"on": {"ping": "done"}}, "done": {"type": "final"}}}
  r = run(amk, tmp_path, ["@fsm", "define kid", json.dumps(kid), "endef",
    "ping:", "\t@echo pings $(sup.send ping)",
    "@fsm", "define sup", json.dumps(sup), "endef",
    "show: sup.__main__", "\t@echo '[$(sup.trace)]'"], "show")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[calling.invoke calling.done.invoke.0.sup.calling waiting.ping]" in r.stdout, r.stdout


def test_a_job_beside_a_machine_sends_to_it_while_it_runs(amk, tmp_path):
  m = {"id": "m", "initial": "a", "states": {
    "a": {"on": {"go": "b"}}, "b": {"on": {"stop": "c"}}, "c": {"type": "final"}}}
  r = run(amk, tmp_path, ["@fsm", "define m", json.dumps(m), "endef",
    "nap.%:", "\t@sleep 0.5",
    "send.%: nap.%", "\t@echo sends $* $(m.send $*)",
    "visitor: send.go send.stop", "\t@true",
    "spawn:", "\t@echo spawned $(amk.goal.spawn visitor)",
    "show: spawn m.__main__", "\t@echo '[$(m.trace)]'"], "show")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[a.go b.stop]" in r.stdout, r.stdout


def test_a_send_to_an_instance_that_has_ended_is_refused(amk, tmp_path):
  kid = {"id": "kid", "initial": "a", "states": {"a": {"always": "b", "on": {"go": "b"}}, "b": {"type": "final"}}}
  sup = {"id": "sup", "initial": "calling", "states": {
    "calling": {"invoke": {"src": "kid.__main__", "onDone": "done"}}, "done": {"type": "final"}}}
  r = run(amk, tmp_path, ["@fsm", "define kid", json.dumps(kid), "endef",
    "@fsm", "define sup", json.dumps(sup), "endef",
    "late: sup.__main__", "\t@echo late $(kid.send go)"], "late")
  assert r.returncode != 0, r.stdout
  assert "kid: instance 0.sup.calling is not running, so nothing takes a token for ev.go" in r.stderr, r.stderr


def test_a_job_forked_before_an_instance_ended_is_refused_a_send_to_it(amk, tmp_path):
  kid = {"id": "kid", "initial": "a", "states": {"a": {"always": "b", "on": {"go": "b"}}, "b": {"type": "final"}}}
  sup = {"id": "sup", "initial": "calling", "states": {
    "calling": {"invoke": {"src": "kid.__main__", "onDone": "done"}}, "done": {"type": "final"}}}
  r = run(amk, tmp_path, ["@fsm", "define kid", json.dumps(kid), "endef",
    "@fsm", "define sup", json.dumps(sup), "endef",
    "nap:", "\t@sleep 1",
    "late: nap", "\t@echo late $(kid.send go)",
    "spawn:", "\t@echo spawned $(eval pid := $(amk.goal.spawn late))",
    "show: spawn sup.__main__", "\t@echo 'state: $(sup.state )' $(amk.job.wait $(pid))"], "show")
  assert "state: done" in r.stdout, r.stdout + r.stderr
  assert "kid: instance 0.sup.calling is not running, so nothing takes a token for ev.go" in r.stderr, r.stderr


@pytest.mark.parametrize("config,want", [
  ({"initial": "a", "states": {"a": {"on": {"x": "b"}},
    "b": {"type": "parallel", "states": {"r": {"type": "parallel", "states": {"c": {}, "d": {}}}, "s": {}}}}},
   "machine.b.r: a parallel state inside a parallel state is not lowered yet"),
  ({"initial": "a", "states": {"a": {"on": {"x": {"target": ["b", "c"]}}}, "b": {}, "c": {}}},
   "machine.a: targets b c are not one per region of a parallel state"),
  ({"initial": "a", "states": {"a": {"initial": "#machine.c", "states": {"b": {}}}, "c": {}}},
   "machine.a: initial c is no state"),
  ({"initial": "a", "states": {"a": {}}, "after": {"1000": "a"}}, "does not meet schema/fsm.json"),
  ({"initial": "a", "states": {"a": {}}, "always": "a"}, "does not meet schema/fsm.json: Additional property 'always'"),
  ({"initial": "a", "states": {"a": {"on": {"x": "h"}}, "h": {"type": "history"}}}, "does not meet schema/fsm.json"),
  ({"initial": "a", "states": {"a": {"always": [{"guard": "g", "target": "b"}]}, "b": {}}},
   "machine.a: an eventless transition with guards needs an unguarded alternative"),
])
def test_the_subset_refuses_what_it_does_not_lower(amk, tmp_path, config, want):
  r = run(amk, tmp_path, ["@fsm", "define machine", json.dumps(config), "endef"])
  assert r.returncode != 0, r.stdout + r.stderr
  assert want in r.stderr, r.stderr


CHAIN_SCXML = "\n".join([
  '<?xml version="1.0" encoding="UTF-8"?>',
  '<scxml xmlns="http://www.w3.org/2005/07/scxml" version="1.0" initial="a" name="chain">',
  '  <state id="a"><transition event="x" target="b"/></state>',
  '  <state id="b"><transition event="y" target="c"/><transition event="x" target="b"/></state>',
  '  <state id="c"><transition event="z" target="done"/></state>',
  '  <final id="done"/>',
  '</scxml>', '',
])


@pytest.mark.engines("lua")
def test_lxsc_parses_and_steps_a_machine_in_the_lua_guest(amk, tmp_path):
  r = run(amk, tmp_path, [
    "define chain", CHAIN_SCXML, "endef",
    "@lua.target", "define probe",
    '  local LXSC = require "lxsc"',
    '  local m = LXSC:parse(amk.var["chain"])',
    "  m:start()",
    '  local fired = 0',
    "  m.onTransition = function(t) fired = fired + 1 end",
    '  local was = table.concat(m:activeStateIds(), ",")',
    '  for _, e in ipairs({"x", "y", "z"}) do m:fireEvent(e); m:step() end',
    '  print(was, table.concat(m:activeStateIds(), ","), fired)',
    "endef",
    "show: probe", "\t@true",
  ], "show")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "a\tdone\t3" in r.stdout, r.stdout


@pytest.mark.engines("lua", "jq")
def test_a_machine_loads_from_scxml_by_its_extension(amk, tmp_path):
  (tmp_path / "chain.scxml").write_text(CHAIN_SCXML)
  r = run(amk, tmp_path, [
    f"load {tmp_path}/chain.scxml",
    "$(amk.pool.produce chain.ev.x)", "$(amk.pool.produce chain.ev.y)", "$(amk.pool.produce chain.ev.z)",
    "show: chain.__main__", "\t@echo '[$(chain.trace)] $(chain.definition )'",
  ], "show")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[a.x b.y c.z] " in r.stdout, r.stdout
  definition = json.loads(r.stdout.split("] ", 1)[1])
  assert definition["id"] == "chain" and definition["states"]["done"]["type"] == "final", definition


DROPPY_SCXML = "\n".join([
  '<scxml xmlns="http://www.w3.org/2005/07/scxml" version="1.0" initial="s0 s1" name="m" datamodel="lua">',
  '  <datamodel><data id="v" expr="0"/></datamodel>',
  '  <state id="s0">',
  '    <onentry><raise event="go"/><assign location="v" expr="1"/></onentry>',
  '    <transition event="go" cond="In(\'s1\')" target="pass"/>',
  '    <transition event="go" target="fail"><log expr="\'x\'"/></transition>',
  '  </state>',
  '  <state id="s1"><onexit><if cond="true"><raise event="e"/></if></onexit></state>',
  '  <final id="pass"/>', '  <final id="fail"/>',
  '</scxml>', '',
])


@pytest.mark.engines("lua", "jq")
def test_the_scxml_converter_writes_the_config_and_names_what_it_leaves_out(amk, tmp_path):
  r = run(amk, tmp_path, ["define doc", DROPPY_SCXML, "endef", "$(info $(fsm.scxml doc))"])
  assert r.returncode == 0, r.stdout + r.stderr
  config = json.loads(r.stdout.strip().splitlines()[0])
  assert config["initial"] == ["#m.s0", "#m.s1"], config
  assert config["states"]["s0"]["on"]["go"] == [{"guard": "@s1", "target": "#m.pass"}, {"target": "#m.fail"}], config
  assert config["states"]["s0"]["on"]["go.*"] == config["states"]["s0"]["on"]["go"], config
  assert r.stderr.strip() == ("doc: scxml leaves out datamodel, onentry of s0 (raise assign),"
                              " content of a transition in s0 (log), onexit of s1 (if)"), r.stderr


def test_fsm_registers_as_a_stacked_engine_over_jq(amk, tmp_path):
  r = run(amk, tmp_path, [
    "$(info [$(filter fsm,$(amk.engines))] [$(filter fsm,$(amk.data.engines))] ext=$(amk.engine.ext.fsm))",
  ])
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[fsm] [fsm] ext=fsm" in r.stdout, r.stdout
  r = run(amk, tmp_path, ["$(info ext=$(amk.engine.ext.scxml))"])
  assert "ext=fsm" in r.stdout, r.stdout

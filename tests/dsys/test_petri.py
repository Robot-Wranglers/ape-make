"""Pins nets: `lib/dsys/petri.amk`, places as pools and firings as consume, step, produce.

A net under @petri runs its first enabled transition until none is, checks its invariants
after each firing and its final marking at the end, and refuses a malformed net at parse.
Pinned with the two traffic lights of Murata's survey, whose trace has one possible order.
"""

import re

import pytest

from conftest import sh

pytestmark = pytest.mark.engines("jq")


def run(amk, tmp_path, body, goal="all"):
  mk = tmp_path / "net.mk"
  mk.write_text("load dsys/petri\n" + body + "\nall:\n\t@true\n")
  return sh(amk, ["-s", "-f", str(mk), goal], cwd=tmp_path, timeout=120)


def net(places, transitions, arcs, amk_keys=""):
  extra = f', "amk": {{ {amk_keys} }}' if amk_keys else ""
  return "\n".join([
    "@petri", "define n",
    f'{{ "places": {{ {places} }}, "transitions": [{transitions}], "arcs": [{arcs}]{extra} }}',
    "endef",
  ])


LIGHTS = net(
  '"a_red": 1, "a_green": 0, "b_red": 1, "b_green": 0, "a_turn": 1, "b_turn": 0, "cycles": 2',
  '"a_go", "a_stop", "b_go", "b_stop"',
  ", ".join([
    '["a_red", "a_go"]', '["a_turn", "a_go"]', '["cycles", "a_go"]', '["a_go", "a_green"]',
    '["a_green", "a_stop"]', '["a_stop", "a_red"]', '["a_stop", "b_turn"]',
    '["b_red", "b_go"]', '["b_turn", "b_go"]', '["b_go", "b_green"]',
    '["b_green", "b_stop"]', '["b_stop", "b_red"]', '["b_stop", "a_turn"]',
  ]),
  ", ".join([
    '"invariants": [{ "a_turn": 1, "a_green": 1, "b_turn": 1, "b_green": 1, "=": 1 }]',
    '"final": { "a_red": 1, "b_red": 1, "a_turn": 1 }',
  ]),
)


def test_the_lights_fire_in_their_one_order(amk, tmp_path):
  r = run(amk, tmp_path, LIGHTS + "\nshow: n.__main__\n\t@echo '[$(n.trace)] [$(n.marking )]'", "show")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[a_go a_stop b_go b_stop a_go a_stop b_go b_stop]" in r.stdout, r.stdout
  assert "a_red=1" in r.stdout and "cycles=0" in r.stdout, r.stdout


def test_each_firing_runs_its_step_with_the_label_it_took(amk, tmp_path):
  body = "\n".join([
    net('"queue": ["c1", "c2"], "crossed": []', '"cross"',
        '["queue", "cross"], ["cross", "crossed"]', '"steps": { "cross": { "run": "drive" } }'),
    "drive:", "\t@echo 'drove $(n.cross.token) on $(n.firing)'",
    "show: n.__main__", "\t@echo '[$(n.marking crossed)]'",
  ])
  r = run(amk, tmp_path, body, "show")
  assert r.returncode == 0, r.stdout + r.stderr
  assert re.search(r"drove c1 on cross\s+drove c2 on cross\s+\[2\]", r.stdout), r.stdout


def test_a_goal_maybe_step_keeps_its_outcome_and_the_run_goes_on(amk, tmp_path):
  body = "\n".join([
    net('"a": 1, "b": 0, "c": 0', '"t", "u"', '["a", "t"], ["t", "b"], ["b", "u"], ["u", "c"]',
        '"steps": { "t": { "run": "bad", "kind": "goal.maybe" }, "u": { "run": "good" } }'),
    "bad:", "\t@exit 3", "good:", "\t@echo ran good",
    "show: n.__main__", "\t@echo '[$(n.t.outcome)] [$(n.trace)]'",
  ])
  r = run(amk, tmp_path, body, "show")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "ran good" in r.stdout and "[failed] [t u]" in r.stdout, r.stdout


def test_a_failed_goal_step_stops_the_run(amk, tmp_path):
  body = "\n".join([
    net('"a": 1, "b": 0', '"t"', '["a", "t"], ["t", "b"]', '"steps": { "t": { "run": "bad" } }'),
    "bad:", "\t@exit 3",
    "show: n.__main__", "\t@echo unreached",
  ])
  r = run(amk, tmp_path, body, "show")
  assert r.returncode != 0 and "the goal failed" in r.stderr and "unreached" not in r.stdout, r.stderr


def test_an_arc_may_take_from_an_existing_pool_and_give_back(amk, tmp_path):
  body = "\n".join([
    "$(amk.pool runners, 1)",
    net('"a": 2, "b": 0', '"t"', '["a", "t"], ["runners", "t"], ["t", "b"], ["t", "runners"]',
        '"pools": { "runners": "runners" }, "steps": { "t": { "run": "work" } }'),
    "work:", "\t@echo working",
    "show: n.__main__", "\t@echo '[$(n.marking )] [$(amk.pool.size runners)] [$(n.trace)]'",
  ])
  r = run(amk, tmp_path, body, "show")
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.count("working") == 2, r.stdout
  assert "[a=0 b=2] [1] [t t]" in r.stdout, r.stdout


@pytest.mark.parametrize("label,fired", [("failed", "skip"), ("success", "go")])
def test_complementary_guards_pick_one_transition_on_the_label(amk, tmp_path, label, fired):
  body = "\n".join([
    net(f'"q": ["{label}"], "ran": [], "skipped": []', '"go", "skip"',
        '["q", "go"], ["go", "ran"], ["q", "skip"], ["skip", "skipped"]',
        '"guard": { "go": "all success", "skip": "not all success" }'),
    "show: n.__main__", "\t@echo '[$(n.trace)] [$(n.marking )]'",
  ])
  r = run(amk, tmp_path, body, "show")
  assert r.returncode == 0, r.stdout + r.stderr
  want = "q=0 ran=1 skipped=0" if fired == "go" else "q=0 ran=0 skipped=1"
  assert f"[{fired}] [{want}]" in r.stdout, r.stdout


@pytest.mark.parametrize("step,want", [("good", "success"), ("bad", "failed")])
def test_the_outcome_rule_labels_the_token_by_the_steps_exit(amk, tmp_path, step, want):
  body = "\n".join([
    net('"go": ["x"], "done": []', '"t"', '["go", "t"], ["t", "done"]',
        f'"steps": {{ "t": {{ "run": "{step}", "kind": "goal.maybe" }} }}, "label": {{ "t": "outcome" }}'),
    "good:", "\t@true", "bad:", "\t@exit 3",
    "show: n.__main__", "\t@echo '[$(amk.pool.acquire n.done)]'",
  ])
  r = run(amk, tmp_path, body, "show")
  assert r.returncode == 0, r.stdout + r.stderr
  assert f"[{want}]" in r.stdout, r.stdout


def test_items_split_and_merge_join_a_task_run_over_a_list(amk, tmp_path):
  body = "\n".join([
    net('"go": ["success"], "items": [], "results": [], "done": []', '"split", "work", "join"',
        ", ".join(['["go", "split"]', '["split", "items", 3]', '["items", "work"]',
                   '["work", "results"]', '["results", "join", 3]', '["join", "done"]']),
        ", ".join(['"steps": { "work": { "run": "work", "kind": "goal.maybe" } }',
                   '"label": { "split": { "items": ["a", "b", "c"] }, "work": "outcome", "join": "merge" }'])),
    "work:", "\t@echo 'work on $(n.work.token)'; test '$(n.work.token)' != b",
    "show: n.__main__", "\t@echo '[$(n.trace)] [$(amk.pool.acquire n.done)]'",
  ])
  r = run(amk, tmp_path, body, "show")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "work on a" in r.stdout and "work on c" in r.stdout, r.stdout
  assert "[split work work work join] [failed]" in r.stdout, r.stdout


def test_the_states_read_off_each_transitions_last_firing(amk, tmp_path):
  body = "\n".join([
    net('"go": ["success"], "q": [], "done": [], "never": []', '"run", "check", "idle"',
        '["go", "run"], ["run", "q"], ["q", "check"], ["check", "done"], ["never", "idle"], ["idle", "done"]',
        ", ".join(['"steps": { "run": { "run": "bad", "kind": "goal.maybe" } }',
                   '"label": { "run": "outcome", "check": "merge", "idle": "skipped" }'])),
    "bad:", "\t@exit 3",
    "show: n.__main__", "\t@echo '[$(n.states )] [$(n.state run)]'",
  ])
  r = run(amk, tmp_path, body, "show")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[run=failed check=failed idle=pending] [failed]" in r.stdout, r.stdout


def test_a_transition_without_a_rule_reads_as_fired(amk, tmp_path):
  r = run(amk, tmp_path, LIGHTS + "\nshow: n.__main__\n\t@echo '[$(n.state a_go)]'", "show")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[fired]" in r.stdout, r.stdout


def test_the_skipped_rule_labels_without_a_step(amk, tmp_path):
  body = "\n".join([
    net('"go": ["success"], "done": []', '"t"', '["go", "t"], ["t", "done"]', '"label": { "t": "skipped" }'),
    "show: n.__main__", "\t@echo '[$(amk.pool.acquire n.done)]'",
  ])
  r = run(amk, tmp_path, body, "show")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[skipped]" in r.stdout, r.stdout


@pytest.mark.parametrize("event,fired", [("pull", "on_pull"), ("push", "on_push")])
def test_a_label_guard_fires_the_transition_whose_label_the_token_carries(amk, tmp_path, event, fired):
  body = "\n".join([
    net(f'"q": ["{event}"], "a": 0, "b": 0', '"on_pull", "on_push"',
        '["q", "on_pull"], ["on_pull", "a"], ["q", "on_push"], ["on_push", "b"]',
        '"guard": { "on_pull": { "label": "pull" }, "on_push": { "label": "push" } }'),
    "show: n.__main__", "\t@echo '[$(n.trace)] [$(n.marking )]'",
  ])
  r = run(amk, tmp_path, body, "show")
  assert r.returncode == 0, r.stdout + r.stderr
  want = "q=0 a=1 b=0" if fired == "on_pull" else "q=0 a=0 b=1"
  assert f"[{fired}] [{want}]" in r.stdout, r.stdout


def test_a_guard_refuses_a_place_holding_more_than_one_token(amk, tmp_path):
  body = net('"q": ["a", "b"], "r": []', '"t"', '["q", "t"], ["t", "r"]',
             '"guard": { "t": "any failed" }')
  r = run(amk, tmp_path, body + "\nshow: n.__main__\n\t@true", "show")
  assert r.returncode != 0, r.stdout
  assert "n: the guard of t reads q, which holds 2 tokens, not 1" in re.sub(r"\s+", " ", r.stderr), r.stderr


@pytest.mark.engines("lua")
def test_an_open_net_lets_a_step_produce_into_its_places(amk, tmp_path):
  body = "\n".join([
    net('"in": ["x"], "out": []', '"t"', '["in", "t"]',
        '"strategy": "open", "steps": { "t": { "run": "step" } }, "final": { "out": 2 }'),
    "@lua.target", "define step",
    '  amk.pool.produce("n.out", amk.var["n.t.token"] .. "1")',
    '  amk.pool.produce("n.out", amk.var["n.t.token"] .. "2")',
    "endef",
    "show: n.__main__", "\t@echo '[$(n.marking )] [$(amk.pool.acquire n.out) $(amk.pool.acquire n.out)]'",
  ])
  r = run(amk, tmp_path, body, "show")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[in=0 out=2] [x1 x2]" in r.stdout, r.stdout


WAITS_FOR = "@touch {me}.on; for i in $$(seq 50); do [ -f {other}.on ] && exit 0; sleep 0.1; done; exit 1"


def test_agoal_steps_are_in_flight_at_once(amk, tmp_path):
  """Each step waits for the other's file, so a serial run would fail on its timeout."""
  body = "\n".join([
    "show: n.__main__", "\t@echo '[$(n.marking )] [$(n.states )] [$(n.inflight)]'",
    net('"a": ["x"], "b": ["y"], "done": []', '"ta", "tb"',
        '["a", "ta"], ["ta", "done"], ["b", "tb"], ["tb", "done"]',
        '"steps": { "ta": { "run": "wa", "kind": "agoal" }, "tb": { "run": "wb", "kind": "agoal" } }'),
    "wa:", "\t" + WAITS_FOR.format(me="a", other="b"),
    "wb:", "\t" + WAITS_FOR.format(me="b", other="a"),
  ])
  r = run(amk, tmp_path, body, "show")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[a=0 b=0 done=2 ta.busy=0 tb.busy=0] [ta=fired tb=fired] []" in r.stdout, r.stdout


def test_a_run_lands_only_its_own_jobs_and_leaves_an_outside_job_its_record(amk, tmp_path):
  """An outside job that finishes first while the net's step runs is never the net's to reap."""
  body = "\n".join([
    "show: n.__main__", "\t@echo '[$(n.state t)] [$(findstring \"success\",$(amk.wait $(outside)))]'",
    net('"go": ["x"], "done": []', '"t"', '["go", "t"], ["t", "done"]',
        '"steps": { "t": { "run": "slow", "kind": "agoal" } }'),
    "fast:", "\t@true",
    "slow:", "\t@sleep 1",
    "outside := $(amk.spawn fast)",
  ])
  r = run(amk, tmp_path, body, "show")
  assert r.returncode == 0, r.stdout + r.stderr
  assert '[fired] ["success"]' in r.stdout, r.stdout


def test_agoal_maybe_lands_a_failure_as_its_outcome(amk, tmp_path):
  body = "\n".join([
    "show: n.__main__", "\t@echo '[$(n.state t)] [$(amk.pool.acquire n.done)]'",
    net('"go": ["x"], "done": []', '"t"', '["go", "t"], ["t", "done"]',
        '"steps": { "t": { "run": "bad", "kind": "agoal.maybe" } }, "label": { "t": "outcome" }'),
    "bad:", "\t@exit 3",
  ])
  r = run(amk, tmp_path, body, "show")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[failed] [failed]" in r.stdout, r.stdout


def test_a_failed_agoal_step_stops_the_run(amk, tmp_path):
  body = "\n".join([
    "show: n.__main__", "\t@echo unreached",
    net('"go": 1, "done": 0', '"t"', '["go", "t"], ["t", "done"]',
        '"steps": { "t": { "run": "bad", "kind": "agoal" } }'),
    "bad:", "\t@exit 3",
  ])
  r = run(amk, tmp_path, body, "show")
  assert r.returncode != 0 and "n: step t failed as job" in r.stderr, r.stderr
  assert "unreached" not in r.stdout, r.stdout


def test_a_pool_arc_bounds_the_firings_in_flight(amk, tmp_path):
  """Each run takes a lock directory, so two at once would fail; one runner keeps them apart."""
  body = "\n".join([
    "$(amk.pool runners, 1)",
    "show: n.__main__", "\t@echo '[$(n.marking )] [$(amk.pool.size runners)]'",
    net('"q": 3, "done": 0', '"t"', '["q", "t"], ["runners", "t"], ["t", "done"], ["t", "runners"]',
        '"pools": { "runners": "runners" }, "steps": { "t": { "run": "work", "kind": "agoal" } }'),
    "work:", "\t@mkdir lock && sleep 0.2 && rmdir lock",
  ])
  r = run(amk, tmp_path, body, "show")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[q=0 done=3 t.busy=0] [1]" in r.stdout, r.stdout


def test_invariants_wait_until_no_firing_is_in_flight(amk, tmp_path):
  """Between the two landings a=0 b=1, which breaks a+b=2; only the idle marking is checked."""
  body = "\n".join([
    "show: n.__main__", "\t@echo '[$(n.marking )]'",
    net('"a": 2, "b": 0', '"t"', '["a", "t"], ["t", "b"]',
        ", ".join(['"steps": { "t": { "run": "work", "kind": "agoal" } }',
                   '"invariants": [{ "a": 1, "b": 1, "=": 2 }]'])),
    "work:", "\t@sleep 0.2",
  ])
  r = run(amk, tmp_path, body, "show")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[a=0 b=2 t.busy=0]" in r.stdout, r.stdout


def test_a_broken_invariant_stops_the_run(amk, tmp_path):
  body = net('"a": 1, "b": 0', '"t"', '["a", "t"], ["t", "b"], ["t", "b"]',
             '"invariants": [{ "a": 1, "b": 1, "=": 1 }]')
  r = run(amk, tmp_path, body + "\nshow: n.__main__\n\t@true", "show")
  assert r.returncode != 0 and "n: invariant 1 broken after t: 2, not 1" in r.stderr, r.stderr


def test_a_stuck_net_misses_its_final_marking(amk, tmp_path):
  body = net('"a": 1, "b": 0, "c": 0', '"t"', '["a", "t"], ["t", "b"]', '"final": { "c": 1 }')
  r = run(amk, tmp_path, body + "\nshow: n.__main__\n\t@true", "show")
  assert r.returncode != 0 and "n: stuck with b at 1, the final marking wants 0" in r.stderr, r.stderr


def test_a_net_may_end_at_any_of_several_final_markings(amk, tmp_path):
  body = net('"a": 1, "b": 0, "c": 0', '"t"', '["a", "t"], ["t", "b"]', '"final": [{ "c": 1 }, { "b": 1 }]')
  r = run(amk, tmp_path, body + "\nshow: n.__main__\n\t@echo '[$(n.marking )]'", "show")
  assert r.returncode == 0 and "[a=0 b=1 c=0]" in r.stdout, r.stdout + r.stderr
  body = net('"a": 1, "b": 0, "c": 0', '"t"', '["a", "t"], ["t", "b"]', '"final": [{ "c": 1 }, { "a": 1 }]')
  r = run(amk, tmp_path, body + "\nshow: n.__main__\n\t@true", "show")
  assert r.returncode != 0 and "n: stuck at a=0 b=1 c=0, none of 2 final markings met" in r.stderr, r.stderr


def test_a_step_runs_its_targets_in_order_with_its_bindings_and_labels_by_its_output(amk, tmp_path):
  body = net('"a": 1, "b": []', '"t"', '["a", "t"], ["t", "b"]',
             '"steps": { "t": { "run": ["one", "two"], "bind": { "who": "t" } } }, "label": { "t": "output" }')
  r = run(amk, tmp_path, "\n".join([
    body, "one:", "\t@echo first $(who)", "two:", "\t@echo second",
    "show: n.__main__", "\t@echo '[$(n.marking )] [$(n.t.output)]'"]), "show")
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout == "[a=0 b=1] [second]\n", r.stdout


def test_a_firing_in_flight_is_a_token_in_its_busy_place(amk, tmp_path):
  """While t's job sleeps, s fires in place and reads t.busy as 1; both land at 0."""
  body = "\n".join([
    "show: n.__main__", "\t@echo '[$(n.marking )]'",
    net('"go": 1, "side": 1, "done": 0, "seen": 0', '"t", "s"',
        '["go", "t"], ["t", "done"], ["side", "s"], ["s", "seen"]',
        '"steps": { "t": { "run": "slow", "kind": "agoal" }, "s": { "run": "peek" } }'),
    "slow:", "\t@sleep 0.3",
    "peek:", "\t@echo '[busy $(n.marking t.busy)]'",
  ])
  r = run(amk, tmp_path, body, "show")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[busy 1]" in r.stdout, r.stdout
  assert "[go=0 side=0 done=1 seen=1 t.busy=0]" in r.stdout, r.stdout


def test_a_firing_takes_all_its_inputs_or_gives_back_what_it_took(amk, tmp_path):
  """With b empty, a grab of t takes a's token, misses b, and puts a's token back."""
  body = "\n".join([
    net('"a": ["x"], "b": 0, "c": 0', '"t"', '["a", "t"], ["b", "t"], ["t", "c"]'),
    "$(info [grab $(call petri._grab,n,t)] [$(n.marking )])",
  ])
  r = run(amk, tmp_path, body)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[grab ] [a=1 b=0 c=0]" in r.stdout, r.stdout


OPEN_NET = net('"in": [], "out": 0', '"t"', '["in", "t"], ["t", "out"]',
               '"open": ["in"], "final": { "out": 2 }')


@pytest.mark.engines("jq", "lua")
def test_an_open_net_waits_for_the_environment_until_its_final_marking(amk, tmp_path):
  """Nothing is enabled at the start; the net waits until a job produces two tokens into in."""
  body = "\n".join([
    OPEN_NET,
    "@lua.target", "define feeder",
    '  os.execute("sleep 0.3")', '  amk.pool.produce("n.in", "a")',
    '  os.execute("sleep 0.3")', '  amk.pool.produce("n.in", "b")', "endef",
    "start:", "\t@echo '[pid $(if $(amk.spawn feeder),y)]'",
    "show: start n.__main__", "\t@echo '[$(n.marking )] [$(n.trace)]'",
  ])
  r = run(amk, tmp_path, body, "show")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[in=0 out=2] [t t]" in r.stdout, r.stdout


def test_an_open_net_with_nothing_arriving_runs_out_of_patience(amk, tmp_path):
  r = run(amk, tmp_path, "petri.patience := 1\n" + OPEN_NET + "\nshow: n.__main__\n\t@true", "show")
  assert r.returncode != 0, r.stdout
  assert "n: quiescent for 1s, nothing enabled and nothing arrived in in" in r.stderr, r.stderr


@pytest.mark.parametrize("body,want", [
  (net('"a": 1', '"t"', '["a", "b"]'), "n: arc a to b does not join a place and a transition"),
  (net('"a": 1, "b": 0', '"t"', '["t", "b"]'), "n: transition t has no input place"),
  (net('"a": 1, "q": []', '"t"', '["a", "t"], ["t", "q"]'), "n: t puts a token in labeled place q but took no label"),
  (net('"a": 1, "b": 0', '"t"', '["a", "t"], ["t", "b"]', '"backend": "s7"'),
   'n: does not meet schema/petri.json: Property amk: Property backend: Value "s7" not in enum; one of "petri"'),
  (net('"a": 1, "b": 0', '"t"', '["a", "t"], ["t", "b"]', '"steps": { "t": { "run": "x", "kind": "scoped" } }'),
   'n: does not meet schema/petri.json: Property amk: Property steps: Additional property t: Property kind: '
   'Value "scoped" not in enum; one of "goal" "goal.maybe" "agoal" "agoal.maybe"'),
  (net('"a": 1, "b": 0', '"t"', '["a", "t"], ["t", "b"]', '"steps": { "u": { "run": "x" } }'), "n: step u names no transition"),
  (net('"a": 1, "b": 0', '"b"', '["a", "b"]'), "n: b is both a place and a transition"),
  (net('"a": 1, "b": 0', '"t"', '["a", "t"], ["t", "b"]', '"open": ["c"]'), "n: open place c is not a place of the net"),
  (net('"a": 1, "t.busy": 0', '"t"', '["a", "t"], ["t", "t.busy"]', '"steps": { "t": { "run": "x", "kind": "agoal" } }'),
   "n: t.busy is both a place and the in-flight count of a transition"),
  (net('"a": 1, "b": 0', '"t"', '["a", "t"], ["t", "b"]', '"label": { "t": "loudest" }'),
   'n: does not meet schema/petri.json: Property amk: Property label: Additional property t: '
   'Value "loudest" matches no branch of oneOf; one of "outcome" "skipped" "merge" "output" an object'),
  (net('"a": 1, "q": []', '"t"', '["a", "t"], ["t", "q", 2]', '"label": { "t": { "items": ["x"] } }'),
   "n: t produces token 2 but has 1 items"),
  (net('"a": 1, "b": 0', '"t"', '["a", "t"], ["t", "b"]', '"guard": { "t": "most success" }'),
   'n: does not meet schema/petri.json: Property amk: Property guard: Additional property t: Value "most success" matches no branch of oneOf; '
   'one of "all success" "not all success" "any failed" "not any failed" "all_success" "not_all_success" "any_failed" "not_any_failed" an object'),
  (net('"a": 1, "b": 0', '"t"', '["a", "t"], ["r", "t"], ["t", "b"]', '"pools": { "r": "nowhere" }'),
   "n: place r names pool nowhere, which is not open"),
  ("$(amk.pool r, 1)\n" + net('"a": 1, "r": 0', '"t"', '["a", "t"], ["t", "r"]', '"pools": { "r": "r" }'),
   "n: r is both a place and an existing pool"),
])
def test_a_malformed_net_is_refused(amk, tmp_path, body, want):
  r = run(amk, tmp_path, body + "\nshow: n.__main__\n\t@true", "show")
  assert r.returncode != 0 and want in re.sub(r"\s+", " ", r.stderr), r.stderr


def test_exec_runs_jq_over_the_net_with_its_state_bound(amk, tmp_path):
  body = "\n".join([
    net('"a": 1, "q": ["x"], "b": 0', '"t"', '["a", "t"], ["q", "t"], ["t", "b"]'),
    "@n.exec", "define at_parse",
    '  "parse \\(.transitions | length) \\($marking.a) \\($labels.q[0])'
    ' \\($trace | length) \\($source.transitions | length)"',
    "endef",
    "fn := $(n.exec $$marking.b)",
    "show: n.__main__",
    "\t@echo 'fn=$(fn) after=$(n.exec $$marking.b) trace=$(n.exec $$trace | join(\",\"))'",
  ])
  r = run(amk, tmp_path, body, "show")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "parse 1 1 x 0 1" in r.stdout, r.stdout
  assert "fn=0 after=1 trace=t" in r.stdout, r.stdout


def test_petri_registers_as_a_stacked_engine_over_jq(amk, tmp_path):
  r = run(amk, tmp_path, "$(info [$(filter petri,$(amk.engines))] ext=$(amk.engine.ext.petri)"
          " guest=$(amk.engine.petri.guest) version=$(petri.__version__)/$(jq.__version__))")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[petri] ext=petri guest=jq version=" in r.stdout, r.stdout
  v = r.stdout.split("version=")[1].split("/")
  assert v[0].strip() == v[1].strip(), r.stdout


def test_a_net_loads_from_a_file_by_its_extension(amk, tmp_path):
  (tmp_path / "m.petri").write_text('{ "places": { "a": 1, "b": 0 }, "transitions": ["t"], "arcs": [["a", "t"], ["t", "b"]] }\n')
  r = run(amk, tmp_path, f"load {tmp_path}/m.petri\nshow: m.__main__\n\t@echo '[$(m.trace)] [$(m.marking )]'", "show")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[t] [a=0 b=1]" in r.stdout, r.stdout


def test_the_target_form_runs_the_net_as_a_target_of_its_name(amk, tmp_path):
  body = net('"a": 1, "b": 0', '"t"', '["a", "t"], ["t", "b"]').replace("@petri", "@petri.target")
  r = run(amk, tmp_path, body + "\nshow: n\n\t@echo '[$(n.trace)]'", "show")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[t]" in r.stdout, r.stdout


def test_update_grows_a_net_in_place_before_it_runs(amk, tmp_path):
  body = "\n".join([
    net('"a": 1, "b": 0', '"t"', '["a", "t"], ["t", "b"]'),
    '$(n.update .places.c = 0 | .transitions += ["u"] | .arcs += [["b", "u"], ["u", "c"]])',
    "@petri.exec (n)", "define grown", "  .transitions | join(\" \")", "endef",
    "show: n.__main__", "\t@echo '[$(n.trace)] [$(n.marking )]'",
  ])
  r = run(amk, tmp_path, body, "show")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "t u\n" in r.stdout and "[t u] [a=0 b=0 c=1]" in r.stdout, r.stdout


def test_petri_is_a_data_engine_whose_nets_are_made_grown_and_versioned(amk, tmp_path):
  body = "\n".join([
    "$(petri.create n)", "v0 := $(petri.version n)",
    '$(n.update .places = {"a": 1, "b": 0} | .transitions = ["t"] | .arcs = [["a", "t"], ["t", "b"]])',
    "v1 := $(n.version)",
    "show: n.__main__",
    "\t@echo \"[$(filter petri,$(amk.data.engines))] moved=$(if $(filter $(v0),$(v1)),no,yes)"
    " [$(n.trace)] v1=$(v1) w=$$(amk.ns wait n -- $(v0))\"",
  ])
  r = run(amk, tmp_path, body, "show")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[petri] moved=yes [t] " in r.stdout, r.stdout
  v1, w = (x.split("=")[1] for x in r.stdout.split()[-2:])
  assert v1 == w, r.stdout


def test_the_net_reads_out_as_pnml(amk, tmp_path):
  r = run(amk, tmp_path, net('"a": 2, "b": 0', '"t"', '["a", "t", 2], ["t", "b"]') + "\n$(info $(n.pnml))")
  assert r.returncode == 0, r.stdout + r.stderr
  for want in ['<place id="a"><initialMarking><text>2</text>', '<transition id="t"/>',
               'source="a" target="t"><inscription><text>2</text>']:
    assert want in r.stdout, r.stdout

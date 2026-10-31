"""Pins a group: a charter declared as JSON under `@actor.group`, members of every kind, the handle
a bound member reads its group through, the restart policy, and a nested group's giving up
as one member's exit.

Each test writes its own makefile. Members run concurrently under the Effection backend, so
the pins hold per event line, never by line order. A member that answers a call prints to
stderr, since its stdout is its answer.
"""

import pytest

from conftest import sh

ENGINES = pytest.mark.engines("jq", "lua", "micropy", "js")

PRELUDE = [
  "$(amk.require lua, micropy, js, jq)",
  "$(amk.include actor)",
  "__main__: ops.__main__",
]


def _group(name, body):
  return ["@actor.group", f"define {name}", body, "endef"]


def _member(at, name, *body):
  return [at, f"define {name}", *body, "endef"]


def _crasher(name, crashes, words):
  return _member(f"@ops.actor (micropy) {{{words}}}", name,
                 f"  if ops.{name}.start_count <= {crashes}:",
                 f"      raise ValueError('crash %s' % ops.{name}.start_count)",
                 f"  return 'up on start %s' % ops.{name}.start_count")


def _run(amk, tmp_path, lines, *goals):
  mk = tmp_path / "group.mk"
  mk.write_text("\n".join(lines) + "\n")
  return sh(amk, ["-f", str(mk), *goals], cwd=tmp_path, timeout=120)


EVERY_KIND = PRELUDE + _group("ops", '{ "intensity": 3, "children": { "echo": { "kind": "block", "engine": "micropy", "restart": "on-failure" } } }') + [
  *_member("@ops.actor (lua) {kind=goal restart=on-failure}", "alpha",
           '  for n = 1, 3 do print("alpha: step " .. n) end'),
  *_member("@ops.actor (js) {kind=goal restart=never}", "charlie",
           '  print("charlie: up");', "  std.exit(1);"),
  *_crasher("delta", 2, "restart=on-failure"),
  "define echo", '  print("ran as a block")', "endef",
  *_member("@ops.actor (js) {kind=scoped restart=on-failure}", "foxtrot",
           "  const start = ops.foxtrot.start_count;",
           "  for (let n = 1; n <= 3; ++n) {",
           "    yield* amk.plex.sleep(20);",
           "    if (start === 1 && n === 2) throw new Error(`crashed on step ${n}`);",
           "    print(`foxtrot: step ${n} of start ${start}`);",
           "  }"),
  *_member("@ops.actor (lua) {restart=on-failure}", "clerk",
           '  print("clerk: start " .. ops.clerk.start_count .. " under " .. ops.config.strategy)',
           "  local ids = {}",
           "  for id in pairs(ops.siblings()) do ids[#ids + 1] = id end",
           "  table.sort(ids)",
           '  print("clerk: siblings " .. table.concat(ids, " "))'),
]


@ENGINES
def test_every_kind_runs_under_one_charter(amk, tmp_path):
  r = _run(amk, tmp_path, EVERY_KIND)
  assert r.returncode == 0, r.stdout + r.stderr
  out = r.stdout
  for m in ("alpha", "charlie", "delta", "echo", "foxtrot", "clerk"):
    assert out.count(f"ops: started {m}\n") >= 1, out
  assert out.count("ops: exited alpha 0") == 1, out
  assert out.count("ops: exited echo 0") == 1, out
  assert out.count("ops: exited charlie 2") == 1 and "restarting charlie" not in out, out
  assert out.count("ops: restarting delta") == 2 and "delta: up on start 3" in out, out
  assert out.count("ops: restarting foxtrot") == 1 and "foxtrot: step 3 of start 2" in out, out
  assert out.count("ops: exited clerk 0") == 1, out
  assert "gave_up" not in out, out


@ENGINES
def test_the_handle_reads_the_group_live(amk, tmp_path):
  r = _run(amk, tmp_path, EVERY_KIND)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "clerk: start 1 under one_for_one" in r.stderr, r.stderr
  assert "clerk: siblings alpha charlie delta echo foxtrot" in r.stderr, r.stderr


@ENGINES
def test_a_goal_by_at_line_is_a_target_and_a_call_is_not(amk, tmp_path):
  r = _run(amk, tmp_path, EVERY_KIND, "alpha")
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.splitlines() == ["alpha: step 1", "alpha: step 2", "alpha: step 3"], r.stdout
  r = _run(amk, tmp_path, EVERY_KIND, "delta")
  assert r.returncode != 0 and "No rule to make target 'delta'" in r.stderr, r.stdout + r.stderr


@ENGINES
def test_a_nested_group_gives_up_as_one_exit_of_its_parent(amk, tmp_path):
  lines = PRELUDE + _group("ops", '{ "children": { "noisy": { "kind": "group", "restart": "never" } } }') \
    + _group("noisy", '{ "intensity": 1 }') \
    + _member("@noisy.actor (micropy) {kind=goal}", "bravo", '  print("bravo: up")', "  raise SystemExit(1)")
  r = _run(amk, tmp_path, lines)
  assert r.returncode == 0, r.stdout + r.stderr
  out = r.stdout
  assert out.count("noisy: restarting bravo") == 1, out
  assert out.count("noisy: gave_up noisy, bravo: too many restarts") == 1, out
  assert out.count("ops: exited noisy 1") == 1, out
  assert "ops: gave_up" not in out, out


@ENGINES
def test_the_window_counts_per_member(amk, tmp_path):
  lines = PRELUDE + _group("ops", '{ "intensity": 3 }') \
    + _crasher("one", 2, "restart=on-failure") + _crasher("two", 2, "restart=on-failure")
  r = _run(amk, tmp_path, lines)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "gave_up" not in r.stdout, r.stdout
  assert "one: up on start 3" in r.stdout and "two: up on start 3" in r.stdout, r.stdout
  assert r.stdout.count("ops: restarting one") == 2, r.stdout
  assert r.stdout.count("ops: restarting two") == 2, r.stdout


@ENGINES
def test_a_member_may_narrow_its_own_window(amk, tmp_path):
  lines = PRELUDE + _group("ops", '{ "intensity": 3 }') + _crasher("one", 2, "restart=on-failure intensity=1")
  r = _run(amk, tmp_path, lines)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.count("ops: restarting one") == 1, r.stdout
  assert "ops: gave_up ops, one: too many restarts" in r.stdout, r.stdout


@ENGINES
def test_an_at_line_word_that_parses_as_a_number_is_stored_as_one(amk, tmp_path):
  lines = PRELUDE[:2] + _group("ops", "{}") + _crasher("one", 0, "restart=on-failure intensity=1") \
    + ["$(info entry: $(ops.get -c .children.one))", "__main__:", "\ttrue"]
  r = _run(amk, tmp_path, lines)
  assert r.returncode == 0, r.stdout + r.stderr
  assert '"intensity":1' in r.stdout and '"restart":"on-failure"' in r.stdout, r.stdout


# The s7 backend: one cooperative plex per group, so its pins hold by exact line order.
S7 = pytest.mark.engines("jq", "s7", "micropy")

S7_PRELUDE = [
  "$(amk.require s7, micropy, jq)",
  "$(amk.include actor)",
  "__main__: ops.__main__",
]


def _s7_group(name, charter):
  return _group(name, '{ "backend": "s7"' + (", " + charter if charter else "") + " }")


def _events(out, group="ops"):
  return [l for l in out.splitlines() if l.startswith(f"{group}: ")]


@S7
def test_s7_scoped_bodies_interleave_at_their_yields(amk, tmp_path):
  step = "  (do ((n 1 (+ n 1))) ((> n {1})) (format #t \"{0}: step ~A~%\" n) (ops 'yield))"
  lines = S7_PRELUDE + _s7_group("ops", "") \
    + _member("@ops.actor (s7) {kind=scoped restart=never}", "a", step.format("a", 3)) \
    + _member("@ops.actor (s7) {kind=scoped restart=never}", "b", step.format("b", 2))
  r = _run(amk, tmp_path, lines)
  assert r.returncode == 0, r.stdout + r.stderr
  steps = [l for l in r.stdout.splitlines() if ": step " in l]
  assert steps == ["a: step 1", "b: step 1", "a: step 2", "b: step 2", "a: step 3"], r.stdout


@S7
def test_s7_restart_always_spends_the_budget_and_gives_up(amk, tmp_path):
  lines = S7_PRELUDE + _s7_group("ops", '"intensity": 1') \
    + _member("@ops.actor (micropy)", "one", "  raise ValueError('down')")
  r = _run(amk, tmp_path, lines)
  assert _events(r.stdout) == [
    "ops: started one", "ops: exited one 1", "ops: restarting one",
    "ops: started one", "ops: exited one 1", "ops: gave_up ops, one: too many restarts"], r.stdout


@S7
def test_s7_on_failure_restarts_a_crash_and_never_does_not(amk, tmp_path):
  lines = S7_PRELUDE + _s7_group("ops", "") + _crasher("one", 1, "restart=on-failure") \
    + _member("@ops.actor (micropy) {restart=never}", "two", "  raise ValueError('down')")
  r = _run(amk, tmp_path, lines)
  assert r.returncode == 0, r.stdout + r.stderr
  assert _events(r.stdout) == [
    "ops: started one", "ops: exited one 1", "ops: restarting one",
    "ops: started one", "ops: exited one 0", "ops: started two", "ops: exited two 1"], r.stdout


@S7
def test_s7_a_scoped_error_is_a_crash(amk, tmp_path):
  lines = S7_PRELUDE + _s7_group("ops", "") + _member(
    "@ops.actor (s7) {kind=scoped restart=on-failure}", "one",
    "  (if (< (string->number (ops 'field \".children.one.start_count\")) 2) (error 'boom \"down\"))",
    "  (display \"one: up\") (newline)")
  r = _run(amk, tmp_path, lines)
  assert r.returncode == 0, r.stdout + r.stderr
  assert _events(r.stdout) == [
    "ops: started one", "ops: exited one 1", "ops: restarting one",
    "ops: started one", "ops: exited one 0"], r.stdout
  assert "one: up" in r.stdout, r.stdout


@S7
def test_s7_the_handle_answers_its_verbs(amk, tmp_path):
  lines = S7_PRELUDE + _s7_group("ops", '"intensity": 2') \
    + _member("@ops.actor (s7) {kind=scoped restart=never}", "one",
              "  (format #t \"one: ~A ~A ~A ~A~%\" (ops 'id) (ops 'group) (ops 'field \".intensity\") (ops 'siblings))") \
    + _member("@ops.actor (micropy) {restart=never}", "two", "  return 'ok'")
  r = _run(amk, tmp_path, lines)
  assert r.returncode == 0, r.stdout + r.stderr
  assert 'one: one ops 2 ("two")' in r.stdout, r.stdout


# Every group runs under a pool: the charter's, else the default actor pool the topic opens.
def _sleeper(name):
  return _member(f"@ops.actor (micropy) {{restart=never}}", name, "  import time", "  time.sleep(0.3)", "  return 'ok'")


@ENGINES
def test_a_charters_pool_bounds_how_many_members_run_at_once(amk, tmp_path):
  lines = PRELUDE + ["$(amk.pool two, 2)"] + _group("ops", '{ "pool": "two", "children": {} }') \
    + _sleeper("a") + _sleeper("b") + _sleeper("c") + _sleeper("d")
  r = _run(amk, tmp_path, lines)
  assert r.returncode == 0, r.stdout + r.stderr
  events = _events(r.stdout)
  first_exit = next(i for i, e in enumerate(events) if " exited " in e)
  assert sum(" started " in e for e in events[:first_exit]) == 2, events
  assert sum(" started " in e for e in events) == 4, events


@S7
def test_s7_a_pool_of_one_runs_scoped_members_one_at_a_time(amk, tmp_path):
  step = "  (do ((n 1 (+ n 1))) ((> n {1})) (format #t \"{0}: step ~A~%\" n) (ops 'yield))"
  lines = S7_PRELUDE + ["$(amk.pool one, 1)"] + _s7_group("ops", '"pool": "one"') \
    + _member("@ops.actor (s7) {kind=scoped restart=never}", "a", step.format("a", 3)) \
    + _member("@ops.actor (s7) {kind=scoped restart=never}", "b", step.format("b", 2))
  r = _run(amk, tmp_path, lines)
  assert r.returncode == 0, r.stdout + r.stderr
  steps = [l for l in r.stdout.splitlines() if ": step " in l]
  assert steps == ["a: step 1", "a: step 2", "a: step 3", "b: step 1", "b: step 2"], r.stdout


@pytest.mark.engines("jq")
def test_loading_the_topic_opens_the_default_actor_pool(amk, tmp_path):
  mk = tmp_path / "group.mk"
  mk.write_text("$(amk.include actor)\n$(info [$(amk.pool actors)])\nall:\n\t@true\n")
  r = sh(amk, ["-s", "-f", str(mk)], cwd=tmp_path, timeout=120)
  assert "[64]" in r.stdout + r.stderr, r.stdout + r.stderr
  r = sh(amk, ["-s", "-f", str(mk)], cwd=tmp_path, env={"AMK_MAX_ACTORS": "5"}, timeout=120)
  assert "[5]" in r.stdout + r.stderr, r.stdout + r.stderr


@pytest.mark.engines("jq")
def test_a_charter_naming_an_unopened_pool_is_refused(amk, tmp_path):
  r = _run(amk, tmp_path, PRELUDE + _group("ops", '{ "pool": "nope", "children": {} }'))
  assert r.returncode != 0 and "no pool named nope" in r.stderr, r.stdout + r.stderr


JSON5_CHARTER = """{
  // members run under the default pool
  intensity: 3,
  children: { echo: { kind: 'block', engine: "micropy", restart: "on-failure", }, },
}"""


@pytest.mark.engines("jq", "lua", "micropy", "js", "sqlite")
def test_a_charter_may_be_json5(amk, tmp_path):
  lines = PRELUDE + _group("ops", JSON5_CHARTER) \
    + ["define echo", '  print("ran as a block")', "endef"]
  r = _run(amk, tmp_path, lines)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.count("ops: exited echo 0") == 1, r.stdout


@pytest.mark.engines("jq", "sqlite")
def test_a_json5_charters_fields_reach_the_group(amk, tmp_path):
  r = _run(amk, tmp_path, PRELUDE + _group("ops", "{ pool: 'nope', /* unopened */ children: {}, }"))
  assert r.returncode != 0 and "no pool named nope" in r.stderr, r.stdout + r.stderr


@pytest.mark.engines("jq", "sqlite")
def test_a_charter_that_does_not_parse_is_refused_by_json5(amk, tmp_path):
  r = _run(amk, tmp_path, PRELUDE + _group("ops", "{ children: {"))
  assert r.returncode != 0 and "amk.json5: malformed JSON" in r.stderr, r.stdout + r.stderr


@pytest.mark.engines("sqlite")
@pytest.mark.parametrize("text,want", [
  ("{a: 1, // note\n b: [0x10, 'x',],}", '{"a":1,"b":[16,"x"]}'),
  ('/* lead */ [1, 2,]', "[1,2]"),
  ('{"plain": true}', '{"plain":true}'),
])
def test_json5_answers_plain_json(amk, tmp_path, text, want):
  mk = tmp_path / "json5.mk"
  mk.write_text(f"define t\n{text}\nendef\n$(info [$(amk.json5 $(value t))])\nall:\n\t@true\n")
  r = sh(amk, ["-s", "-f", str(mk)], cwd=tmp_path, timeout=120)
  assert r.returncode == 0 and f"[{want}]" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("sqlite")
@pytest.mark.parametrize("text", ["{a:", "[1,,2]", "{a: 1} trailing", "'unterminated"])
def test_json5_refuses_what_does_not_parse(amk, tmp_path, text):
  mk = tmp_path / "json5.mk"
  mk.write_text(f"define t\n{text}\nendef\nx := $(amk.json5 $(value t))\nall:\n\t@true\n")
  r = sh(amk, ["-s", "-f", str(mk)], cwd=tmp_path, timeout=120)
  assert r.returncode != 0 and "amk.json5: malformed JSON" in r.stderr, r.stdout + r.stderr


@S7
def test_s7_a_blocking_goal_leaves_the_plex_running(amk, tmp_path):
  step = "  (do ((n 1 (+ n 1))) ((> n 2)) (format #t \"tick: ~A~%\" n) (ops 'yield))"
  lines = S7_PRELUDE + _s7_group("ops", "") \
    + _member("@ops.actor (micropy) {kind=goal restart=never}", "nap",
              "  import time", "  time.sleep(0.5)", "  print('nap: awake')") \
    + _member("@ops.actor (s7) {kind=scoped restart=never}", "tick", step)
  r = _run(amk, tmp_path, lines)
  assert r.returncode == 0, r.stdout + r.stderr
  out = r.stdout.splitlines()
  assert out.index("ops: exited tick 0") < out.index("nap: awake"), r.stdout
  assert "ops: exited nap 0" in out, r.stdout


@S7
def test_s7_a_nested_group_that_gives_up_kills_its_running_goals(amk, tmp_path):
  """The parent runs on after the inner group gives up, so a goal the inner group left would still be alive."""
  lines = ["$(amk.require s7, lua, micropy, jq)", "$(amk.include actor)", "__main__: ops.__main__"] \
    + _s7_group("ops", '"children": { "inner": { "kind": "group", "restart": "never" } }') \
    + _s7_group("inner", '"intensity": 0') \
    + _member("@inner.actor (lua) {kind=goal restart=never}", "asleep",
              "  local f = io.open('nap.pid', 'w') f:write(amk.sys('pid')) f:close()", "  os.execute('sleep 30')") \
    + _member("@inner.actor (micropy) {restart=always}", "boom", "  import time", "  time.sleep(0.3)", "  raise ValueError('down')") \
    + _member("@ops.actor (lua) {kind=goal restart=never}", "linger",
              "  os.execute('sleep 1.5')",
              "  local pid = io.open('nap.pid'):read('a')",
              "  local f = io.open('verdict', 'w') f:write(os.execute('kill -0 ' .. pid .. ' 2>/dev/null') and 'alive' or 'dead') f:close()")
  r = _run(amk, tmp_path, lines)
  assert "inner: gave_up inner, boom: too many restarts" in r.stdout, r.stdout + r.stderr
  assert (tmp_path / "verdict").read_text().strip() == "dead", r.stdout + r.stderr


@S7
def test_s7_a_parent_goal_reaped_inside_a_nested_group_still_reaches_the_parent(amk, tmp_path):
  """The inner group blocks for any job while the parent's faster goal is out, so it collects the parent's exit first."""
  lines = ["$(amk.require s7, lua, jq)", "$(amk.include actor)", "__main__: ops.__main__"] \
    + _s7_group("ops", '"children": { "inner": { "kind": "group", "restart": "never" } }') \
    + _s7_group("inner", "") \
    + _member("@ops.actor (lua) {kind=goal restart=never}", "afast", "  os.execute('sleep 0.1')") \
    + _member("@inner.actor (lua) {kind=goal restart=never}", "slow", "  os.execute('sleep 0.6')")
  mk = tmp_path / "group.mk"
  mk.write_text("\n".join(lines) + "\n")
  r = sh(amk, ["-f", str(mk)], cwd=tmp_path, timeout=20)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "ops: exited afast 0" in r.stdout and "ops: exited inner 0" in r.stdout, r.stdout + r.stderr


@S7
def test_s7_a_failing_goal_is_restarted_on_failure(amk, tmp_path):
  lines = S7_PRELUDE + _s7_group("ops", '"intensity": 1') \
    + _member("@ops.actor (micropy) {kind=goal restart=on-failure}", "one", "  raise SystemExit(1)")
  r = _run(amk, tmp_path, lines)
  assert "ops: restarting one" in r.stdout, r.stdout
  assert "ops: gave_up ops, one: too many restarts" in r.stdout, r.stdout


@S7
def test_s7_a_nested_group_gives_up_as_one_exit_of_its_parent(amk, tmp_path):
  lines = S7_PRELUDE + _s7_group("ops", '"children": { "inner": { "kind": "group", "restart": "never" } }') \
    + _s7_group("inner", '"intensity": 0') \
    + _member("@inner.actor (micropy)", "bravo", "  raise ValueError('down')")
  r = _run(amk, tmp_path, lines)
  assert r.returncode == 0, r.stdout + r.stderr
  assert [l for l in r.stdout.splitlines() if l.startswith(("ops: ", "inner: "))] == [
    "ops: started inner", "inner: started bravo", "inner: exited bravo 1",
    "inner: gave_up inner, bravo: too many restarts", "ops: exited inner 1"], r.stdout


@S7
def test_s7_a_raising_s7_call_member_is_a_crash(amk, tmp_path):
  lines = S7_PRELUDE + _s7_group("ops", "") + _member(
    "@ops.actor (s7) {restart=on-failure}", "one",
    "  (if (< (string->number (ops 'field \".children.one.start_count\")) 2) (error 'boom \"down\") \"up\")")
  r = _run(amk, tmp_path, lines)
  assert r.returncode == 0, r.stdout + r.stderr
  assert _events(r.stdout) == [
    "ops: started one", "ops: exited one 1", "ops: restarting one",
    "ops: started one", "ops: exited one 0"], r.stdout


@S7
def test_s7_a_call_member_cannot_yield(amk, tmp_path):
  lines = S7_PRELUDE + _s7_group("ops", "") + _member(
    "@ops.actor (s7) {restart=never}", "one", "  (ops 'yield)", '  "up"')
  r = _run(amk, tmp_path, lines)
  assert r.returncode == 0, r.stdout + r.stderr
  assert _events(r.stdout) == ["ops: started one", "ops: exited one 1"], r.stdout
  assert "one is a call member and cannot yield" in r.stdout, r.stdout


@ENGINES
def test_a_charter_kind_is_each_childs_default_and_its_own_kind_wins(amk, tmp_path):
  lines = PRELUDE + _group("ops", '{ "kind": "block", "restart": "never", "children": { "echo": {}, "solo": { "kind": "goal" } } }') + [
    "define echo", '  print("echo ran as a block")', "endef",
    "solo:", '\t@echo "solo ran as a goal"',
  ]
  r = _run(amk, tmp_path, lines)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "echo ran as a block" in r.stdout and "solo ran as a goal" in r.stdout, r.stdout
  r = _run(amk, tmp_path, PRELUDE + _group("ops", '{ "kind": "nope", "children": { "a": {} } }'))
  assert r.returncode != 0, r.stdout
  assert ('ops: does not meet schema/group.json: Property kind: Value "nope" not in enum; '
          'one of "goal" "call" "block" "scoped" "group"') in r.stderr, r.stderr


@ENGINES
@pytest.mark.parametrize("charter,want", [('"kind": "goal", ', "goal"), ("", "call")])
def test_a_bound_member_takes_the_charters_kind(amk, tmp_path, charter, want):
  lines = PRELUDE + _group("ops", "{ " + charter + '"restart": "never", "children": {} }') + [
    *_member("@ops.actor (lua)", "m", '  print("m ran")', '  return "up"'),
    "after: ops.__main__", '\t@echo "[$(ops.get -r .children.m.kind)]"',
  ]
  r = _run(amk, tmp_path, lines, "after")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "m ran" in r.stdout + r.stderr and "ops: exited m 0" in r.stdout, r.stdout + r.stderr
  assert f"[{want}]" in r.stdout, r.stdout
  assert "warning" not in r.stderr, r.stderr


@ENGINES
@pytest.mark.parametrize("at", ["@ops.bind.lua", "@ops.lua"])
def test_a_group_has_no_bind_or_engine_decorator(amk, tmp_path, at):
  r = _run(amk, tmp_path, PRELUDE + _group("ops", '{ "children": {} }') + _member(at, "m", '  return "up"'))
  assert r.returncode != 0, r.stdout
  assert f"{at}: no macro {at[1:]}_star" in r.stderr, r.stderr


@ENGINES
def test_the_actor_form_takes_the_engine_as_its_first_word(amk, tmp_path):
  lines = PRELUDE + _group("ops", '{ "children": {} }') + [
    *_member("@ops.actor (lua) {restart=never}", "m", '  return "up"'),
    "after: ops.__main__",
    '\t@echo "[$(ops.get -r .children.m.engine) $(ops.get -r .children.m.restart)]"',
  ]
  r = _run(amk, tmp_path, lines, "after")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "ops: exited m 0" in r.stdout and "[lua never]" in r.stdout, r.stdout


@ENGINES
@pytest.mark.parametrize("at,want", [
  ("@ops.actor", "m: @ops.actor needs an engine; lua js micropy s7"),
  ("@ops.actor (awk)", "m: awk cannot run an actor; lua js micropy s7 can"),
])
def test_the_actor_form_refuses_a_missing_or_unbindable_engine(amk, tmp_path, at, want):
  r = _run(amk, tmp_path, PRELUDE + _group("ops", '{ "children": {} }') + _member(at, "m", '  return "up"'))
  assert r.returncode != 0, r.stdout
  assert want in r.stderr, r.stderr
  assert "warning" not in r.stderr, r.stderr


@pytest.mark.engines("jq", "lua", "micropy", "js", "sqlite")
def test_a_late_member_is_checked_against_the_group_schema(amk, tmp_path):
  r = _run(amk, tmp_path, PRELUDE + _group("ops", '{ "children": {} }')
           + _member("@ops.actor/lua {restart=maybe}", "m", '  return "up"'))
  assert r.returncode != 0, r.stdout
  assert ('m: does not meet schema/group.json: Property children: Additional property m: '
          'Property restart: Value "maybe" not in enum; one of "always" "on-failure" "never"') in r.stderr, r.stderr


SELF_MAIL = {
  "lua": ['  __group__.cast(ops.id, "hi")', '  return "got " .. ops.recv()'],
  "micropy": ['  __group__.cast(ops.id, "hi")', '  return "got " + ops.recv()'],
  "js": ['  __group__.cast(ops.id, "hi");', '  return "got " + ops.recv();'],
}


@ENGINES
@pytest.mark.parametrize("engine", sorted(SELF_MAIL))
def test_a_bound_body_reaches_its_mailbox_by_the_groups_name_and_as_group(amk, tmp_path, engine):
  lines = PRELUDE + _group("ops", '{ "mailbox": "pool", "restart": "never", "children": {} }') + [
    *_member(f"@ops.actor ({engine})", "m", *SELF_MAIL[engine]),
  ]
  r = _run(amk, tmp_path, lines)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "m: got hi" in r.stdout + r.stderr, r.stdout + r.stderr


@S7
def test_s7_a_bound_body_reaches_its_mailbox_by_the_groups_name_and_as_group(amk, tmp_path):
  lines = S7_PRELUDE + _s7_group("ops", '"mailbox": "pool", "restart": "never"') + [
    *_member("@ops.actor (s7)", "m","  (__group__ 'cast (ops 'id) \"hi\")", "  (string-append \"got \" (ops 'recv))"),
  ]
  r = _run(amk, tmp_path, lines)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "m: got hi" in r.stdout + r.stderr, r.stdout + r.stderr


MAIL = PRELUDE + _group("ops", '{ "mailbox": "pool", "children": { "ping": { "kind": "goal", "restart": "never" } } }') + [
  *_member("@ops.actor (lua) {kind=goal restart=never}", "pong",
           "  for n = 1, 2 do",
           '    local m = amk.ops.recv("pong")',
           '    print("pong got " .. m)',
           '    amk.ops.cast("ping", "re-" .. m)',
           "  end"),
  "@micropy.target",
  "define ping",
  "  import amk",
  "  for n in (1, 2):",
  '    amk.ops.cast("pong", "m%d" % n)',
  '    print("ping got " + amk.ops.recv("ping"))',
  "endef",
  "after: ops.__main__",
  '\t@echo "[$(filter ops.%,$(amk.pool ))][$(amk.pool.size ops.ping.inbox)$(amk.pool.size ops.pong.inbox)]"',
]


@ENGINES
def test_a_pool_mailbox_gives_each_member_an_inbox_its_siblings_cast_to(amk, tmp_path):
  r = _run(amk, tmp_path, MAIL, "after")
  assert r.returncode == 0, r.stdout + r.stderr
  got = [l for l in r.stdout.splitlines() if " got " in l]
  assert got == ["pong got m1", "ping got re-m1", "pong got m2", "ping got re-m2"], r.stdout
  assert "[ops.ping.inbox ops.pong.inbox][00]" in r.stdout, r.stdout


ASK = PRELUDE + _group("ops", '{ "mailbox": "pool", "children": { "q": { "kind": "goal", "restart": "never", "ask": true } } }') + [
  *_member("@ops.actor (lua) {kind=goal restart=never}", "echo",
           "  for n = 1, 2 do",
           '    local m = amk.ops.recv("echo")',
           '    amk.ops.reply(m, "re-" .. m:gsub(":", "-"))',
           "  end"),
  "@micropy.target",
  "define q",
  "  import amk",
  "  for w in ('a', 'b'):",
  '    print("q got " + amk.ops.ask("q", "echo", w))',
  "endef",
  "after: ops.__main__",
  '\t@echo "[$(filter ops.%,$(amk.pool ))][$(amk.pool.size ops.q.reply)]"',
]


@ENGINES
def test_an_ask_waits_for_the_reply_to_its_own_reply_pool(amk, tmp_path):
  r = _run(amk, tmp_path, ASK, "after")
  assert r.returncode == 0, r.stdout + r.stderr
  assert [l for l in r.stdout.splitlines() if l.startswith("q got ")] == ["q got re-q-a", "q got re-q-b"], r.stdout
  assert "[ops.q.inbox ops.q.reply ops.echo.inbox][0]" in r.stdout, r.stdout


@ENGINES
def test_a_charter_ask_gives_every_member_a_reply_unless_it_opts_out(amk, tmp_path):
  lines = PRELUDE + _group("ops", '{ "mailbox": "pool", "ask": true, "children": { "a": {}, "b": { "ask": false } } }') + [
    *_member("@ops.actor (lua)", "c", '  return "up"'),
    "$(info [$(filter ops.%,$(amk.pool ))])",
  ]
  r = _run(amk, tmp_path, lines)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[ops.a.inbox ops.a.reply ops.b.inbox ops.c.inbox ops.c.reply]" in r.stdout, r.stdout


@ENGINES
def test_a_member_without_ask_is_refused_an_ask(amk, tmp_path):
  lines = PRELUDE + _group("ops", '{ "mailbox": "pool", "children": { "a": {}, "b": {} } }') + [
    "$(info [$(filter ops.%,$(amk.pool ))])", "$(ops.ask a, b, hi)"]
  r = _run(amk, tmp_path, lines)
  assert r.returncode != 0, r.stdout
  assert "[ops.a.inbox ops.b.inbox]" in r.stdout, r.stdout
  assert "ops: a does not ask; give it ask=true" in r.stderr, r.stderr


@ENGINES
def test_a_charter_without_a_mailbox_opens_no_pool_and_refuses_cast(amk, tmp_path):
  lines = PRELUDE + _group("ops", '{ "children": {} }') + [
    "$(info [$(filter-out goals actors,$(amk.pool ))])", "$(ops.cast x, hi)"]
  r = _run(amk, tmp_path, lines)
  assert r.returncode != 0, r.stdout
  assert "[]" in r.stdout, r.stdout
  assert "ops: no mailboxes; the charter's mailbox is none" in r.stderr, r.stderr


@ENGINES
@pytest.mark.parametrize("before,charter,want", [
  ("", '{ "strategy": "rest_for_one", "children": {} }', 'ops: does not meet schema/group.json: Property strategy: Value "rest_for_one" not in enum; one of "one_for_one"'),
  ("", '{ "mailbox": "mbox", "children": {} }', 'ops: does not meet schema/group.json: Property mailbox: Value "mbox" not in enum; one of "none" "pool"'),
  ("$(foreach i,$(shell seq 1 61),$(amk.pool p$(i), 1))",
   '{ "mailbox": "pool", "children": { "a": {}, "b": {} } }',
   "ops: 2 inboxes and replies do not fit; 63 of 64 pools are open"),
  ("$(foreach i,$(shell seq 1 60),$(amk.pool p$(i), 1))",
   '{ "mailbox": "pool", "children": { "a": { "ask": true }, "b": {} } }',
   "ops: 3 inboxes and replies do not fit; 62 of 64 pools are open"),
])
def test_a_mailbox_charter_is_refused_at_declaration(amk, tmp_path, before, charter, want):
  r = _run(amk, tmp_path, PRELUDE + [before] + _group("ops", charter))
  assert r.returncode != 0, r.stdout
  assert want in r.stderr, r.stderr

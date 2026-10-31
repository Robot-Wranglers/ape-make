"""Pins jobmen: `lib/dsys/jobman.amk` and `lib/jobman/`, pools of jobs and each guest's handle on one.

A jobman spawns a job after taking a token of its pool and gives it back on reap, so map
runs at most size jobs at once, in order, and stops launching at the first failure when
fail_fast is set. Pinned per guest with spawn, lua and js, and for the make side: the
callform, the decorator over the baseline, and the default __jobs__ pool.
"""

import pytest

from conftest import sh

WORKER = [
  "@lua.target",
  "define worker",
  '  local f = io.open("log", "a") f:write("in\\n") f:close()',
  '  os.execute("sleep 0.3")',
  '  f = io.open("log", "a") f:write("out\\n") f:close()',
  "endef",
  "@lua.target",
  "define crasher",
  '  error("boom")',
  "endef",
]


def run(amk, tmp_path, body, goal="probe"):
  mk = tmp_path / "mp.mk"
  mk.write_text(body + "\nall:\n\t@true\n")
  return sh(amk, ["-s", "-f", str(mk), goal], cwd=tmp_path, timeout=120)


def probe(engine, *lines):
  return [f"@{engine}.target", "define probe", *lines, "endef"]


def depth(log):
  """The most jobs inside their critical sections at once."""
  most = now = 0
  for line in log.split():
    now += 1 if line == "in" else -1
    most = max(most, now)
  return most


@pytest.mark.engines("lua", "jq")
def test_lua_map_runs_at_most_size_jobs_at_once_in_order(amk, tmp_path):
  r = run(amk, tmp_path, "\n".join([
    "load dsys/jobman",
    "$(jobman mine, 2)",
    *WORKER,
    *probe("lua",
           "  local rs = amk.jobman.mine.map({{'worker'}, {'worker'}, {'worker'}, {'worker'}})",
           "  local s = {} for i = 1, 4 do s[i] = rs[i].status end",
           "  print(table.concat(s, ' ') .. ' ' .. amk.pool.mine.held())"),
  ]))
  assert r.returncode == 0, r.stdout + r.stderr
  assert "success success success success 0" in r.stdout, r.stdout
  assert depth((tmp_path / "log").read_text()) == 2


@pytest.mark.engines("js", "lua", "jq")
def test_js_map_runs_at_most_size_jobs_at_once_in_order(amk, tmp_path):
  r = run(amk, tmp_path, "\n".join([
    "load dsys/jobman",
    "$(jobman mine, 2)",
    *WORKER,
    *probe("js",
           "  const rs = await amk.jobman.on('mine').map([['worker'], ['worker'], ['worker'], ['worker']]);",
           "  print(rs.map(r => r.status).join(' ') + ' ' + amk.pool.mine.held());"),
  ]))
  assert r.returncode == 0, r.stdout + r.stderr
  assert "success success success success 0" in r.stdout, r.stdout
  assert depth((tmp_path / "log").read_text()) == 2


@pytest.mark.engines("lua", "jq")
def test_fail_fast_stops_launching_after_the_first_failure(amk, tmp_path):
  r = run(amk, tmp_path, "\n".join([
    "load dsys/jobman",
    "@jobman",
    "define strict",
    '  { "size": 1, "fail_fast": true }',
    "endef",
    *WORKER,
    *probe("lua",
           "  local rs = amk.jobman.strict.map({{'crasher'}, {'worker'}, {'worker'}})",
           "  local n = 0 for _ in pairs(rs) do n = n + 1 end",
           "  print(n .. ' ' .. rs[1].status .. ' ' .. tostring(rs[2] == nil))"),
  ]))
  assert r.returncode == 0, r.stdout + r.stderr
  assert "1 failed true" in r.stdout, r.stdout
  assert not (tmp_path / "log").exists()


@pytest.mark.engines("lua", "jq")
def test_spawn_and_wait_hold_a_token_across_the_job(amk, tmp_path):
  r = run(amk, tmp_path, "\n".join([
    "load dsys/jobman",
    *WORKER,
    *probe("lua",
           "  local p = amk.jobman.__jobs__",
           "  local pid = p.spawn({'worker'})",
           "  local during = amk.pool.__jobs__.held()",
           "  local r = p.wait(pid)",
           "  print(during .. ' ' .. amk.pool.__jobs__.held() .. ' ' .. r.status)"),
  ]))
  assert r.returncode == 0, r.stdout + r.stderr
  assert "1 0 success" in r.stdout, r.stdout


NAP = ["nap:", "\t@sleep 5"]


@pytest.mark.engines("lua", "jq")
def test_lua_kill_ends_a_job_and_its_reap_frees_the_token(amk, tmp_path):
  r = run(amk, tmp_path, "\n".join([
    "load dsys/jobman",
    *NAP,
    *probe("lua",
           "  local p = amk.jobman.__jobs__",
           "  local pid = p.spawn({'nap'})",
           "  local sent = p.kill(pid)",
           "  local r = p.wait(pid)",
           "  print(tostring(sent) .. ' ' .. r.status .. ' ' .. amk.pool.__jobs__.held())"),
  ]))
  assert r.returncode == 0, r.stdout + r.stderr
  assert "true signal 0" in r.stdout, r.stdout


@pytest.mark.engines("js", "jq")
def test_js_stop_and_resume_a_job_through_the_handle(amk, tmp_path):
  r = run(amk, tmp_path, "\n".join([
    "load dsys/jobman",
    *NAP,
    *probe("js",
           "  const p = amk.jobman.__jobs__;",
           "  const pid = p.spawn(['nap']);",
           "  const s = p.stop(pid), a = p.wait(pid).status, c = p.resume(pid);",
           "  p.kill(pid);",
           "  print([s, a, c, p.wait(pid).status, amk.pool.__jobs__.held()].join(' '));"),
  ]))
  assert r.returncode == 0, r.stdout + r.stderr
  assert "true stopped true signal 0" in r.stdout, r.stdout


@pytest.mark.engines("s7", "lua", "jq")
def test_s7_map_runs_at_most_size_jobs_at_once_in_order(amk, tmp_path):
  r = run(amk, tmp_path, "\n".join([
    "load dsys/jobman",
    "$(jobman mine, 2)",
    *WORKER,
    *probe("s7",
           "  (let ((rs ((amk-jobman-on \"mine\") 'map '((\"worker\") (\"worker\") (\"worker\") (\"worker\")))))",
           "    (for-each (lambda (r) (display (r 'status)) (display \" \")) rs)",
           "    (display (amk-call \"amk.pool.held\" \"mine\")) (newline))"),
  ]))
  assert r.returncode == 0, r.stdout + r.stderr
  assert "success success success success 0" in r.stdout, r.stdout
  assert depth((tmp_path / "log").read_text()) == 2


@pytest.mark.engines("s7", "lua", "jq")
def test_s7_spawn_and_wait_hold_a_token_across_the_job(amk, tmp_path):
  r = run(amk, tmp_path, "\n".join([
    "load dsys/jobman",
    *WORKER,
    *probe("s7",
           "  (let* ((pid (amk-jobman-__jobs__ 'spawn '(\"worker\")))",
           "         (during (amk-call \"amk.pool.held\" \"__jobs__\"))",
           "         (r (amk-jobman-__jobs__ 'wait pid)))",
           "    (format #t \"~A ~A ~A~%\" during (amk-call \"amk.pool.held\" \"__jobs__\") (r 'status)))"),
  ]))
  assert r.returncode == 0, r.stdout + r.stderr
  assert "1 0 success" in r.stdout, r.stdout


@pytest.mark.engines("micropy", "lua", "jq")
def test_micropy_spawn_wait_and_kill_through_the_handle(amk, tmp_path):
  r = run(amk, tmp_path, "\n".join([
    "load dsys/jobman",
    *WORKER,
    *NAP,
    *probe("micropy",
           "  import amk",
           "  p = amk.jobman.__jobs__",
           "  pid = p.spawn(['worker'])",
           "  during = amk.pool.__jobs__.held()",
           "  r = p.wait(pid)",
           "  nap = p.spawn(['nap'])",
           "  sent = p.kill(nap)",
           "  k = p.wait(nap)",
           "  print(during, r['status'], sent, k['status'], amk.pool.__jobs__.held())"),
  ]))
  assert r.returncode == 0, r.stdout + r.stderr
  assert "1 success True signal 0" in r.stdout, r.stdout


@pytest.mark.engines("micropy", "lua", "jq")
def test_micropy_map_runs_at_most_size_jobs_at_once_in_order(amk, tmp_path):
  r = run(amk, tmp_path, "\n".join([
    "load dsys/jobman",
    "$(jobman mine, 2)",
    *WORKER,
    *probe("micropy",
           "  import amk",
           "  rs = amk.jobman.on('mine').map([['worker'], ['worker'], ['worker'], ['worker']])",
           "  print(' '.join(x['status'] for x in rs), amk.pool.mine.held())"),
  ]))
  assert r.returncode == 0, r.stdout + r.stderr
  assert "success success success success 0" in r.stdout, r.stdout
  assert depth((tmp_path / "log").read_text()) == 2


@pytest.mark.engines("s7", "lua", "jq")
def test_s7_kill_and_stop_through_the_handle(amk, tmp_path):
  r = run(amk, tmp_path, "\n".join([
    "load dsys/jobman",
    *NAP,
    *probe("s7",
           "  (let* ((pid (amk-jobman-__jobs__ 'spawn '(\"nap\")))",
           "         (s (amk-jobman-__jobs__ 'stop pid))",
           "         (a ((amk-jobman-__jobs__ 'wait pid) 'status))",
           "         (k (amk-jobman-__jobs__ 'kill pid))",
           "         (c (amk-jobman-__jobs__ 'resume pid))",
           "         (r (amk-jobman-__jobs__ 'wait pid)))",
           "    (format #t \"~A ~A ~A ~A ~A~%\" s a k (r 'status) (amk-call \"amk.pool.held\" \"__jobs__\")))"),
  ]))
  assert r.returncode == 0, r.stdout + r.stderr
  assert "#t stopped #t signal 0" in r.stdout, r.stdout


unpooled = {
  "lua": [
    "  local m = amk.jobman",
    "  local pid = m.spawn({'nap'})",
    "  local held = amk.pool.__jobs__.held()",
    "  local s, c, k = m.stop(pid), m.resume(pid), m.kill(pid)",
    "  print(held .. ' ' .. tostring(s) .. ' ' .. tostring(c) .. ' ' .. tostring(k) .. ' ' .. m.wait(pid).status .. ' ' .. tostring(m.wait(pid, false)))",
  ],
  "micropy": [
    "  import amk",
    "  m = amk.jobman",
    "  pid = m.spawn(['nap'])",
    "  held = amk.pool.__jobs__.held()",
    "  s, c, k = m.stop(pid), m.resume(pid), m.kill(pid)",
    "  print(held, s, c, k, m.wait(pid)['status'], m.wait(pid, False))",
  ],
  "js": [
    "  const m = amk.jobman;",
    "  const pid = m.spawn(['nap']);",
    "  const held = amk.pool.__jobs__.held();",
    "  const s = m.stop(pid), c = m.resume(pid), k = m.kill(pid);",
    "  print([held, s, c, k, m.wait(pid).status, m.wait(pid, false)].join(' '));",
  ],
  "s7": [
    "  (let* ((pid (amk-jobman-spawn '(\"nap\")))",
    "         (held (amk-call \"amk.pool.held\" \"__jobs__\"))",
    "         (s (amk-jobman-stop pid)) (c (amk-jobman-resume pid)) (k (amk-jobman-kill pid)))",
    "    (format #t \"~A ~A ~A ~A ~A ~A~%\" held s c k ((amk-jobman-wait pid) 'status) (amk-jobman-wait pid #f)))",
  ],
}
unpooled_want = {
  "lua": "0 true true true signal nil",
  "micropy": "0 True True True signal None",
  "js": "0 true true true signal ",
  "s7": "0 #t #t #t signal #f",
}


@pytest.mark.parametrize("engine", [
  pytest.param("lua", marks=pytest.mark.engines("lua", "jq")),
  pytest.param("micropy", marks=pytest.mark.engines("micropy", "lua", "jq")),
  pytest.param("js", marks=pytest.mark.engines("js", "lua", "jq")),
  pytest.param("s7", marks=pytest.mark.engines("s7", "lua", "jq")),
])
def test_the_module_verbs_take_no_token(amk, tmp_path, engine):
  """spawn, wait and job control at module level, with the guest's own values and the __jobs__ pool untouched."""
  r = run(amk, tmp_path, "\n".join(["load dsys/jobman", *NAP, *probe(engine, *unpooled[engine])]))
  assert r.returncode == 0, r.stdout + r.stderr
  assert unpooled_want[engine] in r.stdout, r.stdout + r.stderr


FAST = ["fast:", "\t@true", "slow:", "\t@sleep 1"]
GUESTS = [
  pytest.param("lua", marks=pytest.mark.engines("lua", "jq")),
  pytest.param("micropy", marks=pytest.mark.engines("micropy", "lua", "jq")),
  pytest.param("js", marks=pytest.mark.engines("js", "lua", "jq")),
  pytest.param("s7", marks=pytest.mark.engines("s7", "lua", "jq")),
]

# A pool's wait with no pid takes its own member, and a job outside the pool keeps its record.
scoped = {
  "lua": [
    "  local p = amk.jobman.__jobs__",
    "  local other = amk.goal.spawn('fast')",
    "  local pid = p.spawn({'slow'})",
    "  local r = p.wait()",
    "  local o = require('dkjson').decode(amk.job.wait(other))",
    "  print(tostring(r.pid == pid) .. ' ' .. o.status .. ' ' .. amk.pool.__jobs__.held())",
  ],
  "micropy": [
    "  import amk, json",
    "  p = amk.jobman.__jobs__",
    "  other = amk.goal.spawn('fast')",
    "  pid = p.spawn(['slow'])",
    "  r = p.wait()",
    "  o = json.loads(amk.job.wait(other))",
    "  print(r['pid'] == pid, o['status'], amk.pool.__jobs__.held())",
  ],
  "js": [
    "  const p = amk.jobman.__jobs__;",
    "  const other = amk.goal.spawn('fast');",
    "  const pid = p.spawn(['slow']);",
    "  const r = p.wait();",
    "  const o = JSON.parse(amk.job.wait(other));",
    "  print([r.pid === pid, o.status, amk.pool.__jobs__.held()].join(' '));",
  ],
  "s7": [
    "  (let* ((other (amk-call \"amk.goal.spawn\" \"fast\"))",
    "         (pid (amk-jobman-__jobs__ 'spawn '(\"slow\")))",
    "         (r (amk-jobman-__jobs__ 'wait))",
    "         (o (json-read (amk-call \"amk.job.wait\" other))))",
    "    (format #t \"~A ~A ~A~%\" (= (r 'pid) pid) (o 'status) (amk-call \"amk.pool.held\" \"__jobs__\")))",
  ],
}
scoped_want = {"lua": "true success 0", "micropy": "True success 0", "js": "true success 0", "s7": "#t success 0"}


@pytest.mark.parametrize("engine", GUESTS)
def test_a_pool_waits_only_on_its_own_members(amk, tmp_path, engine):
  r = run(amk, tmp_path, "\n".join(["load dsys/jobman", *FAST, *probe(engine, *scoped[engine])]))
  assert r.returncode == 0, r.stdout + r.stderr
  assert scoped_want[engine] in r.stdout, r.stdout + r.stderr


# race answers the fast list and ends the slow one; close ends every member; both give the tokens back.
plex = {
  "lua": [
    "  local p = amk.jobman.__jobs__",
    "  local w = p.race({{'nap'}, {'fast'}})",
    "  local after = #p.pending()",
    "  p.spawn({'nap'}) p.spawn({'nap'})",
    "  local before = #p.pending()",
    "  local rs = p.close()",
    "  print(w.status .. ' ' .. after .. ' ' .. before .. ' ' .. #rs .. ' ' .. rs[1].status .. ' ' .. rs[2].status .. ' ' .. #p.pending() .. ' ' .. amk.pool.__jobs__.held())",
  ],
  "micropy": [
    "  import amk",
    "  p = amk.jobman.__jobs__",
    "  w = p.race([['nap'], ['fast']])",
    "  after = len(p.pending())",
    "  p.spawn(['nap']); p.spawn(['nap'])",
    "  before = len(p.pending())",
    "  rs = p.close()",
    "  print(w['status'], after, before, len(rs), rs[0]['status'], rs[1]['status'], len(p.pending()), amk.pool.__jobs__.held())",
  ],
  "js": [
    "  const p = amk.jobman.__jobs__;",
    "  const w = p.race([['nap'], ['fast']]);",
    "  const after = p.pending().length;",
    "  p.spawn(['nap']); p.spawn(['nap']);",
    "  const before = p.pending().length;",
    "  const rs = p.close();",
    "  print([w.status, after, before, rs.length, rs[0].status, rs[1].status, p.pending().length, amk.pool.__jobs__.held()].join(' '));",
  ],
  "s7": [
    "  (let* ((p amk-jobman-__jobs__)",
    "         (w (p 'race '((\"nap\") (\"fast\"))))",
    "         (after (length (p 'pending)))",
    "         (a (p 'spawn '(\"nap\"))) (b (p 'spawn '(\"nap\")))",
    "         (before (length (p 'pending)))",
    "         (rs (p 'close)))",
    "    (format #t \"~A ~A ~A ~A ~A ~A ~A ~A~%\" (w 'status) after before (length rs) ((car rs) 'status) ((cadr rs) 'status) (length (p 'pending)) (amk-call \"amk.pool.held\" \"__jobs__\")))",
  ],
}


@pytest.mark.parametrize("engine", GUESTS)
def test_race_and_close_end_the_members_and_give_back_their_tokens(amk, tmp_path, engine):
  r = run(amk, tmp_path, "\n".join(["load dsys/jobman", *FAST, *NAP, *probe(engine, *plex[engine])]))
  assert r.returncode == 0, r.stdout + r.stderr
  assert "success 0 2 2 signal signal 0 0" in r.stdout, r.stdout + r.stderr


# spawn.<kind> on the jobman and the module: what runs is in each record's kind, a call's value is read once, and every token comes back.
kinds = {
  "lua": [
    "  local j, m = amk.jobman.__jobs__, amk.jobman",
    "  local g, gs = j.wait(j.spawn.goal('fast')), j.wait(j.spawn.goals({'fast', 'fast'}))",
    "  local c = j.spawn.call('greet', 'world')",
    "  local cr = j.wait(c)",
    "  local b, mg = j.wait(j.spawn({'fast'})), m.wait(m.spawn.goal('fast'))",
    "  print(g.kind, gs.kind, cr.kind, amk.job.value(c), b.kind, mg.kind, amk.pool.__jobs__.held())",
  ],
  "micropy": [
    "  import amk",
    "  j, m = amk.jobman.__jobs__, amk.jobman",
    "  g, gs = j.wait(j.spawn.goal('fast')), j.wait(j.spawn.goals(['fast', 'fast']))",
    "  c = j.spawn.call('greet', 'world')",
    "  cr = j.wait(c)",
    "  b, mg = j.wait(j.spawn(['fast'])), m.wait(m.spawn.goal('fast'))",
    "  print(g['kind'], gs['kind'], cr['kind'], amk.job.value(c), b['kind'], mg['kind'], amk.pool.__jobs__.held(), sep='\\t')",
  ],
  "js": [
    "  const j = amk.jobman.__jobs__, m = amk.jobman;",
    "  const g = j.wait(j.spawn.goal('fast')), gs = j.wait(j.spawn.goals(['fast', 'fast']));",
    "  const c = j.spawn.call('greet', 'world');",
    "  const cr = j.wait(c);",
    "  const b = j.wait(j.spawn(['fast'])), mg = m.wait(m.spawn.goal('fast'));",
    "  print([g.kind, gs.kind, cr.kind, amk.job.value(c), b.kind, mg.kind, amk.pool.__jobs__.held()].join('\\t'));",
  ],
  "s7": [
    "  (let* ((j amk-jobman-__jobs__)",
    "         (g (j 'wait (j 'spawn.goal \"fast\")))",
    "         (gs (j 'wait (j 'spawn.goals '(\"fast\" \"fast\"))))",
    "         (c (j 'spawn.call \"greet\" \"world\"))",
    "         (cr (j 'wait c))",
    "         (b (j 'wait (j 'spawn '(\"fast\"))))",
    "         (mg (amk-jobman-wait (amk-jobman-spawn-kind 'goal \"fast\"))))",
    "    (format #t \"~A\\t~A\\t~A\\t~A\\t~A\\t~A\\t~A~%\" (g 'kind) (gs 'kind) (cr 'kind) (amk-call \"amk.job.value\" c) (b 'kind) (mg 'kind) (amk-call \"amk.pool.held\" \"__jobs__\")))",
  ],
}
refused_kind = {
  "lua": ["  amk.jobman.__jobs__.spawn.nope('x')"],
  "micropy": ["  import amk", "  amk.jobman.__jobs__.spawn.nope('x')"],
  "js": ["  amk.jobman.__jobs__.spawn.nope('x');"],
  "s7": ["  (amk-jobman-__jobs__ 'spawn.nope \"x\")"],
}


@pytest.mark.parametrize("engine", GUESTS)
def test_a_jobman_spawns_by_kind_and_make_refuses_a_kind_it_lacks(amk, tmp_path, engine):
  head = ["load dsys/jobman", "greet = hello $(1)", *FAST]
  r = run(amk, tmp_path, "\n".join([*head, *probe(engine, *kinds[engine])]))
  assert r.returncode == 0, r.stdout + r.stderr
  assert "goal\tgoals\tcall\thello world\tgoals\tgoal\t0" in r.stdout, r.stdout + r.stderr
  r = run(amk, tmp_path, "\n".join([*head, *probe(engine, *refused_kind[engine])]))
  assert r.returncode != 0
  assert "amk.job.spawn: give kind=name, one of goal=.. goals=.. call=..; got 'nope=x'" in r.stderr, r.stderr


@pytest.mark.engines("lua", "jq")
def test_a_peek_answers_a_finished_member_and_leaves_it_to_the_wait(amk, tmp_path):
  r = run(amk, tmp_path, "\n".join([
    "load dsys/jobman",
    *FAST,
    *probe("lua",
           "  local p = amk.jobman.__jobs__",
           "  local pid = p.spawn({'fast'})",
           "  os.execute('sleep 0.5')",
           "  local k = p.peek(pid)",
           "  local held = amk.pool.__jobs__.held()",
           "  local r = p.wait(pid)",
           "  print(k.status .. ' ' .. held .. ' ' .. tostring(k.pid == r.pid) .. ' ' .. amk.pool.__jobs__.held())"),
  ]))
  assert r.returncode == 0, r.stdout + r.stderr
  assert "success 1 true 0" in r.stdout, r.stdout


@pytest.mark.engines("jq")
def test_loading_the_topic_opens_the_procs_pool_once(amk, tmp_path):
  body = "\n".join([
    "load dsys/jobman",
    "load dsys/jobman",
    "$(info [$(amk.pool )] [$(amk.pool __jobs__)])",
  ])
  r = run(amk, tmp_path, body, goal="all")
  assert "[goals __jobs__] [4]" in r.stdout + r.stderr, r.stdout + r.stderr
  r = sh(amk, ["-s", "-f", str(tmp_path / "mp.mk")], cwd=tmp_path, env={"AMK_MAX_JOBS": "3"}, timeout=120)
  assert "[goals __jobs__] [3]" in r.stdout + r.stderr, r.stdout + r.stderr
  r = run(amk, tmp_path, "jobman.max_jobs := 6\n" + body, goal="all")
  assert "[goals __jobs__] [6]" in r.stdout + r.stderr, r.stdout + r.stderr


@pytest.mark.engines("jq")
def test_the_decorator_and_callform_declare_a_pool_with_fail_fast(amk, tmp_path):
  r = run(amk, tmp_path, "\n".join([
    "load dsys/jobman",
    "@jobman",
    "define wide",
    '  { "size": 5 }',
    "endef",
    "$(jobman narrow, 1, true)",
    "$(info [$(amk.pool )] [$(amk.pool wide)] [$(jobman.wide.fail_fast)] [$(amk.pool narrow)] [$(jobman.narrow.fail_fast)] [$(jobman.__jobs__.fail_fast)])",
  ]), goal="all")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[goals __jobs__ wide narrow] [5] [false] [1] [true] [false]" in r.stdout + r.stderr, r.stdout + r.stderr


@pytest.mark.engines("jq", "sqlite")
@pytest.mark.parametrize("body,want", [
  ('{ "size": 1, "retries": 3 }', "Additional property 'retries' not allowed"),
  ('{ "fail_fast": "yes" }', "Property fail_fast: Type mismatch: expected boolean, got string"),
  ('{ "size": -1 }', "Property size: Less than minimum 0"),
  ('{ "strategy": "lifo" }', 'Property strategy: Value "lifo" not in enum'),
])
def test_the_decorator_is_checked_against_its_schema(amk, tmp_path, body, want):
  r = run(amk, tmp_path, "\n".join([
    "load dsys/jobman", "@jobman", "define odd", f"  {body}", "endef",
  ]), goal="all")
  assert r.returncode != 0, r.stdout + r.stderr
  assert "odd: does not meet schema/jobman.json: " + want in r.stderr, r.stderr


@pytest.mark.engines("jq")
def test_the_decorator_takes_a_pools_keys(amk, tmp_path):
  r = run(amk, tmp_path, "\n".join([
    "load dsys/jobman",
    "@jobman", "define gpus", '  { "labels": ["g0", "g1"], "fail_fast": true }', "endef",
    "$(info [$(amk.pool gpus)] [$(amk.pool.acquire gpus)] [$(jobman.gpus.fail_fast)])",
  ]), goal="all")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[2] [g0] [true]" in r.stdout + r.stderr, r.stdout + r.stderr

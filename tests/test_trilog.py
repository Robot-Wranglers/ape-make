"""Pins the trilog engine.

trilog is a Prolog guest: a chunk is clauses and directives, run one clause at a time. A
directive's uncaught error is reported on stderr and fails the chunk. The handle is amk_
builtins named after make's verbs: amk_var, amk_goal, amk_goal_spawn, amk_job_*, amk_send,
amk_expand, amk_call. The engine's import makes a workspace, as jq's does; the state import,
through the ns form, sets every amk_export(Name, Value) in make.
"""

import json

import pytest

from conftest import sh

pytestmark = pytest.mark.engines("trilog")

jobs = "\n".join([
  "load dsys/job",
  "ok:",
  "\ttrue",
  "bad:",
  "\tfalse",
  "slow:",
  "\tsleep 5",
  "",
])


def run(amk, tmp_path, text, goal):
  mk = tmp_path / "t.mk"
  mk.write_text(text)
  return sh(amk, ["-s", "-f", str(mk), goal], cwd=tmp_path, timeout=120)


def test_a_chunk_runs_its_directives_over_its_clauses(amk, tmp_path):
  r = run(amk, tmp_path, "\n".join([
    "@trilog.target",
    "define found",
    "p(1).",
    "p(2).",
    ":- findall(X, p(X), L), write(L), nl.",
    "endef",
    "",
  ]), "found")
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "[1,2]", r.stdout + r.stderr


def test_an_uncaught_error_goes_to_stderr_and_fails(amk, tmp_path):
  r = run(amk, tmp_path, "\n".join([
    "@trilog.target",
    "define raising",
    ":- X is 1/0, write(X).",
    "endef",
    "",
  ]), "raising")
  assert r.returncode != 0, r.stdout + r.stderr
  assert "zero_divisor" in r.stderr and r.stdout.strip() == "", r.stdout + r.stderr


def test_nested_catch_inside_findall_runs(amk, tmp_path):
  r = run(amk, tmp_path, "\n".join([
    "@trilog.target",
    "define nested",
    "p(1).",
    ":- catch(catch(catch(findall(X, catch(p(X), _, fail), L), _, true), _, true), _, true), write(L), nl.",
    "endef",
    "",
  ]), "nested")
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "[1]", r.stdout + r.stderr


def test_var_and_set_reach_make_variables(amk, tmp_path):
  r = run(amk, tmp_path, "\n".join([
    "greeting := hello",
    "@trilog.target",
    "define vars",
    ":- amk_var(greeting, G), amk_var_set(made, G), amk_var(made, M), write(M), nl.",
    ":- (amk_var(never_set, _) -> write(seen) ; write(unseen)), nl.",
    "endef",
    "",
  ]), "vars")
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.split() == ["hello", "unseen"], r.stdout + r.stderr


def test_an_import_exports_every_amk_export(amk, tmp_path):
  r = run(amk, tmp_path, "\n".join([
    "define facts",
    "amk_export(color, red).",
    "amk_export(size, large).",
    "endef",
    "x := $(trilog.ns* main, import, facts)",
    "shown:",
    "\t@echo $(color) $(size)",
    "",
  ]), "shown")
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "red large", r.stdout + r.stderr


def test_json_write_follows_insimuls_mapping(amk, tmp_path):
  r = run(amk, tmp_path, "\n".join([
    "@trilog.target",
    "define shown",
    ":- json_write(f(x, [1, 2.5], 's\"q', _, [a|_], [], [a, b])), nl.",
    "endef",
    "",
  ]), "shown")
  assert r.returncode == 0, r.stdout + r.stderr
  assert json.loads(r.stdout) == {"functor": "f", "args": [
    "x", [1, 2.5], "s\"q", None, {"functor": ".", "args": ["a", None]}, [], ["a", "b"]]}, r.stdout + r.stderr


def test_a_query_answers_one_json_object_per_solution(amk, tmp_path):
  r = run(amk, tmp_path, "\n".join([
    "@trilog.target",
    "define asked",
    "?- member(X, [a, g(1)]), _Hid = 1, Y = X.",
    "?- true.",
    "?- fail.",
    "endef",
    "",
  ]), "asked")
  assert r.returncode == 0, r.stdout + r.stderr
  assert [json.loads(l) for l in r.stdout.splitlines()] == [
    {"X": "a", "Y": "a"}, {"X": {"functor": "g", "args": [1]}, "Y": {"functor": "g", "args": [1]}}, {}], r.stdout + r.stderr


def test_the_engine_import_makes_a_workspace_from_a_define(amk, tmp_path):
  r = run(amk, tmp_path, "\n".join([
    "@trilog.import",
    "define kb",
    "parent(tom, bob).",
    "grandparent(G, C) :- parent(G, P), parent(P, C).",
    "endef",
    "x := $(kb.update assertz(parent(bob, ann)))",
    "shown:",
    "\t@echo '$(kb.get grandparent(tom, C))'",
    "",
  ]), "shown")
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == '{"C":"ann"}', r.stdout + r.stderr


def test_the_library_gives_each_namespace_a_findall_handle(amk, tmp_path):
  r = run(amk, tmp_path, "\n".join([
    "load trilog",
    "@trilog.import",
    "define kb",
    "edge(a, b).",
    "edge(a, c).",
    "edge3(a, b, x).",
    "endef",
    "shown:",
    "\t@echo '$(kb.findall edge, a) $(kb.findall edge3, a, b) $(trilog.findall kb, edge, z)'",
    "",
  ]), "shown")
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == '["b","c"] ["x"] []', r.stdout + r.stderr


def test_assertz_and_retract_handles_keep_their_change(amk, tmp_path):
  r = run(amk, tmp_path, "\n".join([
    "load trilog",
    "@trilog.import",
    "define kb",
    "edge(a, b).",
    "endef",
    "$(kb.assertz edge(a, c))",
    "$(kb.retract edge(a, b))",
    "shown:",
    "\t@echo '$(kb.findall edge, a)'",
    "",
  ]), "shown")
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == '["c"]', r.stdout + r.stderr


def test_rules_over_facts_see_an_update_at_once(amk, tmp_path):
  r = run(amk, tmp_path, "\n".join([
    "load trilog",
    "@trilog.import",
    "define family",
    "parent(tom, bob).",
    "parent(bob, ann).",
    "parent(bob, pat).",
    "grandparent(G, C) :- parent(G, P), parent(P, C).",
    "elder(C, G) :- grandparent(G, C).",
    "sibling(A, B) :- parent(P, A), parent(P, B), A \\= B.",
    "endef",
    "before := $(family.findall grandparent, tom)",
    "born := $(family.update assertz(parent(bob, sue)))",
    "shown:",
    "\t@echo '$(before) $(family.findall grandparent, tom) $(family.findall elder, ann) $(family.findall sibling, ann)'",
    "",
  ]), "shown")
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == '["ann","pat"] ["ann","pat","sue"] ["tom"] ["pat","sue"]', r.stdout + r.stderr


def test_a_deep_recursion_over_open_choicepoints_runs(amk, tmp_path):
  r = run(amk, tmp_path, "\n".join([
    "@trilog.target",
    "define found",
    "t(0).",
    "t(N) :- N > 0, M is N - 1, t(M).",
    "t(_).",
    ":- t(70000), write(ok), nl.",
    "endef",
    "",
  ]), "found")
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "ok", r.stdout + r.stderr


def test_nested_solves_do_not_grow_the_c_stack(amk, tmp_path):
  r = run(amk, tmp_path, "\n".join([
    "@trilog.target",
    "define found",
    "n(0, X) :- !, X = ok.",
    "n(D, X) :- E is D - 1, findall(Y, n(E, Y), [X]).",
    ":- n(200, X), write(X), nl.",
    "endef",
    "",
  ]), "found")
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "ok", r.stdout + r.stderr


def test_amk_expand_and_amk_call_reach_make(amk, tmp_path):
  r = run(amk, tmp_path, "\n".join([
    "x := 1 2 3",
    "@trilog.target",
    "define reached",
    ":- amk_expand('$(words $(x))', N), amk_call(subst, [' ', '-', 'a b c'], S), write(N/S), nl.",
    "endef",
    "",
  ]), "reached")
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "3/a-b-c", r.stdout + r.stderr


def test_amk_goal_answers_each_goals_outcome(amk, tmp_path):
  r = run(amk, tmp_path, jobs + "\n".join([
    "@trilog.target",
    "define acting",
    ":- amk_goal(ok, A), amk_goal(bad, B), write(A-B), nl.",
    "endef",
    "",
  ]), "acting")
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "success-failed", r.stdout + r.stderr


def test_a_job_mails_its_spawner(amk, tmp_path):
  r = run(amk, tmp_path, jobs + "\n".join([
    "@trilog.target",
    "define talker",
    ":- amk_send(hello).",
    "endef",
    "@trilog.target",
    "define listener",
    ":- amk_goal_spawn(talker, P), amk_job_wait(P, O, M), write(O/M), nl.",
    "endef",
    "",
  ]), "listener")
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "success/hello", r.stdout + r.stderr


def test_spawn_and_job_all_gather_in_order(amk, tmp_path):
  r = run(amk, tmp_path, jobs + "\n".join([
    "@trilog.target",
    "define gathered",
    ":- amk_goal_spawn(ok, P1), amk_goal_spawn(bad, P2), amk_job_all([P1, P2], Os), write(Os), nl.",
    "endef",
    "",
  ]), "gathered")
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "[success,failed]", r.stdout + r.stderr


def test_the_event_calculus_import_puts_the_axioms_ahead_of_the_define(amk, tmp_path):
  r = run(amk, tmp_path, "\n".join([
    "load trilog",
    "@trilog.import.event_calculus",
    "define lamp",
    "initially(off).",
    "initiates(flip, on, T) :- holdsAt(off, T).",
    "terminates(flip, off, T) :- holdsAt(off, T).",
    "happens(flip, 1).",
    "endef",
    "probe:",
    "\t@echo '$(strip $(lamp.get holdsAt(F, 1)))|$(strip $(lamp.get holdsAt(F, 2)))'",
    "",
  ]), "probe")
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == '{"F":"off"}|{"F":"on"}', r.stdout + r.stderr


def test_job_any_takes_the_first_and_job_stop_ends_the_rest(amk, tmp_path):
  r = run(amk, tmp_path, jobs + "\n".join([
    "@trilog.target",
    "define raced",
    ":- amk_goal_spawn(slow, S), amk_goal_spawn(ok, F), amk_job_any([S, F], W, O),",
    "   (W == F -> write(fast(O)) ; write(slow)), nl, amk_job_stop(S).",
    "endef",
    "",
  ]), "raced")
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "fast(success)", r.stdout + r.stderr

"""Pins the tuple space in `/zip/lib/tspace/init.amk` and its engine bindings.

An actual matches by type and value, a formal such as `?int` by type alone. Pinned are
each formal against a tuple of every type, the two refusals, inp taking once, the make
verbs, and each binding storing and matching its own language's types.
"""

import json
import sqlite3

import pytest

from conftest import sh

TYPES = ['k 7', 'k \'"7"\'', 'k 7.5', 'k true', 'k null', "k '[1]'", "k '{\"a\":1}'"]


def run(amk, tmp_path, body, *flags, timeout=120):
  mk = tmp_path / "space.mk"
  mk.write_text("SHELL := bash\nload tspace\n" + body + "\n")
  return sh(amk, ["-s", *flags, "-f", str(mk), "probe"], cwd=tmp_path, timeout=timeout)


def recipe(*lines):
  return "probe:\n" + "".join(f"\t@${{tspace.sh}} ; {line}\n" for line in lines)


def tuples(text):
  return [json.loads(line)["t"] for line in text.splitlines() if line.startswith('{"t"')]


@pytest.mark.engines("sqlite")
@pytest.mark.parametrize("formal,want", [
  ("?", [7, "7", 7.5, True, None, [1], {"a": 1}]),
  ("?int", [7]), ("?str", ["7"]), ("?float", [7.5]), ("?bool", [True]),
  ("?null", [None]), ("?list", [[1]]), ("?dict", [{"a": 1}]),
  ("?number", [7, 7.5]), ("?table", [[1], {"a": 1}]),
])
def test_each_formal_matches_its_type_only(amk, tmp_path, formal, want):
  r = run(amk, tmp_path, recipe(*[f"tspace out {t}" for t in TYPES], f"tspace read k '{formal}'"))
  assert r.returncode == 0, r.stdout + r.stderr
  assert [t[1] for t in tuples(r.stdout)] == want, r.stdout


@pytest.mark.engines("sqlite")
def test_an_actual_matches_type_and_value(amk, tmp_path):
  r = run(amk, tmp_path, recipe(*[f"tspace out {t}" for t in TYPES], "tspace read k 7", "tspace read k '\"7\"'"))
  assert r.returncode == 0, r.stdout + r.stderr
  assert tuples(r.stdout) == [["k", 7], ["k", "7"]], r.stdout


@pytest.mark.engines("sqlite")
def test_inp_takes_the_oldest_match_once(amk, tmp_path):
  r = run(amk, tmp_path, recipe("tspace out k 1", "tspace out k 2", "tspace inp k ?int", "tspace inp k ?int", "echo \"empty=[$$(tspace inp k ?int)]\""))
  assert r.returncode == 0, r.stdout + r.stderr
  assert tuples(r.stdout) == [["k", 1], ["k", 2]] and "empty=[]" in r.stdout, r.stdout


@pytest.mark.engines("sqlite")
@pytest.mark.parametrize("line,error", [("tspace out k ?int", "out takes actuals only"), ("tspace read k ?nope", "unknown formal")])
def test_a_misplaced_or_unknown_formal_is_refused(amk, tmp_path, line, error):
  r = run(amk, tmp_path, recipe(line))
  assert r.returncode != 0, r.stdout
  assert error in r.stderr, r.stderr


@pytest.mark.engines("sqlite")
def test_make_verbs_take_variadic_fields(amk, tmp_path):
  r = run(amk, tmp_path, "$(info $(tspace out, k, 1, one))\n$(info $(tspace read, k, ?int, ?str))\nprobe:\n\t@true")
  assert r.returncode == 0, r.stdout + r.stderr
  assert tuples(r.stdout) == [["k", 1, "one"]], r.stdout


@pytest.mark.engines("sqlite")
def test_make_verbs_trim_their_fields(amk, tmp_path):
  r = run(amk, tmp_path, "$(tspace out, k, 1, one)\n$(info $(tspace read, k, ?int, ?str))\nprobe:\n\t@true")
  assert r.returncode == 0, r.stdout + r.stderr
  assert tuples(r.stdout) == [["k", 1, "one"]], r.stdout


@pytest.mark.engines("sqlite")
def test_two_spaces_stay_disjoint(amk, tmp_path):
  r = run(amk, tmp_path, "\n".join([
    "$(tspace.create jobs)",
    "$(jobs.out k, 1)$(tspace out, k, 2)",
    "$(info $(jobs.read k, ?int))",
    "$(info $(tspace read, k, ?int))",
    "probe:\n\t@true",
  ]))
  assert r.returncode == 0, r.stdout + r.stderr
  assert tuples(r.stdout) == [["k", 1], ["k", 2]], r.stdout


@pytest.mark.engines("sqlite")
def test_a_recipe_reaches_a_space_by_its_handles(amk, tmp_path):
  r = run(amk, tmp_path, "$(tspace.create jobs)\n" + recipe("jobs.out k 1", "tspace out k 2", "jobs.inp k ?int", "echo \"empty=[$$(jobs.inp k ?int)]\""))
  assert r.returncode == 0, r.stdout + r.stderr
  assert tuples(r.stdout) == [["k", 1]], r.stdout
  assert "empty=[]" in r.stdout, r.stdout


@pytest.mark.engines("sqlite")
def test_an_owned_space_keeps_its_tuples_across_runs(amk, tmp_path):
  first = run(amk, tmp_path, "$(tspace.create jobs, owned=jobs.db)\n$(jobs.out k, 1)\nprobe:\n\t@true")
  assert first.returncode == 0, first.stdout + first.stderr
  second = run(amk, tmp_path, "$(tspace.create jobs, owned=jobs.db)\n$(info $(jobs.read k, ?int))\nprobe:\n\t@true")
  assert second.returncode == 0, second.stdout + second.stderr
  assert tuples(second.stdout) == [["k", 1]], second.stdout


SEEDED = '@tspace\ndefine shop\n{"seed": [["stock", "tea", 10], ["stock", "cake", 4]]}\nendef\n'


@pytest.mark.engines("sqlite")
def test_at_tspace_creates_a_space_and_writes_its_seed(amk, tmp_path):
  r = run(amk, tmp_path, SEEDED + "$(info $(shop.read stock, ?str, ?int))\nprobe:\n\t@true")
  assert r.returncode == 0, r.stdout + r.stderr
  assert tuples(r.stdout) == [["stock", "tea", 10], ["stock", "cake", 4]], r.stdout


@pytest.mark.engines("sqlite")
def test_an_empty_at_tspace_body_makes_an_empty_space(amk, tmp_path):
  r = run(amk, tmp_path, "@tspace\ndefine shop\nendef\n$(shop.out k, 1)\n$(info $(shop.read k, ?int))\nprobe:\n\t@true")
  assert r.returncode == 0, r.stdout + r.stderr
  assert tuples(r.stdout) == [["k", 1]], r.stdout


@pytest.mark.engines("sqlite")
def test_a_seed_is_written_only_by_the_create_that_makes_the_space(amk, tmp_path):
  body = '@tspace\ndefine jobs\n{"owned": "jobs.db", "seed": [["k", 1]]}\nendef\n'
  first = run(amk, tmp_path, body + "$(jobs.inp k, ?int)\nprobe:\n\t@true")
  assert first.returncode == 0, first.stdout + first.stderr
  second = run(amk, tmp_path, body + "$(info n=$(tspace.exec jobs, SELECT count(*) AS n FROM tspace))\nprobe:\n\t@true")
  assert second.returncode == 0, second.stdout + second.stderr
  assert 'n={"n":0}' in second.stdout, second.stdout


@pytest.mark.engines("sqlite")
def test_create_takes_a_seed_as_its_third_argument(amk, tmp_path):
  r = run(amk, tmp_path, '$(tspace.create jobs, , [["k", 1], ["k", 2]])\n$(info $(jobs.read k, ?int))\nprobe:\n\t@true')
  assert r.returncode == 0, r.stdout + r.stderr
  assert tuples(r.stdout) == [["k", 1], ["k", 2]], r.stdout


@pytest.mark.engines("sqlite")
def test_exec_runs_sql_against_a_space_and_keeps_its_commas(amk, tmp_path):
  r = run(amk, tmp_path, SEEDED + "$(info $(tspace.exec shop, SELECT count(*) AS n, 7 AS k FROM tspace))\nprobe:\n\t@true")
  assert r.returncode == 0, r.stdout + r.stderr
  assert '{"n":2,"k":7}' in r.stdout, r.stdout


@pytest.mark.engines("sqlite")
def test_at_tspace_target_runs_the_define_as_sql_on_the_default_space(amk, tmp_path):
  r = run(amk, tmp_path, "probe: tally\n\t@true\n$(tspace out, k, 1)\n$(tspace out, k, 2)\n"
    + "@tspace.target\ndefine tally\nSELECT count(*) AS n, 'a, b' AS s FROM tspace\nendef\n")
  assert r.returncode == 0, r.stdout + r.stderr
  assert '{"n":2,"s":"a, b"}' in r.stdout, r.stdout


@pytest.mark.engines("sqlite")
@pytest.mark.parametrize("body,error", [
  ("x := $(tspace.import shop, [])", "does not define tspace.import"),
  ("@tspace.import\ndefine shop\n[]\nendef", "does not define @tspace.import"),
])
def test_import_is_not_implemented(amk, tmp_path, body, error):
  r = run(amk, tmp_path, body + "\nprobe:\n\t@true")
  assert r.returncode != 0, r.stdout + r.stderr
  assert error in r.stderr, r.stderr


GUEST_TARGETS = {
  "lua": "  print(#shop.read('k', 'integer'))",
  "micropy": "  print(len(shop.read('k', int)))",
  "js": "  print(shop.read('k', Number.isInteger).length);",
  "s7": "  (display (length (shop 'read \"k\" integer?)))\n  (newline)",
}


@pytest.mark.engines("sqlite")
@pytest.mark.parametrize("engine", GUEST_TARGETS)
def test_a_space_guest_target_binds_the_space_by_name(amk, tmp_path, engine):
  r = run(amk, tmp_path, "$(tspace.create shop)\n$(shop.out k, 1)\n$(shop.out k, 2)\n"
    + f"@shop.{engine}.target\ndefine probe\n{GUEST_TARGETS[engine]}\nendef\n")
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip().splitlines()[-1] == "2", r.stdout


@pytest.mark.engines("sqlite")
def test_a_space_guest_target_takes_prerequisites(amk, tmp_path):
  r = run(amk, tmp_path, "$(tspace.create shop)\nfill:\n\t@${tspace.sh} ; shop.out k 1\n"
    + "@shop.micropy.target: fill\ndefine probe\n  print(len(shop.read('k', int)))\nendef\n")
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip().splitlines()[-1] == "1", r.stdout


@pytest.mark.engines("sqlite")
def test_a_space_guest_import_lifts_functions_that_use_the_space(amk, tmp_path):
  r = run(amk, tmp_path, "$(tspace.create shop)\n$(shop.out k, 1)\n"
    + "@shop.lua\ndefine lib\n  function stock(name) return #shop.read(name, 'integer') end\nendef\n"
    + "$(info n=$(stock k))\nprobe:\n\t@true")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "n=1" in r.stdout, r.stdout


@pytest.mark.engines("sqlite")
def test_tspace_registers_as_a_data_stacked_engine(amk, tmp_path):
  r = run(amk, tmp_path, "$(tspace.create shop)\n"
    + "$(info data=$(amk.data.engines) stacked=$(amk.stacked.engines) reflex=$(filter tspace,$(tspace.reflexes)))\nprobe:\n\t@true")
  assert r.returncode == 0, r.stdout + r.stderr
  line = next(l for l in r.stdout.splitlines() if l.startswith("data="))
  assert "tspace" in line.split("stacked=")[0] and "tspace" in line.split("stacked=")[1] and line.endswith("reflex="), line


@pytest.mark.engines("sqlite")
def test_two_owners_of_a_shared_space_take_each_tuple_once(amk, tmp_path):
  seed = run(amk, tmp_path, "$(tspace.create jobs, shared=jobs.db)\n$(foreach n,$(shell seq 1 40),$(jobs.out job, $(n)))\nprobe:\n\t@true")
  assert seed.returncode == 0, seed.stdout + seed.stderr
  take = tmp_path / "take.mk"
  take.write_text("SHELL := bash\nload tspace\n$(tspace.create jobs, shared=jobs.db)\n"
                  + recipe("while r=$$(jobs.inp job ?int) && [ -n \"$$r\" ]; do echo \"$$r\"; done"))
  r = sh("sh", ["-c", f"{amk} -s -f {take} probe > a.out & {amk} -s -f {take} probe > b.out & wait"], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  taken = tuples((tmp_path / "a.out").read_text()) + tuples((tmp_path / "b.out").read_text())
  assert sorted(t[1] for t in taken) == list(range(1, 41)), taken


@pytest.mark.engines("sqlite")
def test_a_read_does_not_wait_on_another_owners_write_lock(amk, tmp_path):
  seed = run(amk, tmp_path, "$(tspace.create jobs, shared=jobs.db)\n$(jobs.out k, 1)\nprobe:\n\t@true")
  assert seed.returncode == 0, seed.stdout + seed.stderr
  holder = sqlite3.connect(tmp_path / "jobs.db", isolation_level=None)
  holder.execute("BEGIN IMMEDIATE")
  try:
    r = run(amk, tmp_path, "$(tspace.create jobs, shared=jobs.db)\n$(info $(jobs.read k, ?int))\nprobe:\n\t@true")
  finally:
    holder.execute("ROLLBACK")
    holder.close()
  assert r.returncode == 0, r.stdout + r.stderr
  assert tuples(r.stdout) == [["k", 1]], r.stdout


FEED = "feed:\n\t@${tspace.sh} ; sleep 0.3 ; tspace inp k 0 ; sleep 0.3 ; tspace out k 1\n"


@pytest.mark.engines("sqlite")
def test_recipe_blocking_verbs_wait_on_another_recipe(amk, tmp_path):
  wait = "wait:\n\t@${tspace.sh} ; tspace no k 0 && echo gone ; tspace rd k 1 ; tspace in k 1 ; echo \"left=[$$(tspace inp k ?int)]\"\n"
  r = run(amk, tmp_path, "$(tspace out, k, 0)\nprobe: wait feed\n\t@true\n" + wait + FEED, "-j2")
  assert r.returncode == 0, r.stdout + r.stderr
  assert tuples(r.stdout) == [["k", 0], ["k", 1], ["k", 1]], r.stdout
  assert "gone" in r.stdout and "left=[]" in r.stdout, r.stdout


@pytest.mark.engines("sqlite")
def test_a_version_moves_on_a_change_and_a_wait_answers_past_it(amk, tmp_path):
  lines = [
    "v0=$$(amk.ns version tuplespace)",
    "tspace inp k ?int",
    "v1=$$(amk.ns version tuplespace)",
    "tspace out k 1",
    "v2=$$(amk.ns version tuplespace)",
    "w=$$(amk.ns wait tuplespace -- $$v1)",
    "echo \"v=[$$v0 $$v1 $$v2 $$w]\"",
  ]
  r = run(amk, tmp_path, "probe:\n\t@${tspace.sh} ; " + " ; ".join(lines) + "\n")
  assert r.returncode == 0, r.stdout + r.stderr
  v0, v1, v2, w = (int(x) for x in r.stdout.strip()[3:-1].split())
  assert (v1, v2, w) == (v0, v0 + 1, v0 + 1), r.stdout


@pytest.mark.engines("sqlite")
def test_two_waiters_on_one_pattern_are_answered_one_each(amk, tmp_path):
  waiter = "{0}:\n\t@${{tspace.sh}} ; r=$$(tspace in k ?int) ; echo \"{0} took $$r\"\n"
  feed = "feed:\n\t@${tspace.sh} ; sleep 0.3 ; tspace out k 1 ; sleep 0.3 ; tspace out k 2\n"
  r = run(amk, tmp_path, "probe: a b feed\n\t@true\n" + waiter.format("a") + waiter.format("b") + feed, "-j3")
  assert r.returncode == 0, r.stdout + r.stderr
  took = sorted(line.split(" took ") for line in r.stdout.splitlines() if " took " in line)
  assert [who for who, _ in took] == ["a", "b"], r.stdout
  assert sorted(json.loads(t)["t"][1] for _, t in took) == [1, 2], r.stdout


@pytest.mark.engines("sqlite", "lua")
def test_a_waiter_ends_when_its_owner_exits(amk, tmp_path):
  body = "\n".join([
    "seed := $(lua.exec)",
    "probe:",
    "\t@echo spawned=$(lua.exec print(amk.spawn('waiter')))",
    "waiter:",
    "\t@${tspace.sh} ; tspace in never ?int ; echo \"status=$$?\"",
  ])
  r = run(amk, tmp_path, body)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "spawned=" in r.stdout, r.stdout


@pytest.mark.engines("sqlite")
@pytest.mark.parametrize("depth", [1, 2])
def test_recipes_under_sub_makes_wait_and_out_through_the_forwarder(amk, tmp_path, depth):
  body = "\n".join([
    "probe:",
    "\t@$(MAKE) -s -j2 -f $(firstword $(MAKEFILE_LIST)) " + ("pair" if depth == 1 else "middle"),
    "middle:",
    "\t@$(MAKE) -s -j2 -f $(firstword $(MAKEFILE_LIST)) pair",
    "pair: waiter feeder",
    "waiter:",
    "\t@${tspace.sh} ; tspace in k ?int ; echo \"seen=$$(amk.ns version tuplespace)\"",
    "feeder:",
    "\t@${tspace.sh} ; sleep 0.3 ; tspace out k 1",
  ])
  r = run(amk, tmp_path, body, timeout=20)
  assert r.returncode == 0, r.stdout + r.stderr
  assert tuples(r.stdout) == [["k", 1]], r.stdout
  assert "seen=" in r.stdout and "seen=\n" not in r.stdout, r.stdout


@pytest.mark.engines("sqlite")
def test_a_restarted_consumer_takes_each_tuple_once_and_in_order(amk, tmp_path):
  body = "\n".join([
    "probe:",
    "\t@${tspace.sh} ; for n in 1 2 3 4; do tspace out k $$n; done ; tspace out armed 1 ;"
    " until $(MAKE) -s -f $(firstword $(MAKEFILE_LIST)) consume; do echo restarted; done ;"
    " echo \"left=[$$(tspace inp k ?int)]\"",
    "consume:",
    "\t@${tspace.sh} ; while t=$$(tspace inp k ?int) && [ -n \"$$t\" ]; do echo \"$$t\" ;"
    " if [ -n \"$$(tspace inp armed ?int)\" ]; then exit 1; fi ; done",
  ])
  r = run(amk, tmp_path, body, timeout=20)
  assert r.returncode == 0, r.stdout + r.stderr
  assert tuples(r.stdout) == [["k", 1], ["k", 2], ["k", 3], ["k", 4]], r.stdout
  assert r.stdout.count("restarted") == 1 and "left=[]" in r.stdout, r.stdout


@pytest.mark.engines("sqlite")
def test_a_parked_verb_in_the_owner_is_refused(amk, tmp_path):
  r = run(amk, tmp_path, "$(info $(tspace in, never, ?int))\nprobe:\n\t@true")
  assert r.returncode != 0, r.stdout
  assert "would wait on itself" in r.stderr, r.stderr


@pytest.mark.engines("sqlite")
def test_the_one_shot_and_bulk_verbs(amk, tmp_path):
  r = run(amk, tmp_path, recipe(
    "tspace nop k ?int && echo empty",
    "tspace out_all '[\"k\", 1]' '[\"k\", 2]' '[\"j\", 3]'",
    "tspace rdp k ?int",
    "tspace nop k ?int || echo taken",
    "echo \"all=$$(tspace all | wc -l | tr -d ' ')\"",
    "tspace in_all k ?int",
    "echo \"left=$$(tspace all)\"",
    "tspace set '[\"m\", 9]'",
    "tspace all",
  ))
  assert r.returncode == 0, r.stdout + r.stderr
  assert tuples(r.stdout) == [["k", 1], ["k", 1], ["k", 2], ["m", 9]], r.stdout
  assert "empty" in r.stdout and "taken" in r.stdout and "all=3" in r.stdout, r.stdout
  assert 'left={"t":["j",3]}' in r.stdout, r.stdout


@pytest.mark.engines("sqlite")
def test_the_uniform_verbs_take_one_random_match(amk, tmp_path):
  r = run(amk, tmp_path, recipe(
    *[f"tspace out k {n}" for n in range(1, 6)],
    "tspace urdp k ?int",
    "tspace uinp k ?int",
    "tspace uinp k ?int",
    "echo \"left=$$(tspace read k ?int | wc -l | tr -d ' ')\"",
    "echo \"none=[$$(tspace uinp j ?int)]\"",
  ))
  assert r.returncode == 0, r.stdout + r.stderr
  got = tuples(r.stdout)
  assert len(got) == 3 and all(1 <= t[1] <= 5 for t in got) and got[1] != got[2], r.stdout
  assert "left=3" in r.stdout and "none=[]" in r.stdout, r.stdout


@pytest.mark.engines("sqlite")
def test_uin_waits_then_takes(amk, tmp_path):
  wait = "wait:\n\t@${tspace.sh} ; tspace uin k ?int\n"
  r = run(amk, tmp_path, "probe: wait feed\n\t@true\n" + wait + FEED, "-j2")
  assert r.returncode == 0, r.stdout + r.stderr
  assert tuples(r.stdout) == [["k", 1]], r.stdout


def handler(name, pattern, body):
  return f"@amk.fxn!\ndefine {name}\n{body}\nendef\n$(tspace out_s, {name}, {pattern})\n"


@pytest.mark.engines("sqlite", "lua")
def test_a_handler_is_called_once_per_matching_out_from_make_a_recipe_and_a_guest(amk, tmp_path):
  r = run(amk, tmp_path, handler("on_k", "k, ?", "$(tspace out, got, $(2))")
    + "$(tspace out, k, 1)\n"
    + "@lua.target\ndefine fromlua\n  amk.tspace.out('k', 3)\nendef\n"
    + "probe: fromlua\n\t@${tspace.sh} ; tspace out k 2 ; tspace out j 9 ; tspace rdp k ? ; tspace read got ? ; tspace read j ?\n")
  assert r.returncode == 0, r.stdout + r.stderr
  got = tuples(r.stdout)
  assert sorted(t[1] for t in got if t[0] == "got") == [1, 2, 3], r.stdout
  assert [t for t in got if t[0] != "got"] == [["j", 9]], r.stdout


REFLEX = {
  "lua": "  local function twice(n) return n * 2 end\n  shop.out('got', item, twice(qty), flag, note)",
  "js": "  const twice = n => n * 2;\n  shop.out('got', item, twice(qty), flag, note);",
  "micropy": "  def twice(n):\n      return n * 2\n  shop.out('got', item, twice(qty), flag, note)",
  "s7": "  (define (twice n) (* n 2))\n  (shop 'out \"got\" item (twice qty) flag note)",
}


@pytest.mark.parametrize("engine", sorted(REFLEX))
def test_a_reflex_names_and_types_its_fields_and_binds_its_space(amk, engines, tmp_path, engine):
  if "sqlite" not in engines or engine not in engines:
    pytest.skip(f"this amk carries no sqlite or {engine}")
  r = run(amk, tmp_path, "$(tspace.create shop)\n"
    + f"@shop.reflex {engine} order item=str _ qty=int flag=bool note=\ndefine price\n{REFLEX[engine]}\nendef\n"
    + "$(info helper=[$(twice 3)])\n"
    + "probe:\n\t@${tspace.sh} ; shop.out order tea x 4 true hi ; shop.rd_s ; shop.all\n")
  assert r.returncode == 0, r.stdout + r.stderr
  assert tuples(r.stdout) == [
    ["price", ["order", "?str", "?", "?int", "?bool", "?any"]],
    ["got", "tea", 8, True, "hi"],
  ], r.stdout
  assert "helper=[]" in r.stdout, r.stdout


@pytest.mark.engines("sqlite")
def test_any_matches_every_type(amk, tmp_path):
  r = run(amk, tmp_path, recipe(*[f"tspace out {t}" for t in TYPES], "tspace read k ?any"))
  assert r.returncode == 0, r.stdout + r.stderr
  assert [t[1] for t in tuples(r.stdout)] == [7, "7", 7.5, True, None, [1], {"a": 1}], r.stdout


@pytest.mark.engines("sqlite", "lua", "awk")
@pytest.mark.parametrize("at,error", [
  ("@shop.reflex awk k n=int", "awk cannot compile a reflex"),
  ("@shop.reflex lua k n=float32", "float32 is not a type"),
  ("@shop.reflex lua k shop=int", "a field cannot be named after its space"),
  ("@shop.reflex lua k n=int n=str", "a field name is used twice"),
  ("@shop.reflex", "body: @shop.reflex needs an engine"),
])
def test_a_reflex_refuses_what_it_cannot_compile(amk, tmp_path, at, error):
  r = run(amk, tmp_path, f"$(tspace.create shop)\n{at}\ndefine body\n  print(1)\nendef\nprobe:\n\t@true\n")
  assert r.returncode != 0, r.stdout + r.stderr
  assert error in r.stderr, r.stderr


@pytest.mark.engines("sqlite")
def test_a_tuple_takes_a_quoted_literal_with_a_space(amk, tmp_path):
  r = run(amk, tmp_path, "$(tspace.create shop)\n@shop.reflex amk (\"big order\", n=int)\ndefine seen\n$(info seen: $(2))\nendef\n"
    + "$(shop.out big order, 7)\n$(shop.out big, 7)\nprobe:\n\t@${tspace.sh} ; shop.rd_s\n")
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.count("seen: 7") == 1, r.stdout
  assert tuples(r.stdout) == [["seen", ["big order", "?int"]]], r.stdout


@pytest.mark.engines("sqlite")
def test_a_reflex_in_amk_makes_the_define_a_handler_taking_the_tuple_by_position(amk, tmp_path):
  r = run(amk, tmp_path, "$(tspace.create shop)\n@shop.reflex amk k n=int\ndefine seen\n$(info seen: $(2))\nendef\n"
    + "$(shop.out k, 7)\n$(shop.out k, no)\nprobe:\n\t@${tspace.sh} ; shop.rd_s\n")
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.count("seen: 7") == 1 and "seen: no" not in r.stdout, r.stdout
  assert tuples(r.stdout) == [["seen", ["k", "?int"]]], r.stdout


def two_reflexes(first, second):
  return ("$(tspace.create shop)\n"
    + f"@shop.reflex lua {first}\ndefine one\n  shop.out('x')\nendef\n"
    + f"@shop.reflex lua {second}\ndefine two\n  shop.out('x')\nendef\n"
    + "probe:\n\t@${tspace.sh} ; shop.rd_s\n")


@pytest.mark.engines("sqlite", "lua")
@pytest.mark.parametrize("first,second,overlap", [
  ("k n=int", "k n=int", True),
  ("k _", "k n=int", True),
  ("k n=number", "k n=int", True),
  ("k n=int", "k 1", True),
  ("k n=int", "k n=str", False),
  ("k n=int", "j n=int", False),
  ("k n=int", "k n=int m=int", False),
])
def test_a_handler_whose_pattern_overlaps_another_is_refused(amk, tmp_path, first, second, overlap):
  r = run(amk, tmp_path, two_reflexes(first, second))
  if overlap:
    assert r.returncode != 0 and "overlaps" in r.stderr, r.stdout + r.stderr
  else:
    assert r.returncode == 0, r.stdout + r.stderr
    assert [t[0] for t in tuples(r.stdout)] == ["one", "two"], r.stdout


REACT = (
  '@tspace\ndefine shop\n  { "seed": [["k", 1], ["j", 9], ["k", 2]] }\nendef\n'
  "@shop.reflex lua (k, n=int)\ndefine seen\n  print('seen ' .. n)\nendef\n")


@pytest.mark.engines("sqlite", "lua", "jq")
def test_a_spaces_main_target_routes_its_stored_tuples_through_its_reflexes_in_order(amk, tmp_path):
  r = run(amk, tmp_path, REACT + "probe: shop.__main__\n\t@${tspace.sh} ; shop.all\n")
  assert r.returncode == 0, r.stdout + r.stderr
  out = r.stdout + r.stderr
  assert [l for l in out.splitlines() if l.startswith("seen")] == ["seen 1", "seen 2"], out
  assert tuples(r.stdout) == [["j", 9]], r.stdout


@pytest.mark.engines("sqlite", "lua", "jq")
def test_react_with_nothing_stored_for_a_reflex_routes_nothing(amk, tmp_path):
  r = run(amk, tmp_path, REACT + "$(shop.react )\n$(shop.react )\nprobe:\n\t@${tspace.sh} ; shop.react ; shop.all\n")
  assert r.returncode == 0, r.stdout + r.stderr
  out = r.stdout + r.stderr
  assert [l for l in out.splitlines() if l.startswith("seen")] == ["seen 1", "seen 2"], out
  assert tuples(r.stdout) == [["j", 9]], r.stdout


def two_on_one_pattern(space):
  return (space
    + "@shop.reflex lua k n=int\ndefine one\n  print('one ' .. n)\nendef\n"
    + "@shop.reflex lua k n=int\ndefine two\n  print('two ' .. n)\nendef\n"
    + "$(shop.out k, 7)\nprobe:\n\t@true\n")


@pytest.mark.engines("sqlite", "lua", "jq")
@pytest.mark.parametrize("space", [
  '@tspace\ndefine shop\n  { "strategy": { "reflexes": "shared" } }\nendef\n',
  "$(tspace.create shop, reflexes=shared)\n",
])
def test_a_shared_space_lets_reflexes_overlap_and_each_fires_in_order(amk, tmp_path, space):
  r = run(amk, tmp_path, two_on_one_pattern(space))
  assert r.returncode == 0, r.stdout + r.stderr
  out = r.stdout + r.stderr
  assert [l for l in out.splitlines() if l.startswith(("one", "two"))] == ["one 7", "two 7"], out


@pytest.mark.engines("sqlite", "lua", "jq")
@pytest.mark.parametrize("space,error", [
  ("$(tspace.create shop)\n", "overlaps"),
  ("$(tspace.create shop, reflexes=exclusive)\n", "overlaps"),
  ("$(tspace.create shop, reflexes=maybe)\n", "shop: reflexes is exclusive or shared, not maybe"),
  ('@tspace\ndefine shop\n  { "strategy": { "pick": "random" } }\nendef\n', "shop: does not meet schema/tspace.json: Property strategy: Additional property 'pick' not allowed"),
])
def test_an_exclusive_space_refuses_overlap_and_a_strategy_is_a_closed_vocabulary(amk, tmp_path, space, error):
  r = run(amk, tmp_path, two_on_one_pattern(space))
  assert r.returncode != 0, r.stdout
  assert error in r.stderr, r.stderr


@pytest.mark.engines("sqlite", "lua")
def test_the_refusal_names_both_at_lines_a_witness_and_the_fields(amk, tmp_path):
  r = run(amk, tmp_path, two_reflexes("k n=int", "k n=number"))
  mk = str(tmp_path / "space.mk")
  assert r.returncode != 0, r.stdout + r.stderr
  for line in [
    f"{mk}:8: @shop.reflex lua k n=number",
    f"overlaps {mk}:4: @shop.reflex lua k n=int",
    'on the space shop: both patterns match ["k",1].',
    "field 2: n=number and n=int share integers",
    "A handler is the only destination of the tuples it matches",
  ]:
    assert line in r.stderr, r.stderr


@pytest.mark.engines("sqlite")
def test_a_name_registered_again_replaces_itself_without_refusal(amk, tmp_path):
  r = run(amk, tmp_path, "$(tspace out_s, h, k, ?int)\n$(tspace out_s, h, k, ?int)\n$(tspace out_s, h, k, ?str)\n"
    + recipe("tspace rd_s"))
  assert r.returncode == 0 and "overlaps" not in r.stderr, r.stdout + r.stderr
  assert tuples(r.stdout) == [["h", ["k", "?str"]]], r.stdout


@pytest.mark.engines("sqlite")
def test_a_raw_out_s_overlap_is_refused_and_named_by_its_caller(amk, tmp_path):
  r = run(amk, tmp_path, "$(tspace out_s, a, k, ?int)\n$(tspace out_s, b, k, ?)\n" + recipe("tspace rd_s"))
  assert r.returncode != 0, r.stdout + r.stderr
  assert "out_s b" in r.stderr and "the handler a, registered by out_s" in r.stderr, r.stderr
  assert "space.mk:4: ***" in r.stderr and tuples(r.stdout) == [], r.stdout + r.stderr


@pytest.mark.engines("sqlite")
def test_a_handler_that_routes_to_itself_stops_at_the_depth_bound(amk, tmp_path):
  r = run(amk, tmp_path, handler("again", "k, ?", "$(tspace out, k, $(2))") + recipe("tspace out k 1"))
  assert r.returncode != 0, r.stdout + r.stderr
  assert "handler again: routed more than 100 deep" in r.stderr, r.stderr


VERBS = {
  "lua": "@lua.target\ndefine bound\n  local ts = amk.tspace\n  ts.out_all({'k', 1}, {'k', 2})\n  print(ts.nop('j', 'integer'), ts.rdp('k', 'integer')[2], #ts.all(), ts.uinp('k', 'integer')[1], #ts.in_all('k', 'integer'), ts.nop('k', 'integer'))\nendef",
  "micropy": "@micropy.target\ndefine bound\n  from amk import tspace as ts\n  ts.out_all(['k', 1], ['k', 2])\n  print(ts.nop('j', int), ts.rdp('k', int)[1], len(ts.all()), ts.uinp('k', int)[0], len(ts.in_all('k', int)), ts.nop('k', int))\nendef",
  "js": "@js.target\ndefine bound\n  const ts = amk.tspace;\n  ts.out_all(['k', 1], ['k', 2]);\n  print(ts.nop('j', Number.isInteger), ts.rdp('k', Number.isInteger)[1], ts.all().length, ts.uinp('k', Number.isInteger)[0], ts.in_all('k', Number.isInteger).length, ts.nop('k', Number.isInteger));\nendef",
  "s7": "@s7.target\ndefine bound\n  (define ts (amk-tspace-on \"tuplespace\"))\n  (ts 'out_all #(\"k\" 1) #(\"k\" 2))\n  (format #t \"~A ~A ~A ~A ~A ~A~%\" (ts 'nop \"j\" integer?) (cadr (ts 'rdp \"k\" integer?)) (length (ts 'all)) (car (ts 'uinp \"k\" integer?)) (length (ts 'in_all \"k\" integer?)) (ts 'nop \"k\" integer?))\nendef",
}


@pytest.mark.parametrize("engine", sorted(VERBS))
def test_a_binding_has_the_one_shot_and_bulk_verbs(amk, engines, tmp_path, engine):
  if "sqlite" not in engines or engine not in engines:
    pytest.skip(f"this amk carries no sqlite or {engine}")
  r = run(amk, tmp_path, VERBS[engine] + "\nprobe: bound\n\t@true")
  assert r.returncode == 0, r.stdout + r.stderr
  words = [{"#t": "true", "#f": "false"}.get(w, w.lower()) for w in r.stdout.split()]
  assert words == ["true", "1", "2", "k", "1", "true"], r.stdout


BLOCKING = {
  "lua": "@lua.target\ndefine bound\n  print(amk.tspace.in_('k', 1)[2])\nendef",
  "micropy": "@micropy.target\ndefine bound\n  from amk import tspace\n  print(tspace.in_('k', 1)[1])\nendef",
  "js": "@js.target\ndefine bound\n  os.setTimeout(() => print('tick'), 100);\n  print((await amk.tspace.in('k', 1))[1]);\nendef",
  "s7": "@s7.target\ndefine bound\n  (format #t \"~A~%\" (cadr (amk-tspace-in \"k\" 1)))\nendef",
}


@pytest.mark.parametrize("engine", sorted(BLOCKING))
def test_a_binding_blocks_in_until_a_later_out(amk, engines, tmp_path, engine):
  if "sqlite" not in engines or engine not in engines:
    pytest.skip(f"this amk carries no sqlite or {engine}")
  r = run(amk, tmp_path, "$(tspace out, k, 0)\n" + BLOCKING[engine] + "\nprobe: bound feed\n\t@true\n" + FEED, "-j2")
  assert r.returncode == 0, r.stdout + r.stderr
  lines = [line.split() for line in r.stdout.splitlines() if line.strip() and not line.startswith('{"t"')]
  assert lines == ([["tick"], ["1"]] if engine == "js" else [["1"]]), r.stdout


INDEXED = {
  "lua": "@lua.target\ndefine bound\n  local j = amk.tspace['jobs']\n  j.out('k', 1)\n  amk.tspace['jobs'].out('k', 2)\n  print(#j['tuplespace'].read('k', 'integer'), #amk.tspace.on('jobs').read('k', 'integer'), j.on == amk.tspace.on)\nendef",
  "micropy": "@micropy.target\ndefine bound\n  from amk import tspace\n  j = tspace['jobs']\n  j.out('k', 1)\n  tspace['jobs'].out('k', 2)\n  print(len(j['tuplespace'].read('k', int)), len(tspace.on('jobs').read('k', int)), j.on is tspace.on)\nendef",
  "js": "@js.target\ndefine bound\n  const j = amk.tspace['jobs'];\n  j.out('k', 1);\n  amk.tspace['jobs'].out('k', 2);\n  print(j['tuplespace'].read('k', Number.isInteger).length, amk.tspace.on('jobs').read('k', Number.isInteger).length, j.on === amk.tspace.on);\nendef",
}


@pytest.mark.parametrize("engine", sorted(INDEXED))
def test_a_binding_indexes_a_named_space(amk, engines, tmp_path, engine):
  if "sqlite" not in engines or engine not in engines:
    pytest.skip(f"this amk carries no sqlite or {engine}")
  r = run(amk, tmp_path, "$(tspace.create jobs)\n" + INDEXED[engine] + "\nprobe: bound\n\t@true")
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.split() == ["0", "2", "true"] or r.stdout.split() == ["0", "2", "True"], r.stdout


CHAINED = {
  "lua": "$(info [$(lua.exec amk.tspace.create('made'); print(amk.tspace.version('made'), type(amk.tspace.nope.read), amk.tspace['made'].version('made')))])",
  "micropy": "$(info [$(micropy.exec from amk import tspace; tspace.create('made'); print(tspace.version('made'), hasattr(tspace, 'nope'), tspace['made'].version('made')))])",
  "js": "$(info [$(js.exec amk.tspace.create('made'); print(amk.tspace.version('made'), typeof amk.tspace.nope.read, amk.tspace['made'].version('made')))])",
}


@pytest.mark.parametrize("engine", sorted(CHAINED))
def test_a_handle_stands_a_missing_field_for_the_make_function_under_tspace(amk, engines, tmp_path, engine):
  if "sqlite" not in engines or engine not in engines:
    pytest.skip(f"this amk carries no sqlite or {engine}")
  r = run(amk, tmp_path, CHAINED[engine] + "\nprobe:\n\t@true")
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.split() in (["[1", "function", "1]"], ["[1", "False", "1]"]), r.stdout


@pytest.mark.engines("sqlite", "micropy", "jq")
def test_a_space_a_forwarder_creates_is_claimed_for_its_engine_in_the_owner(amk, tmp_path):
  body = "\n".join([
    "@micropy.target",
    "define made",
    "  from amk import tspace",
    "  tspace.create('later')",
    "  tspace['later'].out('k', 2)",
    "  print('child:', tspace['later'].read('k', int))",
    "endef",
    "probe: made",
    "\t@${tspace.sh} ; echo \"owner: $$(amk.ns get later -- 'SELECT count(*) AS n FROM tspace')\"",
  ])
  r = run(amk, tmp_path, body)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "child: [['k', 2]]" in r.stdout and 'owner: {"n":1}' in r.stdout, r.stdout + r.stderr


UNLOADED = {
  "lua": "$(lua.exec print(amk.tspace))",
  "micropy": "$(micropy.exec from amk import tspace)",
  "js": "$(js.exec amk.tspace)",
  "s7": "$(s7.exec (amk-tspace-out \"k\" 1))",
}


@pytest.mark.parametrize("engine", sorted(UNLOADED))
def test_a_binding_names_the_missing_load_when_make_has_no_space(amk, engines, tmp_path, engine):
  if "sqlite" not in engines or engine not in engines:
    pytest.skip(f"this amk carries no sqlite or {engine}")
  mk = tmp_path / "bare.mk"
  mk.write_text(f"SHELL := bash\n$(amk.require sqlite, {engine})\n{UNLOADED[engine]}\nprobe:\n\t@true\n")
  r = sh(amk, ["-s", "-f", str(mk), "probe"], cwd=tmp_path, timeout=120)
  assert r.returncode != 0, r.stdout + r.stderr
  assert "amk.tspace: the makefile has no tuple space; add load tspace" in r.stderr, r.stderr


SPACES = {
  "lua": "@lua.target\ndefine bound\n  local j = amk.tspace.on('jobs')\n  j.out('k', 1)\n  print(#amk.tspace.read('k', 'integer'), #j.read('k', 'integer'))\nendef",
  "micropy": "@micropy.target\ndefine bound\n  from amk import tspace\n  j = tspace.on('jobs')\n  j.out('k', 1)\n  print(len(tspace.read('k', int)), len(j.read('k', int)))\nendef",
  "js": "@js.target\ndefine bound\n  const j = amk.tspace.on('jobs');\n  j.out('k', 1);\n  print(amk.tspace.read('k', Number.isInteger).length, j.read('k', Number.isInteger).length);\nendef",
  "s7": "@s7.target\ndefine bound\n  (define j (amk-tspace-on \"jobs\"))\n  (j 'out \"k\" 1)\n  (format #t \"~A ~A~%\" (length (amk-tspace-read \"k\" integer?)) (length (j 'read \"k\" integer?)))\nendef",
}


@pytest.mark.parametrize("engine", sorted(SPACES))
def test_a_binding_reaches_a_named_space(amk, engines, tmp_path, engine):
  if "sqlite" not in engines or engine not in engines:
    pytest.skip(f"this amk carries no sqlite or {engine}")
  r = run(amk, tmp_path, "$(tspace.create jobs)\n" + SPACES[engine] + "\nprobe: bound\n\t@true")
  assert r.returncode == 0, r.stdout + r.stderr
  assert [line.split() for line in r.stdout.splitlines() if line.strip()] == [["0", "1"]], r.stdout


BINDINGS = {
  "lua": "\n".join([
    "@lua.target",
    "define bound",
    "  local ts = amk.tspace",
    "  ts.out('k', 1, 1.5, 'integer', true, nil)",
    "  print(#ts.read('k', 'integer', 'float', 'string', 'boolean', 'nil'), #ts.read('k', 'number', 'number', 'integer', 'any', 'any'))",
    "  print(ts.inp('k', 'any', 'any', 'any', 'any', 'any') ~= nil, ts.inp('k', 'any', 'any', 'any', 'any', 'any') == nil)",
    "endef",
  ]),
  "micropy": "\n".join([
    "@micropy.target",
    "define bound",
    "  from amk import tspace",
    "  tspace.out('k', 1, 1.5, '7', True, None)",
    "  print(len(tspace.read('k', int, float, str, bool, type(None))), len(tspace.read('k', (int, float), (int, float), int, object, object)))",
    "  print(tspace.inp('k', object, object, object, object, object) is not None, tspace.inp('k', object, object, object, object, object) is None)",
    "endef",
  ]),
  "js": "\n".join([
    "@js.target",
    "define bound",
    "  const ts = amk.tspace;",
    "  ts.out('k', 1, 1.5, '7', true, null);",
    "  print(ts.read('k', Number.isInteger, Number, String, Boolean, null).length, ts.read('k', Number, Number.isInteger, undefined, undefined, undefined).length);",
    "  print(ts.inp('k', undefined, undefined, undefined, undefined, undefined) !== null, ts.inp('k', undefined, undefined, undefined, undefined, undefined) === null);",
    "endef",
  ]),
  "s7": "\n".join([
    "@s7.target",
    "define bound",
    "  (define (yes x) (if x \"true\" \"false\"))",
    "  (amk-tspace-out \"k\" 1 1.5 \"7\" #t 'null)",
    "  (format #t \"~A ~A~%\" (length (amk-tspace-read \"k\" integer? float? string? boolean? amk-tspace-null?)) (length (amk-tspace-read \"k\" real? real? integer? amk-tspace-any amk-tspace-any)))",
    "  (format #t \"~A ~A~%\" (yes (amk-tspace-inp \"k\" amk-tspace-any amk-tspace-any amk-tspace-any amk-tspace-any amk-tspace-any)) (yes (not (amk-tspace-inp \"k\" amk-tspace-any amk-tspace-any amk-tspace-any amk-tspace-any amk-tspace-any))))",
    "endef",
  ]),
}


@pytest.mark.parametrize("engine", sorted(BINDINGS))
def test_a_binding_keeps_native_types(amk, engines, tmp_path, engine):
  if "sqlite" not in engines or engine not in engines:
    pytest.skip(f"this amk carries no sqlite or {engine}")
  r = run(amk, tmp_path, BINDINGS[engine] + "\nprobe: bound\n\t@true")
  assert r.returncode == 0, r.stdout + r.stderr
  lines = [line.lower().split() for line in r.stdout.splitlines() if line.strip()]
  assert lines == [["1", "0"], ["true", "true"]], r.stdout


MISSES = {
  "js": "$(js.exec print(amk.nope === undefined))",
  "lua": "$(lua.exec print(amk.nope == nil))",
  "micropy": "$(micropy.exec import amk; print(not hasattr(amk, 'nope')))",
  "s7": "$(s7.exec (display (catch #t (lambda () amk-nope-x \"false\") (lambda args \"true\"))))",
}


@pytest.mark.parametrize("engine", sorted(MISSES))
def test_an_unknown_amk_module_stays_missing(amk, engines, tmp_path, engine):
  if engine not in engines:
    pytest.skip(f"this amk carries no {engine}")
  mk = tmp_path / "miss.mk"
  mk.write_text(f"$(info got=$(strip {MISSES[engine]}))\nall:\n\t@true\n")
  r = sh(amk, ["-s", "-f", str(mk)], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "got=true" in r.stdout.lower(), r.stdout + r.stderr


IMPORTABLES = {
  "lua": "$(lua.exec print(amk.dkjson == nil and amk.string == nil))",
  "micropy": "$(micropy.exec import amk; print(not hasattr(amk, 'json') and not hasattr(amk, 'mip')))",
}


@pytest.mark.parametrize("engine", sorted(IMPORTABLES))
def test_an_importable_module_is_not_an_amk_module(amk, engines, tmp_path, engine):
  """The name answers on amk only through its own file under lib/name/; stdlib and vendored modules stay missing."""
  if engine not in engines:
    pytest.skip(f"this amk carries no {engine}")
  mk = tmp_path / "miss.mk"
  mk.write_text(f"$(info got=$(strip {IMPORTABLES[engine]}))\nall:\n\t@true\n")
  r = sh(amk, ["-s", "-f", str(mk)], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "got=true" in r.stdout.lower(), r.stdout + r.stderr

"""Pins pools: a named token ledger of a size, goals being make's jobserver.

The builtins open and read a pool with no engine; `@pool` above a JSON define needs
the dsys topic and jq. Pinned are the listing and members, acquire and release moving held,
the refusals, the auth form, a pool of one as a mutex, a pool of pieces as a horcrux lock,
jobs serializing through one, each guest's attribute form, and the decorator's defaults.
"""

import re

import pytest

from conftest import sh


def run(amk, tmp_path, body, *flags, goal="all", timeout=120):
  mk = tmp_path / "pool.mk"
  mk.write_text(body + "\nall:\n\t@true\n")
  return sh(amk, ["-s", *flags, "-f", str(mk), goal], cwd=tmp_path, timeout=timeout)


def shown(amk, tmp_path, body, *flags, goal="all"):
  """Every bracketed value the run printed, in order; brackets are the test's own marks."""
  r = run(amk, tmp_path, body, *flags, goal=goal)
  assert r.returncode == 0, r.stdout + r.stderr
  return re.findall(r"\[([^\]]*)\]", r.stdout + r.stderr)


def refused(amk, tmp_path, body, *flags):
  r = run(amk, tmp_path, body, *flags)
  assert r.returncode != 0, r.stdout
  return r.stderr


def test_the_callform_opens_lists_and_reads(amk, tmp_path):
  out = shown(amk, tmp_path, "\n".join([
    "$(amk.pool workers, 3)",
    "$(amk.pool quiet, 1)",
    "$(amk.pool other, 5)",
    "$(info [$(amk.pool )])",
    "$(info [$(amk.pool workers)] [$(amk.pool.size workers)] [$(amk.pool.held workers)])",
    "$(info [$(amk.pool quiet)] [$(amk.pool other)] [$(amk.pool nothing)])",
  ]))
  assert out == ["goals workers quiet other", "3", "3", "0", "1", "5", ""]


def test_the_callform_takes_size_and_labels_as_kwargs(amk, tmp_path):
  out = shown(amk, tmp_path, "\n".join([
    "$(amk.pool wide, size=3)",
    "$(amk.pool gpu, labels=g0 g1, size=, label_gen=, strategy=fifo)",
    "$(info [$(amk.pool wide)] [$(amk.pool gpu)] [$(amk.pool.size gpu)])",
  ]))
  assert out == ["3", "2", "2"]


def test_a_labeled_pool_answers_labels_in_order(amk, tmp_path):
  out = shown(amk, tmp_path, "\n".join([
    "$(amk.pool gpu, labels=g0 g1)",
    "$(info [$(amk.pool.acquire gpu)] [$(amk.pool.acquire gpu)] [$(amk.pool.held gpu)] [$(amk.pool.acquire gpu, 0)])",
    "$(info [$(amk.pool.release gpu, g0)$(amk.pool.acquire gpu)])",
  ]))
  assert out == ["g0", "g1", "2", "", "g0"]


def test_a_labeled_release_names_a_label_held(amk, tmp_path):
  out = shown(amk, tmp_path, "\n".join([
    "$(amk.pool cell, labels=off on)",
    "$(info [$(amk.pool.acquire cell)$(amk.pool.acquire cell)$(amk.pool.release cell, on)] [$(amk.pool.held cell)])",
    "$(info [$(amk.pool.acquire cell)] [$(amk.pool.release cell, off)$(amk.pool.release cell, on)$(amk.pool.held cell)])",
  ]))
  assert out == ["offon", "1", "on", "0"]


def test_a_label_fills_its_token_whole(amk, tmp_path):
  long = "x" * 31
  out = shown(amk, tmp_path, "\n".join([
    f"$(amk.pool wide, labels={long} y)",
    "$(info [$(amk.pool.acquire wide)] [$(amk.pool.acquire wide)])",
  ]))
  assert out == [long, "y"]


def test_produce_and_consume_resize_in_the_opener(amk, tmp_path):
  out = shown(amk, tmp_path, "\n".join([
    "$(amk.pool gpu, labels=g0)",
    "$(amk.pool plain, 1)",
    "$(info [$(amk.pool.produce gpu, g9)$(amk.pool.produce plain)])",
    "$(info [$(amk.pool.acquire gpu)] [$(amk.pool.acquire gpu)] [$(amk.pool.acquire plain)$(amk.pool.acquire plain)])",
    "$(info [$(amk.pool.release gpu, g0)$(amk.pool.release gpu, g9)$(amk.pool.consume gpu, 0)] [$(amk.pool.consume gpu, 0)] [$(amk.pool.consume gpu, 0)])",
  ]))
  assert out == ["", "g0", "g9", "11", "g0", "g9", ""]


def test_a_bare_release_of_one_held_label_returns_it(amk, tmp_path):
  out = shown(amk, tmp_path, "\n".join([
    "$(amk.pool gpu, labels=g0 g1)",
    "$(info [$(amk.pool.acquire gpu)$(amk.pool.release gpu)] [$(amk.pool.acquire gpu)] [$(amk.pool.acquire gpu)])",
  ]))
  assert out == ["g0", "g1", "g0"]


@pytest.mark.parametrize("body,want", [
  ("$(amk.pool p, colour=red)", "no key colour"),
  ("$(amk.pool p, size=3, labels=a b)", "size 3 disagrees with the labels"),
  ("$(amk.pool p, size=2, label_gen=mk)", "label_gen is reserved"),
  ("$(amk.pool p, size=2, strategy=lifo)", "strategy lifo; one of default strict open"),
  ("$(amk.pool p, labels=a b)\n$(info $(amk.pool.auth p))", "a labeled pool gives no auth"),
  ("$(amk.pool p, labels=a b)\n$(info $(amk.pool.acquire p)$(amk.pool.acquire p)$(amk.pool.release p))", "release names a label unless exactly one is held"),
  ("$(amk.pool p, labels=a b)\n$(info $(amk.pool.acquire p)$(amk.pool.release p, b))", "b is not held here"),
  ("$(amk.pool p, labels=a b)\n$(info $(amk.pool.acquire p)$(amk.pool.release p, z))", "z is not held here"),
  ("$(amk.pool p, 2)\n$(info $(amk.pool.acquire p)$(amk.pool.release p, a))", "release takes a label only on a labeled pool"),
  ("$(amk.pool p, labels=" + "x" * 32 + ")", "is not 1 to 31 bytes"),
  ("$(amk.pool p, labels=a)\n$(info $(amk.pool.produce p, " + "x" * 32 + "))", "is not 1 to 31 bytes"),
  ("$(amk.pool p, labels=a)\n$(info $(amk.pool.produce p))", "is not 1 to 31 bytes"),
  ("$(amk.pool p, 2)\n$(info $(amk.pool.produce p, a))", "produce takes a label only on a labeled pool"),
  ("$(amk.pool p, 16385)", "16384 tokens fill the pipe, and p has more"),
  ("$(amk.pool p, 2)\n$(info $(amk.pool.acquire p)$(amk.pool.consume p))", "consume takes a fresh token, and this process holds one"),
  ("$(info $(amk.pool.produce goals))", "goals is the jobserver"),
])
def test_the_kwargs_and_labels_refuse(amk, tmp_path, body, want):
  assert want in refused(amk, tmp_path, body)


def test_goals_is_the_jobserver(amk, tmp_path):
  body = "\n".join([
    "probe:",
    "\t@echo '[$(amk.pool goals)] [$(amk.pool.held goals)] [$(amk.pool.auth goals)]'",
  ])
  out = shown(amk, tmp_path, body, "-j4", goal="probe")
  assert out[:2] == ["4", "0"]
  assert re.fullmatch(r"\d+,\d+|fifo:.+", out[2]), out
  assert shown(amk, tmp_path, body, goal="probe") == ["1", "0", ""]


def test_acquire_and_release_move_held(amk, tmp_path):
  out = shown(amk, tmp_path, "\n".join([
    "$(amk.pool workers, 2)",
    "$(info [$(amk.pool.acquire workers)$(amk.pool.held workers)$(amk.pool.acquire workers)$(amk.pool.held workers)$(amk.pool.release workers)$(amk.pool.held workers)])",
  ]))
  assert out == ["11121"]


def test_an_empty_ledger_answers_nothing_without_blocking(amk, tmp_path):
  out = shown(amk, tmp_path, "\n".join([
    "$(amk.pool one, 1)",
    "$(info [$(amk.pool.acquire one)][$(amk.pool.acquire one, 0)][$(amk.pool.acquire one, 50)][$(amk.pool.release one)$(amk.pool.acquire one, 0)])",
  ]))
  assert out == ["1", "", "", "1"]


def test_a_pool_of_one_is_a_mutex(amk, tmp_path):
  lock = "$(amk.pool.acquire m, 0)"
  unlock = "$(amk.pool.release m)"
  out = shown(amk, tmp_path, "\n".join([
    "$(amk.pool m, 1)",
    f"$(info [{lock}][{lock}][$(amk.pool.held m)][{unlock}{lock}][{lock}][{unlock}$(amk.pool.held m)])",
  ]))
  assert out == ["1", "", "1", "1", "", "0"]


def test_a_pool_of_pieces_is_a_horcrux_lock(amk, tmp_path):
  """A reader takes one piece and a writer needs every piece, so pieces out is readers in."""
  take = "$(amk.pool.acquire h, 0)"
  give = "$(amk.pool.release h)"
  out = shown(amk, tmp_path, "\n".join([
    "$(amk.pool h, 3)",
    f"$(info [{take}{take}{take}][{take}][$(amk.pool.held h)])",
    f"$(info [{give}{give}{give}$(amk.pool.held h)][{take}{take}{take}][{take}][$(amk.pool.held h)])",
  ]))
  assert out == ["111", "", "3", "0", "111", "", "3"]


@pytest.mark.engines("lua")
def test_spawned_jobs_serialize_through_a_mutex(amk, tmp_path):
  """A job is a fork, so it keeps the pool and reaches its verbs through the guest's handle."""
  body = "\n".join([
    "$(amk.pool m, 1)",
    "@lua.target",
    "define worker",
    '  amk.pool.acquire("m")',
    '  local f = io.open("log", "a") f:write("in\\n") f:close()',
    '  os.execute("sleep 0.2")',
    '  f = io.open("log", "a") f:write("out\\n") f:close()',
    '  amk.pool.release("m")',
    "endef",
    "probe:",
    "\t@$(lua.exec local a = amk.spawn('worker') local b = amk.spawn('worker') local c = amk.spawn('worker') amk.wait(a) amk.wait(b) amk.wait(c))",
  ])
  r = run(amk, tmp_path, body, goal="probe")
  assert r.returncode == 0, r.stdout + r.stderr
  assert (tmp_path / "log").read_text().split() == ["in", "out"] * 3


GUEST_CALLS = {
  "lua": '$(lua.exec print(amk.pool.acquire("door", "0") .. amk.pool.held("door") .. amk.pool.size("door")))',
  "micropy": '$(micropy.exec import amk; print(amk.pool.acquire("door", "0") + amk.pool.held("door") + amk.pool.size("door")))',
  "js": '$(js.exec print(amk.pool.acquire("door", "0") + amk.pool.held("door") + amk.pool.size("door")))',
  "s7": '$(s7.exec (display (string-append (amk-pool-acquire "door" "0") (amk-pool-held "door") (amk-pool-size "door"))))',
}


@pytest.mark.parametrize("engine", sorted(GUEST_CALLS))
def test_a_guest_reaches_the_verbs_as_attributes_of_amk(amk, tmp_path, engine, engines):
  """A missing field of the handle that names a make function calls it, so no binding file is needed."""
  if engine not in engines:
    pytest.skip(f"no {engine} in this build")
  out = shown(amk, tmp_path, "\n".join([
    "$(amk.pool door, 1)",
    f"$(info [{GUEST_CALLS[engine]}])",
  ]))
  assert out == ["111"]


BOUND_CALLS = {
  "lua": '$(lua.exec print(amk.pool.door.acquire("0") .. amk.pool.door.held() .. amk.pool.goals.held()))',
  "micropy": '$(micropy.exec import amk; print(amk.pool.door.acquire("0") + amk.pool.door.held() + amk.pool.goals.held()))',
  "js": '$(js.exec print(amk.pool.door.acquire("0") + amk.pool.door.held() + amk.pool.goals.held()))',
  "s7": '$(s7.exec (display (string-append (amk-pool-door-acquire "0") (amk-pool-door-held) (amk-pool-goals-held))))',
}


@pytest.mark.parametrize("engine", sorted(BOUND_CALLS))
def test_a_pool_is_a_handle_of_its_own_name(amk, tmp_path, engine, engines):
  """Opening a pool binds its verbs as functions of its name, so every guest spells them as fields."""
  if engine not in engines:
    pytest.skip(f"no {engine} in this build")
  out = shown(amk, tmp_path, "\n".join([
    "$(amk.pool door, 1)",
    f"$(info [{BOUND_CALLS[engine]}])",
    "$(info [$(amk.pool.door.acquire 0)][$(amk.pool.door.held )][$(amk.pool.door.release )$(amk.pool.door.held )])",
  ]))
  assert out == ["110", "", "1", "0"]


@pytest.mark.engines("lua")
def test_a_holder_that_dies_gives_its_token_back(amk, tmp_path):
  """A recipe child's exit returns what it holds, so a crash between acquire and release leaks nothing."""
  body = "\n".join([
    "$(amk.pool door, 1)",
    "@lua.target",
    "define crasher",
    '  amk.pool.acquire("door")',
    '  error("boom")',
    "endef",
    "@lua.target",
    "define waiter",
    '  print("got[" .. amk.pool.acquire("door", "2000") .. "]")',
    "endef",
    "probe:",
    "\t@$(lua.exec local a = amk.spawn('crasher') amk.wait(a) local b = amk.spawn('waiter') amk.wait(b))",
  ])
  r = run(amk, tmp_path, body, goal="probe")
  assert "got[1]" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("lua")
def test_a_holder_that_dies_gives_its_labels_back(amk, tmp_path):
  body = "\n".join([
    "$(amk.pool gpu, labels=g0 g1)",
    "@lua.target",
    "define crasher",
    '  amk.pool.acquire("gpu")',
    '  error("boom")',
    "endef",
    "@lua.target",
    "define waiter",
    '  print("got[" .. amk.pool.acquire("gpu", "2000") .. " " .. amk.pool.acquire("gpu", "2000") .. "]")',
    "endef",
    "probe:",
    "\t@$(lua.exec local a = amk.spawn('crasher') amk.wait(a) local b = amk.spawn('waiter') amk.wait(b))",
  ])
  r = run(amk, tmp_path, body, goal="probe")
  assert "got[g1 g0]" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("lua")
def test_only_the_opener_resizes(amk, tmp_path):
  body = "\n".join([
    "$(amk.pool gpu, labels=g0)",
    "@lua.target",
    "define grower",
    '  amk.pool.produce("gpu", "g1")',
    "endef",
    "probe:",
    "\t@$(lua.exec local a = amk.spawn('grower') amk.wait(a))",
  ])
  r = run(amk, tmp_path, body, goal="probe")
  assert "only the process that opened it may produce" in r.stdout + r.stderr, r.stdout + r.stderr


def test_an_empty_pool_opens_and_fills_by_produce(amk, tmp_path):
  out = shown(amk, tmp_path, "\n".join([
    "$(amk.pool place, 0)",
    "$(info [$(amk.pool.size place)] [$(amk.pool.acquire place, 0)])",
    "$(info [$(amk.pool.produce place)$(amk.pool.size place)] [$(amk.pool.consume place)$(amk.pool.size place)])",
  ]))
  assert out == ["0", "", "1", "10"]


def test_a_labeled_pool_may_start_empty(amk, tmp_path):
  out = shown(amk, tmp_path, "\n".join([
    "$(amk.pool crossed, labeled=true)",
    "$(info [$(amk.pool.size crossed)] [$(amk.pool.acquire crossed, 0)])",
    "$(info [$(amk.pool.produce crossed, a1)$(amk.pool.acquire crossed)])",
  ]))
  assert out == ["0", "", "a1"]


@pytest.mark.engines("lua")
def test_an_open_pool_is_resized_from_any_process_and_counted_by_the_kernel(amk, tmp_path):
  body = "\n".join([
    "$(amk.pool q, labels=a b, strategy=open)",
    "@lua.target",
    "define step",
    '  print("took " .. amk.pool.consume("q"))',
    '  amk.pool.produce("q", "z")',
    '  amk.pool.produce("q", "y")',
    '  print("sees " .. amk.pool.size("q"))',
    "endef",
    "probe:",
    "\t$(info $(amk.goal step))@true",
    "\t@echo '[$(amk.pool.size q)] [$(amk.pool.acquire q)$(amk.pool.size q)] [$(amk.pool.acquire q) $(amk.pool.acquire q)]'",
  ])
  r = run(amk, tmp_path, body, goal="probe")
  out = r.stdout + r.stderr
  assert r.returncode == 0, out
  assert "took a\nsees 3" in out, out
  assert "[3] [b2] [z y]" in out, out


@pytest.mark.engines("lua")
def test_the_size_after_a_resize_is_the_openers(amk, tmp_path):
  body = "\n".join([
    "$(amk.pool place, 1)",
    "$(amk.pool.produce place)",
    "$(info [opener $(amk.pool.size place)])",
    "@lua.target",
    "define reader",
    '  print(amk.pool.size("place"))',
    "endef",
    "probe:",
    "\t@$(lua.exec local a = amk.spawn('reader') amk.wait(a))",
  ])
  r = run(amk, tmp_path, body, goal="probe")
  out = r.stdout + r.stderr
  assert "[opener 2]" in out, out
  assert "the size is kept only by the process that opened it" in out, out


@pytest.mark.parametrize("body,want", [
  ("$(amk.pool workers, 2)\n$(amk.pool workers, 3)", "workers is already open"),
  ("$(amk.pool goals, 3)", "goals is the jobserver, sized by -j"),
  ("$(amk.pool odd, size=two)", "odd: size two is not a number"),
  ("$(amk.pool odd, size=, labels=)", "odd needs a size or labels"),
  ("$(amk.pool odd, labeled=yes)", "odd: labeled is true or false, not yes"),
  ("$(amk.pool odd, size=2, labeled=true)", "odd: a labeled pool takes its tokens from labels, not size 2"),
  ("$(amk.pool held, 2)", "held is a verb, not a name a pool may take"),
  ("$(info [$(amk.pool.held nothing)])", "no pool named nothing"),
  ("$(amk.pool one, 1)\n$(info [$(amk.pool.release one)])", "one: nothing held to release"),
])
def test_each_refusal_names_the_pool(amk, tmp_path, body, want):
  assert want in refused(amk, tmp_path, body)


def test_auth_is_the_stock_pipe_form(amk, tmp_path):
  out = shown(amk, tmp_path, "$(amk.pool workers, 2)\n$(info [$(amk.pool.auth workers)])")
  assert re.fullmatch(r"\d+,\d+", out[0]), out


JQ = pytest.mark.engines("jq")


@JQ
def test_loading_the_topic_opens_no_pool(amk, tmp_path):
  assert shown(amk, tmp_path, "load dsys\n$(info [$(amk.pool )])") == ["goals"]


DECORATED = [
  "load dsys/pool",
  "@pool", "define wide", '{ "size": 4 }', "endef",
  "@pool", "define plain", "{}", "endef",
]


@JQ
def test_a_decorated_pool_merges_over_the_baseline(amk, tmp_path):
  out = shown(amk, tmp_path, "\n".join(DECORATED + [
    "$(info [$(amk.pool )])",
    "$(foreach p,wide plain,$(info [$(p) $(amk.pool.size $(p))]))",
  ]))
  assert out == ["goals wide plain", "wide 4", "plain 2"]


@JQ
def test_a_decorated_pool_acquires_like_a_callform_one(amk, tmp_path):
  out = shown(amk, tmp_path, "\n".join(DECORATED + [
    "$(info [$(amk.pool.acquire plain)$(amk.pool.acquire plain)$(amk.pool.acquire plain, 0)$(amk.pool.held plain)])",
  ]))
  assert out == ["112"]


@JQ
def test_a_decorated_pool_takes_labels(amk, tmp_path):
  out = shown(amk, tmp_path, "\n".join([
    "load dsys/pool",
    "@pool", "define gpu", '{ "labels": ["g0", "g1", "g2"] }', "endef",
    "@pool", "define pair", '{ "size": 2, "labels": ["a", "b"] }', "endef",
    "$(info [$(amk.pool.size gpu)] [$(amk.pool.acquire gpu)] [$(amk.pool.size pair)] [$(amk.pool.acquire pair)])",
  ]))
  assert out == ["3", "g0", "2", "a"]


@JQ
@pytest.mark.parametrize("body,want", [
  ('@pool\ndefine goals\n{ "size": 3 }\nendef', "goals is the jobserver"),
  ('@pool\ndefine odd\n{ "size": 3, "labels": ["a", "b"] }\nendef', "size 3 disagrees with the labels"),
])
def test_a_decorated_pool_refuses_what_the_callform_does(amk, tmp_path, body, want):
  assert want in refused(amk, tmp_path, "load dsys/pool\n" + body)


@pytest.mark.engines("jq", "sqlite")
@pytest.mark.parametrize("body,want", [
  ('{ "size": 2, "colour": "red" }', "Additional property 'colour' not allowed"),
  ('{ "label_gen": "mk" }', "Property label_gen: Type mismatch: expected null, got string"),
  ('{ "strategy": "lifo" }', 'Property strategy: Value "lifo" not in enum; one of "default" "strict" "fifo" "open"'),
  ('{ "size": -1 }', "Property size: Less than minimum 0"),
  ('{ "size": "2" }', "Property size: Type mismatch: expected integer, got string"),
  ('{ "labels": ["has space"] }', "Property labels: Does not match pattern"),
])
def test_a_decorated_pool_is_checked_against_its_schema(amk, tmp_path, body, want):
  err = refused(amk, tmp_path, f"load dsys/pool\n@pool\ndefine odd\n{body}\nendef")
  assert "odd: does not meet schema/pool.json: " + want in err, err


def test_the_mutex_factory_locks_tries_and_unlocks_by_name(amk, tmp_path):
  out = shown(amk, tmp_path, "\n".join([
    "load dsys/locks",
    "$(amk.mutex door)",
    "$(amk.mutex door)",
    "$(info [$(amk.pool door)][$(amk.mutex.door.trylock )][$(amk.mutex.door.trylock )][$(amk.pool.door.held )]"
    "[$(amk.mutex.door.unlock )$(amk.mutex.door.lock )][$(amk.mutex.door.unlock )$(amk.pool.door.held )])",
  ]))
  assert out == ["1", "1", "", "1", "1", "0"]


def test_the_horcrux_factory_shares_pieces_with_readers_and_all_with_a_writer(amk, tmp_path):
  out = shown(amk, tmp_path, "\n".join([
    "load dsys/locks",
    "$(amk.horcrux book, 3)",
    "$(info [$(amk.pool book)][$(amk.pool book.w)])",
    "$(info [$(amk.horcrux.book.rlock )$(amk.horcrux.book.rlock )][$(amk.horcrux.book.tryrlock )][$(amk.horcrux.book.tryrlock )][$(amk.pool.book.held )])",
    "$(info [$(amk.horcrux.book.runlock )$(amk.horcrux.book.runlock )$(amk.horcrux.book.runlock )$(amk.pool.book.held )])",
    "$(info [$(amk.horcrux.book.wlock )$(amk.pool.book.held )$(amk.pool.book.w.held )][$(amk.horcrux.book.tryrlock )][$(amk.horcrux.book.wunlock )$(amk.pool.book.held )$(amk.pool.book.w.held )])",
  ]))
  assert out == ["3", "1", "11", "1", "", "3", "0", "131", "", "00"]


def test_the_mutex_factory_takes_its_name_from_the_assignment(amk, tmp_path):
  out = shown(amk, tmp_path, "\n".join([
    "load dsys/locks",
    "door := $(amk.mutex )",
    "$(info [$(door)][$(amk.pool door)][$(amk.mutex.door.trylock )][$(amk.mutex.door.trylock )])",
  ]))
  assert out == ["door", "1", "1", ""]


def test_the_horcrux_factory_takes_its_name_from_the_assignment_and_its_size_alone(amk, tmp_path):
  out = shown(amk, tmp_path, "\n".join([
    "load dsys/locks",
    "book := $(amk.horcrux 3)",
    "$(info [$(book)][$(amk.pool book)][$(amk.pool book.w)])",
    "$(info [$(amk.horcrux.book.rlock )][$(amk.pool.book.held )])",
  ]))
  assert out == ["book", "3", "1", "1", "1"]


@pytest.mark.engines("lua")
def test_a_guest_locks_a_named_mutex_as_a_field(amk, tmp_path):
  out = shown(amk, tmp_path, "\n".join([
    "load dsys/locks",
    "$(amk.mutex door)",
    '$(info [$(lua.exec print(amk.mutex.door.trylock() .. amk.mutex.door.trylock() .. amk.pool.door.held() .. amk.mutex.door.unlock() .. amk.pool.door.held()))])',
  ]))
  assert out == ["110"]


def test_the_rendezvous_factory_opens_a_value_a_receipt_and_a_sender_mutex(amk, tmp_path):
  out = shown(amk, tmp_path, "\n".join([
    "load dsys/locks",
    "$(amk.rendezvous chan)",
    "$(amk.rendezvous chan)",
    "$(info [$(filter chan chan.ack chan.s,$(amk.pool ))][$(amk.pool chan)][$(amk.pool chan.ack)][$(amk.pool chan.s)])",
  ]))
  assert out == ["chan chan.ack chan.s", "0", "0", "1"]


@pytest.mark.engines("lua", "micropy", "jq")
def test_a_send_returns_only_once_its_value_is_received(amk, tmp_path):
  r = run(amk, tmp_path, "\n".join([
    "load dsys/locks",
    "load dsys/jobman",
    "$(amk.rendezvous chan)",
    "@micropy.target",
    "define sender",
    "  import amk",
    "  for v in ('a', 'b', 'c'):",
    "    amk.rendezvous.chan.send(v)",
    "    print('sent ' + v)",
    "endef",
    "@lua.target",
    "define receiver",
    "  for i = 1, 3 do",
    '    os.execute("sleep 0.2")',
    '    print("received " .. amk.rendezvous.chan.recv())',
    "  end",
    "endef",
    "@lua.target",
    "define pair",
    "  local jobs = amk.jobman.__jobs__",
    "  local a, b = jobs.spawn.goal('receiver'), jobs.spawn.goal('sender')",
    "  jobs.wait(a) jobs.wait(b)",
    "endef",
    "after: pair",
    "\t@echo \"[$(amk.pool.size chan)][$(amk.pool.size chan.ack)]\"",
  ]), goal="after")
  assert r.returncode == 0, r.stdout + r.stderr
  lines = [l for l in r.stdout.splitlines() if l.startswith(("sent ", "received "))]
  assert lines == ["received a", "sent a", "received b", "sent b", "received c", "sent c"], r.stdout
  assert "[0][0]" in r.stdout, r.stdout

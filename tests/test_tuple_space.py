"""Pins a tuple space over a sqlite workspace: one atomic take shared by concurrent workers.

The space is a table, and take is an insert trigger that answers the oldest match and removes
it in the same statement. Workers run at once under -j4, one shell worker on the ask channel
and two engine workers through amk.call. Pinned: every item is taken exactly once, the work
spreads over more than one worker, nothing is written to disk, and a take on an empty space
answers nothing.
"""

import json

import pytest

from conftest import sh

N = 60

space = "\n".join([
  "@sqlite.import",
  "define space",
  "  CREATE TABLE ts(t TEXT);",
  "  CREATE TABLE answer(t TEXT);",
  "  CREATE VIEW put(p) AS SELECT NULL;",
  "  CREATE VIEW take(p) AS SELECT NULL;",
  "  CREATE TRIGGER put INSTEAD OF INSERT ON put BEGIN",
  "    DELETE FROM answer;",
  "    INSERT INTO ts VALUES(json(NEW.p));",
  "  END;",
  "  CREATE TRIGGER take INSTEAD OF INSERT ON take BEGIN",
  "    DELETE FROM answer;",
  "    INSERT INTO answer SELECT t FROM ts WHERE t ->> 0 = NEW.p ORDER BY rowid LIMIT 1;",
  "    DELETE FROM ts WHERE rowid = (SELECT min(rowid) FROM ts WHERE t ->> 0 = NEW.p);",
  "  END;",
  "endef",
  "ts = $(space.update --arg p '$(2)' INSERT INTO $(1) VALUES(:p); SELECT json(t) AS t FROM answer)",
  'ts.sh = source amk.sh ; ts() { amk.ns update space --arg p "$$2" -- "INSERT INTO $$1 VALUES(:p); SELECT json(t) AS t FROM answer" ; }',
])

workers = "\n".join([
  "SHELL := bash",
  space,
  "items:",
  f"\t@${{ts.sh}} ; for n in $$(seq 1 {N}); do ts put \"[\\\"item\\\",$$n]\" ; done",
  "sh.worker lua.worker micropy.worker: items",
  "sh.worker:",
  "\t@${ts.sh} ; while t=$$(ts take item) && [ -n \"$$t\" ]; do \\",
  "\t  n=$$(printf '%s' \"$$t\" | jq.pipe '.t[1]') ; ts put \"[\\\"done\\\",$$n,\\\"sh\\\"]\" ; done",
  "@lua.import.target",
  "define lua.worker",
  "  local json = require('dkjson')",
  "  while true do",
  "    local t = amk.call('ts', 'take', 'item')",
  "    if t == '' then break end",
  "    amk.call('ts', 'put', '[\"done\",' .. json.decode(t).t[2] .. ',\"lua\"]')",
  "  end",
  "endef",
  "@micropy.import.target",
  "define micropy.worker",
  "  import json, amk",
  "  while True:",
  "    t = amk.call('ts', 'take', 'item')",
  "    if not t:",
  "      break",
  "    amk.call('ts', 'put', '[\"done\",%d,\"micropy\"]' % json.loads(t)['t'][1])",
  "endef",
  "report: sh.worker lua.worker micropy.worker",
  "\t@${ts.sh} ; amk.ns get space -- \"SELECT t ->> 0 AS kind, t ->> 1 AS n, t ->> 2 AS who FROM ts\"",
  "",
])


@pytest.mark.engines("sqlite", "lua", "micropy")
def test_concurrent_workers_take_every_item_exactly_once(amk, tmp_path):
  (tmp_path / "space.mk").write_text(workers)
  r = sh(amk, ["-j4", "-f", "space.mk", "report"], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  rows = [json.loads(line) for line in r.stdout.splitlines() if line.startswith("{")]
  assert not [row for row in rows if row["kind"] == "item"], r.stdout
  done = [row for row in rows if row["kind"] == "done"]
  assert sorted(row["n"] for row in done) == list(range(1, N + 1)), r.stdout
  assert len({row["who"] for row in done}) > 1, r.stdout
  assert sorted(p.name for p in tmp_path.iterdir()) == ["space.mk"], list(tmp_path.iterdir())


@pytest.mark.engines("sqlite")
def test_a_take_on_an_empty_space_answers_nothing(amk, tmp_path):
  (tmp_path / "empty.mk").write_text("\n".join([
    "SHELL := bash",
    space,
    "probe:",
    "\t@${ts.sh} ; t=$$(ts take nothing) ; echo \"got=[$$t] st=$$?\"",
    "",
  ]))
  r = sh(amk, ["-f", "empty.mk", "probe"], cwd=tmp_path, timeout=60)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "got=[] st=0" in r.stdout, r.stdout + r.stderr

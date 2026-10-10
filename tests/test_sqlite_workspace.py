"""Pins the sqlite workspace row, its targets, and its command line.

A namespace is one in-memory database: rows come back as JSON lines, state survives across
requests, `--argjson` binds typed, owned and shared backings write, load, and reload the dump.
A target runs sqlite's shell with its flags over an in-memory database and reads standard
input through a dot command; the multicall name is the shell itself.
"""

import json

import pytest

from conftest import sh

ask = "printf '%s\\n' \"$(1)\" >&$$AMK_CALL && read -r st n <&$$AMK_REPLY && { [ \"$$n\" = 0 ] || IFS= read -r $(2) <&$$AMK_REPLY; }"

program = "\n".join([
  "SHELL := bash",
  "define ask",
  ask,
  "endef",
  "$(sqlite.ns D, create)",
  "$(sqlite.ns O, create, owned $(dir)/o.sql)",
  "$(sqlite.ns P, create, owned $(dir)/p.sql)",
  "$(sqlite.ns H, create, shared $(dir)/h.sql)",
  "seed := $(D.update CREATE TABLE edge(a, b); INSERT INTO edge VALUES(1,2),(2,3),(3,1))",
  "rows:",
  "\t@$(call ask,get D SELECT a FROM edge ORDER BY a,r) && echo \"first=[$$r]\"",
  "state:",
  "\t@$(call ask,update D INSERT INTO edge VALUES(3,4),r); $(call ask,get D SELECT count(*) AS n FROM edge,r); echo \"n=[$$r]\"",
  "walk:",
  "\t@source amk.sh; amk.ns get D -- 'WITH RECURSIVE r(x) AS (SELECT 1 UNION SELECT b FROM edge, r WHERE a = x) SELECT json_group_array(x) AS seen FROM r' | tr -d '\\n'; echo",
  "dump:",
  "\t@source amk.sh; amk.call 'dump D' | tr '\\n' ' '; echo",
  "owned:",
  "\t@$(call ask,update O CREATE TABLE t(k); INSERT INTO t VALUES('x'),r); echo \"file=[$$(cat $(dir)/o.sql | tr '\\n' ' ')]\"",
  "preload:",
  "\t@$(call ask,get P SELECT k FROM t,r); echo \"pre=[$$r]\"",
  "shared:",
  "\t@$(call ask,update H CREATE TABLE t(k); INSERT INTO t VALUES(1),r); printf 'CREATE TABLE t(k);\\nINSERT INTO t VALUES(1),(2),(3);\\n' > $(dir)/h.sql; sleep 1.1",
  "\t@$(call ask,get H SELECT count(*) AS n FROM t,r); echo \"shared=[$$r]\"",
  "typed:",
  "\t@source amk.sh; amk.ns get D --argjson v 3 --argjson s '\"x\"' -- 'SELECT typeof(:v) AS v, typeof(:s) AS s, :v + 1 AS n' | tr -d '\\n'; echo",
  "",
])

targets = "\n".join([
  "@sqlite.import.target -json",
  "define sq.gen",
  "  SELECT 1 AS n UNION ALL SELECT 2;",
  "endef",
  "@sqlite.import.target -csv -header",
  "define sq.csv",
  "  SELECT 'a' AS k, 1 AS v UNION ALL SELECT 'b', 2;",
  "endef",
  "@sqlite.import.target -json",
  "define sq.sum",
  "  .import --csv /dev/stdin t",
  "  SELECT sum(v) AS total FROM t;",
  "endef",
  "",
])


@pytest.fixture
def mk(tmp_path):
  p = tmp_path / "sqlite.mk"
  p.write_text(program)
  return p


@pytest.mark.engines("sqlite")
def test_rows_come_back_as_json_objects(amk, tmp_path, mk):
  r = sh(amk, ["-f", str(mk), f"dir={tmp_path}", "rows"], cwd=tmp_path)
  assert r.returncode == 0, r.stdout + r.stderr
  assert 'first=[{"a":1}]' in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("sqlite")
def test_state_survives_across_requests(amk, tmp_path, mk):
  r = sh(amk, ["-f", str(mk), f"dir={tmp_path}", "state"], cwd=tmp_path)
  assert r.returncode == 0, r.stdout + r.stderr
  assert 'n=[{"n":4}]' in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("sqlite")
def test_a_recursive_query_walks_a_cycle(amk, tmp_path, mk):
  r = sh(amk, ["-f", str(mk), f"dir={tmp_path}", "walk"], cwd=tmp_path)
  assert r.returncode == 0, r.stdout + r.stderr
  assert json.loads(r.stdout.strip())["seen"] == [1, 2, 3], r.stdout + r.stderr


@pytest.mark.engines("sqlite")
def test_dump_replays_schema_and_rows(amk, tmp_path, mk):
  r = sh(amk, ["-f", str(mk), f"dir={tmp_path}", "dump"], cwd=tmp_path)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "CREATE TABLE edge(a, b);" in r.stdout, r.stdout + r.stderr
  assert 'INSERT INTO "edge" VALUES(1,2);' in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("sqlite")
def test_an_owned_backing_writes_the_dump(amk, tmp_path, mk):
  r = sh(amk, ["-f", str(mk), f"dir={tmp_path}", "owned"], cwd=tmp_path)
  assert r.returncode == 0, r.stdout + r.stderr
  assert (tmp_path / "o.sql").read_text() == "CREATE TABLE t(k);\nINSERT INTO \"t\" VALUES('x');\n"


@pytest.mark.engines("sqlite")
def test_an_owned_backing_loads_an_existing_dump(amk, tmp_path, mk):
  (tmp_path / "p.sql").write_text("CREATE TABLE t(k);\nINSERT INTO \"t\" VALUES('pre');\n")
  r = sh(amk, ["-f", str(mk), f"dir={tmp_path}", "preload"], cwd=tmp_path)
  assert r.returncode == 0, r.stdout + r.stderr
  assert 'pre=[{"k":"pre"}]' in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("sqlite")
def test_a_shared_backing_reloads_an_outside_write(amk, tmp_path, mk):
  r = sh(amk, ["-f", str(mk), f"dir={tmp_path}", "shared"], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert 'shared=[{"n":3}]' in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("sqlite")
def test_argjson_binds_a_typed_value(amk, tmp_path, mk):
  r = sh(amk, ["-f", str(mk), f"dir={tmp_path}", "typed"], cwd=tmp_path)
  assert r.returncode == 0, r.stdout + r.stderr
  assert json.loads(r.stdout.strip()) == {"v": "integer", "s": "text", "n": 4}, r.stdout + r.stderr


@pytest.fixture
def tk(tmp_path):
  p = tmp_path / "targets.mk"
  p.write_text(targets)
  return p


@pytest.mark.engines("sqlite")
def test_a_target_runs_the_shell_with_its_flags(amk, tmp_path, tk):
  r = sh(amk, ["-s", "-f", str(tk), "sq.gen"], cwd=tmp_path)
  assert r.returncode == 0, r.stdout + r.stderr
  assert json.loads(r.stdout) == [{"n": 1}, {"n": 2}], r.stdout + r.stderr


@pytest.mark.engines("sqlite")
def test_a_target_imports_its_standard_input(amk, tmp_path, tk):
  r = sh("sh", ["-c", f"{amk} -s -f {tk} sq.csv | {amk} -s -f {tk} sq.sum"], cwd=tmp_path)
  assert r.returncode == 0, r.stdout + r.stderr
  assert json.loads(r.stdout) == [{"total": 3}], r.stdout + r.stderr


@pytest.mark.engines("sqlite")
def test_the_multicall_name_is_the_shell_over_a_file(amk, tmp_path):
  r = sh(amk, ["--sqlite", "x.db", "CREATE TABLE t(n); INSERT INTO t VALUES(7);"], cwd=tmp_path)
  assert r.returncode == 0, r.stdout + r.stderr
  r = sh(amk, ["--sqlite", "-json", "x.db", "SELECT n FROM t"], cwd=tmp_path)
  assert r.returncode == 0, r.stdout + r.stderr
  assert json.loads(r.stdout) == [{"n": 7}], r.stdout + r.stderr


@pytest.mark.engines("sqlite")
def test_the_multicall_name_after_dashdash_runs_in_memory(amk, tmp_path):
  r = sh(amk, ["--sqlite", "-json", "--", "CREATE TABLE t(n);\nINSERT INTO t VALUES(7);\n.mode csv\nSELECT n FROM t;"], cwd=tmp_path)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "7", r.stdout + r.stderr
  assert not list(tmp_path.glob("*.db")), list(tmp_path.iterdir())

"""Pins the cypher workspace row: a sqlite workspace with GraphQLite registered.

A namespace takes Cypher as it is in get and update, with a bound name as a parameter, and
answers one row per line; SQL calling the cypher function still works and answers the rows
as one JSON text. A Cypher write under get is refused. A plain sqlite workspace carries
none of the graph schema. The cypher library adds match, create, merge and select handles.
"""

import json

import pytest

from conftest import sh

program = "\n".join([
  "$(cypher.ns G, create)",
  "$(sqlite.ns S, create)",
  "seed := $(G.update CREATE (a:Person {name: \"Ann\", age: 30})-[:KNOWS]->(b:Person {name: \"Bo\", age: 41})-[:KNOWS]->(c:Person {name: \"Cy\", age: 35}))",
  "reach := $(G.get --argjson min 32 MATCH (a:Person {name: \"Ann\"})-[:KNOWS*1..3]->(x:Person) WHERE x.age > $$min RETURN x.name AS name ORDER BY x.name)",
  "count := $(G.get MATCH (p:Person) RETURN count(p) AS n)",
  "wrapped := $(G.get SELECT cypher('MATCH (p:Person) RETURN count(p) AS n') AS rows)",
  "plain := $(S.get SELECT count(*) AS n FROM sqlite_master)",
  "$(info seed=$(seed))",
  "$(info reach=$(reach))",
  "$(info count=$(count))",
  "$(info wrapped=$(wrapped))",
  "$(info plain=$(plain))",
  "all:",
  "\t@true",
  "",
])


def _rows(stdout, key):
  """The rows printed under key: its own line past the equals sign, then every line up to the next key."""
  lines = stdout.splitlines()
  start = next(i for i, l in enumerate(lines) if l.startswith(key + "="))
  rows = [lines[start].split("=", 1)[1]]
  for l in lines[start + 1:]:
    if l[:1].isalpha() and "=" in l and l.split("=", 1)[0].isidentifier():
      break
    rows.append(l)
  return [json.loads(r) for r in rows if r.strip()]


@pytest.fixture
def mk(tmp_path):
  p = tmp_path / "cypher.mk"
  p.write_text(program)
  return p


@pytest.mark.engines("cypher", "sqlite")
def test_a_variable_length_path_filters_on_a_property(amk, tmp_path, mk):
  r = sh(amk, ["-f", str(mk)], cwd=tmp_path)
  assert r.returncode == 0, r.stdout + r.stderr
  assert _rows(r.stdout, "reach") == [{"name": "Bo"}, {"name": "Cy"}], r.stdout + r.stderr


@pytest.mark.engines("cypher", "sqlite")
def test_an_aggregate_counts_nodes(amk, tmp_path, mk):
  r = sh(amk, ["-f", str(mk)], cwd=tmp_path)
  assert r.returncode == 0, r.stdout + r.stderr
  assert _rows(r.stdout, "count") == [{"n": 3}], r.stdout + r.stderr


@pytest.mark.engines("cypher", "sqlite")
def test_a_write_answers_its_counts_as_one_row(amk, tmp_path, mk):
  r = sh(amk, ["-f", str(mk)], cwd=tmp_path)
  assert r.returncode == 0, r.stdout + r.stderr
  seed = _rows(r.stdout, "seed")
  assert len(seed) == 1 and seed[0]["nodes_created"] == 3 and seed[0]["relationships_created"] == 2, r.stdout


@pytest.mark.engines("cypher", "sqlite")
def test_sql_calling_the_function_still_answers_one_text(amk, tmp_path, mk):
  r = sh(amk, ["-f", str(mk)], cwd=tmp_path)
  assert r.returncode == 0, r.stdout + r.stderr
  wrapped = _rows(r.stdout, "wrapped")
  assert json.loads(wrapped[0]["rows"]) == [{"n": 3}], r.stdout


@pytest.mark.engines("cypher")
def test_a_cypher_write_under_get_is_refused(amk, tmp_path):
  mk = tmp_path / "refuse.mk"
  mk.write_text("$(cypher.ns G, create)\nx := $(G.get CREATE (:T {n: 1}))\nall:\n\t@true\n")
  r = sh(amk, ["-f", str(mk)], cwd=tmp_path)
  assert r.returncode != 0, r.stdout + r.stderr
  assert "belongs in update" in r.stderr, r.stderr


@pytest.mark.engines("cypher", "sqlite")
def test_a_plain_sqlite_workspace_carries_no_graph_schema(amk, tmp_path, mk):
  r = sh(amk, ["-f", str(mk)], cwd=tmp_path)
  assert r.returncode == 0, r.stdout + r.stderr
  assert 'plain={"n":0}' in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("cypher", "sqlite")
def test_the_library_adds_match_create_merge_and_select_handles(amk, tmp_path):
  mk = tmp_path / "handles.mk"
  mk.write_text("\n".join([
    "load cypher",
    "$(cypher.ns G, create)",
    "made := $(G.create (:T {n: 1})-[:TO]->(:T {n: 2}))",
    "same := $(G.merge (t:T {n: 2}) SET t.seen = true)",
    "$(info pairs=$(G.match (a:T)-[:TO]->(b:T) RETURN a.n AS a, b.n AS b))",
    "$(info rows=$(G.select count(*) AS n FROM nodes))",
    "$(info bound=$(cypher.match G, (t:T) WHERE t.seen RETURN t.n AS n))",
    "all:",
    "\t@true",
    "",
  ]))
  r = sh(amk, ["-f", str(mk)], cwd=tmp_path)
  assert r.returncode == 0, r.stdout + r.stderr
  assert _rows(r.stdout, "pairs") == [{"a": 1, "b": 2}], r.stdout
  assert _rows(r.stdout, "rows") == [{"n": 2}], r.stdout
  assert _rows(r.stdout, "bound") == [{"n": 2}], r.stdout

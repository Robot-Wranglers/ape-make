"""Pins the graph library: a json document compiled to Cypher into a cypher workspace.

A document round-trips through load and dump, the bare-map sugar normalizes to the same
document, the workspace answers the cypher verbs afterward, a second document merges in by
id, a bad document is refused at the define, and an owned backing carries the graph to
another make.
"""

import json

import pytest

from conftest import sh

DOC = ('{"nodes": {"ann": {"label": "Person", "age": 30}, "bo": {"label": "Person", "age": 41}},'
       ' "edges": [{"source": "ann", "target": "bo", "type": "REPORTS_TO", "since": 2019}]}')
SUGAR = '{"ann": {"label": "Person", "age": 30, "REPORTS_TO": ["bo"]}, "bo": {"label": "Person", "age": 41}}'
MORE = ('{"nodes": {"bo": {"label": "Person", "age": 42}, "cy": {"label": "Person", "age": 52}},'
        ' "edges": [{"source": "bo", "target": "cy", "type": "REPORTS_TO"}]}')


def run(amk, tmp_path, lines):
  """A makefile of the lines after load graph, with the three documents held in variables, since a callform splits inline json at its commas."""
  mk = tmp_path / "graph.mk"
  mk.write_text("\n".join(["load graph", f"doc := {DOC}", f"sugar := {SUGAR}", f"more := {MORE}", *lines, "all:", "\t@true", ""]))
  return sh(amk, ["-f", str(mk)], cwd=tmp_path)


def value(stdout, key):
  line = next(l for l in stdout.splitlines() if l.startswith(key + "="))
  return json.loads(line.split("=", 1)[1])


def rows(stdout, key):
  lines = stdout.splitlines()
  start = next(i for i, l in enumerate(lines) if l.startswith(key + "="))
  out = [lines[start].split("=", 1)[1]]
  for l in lines[start + 1:]:
    if "=" in l and l.split("=", 1)[0].isidentifier():
      break
    out.append(l)
  return [json.loads(r) for r in out if r.strip()]


@pytest.mark.engines("cypher", "jq", "sqlite")
def test_a_document_round_trips_through_load_and_dump(amk, tmp_path):
  r = run(amk, tmp_path, [
    "@graph", "define org", DOC, "endef",
    "$(info norm=$(graph.normalize $(doc)))",
    "$(info dump=$(graph.dump org))",
  ])
  assert r.returncode == 0, r.stdout + r.stderr
  assert value(r.stdout, "dump") == value(r.stdout, "norm") == json.loads(DOC), r.stdout


@pytest.mark.engines("cypher", "jq", "sqlite")
def test_the_bare_map_sugar_is_the_same_document(amk, tmp_path):
  r = run(amk, tmp_path, [
    "@graph", "define org", SUGAR, "endef",
    "$(info norm=$(graph.normalize $(sugar)))",
    "$(info dump=$(graph.dump org))",
  ])
  assert r.returncode == 0, r.stdout + r.stderr
  want = json.loads(DOC)
  del want["edges"][0]["since"]
  assert value(r.stdout, "dump") == value(r.stdout, "norm") == want, r.stdout


@pytest.mark.engines("cypher", "jq", "sqlite")
def test_the_workspace_answers_the_cypher_verbs_afterward(amk, tmp_path):
  r = run(amk, tmp_path, [
    "@graph", "define org", DOC, "endef",
    "$(info boss=$(org.match (p {id: \"ann\"})-[:REPORTS_TO]->(m) RETURN m.id AS id))",
    "hired := $(org.create (:Person {id: \"cy\", age: 52}))",
    "$(info n=$(org.match (p:Person) RETURN count(p) AS n))",
  ])
  assert r.returncode == 0, r.stdout + r.stderr
  assert rows(r.stdout, "boss") == [{"id": "bo"}], r.stdout
  assert rows(r.stdout, "n") == [{"n": 3}], r.stdout


@pytest.mark.engines("cypher", "jq", "sqlite")
def test_a_second_document_merges_in_by_id(amk, tmp_path):
  r = run(amk, tmp_path, [
    "@graph", "define org", DOC, "endef",
    "merged := $(org.update $(graph.compile $(more)))",
    "$(info dump=$(graph.dump org))",
  ])
  assert r.returncode == 0, r.stdout + r.stderr
  got = value(r.stdout, "dump")
  assert sorted(got["nodes"]) == ["ann", "bo", "cy"], got
  assert got["nodes"]["bo"]["age"] == 42, got
  assert len(got["edges"]) == 2, got


@pytest.mark.engines("cypher", "jq", "sqlite")
@pytest.mark.parametrize("doc,said", [
  ('{"nodes": {"a": {}}, "edges": [{"source": "a", "target": "zz", "type": "TO"}]}', "not a node"),
  ('{"nodes": {"a": {"label": "Bad Label"}}, "edges": []}', "schema"),
  ('{"nodes": {"a": {"bad-key": 1}}, "edges": []}', "identifier"),
])
def test_a_bad_document_is_refused(amk, tmp_path, doc, said):
  r = run(amk, tmp_path, ["@graph", "define org", doc, "endef"])
  assert r.returncode != 0, r.stdout + r.stderr
  assert said in r.stderr or said in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("cypher", "jq", "sqlite")
def test_an_owned_backing_carries_the_graph_to_another_make(amk, tmp_path):
  back = tmp_path / "org.db"
  first = run(amk, tmp_path, [f"@graph {{owned={back}}}", "define org", DOC, "endef"])
  assert first.returncode == 0, first.stdout + first.stderr
  mk = tmp_path / "again.mk"
  mk.write_text("\n".join([
    "load graph",
    f"$(graph.create org, owned={back})",
    "$(info dump=$(graph.dump org))",
    "all:", "\t@true", "",
  ]))
  second = sh(amk, ["-f", str(mk)], cwd=tmp_path)
  assert second.returncode == 0, second.stdout + second.stderr
  assert value(second.stdout, "dump") == json.loads(DOC), second.stdout

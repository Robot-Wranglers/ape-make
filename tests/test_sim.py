"""Pins the @sim decorator: a graph, a trilog workspace and a tuple space under one name.

Each key of the define seeds its workspace and a key left out makes it empty; afterward the
three answer their own engines' verbs and handles under the dotted names. Rules may be one
text or a list, the rules workspace holds the event calculus ahead of them, and a key the
schema does not know is refused at the define.
"""

import json

import pytest

from conftest import sh

WORLD = "\n".join([
  "@sim",
  "define world",
  "  {",
  '    graph: {"ann": {"label": "Person", "KNOWS": ["bo"]}, "bo": {"label": "Person"}},',
  '    rules: "likes(ann, bo). friend(X, Y) :- likes(X, Y).",',
  '    events: {"seed": [["tick", 1]]}',
  "  }",
  "endef",
])


def run(amk, tmp_path, lines):
  mk = tmp_path / "sim.mk"
  mk.write_text("\n".join(["load dsys/sim", *lines, "all:", "\t@true", ""]))
  return sh(amk, ["-s", "-f", str(mk)], cwd=tmp_path)


def value(stdout, key):
  line = next(l for l in stdout.splitlines() if l.startswith(key + "="))
  return line.split("=", 1)[1]


@pytest.mark.engines("cypher", "jq", "trilog", "sqlite")
def test_each_key_seeds_its_workspace(amk, tmp_path):
  r = run(amk, tmp_path, [
    WORLD,
    "$(info knows=$(world.graph.match (a)-[:KNOWS]->(b) RETURN b.id AS id))",
    "$(info friend=$(world.rules.findall friend, ann))",
    "$(info tick=$(world.events.read tick, ?))",
  ])
  assert r.returncode == 0, r.stdout + r.stderr
  assert json.loads(value(r.stdout, "knows")) == {"id": "bo"}, r.stdout
  assert json.loads(value(r.stdout, "friend")) == ["bo"], r.stdout
  assert json.loads(value(r.stdout, "tick"))["t"] == ["tick", 1], r.stdout


@pytest.mark.engines("cypher", "jq", "trilog", "sqlite")
def test_a_key_left_out_makes_an_empty_workspace(amk, tmp_path):
  r = run(amk, tmp_path, [
    "@sim", "define world", "endef",
    "$(info nodes=$(graph.dump world.graph))",
    "$(info clauses=$(world.rules.get current_predicate(holdsAt/N)))",
    "$(info tuples=[$(strip $(world.events.all))])",
    "made := $(world.graph.create (:T {id: \"t\"}))",
    "told := $(world.rules.load fact(1).)",
    "put := $(world.events.out tick, 1)",
    "$(info after=$(world.graph.match (t:T) RETURN t.id AS id) $(world.rules.findall fact) $(world.events.read tick, ?))",
  ])
  assert r.returncode == 0, r.stdout + r.stderr
  assert json.loads(value(r.stdout, "nodes")) == {"nodes": {}, "edges": []}, r.stdout
  assert json.loads(value(r.stdout, "clauses")) == {"N": 2}, r.stdout
  assert value(r.stdout, "tuples") == "[]", r.stdout
  assert '{"id":"t"}' in value(r.stdout, "after") and "[1]" in value(r.stdout, "after"), r.stdout


@pytest.mark.engines("cypher", "jq", "trilog", "sqlite")
def test_rules_may_be_a_list_of_texts(amk, tmp_path):
  r = run(amk, tmp_path, [
    "@sim", "define world",
    '  {rules: ["p(1).", "p(2).", "q(X) :- p(X)."]}',
    "endef",
    "$(info q=$(world.rules.findall q))",
  ])
  assert r.returncode == 0, r.stdout + r.stderr
  assert json.loads(value(r.stdout, "q")) == [1, 2], r.stdout


@pytest.mark.engines("cypher", "jq", "trilog", "sqlite")
def test_the_rules_workspace_speaks_the_event_calculus(amk, tmp_path):
  r = run(amk, tmp_path, [
    "@sim", "define world",
    "  {rules: [",
    '    "initially(at(hall)).",',
    '    "happens(enter(kitchen), 1).",',
    '    "initiates(enter(R), at(R), _).",',
    '    "terminates(enter(R), at(Q), T) :- holdsAt(at(Q), T), \\\\+ R = Q."',
    "  ]}",
    "endef",
    "$(info before=$(world.rules.get holdsAt(F, 1)))",
    "$(info after=$(world.rules.get holdsAt(F, 2)))",
    "$(info host=$(words $(trilog.event_calculus)))",
    "again := $(world.rules.load $(trilog.event_calculus) initially(at(study)).)",
    "$(info kept=$(world.rules.get holdsAt(F, 1)))",
  ])
  assert r.returncode == 0, r.stdout + r.stderr
  assert json.loads(value(r.stdout, "before"))["F"] == {"functor": "at", "args": ["hall"]}, r.stdout
  assert json.loads(value(r.stdout, "after"))["F"] == {"functor": "at", "args": ["kitchen"]}, r.stdout
  assert int(value(r.stdout, "host")) > 20, r.stdout
  assert json.loads(value(r.stdout, "kept"))["F"] == {"functor": "at", "args": ["study"]}, r.stdout


@pytest.mark.engines("cypher", "jq", "trilog", "sqlite")
def test_an_unknown_key_is_refused_at_the_define(amk, tmp_path):
  r = run(amk, tmp_path, ["@sim", "define world", '  {agents: []}', "endef"])
  assert r.returncode != 0, r.stdout + r.stderr
  assert "schema" in r.stderr, r.stderr

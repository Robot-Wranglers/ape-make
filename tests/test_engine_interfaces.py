"""Pins the engine interfaces: every builtin name exists for every engine and refuses what the row lacks.

A row has a command line and at most one kept-state interface. A name the interface does not
answer is a fatal error naming the engine, through the builtin, `.ns`, or a handle alike. The
workspace members carry their contracts: sqlite's get refuses a write, and a failed load leaves
the database as it was.
"""

import pytest

from conftest import sh


def _run(amk, tmp_path, lines):
  mk = tmp_path / "probe.mk"
  mk.write_text("\n".join(lines + ["all:", "\t@echo done", ""]))
  return sh(amk, ["-s", "-f", str(mk), "all"], cwd=tmp_path)


@pytest.mark.engines("awk")
def test_an_engine_with_no_kept_state_refuses_ns(amk, tmp_path):
  r = _run(amk, tmp_path, ["$(awk.ns W, create)"])
  assert r.returncode != 0, r.stdout + r.stderr
  assert "awk has no state or workspace interface" in r.stderr, r.stderr


@pytest.mark.engines("awk")
def test_an_engine_with_no_kept_state_refuses_import(amk, tmp_path):
  r = _run(amk, tmp_path, ["$(awk.import W, [])"])
  assert r.returncode != 0, r.stdout + r.stderr
  assert "awk has no state or workspace interface" in r.stderr, r.stderr


@pytest.mark.engines("sqlite")
def test_a_workspace_refuses_a_state_operation_by_builtin(amk, tmp_path):
  r = _run(amk, tmp_path, ["x := $(sqlite.exec 1)"])
  assert r.returncode != 0, r.stdout + r.stderr
  assert "sqlite has no such operation; one of get update load" in r.stderr, r.stderr


@pytest.mark.engines("jq", "lua")
@pytest.mark.parametrize("line, message", [
  ("x := $(jq.exec .)", "jq has no such operation; one of get update load"),
  ("x := $(lua.get .)", "lua has no such operation; one of exec import"),
])
def test_a_builtin_outside_the_interface_refuses(amk, tmp_path, line, message):
  r = _run(amk, tmp_path, [line])
  assert r.returncode != 0, r.stdout + r.stderr
  assert message in r.stderr, r.stderr


@pytest.mark.engines("sqlite")
def test_a_workspace_refuses_a_state_operation_by_handle(amk, tmp_path):
  r = _run(amk, tmp_path, ["$(sqlite.ns W, create)", "x := $(W.exec 1)"])
  assert r.returncode != 0, r.stdout + r.stderr
  assert "sqlite has no such operation; one of get update load" in r.stderr, r.stderr


@pytest.mark.engines("lua")
def test_a_state_refuses_a_workspace_operation_by_handle(amk, tmp_path):
  r = _run(amk, tmp_path, ["$(lua.ns W, create)", "x := $(W.get 1)"])
  assert r.returncode != 0, r.stdout + r.stderr
  assert "lua has no such operation; one of exec import" in r.stderr, r.stderr


@pytest.mark.engines("sqlite")
def test_sqlite_get_refuses_a_write(amk, tmp_path):
  r = _run(amk, tmp_path, [
    "$(sqlite.ns W, create)",
    "$(W.update CREATE TABLE t(k))",
    "x := $(W.get INSERT INTO t VALUES(1))",
    "$(info n=$(W.get SELECT count(*) AS n FROM t))",
  ])
  assert "a statement that writes belongs in update" in r.stderr, r.stderr
  assert 'n={"n":0}' in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("sqlite")
def test_sqlite_load_that_fails_leaves_the_database(amk, tmp_path):
  r = _run(amk, tmp_path, [
    "$(sqlite.ns W, create)",
    "$(W.update CREATE TABLE t(k); INSERT INTO t VALUES('kept'))",
    "$(W.load CREATE TABLE u(k); INSERT INTO nowhere VALUES(1))",
    "$(info rows=$(W.get SELECT k FROM t))",
  ])
  assert 'rows={"k":"kept"}' in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("sqlite")
def test_sqlite_load_replaces_a_table_of_the_same_name(amk, tmp_path):
  r = _run(amk, tmp_path, [
    "$(sqlite.ns W, create)",
    "$(W.update CREATE TABLE t(k); INSERT INTO t VALUES('old'))",
    "$(W.load CREATE TABLE t(k); INSERT INTO t VALUES('new'))",
    "$(info rows=$(W.get SELECT k FROM t))",
  ])
  assert 'rows={"k":"new"}' in r.stdout, r.stdout + r.stderr

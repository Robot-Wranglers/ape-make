"""Pins a failed workspace operation as a failure of the call that made it.

Pinned under jq and sqlite: a failed get or update through make stops the run at the
expansion with the makefile's line, through amk.call it raises in the caller, and jq's
exit-status option answers a false last output as status 1 without stopping make.
"""

import pytest

from conftest import sh

# Each engine's namespace w, and a get and an update that fail in it.
cases = {
  "jq": dict(create="$(jq.import w, {\"a\": 1})",
             get='error("get boom")', update='error("update boom")', reason="boom"),
  "sqlite": dict(create="$(sqlite.ns w, create)",
                 get="select * from nope", update="insert into nope values (1)", reason="no such table"),
}


def run(amk, tmp_path, lines):
  mk = tmp_path / "f.mk"
  mk.write_text("\n".join(lines + ["all:", "\t@echo ran", ""]))
  return sh(amk, ["-s", "-f", str(mk)], timeout=120)


@pytest.mark.parametrize("engine", cases)
@pytest.mark.parametrize("op", ["get", "update"])
def test_a_failed_operation_stops_make_at_the_expansion(amk, engines, tmp_path, engine, op):
  if engine not in engines:
    pytest.skip(f"needs {engine}")
  c = cases[engine]
  lines = [f"$(amk.require {engine})", c["create"], f"$(info {op}=[$(w.{op} {c[op]})])"]
  r = run(amk, tmp_path, lines)
  assert r.returncode != 0, r.stdout + r.stderr
  assert f"f.mk:3: *** w.{op}: {engine} {op} exited with status" in r.stderr, r.stderr
  assert c["reason"] in r.stderr, r.stderr
  assert f"{op}=[" not in r.stdout and "ran" not in r.stdout, r.stdout


@pytest.mark.parametrize("engine", cases)
def test_a_failed_operation_through_amk_call_raises_in_the_caller(amk, engines, tmp_path, engine):
  if engine not in engines or "lua" not in engines:
    pytest.skip(f"needs {engine} and lua")
  c = cases[engine]
  lines = [f"$(amk.require {engine}, lua)", c["create"],
           "define prog",
           f'  local ok, e = pcall(amk.call, "w.get", {c["get"]!r})',
           '  print(ok and "answered" or ("raised " .. e))',
           "endef",
           "$(info $(lua.exec* prog))"]
  r = run(amk, tmp_path, lines)
  assert r.returncode == 0, r.stdout + r.stderr
  assert f"raised amk.call: w.get: {engine} get exited with status" in r.stdout, r.stdout
  assert "ran" in r.stdout, r.stdout


@pytest.mark.engines("jq")
def test_jq_exit_status_option_answers_without_stopping_make(amk, tmp_path):
  lines = ["$(amk.require jq)", '$(jq.import w, {"a": false})',
           "$(info a=[$(w.get -e .a)] status=[$(.SHELLSTATUS)])"]
  r = run(amk, tmp_path, lines)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "a=[false] status=[1]" in r.stdout and "ran" in r.stdout, r.stdout

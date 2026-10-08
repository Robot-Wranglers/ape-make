"""Pins `amk.fxn!`, which promotes a variable to a make function called as `call` would call it.

Pinned are the at line above a define, the functional form on a variable of the same name,
a new name with bound leading arguments, `amk.args` inside a promoted body, the refusals,
and a guest reaching a promoted function through `amk.call`.
"""

import pytest

from conftest import sh


def run(amk, tmp_path, body):
  mk = tmp_path / "fxn.mk"
  mk.write_text(body + "\nprobe:\n\t@true\n")
  return sh(amk, ["-s", "-f", str(mk), "probe"], cwd=tmp_path, timeout=120)


def test_the_at_line_promotes_a_define(amk, tmp_path):
  r = run(amk, tmp_path, "@amk.fxn!\ndefine greet\nhello $(1), from $(2)\nendef\n$(info got=[$(greet world,amk)])")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "got=[hello world, from amk]" in r.stdout, r.stdout + r.stderr


def test_a_variable_keeps_its_name_and_call_still_reaches_it(amk, tmp_path):
  r = run(amk, tmp_path, "pair = $(1)+$(2)\n$(amk.fxn! pair)\n$(info got=[$(pair a,b)] [$(call pair,c,d)])")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "got=[a+b] [c+d]" in r.stdout, r.stdout + r.stderr


def test_a_new_name_binds_leading_arguments(amk, tmp_path):
  r = run(amk, tmp_path, "verb = $(1):$(2):$(3)\n$(amk.fxn! jobs.read, verb, jobs, read)\n$(info got=[$(jobs.read k)])")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "got=[jobs:read:k]" in r.stdout, r.stdout + r.stderr


def test_bound_arguments_are_trimmed_like_the_name_and_variable(amk, tmp_path):
  r = run(amk, tmp_path, "verb = [$(1)]:[$(2)]:[$(3)]\n$(amk.fxn! jobs.read, verb, jobs, read)\n$(info got=$(jobs.read k))")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "got=[jobs]:[read]:[k]" in r.stdout, r.stdout + r.stderr


def test_caller_arguments_are_trimmed(amk, tmp_path):
  r = run(amk, tmp_path, "pair = [$(1)]+[$(2)]\n$(amk.fxn! pair)\n$(info got=$(pair a , b ))")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "got=[a]+[b]" in r.stdout, r.stdout + r.stderr


def test_amk_args_sees_the_bound_and_given_arguments(amk, tmp_path):
  r = run(amk, tmp_path, "j = $(amk.args)\n$(amk.fxn! both, j, x)\n$(info got=[$(both a, b)])")
  assert r.returncode == 0, r.stdout + r.stderr
  assert 'got=[["x","a","b"]]' in r.stdout, r.stdout + r.stderr


@pytest.mark.parametrize("body,error", [
  ("v = 1\n$(amk.fxn! abspath, v)", "abspath is a make function already"),
  ("v = 1\n$(amk.fxn! w, v)\n$(amk.fxn! w, v)", "w is a make function already"),
  ("$(amk.fxn! nope)", "nope names no variable"),
  ("$(amk.fxn! w, nope)", "nope names no variable or function"),
])
def test_a_promotion_refuses(amk, tmp_path, body, error):
  r = run(amk, tmp_path, body)
  assert r.returncode != 0, r.stdout + r.stderr
  assert error in r.stderr, r.stdout + r.stderr


def test_a_guest_calls_a_promoted_function(amk, engines, tmp_path):
  if "lua" not in engines:
    pytest.skip("this amk carries no lua")
  r = run(amk, tmp_path, "verb = $(1):$(2)\n$(amk.fxn! jobs.read, verb, jobs)\n$(info got=[$(lua.exec io.write(amk.call('jobs.read', 'k')))])")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "got=[jobs:k]" in r.stdout, r.stdout + r.stderr

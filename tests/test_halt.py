"""Pins the halt request.

A recipe sends `halt` on the call channel and its own make stops: the recipe's remaining
lines and the command line's remaining goals never run, nothing is printed on stderr,
and the process leaves with status 112. A sub-make that halts halts its parent the same
way, so a chain ends at every level; a spawned job that halts reports that status to its
spawner; a guest's exit_code still wins.
"""

import pytest

from conftest import sh

HALT = 112

program = "\n".join([
  "SHELL := bash",
  "stop:",
  "\t@echo before; source amk.sh; amk.call halt; echo \"st=$$?\"",
  "\t@echo not-this-line",
  "after:",
  "\t@echo not-this-goal",
  "outer:",
  "\t@echo outer; $(MAKE) -s -f $(firstword $(MAKEFILE_LIST)) stop; echo not-after-inner",
  "quiet:",
  "\t@source amk.sh; amk.call halt",
  "killed:",
  "\t@echo before; ( source amk.sh; amk.call halt; kill -KILL $$$$ ); echo not-this-command",
  "spawned:",
  "\t@echo job=[$(lua.exec local p = amk.spawn({'quiet', 'after'}) local r = amk.wait(p) print(r.code))]",
  "marked:",
  "\t@echo m=[$(lua.exec amk.exit_code(7))]; source amk.sh; amk.call halt",
  "",
])


@pytest.fixture
def prog(tmp_path):
  mk = tmp_path / "halt.mk"
  mk.write_text(program)
  return mk


def test_a_halt_drops_the_rest_of_the_recipe_and_the_goals(amk, prog):
  r = sh(amk, ["-s", "-f", str(prog), "stop", "after"], timeout=120)
  assert r.returncode == HALT, r.stdout + r.stderr
  assert r.stdout == "before\nst=0\n", r.stdout + r.stderr
  assert r.stderr == "", r.stderr


def test_a_halted_recipe_may_end_its_shell_by_signal(amk, prog):
  r = sh(amk, ["-s", "-f", str(prog), "killed", "after"], timeout=120)
  assert r.returncode == HALT, r.stdout + r.stderr
  assert r.stdout == "before\n", r.stdout + r.stderr
  assert r.stderr == "", r.stderr


def test_a_halting_sub_make_halts_its_parent(amk, prog):
  r = sh(amk, ["-s", "-f", str(prog), "outer", "after"], timeout=120)
  assert r.returncode == HALT, r.stdout + r.stderr
  assert r.stdout == "outer\nbefore\nst=0\n", r.stdout + r.stderr
  assert r.stderr == "", r.stderr


@pytest.mark.engines("lua")
def test_a_halting_job_reports_the_status_to_its_spawner(amk, prog):
  r = sh(amk, ["-s", "-f", str(prog), "spawned"], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout == f"job=[{HALT}]\n", r.stdout + r.stderr


@pytest.mark.engines("lua")
def test_a_guests_exit_code_wins_over_a_halt(amk, prog):
  r = sh(amk, ["-s", "-f", str(prog), "marked", "after"], timeout=120)
  assert r.returncode == 7, r.stdout + r.stderr
  assert "not-this-goal" not in r.stdout, r.stdout

"""Pins the spawn api.

`amk.spawn(goals)` forks this parsed image to run a goal list and `amk.wait(pid)` collects
it. Pinned: two spawns report their own statuses, a failing goal reports failed with make's
code, a child make's own reaping saw first under -j still reaches wait, and a request served
by a zygote can spawn.
"""

import pytest

from conftest import sh

paired = "\n".join([
  "seed := $(lua.persistent)",
  "all:",
  "\t@echo result=[$(lua.persistent a = amk.spawn({'one'}) b = amk.spawn({'two'}) local rb = amk.wait(b) print(amk.wait(a).status .. ' ' .. rb.status .. ' ' .. rb.code))]",
  "one:",
  "\t@echo one",
  "two:",
  "\t@exit 3",
  "",
])

parked = "\n".join([
  "seed := $(lua.persistent)",
  "all: slow fast last",
  "slow:",
  "\t@sleep 0.4",
  "fast:",
  "\t@echo fast $(lua.persistent p = amk.spawn({'one'}))",
  "last: fast slow",
  "\t@echo r=$(lua.persistent print(amk.wait(p).status))",
  "one:",
  "\t@sleep 0.1",
  "",
])

served = "\n".join([
  "seed := $(lua.persistent)",
  "show:",
  "\t@echo r=$(lua.persistent print(amk.wait(amk.spawn({'one'})).status))",
  "one:",
  "\t@echo one",
  "",
])


@pytest.mark.engines("lua")
def test_each_spawn_reports_its_own_status(amk, tmp_path):
  mk = tmp_path / "paired.mk"
  mk.write_text(paired)
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "one" in r.stdout, r.stdout
  assert "result=[success failed 2]" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("lua")
def test_a_child_make_reaped_first_still_reaches_wait(amk, tmp_path):
  mk = tmp_path / "parked.mk"
  mk.write_text(parked)
  r = sh(amk, ["-s", "-j2", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "r=success" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("lua")
def test_a_served_request_can_spawn(amk, tmp_path, zygote):
  mk = tmp_path / "served.mk"
  mk.write_text(served)
  sock = zygote(["-f", str(mk)], cwd=tmp_path)
  r = sh(amk, ["--client", str(sock), "show"], cwd=tmp_path, timeout=60)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "one" in r.stdout and "r=success" in r.stdout, r.stdout + r.stderr


goals = "\n".join([
  "seed := $(lua.persistent)",
  "all:",
  "\t@: $(lua.persistent amk.wait(amk.spawn({'one', 'two'})))",
  "one:",
  "\t@echo one sees [$(MAKECMDGOALS)]",
  "two:",
  "\t@echo two sees [$(MAKECMDGOALS)]",
  "",
])


@pytest.mark.engines("lua")
def test_a_spawned_job_sees_its_own_goals(amk, tmp_path):
  """The spawn runs while a recipe expands; its goals must reach every target, not the expanding one's set."""
  mk = tmp_path / "goals.mk"
  mk.write_text(goals)
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "one sees [ one two]" in r.stdout, r.stdout + r.stderr
  assert "two sees [ one two]" in r.stdout, r.stdout + r.stderr

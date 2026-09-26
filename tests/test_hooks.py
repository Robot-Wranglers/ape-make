"""Pins the hooks.

make announces the goal list and each recipe's start and end to every engine with a hook
entry. Lua hears them as `amk.on.<event>(e)` in its persistent state. Pinned: the three
events fire in order with the target and status, a failing recipe under -k reports as
failed with its exit code, and a hook that errors reports on stderr without stopping make.
"""

import pytest

from conftest import sh

subscribe = " ".join([
  "log = {} n = 0",
  "local function note(s) n = n + 1 log[n] = s end",
  "amk.on.goals = function(e) note(e.event .. '=' .. e.target) end",
  "amk.on.recipe_start = function(e) note(e.target .. '?') end",
  "amk.on.recipe_end = function(e) note(e.target .. ':' .. e.status .. '/' .. e.code) end",
])

dump = "local s = '' for i in pairs(log) do s = s .. log[i] .. ' ' end print(s)"

makefile = "\n".join([
  "seed := $(lua.persistent %s)" % subscribe,
  "all: a b c",
  "a:",
  "\t@true",
  "b:",
  "\t@exit 3",
  "c:",
  "\t@echo [$(lua.persistent %s)]" % dump,
  "",
])

erring = "\n".join([
  "seed := $(lua.persistent amk.on.recipe_start = function(e) error('no ' .. e.target) end)",
  "all:",
  "\t@echo ran",
  "",
])


@pytest.mark.engines("lua")
def test_events_fire_in_order(amk, tmp_path):
  mk = tmp_path / "hooks.mk"
  mk.write_text(makefile)
  r = sh(amk, ["-s", "-k", "-f", str(mk)], timeout=120)
  assert r.returncode == 2, r.stdout + r.stderr
  assert "[goals=all a? a:success/0 b? b:failed/3 ]" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("lua")
def test_a_hook_error_reports_and_make_goes_on(amk, tmp_path):
  mk = tmp_path / "erring.mk"
  mk.write_text(erring)
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "ran", r.stdout
  assert "lua hook recipe_start" in r.stderr and "no all" in r.stderr, r.stderr

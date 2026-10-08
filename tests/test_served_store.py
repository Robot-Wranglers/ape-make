"""Pins which store a served request writes.

A request carries the call pair its caller's recipe holds, so a served child forwards every
store call up it and the run has one store. Pinned: a recipe's request updates a value its
caller then reads, the same two served levels deep, a client with no pair is an owner from
the parse, a backgrounded client whose recipe ended gets a nonzero status and an error line
rather than a store of its own, and a cold make's request joins the cold make's store.
"""

import pytest

from conftest import sh

ask = "printf '%s\\n' \"$(1)\" >&$$AMK_CALL && read -r st n <&$$AMK_REPLY && { [ \"$$n\" = 0 ] || IFS= read -r $(2) <&$$AMK_REPLY; }"

program = "\n".join([
  "SHELL := bash",
  "define ask",
  ask,
  "endef",
  "$(jq.ns S, create)",
  "seed := $(S.update [1,2,3])",
  "client := $(amk) --client $(sock)",
  "outer:",
  "\t@$(client) grow && $(call ask,get S length,r) && echo \"outer=[$$r]\"",
  "grow:",
  "\t@$(call ask,update S . + [9],r); echo \"grow=[$$st]\"",
  "deep:",
  "\t@$(client) outer && $(call ask,get S length,r) && echo \"deep=[$$r]\"",
  "bg:",
  "\t@$(client) later &",
  "later:",
  "\t@sleep 0.5; $(call ask,get S length,r); echo \"later=[$$st $$n]\"",
  "",
])


@pytest.fixture
def served(amk, tmp_path, zygote, sock):
  """The program parked on a zygote, with the binary and the socket named to its recipes."""
  mk = tmp_path / "served.mk"
  mk.write_text(program)
  zygote(["-s", "-f", str(mk), f"amk={amk}", f"sock={sock}"], cwd=tmp_path)
  return mk


@pytest.mark.engines("jq")
def test_a_recipes_request_updates_the_callers_store(amk, tmp_path, served, sock):
  r = sh(amk, ["--client", str(sock), "outer"], cwd=tmp_path, timeout=60)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "grow=[0]\nouter=[4]" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("jq")
def test_a_request_two_served_levels_deep_reaches_the_top(amk, tmp_path, served, sock):
  r = sh(amk, ["--client", str(sock), "deep"], cwd=tmp_path, timeout=60)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "grow=[0]\nouter=[4]\ndeep=[4]" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("jq")
def test_a_client_with_no_pair_is_an_owner_from_the_parse(amk, tmp_path, served, sock):
  for _ in range(2):
    r = sh(amk, ["--client", str(sock), "outer"], cwd=tmp_path, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "outer=[4]" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("jq")
def test_a_backgrounded_client_whose_recipe_ended_fails_loudly(amk, tmp_path, served, sock):
  r = sh(amk, ["--client", str(sock), "bg"], cwd=tmp_path, timeout=60)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "later=[2 0]" in r.stdout, r.stdout + r.stderr
  assert "no reply from the store's owner" in r.stderr, r.stdout + r.stderr


@pytest.mark.engines("jq")
def test_a_cold_makes_request_joins_the_cold_makes_store(amk, tmp_path, served, sock):
  r = sh(amk, ["-s", "-f", str(served), f"amk={amk}", f"sock={sock}", "outer"], cwd=tmp_path, timeout=60)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "grow=[0]\nouter=[4]" in r.stdout, r.stdout + r.stderr

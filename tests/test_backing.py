"""Pins the backing modes of a named value.

A store namespace may declare a backing at creation, a mode word then a path: `run` keeps
the value in the store alone, `owned` loads the file once and writes every update through,
`shared` also reloads when the file changed since the last load. Pinned: each mode's
file behavior, a conflicting second declaration, a sub-make's repeat, and the channel form.
"""

import json

import pytest

from conftest import sh

ask = "printf '%s\\n' \"$(1)\" >&$$AMK_CALL && read -r st n <&$$AMK_REPLY && { [ \"$$n\" = 0 ] || IFS= read -r $(2) <&$$AMK_REPLY; }"

program = "\n".join([
  "SHELL := bash",
  "define ask",
  ask,
  "endef",
  "$(jq.ns R, create, run)",
  "$(jq.ns O, create, owned $(dir)/o.json)",
  "$(jq.ns H, create, shared $(dir)/h.json)",
  "run:",
  "\t@$(call ask,update R [1],r); [ -e $(dir)/r.json ] && echo run=file || echo run=nofile",
  "owned:",
  "\t@$(call ask,update O [1],r); echo \"file=$$(cat $(dir)/o.json)\"; printf '[9,9]' > $(dir)/o.json",
  "\t@$(call ask,get O length,n); echo \"owned=$$n\"",
  "shared:",
  "\t@$(call ask,update H [1],r); printf '[9,9]' > $(dir)/h.json; sleep 1.1",
  "\t@$(call ask,get H length,n); echo \"shared=$$n\"; $(call ask,get H length,n); echo \"again=$$n\"",
  "\t@$(call ask,update H . + [3],r); echo \"file=$$(cat $(dir)/h.json)\"",
  "conflict:",
  "\t@source amk.sh; st=0; amk.call 'create O shared $(dir)/o.json' || st=$$?; echo \"st=$$st\"; same=0; amk.call 'create O owned $(dir)/o.json' || same=$$?; echo \"same=$$same\"",
  "\t@source amk.sh; amk.call 'create N owned $(dir)/n.json' && $(call ask,update N 7,r) && echo \"n=$$(cat $(dir)/n.json)\"",
  "sub:",
  "\t@$(MAKE) -s -f $(firstword $(MAKEFILE_LIST)) dir=$(dir) grow && $(call ask,get O length,n) && echo \"sub=$$n\"",
  "grow:",
  "\t@$(call ask,update O . + [2],r)",
  "",
])


@pytest.fixture
def prog(tmp_path):
  mk = tmp_path / "backing.mk"
  mk.write_text(program)
  return mk


def _run(amk, prog, goal, env=None):
  return sh(amk, ["-s", "-f", str(prog), f"dir={prog.parent}", goal], timeout=120, env=env)


@pytest.mark.engines("jq")
def test_run_leaves_no_file(amk, prog):
  r = _run(amk, prog, "run")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "run=nofile" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("jq")
def test_owned_mirrors_every_update_and_ignores_an_outside_write(amk, prog):
  r = _run(amk, prog, "owned")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "file=[1]\nowned=1" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("jq")
def test_shared_sees_an_outside_write_and_writes_through(amk, prog):
  r = _run(amk, prog, "shared")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "shared=2\nagain=2\nfile=[9,9,3]" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("jq")
def test_shared_does_not_reload_an_unchanged_file(amk, prog):
  r = _run(amk, prog, "shared", env={"AMK_DEBUG": "1"})
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stderr.count("amk: store: H loaded from") == 1, r.stdout + r.stderr


@pytest.mark.engines("jq")
def test_a_conflicting_declaration_fails_and_a_repeat_or_a_new_one_is_taken(amk, prog):
  r = _run(amk, prog, "conflict")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "st=2\nsame=0\nn=7" in r.stdout, r.stdout + r.stderr
  assert "O is backed as owned" in r.stderr, r.stdout + r.stderr
  assert json.loads((prog.parent / "n.json").read_text()) == 7


@pytest.mark.engines("jq")
def test_a_sub_makes_repeated_declaration_joins_the_owners_backing(amk, prog):
  r = _run(amk, prog, "sub")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "sub=1" in r.stdout, r.stdout + r.stderr
  assert json.loads((prog.parent / "o.json").read_text()) == [2], r.stdout + r.stderr

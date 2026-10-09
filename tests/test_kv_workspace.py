"""Pins the workspace row's contract with a second row.

kv is a workspace row whose value is key=value lines, shaped like a table. Pinned: a recipe
reaches a kv namespace through the request line a jq one takes, with the row chosen by the
owner; `dump` uses the row's whole program; an owned backing writes kv lines and loads them
back; `kv.import` seeds a namespace; the unknown-operation message lists the row's own ops.
"""

import pytest

from conftest import sh

ask = "printf '%s\\n' \"$(1)\" >&$$AMK_CALL && read -r st n <&$$AMK_REPLY && { [ \"$$n\" = 0 ] || IFS= read -r $(2) <&$$AMK_REPLY; }"

program = "\n".join([
  "SHELL := bash",
  "define ask",
  ask,
  "endef",
  "$(kv.ns K, create)",
  "$(kv.ns O, create, owned $(dir)/o.kv)",
  "$(jq.ns J, create)",
  "seed := $(K.update color red)",
  "jseed := $(J.update [1,2])",
  "@kv.import",
  "define T",
  "a=1",
  "b=2",
  "endef",
  "both:",
  "\t@$(call ask,get K color,r) && echo \"kv=[$$r]\" && $(call ask,get J length,r) && echo \"jq=[$$r]\"",
  "grow:",
  "\t@$(call ask,update K size 9,r); $(call ask,get K size,r); echo \"size=[$$r]\"",
  "dump:",
  "\t@source amk.sh; amk.call 'dump K' | tr '\\n' ' '; echo",
  "owned:",
  "\t@$(call ask,update O n 1,r); echo \"file=[$$(cat $(dir)/o.kv | tr '\\n' ' ')]\"",
  "imported:",
  "\t@$(call ask,get T b,r); echo \"b=[$$r]\"",
  "unknown:",
  "\t@$(call ask,drop K x,r); echo \"st=[$$st]\"",
  "",
])


@pytest.fixture
def mk(tmp_path):
  p = tmp_path / "kv.mk"
  p.write_text(program)
  return p


@pytest.mark.engines("kv", "jq")
def test_a_recipe_reaches_a_kv_and_a_jq_namespace_through_one_channel(amk, tmp_path, mk):
  r = sh(amk, ["-f", str(mk), f"dir={tmp_path}", "both", "grow"], cwd=tmp_path)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "kv=[red]\njq=[2]\nsize=[9]" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("kv", "jq")
def test_dump_prints_the_whole_value_with_the_rows_whole_program(amk, tmp_path, mk):
  r = sh(amk, ["-f", str(mk), f"dir={tmp_path}", "dump"], cwd=tmp_path)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "color=red" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("kv", "jq")
def test_an_owned_backing_writes_kv_lines(amk, tmp_path, mk):
  r = sh(amk, ["-f", str(mk), f"dir={tmp_path}", "owned"], cwd=tmp_path)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "file=[n=1 ]" in r.stdout, r.stdout + r.stderr
  assert (tmp_path / "o.kv").read_text() == "n=1\n"


@pytest.mark.engines("kv", "jq")
def test_kv_import_seeds_a_namespace_from_text(amk, tmp_path, mk):
  r = sh(amk, ["-f", str(mk), f"dir={tmp_path}", "imported"], cwd=tmp_path)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "b=[2]" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("kv", "jq")
def test_an_unknown_operation_lists_the_rows_own_ops(amk, tmp_path, mk):
  r = sh(amk, ["-f", str(mk), f"dir={tmp_path}", "unknown"], cwd=tmp_path)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "st=[2]" in r.stdout, r.stdout + r.stderr
  assert "unknown operation drop; one of get update load, dump, filter, create" in r.stderr, r.stderr

"""Pins the recipe-time call.

A recipe writes one request to the descriptor `AMK_CALL` names and reads the reply from
`AMK_REPLY`, a status and count line then that many output lines, answered from the jq
store while the shell runs. Pinned: a plain ask, a hundred takes ending at empty, an
answer partway through a long recipe, a sub-make's and a spawned job's update reaching the
parent, outputs arriving verbatim one per line, tagged callers in one pipeline, and filter.
"""

import pytest

from conftest import sh

ask = "printf '%s\\n' \"$(1)\" >&$$AMK_CALL && read -r st n <&$$AMK_REPLY && { [ \"$$n\" = 0 ] || IFS= read -r $(2) <&$$AMK_REPLY; }"

program = "\n".join([
  "SHELL := bash",
  "define ask",
  ask,
  "endef",
  "three := [1,2,3]",
  "seed := $(jq.persistent update S $(three))",
  "one:",
  "\t@$(call ask,get S length,r); echo \"r=[$$st $$n $$r]\"",
  "loop:",
  "\t@true $(jq.persistent update L [range(100)])",
  "\t@k=0; while :; do $(call ask,take L [.[:-1]$(,) .[-1]],top); [ \"$$st\" = 0 ] || exit 1; k=$$((k + 1)); $(call ask,get L length,len); [ \"$$len\" != 0 ] || break; done; $(call ask,dump L,left); echo \"takes=$$k last=$$top left=$$left\"",
  "slow:",
  "\t@sleep 0.3; $(call ask,get S .[0],v); echo \"v=$$v\"; sleep 0.2; echo done",
  "parent:",
  "\t@$(MAKE) -s -f $(firstword $(MAKEFILE_LIST)) child",
  "\t@$(call ask,get S length,r); echo \"parent=[$$r]\"",
  "child: child.update",
  "\t@echo \"sub=$(jq.persistent get S length)\"",
  "child.update:",
  "\t@$(call ask,update S . + [9],r); echo \"child=[$$st $$n]\"",
  "spawned:",
  "\t@echo job=[$(lua.persistent local p = amk.spawn({'worker'}) print(amk.wait(p).status))]",
  "\t@$(call ask,get S length,r); echo \"after=[$$r]\"",
  "worker: worker.update",
  "\t@echo \"sub=$(jq.persistent get S length)\"",
  "worker.update:",
  "\t@$(call ask,update S . + [8],r); echo \"worker=[$$st $$n]\"",
  "lines:",
  "\t@true $(jq.persistent update W $(words))",
  "\t@printf 'get W -r .[]\\n' >&$$AMK_CALL; read -r st n <&$$AMK_REPLY; echo \"head=[$$st $$n]\"; while [ $$n -gt 0 ]; do IFS= read -r l <&$$AMK_REPLY; echo \"[$$l]\"; n=$$((n - 1)); done",
  "\t@$(call ask,get W .[0],q); echo \"q=[$$q]\"",
  "tagged:",
  "\t@source amk.sh; printf '%s\\n' 5 1 4 | jq.pipe -s sort | jq.pipe -c .[1:]",
  "\t@source amk.sh; amk.call 'get S .[1]'; echo \"st=$$?\"",
  "filters:",
  "\t@source amk.sh; printf '1\\n2\\n' | jq.pipe -s add; printf 'null\\n' | jq.pipe -e . || echo \"e=$$?\"; printf '{}\\n' | jq.pipe --tab . || echo \"bad=$$?\"; jq.pipe -n --arg w hi '$$w' </dev/null; printf '{\"a\": \"x y\"}\\n' | jq.pipe -r .a",
  ", := ,",
  "words := [\"a b\", \"\", \"c\"]",
  "",
])


@pytest.fixture
def prog(tmp_path):
  mk = tmp_path / "call.mk"
  mk.write_text(program)
  return mk


@pytest.mark.engines("jq")
def test_a_recipe_asks_and_reads_a_reply(amk, prog):
  r = sh(amk, ["-s", "-f", str(prog), "one"], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "r=[0 1 3]" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("jq")
def test_a_hundred_takes_in_one_recipe_end_at_empty(amk, prog):
  r = sh(amk, ["-s", "-f", str(prog), "loop"], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "takes=100 last=0 left=[]" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("jq")
def test_a_request_during_a_long_recipe_is_answered(amk, prog):
  r = sh(amk, ["-s", "-f", str(prog), "slow"], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "v=1\ndone" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("jq")
def test_a_sub_makes_update_is_seen_by_its_parent(amk, prog):
  r = sh(amk, ["-s", "-f", str(prog), "parent"], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "child=[0 0]\nsub=4\nparent=[4]" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("jq", "lua")
def test_a_spawned_jobs_update_is_seen_by_its_parent(amk, prog):
  r = sh(amk, ["-s", "-f", str(prog), "spawned"], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "worker=[0 0]\nsub=4\njob=[success]\nafter=[4]" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("jq")
def test_outputs_arrive_verbatim_one_per_line(amk, prog):
  r = sh(amk, ["-s", "-f", str(prog), "lines"], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "head=[0 3]\n[a b]\n[]\n[c]\n" in r.stdout, r.stdout + r.stderr
  assert 'q=["a b"]' in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("jq")
def test_tagged_callers_in_one_pipeline_each_get_their_own_reply(amk, prog):
  r = sh(amk, ["-s", "-f", str(prog), "tagged"], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[4,5]\n2\nst=0\n" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("jq")
def test_filter_runs_the_tools_options_and_refuses_the_rest(amk, prog):
  r = sh(amk, ["-s", "-f", str(prog), "filters"], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "3\nnull\ne=1\nbad=2\n\"hi\"\nx y\n" in r.stdout, r.stdout + r.stderr
  assert "unsupported option --tab" in r.stderr, r.stderr

"""Pins the recipe-time ask, on a jq store and on a lua namespace.

A recipe writes one request to the descriptor `AMK_ASK` names and reads the reply from
`AMK_REPLY`, a status and count line then that many output lines, answered from the jq
store while the shell runs. Pinned are a plain ask, a hundred pops ending at empty, an answer
partway through a long recipe, a sub-make's and a spawned job's update reaching the parent,
outputs arriving verbatim one per line, tagged callers in one pipeline, filter, and load.
"""

import json

import pytest

from conftest import sh

ask = "printf '%s\\n' \"$(1)\" >&$$AMK_ASK && read -r st n <&$$AMK_REPLY && { [ \"$$n\" = 0 ] || IFS= read -r $(2) <&$$AMK_REPLY; }"

program = "\n".join([
  "SHELL := bash",
  "define ask",
  ask,
  "endef",
  "three := [1,2,3]",
  "$(jq.ns S, create)",
  "$(jq.ns L, create)",
  "$(jq.ns W, create)",
  "seed := $(S.update $(three))",
  "one:",
  "\t@$(call ask,get S length,r); echo \"r=[$$st $$n $$r]\"",
  "loop:",
  "\t@true $(L.update [range(100)])",
  "\t@k=0; while :; do $(call ask,update L .[:-1]$(,) .[-1],top); [ \"$$st\" = 0 ] || exit 1; k=$$((k + 1)); $(call ask,get L length,len); [ \"$$len\" != 0 ] || break; done; $(call ask,dump L,left); echo \"pops=$$k last=$$top left=$$left\"",
  "slow:",
  "\t@sleep 0.3; $(call ask,get S .[0],v); echo \"v=$$v\"; sleep 0.2; echo done",
  "parent:",
  "\t@$(MAKE) -s -f $(firstword $(MAKEFILE_LIST)) child",
  "\t@$(call ask,get S length,r); echo \"parent=[$$r]\"",
  "child: child.update",
  "\t@echo \"sub=$(S.get length)\"",
  "child.update:",
  "\t@$(call ask,update S . + [9],r); echo \"child=[$$st $$n]\"",
  "spawned:",
  "\t@echo job=[$(lua.exec local p = amk.spawn('worker') print(require('dkjson').decode(amk.wait(p)).status))]",
  "\t@$(call ask,get S length,r); echo \"after=[$$r]\"",
  "worker: worker.update",
  "\t@echo \"sub=$(S.get length)\"",
  "worker.update:",
  "\t@$(call ask,update S . + [8],r); echo \"worker=[$$st $$n]\"",
  "lines:",
  "\t@true $(W.update $(words))",
  "\t@printf 'get W -r .[]\\n' >&$$AMK_ASK; read -r st n <&$$AMK_REPLY; echo \"head=[$$st $$n]\"; while [ $$n -gt 0 ]; do IFS= read -r l <&$$AMK_REPLY; echo \"[$$l]\"; n=$$((n - 1)); done",
  "\t@$(call ask,get W .[0],q); echo \"q=[$$q]\"",
  "tagged:",
  "\t@source amk.sh; printf '%s\\n' 5 1 4 | jq.pipe -s sort | jq.pipe -c .[1:]",
  "\t@source amk.sh; amk.ask 'get S .[1]'; echo \"st=$$?\"",
  "filters:",
  "\t@source amk.sh; printf '1\\n2\\n' | jq.pipe -s add; printf 'null\\n' | jq.pipe -e . || echo \"e=$$?\"; printf '{}\\n' | jq.pipe --tab . || echo \"bad=$$?\"; jq.pipe -n --arg w hi '$$w' </dev/null; printf '{\"a\": \"x y\"}\\n' | jq.pipe -r .a",
  "loads:",
  "\t@$(call ask,load M $(src),r); echo \"load=[$$st $$n]\"; $(call ask,get M .n,v); echo \"n=[$$v]\"; $(call ask,dump M,d); echo \"dump=[$$d]\"",
  "\t@$(call ask,load M $(src).absent,r); echo \"absent=[$$st]\"; $(call ask,take M .,r); echo \"take=[$$st]\"; $(call ask,get M .n,v); echo \"still=[$$v]\"",
  ", := ,",
  "words := [\"a b\", \"\", \"c\"]",
  "",
])


@pytest.fixture
def prog(tmp_path):
  mk = tmp_path / "ask.mk"
  mk.write_text(program)
  return mk


@pytest.mark.engines("jq")
def test_a_recipe_asks_and_reads_a_reply(amk, prog):
  r = sh(amk, ["-s", "-f", str(prog), "one"], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "r=[0 1 3]" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("jq")
def test_a_hundred_pops_in_one_recipe_end_at_empty(amk, prog):
  r = sh(amk, ["-s", "-f", str(prog), "loop"], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "pops=100 last=0 left=[]" in r.stdout, r.stdout + r.stderr


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


@pytest.mark.engines("jq")
def test_load_reads_a_file_on_the_channel_and_a_bad_request_costs_the_value_nothing(amk, prog, tmp_path):
  src = tmp_path / "m.json"
  src.write_text(json.dumps({"n": 5}))
  r = sh(amk, ["-s", "-f", str(prog), "loads", f"src={src}"], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert 'load=[0 0]\nn=[5]\ndump=[{"n":5}]\n' in r.stdout, r.stdout + r.stderr
  assert "absent=[2]\ntake=[2]\nstill=[5]\n" in r.stdout, r.stdout + r.stderr
  assert "cannot read" in r.stderr and 'unknown operation "take" on namespace "M" (jq)' in r.stderr, r.stderr


lua_program = "\n".join([
  "SHELL := bash",
  "$(lua.ns work, create)",
  "$(work.exec n = 1)",
  "bump:",
  "\t@source amk.sh; amk.ask 'exec work n = n + 1'; echo \"bump=[$$?]\"; amk.ask 'exec work print(n)'",
  "after: bump",
  "\t@echo \"after=[$(work.exec print(n))]\"",
  "imported:",
  "\t@source amk.sh; amk.ask 'import work y = 5'",
  "credited: imported",
  "\t@echo \"vars=[$(lua.__vars__)] y=[$(y)]\"",
  "refused:",
  "\t@source amk.sh; amk.ask 'get work .' || echo \"get=[$$?]\"",
  "",
])


@pytest.fixture
def lua_prog(tmp_path):
  mk = tmp_path / "lua-ask.mk"
  mk.write_text(lua_program)
  return mk


@pytest.mark.engines("lua")
def test_an_exec_on_the_channel_runs_in_the_owners_state(amk, lua_prog):
  r = sh(amk, ["-s", "-f", str(lua_prog), "after"], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "bump=[0]\n2\nafter=[2]" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("lua")
def test_an_import_on_the_channel_prints_and_credits_its_names(amk, lua_prog):
  r = sh(amk, ["-s", "-f", str(lua_prog), "credited"], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "y\nvars=[y] y=[5]" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("lua", "jq")
def test_an_op_the_owner_lacks_is_refused_by_name(amk, lua_prog):
  r = sh(amk, ["-s", "-f", str(lua_prog), "refused"], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "get=[2]" in r.stdout, r.stdout + r.stderr
  assert 'unknown operation "get" on namespace "work" (lua); one of: exec import' in r.stderr, r.stderr


workspace = "$(sqlite.ns D, create)\n$(sqlite.ns D, update, CREATE TABLE t(k))\n"


@pytest.mark.engines("sqlite", "js")
def test_a_js_ask_waits_without_blocking_the_guest(amk, tmp_path):
  mk = tmp_path / "ask.mk"
  mk.write_text(workspace + "\n".join([
    "@js.target",
    "define waiter",
    '  const v = Number(amk.call("sqlite.ns", "D", "version"));',
    '  const moved = amk.ask("wait", "D", String(v));',
    '  amk.call("sqlite.ns", "D", "update", "INSERT INTO t VALUES (1)");',
    '  print("moved=" + (Number(await moved) > v));',
    "endef",
    "probe: waiter",
    "\t@true",
    "",
  ]))
  r = sh(amk, ["-s", "-f", str(mk), "probe"], timeout=30)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "moved=true" in r.stdout, r.stdout + r.stderr


waiters = {
  "lua": "\n".join([
    "@lua.target",
    "define waiter",
    '  local v = tonumber(amk.call("sqlite.ns", "D", "version"))',
    '  local h = amk.ask("wait", "D", tostring(v))',
    '  amk.call("sqlite.ns", "D", "update", "INSERT INTO t VALUES (1)")',
    '  print("moved=" .. tostring(tonumber(h.result()) > v))',
    "endef",
  ]),
  "micropy": "\n".join([
    "@micropy.target",
    "define waiter",
    "  import amk",
    '  v = int(amk.call("sqlite.ns", "D", "version"))',
    '  h = amk.ask("wait", "D", str(v))',
    '  amk.call("sqlite.ns", "D", "update", "INSERT INTO t VALUES (1)")',
    '  print("moved=" + str(int(h.result()) > v).lower())',
    "endef",
  ]),
  "s7": "\n".join([
    "@s7.target",
    "define waiter",
    '  (let* ((v (string->number (amk-call \'sqlite.ns "D" "version")))',
    '         (id (amk-ask-begin \'wait "D" (number->string v))))',
    '    (amk-call \'sqlite.ns "D" "update" "INSERT INTO t VALUES (1)")',
    '    (display (if (> (string->number (amk-ask-end id)) v) "moved=true" "moved=false")))',
    "endef",
  ]),
}


@pytest.mark.parametrize("engine", sorted(waiters))
def test_a_guests_ask_waits_without_blocking_the_guest(amk, engines, tmp_path, engine):
  if engine not in engines or "sqlite" not in engines:
    pytest.skip(f"needs {engine} and sqlite")
  mk = tmp_path / "ask.mk"
  mk.write_text(workspace + waiters[engine] + "\nprobe: waiter\n\t@true\n")
  r = sh(amk, ["-s", "-f", str(mk), "probe"], timeout=30)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "moved=true" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("sqlite", "js")
def test_a_js_ask_in_the_owner_that_would_park_is_refused(amk, tmp_path):
  mk = tmp_path / "ask.mk"
  mk.write_text(workspace + "\n".join([
    '$(info $(js.exec try { await amk.ask("wait", "D", amk.call("sqlite.ns", "D", "version")); print("moved"); } catch (e) { print(String(e)); }))',
    "probe:",
    "\t@true",
    "",
  ]))
  r = sh(amk, ["-s", "-f", str(mk), "probe"], timeout=30)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "the owner would wait on itself" in r.stdout, r.stdout + r.stderr

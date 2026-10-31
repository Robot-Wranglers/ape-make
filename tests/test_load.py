"""Pins the load directive.

`load path/module.<ext>` goes to the engine that claims `<ext>` in main: an import of the
text, of the path for wasm, a workspace load for a store. `./`, `../` and `/` paths are
taken as written, any other is under the payload's library for the engine, and one `...`
component walks every depth below it. Pinned: each shape and the fatal cases.
"""

from pathlib import Path

import pytest

from conftest import sh

fib = Path(__file__).resolve().parents[1] / "src/wasm3-0.9.0/test/lang/fib32.wasm"


def run(amk, tmp_path, lines, files=None, flags=(), env=None):
  for name, text in (files or {}).items():
    (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / name).write_text(text)
  mk = tmp_path / "load.mk"
  mk.write_text("\n".join(lines + ["all:", "\t@true", ""]))
  return sh(amk, [*flags, "-f", str(mk)], cwd=tmp_path, env=env, timeout=60)


@pytest.mark.engines("s7")
def test_the_warnings_honor_silent_and_amk_warning_is_the_same_channel(amk, tmp_path):
  r = run(amk, tmp_path, ["load amb", "$(amk.warning hello from the makefile)"])
  assert r.returncode == 0, r.stdout + r.stderr
  assert "load.mk:1: load: amb: found as /zip/lib/s7/amb.scm, loaded in s7" in r.stderr, r.stderr
  assert "load.mk:2: hello from the makefile" in r.stderr, r.stderr
  assert r.stdout == "", r.stdout
  for flags in (["-s"], ["--silent"]):
    r = run(amk, tmp_path, ["load amb", "$(amk.warning hello from the makefile)"], flags=flags)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stderr == "", r.stderr
  r = run(amk, tmp_path, ["load nosuch"], flags=["-s"])
  assert r.returncode != 0, r.stdout + r.stderr
  assert "the payload was searched" not in r.stderr, r.stderr
  assert "load: nosuch: NoSuchModule: ENOENT" in r.stderr, r.stderr


@pytest.mark.engines("lua")
def test_relative_lua_file_lifts_its_functions(amk, tmp_path):
  r = run(amk, tmp_path, [
    "load ./twice.lua",
    "$(info twice=$(twice 21) loaded=[$(.LOADED)] feature=$(filter load,$(.FEATURES)))",
  ], {"twice.lua": "function twice(x) return 2 * x end\n"})
  assert r.returncode == 0, r.stdout + r.stderr
  assert "twice=42 loaded=[./twice.lua] feature=load" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("lua")
def test_two_files_on_one_line(amk, tmp_path):
  r = run(amk, tmp_path, [
    "load ./one.lua ./two.lua",
    "$(info $(one x) $(two x) [$(.LOADED)])",
  ], {"one.lua": "function one(s) return 1 end\n", "two.lua": "function two(s) return 2 end\n"})
  assert r.returncode == 0, r.stdout + r.stderr
  assert "1 2 [./one.lua ./two.lua]" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("wasm")
@pytest.mark.skipif(not fib.exists(), reason="wasm3 sources are not unpacked")
def test_absolute_wasm_module_lifts_its_exports(amk, tmp_path):
  r = run(amk, tmp_path, [
    f"load {fib}",
    "$(info fib=$(fib 10))",
  ])
  assert r.returncode == 0, r.stdout + r.stderr
  assert "fib=55" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("jq")
def test_jq_file_replaces_the_main_state(amk, tmp_path):
  r = run(amk, tmp_path, [
    "load ./state.jq",
    "$(info n=$(jq.get .a | length) b=$(jq.get -r .b))",
  ], {"state.jq": '{"a": [1, 2, 3], "b": "x"}\n'})
  assert r.returncode == 0, r.stdout + r.stderr
  assert "n=3 b=x" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("lua")
def test_unqualified_name_is_the_payload_library(amk, tmp_path):
  r = run(amk, tmp_path, [
    "load dkjson.lua",
    "$(info [$(.LOADED)])",
  ], {"dkjson.lua": "error('the working directory is not the library')\n"})
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[/zip/lib/lua/dkjson.lua]" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("lua")
def test_dots_walk_below_a_relative_directory(amk, tmp_path):
  r = run(amk, tmp_path, [
    "load ./mods/.../deep.lua",
    "$(info deep=$(deep x) [$(.LOADED)])",
  ], {"mods/a/b/deep.lua": "function deep(s) return 'found' end\n"})
  assert r.returncode == 0, r.stdout + r.stderr
  assert "deep=found [./mods/a/b/deep.lua]" in r.stdout, r.stdout + r.stderr
  r = run(amk, tmp_path, ["load ./mods/.../top.lua", "$(info [$(.LOADED)])"], {"mods/top.lua": "t = 1\n"})
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[./mods/top.lua]" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("lua")
def test_dots_walk_the_payload_library(amk, tmp_path):
  r = run(amk, tmp_path, ["load .../dkjson.lua", "$(info [$(.LOADED)])"])
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[/zip/lib/lua/dkjson.lua]" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("js")
def test_dots_matching_more_than_one_file_is_fatal_even_under_dash_load(amk, tmp_path):
  r = run(amk, tmp_path, ["-load .../mod.js"])
  assert r.returncode != 0, r.stdout + r.stderr
  assert "load: .../mod.js: ... matches" in r.stderr, r.stderr


@pytest.mark.engines("lua")
def test_init_stem_is_fatal_even_under_dash_load(amk, tmp_path):
  r = run(amk, tmp_path, ["-load ./init.lua"], {"init.lua": "x = 1\n"})
  assert r.returncode != 0, r.stdout + r.stderr
  assert "load: ./init.lua: init is a module's own file" in r.stderr, r.stderr


@pytest.mark.engines("lua")
def test_two_dots_components_are_fatal(amk, tmp_path):
  r = run(amk, tmp_path, ["load ./.../.../x.lua"])
  assert r.returncode != 0, r.stdout + r.stderr
  assert "more than one ... component" in r.stderr, r.stderr


@pytest.mark.engines("s7")
def test_bare_name_falls_back_to_an_engine_library_with_a_warning(amk, tmp_path):
  r = run(amk, tmp_path, ["load amb", "$(info [$(.LOADED)])"])
  assert r.returncode == 0, r.stdout + r.stderr
  assert "load: amb: found as /zip/lib/s7/amb.scm, loaded in s7" in r.stderr, r.stderr
  assert "[/zip/lib/s7/amb.scm]" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("lua", "js")
def test_a_stem_held_by_two_engine_libraries_is_ambiguous_even_under_dash_load(bundle, tmp_path):
  mk = tmp_path / "dup.mk"
  mk.write_text("-load dup\n$(info not reached)\nall:\n\t@true\n")
  r = sh(bundle, ["-f", str(mk)], cwd=tmp_path, timeout=60)
  assert r.returncode != 0, r.stdout + r.stderr
  assert "load: dup: ambiguous, 2 engine libraries hold it: /zip/lib/js/dup.js /zip/lib/lua/dup.lua" in r.stderr, r.stderr
  assert "not reached" not in r.stdout, r.stdout
  mk.write_text("load dup.lua\n$(info dup=$(dup x) [$(.LOADED)])\nall:\n\t@true\n")
  r = sh(bundle, ["-f", str(mk)], cwd=tmp_path, timeout=60)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "dup=lua [/zip/lib/lua/dup.lua]" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("s7")
def test_unclaimed_extension_falls_back_to_the_exact_library_file(amk, tmp_path):
  r = run(amk, tmp_path, ["load amb.scm", "$(info [$(.LOADED)])"])
  assert r.returncode == 0, r.stdout + r.stderr
  assert "found as /zip/lib/s7/amb.scm" in r.stderr, r.stderr
  r = run(amk, tmp_path, ["load amb.txt"])
  assert r.returncode != 0, r.stdout + r.stderr
  assert "searched as <root>/*/amb.txt," in r.stderr, r.stderr
  assert "NoSuchModule" in r.stderr, r.stderr


def test_bare_name_degrades_to_amk_include_with_its_order_and_guard(amk, tmp_path):
  root = tmp_path / "root"
  for name, text in {
    "outer/init.amk": "outer.runs += x\nload inner\n",
    "inner/init.amk": "inner.runs += x\n",
    "amk/solo.amk": "solo.runs += x\n",
  }.items():
    (root / name).parent.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(text)
  env = {"AMKPATH": str(root)}
  probe = "$(info outer=$(outer.runs) inner=$(inner.runs) [$(amk.included)] [$(.LOADED)])"
  r = run(amk, tmp_path, ["load outer", probe], env=env)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stderr == "", r.stderr
  assert f"outer=x inner=x [m5 outer inner] [{root}/inner/init.amk {root}/outer/init.amk]" in r.stdout, r.stdout + r.stderr
  r = run(amk, tmp_path, ["load solo", "$(info solo=$(solo.runs) [$(.LOADED)])"], env=env)
  assert r.returncode == 0, r.stdout + r.stderr
  assert f"solo=x [{root}/amk/solo.amk]" in r.stdout, r.stdout + r.stderr
  r = run(amk, tmp_path, [
    "$(amk.include inner)",
    "load inner",
    "load outer",
    "load outer",
    "$(info inner=$(inner.runs) outer=$(outer.runs) [$(amk.loaded)] [$(.LOADED)])",
  ], env=env)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "found as" not in r.stderr, r.stderr
  assert f"inner=x outer=x [inner outer inner outer] [{root}/outer/init.amk]" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("jq")
def test_a_topic_part_loads_alone_and_once(amk, tmp_path):
  probe = "$(info [$(amk.included)] [$(.LOADED)] $(origin pool_star) $(origin amk.mutex))"
  r = run(amk, tmp_path, ["load dsys/pool", probe])
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[m5 dsys/pool] [/zip/lib/dsys/pool.amk] file undefined" in r.stdout, r.stdout + r.stderr
  r = run(amk, tmp_path, ["load dsys/pool", "load dsys", probe])
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[m5 dsys/pool dsys dsys/locks] [/zip/lib/dsys/pool.amk /zip/lib/dsys/locks.amk /zip/lib/dsys/init.amk] file file" in r.stdout, r.stdout + r.stderr
  r = run(amk, tmp_path, ["load dsys/nope"])
  assert r.returncode != 0, r.stdout
  assert "then <root>/dsys/nope/init.amk, then <root>/dsys/nope.amk, a part of its topic" in r.stderr, r.stderr
  assert "load: dsys/nope: NoSuchModule" in r.stderr, r.stderr


@pytest.mark.engines("jq")
def test_a_topic_reads_its_own_parts_while_a_part_alone_honors_amkpath(amk, tmp_path):
  root = tmp_path / "root"
  (root / "dsys").mkdir(parents=True)
  (root / "dsys" / "pool.amk").write_text("dsys.part := shadow\n")
  env = {"AMKPATH": str(root)}
  probe = "$(info part=$(dsys.part) star=$(origin pool_star) [$(.LOADED)])"
  r = run(amk, tmp_path, ["dsys.part := none", "load dsys", probe], env=env)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "part=none star=file [/zip/lib/dsys/pool.amk /zip/lib/dsys/locks.amk /zip/lib/dsys/init.amk]" in r.stdout, r.stdout + r.stderr
  r = run(amk, tmp_path, ["load dsys/pool", probe], env=env)
  assert r.returncode == 0, r.stdout + r.stderr
  assert f"part=shadow star=undefined [{root}/dsys/pool.amk]" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("lua")
def test_a_path_loads_once_and_every_line_is_recorded(amk, tmp_path):
  r = run(amk, tmp_path, [
    "load ./count.lua",
    "load ./count.lua",
    "load ./sub/.../count.lua ./count.lua",
    "$(info n=$(count x) [$(.LOADED)] [$(amk.loaded)])",
  ], {"count.lua": "n = (n or 0) + 1\nfunction count(s) return n end\n",
      "sub/a/count.lua": "n = (n or 0) + 10\n"})
  assert r.returncode == 0, r.stdout + r.stderr
  assert "n=11 [./count.lua ./sub/a/count.lua] [./count.lua ./count.lua ./sub/.../count.lua ./count.lua]" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("lua")
def test_amkpath_roots_shadow_the_payload_in_order(amk, tmp_path):
  first, second = tmp_path / "first", tmp_path / "second"
  for root, body in ((first, "function which(s) return 'first' end\n"), (second, "function which(s) return 'second' end\n")):
    (root / "lua").mkdir(parents=True)
    (root / "lua" / "which.lua").write_text(body)
  (second / "lua" / "dkjson.lua").write_text("shadowed = true\n")
  (second / "amk").mkdir()
  (second / "amk" / "mylib.mk").write_text("mylib.answer := 42\n")
  (second / "topic").mkdir()
  (second / "topic" / "init.amk").write_text("topic.answer := 7\n")
  env = {"AMKPATH": f"{first}:{second}"}
  r = run(amk, tmp_path, [
    "load which",
    "load which.lua",
    "load dkjson.lua",
    "load mylib",
    "load topic",
    "$(info which=$(which x) shadowed=$(origin shadowed) mylib=$(mylib.answer) topic=$(topic.answer) [$(amk.included)])",
    "$(info [$(.LOADED)])",
  ], env=env)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "which=first shadowed=file mylib=42 topic=7 [m5 mylib topic]" in r.stdout, r.stdout + r.stderr
  assert f"[{first}/lua/which.lua {second}/lua/dkjson.lua {second}/amk/mylib.mk {second}/topic/init.amk]" in r.stdout, r.stdout + r.stderr
  assert f"load: which: found as {first}/lua/which.lua, loaded in lua" in r.stderr, r.stderr
  lines = ["load which", "$(info which=$(which x))"]
  r = run(amk, tmp_path, lines, env={"AMK_PATH": str(second)})
  assert r.returncode == 0, r.stdout + r.stderr
  assert "which=second" in r.stdout, r.stdout + r.stderr
  r = run(amk, tmp_path, lines, env={"AMKPATH": str(first), "AMK_PATH": str(second)})
  assert r.returncode == 0, r.stdout + r.stderr
  assert "which=first" in r.stdout, r.stdout + r.stderr


def test_bare_name_with_no_match_states_the_policy_and_fails_fast(amk, tmp_path):
  r = run(amk, tmp_path, ["load nosuch", "$(info not reached)"])
  assert r.returncode != 0, r.stdout + r.stderr
  assert "searched as <root>/*/nosuch.*, then <root>/amk/nosuch.amk or .mk, then <root>/nosuch/init.amk" in r.stderr, r.stderr
  assert "load: nosuch: NoSuchModule: ENOENT" in r.stderr, r.stderr
  assert "not reached" not in r.stdout, r.stdout
  r = run(amk, tmp_path, ["-load nosuch", "$(info ok [$(.LOADED)])"])
  assert r.returncode == 0, r.stdout + r.stderr
  assert "ok []" in r.stdout, r.stdout + r.stderr


def test_shared_object_is_a_platform_error_even_under_dash_load(amk, tmp_path):
  for line in ("load ./plugin.so", "-load plugin.so", "load /opt/plugin.so(setup)"):
    r = run(amk, tmp_path, [line, "$(info not reached)"])
    assert r.returncode != 0, line + r.stdout + r.stderr
    assert "PlatformError: ENOSYS: amk is portable via cosmocc, no support for .so" in r.stderr, line + r.stderr
    assert "not reached" not in r.stdout, line + r.stdout


def test_unclaimed_extension_is_fatal(amk, tmp_path):
  r = run(amk, tmp_path, ["load ./notes.txt"], {"notes.txt": "hello\n"})
  assert r.returncode != 0, r.stdout + r.stderr
  assert "load: ./notes.txt: no engine claims the extension; one of" in r.stderr, r.stderr
  assert ".lua" in r.stderr or ".jq" in r.stderr, r.stderr


@pytest.mark.engines("lua")
def test_missing_file_is_fatal_under_load_and_silent_under_dash_load(amk, tmp_path):
  r = run(amk, tmp_path, ["load ./missing.lua"])
  assert r.returncode != 0, r.stdout + r.stderr
  assert "load: ./missing.lua: No such file or directory" in r.stderr, r.stderr
  r = run(amk, tmp_path, ["-load ./missing.lua", "-load .../missing.lua", "$(info ok [$(.LOADED)])"])
  assert r.returncode == 0, r.stdout + r.stderr
  assert "ok []" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("lua")
def test_file_that_does_not_import_is_fatal_under_load_and_silent_under_dash_load(amk, tmp_path):
  files = {"bad.lua": "function (\n"}
  r = run(amk, tmp_path, ["load ./bad.lua"], files)
  assert r.returncode != 0, r.stdout + r.stderr
  assert "load: ./bad.lua: lua import exited with status" in r.stderr, r.stderr
  r = run(amk, tmp_path, ["-load ./bad.lua", "$(info ok)"], files)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "ok" in r.stdout, r.stdout + r.stderr

"""Pins the prelude.

Patch 0034 has make read the payload's `__init__.mk` before any makefile, with no shell
in between: bash with strict flags, silent stop-on-error make that warns on undefined
variables, `AMK_GOAL` as the default goal when set, and `__file__` as the entry makefile.
An environment knob or a later assignment wins, the first target is still the default
goal when nothing names one, and `AMK_NO_PRELUDE` skips the whole thing.
"""

import pytest

from conftest import packed, sh


def test_payload_carries_the_prelude_and_no_boot_script(amk):
  assert "__file__" in packed(amk, "__init__.mk")
  r = sh(amk, ["--awk", "{ }", "/zip/__main__.sh"])
  assert r.returncode != 0, "a boot script would cost every start a shell"


def test_prelude_stays_out_of_the_makefile_list(amk, tmp_path):
  mk = tmp_path / "a.mk"
  mk.write_text("all:\n\t@echo $(firstword $(MAKEFILE_LIST)) $(words $(MAKEFILE_LIST))\n")
  r = sh(amk, ["-f", str(mk)], cwd=tmp_path)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.split() == [str(mk), "1"]


def test_no_prelude_knob_gives_plain_make(amk, tmp_path):
  mk = tmp_path / "a.mk"
  mk.write_text("all:\n\t@echo shell=$(SHELL) file=$(value __file__)\n")
  r = sh(amk, ["-f", str(mk)], cwd=tmp_path, env={"AMK_NO_PRELUDE": "1"})
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "shell=/bin/sh file="


def test_defaults_land_before_the_makefile(amk, tmp_path):
  mk = tmp_path / "a.mk"
  mk.write_text("\n".join([
    "__main__:",
    "\techo shell=$(SHELL) flags=$(.SHELLFLAGS)",
    "\techo file=$(__file__) goal=$(.DEFAULT_GOAL)",
    "\techo mf=$(MAKEFLAGS)",
    "",
  ]))
  r = sh(amk, ["-f", str(mk)], cwd=tmp_path)
  assert r.returncode == 0, r.stdout + r.stderr
  out = r.stdout
  assert "shell=bash flags=-euo pipefail -c" in out
  assert f"file={mk} goal=__main__" in out, "the first target is still the default"
  assert "s" in out.split("mf=", 1)[1].split()[0]
  assert "--warn-undefined-variables" in out


def test_strict_shell_stops_a_failing_pipeline(amk, tmp_path):
  mk = tmp_path / "a.mk"
  mk.write_text("__main__:\n\tfalse | true\n\techo reached\n")
  r = sh(amk, ["-f", str(mk)], cwd=tmp_path)
  assert r.returncode != 0
  assert "reached" not in r.stdout


def test_undefined_variable_warns(amk, tmp_path):
  mk = tmp_path / "a.mk"
  mk.write_text("__main__:\n\techo $(nothing_here)\n")
  r = sh(amk, ["-f", str(mk)], cwd=tmp_path)
  assert "undefined variable 'nothing_here'" in r.stderr


def test_environment_knobs_override_the_defaults(amk, tmp_path):
  mk = tmp_path / "a.mk"
  mk.write_text("\n".join([
    "__main__:",
    "\t@echo wrong",
    "other:",
    "\t@echo shell=$(SHELL) flags=$(.SHELLFLAGS) file=$(__file__)",
    "",
  ]))
  env = {"AMK_SHELL": "sh", "AMK_SHELLFLAGS": "-c", "AMK_GOAL": "other", "__file__": "elsewhere"}
  r = sh(amk, ["-f", str(mk)], cwd=tmp_path, env=env)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "shell=sh flags=-c file=elsewhere"


def test_main_target_is_the_default_wherever_it_sits(amk, tmp_path):
  mk = tmp_path / "a.mk"
  mk.write_text("first:\n\t@echo first\n__main__:\n\t@echo main goal=$(.DEFAULT_GOAL)\n")
  r = sh(amk, ["-f", str(mk)], cwd=tmp_path)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "main goal=__main__"


def test_first_target_is_the_default_without_a_main(amk, tmp_path):
  mk = tmp_path / "a.mk"
  mk.write_text("first:\n\t@echo first\nsecond:\n\t@echo wrong\n")
  r = sh(amk, ["-f", str(mk)], cwd=tmp_path)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "first"


def test_a_named_default_goal_beats_main(amk, tmp_path):
  mk = tmp_path / "a.mk"
  mk.write_text("__main__:\n\t@echo wrong\n.DEFAULT_GOAL := other\nother:\n\t@echo other\n")
  r = sh(amk, ["-f", str(mk)], cwd=tmp_path)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "other"


def test_a_main_imported_target_is_the_default(amk, tmp_path):
  mk = tmp_path / "a.mk"
  mk.write_text("other:\n\t@echo wrong\n@awk.import.target\ndefine __main__\nBEGIN { print \"from an import\" }\nendef\n")
  r = sh(amk, ["-f", str(mk)], cwd=tmp_path)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "from an import"


def test_the_flags_follow_a_shell_the_makefile_names(amk, tmp_path):
  mk = tmp_path / "a.mk"
  mk.write_text("SHELL := /bin/sh\n__main__:\n\t@echo flags=$(.SHELLFLAGS)\n")
  r = sh(amk, ["-f", str(mk)], cwd=tmp_path)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "flags=-eu -c"


def test_a_makefile_assignment_overrides_the_prelude(amk, tmp_path):
  mk = tmp_path / "a.mk"
  mk.write_text("\n".join([
    "SHELL := sh",
    ".SHELLFLAGS := -c",
    ".DEFAULT_GOAL := all",
    "__main__:",
    "\t@echo wrong",
    "all:",
    "\t@echo shell=$(SHELL) flags=$(.SHELLFLAGS)",
    "",
  ]))
  r = sh(amk, ["-f", str(mk)], cwd=tmp_path)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "shell=sh flags=-c"


def test_file_names_the_entry_not_an_include(amk, tmp_path):
  (tmp_path / "inc.mk").write_text("from_inc := $(__file__)\n")
  mk = tmp_path / "a.mk"
  mk.write_text("include inc.mk\n__main__:\n\t@echo $(from_inc) $(__file__)\n")
  r = sh(amk, ["-f", str(mk)], cwd=tmp_path)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.split() == [str(mk), str(mk)]


def test_recursion_keeps_the_prelude(amk, tmp_path):
  mk = tmp_path / "a.mk"
  mk.write_text("\n".join([
    "__main__:",
    "\t@$(MAKE) -f $(__file__) inner",
    "inner:",
    "\t@echo shell=$(SHELL) level=$(MAKELEVEL)",
    "",
  ]))
  r = sh(amk, ["-f", str(mk)], cwd=tmp_path)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "shell=bash level=1"


@pytest.mark.engines("sqlite", "micropy")
def test_include_reads_a_library_by_name_once(amk, tmp_path):
  """A name is make's own library under lib/amk/ first, else a topic's init.amk; several names at once; a second include of one is nothing."""
  mk = tmp_path / "a.mk"
  mk.write_text("\n".join([
    "$(amk.include utmpl, tspace)",
    "$(amk.include tspace)",
    "__main__:",
    "\t@echo $(origin utmpl.py) $(origin tspace.create) [$(amk.included)]",
    "",
  ]))
  r = sh(amk, ["-f", str(mk)], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.split() == ["file", "file", "[m5", "utmpl", "tspace]"], r.stdout


def test_include_of_an_unknown_name_stops_make(amk, tmp_path):
  mk = tmp_path / "a.mk"
  mk.write_text("$(amk.include nosuch)\n__main__:\n\t@true\n")
  r = sh(amk, ["-f", str(mk)], cwd=tmp_path, timeout=120)
  assert r.returncode != 0, r.stdout + r.stderr
  assert "amk.include: no library named nosuch in the payload" in r.stderr, r.stderr


def stacked(amk, tmp_path, lines):
  mk = tmp_path / "a.mk"
  mk.write_text("\n".join(lines + ["__main__:", "\t@true", ""]))
  return sh(amk, ["-s", "-f", str(mk)], cwd=tmp_path, timeout=120)


def test_registration_aliases_the_missing_target_form(amk, tmp_path):
  r = stacked(amk, tmp_path, ["p.import.target_star = [$(1)]", "$(amk.engine p, guest=amk)",
    "$(info $(call p.target_star,z) $(amk.engines) $(amk.stacked.engines))"])
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout == "[z] amklang p amklang p\n"


def test_registration_records_the_row_and_its_extensions(amk, tmp_path):
  r = stacked(amk, tmp_path, [
    "p.target_star = x",
    "$(amk.engine p, guest=lua, aliases=pp ppp, language=P, version=1.2)",
    "$(info guest=$(amk.engine.p.guest) aliases=[$(amk.engine.p.aliases)] lang=$(amk.engine.p.language)"
    " impl=$(amk.engine.p.implementation) version=$(p.__version__) ext=$(amk.engine.ext.p)/$(amk.engine.ext.pp)/$(amk.engine.ext.ppp)"
    " jit=[$(amk.engine.p.jit.env)$(amk.engine.p.jit.build)])",
  ])
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout == "guest=lua aliases=[pp ppp] lang=P impl=lua version=1.2 ext=p/p/p jit=[]\n", r.stdout


@pytest.mark.engines("jq")
def test_the_spec_decorator_registers_from_a_json_row(amk, tmp_path):
  r = stacked(amk, tmp_path, [
    "p.target_star = x",
    "@amk.engine.spec",
    "define p",
    '  {"guest": "lua", "aliases": "pp q", "language": "the P language", "version": "1.2"}',
    "endef",
    "$(info [$(amk.engines)] aliases=[$(amk.engine.p.aliases)] lang=[$(amk.engine.p.language)]"
    " version=$(p.__version__) ext=$(amk.engine.ext.pp)/$(amk.engine.ext.q))",
  ])
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout == "[amklang p] aliases=[pp q] lang=[the P language] version=1.2 ext=p/p\n", r.stdout


def test_make_registers_as_amklang_in_the_prelude(amk, tmp_path):
  r = stacked(amk, tmp_path, [
    "$(info [$(amk.engines)] ext=$(amk.engine.ext.amklang)/$(origin amk.engine.ext.amk) guest=$(amk.engine.amklang.guest)"
    " lang=$(amk.engine.amklang.language) impl=$(amk.engine.amklang.implementation) version=$(amklang.__version__)/$(.AMK_VERSION))",
  ])
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[amklang] ext=amklang/undefined guest=amk lang=make impl=amk" in r.stdout, r.stdout
  version = r.stdout.split("version=")[1].split()[0]
  assert version.split("/")[0] == version.split("/")[1], version
  r = stacked(amk, tmp_path, ["@amklang.import", "define lib", "  who := world", "  greet = hi $(1) and $(who)", "endef",
    "$(info $(call greet,a) [$(origin lib)])"])
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout == "hi a and world [file]\n", r.stdout
  mk = tmp_path / "a.mk"
  mk.write_text("\n".join(["@amklang.import", "define lib", "    @amk.target", "    define hello", "      echo hello from $@",
    "    endef", "endef", ""]))
  r = sh(amk, ["-s", "-f", str(mk), "hello"], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout == "hello from hello\n", r.stdout
  mk = tmp_path / "t.mk"
  mk.write_text("\n".join(["@amk.target", "define t1", "  echo one", "endef", "@amklang.target", "define t2", "  echo two",
    "endef", "@amklang.import.target", "define t3", "  echo three", "endef", ""]))
  r = sh(amk, ["-s", "-f", str(mk), "t1", "t2", "t3"], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout == "one\ntwo\nthree\n", r.stdout
  for lines, message in [
    (["$(amklang.ns a, exec, b)"], "stacked engine amklang does not define amklang.ns"),
  ]:
    r = stacked(amk, tmp_path, lines)
    assert r.returncode != 0, r.stdout
    assert message in r.stderr, r.stderr


def test_amklang_runs_a_program_in_a_fork_of_the_default_workspace(amk, tmp_path):
  r = stacked(amk, tmp_path, [
    "seen := parent",
    "define prog",
    "$(info one $(seen))",
    "seen := child",
    "$(info two $(seen))",
    "endef",
    "define goals",
    "hello:",
    "\t@echo hi $(who)",
    "endef",
    "a := [$(call amklang,$(value prog))]",
    "b := [$(call amklang.exec,$(value prog))]",
    "c := [$(call amklang.argv,hello 'who=a b',$(value goals))]",
    "$(info $(a) $(b) $(c) $(seen))",
  ])
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout == "[one parent\ntwo child] [one parent\ntwo child] [hi a b] parent\n", r.stdout
  r = stacked(amk, tmp_path, [
    "seen := parent",
    "@amklang.exec",
    "define prog",
    "  seen := child",
    "  $(info exec $(seen))",
    "endef",
    "@amklang.argv hello 'who=a b'",
    "define goals",
    "  hello:",
    "  \t@echo hi $(who)",
    "endef",
    "$(info after $(seen))",
  ])
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout == "exec child\nhi a b\nafter parent\n", r.stdout
  r = stacked(amk, tmp_path, ["x := $(amklang.argv nosuch,)"])
  assert r.returncode != 0, r.stdout
  assert "$(amklang.argv ...): the program failed" in r.stderr, r.stderr


@pytest.mark.engines("jq", "lua")
def test_the_bash_library_registers_on_load(amk, tmp_path):
  r = stacked(amk, tmp_path, [
    "load bash",
    "$(info [$(amk.engines)] ext=$(amk.engine.ext.bash) guest=$(amk.engine.bash.guest)"
    " impl=$(amk.engine.bash.implementation) version=$(bash.__version__)/$(lua.__version__) [$(.LOADED)])",
  ])
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[amklang bash] ext=bash guest=lua impl=bash" in r.stdout, r.stdout
  assert "[/zip/lib/amk/bash.amk]" in r.stdout, r.stdout
  version = r.stdout.split("version=")[1].split()[0]
  assert version.count("/") == 1 and version.split("/")[0] == version.split("/")[1], version
  r = stacked(amk, tmp_path, ["load bash", "$(bash.ns a, exec, b)"])
  assert r.returncode != 0, r.stdout
  assert "stacked engine bash does not define bash.ns" in r.stderr, r.stderr


@pytest.mark.parametrize("lines,message", [
  (["$(amk.engine p, guest=amk)"], "stacked engine p does not define @p.target"),
  (["p.target_star = x", "$(amk.engine p, guest=amk)", "$(amk.engine p, guest=amk)"], "amk.engine: p is already an engine"),
  (["p.target_star = x", "$(amk.engine p, guest=amk)", "$(p.ns a, exec, b)"], "stacked engine p does not define p.ns"),
  (["p.target_star = x", "$(amk.engine p, guest=amk)", "@p.argv", "define t", "endef"], "stacked engine p does not define @p.argv"),
  (["p.target_star = x", "$(amk.engine p)"], "amk.engine: p: guest= is required"),
  (["p.target_star = x", "$(amk.engine p, guest=cobol)"], "amk.engine: p: guest cobol is not an engine in this build"),
  (["p.target_star = x", "$(amk.engine p, guest=amk, colour=red)"], "amk.engine: p: unknown key colour; one of guest aliases"),
  (["p.target_star = x", "$(amk.engine p, guest=amk, red)"], "amk.engine: p: red is not key=value"),
  (["p.target_star = x", "$(amk.engine p, guest=amk, aliases=lua)"], "amk.engine: p: alias lua is an engine already"),
  (["p.target_star = x", "$(amk.engine p, guest=amk, jit.build=p.build)"], "amk.engine: p: jit is for a guest that imports modules, and amk imports text"),
  (["load wasm", "p.target_star = x", "$(amk.engine p, guest=wasm)"], "amk.engine: p: a wasm guest imports modules; give jit.build="),
], ids=["no target form", "a second registration", "a missing function", "a missing decorator", "no guest", "an unknown guest",
        "an unknown key", "a bare word", "an alias a row holds", "jit on a text guest", "a wasm guest with no command"])
def test_registration_stops_make(amk, tmp_path, lines, message):
  r = stacked(amk, tmp_path, lines)
  assert r.returncode != 0, r.stdout
  assert message in r.stderr, r.stderr

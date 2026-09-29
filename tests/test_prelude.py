"""Pins the prelude.

Patch 0034 has make read the payload's `__init__.mk` before any makefile, with no shell
in between: bash with strict flags, silent stop-on-error make that warns on undefined
variables, `AMK_GOAL` as the default goal when set, and `__file__` as the entry makefile.
An environment knob or a later assignment wins, the first target is still the default
goal when nothing names one, and `AMK_NO_PRELUDE` skips the whole thing.
"""

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

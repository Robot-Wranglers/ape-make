"""Pins the function profiler.

With `AMK_PROFILE` naming a file, or a dash for stderr, a run appends one table: a header
with the pid and the wall, then one row per name with self and total milliseconds and a
count. Builtins appear under `fn`, macros reached through call under `call`, recursive
variables under `var`. A dispatching macro's self time is near zero and its total covers
what it dispatched to. Unset, nothing is written.
"""

import re

from conftest import sh

PROGRAM = "\n".join([
  "define twice",
  "$(call once,$(1))$(call once,$(1))",
  "endef",
  "define once",
  "$(shell printf %s $(1))",
  "endef",
  "name = $(call twice,x)",
  "out := $(name)$(name)$(name)",
  "all:",
  "\t@printf '%s\\n' '$(out)'",
])

HEADER = re.compile(r"^# amk profile pid=\d+ wall=\d+\.\d+s names=\d+$", re.M)
ROW = re.compile(r"^\s*(\d+\.\d+)\s+(\d+\.\d+)\s+(\d+)\s+(\S+) (\S+)$", re.M)


def run(amk, tmp_path, env):
  mk = tmp_path / "prof.mk"
  mk.write_text(PROGRAM + "\n")
  return sh(amk, ["-f", str(mk)], env=env, timeout=120)


def rows(text):
  return {f"{kind} {name}": (float(s), float(t), int(c)) for s, t, c, kind, name in ROW.findall(text)}


def test_unset_writes_nothing(amk, tmp_path):
  r = run(amk, tmp_path, {})
  assert r.returncode == 0, r.stdout + r.stderr
  assert "amk profile" not in r.stderr, r.stderr


def test_dash_writes_the_table_to_stderr(amk, tmp_path):
  r = run(amk, tmp_path, {"AMK_PROFILE": "-"})
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "xxxxxx", r.stdout
  assert HEADER.search(r.stderr), r.stderr
  table = rows(r.stderr)
  assert table["call twice"][2] == 3, table
  assert table["call once"][2] == 6, table
  assert table["fn shell"][2] == 6, table
  assert table["var name"][2] == 3, table


def test_self_excludes_children_and_total_includes_them(amk, tmp_path):
  r = run(amk, tmp_path, {"AMK_PROFILE": "-"})
  table = rows(r.stderr)
  twice_self, twice_total, _ = table["call twice"]
  shell_self, shell_total, _ = table["fn shell"]
  # the forks live under shell, so the dispatching macro owns almost none of its own total
  assert shell_self > 0, table
  assert twice_total > shell_total * 0.9, table
  assert twice_self < twice_total, table


def test_the_flag_is_the_switch_and_leaves_argv(amk, tmp_path):
  mk = tmp_path / "prof.mk"
  mk.write_text(PROGRAM + "\n")
  # the bare flag goes to stderr, and make never sees the word
  r = sh(amk, ["--profile", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "xxxxxx", r.stdout
  assert HEADER.search(r.stderr), r.stderr
  assert "unrecognized" not in r.stderr, r.stderr
  # the file form, placed after the makefile, lands in the file and leaves stderr quiet
  log = tmp_path / "flag.txt"
  r = sh(amk, ["-f", str(mk), f"--profile={log}"], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "amk profile" not in r.stderr, r.stderr
  assert "call twice" in log.read_text(), log.read_text()[:300]


def test_the_flag_is_listed_in_help(amk):
  r = sh(amk, ["--help"], timeout=60)
  assert "--profile[=FILE]" in r.stdout, r.stdout[-1500:]


def test_a_file_collects_every_process(amk, tmp_path):
  log = tmp_path / "profile.txt"
  r = run(amk, tmp_path, {"AMK_PROFILE": str(log)})
  assert r.returncode == 0, r.stdout + r.stderr
  assert "amk profile" not in r.stderr, r.stderr
  text = log.read_text()
  assert len(HEADER.findall(text)) == 1, text
  assert "call twice" in text, text

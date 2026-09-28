"""Pins the value channel.

`$(goal name)` brings a goal up to date and answers its value. A define cell keeps its
program's output in a file under the goal directory and reruns only when a value it
references is newer, and a `$(goal x)` in a cell's body is an edge, so -j orders cells.
A plain file target has a value too, its contents.
"""

import time

import pytest

from conftest import sh

cells = "\n".join([
  "define.lua base",
  "local f = io.open('base.count', 'a') f:write('x\\n') f:close()",
  "print(tonumber(io.open('input.txt'):read('a')) + $(goal seed))",
  "endef",
  "define.micropy doubled",
  "print(int('$(goal base)') * 2)",
  "endef",
  "define.js both",
  'print("$(goal base)" + "/" + "$(goal doubled)")',
  "endef",
  "seed := 5",
  "$(shell mkdir -p .amk/goals)",
  ".amk/goals/seed: ; $(file >$@,$(seed))",
  "",
])


@pytest.mark.engines("lua", "micropy", "js")
def test_values_flow_between_cells_in_different_languages(amk, tmp_path):
  mk = tmp_path / "cells.mk"
  mk.write_text(cells)
  (tmp_path / "input.txt").write_text("10\n")
  r = sh(amk, ["-s", "-f", str(mk), "both"], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "15/30", r.stdout + r.stderr
  assert (tmp_path / ".amk/goals/both").read_text() == "15/30\n"


@pytest.mark.engines("lua", "micropy", "js")
def test_a_cell_reruns_only_when_a_value_it_uses_changes(amk, tmp_path):
  mk = tmp_path / "cells.mk"
  mk.write_text(cells)
  (tmp_path / "input.txt").write_text("10\n")
  for _ in range(2):
    r = sh(amk, ["-s", "-f", str(mk), "both"], cwd=tmp_path, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
  assert (tmp_path / "base.count").read_text().count("x") == 1, "base ran again with nothing changed"
  time.sleep(1.1)
  (tmp_path / "input.txt").write_text("20\n")
  r = sh(amk, ["-s", "-f", str(mk), "both"], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "15/30", "input.txt is not a value base references, so base stays as it was"
  (tmp_path / ".amk/goals/seed").unlink()
  time.sleep(1.1)
  r = sh(amk, ["-s", "-f", str(mk), "both"], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "25/50", r.stdout + r.stderr
  assert (tmp_path / "base.count").read_text().count("x") == 2


@pytest.mark.engines("lua")
def test_a_file_target_is_a_value_too(amk, tmp_path):
  mk = tmp_path / "file.mk"
  mk.write_text("\n".join([
    "define.lua shout",
    "print(string.upper('$(goal words.txt)'))",
    "endef",
    "words.txt: ; $(file >$@,hello there)",
    "",
  ]))
  r = sh(amk, ["-s", "-f", str(mk), "shout"], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "HELLO THERE", r.stdout
  time.sleep(1.1)
  (tmp_path / "words.txt").write_text("changed\n")
  r = sh(amk, ["-s", "-f", str(mk), "shout"], cwd=tmp_path, timeout=120)
  assert r.stdout.strip() == "CHANGED", r.stdout + r.stderr


@pytest.mark.engines("lua")
def test_a_plain_rule_reads_a_value_at_recipe_time(amk, tmp_path):
  mk = tmp_path / "plain.mk"
  mk.write_text("\n".join([
    "define.lua answer",
    "print(6 * 7)",
    "endef",
    "show: answer",
    "\t@echo got=$(goal answer)",
    "",
  ]))
  r = sh(amk, ["-s", "-f", str(mk), "show"], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "got=42" in r.stdout, r.stdout


@pytest.mark.engines("micropy")
def test_a_cell_program_has_no_size_limit(amk, tmp_path):
  padding = "# " + "x" * 300000
  mk = tmp_path / "big.mk"
  mk.write_text("\n".join([
    "define.micropy big",
    padding,
    "print(len(open(__file__).read()) if False else 'ran')",
    "endef",
    "",
  ]))
  r = sh(amk, ["-s", "-f", str(mk), "big"], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr[-500:]
  assert r.stdout.strip() == "ran", r.stdout
  assert not list((tmp_path / ".amk/goals").glob("*.src")), "no program file should be left beside the value"


@pytest.mark.engines("awk", "jq")
def test_awk_and_jq_cells_take_their_program_their_own_way(amk, tmp_path):
  mk = tmp_path / "argv.mk"
  mk.write_text("\n".join([
    "define.awk words",
    'BEGIN { print "a b c" }',
    "endef",
    "define.jq count",
    '"$(goal words)" | split(" ") | length',
    "endef",
    "",
  ]))
  r = sh(amk, ["-s", "-f", str(mk), "count"], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "3", r.stdout + r.stderr


def test_job_stdin_feeds_the_line_it_appears_in(amk, tmp_path):
  mk = tmp_path / "stdin.mk"
  mk.write_text("\n".join([
    "define text",
    "first line",
    "second line",
    "endef",
    "show:",
    "\t@$(job.stdin $(text))cat",
    "\t@$(job.stdin only one)tr a-z A-Z",
    "\t@echo plain",
    "",
  ]))
  r = sh(amk, ["-s", "-f", str(mk), "show"], cwd=tmp_path, timeout=120, stdin="not this\n")
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout == "first line\nsecond lineONLY ONEplain\n", repr(r.stdout)


def test_job_stdin_is_per_target_under_j(amk, tmp_path):
  mk = tmp_path / "stdin-j.mk"
  mk.write_text("\n".join([
    "all: a b c",
    "a:",
    "\t@$(job.stdin from a)sleep 0.2; cat",
    "\t@echo",
    "b:",
    "\t@$(job.stdin from b)cat",
    "\t@echo",
    "c:",
    "\t@sleep 0.1; $(job.stdin from c)cat",
    "\t@echo",
    "",
  ]))
  r = sh(amk, ["-s", "-j3", "-f", str(mk)], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert sorted(r.stdout.split()) == ["a", "b", "c", "from", "from", "from"], repr(r.stdout)


@pytest.mark.engines("lua")
def test_independent_cells_run_at_once_under_j(amk, tmp_path):
  mk = tmp_path / "par.mk"
  mk.write_text("\n".join([
    "define.lua slow1",
    "os.execute('sleep 0.6') print(1)",
    "endef",
    "define.lua slow2",
    "os.execute('sleep 0.6') print(2)",
    "endef",
    "define.lua total",
    "print($(goal slow1) + $(goal slow2))",
    "endef",
    "",
  ]))
  start = time.time()
  r = sh(amk, ["-s", "-j2", "-f", str(mk), "total"], cwd=tmp_path, timeout=120)
  elapsed = time.time() - start
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "3", r.stdout
  assert elapsed < 1.1, f"the two slow cells ran one after the other: {elapsed:.2f}s"

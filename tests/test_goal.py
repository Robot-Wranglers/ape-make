"""Pins the value channel.

`$(goal name)` brings a goal up to date and answers its value. An imported target that
something references keeps its output in a file under the goal directory and reruns when
a value it reads is newer; any other runs when asked and keeps no file. A body reaches
the engine as written but for `@x@`, a reference to the goal x in any case: an edge, so
-j orders the targets, and the value's raw text. A plain file target has a value too.
"""

import time

import pytest

from conftest import sh

targets = "\n".join([
  "@lua.import.target",
  "define base",
  "local f = io.open('base.count', 'a') f:write('x\\n') f:close()",
  "print(tonumber(io.open('input.txt'):read('a')) + @seed@)",
  "endef",
  "@micropy.import.target",
  "define doubled",
  "print(int('@base@') * 2)",
  "endef",
  "@js.import.target",
  "define both",
  'print("@base@" + "/" + "@doubled@")',
  "endef",
  "seed := 5",
  "$(shell mkdir -p .amk/goals)",
  ".amk/goals/seed: ; $(file >$@,$(seed))",
  "",
])


@pytest.mark.engines("lua", "micropy", "js")
def test_values_flow_between_imported_targets_in_different_languages(amk, tmp_path):
  mk = tmp_path / "targets.mk"
  mk.write_text(targets)
  (tmp_path / "input.txt").write_text("10\n")
  r = sh(amk, ["-s", "-f", str(mk), "both"], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "15/30", r.stdout + r.stderr
  assert (tmp_path / ".amk/goals/doubled").read_text() == "30\n"
  assert not (tmp_path / ".amk/goals/both").exists(), "nothing references both, so it keeps no value"


@pytest.mark.engines("lua", "micropy", "js")
def test_an_imported_target_reruns_only_when_a_value_it_uses_changes(amk, tmp_path):
  mk = tmp_path / "targets.mk"
  mk.write_text(targets)
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


def ran(name):
  return f"local f = io.open('runs.log', 'a') f:write('{name}\\n') f:close()"


diamond = "\n".join([
  "@lua.import.target",
  "define report",
  ran("report"),
  "print('@total@ over @count@')",
  "endef",
  "@lua.import.target",
  "define total",
  ran("total"),
  "local n = 0 for x in ('@sorted@'):gmatch('%S+') do n = n + x end print(n)",
  "endef",
  "@lua.import.target",
  "define count",
  ran("count"),
  "print(select(2, ('@sorted@'):gsub('%S+', '')))",
  "endef",
  "@lua.import.target",
  "define sorted",
  ran("sorted"),
  "local xs = {} for x in ('@numbers.txt@'):gmatch('%S+') do xs[#xs + 1] = tonumber(x) end",
  "table.sort(xs) print(table.concat(xs, ' '))",
  "endef",
  "@lua.import.target",
  "define aside",
  ran("aside"),
  "print('aside: @other.txt@')",
  "endef",
  "numbers.txt other.txt: ;",
  "",
])


@pytest.mark.engines("lua")
def test_a_changed_input_reruns_its_downstreams_and_nothing_else(amk, tmp_path):
  mk = tmp_path / "diamond.mk"
  mk.write_text(diamond)
  log = tmp_path / "runs.log"
  values = tmp_path / ".amk/goals"

  def build(*flags):
    log.write_text("")
    r = sh(amk, ["-s", *flags, "-f", str(mk), "report", "aside"], cwd=tmp_path, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    return sorted(r.stdout.split("\n")[:2]), log.read_text().split()

  (tmp_path / "numbers.txt").write_text("3 1 2\n")
  (tmp_path / "other.txt").write_text("first\n")
  out, runs = build("-j4")
  assert out == ["6 over 3", "aside: first"], out
  assert sorted(runs) == ["aside", "count", "report", "sorted", "total"], runs
  assert runs.index("sorted") < min(runs.index("total"), runs.index("count")), runs
  assert runs.index("report") > max(runs.index("total"), runs.index("count")), runs
  assert (values / "sorted").read_text() == "1 2 3\n"

  ends = ["aside", "report"]
  out, runs = build()
  assert out == ["6 over 3", "aside: first"], out
  assert sorted(runs) == ends, "nothing changed, so only the unreferenced ends run: %s" % runs

  time.sleep(1.1)
  (tmp_path / "numbers.txt").write_text("40 10 20 30\n")
  out, runs = build()
  assert out == ["100 over 4", "aside: first"], out
  kept = [n for n in runs if n != "aside"]
  assert kept == ["sorted", "total", "count", "report"] or kept == ["sorted", "count", "total", "report"], runs
  assert (values / "sorted").read_text() == "10 20 30 40\n"
  assert (values / "total").read_text() == "100\n"
  assert (values / "count").read_text() == "4\n"

  time.sleep(1.1)
  (tmp_path / "other.txt").write_text("second\n")
  out, runs = build()
  assert out == ["100 over 4", "aside: second"], out
  assert sorted(runs) == ends, runs

  time.sleep(1.1)
  (values / "total").write_text("7\n")
  out, runs = build()
  assert out == ["7 over 4", "aside: second"], out
  assert sorted(runs) == ends, "a value changed in the middle reruns no kept value: %s" % runs
  assert not (values / "report").exists() and not (values / "aside").exists()


@pytest.mark.engines("lua")
def test_a_failed_target_keeps_failing_under_delete_on_error(amk, tmp_path):
  body = "\n".join([
    "@lua.import.target",
    "define up",
    "print('partial')",
    "if not io.open('fixed') then error('boom') end",
    "endef",
    "@lua.import.target",
    "define down",
    ran("down"),
    "print('got [@up@]')",
    "endef",
    "",
  ])
  log = tmp_path / "runs.log"
  value = tmp_path / ".amk/goals/up"

  mk = tmp_path / "strict.mk"
  mk.write_text(".DELETE_ON_ERROR:\n" + body)
  for _ in range(2):
    log.write_text("")
    r = sh(amk, ["-s", "-f", str(mk), "down"], cwd=tmp_path, timeout=120)
    assert r.returncode == 2, r.stdout + r.stderr
    assert "boom" in r.stderr, r.stderr
    assert not value.exists(), "the failed target left a value behind"
    assert log.read_text() == "", "the downstream ran on a failed upstream"
  (tmp_path / "fixed").write_text("")
  r = sh(amk, ["-s", "-f", str(mk), "down"], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "got [partial]", r.stdout + r.stderr

  (tmp_path / "fixed").unlink()
  value.unlink()
  mk = tmp_path / "loose.mk"
  mk.write_text(body)
  r = sh(amk, ["-s", "-f", str(mk), "down"], cwd=tmp_path, timeout=120)
  assert r.returncode == 2, r.stdout + r.stderr
  assert value.read_text() == "partial\n", "without the special target make keeps what a failed recipe wrote"


probe = [
  "@lua.import.target",
  "define probe",
  "print('{0}', os.getenv('who'), io.read('a'))",
  "endef",
  "",
]


@pytest.mark.engines("lua")
def test_an_unreferenced_target_runs_every_time_and_keeps_no_file(amk, tmp_path):
  mk = tmp_path / "probe.mk"

  def run(body, who, stdin):
    mk.write_text("\n".join(probe).format(body))
    flags = ["-s", "--warn-undefined-variables", "-f", str(mk), "probe"]
    r = sh(amk, flags, cwd=tmp_path, timeout=120, env={"who": who}, stdin=stdin)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stderr == "", "a makefile with no reference read the value directory: " + r.stderr
    return r.stdout.split()

  assert run("one", "x", "first") == ["one", "x", "first"]
  assert run("one", "y", "first") == ["one", "y", "first"], "the environment changed"
  assert run("one", "y", "second") == ["one", "y", "second"], "standard input changed"
  assert run("two", "y", "second") == ["two", "y", "second"], "the body changed"
  assert not (tmp_path / ".amk").exists(), "no reference, so no value directory"
  r = sh(amk, ["-p", "-n", "-f", str(mk), "probe"], cwd=tmp_path, timeout=120, stdin="")
  assert ".amk/goals" not in r.stdout, "no reference, so no rule names the value directory"


@pytest.mark.engines("lua")
def test_a_value_is_kept_only_for_a_body_that_names_it(amk, tmp_path):
  mk = tmp_path / "kept.mk"
  mk.write_text("\n".join([
    "@lua.import.target",
    "define named",
    ran("named"),
    "print('n')",
    "endef",
    "@lua.import.target",
    "define reader",
    ran("reader"),
    "print('read @named@')",
    "endef",
    "",
  ]))
  for _ in range(2):
    r = sh(amk, ["-s", "-f", str(mk), "reader", "named"], cwd=tmp_path, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout == "read n\nn\n", r.stdout + r.stderr
  assert (tmp_path / "runs.log").read_text().split() == ["named", "reader", "reader"]


@pytest.mark.engines("lua")
def test_a_file_target_is_a_value_too(amk, tmp_path):
  mk = tmp_path / "file.mk"
  mk.write_text("\n".join([
    "@lua.import.target",
    "define shout",
    "print(string.upper('@words.txt@'))",
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
  assert not (tmp_path / ".amk/goals/words.txt").exists(), "a plain file is read where it is"


@pytest.mark.engines("lua")
def test_a_plain_rule_reads_a_value_at_recipe_time(amk, tmp_path):
  mk = tmp_path / "plain.mk"
  mk.write_text("\n".join([
    "@lua.import.target",
    "define answer",
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
def test_an_imported_program_has_no_size_limit(amk, tmp_path):
  padding = "# " + "x" * 300000
  mk = tmp_path / "big.mk"
  mk.write_text("\n".join([
    "@micropy.import.target",
    "define big",
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
def test_awk_and_jq_imported_targets_take_their_program_their_own_way(amk, tmp_path):
  mk = tmp_path / "argv.mk"
  mk.write_text("\n".join([
    "@awk.import.target",
    "define words",
    'BEGIN { print "a b c" }',
    "endef",
    "@jq.import.target",
    "define count",
    '"@words@" | split(" ") | length',
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
def test_an_imported_target_reads_make_state_through_the_handle(amk, tmp_path):
  mk = tmp_path / "handle.mk"
  mk.write_text("\n".join([
    "flavor := plain",
    "@lua.import.target",
    "define probe",
    'print(amk.expand("$(goal.dir) $(flavor)") .. " " .. amk.var.flavor)',
    'amk.var.flavor = "changed"',
    "endef",
    "show: probe",
    "\t@echo after=$(flavor)",
    "",
  ]))
  r = sh(amk, ["-s", "-f", str(mk), "goal.dir=vals", "show"], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.split("\n")[:2] == ["vals plain plain", "after=plain"], r.stdout + r.stderr


@pytest.mark.engines("lua")
def test_independent_imported_targets_run_at_once_under_j(amk, tmp_path):
  mk = tmp_path / "par.mk"
  mk.write_text("\n".join([
    "@lua.import.target",
    "define slow1",
    "os.execute('sleep 0.6') print(1)",
    "endef",
    "@lua.import.target",
    "define slow2",
    "os.execute('sleep 0.6') print(2)",
    "endef",
    "@lua.import.target",
    "define total",
    "print(@slow1@ + @slow2@)",
    "endef",
    "",
  ]))
  start = time.time()
  r = sh(amk, ["-s", "-j2", "-f", str(mk), "total"], cwd=tmp_path, timeout=120)
  elapsed = time.time() - start
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "3", r.stdout
  assert elapsed < 1.1, f"the two slow targets ran one after the other: {elapsed:.2f}s"


@pytest.mark.engines("awk", "js")
def test_an_imported_body_reaches_its_engine_as_written(amk, tmp_path):
  mk = tmp_path / "literal.mk"
  mk.write_text("\n".join([
    "x := from make",
    "@awk.import.target",
    "define second",
    'BEGIN { $0 = "one two three"; print $2, "a @ b @ c" }',
    "endef",
    "@js.import.target",
    "define templated",
    "const x = 'from js'; print(`${x} $(x)`);",
    "endef",
    "",
  ]))
  r = sh(amk, ["-s", "-f", str(mk), "second", "templated"], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.split("\n")[:2] == ["two a @ b @ c", "from js $(x)"], r.stdout + r.stderr


@pytest.mark.engines("lua", "s7")
def test_a_value_is_spliced_raw(amk, tmp_path):
  mk = tmp_path / "raw.mk"
  mk.write_text("\n".join([
    "@lua.import.target",
    "define g1",
    "print('1 2 3')",
    "endef",
    "@s7.import.target",
    "define summed",
    '(format #t "~A ~S" (apply + (list @g1@)) "@g1@")',
    "endef",
    "",
  ]))
  r = sh(amk, ["-s", "-f", str(mk), "summed"], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == '6 "1 2 3"', r.stdout + r.stderr


@pytest.mark.engines("lua")
def test_a_reference_folds_case_and_may_come_first(amk, tmp_path):
  mk = tmp_path / "fold.mk"
  mk.write_text("\n".join([
    "@lua.import.target",
    "define shown",
    "print('@JSON@ @Json@')",
    "endef",
    "@lua.import.target",
    "define json",
    "print('[]')",
    "endef",
    "",
  ]))
  r = sh(amk, ["-s", "-j2", "-f", str(mk), "shown"], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "[] []", r.stdout + r.stderr


@pytest.mark.engines("lua")
def test_a_file_on_disk_is_no_target_without_a_rule(amk, tmp_path):
  body = ["@lua.import.target", "define shown", "print('@Input.txt@')", "endef", ""]
  mk = tmp_path / "disk.mk"
  mk.write_text("\n".join(body))
  (tmp_path / ".amk/goals").mkdir(parents=True)
  clean = sh(amk, ["-s", "-f", str(mk), "shown"], cwd=tmp_path, timeout=120)
  (tmp_path / "input.txt").write_text("here\n")
  (tmp_path / ".amk/goals/input.txt").write_text("here\n")
  dirty = sh(amk, ["-s", "-f", str(mk), "shown"], cwd=tmp_path, timeout=120)
  for r in (clean, dirty):
    assert r.returncode == 2, r.stdout + r.stderr
    assert "@Input.txt@ in imported target 'shown' names no target" in r.stderr, r.stderr
  assert clean.stderr == dirty.stderr, "what is on disk changed how the makefile reads"

  mk.write_text("\n".join(body + ["input.txt: ;", ""]))
  r = sh(amk, ["-s", "-f", str(mk), "shown"], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "here", r.stdout + r.stderr


@pytest.mark.engines("lua")
def test_a_reference_must_name_exactly_one_target(amk, tmp_path):
  head = ["@lua.import.target", "define shown", "print('@value@')", "endef"]
  one = ["@lua.import.target", "define {0}", "print(1)", "endef"]
  mk = tmp_path / "none.mk"
  mk.write_text("\n".join(head + [""]))
  r = sh(amk, ["-s", "-f", str(mk), "shown"], cwd=tmp_path, timeout=120)
  assert r.returncode != 0, r.stdout
  assert "@value@ in imported target 'shown' names no target" in r.stderr, r.stderr
  assert "spaces" in r.stderr, r.stderr
  mk = tmp_path / "two.mk"
  mk.write_text("\n".join(head + [l.format("Value") for l in one] + [l.format("VALUE") for l in one] + [""]))
  r = sh(amk, ["-s", "-f", str(mk), "shown"], cwd=tmp_path, timeout=120)
  assert r.returncode != 0, r.stdout
  assert "names both" in r.stderr and "'Value'" in r.stderr and "'VALUE'" in r.stderr, r.stderr

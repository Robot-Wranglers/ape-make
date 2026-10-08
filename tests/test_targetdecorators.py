"""Pins the target decorator rewrite.

A column-0 `@name` or `@name(args)` directly above a target or an assignment becomes a make
call by its kind. It runs after the define decorators, and an at line with nothing directly
below prints back as written. Pinned: the printed text, each kind run through make, around on
a macro through m5 from the prelude, and both decorators in one makefile."""

import pytest

from conftest import sh


def pre(amk, tmp_path, text, name="in.mk"):
  mk = tmp_path / name
  mk.write_text(text)
  r = sh(amk, ["--preprocessor", str(mk)], cwd=tmp_path, timeout=60)
  return r


def run(amk, tmp_path, text, goal="all"):
  mk = tmp_path / "main.mk"
  mk.write_text(text)
  return sh(amk, ["-s", "-f", str(mk), goal], cwd=tmp_path, timeout=120)


def test_a_before_decorator_joins_the_recipe_as_a_call(amk, tmp_path):
  r = pre(amk, tmp_path, "@log(hi)\nall:\n\ttrue\n")
  assert r.returncode == 0, r.stderr
  assert "all:\n\t$(call log,hi)\n\ttrue\n" in r.stdout, r.stdout


def test_a_block_decorator_rides_above_an_assignment(amk, tmp_path):
  r = pre(amk, tmp_path, "@note(x) ::: prefix\nfoo = 1\n")
  assert r.returncode == 0, r.stderr
  assert "$(call note,x)\nfoo = 1\n" in r.stdout, r.stdout


def test_a_mark_decorator_names_its_target(amk, tmp_path):
  r = pre(amk, tmp_path, "@amk.file\nout.txt:\n\ttouch $@\n@stamp(x) ::: mark\nall:\n\ttrue\n")
  assert r.returncode == 0, r.stderr
  assert "$(call amk.file,out.txt)\nout.txt:\n\ttouch $@\n" in r.stdout, r.stdout
  assert "$(call stamp,all,x)\nall:\n\ttrue\n" in r.stdout, r.stdout


def test_the_value_marks_lower_to_their_special_targets(amk, tmp_path):
  mk = tmp_path / "main.mk"
  mk.write_text("@amk.file\nout.txt:\n\ttouch $@\n@amk.nocache\nstamp:\n\tdate\nall:\n\ttrue\n")
  r = sh(amk, ["-p", "-n", "-f", str(mk), "all"], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert ".AMK_FILE: out.txt" in r.stdout and ".AMK_NOCACHE: stamp" in r.stdout, r.stdout


def test_an_after_return_decorator_runs_behind_the_body(amk, tmp_path):
  r = run(amk, tmp_path, "mark = echo mark-$(1)\n@mark(x) ::: after_return\nall:\n\techo body\n")
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.splitlines() == ["body", "mark-x"], r.stdout


def test_an_after_throw_decorator_runs_only_when_the_body_fails(amk, tmp_path):
  r = run(amk, tmp_path, "mark = echo caught\n@mark ::: after_throw\nall:\n\tfalse\n")
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.splitlines() == ["caught"], r.stdout


@pytest.mark.xfail(
  reason="amk's recipe shell runs with errexit, so a failing body stops the shell before the after "
  "call the plain connector chains; compose.mk's shell has no errexit, so there it runs.",
  strict=True,
)
def test_an_after_decorator_runs_whatever_the_body_returns(amk, tmp_path):
  r = run(amk, tmp_path, "mark = echo mark\n@mark ::: after\nall:\n\tfalse\n")
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.splitlines() == ["mark"], r.stdout


def test_stacked_kinds_run_in_source_order(amk, tmp_path):
  text = "pre = echo pre-$(1)\npost = echo post-$(1)\n@pre(a)\n@pre(b)\n@post(c) ::: after_return\nall:\n\techo body\n"
  r = run(amk, tmp_path, text)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.splitlines() == ["pre-a", "pre-b", "body", "post-c"], r.stdout


def test_a_companion_assignment_supplies_the_kind(amk, tmp_path):
  r = run(amk, tmp_path, "mark = echo mark\nmark.advice := after_return\n@mark\nall:\n\techo body\n")
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.splitlines() == ["body", "mark"], r.stdout


def test_block_decorators_bracket_an_assignment(amk, tmp_path):
  r = run(amk, tmp_path, "note = $(info note $(1))\n@note(above) ::: prefix\n@note(below) ::: postfix\nfoo = 1\nall:\n\techo foo=$(foo)\n")
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.splitlines() == ["note above", "note below", "foo=1"], r.stdout


def test_an_around_decorator_calls_through_to_the_moved_body(amk, tmp_path):
  r = run(amk, tmp_path, "wrap = echo before ; $($(1)) ; echo after\n@wrap ::: around\nall:\n\techo body\n")
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.splitlines() == ["before", "body", "after"], r.stdout


def test_an_around_decorator_propagates_a_failing_body(amk, tmp_path):
  r = run(amk, tmp_path, "wrap = $($(1))\n@wrap ::: around\nall:\n\tfalse\n")
  assert r.returncode != 0, r.stdout + r.stderr


def test_an_around_decorator_on_a_macro_calls_through_to_the_frozen_value(amk, tmp_path):
  r = run(amk, tmp_path, "wrap = [$(call $(1),$(2))]\n@wrap ::: around\ngreet = hi $(1)\n$(info $(call greet,bob))\nall:\n\ttrue\n")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[hi bob]" in r.stdout, r.stdout


def test_a_define_decorator_and_a_target_decorator_share_a_makefile(amk, tmp_path):
  text = "\n".join([
    "probe_star = $(info star $(1))",
    "log = $(info log $(1))",
    "@probe",
    "define d",
    "endef",
    "@log(hi)",
    "all:",
    "\ttrue",
    "",
  ])
  r = run(amk, tmp_path, text)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "star d" in r.stdout and "log hi" in r.stdout, r.stdout


def test_a_decorator_with_a_blank_line_before_its_target_is_left_alone(amk, tmp_path):
  text = "@log(hi)\n\nall:\n\ttrue\n"
  r = pre(amk, tmp_path, text)
  assert r.returncode == 0, r.stderr
  assert r.stdout == text


def test_a_stray_decorator_line_reaches_make_and_stops_it(amk, tmp_path):
  # nothing takes the line, so make itself refuses it.
  r = run(amk, tmp_path, "log = $(info log $(1))\n@log(hi)\n\nall:\n\techo body\n")
  assert r.returncode != 0, r.stdout + r.stderr
  assert "missing separator" in r.stderr, r.stderr

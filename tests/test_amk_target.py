"""Pins `@amk.target`, which makes a define a phony target whose body is one joined recipe.

Pinned: the body runs as a recipe with make's own dollars, the lines share one shell, a
failing line stops the rest, blank lines and comments cost no shell, a trailing comment is
stripped outside quotes, a line that already continues or ends in an operator is left alone,
a leading at-hash block stays the docstring, the join kinds, the text after the colon is the
prerequisites, the define is still a plain variable, and a file of the name does not stop it.
"""

import pytest

from conftest import sh


def run(amk, tmp_path, lines, goal="report", flags=()):
  mk = tmp_path / "target.mk"
  mk.write_text("\n".join(lines) + "\n")
  return sh(amk, ["-s", *flags, "-f", str(mk), goal], cwd=tmp_path, timeout=120)


def test_the_body_is_a_recipe_with_make_dollars(amk, tmp_path):
  r = run(amk, tmp_path, [
    "who := world",
    "@amk.target",
    "define report",
    "  v=shell; echo hello $(who) from $$v",
    "endef",
  ])
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "hello world from shell", r.stdout + r.stderr


def test_the_lines_share_one_shell_and_fail_fast(amk, tmp_path):
  r = run(amk, tmp_path, [
    "@amk.target",
    "define report",
    "  v=kept",
    "  echo $$v",
    "  false",
    "  echo never",
    "endef",
  ])
  assert r.returncode != 0, r.stdout + r.stderr
  assert r.stdout.split() == ["kept"], r.stdout + r.stderr


def test_blank_lines_and_comments_cost_no_shell(amk, tmp_path):
  r = run(amk, tmp_path, [
    "@amk.target",
    "define report",
    "  @# the docstring stays",
    "  # a comment line",
    "",
    "  echo one # trailing",
    "  echo '# not a comment'",
    "endef",
  ], flags=("-n",))
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.splitlines() == ["# the docstring stays", "\\", "echo one && \\", "echo '# not a comment'"], r.stdout + r.stderr


def test_a_continued_or_operator_line_is_left_alone(amk, tmp_path):
  r = run(amk, tmp_path, [
    "@amk.target",
    "define report",
    "  printf '%s\\n' one \\",
    "    two |",
    "  tr a-z A-Z",
    "endef",
  ])
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.split() == ["ONE", "TWO"], r.stdout + r.stderr


@pytest.mark.parametrize("at, expect", [
  ("@amk.target{join=;}", ["\\", "v=kept ; \\", "echo $v ; \\", "echo done"]),
  ("@amk.target{join=none}", ["v=kept", "echo $v ;", "echo done"]),
], ids=["semicolon", "none"])
def test_the_join_kinds(amk, tmp_path, at, expect):
  r = run(amk, tmp_path, [at, "define report", "  v=kept", "  echo $$v ;", "  echo done", "endef"], flags=("-n",))
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.splitlines() == expect, r.stdout + r.stderr


def test_the_text_after_the_colon_is_the_prerequisites(amk, tmp_path):
  r = run(amk, tmp_path, [
    "first:",
    "\techo first ran",
    "@amk.target{join=&&} : first",
    "define report",
    "  echo report ran",
    "endef",
    "$(info body=[$(report)])",
  ])
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.splitlines() == ["body=[  echo report ran]", "first ran", "report ran"], r.stdout + r.stderr


def test_a_defined_preamble_opens_the_recipe(amk, tmp_path):
  r = run(amk, tmp_path, [
    "report.preamble = v=pre; echo $$v",
    "@amk.target",
    "define report",
    "  echo $$v body",
    "endef",
  ])
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.split() == ["pre", "pre", "body"], r.stdout + r.stderr


def test_a_space_amk_line_sources_the_shell_side(amk, tmp_path):
  r = run(amk, tmp_path, [
    "$(amk.require sqlite)",
    "load tspace",
    "$(tspace.create shop)",
    "@shop.amk",
    "define report",
    "  shop.out note 1",
    "  shop.all",
    "endef",
  ])
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == '{"t":["note",1]}', r.stdout + r.stderr


def test_a_target_of_the_name_is_phony(amk, tmp_path):
  (tmp_path / "report").write_text("")
  r = run(amk, tmp_path, ["@amk.target", "define report", "  echo ran anyway", "endef"])
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "ran anyway", r.stdout + r.stderr

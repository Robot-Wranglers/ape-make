"""Pins an imported target's engine flags.

`$(<name>.import.target target,program,flags)`, its star form `$(<name>.import.target* var,flags)`,
and `@<name>.import.target flags` above a define pass flags to the engine ahead of the program.
Pinned: a jq target with no flags reads its standard input as `.`, `--null-input` makes it a
generator, every form carries the flags, another engine takes its own flags, and a kept value
read through `@name@` keeps its target's flags.
"""

import pytest

from conftest import sh


def _run(amk, tmp_path, lines, goal, stdin=None):
  mk = tmp_path / "flags.mk"
  mk.write_text("\n".join(lines) + "\n")
  return sh(amk, ["-s", "-f", str(mk), goal], cwd=tmp_path, timeout=120, stdin=stdin)


@pytest.mark.engines("jq")
def test_jq_without_flags_filters_stdin(amk, tmp_path):
  r = _run(amk, tmp_path, [
    "@jq.import.target",
    "define pick",
    "  .name",
    "endef",
  ], "pick", stdin='{"name": "a b"}\n')
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == '"a b"', r.stdout + r.stderr


@pytest.mark.engines("jq")
@pytest.mark.parametrize("lines", [
  ["@jq.import.target --null-input", "define gen", "  [range(3)] | add", "endef"],
  ["$(jq.import.target gen,[range(3)] | add,--null-input)"],
  ["define gen", "  [range(3)] | add", "endef", "$(jq.import.target* gen, --null-input)"],
], ids=["at-line", "plain", "star"])
def test_null_input_generates_in_every_form(amk, tmp_path, lines):
  r = _run(amk, tmp_path, lines, "gen", stdin="")
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "3", r.stdout + r.stderr


@pytest.mark.engines("awk")
def test_another_engine_takes_its_own_flags(amk, tmp_path):
  r = _run(amk, tmp_path, [
    "@awk.import.target -v greeting=hi",
    "define hello",
    "  BEGIN { print greeting }",
    "endef",
  ], "hello")
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "hi", r.stdout + r.stderr


@pytest.mark.engines("awk", "jq")
def test_a_kept_value_keeps_its_flags(amk, tmp_path):
  r = _run(amk, tmp_path, [
    "@jq.import.target --null-input",
    "define base",
    "  [20, 21] | add",
    "endef",
    "@awk.import.target",
    "define bump",
    "  BEGIN { print @base@ + 1 }",
    "endef",
  ], "bump", stdin="")
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "42", r.stdout + r.stderr

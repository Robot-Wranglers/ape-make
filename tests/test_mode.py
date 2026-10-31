"""Pins amk.mode: there is always a mode, default unless one is set, and setting one is checked.

Pinned: an unknown mode is fatal and names the known ones, and a mode set after a file target
is fatal and names that target, while the same mode set before any target, on the command
line, or through AMK_MODE is accepted.
"""

import pytest

from conftest import sh


def run(amk, tmp_path, text, args=(), env=None):
  (tmp_path / "mode.mk").write_text(text + "\n")
  return sh(amk, ["-s", "-f", "mode.mk", *args], cwd=tmp_path, env=env, timeout=120)


def test_an_unknown_mode_is_fatal(amk, tmp_path):
  r = run(amk, tmp_path, "$(amk.mode bogus)\nall:\n\ttrue")
  assert r.returncode != 0, r.stdout
  assert "bogus" in r.stderr and "dataflow" in r.stderr and "default" in r.stderr, r.stderr


def test_a_mode_after_a_file_target_is_fatal(amk, tmp_path):
  r = run(amk, tmp_path, "out.txt:\n\ttouch $@\n$(amk.mode dataflow)")
  assert r.returncode != 0, r.stdout
  assert "out.txt" in r.stderr, r.stderr


@pytest.mark.parametrize("text,env", [
  pytest.param("$(amk.mode dataflow)\n", None, id="before any target"),
  pytest.param("", {"AMK_MODE": "dataflow"}, id="environment"),
])
def test_a_mode_set_before_any_target_is_accepted(amk, tmp_path, text, env):
  r = run(amk, tmp_path, text + "out.txt:\n\techo mode=$(amk.mode)", env=env)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "mode=dataflow" in r.stdout, r.stdout


def test_an_unknown_mode_on_the_command_line_is_fatal(amk, tmp_path):
  r = run(amk, tmp_path, "out.txt:\n\ttrue", ("amk.mode=bogus",))
  assert r.returncode != 0, r.stdout
  assert "bogus" in r.stderr, r.stderr


@pytest.mark.engines("lua")
def test_a_value_is_the_same_under_every_mode(amk, tmp_path):
  text = "\n".join([
    "amk.dataflow_dir := values",
    "seed:",
    "\techo 3",
    "@lua.import.target",
    "define show",
    "print(>>seed<< * 2)",
    "endef",
  ])
  plain = run(amk, tmp_path, text, ("show",))
  assert plain.returncode == 0, plain.stdout + plain.stderr
  flow = run(amk, tmp_path, text, ("show", "amk.mode=dataflow"))
  assert flow.returncode == 0, flow.stdout + flow.stderr
  assert plain.stdout == flow.stdout == "6\n", (plain.stdout, flow.stdout)

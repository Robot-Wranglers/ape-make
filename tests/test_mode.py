"""Pins amk.mode: there is always a mode, default unless one is set, and setting one is checked.

Pinned: an unknown mode is fatal and names the known ones, and a mode set after a file target
is fatal and names that target, while the same mode set before any target, on the command
line, or through AMK_MODE is accepted. Every test here waits on the mode subsystem.
"""

import pytest

from conftest import sh

pending = pytest.mark.xfail(strict=True, reason="fa05d9d073: the mode subsystem")


def run(amk, tmp_path, text, args=(), env=None):
  (tmp_path / "mode.mk").write_text(text + "\n")
  return sh(amk, ["-s", "-f", "mode.mk", *args], cwd=tmp_path, env=env, timeout=120)


@pending
def test_an_unknown_mode_is_fatal(amk, tmp_path):
  r = run(amk, tmp_path, "$(amk.mode bogus)\nall:\n\ttrue")
  assert r.returncode != 0, r.stdout
  assert "bogus" in r.stderr and "dataflow" in r.stderr and "default" in r.stderr, r.stderr


@pending
def test_a_mode_after_a_file_target_is_fatal(amk, tmp_path):
  r = run(amk, tmp_path, "out.txt:\n\ttouch $@\n$(amk.mode dataflow)")
  assert r.returncode != 0, r.stdout
  assert "out.txt" in r.stderr, r.stderr


@pending
@pytest.mark.parametrize("text,env", [
  pytest.param("$(amk.mode dataflow)\n", None, id="before any target"),
  pytest.param("", {"AMK_MODE": "dataflow"}, id="environment"),
])
def test_a_mode_set_before_any_target_is_accepted(amk, tmp_path, text, env):
  r = run(amk, tmp_path, text + "out.txt:\n\techo mode=$(amk.mode)", env=env)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "mode=dataflow" in r.stdout, r.stdout


@pending
def test_an_unknown_mode_on_the_command_line_is_fatal(amk, tmp_path):
  r = run(amk, tmp_path, "out.txt:\n\ttrue", ("amk.mode=bogus",))
  assert r.returncode != 0, r.stdout
  assert "bogus" in r.stderr, r.stderr

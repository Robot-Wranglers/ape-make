"""Pins `$(amk.require names...)`: empty when every name is in `.FEATURES`, fatal otherwise.

The fatal message names the function, every name asked for and the missing ones, and the
makefile line that asked. Names separate by spaces or commas. The message is red only on a
terminal, so a captured stderr never carries the escape.
"""

from conftest import sh


def run(amk, tmp_path, text):
  mk = tmp_path / "require.mk"
  mk.write_text(text + "\nall:\n\t@echo ran\n")
  return sh(amk, ["-s", "-f", str(mk)], timeout=120)


def test_present_names_expand_to_nothing(amk, tmp_path):
  r = run(amk, tmp_path, "$(info [$(amk.require jq awk)])")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[]" in r.stdout and "ran" in r.stdout, r.stdout


def test_commas_and_spaces_both_separate(amk, tmp_path):
  r = run(amk, tmp_path, "$(info [$(amk.require jq,awk sys)])")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[]" in r.stdout, r.stdout


def test_a_missing_name_is_fatal(amk, tmp_path):
  r = run(amk, tmp_path, "$(amk.require jq nosuchfeature)")
  assert r.returncode == 2, r.stdout + r.stderr
  assert "ran" not in r.stdout, r.stdout
  assert "amk.require: this makefile needs amk with jq nosuchfeature, and this amk has no nosuchfeature" in r.stderr, r.stderr
  assert "require.mk:1:" in r.stderr, r.stderr


def test_only_the_missing_names_are_reported(amk, tmp_path):
  r = run(amk, tmp_path, "$(amk.require nope1, awk nope2)")
  assert r.returncode == 2, r.stdout + r.stderr
  assert "this amk has no nope1 nope2" in r.stderr, r.stderr


def test_captured_stderr_has_no_color(amk, tmp_path):
  r = run(amk, tmp_path, "$(amk.require nosuchfeature)")
  assert r.returncode == 2, r.stdout + r.stderr
  assert "\033[" not in r.stderr, repr(r.stderr)

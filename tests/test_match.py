"""Pins the match builtins against grep.

`$(amk.match re,text)` answers the lines of the text an extended regular expression
matches, `$(amk.match.file re,path)` the same over a file, and the star form reads the
pattern or the text from a variable. Every answer is compared with `grep -E` over the same
lines, so the builtin can stand in for a parse-time grep shell.
"""

import shutil
import subprocess

import pytest

from conftest import sh

TEXT = "\n".join([
  "foo: bar",
  "__main__: help",
  "  indented: x",
  "__main__:= value",
  "lib.pre: a",
  "echo __main__: not a header",
  "last",
])

CASES = {
  "header": r"^__main__[[:blank:]]*:([^=]|$)",
  "pre": r"^[A-Za-z0-9_.%/-]+\.pre:",
  "colon": r":",
  "none": r"^zzz",
  "last": r"t$",
}


def host_grep(pattern, text):
  r = subprocess.run(["grep", "-E", pattern], input=text + "\n", capture_output=True, text=True)
  return r.stdout.rstrip("\n")


def run(amk, tmp_path, text):
  mk = tmp_path / "match.mk"
  mk.write_text(text + "\nall:\n\ttrue\n")
  return sh(amk, ["-s", "-f", str(mk)], timeout=120)


def body(name, text):
  return "\n".join([f"define {name}", *text.splitlines(), "endef"])


needs_host = pytest.mark.skipif(shutil.which("grep") is None, reason="no grep on the host")


def test_match_is_a_feature(amk, tmp_path):
  r = run(amk, tmp_path, "$(info [$(filter match,$(.FEATURES))])")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[match]" in r.stdout, r.stdout


@needs_host
@pytest.mark.parametrize("case", CASES.keys())
def test_text_matches_grep(amk, tmp_path, case):
  pattern = CASES[case]
  text = body("text", TEXT) + "\n" + body("re", pattern) + "\n$(info [$(amk.match $(value re),$(value text))])"
  r = run(amk, tmp_path, text)
  assert r.returncode == 0, r.stdout + r.stderr
  assert f"[{host_grep(pattern, TEXT)}]" in r.stdout, r.stdout


@needs_host
def test_file_matches_grep(amk, tmp_path):
  path = tmp_path / "lines.txt"
  path.write_text(TEXT + "\n")
  pattern = CASES["header"]
  text = body("re", pattern) + f"\n$(info [$(amk.match.file $(value re),{path})])"
  r = run(amk, tmp_path, text)
  assert r.returncode == 0, r.stdout + r.stderr
  assert f"[{host_grep(pattern, TEXT)}]" in r.stdout, r.stdout


def test_a_trailing_newline_is_not_a_line(amk, tmp_path):
  path = tmp_path / "lines.txt"
  path.write_text("a\n\nb\n")
  r = run(amk, tmp_path, f"$(info [$(amk.match.file ^,{path})])")
  assert r.returncode == 0, r.stdout + r.stderr
  # every line matches, the empty one included; the newline that ends the file is not a line
  assert "[a\n\nb]" in r.stdout, r.stdout


def test_a_missing_file_is_empty_with_a_warning(amk, tmp_path):
  r = run(amk, tmp_path, f"$(info [$(amk.match.file x,{tmp_path}/absent)])")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[]" in r.stdout, r.stdout
  assert "amk.match.file" in r.stderr and "absent" in r.stderr, r.stderr


def test_a_bad_pattern_is_fatal(amk, tmp_path):
  r = run(amk, tmp_path, "$(info [$(amk.match x[,x)])")
  assert r.returncode != 0, r.stdout
  assert "amk.match" in r.stderr, r.stderr


@needs_host
def test_star_reads_variables(amk, tmp_path):
  text = body("text", TEXT) + "\n" + body("re", CASES["colon"]) + "\n$(info [$(amk.match* re, text)])"
  r = run(amk, tmp_path, text)
  assert r.returncode == 0, r.stdout + r.stderr
  assert f"[{host_grep(CASES['colon'], TEXT)}]" in r.stdout, r.stdout

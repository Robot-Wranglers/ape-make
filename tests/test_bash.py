"""Pins the bash engine: `$(bash cmd)`, its other forms, and its command line.

The output keeps every line but the last newline, a comma stays in the command, it runs under
bash with pipefail whatever SHELL says, a nonzero status is fatal and names it, a missing bash
is 127, and a guest reaches the builtin through amk.call. A command under the engine's at line
is an imported target: a value computed once per run under the dataflow mode, and a failing one fails.
"""

import json
import os
import subprocess
import zipfile

import pytest

from conftest import sh


def run(amk, tmp_path, text, env=None):
  mk = tmp_path / "bash.mk"
  mk.write_text(text + "\nall:\n\ttrue\n")
  return sh(amk, ["-s", "-f", str(mk)], env=env, timeout=120)


def test_lines_are_kept(amk, tmp_path):
  r = run(amk, tmp_path, "$(info [$(bash printf 'a\\nb\\n\\nc\\n')])")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[a\nb\n\nc]" in r.stdout, r.stdout


def test_commas_stay_in_the_command(amk, tmp_path):
  r = run(amk, tmp_path, "$(info [$(bash echo a,b,c)])")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[a,b,c]" in r.stdout, r.stdout


def test_bash_runs_whatever_shell_says(amk, tmp_path):
  r = run(amk, tmp_path, "SHELL := /bin/sh\n$(info [$(bash echo $${BASH_VERSION:+bash})])")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[bash]" in r.stdout, r.stdout


@pytest.mark.parametrize("cmd,status", [
  pytest.param("exit 3", "3", id="exit"),
  pytest.param("false | true", "1", id="pipefail"),
  pytest.param("echo $${nope}", "1", id="unset"),
])
def test_a_nonzero_status_is_fatal(amk, tmp_path, cmd, status):
  r = run(amk, tmp_path, f"$(info [$(bash {cmd})])")
  assert r.returncode == 2, r.stdout + r.stderr
  assert f"bash: bash exited with status {status}" in r.stderr, r.stderr


def test_no_bash_is_127(amk, tmp_path):
  empty = tmp_path / "empty"
  empty.mkdir()
  mk = tmp_path / "bash.mk"
  mk.write_text("$(info [$(bash true)])\nall:\n\ttrue\n")
  env = {k: v for k, v in os.environ.items() if k not in ("MAKELEVEL", "MAKEFLAGS", "MFLAGS")}
  env.update(PATH=str(empty), AMK_NO_PATH="1")
  r = subprocess.run(["/bin/sh", "-c", 'exec "$0" "$@"', str(amk), "-s", "-f", str(mk)],
                     capture_output=True, text=True, env=env, timeout=120)
  assert r.returncode == 2, r.stdout + r.stderr
  assert "bash exited with status 127" in r.stderr, r.stderr


def test_the_payload_bash_reads_the_engines_zip(amk, tmp_path):
  r = run(amk, tmp_path, "$(info [$(bash [ -f /zip/__init__.mk ] && read -r line < /zip/__init__.mk && echo read)])")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[read]" in r.stdout, r.stdout


def test_the_payload_cat_and_ls_read_the_engines_zip(amk, tmp_path):
  if "bin/cat" not in sh(amk, ["--ape-list"]).stdout.split():
    pytest.skip("this build leaves cat and ls out")
  mk = tmp_path / "bash.mk"
  mk.write_text("\n".join([
    "all:",
    "\tcommand -v cat ls",
    "\techo listed=$$(ls /zip/bin)",
    "\tcat /zip/bin/amk.sh | { read -r line; echo \"first=$$line\"; }",
    "",
  ]))
  cache = tmp_path / "cache"
  r = sh(amk, ["-s", "-f", str(mk)], env={"XDG_CACHE_HOME": str(cache)}, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  found = r.stdout.splitlines()[:2]
  assert all(p.startswith(str(cache)) for p in found), found
  assert "amk.sh" in r.stdout.split("listed=")[1].split("\n")[0].split(), r.stdout
  assert "first=# The ask channel from a recipe" in r.stdout, r.stdout


def test_a_recipe_sources_a_payload_script(amk, tmp_path):
  mk = tmp_path / "bash.mk"
  mk.write_text("all:\n\tsource /zip/bin/amk.sh && echo sourced\n")
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "sourced" in r.stdout, r.stdout


def test_an_inherited_zip_name_is_replaced(amk, tmp_path):
  other = tmp_path / "other.zip"
  with zipfile.ZipFile(other, "w") as z:
    z.writestr("other.txt", "another payload\n")
  r = run(amk, tmp_path, "$(info [$(bash [ -f /zip/__init__.mk ] && echo $${COSMOPOLITAN_INIT_ZIPOS})])",
          env={"COSMOPOLITAN_INIT_ZIPOS": str(other)})
  assert r.returncode == 0, r.stdout + r.stderr
  assert f"[{amk}]" in r.stdout, r.stdout


def test_bash_is_an_engine(amk):
  r = sh(amk, ["--list-engines"])
  row = next(e for e in json.loads(r.stdout)["engines"] if e["name"] == "bash")
  assert row["aliases"] == ["sh"] and row["capabilities"]["argv"] is True, row


def test_argv_puts_options_ahead_of_the_command(amk, tmp_path):
  r = run(amk, tmp_path, "$(info [$(bash.argv -x, echo traced,twice)])")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[traced,twice]" in r.stdout and "+ echo traced,twice" in r.stderr, r.stdout + r.stderr


def test_the_alias_is_the_same_engine(amk, tmp_path):
  r = run(amk, tmp_path, "$(info [$(sh echo $${BASH_VERSION:+bash})])")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[bash]" in r.stdout, r.stdout


def test_the_flag_is_bashs_own_command_line(amk, tmp_path):
  empty = tmp_path / "empty"
  empty.mkdir()
  r = subprocess.run(["/bin/sh", "-c", 'exec "$0" "$@"', str(amk), "--bash", "-c", 'echo "$0 $*"', "zero", "one", "two"],
                     capture_output=True, text=True, timeout=120,
                     env={**{k: v for k, v in os.environ.items() if k in ("HOME", "TMPDIR")},
                          "PATH": str(empty), "XDG_CACHE_HOME": str(tmp_path / "cache")})
  assert r.stdout.strip() == "zero one two", r.stdout + r.stderr
  script = tmp_path / "s.sh"
  script.write_text('echo "${BASH_SOURCE[0]##*/} $*"\nexit 4\n')
  r = sh(amk, ["--bash", str(script), "a", "b"])
  assert r.stdout.strip() == "s.sh a b" and r.returncode == 4, r.stdout + r.stderr
  r = sh(amk, ["--bash", "--version"])
  assert "GNU bash" in r.stdout and "GNU Make" not in r.stdout, r.stdout


def test_bash_has_no_name_among_the_tools(amk, tmp_path):
  mk = tmp_path / "bash.mk"
  mk.write_text("all:\n\t@readlink \"$$(command -v bash)\" || echo a-file\n")
  r = sh(amk, ["-f", str(mk)], env={"XDG_CACHE_HOME": str(tmp_path / "cache")})
  assert r.stdout.strip() == "a-file", r.stdout + r.stderr


def test_a_target_takes_the_engines_options(amk, tmp_path):
  mk = tmp_path / "bash.mk"
  mk.write_text("\n".join([
    "@bash.target -x",
    "define traced",
    "echo from-target",
    "endef",
    "",
  ]))
  r = sh(amk, ["-f", str(mk), "traced"])
  assert r.returncode == 0, r.stdout + r.stderr
  assert "from-target" in r.stdout and "+ echo from-target" in r.stderr, r.stdout + r.stderr


@pytest.mark.engines("micropy")
def test_a_guest_reaches_it_through_call(amk, tmp_path):
  r = run(amk, tmp_path, "\n".join([
    "define prog",
    "out = amk.call('bash','X=1; printf \"%s,%s\\\\n\" $X two; echo three')",
    "print(out.splitlines())",
    "endef",
    "$(info $(micropy* prog))",
  ]))
  assert r.returncode == 0, r.stdout + r.stderr
  assert "['1,two', 'three']" in r.stdout, r.stdout


library = [
  "$(amk.mode dataflow)",
  "amk.dataflow_dir := values",
  "$(amk.include bash)",
  "@bash.import.target",
  "define listing",
  "echo x >> listing.count; printf 'a b'",
  "endef",
  "@lua.import.target",
  "define first",
  "print(('>>listing<<'):match('%S+'))",
  "endef",
  "@lua.import.target",
  "define last",
  "print(('>>listing<<'):match('%S+$'))",
  "endef",
  "both: first last",
  "\ttrue",
]


@pytest.mark.engines("lua")
def test_a_command_is_a_value_computed_once_per_run(amk, tmp_path):
  (tmp_path / "bash.mk").write_text("\n".join(library) + "\n")
  r = sh(amk, ["-s", "-f", "bash.mk", "both"], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.split() == ["a", "b"], r.stdout
  assert (tmp_path / "listing.count").read_text() == "x\n", "the command ran more than once"
  record = json.loads((tmp_path / "values" / "listing.json").read_text())
  assert record["engine"] == "bash" and record["status"] == 0, record


@pytest.mark.engines("lua")
def test_a_failing_command_fails_its_target(amk, tmp_path):
  text = "\n".join(library[:4] + ["define listing", "echo partial; exit 3", "endef", "listing.show: listing", "\ttrue"])
  (tmp_path / "bash.mk").write_text(text + "\n")
  r = sh(amk, ["-s", "-f", "bash.mk", "listing.show"], cwd=tmp_path, timeout=120)
  assert r.returncode == 2, r.stdout + r.stderr
  assert "Error 3" in r.stderr, r.stderr
  assert not (tmp_path / "values" / "listing").exists()
  assert (tmp_path / "values" / "listing.failed").read_text() == "partial\n"

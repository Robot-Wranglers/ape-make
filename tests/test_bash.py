"""Pins `$(amk.bash cmd)` and the payload's bash library.

The output keeps every line but the last newline, a comma stays in the command, it runs under
bash with pipefail whatever SHELL says, a nonzero status is fatal and names it, a missing bash
is 127, and a guest reaches the builtin through amk.call. A command under the library's at line
is an imported target: a value computed once per run under the dataflow mode, and a failing one fails.
"""

import json
import os
import subprocess

import pytest

from conftest import sh


def run(amk, tmp_path, text, env=None):
  mk = tmp_path / "bash.mk"
  mk.write_text(text + "\nall:\n\ttrue\n")
  return sh(amk, ["-s", "-f", str(mk)], env=env, timeout=120)


def test_lines_are_kept(amk, tmp_path):
  r = run(amk, tmp_path, "$(info [$(amk.bash printf 'a\\nb\\n\\nc\\n')])")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[a\nb\n\nc]" in r.stdout, r.stdout


def test_commas_stay_in_the_command(amk, tmp_path):
  r = run(amk, tmp_path, "$(info [$(amk.bash echo a,b,c)])")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[a,b,c]" in r.stdout, r.stdout


def test_bash_runs_whatever_shell_says(amk, tmp_path):
  r = run(amk, tmp_path, "SHELL := /bin/sh\n$(info [$(amk.bash echo $${BASH_VERSION:+bash})])")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[bash]" in r.stdout, r.stdout


@pytest.mark.parametrize("cmd,status", [
  pytest.param("exit 3", "3", id="exit"),
  pytest.param("false | true", "1", id="pipefail"),
  pytest.param("echo $${nope}", "1", id="unset"),
])
def test_a_nonzero_status_is_fatal(amk, tmp_path, cmd, status):
  r = run(amk, tmp_path, f"$(info [$(amk.bash {cmd})])")
  assert r.returncode == 2, r.stdout + r.stderr
  assert f"$(amk.bash ...): bash exited with status {status}" in r.stderr, r.stderr


def test_no_bash_is_127(amk, tmp_path):
  empty = tmp_path / "empty"
  empty.mkdir()
  mk = tmp_path / "bash.mk"
  mk.write_text("$(info [$(amk.bash true)])\nall:\n\ttrue\n")
  env = {k: v for k, v in os.environ.items() if k not in ("MAKELEVEL", "MAKEFLAGS", "MFLAGS")}
  env.update(PATH=str(empty), AMK_NO_PATH="1")
  r = subprocess.run(["/bin/sh", "-c", 'exec "$0" "$@"', str(amk), "-s", "-f", str(mk)],
                     capture_output=True, text=True, env=env, timeout=120)
  assert r.returncode == 2, r.stdout + r.stderr
  assert "bash exited with status 127" in r.stderr, r.stderr


@pytest.mark.engines("micropy")
def test_a_guest_reaches_it_through_call(amk, tmp_path):
  r = run(amk, tmp_path, "\n".join([
    "define prog",
    "out = amk.call('amk.bash', 'X=1; printf \"%s,%s\\\\n\" $X two; echo three')",
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
  assert record["engine"] == "lua" and record["status"] == 0, record


@pytest.mark.engines("lua")
def test_a_failing_command_fails_its_target(amk, tmp_path):
  text = "\n".join(library[:4] + ["define listing", "echo partial; exit 3", "endef", "listing.show: listing", "\ttrue"])
  (tmp_path / "bash.mk").write_text(text + "\n")
  r = sh(amk, ["-s", "-f", "bash.mk", "listing.show"], cwd=tmp_path, timeout=120)
  assert r.returncode == 2, r.stdout + r.stderr
  assert "Error 3" in r.stderr, r.stderr
  assert not (tmp_path / "values" / "listing").exists()
  assert (tmp_path / "values" / "listing.failed").read_text() == "partial\n"

"""Pins the boot: a payload's entry, `__main__` under an engine's extension, takes over the run.

A shell entry runs by its path under /zip under the payload's bash, so the script is its own
argument zero, the caller's arguments follow, and the engine names itself in
COSMOPOLITAN_INIT_ZIPOS. A run already booted skips it, and one that cannot use the payload's
bash says so on stderr. `--bundle-main` writes the entry from a file's extension.
"""

import os
import pty
import select
import subprocess

import pytest

from conftest import sh

script = "\n".join([
  'echo "zero=$0 source=${BASH_SOURCE[0]} args=$*"',
  'echo "self=${COSMOPOLITAN_INIT_ZIPOS}"',
  '[ -f /zip/bin/amk.sh ] && echo reads-zip',
  "",
])


@pytest.fixture(scope="module")
def booting(amk, tmp_path_factory):
  """A copy of the binary whose payload carries a boot script, and an entry makefile a run falls back to."""
  src = tmp_path_factory.mktemp("boot")
  (src / "entry.mk").write_text("all:\n\t@echo ran-as-make\n")
  (src / "__main__.sh").write_text(script)
  out = src / "boot.amk"
  r = sh(amk, ["--bundle", "entry.mk", "__main__.sh", "--out", str(out)], cwd=src)
  assert r.returncode == 0, r.stderr
  return out


def bare(binary, args, **env):
  """A run with only the named environment, for the cases a missing variable decides."""
  return subprocess.run(["/bin/sh", "-c", 'exec "$0" "$@"', str(binary), *args],
                        capture_output=True, text=True, env=env, timeout=120)


def test_the_script_runs_by_its_path(booting):
  r = sh(booting, ["one", "two"])
  assert r.returncode == 0, r.stdout + r.stderr
  assert "zero=/zip/__main__.sh source=/zip/__main__.sh args=one two" in r.stdout, r.stdout
  assert f"self={booting}" in r.stdout, r.stdout
  assert "reads-zip" in r.stdout, r.stdout
  assert r.stderr == "", r.stderr


def test_a_booted_run_skips_the_script(booting):
  r = sh(booting, ["-s"], env={"AMK_BOOTED": "1"})
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "ran-as-make", r.stdout


def test_no_path_with_a_boot_script_warns(booting):
  r = sh(booting, [], env={"AMK_NO_PATH": "1"})
  assert "warning: AMK_NO_PATH is set, and the entry needs the payload's bash" in r.stderr, r.stderr


def test_no_cache_home_warns(booting):
  r = bare(booting, [], PATH=os.environ["PATH"])
  assert "warning: no HOME and no XDG_CACHE_HOME" in r.stderr, r.stderr


def test_a_failed_unpack_warns(booting):
  r = bare(booting, [], PATH=os.environ["PATH"], XDG_CACHE_HOME="/dev/null/cache")
  assert "warning: the payload's tools did not unpack into /dev/null/cache" in r.stderr, r.stderr


def on_a_terminal(binary, **env):
  """A run whose stderr is a terminal, and what it wrote there."""
  master, slave = pty.openpty()
  try:
    subprocess.run(["/bin/sh", "-c", 'exec "$0" "$@"', str(binary)],
                   stdout=subprocess.DEVNULL, stderr=slave, env=env, timeout=120)
    # macOS drops unread output when the last writer closes, so the read comes first.
    ready, _, _ = select.select([master], [], [], 5)
    return os.read(master, 65536).decode() if ready else ""
  finally:
    os.close(slave)
    os.close(master)


def test_a_warning_is_red_on_a_terminal(booting):
  err = on_a_terminal(booting, PATH=os.environ["PATH"])
  assert err.startswith("\033[1;31mamk: warning: no HOME"), repr(err)
  assert err.splitlines()[0].endswith("\033[0m"), repr(err)


def test_no_color_keeps_a_warning_plain(booting):
  err = on_a_terminal(booting, PATH=os.environ["PATH"], NO_COLOR="1")
  assert err.startswith("amk: warning: no HOME") and "\033[" not in err, repr(err)


def test_no_bash_warns_and_stops(booting, tmp_path):
  empty = tmp_path / "empty"
  empty.mkdir()
  r = bare(booting, ["-s", "SHELL=/bin/sh"], PATH=str(empty), AMK_NO_PATH="1")
  assert r.returncode == 127, r.stdout + r.stderr
  assert "bash: no bash on PATH" in r.stderr, r.stderr
  assert "warning: the entry /zip/__main__.sh did not run" in r.stderr, r.stderr
  assert "ran-as-make" not in r.stdout, r.stdout


def entry(amk, src, name, text, binary=None):
  """A copy of the binary with the named file as its entry, or the failed run."""
  (src / name).write_text(text)
  out = src / "tool.amk"
  r = sh(binary or amk, ["--bundle-main", name, "--out", str(out)], cwd=src)
  return out if r.returncode == 0 else r


def test_bundle_main_takes_a_shell_script_as_written(amk, tmp_path):
  out = entry(amk, tmp_path, "tool.sh", "\n".join([
    "#!/usr/bin/env bash",
    "echo \"zero=$0 args=$*\"",
    "echo '{\"a\":[1,2]}' | jq -c .a",
    "",
  ]))
  assert "__main__.sh" in sh(out, ["--ape-list"]).stdout.split()
  empty = tmp_path / "empty"
  empty.mkdir()
  r = bare(out, ["one", "two"], PATH=str(empty), XDG_CACHE_HOME=str(tmp_path / "cache"))
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.split("\n")[:2] == ["zero=/zip/__main__.sh args=one two", "[1,2]"], r.stdout


@pytest.mark.engines("lua")
def test_bundle_main_takes_another_engines_program(amk, tmp_path):
  out = entry(amk, tmp_path, "tool.lua", "print('lua entry ' .. 1 + 1)\n")
  r = sh(out, [])
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "lua entry 2", r.stdout


def test_bundle_main_takes_a_makefile_as_bundle_does(amk, tmp_path):
  out = entry(amk, tmp_path, "tool.mk", "all:\n\t@echo makefile-entry\n")
  r = sh(out, [], cwd=tmp_path)
  assert r.returncode == 0 and r.stdout.strip() == "makefile-entry", r.stdout + r.stderr


@pytest.mark.parametrize("name", ["tool.jq", "tool.txt", "tool"])
def test_bundle_main_refuses_an_extension_no_engine_runs(amk, tmp_path, name):
  r = entry(amk, tmp_path, name, ".\n")
  assert r.returncode == 2, r.stdout + r.stderr
  assert "no engine runs this extension as an entry" in r.stderr, r.stderr


@pytest.mark.engines("lua")
def test_a_payload_holds_one_entry(amk, tmp_path):
  first = entry(amk, tmp_path, "tool.sh", "echo first\n")
  kept = tmp_path / "first.amk"
  first.rename(kept)
  r = entry(amk, tmp_path, "tool.lua", "print('second')\n", binary=kept)
  assert r.returncode == 2, r.stdout + r.stderr
  assert "the payload already has an entry" in r.stderr and "__main__.sh" in r.stderr, r.stderr
  again = entry(amk, tmp_path, "tool.sh", "echo replaced\n", binary=kept)
  assert sh(again, []).stdout.strip() == "replaced"

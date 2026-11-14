"""Pins the tool engines: jq, sqlite, awk and micropython answer to their own names on PATH.

Beside the payload's tools, the tools directory holds a link per name and alias of an engine
whose command line is the tool's own. Pinned: which names are linked, each tool's version and
help are its own and never make's, a word amk would take as its own option reaches the tool,
a recipe finds the names, a boot script calls them unmodified, and micropython's flag alone
still takes a program.
"""

import os
import subprocess

import pytest

from conftest import sh

names = ["jq", "sqlite", "sqlite3", "awk", "gawk"]
micropy_names = ["micropy", "micropython"]
flags = ["jq", "sqlite", "awk"]
own = {"jq": "jq-", "sqlite": "3.", "sqlite3": "3.", "awk": "GNU Awk", "gawk": "GNU Awk"}


@pytest.fixture(scope="module")
def tools(amk, tmp_path_factory):
  """The tools directory one run of the binary fills, under a cache of its own."""
  cache = tmp_path_factory.mktemp("cache")
  mk = cache / "a.mk"
  mk.write_text("all:\n\t@command -v jq\n")
  r = sh(amk, ["-f", str(mk)], env={"XDG_CACHE_HOME": str(cache)})
  assert r.returncode == 0, r.stdout + r.stderr
  found = r.stdout.strip()
  assert found.startswith(str(cache)), found
  return os.path.dirname(found)


def test_only_the_tool_engines_are_linked(amk, engines, tools):
  links = sorted(n for n in os.listdir(tools) if os.path.islink(os.path.join(tools, n)))
  assert links == sorted(names + (micropy_names if "micropy" in engines else [])), links
  assert all(os.readlink(os.path.join(tools, n)) == str(amk) for n in links)


@pytest.mark.parametrize("name", names)
@pytest.mark.parametrize("flag", ["--version", "--help"])
def test_a_name_answers_for_itself(tools, name, flag):
  r = sh(os.path.join(tools, name), [flag])
  assert r.returncode == 0, r.stdout + r.stderr
  assert "GNU Make" not in r.stdout + r.stderr, r.stdout
  if flag == "--version":
    assert own[name] in r.stdout, r.stdout
  else:
    assert "Usage" in r.stdout + r.stderr, r.stdout + r.stderr


@pytest.mark.parametrize("name", flags)
@pytest.mark.parametrize("flag", ["--version", "--help"])
def test_an_engine_flag_answers_for_itself(amk, name, flag):
  r = sh(amk, [f"--{name}", flag])
  assert r.returncode == 0, r.stdout + r.stderr
  assert "GNU Make" not in r.stdout + r.stderr, r.stdout
  if flag == "--version":
    assert own[name] in r.stdout, r.stdout
  else:
    assert "Usage" in r.stdout + r.stderr, r.stdout + r.stderr


def test_a_tool_keeps_the_word_amk_would_take(amk, tools):
  r = sh(os.path.join(tools, "awk"), ["BEGIN { print ARGV[1] }", "--profile"])
  assert r.stdout.strip() == "--profile", r.stdout + r.stderr
  r = sh(os.path.join(tools, "jq"), ["-n", "--arg", "x", "--profile", "$x"])
  assert r.stdout.strip() == '"--profile"', r.stdout + r.stderr
  r = sh(amk, ["--jq", "-n", "--arg", "x", "--profile", "$x"])
  assert r.stdout.strip() == '"--profile"', r.stdout + r.stderr


def test_the_tools_do_their_work(tools, tmp_path):
  r = sh(os.path.join(tools, "jq"), ["-c", ".a"], stdin='{"a":[1,2]}')
  assert r.stdout.strip() == "[1,2]", r.stdout + r.stderr
  r = sh(os.path.join(tools, "sqlite3"), [":memory:", "select 1+1"])
  assert r.stdout.strip() == "2", r.stdout + r.stderr
  r = sh(os.path.join(tools, "awk"), ["-F:", "{ print $2 }"], stdin="k:v\n")
  assert r.stdout.strip() == "v", r.stdout + r.stderr
  r = sh(os.path.join(tools, "awk"), ["BEGIN { exit 3 }"])
  assert r.returncode == 3, r.stdout + r.stderr


@pytest.mark.engines("micropy")
@pytest.mark.parametrize("name", micropy_names)
def test_a_micropython_name_is_the_ports_command_line(tools, tmp_path, name):
  tool = os.path.join(tools, name)
  r = sh(tool, ["-h"])
  assert r.returncode == 0 and r.stdout.startswith("usage:"), r.stdout + r.stderr
  assert "GNU Make" not in r.stdout + r.stderr, r.stdout
  r = sh(tool, ["--version"])
  assert r.returncode == 0 and r.stdout.startswith("MicroPython v"), r.stdout + r.stderr
  r = sh(tool, ["-c", "import sys; print(sys.argv)", "a", "--profile"])
  assert r.stdout.strip() == "['-c', 'a', '--profile']", r.stdout + r.stderr
  r = sh(tool, ["-c", "import sys; sys.exit(3)"])
  assert r.returncode == 3, r.stdout + r.stderr
  (tmp_path / "script.py").write_text("import sys\nprint(__name__, sys.argv[1:])\n")
  r = sh(tool, [str(tmp_path / "script.py"), "a", "b"])
  assert r.stdout.strip() == "__main__ ['a', 'b']", r.stdout + r.stderr
  r = sh(tool, ["-m", "script", "c"], cwd=tmp_path)
  assert r.stdout.strip() == "__main__ ['c']", r.stdout + r.stderr
  r = sh(tool, ["print('no file by this name')"])
  assert r.returncode == 2 and "can't open file" in r.stderr, r.stdout + r.stderr
  r = sh(tool, [], stdin="print(6 * 7)\n")
  assert r.stdout.strip() == "42", r.stdout + r.stderr


@pytest.mark.engines("micropy")
@pytest.mark.parametrize("path", [None, "elsewhere"])
def test_a_micropython_name_has_the_payload_modules(tools, tmp_path, path):
  env = {"MICROPYPATH": str(tmp_path / path)} if path else None
  r = sh(os.path.join(tools, "micropython"), ["-c", "import amk, asyncio, mip\nprint(amk.__name__, asyncio.__name__, mip.__name__)"], env=env)
  assert r.stdout.strip() == "amk asyncio mip", r.stdout + r.stderr


@pytest.mark.engines("micropy")
@pytest.mark.parametrize("path", [None, "elsewhere"])
def test_a_boot_script_calls_micropython_unmodified(amk, tmp_path, path):
  (tmp_path / "entry.mk").write_text("all:\n\t@true\n")
  (tmp_path / "__main__.sh").write_text("micropython -c 'import asyncio, mip, sys; print(sys.argv)' a\n")
  out = tmp_path / "tool.amk"
  r = sh(amk, ["--bundle", "entry.mk", "__main__.sh", "--out", str(out)], cwd=tmp_path)
  assert r.returncode == 0, r.stderr
  empty = tmp_path / "empty"
  empty.mkdir()
  env = {"PATH": str(empty), "XDG_CACHE_HOME": str(tmp_path / "cache")}
  if path:
    env["MICROPYPATH"] = str(tmp_path / path)
  r = subprocess.run(["/bin/sh", "-c", 'exec "$0" "$@"', str(out)], capture_output=True, text=True, env=env, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "['-c', 'a']", r.stdout + r.stderr


@pytest.mark.engines("micropy")
@pytest.mark.parametrize("name", micropy_names)
def test_the_micropython_flag_reaches_it_after_a_double_dash(amk, name):
  r = sh(amk, [f"--{name}", "--", "-c", "import sys; print(sys.argv)", "a", "--profile"])
  assert r.stdout.strip() == "['-c', 'a', '--profile']", r.stdout + r.stderr
  r = sh(amk, [f"--{name}", "--", "--version"])
  assert r.returncode == 0 and r.stdout.startswith("MicroPython v"), r.stdout + r.stderr


@pytest.mark.engines("micropy")
def test_the_micropython_flag_alone_still_takes_a_program(amk, tmp_path):
  r = sh(amk, ["--micropy", "print(amk.__name__)"])
  assert r.stdout.strip() == "amk", r.stdout + r.stderr
  (tmp_path / "program.py").write_text("print('from a file')\n")
  r = sh(amk, ["--micropy", str(tmp_path / "program.py")])
  assert r.stdout.strip() == "from a file", r.stdout + r.stderr
  r = sh(amk, ["--micropy", "-"], stdin="print('from stdin')\n")
  assert r.stdout.strip() == "from stdin", r.stdout + r.stderr


def test_a_boot_script_calls_them_unmodified(amk, tmp_path):
  (tmp_path / "entry.mk").write_text("all:\n\t@true\n")
  (tmp_path / "__main__.sh").write_text("\n".join([
    "echo '{\"a\":1}' | jq -c .a",
    "sqlite3 :memory: 'select 2+3'",
    "printf 'x y\\n' | awk '{ print $2 }'",
    "",
  ]))
  out = tmp_path / "tool.amk"
  r = sh(amk, ["--bundle", "entry.mk", "__main__.sh", "--out", str(out)], cwd=tmp_path)
  assert r.returncode == 0, r.stderr
  empty = tmp_path / "empty"
  empty.mkdir()
  r = subprocess.run(["/bin/sh", "-c", 'exec "$0" "$@"', str(out)], capture_output=True, text=True,
                     env={"PATH": str(empty), "XDG_CACHE_HOME": str(tmp_path / "cache")}, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.split() == ["1", "5", "y"], r.stdout + r.stderr

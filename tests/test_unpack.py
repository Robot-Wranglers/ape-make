"""Pins `--ape-unpack`: the binary copies one payload member out to the host.

Pinned: the path on stdout that an include relies on, byte and mode fidelity, the
accepted spellings, the rejected names, the staleness rule that measures a copy against
the binary, and the include idiom with the binary found on the path.
"""

import os
from pathlib import Path

import pytest

from conftest import packed, sh

# The classic form: an installed binary found on the path hands a library to a makefile; gmsl reads its helper beside itself.
idiom = "\n".join([
  "helper := $(shell amk --ape-unpack=lib/__gmsl)",
  "include $(shell amk --ape-unpack=lib/gmsl)",
  "shout:",
  "\t@echo $(call uc,hello)",
  "",
])


@pytest.fixture
def work(tmp_path):
  d = tmp_path / "work"
  d.mkdir()
  return d


def _leftovers(d):
  return [p for p in d.rglob(".tmp.*")]


def _age(path, binary, seconds):
  """Set a copy's mtime relative to the binary's, which is the verb's whole staleness rule."""
  at = Path(binary).stat().st_mtime + seconds
  os.utime(path, (at, at))


def test_ape_list_names_every_member(amk, work):
  """The listing is every payload member, one per line, sorted, in the spelling unpack takes, and nothing else."""
  r = sh(amk, ["--ape-list"], timeout=60)
  assert r.returncode == 0, r.stderr
  names = r.stdout.splitlines()
  assert names and names == sorted(names) and len(set(names)) == len(names), r.stdout[:500]
  assert "lib/gmsl" in names and "lib/__gmsl" in names, names[:20]
  assert not any(n.startswith("/") or "//" in n or n.endswith("/") for n in names), names[:20]
  assert r.stderr == "", r.stderr
  # a listed name is one unpack accepts, and its bytes are the payload's
  r = sh(amk, ["--ape-unpack", "lib/gmsl", str(work / "gmsl")], timeout=60)
  assert r.returncode == 0 and (work / "gmsl").read_bytes() == packed(amk, "lib/gmsl").encode(), r.stderr


def test_first_write_prints_the_path(amk, work):
  """An include takes whatever the command prints, so the path is the whole of stdout."""
  r = sh(amk, ["--ape-unpack", "lib/gmsl"], cwd=work)
  assert r.returncode == 0, r.stderr
  assert r.stdout == "lib/gmsl\n"
  assert r.stderr == ""


def test_a_member_lands_byte_exact(amk, work):
  assert sh(amk, ["--ape-unpack", "lib/gmsl"], cwd=work).returncode == 0
  assert (work / "lib" / "gmsl").read_text() == packed(amk, "lib/gmsl")
  assert _leftovers(work) == []


def test_a_tool_lands_executable(amk, work):
  """The payload tools run as programs, so the mode matters as much as the bytes."""
  assert sh(amk, ["--ape-unpack", "bin/sed"], cwd=work).returncode == 0
  landed = work / "bin" / "sed"
  assert os.access(landed, os.X_OK)
  assert landed.stat().st_size > 1_000_000


@pytest.mark.parametrize("args", [
  ["--ape-unpack=lib/gmsl", "vendor/deep/g.mk"],
  ["--ape-unpack", "lib/gmsl", "vendor/deep/g.mk"],
  ["-x", "lib/gmsl", "vendor/deep/g.mk"],
])
def test_every_spelling_takes_a_destination(amk, work, args):
  """The destination's parents are created, and the printed path is the destination."""
  r = sh(amk, args, cwd=work)
  assert r.returncode == 0, r.stderr
  assert r.stdout == "vendor/deep/g.mk\n"
  assert (work / "vendor" / "deep" / "g.mk").read_text() == packed(amk, "lib/gmsl")
  assert _leftovers(work) == []


def test_a_copy_as_new_as_the_binary_is_left_alone(amk, work):
  """The no-op still prints the path, since an include reads it on every parse."""
  landed = work / "lib" / "gmsl"
  landed.parent.mkdir()
  landed.write_text("# edited by hand\n")
  _age(landed, amk, +60)
  r = sh(amk, ["--ape-unpack", "lib/gmsl"], cwd=work)
  assert r.returncode == 0, r.stderr
  assert r.stdout == "lib/gmsl\n"
  assert landed.read_text() == "# edited by hand\n"


def test_a_copy_older_than_the_binary_is_replaced(amk, work):
  """A newer binary means a newer payload, so an older copy is out of date."""
  landed = work / "lib" / "gmsl"
  landed.parent.mkdir()
  landed.write_text("# from an older payload\n")
  _age(landed, amk, -60)
  r = sh(amk, ["--ape-unpack", "lib/gmsl"], cwd=work)
  assert r.returncode == 0, r.stderr
  assert landed.read_text() == packed(amk, "lib/gmsl")


@pytest.mark.parametrize("args", [
  ["--ape-unpack", "lib/gmsl", "--force"],
  ["--ape-unpack=lib/gmsl", "--force"],
  ["-x", "--force", "lib/gmsl"],
])
def test_force_replaces_a_current_copy(amk, work, args):
  """Force is position-free after the flag, and it is never taken for a name."""
  landed = work / "lib" / "gmsl"
  landed.parent.mkdir()
  landed.write_text("# edited by hand\n")
  _age(landed, amk, +60)
  r = sh(amk, args, cwd=work)
  assert r.returncode == 0, r.stderr
  assert r.stdout == "lib/gmsl\n"
  assert landed.read_text() == packed(amk, "lib/gmsl")
  assert not (work / "--force").exists()


@pytest.mark.parametrize("args", [
  ["--ape-unpack"],
  ["--ape-unpack="],
  ["--ape-unpack", "/etc/hosts"],
  ["--ape-unpack", "../gmsl"],
  ["--ape-unpack", "lib/../../escape"],
  ["--ape-unpack", "no-such-member.mk"],
])
def test_a_bad_name_fails_and_writes_nothing(amk, work, args):
  """A name that is absent, absolute, or climbing fails as make fails, under one label."""
  r = sh(amk, args, cwd=work)
  assert r.returncode == 2, (r.stdout, r.stderr)
  assert r.stdout == ""
  assert r.stderr.startswith("amk: --ape-unpack:"), r.stderr
  assert list(work.iterdir()) == []


@pytest.fixture
def project(tmp_path):
  """A project holding the idiom's makefile and nothing of the distribution."""
  d = tmp_path / "project"
  d.mkdir()
  (d / "Makefile").write_text(idiom)
  return d


def _make(installed, project, *goals):
  path = f"{installed.parent}{os.pathsep}{os.environ['PATH']}"
  return sh(installed, ["-s", "-f", "Makefile", *goals], cwd=project, env={"PATH": path})


def test_the_include_idiom_unpacks_then_runs(installed, project):
  """The first parse writes the library beside the makefile, and its macros are in reach."""
  r = _make(installed, project, "shout")
  assert r.returncode == 0, r.stderr
  assert (project / "lib" / "gmsl").exists()
  assert r.stdout.strip() == "HELLO"


def test_the_include_idiom_leaves_a_fresh_copy_alone(installed, project):
  """Every parse and every recursion runs the verb, so a current copy must not move."""
  assert _make(installed, project, "shout").returncode == 0
  landed = project / "lib" / "gmsl"
  before = landed.stat().st_mtime_ns
  assert _make(installed, project, "shout").returncode == 0
  assert landed.stat().st_mtime_ns == before


def test_the_include_idiom_replaces_a_copy_older_than_the_binary(installed, project, amk):
  """Upgrading the install is what refreshes a project's copy."""
  landed = project / "lib" / "gmsl"
  landed.parent.mkdir()
  landed.write_text("# from an older payload\n")
  _age(landed, installed, -60)
  r = _make(installed, project, "shout")
  assert r.returncode == 0, r.stderr
  assert landed.read_text() == packed(amk, "lib/gmsl")

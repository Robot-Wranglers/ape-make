"""Pins `$(amk.sys name)`: process and host identities answered from the kernel.

Each name is compared with what the host tools print for the same process or host: the
parent pid is pytest's own, the uid and the host name match the shell's, the kernel name
and machine match uname, epoch is within a few seconds of the harness clock, and a uuid is
a version 4 string that differs between two calls.
"""

import os
import platform
import re
import socket
import time

from conftest import sh

UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


def run(amk, tmp_path, text):
  mk = tmp_path / "sys.mk"
  mk.write_text(text + "\nall:\n\ttrue\n")
  return sh(amk, ["-s", "-f", str(mk)], timeout=120)


def test_sys_is_a_feature(amk, tmp_path):
  r = run(amk, tmp_path, "$(info [$(filter sys,$(.FEATURES))])")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[sys]" in r.stdout, r.stdout


def test_identities_match_the_host(amk, tmp_path):
  names = "pid ppid uid uname arch hostname epoch"
  text = "\n".join(f"$(info {n}=[$(amk.sys {n})])" for n in names.split())
  before = int(time.time())
  r = run(amk, tmp_path, text)
  after = int(time.time())
  assert r.returncode == 0, r.stdout + r.stderr
  got = dict(re.findall(r"^(\w+)=\[(.*)\]$", r.stdout, re.M))
  assert set(got) == set(names.split()), r.stdout
  assert got["pid"].isdigit() and got["pid"] != got["ppid"]
  assert got["uid"] == str(os.getuid())
  assert got["uname"] == platform.system()
  assert got["arch"] == platform.machine()
  assert got["hostname"] == socket.gethostname()
  assert before <= int(got["epoch"]) <= after + 1


def test_ppid_is_the_caller(amk, tmp_path):
  # sh execs the binary, so the make process's parent is this test process
  r = run(amk, tmp_path, "$(info ppid=[$(amk.sys ppid)])")
  assert r.returncode == 0, r.stdout + r.stderr
  assert f"ppid=[{os.getpid()}]" in r.stdout, r.stdout


def test_uuid_is_v4_and_fresh(amk, tmp_path):
  r = run(amk, tmp_path, "$(info a=[$(amk.sys uuid)])\n$(info b=[$(amk.sys uuid)])")
  assert r.returncode == 0, r.stdout + r.stderr
  a, b = re.findall(r"^[ab]=\[(.*)\]$", r.stdout, re.M)
  assert UUID.match(a) and UUID.match(b), r.stdout
  assert a != b


def test_an_unknown_name_is_fatal(amk, tmp_path):
  r = run(amk, tmp_path, "$(info [$(amk.sys nope)])")
  assert r.returncode != 0, r.stdout
  assert "amk.sys: unknown name" in r.stderr, r.stderr

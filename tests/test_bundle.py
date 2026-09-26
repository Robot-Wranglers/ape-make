"""Pins the bundle: a binary whose payload carries its own makefile as the entry.

`--bundle main.mk lib/ --out b.amk` writes a copy of the binary with those files in
its payload, the first renamed to the entry name. Pinned: the entry runs when no
makefile is named, a named makefile still wins, recursion stays inside the binary,
the payload keeps its tools and libraries, nothing on the path is needed, a bundle
serves a zygote, and a bundle can bundle again.
"""

import os
import subprocess
import time

from conftest import BUNDLE_SRC, packed, popen, sh

# The line the bundled entry prints; smoke drives the same makefile.
entry_line = "bundle: hello from /zip/__main__.mk"


def test_the_entry_runs_when_no_makefile_is_named(bundle, tmp_path):
  r = sh(bundle, ["-s", "entry"], cwd=tmp_path)
  assert r.returncode == 0, r.stderr
  assert entry_line in r.stdout


def test_the_entry_is_the_default_goal(bundle, tmp_path):
  r = sh(bundle, ["-s"], cwd=tmp_path)
  assert r.returncode == 0, r.stderr
  assert entry_line in r.stdout


def test_a_named_makefile_still_wins(bundle, tmp_path):
  (tmp_path / "Makefile").write_text("here:\n\t@echo from-disk\n")
  r = sh(bundle, ["-s", "-f", "Makefile", "here"], cwd=tmp_path)
  assert r.returncode == 0, r.stderr
  assert r.stdout.strip() == "from-disk"
  assert entry_line not in r.stdout


def test_recursion_stays_inside_the_binary(bundle, tmp_path):
  """A child that left the binary would lose the entry and report a missing goal."""
  r = sh(bundle, ["-s", "--no-print-directory", "recurse"], cwd=tmp_path)
  assert r.returncode == 0, r.stderr
  assert entry_line in r.stdout
  assert "No rule to make target" not in (r.stdout + r.stderr)


def test_the_payload_keeps_the_base_members(amk, bundle):
  """Bundling adds files; the tools and libraries of the base binary stay."""
  assert packed(bundle, "lib/gmsl") == packed(amk, "lib/gmsl")
  assert packed(bundle, "lib/dkjson.lua") == packed(amk, "lib/dkjson.lua")
  assert packed(bundle, "lib/greet.mk") == (BUNDLE_SRC / "lib" / "greet.mk").read_text()
  assert packed(bundle, "__main__.mk") == (BUNDLE_SRC / "main.mk").read_text()


def test_a_bundle_runs_with_nothing_on_the_path(bundle, tmp_path):
  """The distribution case: only the binary, no shell tools from the host."""
  r = subprocess.run(
    ["env", "-i", f"HOME={os.environ['HOME']}", "AMK_NO_PATH=1", "PATH=/nonexistent",
     "/bin/sh", "-c", '"$0" -s entry', str(bundle)],
    capture_output=True, text=True, cwd=tmp_path, timeout=300,
  )
  assert r.returncode == 0, r.stderr
  assert entry_line in r.stdout


def test_a_bundle_serves_a_zygote(bundle, tmp_path, sock):
  """The resident roles work on the entry, since no makefile is on disk to name."""
  z = popen(bundle, ["--serve", str(sock)], cwd=tmp_path, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
  try:
    deadline = time.time() + 60
    while time.time() < deadline and not sock.is_socket():
      time.sleep(0.05)
    assert sock.is_socket(), "zygote never bound"
    r = sh(bundle, ["--client", str(sock), "served"], cwd=tmp_path, timeout=120)
    assert r.returncode == 0, r.stderr
    assert "served by pid" in r.stdout, r.stdout
  finally:
    z.kill()
    z.wait(timeout=30)


def test_a_bundle_bundles_again(bundle, tmp_path):
  """The verb is on every copy, and the payload it writes carries the same base."""
  again = tmp_path / "c.amk"
  r = sh(bundle, ["--bundle", "lib/greet.mk", "--out", str(again)], cwd=BUNDLE_SRC)
  assert r.returncode == 0, r.stderr
  assert packed(again, "__main__.mk").strip() == "greeting := hello"
  assert packed(again, "lib/gmsl") == packed(bundle, "lib/gmsl")

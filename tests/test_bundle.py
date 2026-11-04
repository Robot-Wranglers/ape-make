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

import pytest

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
  assert packed(bundle, "lib/gmsl/gmsl") == packed(amk, "lib/gmsl/gmsl")
  assert packed(bundle, "lib/lua/dkjson.lua") == packed(amk, "lib/lua/dkjson.lua")
  assert packed(bundle, "lib/greet.mk") == (BUNDLE_SRC / "lib" / "greet.mk").read_text()
  assert packed(bundle, "__main__.mk") == (BUNDLE_SRC / "main.mk").read_text()


def test_a_bundle_runs_with_nothing_on_the_path(bundle, tmp_path):
  """The distribution case: only the binary, so its recipes run on the payload's own bash and tools."""
  cache = tmp_path / "cache"
  probe = 'probe: ; echo "shell=$${BASH_VERSION:+bash} sed=$$(command -v sed)"'
  # HOME stays real, since the ape loader a portable binary needs on macOS was unpacked there once with host tools.
  r = subprocess.run(
    ["env", "-i", f"HOME={os.environ['HOME']}", f"XDG_CACHE_HOME={cache}", "PATH=/nonexistent",
     "/bin/sh", "-c", '"$0" -s --eval "$1" entry probe', str(bundle), probe],
    capture_output=True, text=True, cwd=tmp_path, timeout=300,
  )
  assert r.returncode == 0, r.stderr
  assert entry_line in r.stdout
  assert f"shell=bash sed={cache}/amk/" in r.stdout, r.stdout


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
  assert packed(again, "lib/gmsl/gmsl") == packed(bundle, "lib/gmsl/gmsl")


def members(binary):
  r = sh(binary, ["--ape-list"], timeout=60)
  assert r.returncode == 0, r.stderr
  return r.stdout.split()


def test_ls_prints_each_member_under_zip(amk):
  r = sh(amk, ["--bundle-ls"], timeout=60)
  assert r.returncode == 0, r.stderr
  assert r.stdout.split() == ["/zip/" + m for m in members(amk)]


def test_cp_lands_files_and_leaves_the_entry(bundle, tmp_path):
  (tmp_path / "state").mkdir()
  (tmp_path / "state" / "count").write_text("7\n")
  (tmp_path / "note.txt").write_text("a note\n")
  out = tmp_path / "c.amk"
  r = sh(bundle, ["--bundle-cp", "state/", "/zip/state/", "--out", str(out)], cwd=tmp_path)
  assert r.returncode == 0 and r.stdout.strip() == str(out), r.stdout + r.stderr
  assert set(members(out)) - set(members(bundle)) == {"state/count"}
  assert packed(out, "state/count") == "7\n"
  assert packed(out, "__main__.mk") == packed(bundle, "__main__.mk")
  for dest, name in [("/zip/doc/readme", "doc/readme"), ("/zip/doc/", "doc/note.txt"), ("/zip", "note.txt")]:
    r = sh(bundle, ["--bundle-cp", "note.txt", dest, "--out", str(out)], cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert packed(out, name) == "a note\n", dest
  r = sh(bundle, ["--bundle-cp", "note.txt", "state", "/zip/kept/", "--out", str(out)], cwd=tmp_path)
  assert r.returncode == 0, r.stderr
  assert {"kept/note.txt", "kept/state/count"} <= set(members(out))


def test_cp_copies_members_out(bundle, tmp_path):
  r = sh(bundle, ["--bundle-cp", "/zip/lib/greet.mk", "greet.copy"], cwd=tmp_path)
  assert r.returncode == 0 and r.stdout == "", r.stdout + r.stderr
  assert (tmp_path / "greet.copy").read_text() == packed(bundle, "lib/greet.mk")
  r = sh(bundle, ["--bundle-cp", "/zip/lib/gmsl", "out"], cwd=tmp_path)
  assert r.returncode == 0, r.stderr
  assert (tmp_path / "out" / "gmsl").read_text() == packed(bundle, "lib/gmsl/gmsl")


def test_a_write_replaces_in_place_and_keeps_its_size(bundle, tmp_path):
  tool = tmp_path / "tool.amk"
  tool.write_bytes(bundle.read_bytes())
  tool.chmod(0o755)
  sizes = []
  for n in range(3):
    (tmp_path / "count").write_text(f"{n}\n")
    r = sh(tool, ["--bundle-cp", "count", "/zip/state/count", "--in-place"], cwd=tmp_path)
    assert r.returncode == 0 and r.stdout.strip() == str(tool), r.stdout + r.stderr
    assert packed(tool, "state/count") == f"{n}\n"
    sizes.append(tool.stat().st_size)
  assert sizes[0] == sizes[1] == sizes[2], sizes
  r = sh(tool, ["--bundle-rm", "/zip/state", "--in-place"])
  assert r.returncode == 0, r.stderr
  assert tool.stat().st_size == bundle.stat().st_size
  assert members(tool) == members(bundle)


def test_writers_in_place_at_once_all_land(bundle, tmp_path):
  tool = tmp_path / "tool.amk"
  tool.write_bytes(bundle.read_bytes())
  tool.chmod(0o755)
  names = [f"f{n}" for n in range(8)]
  for name in names:
    (tmp_path / name).write_text(name + "\n")
  writers = [popen(tool, ["--bundle-cp", name, f"/zip/state/{name}", "--in-place"], cwd=tmp_path,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE) for name in names]
  for w in writers:
    err = w.communicate(timeout=120)[1]
    assert w.returncode == 0, err
  assert {f"state/{name}" for name in names} <= set(members(tool))
  assert not [p.name for p in tmp_path.iterdir() if ".tmp." in p.name]


def test_a_write_in_place_respects_the_binarys_permissions(bundle, tmp_path):
  if os.geteuid() == 0:
    pytest.skip("root writes anywhere")
  (tmp_path / "f").write_text("x\n")
  home = tmp_path / "bin"
  home.mkdir()
  tool = home / "tool.amk"
  tool.write_bytes(bundle.read_bytes())
  args = ["--bundle-cp", str(tmp_path / "f"), "/zip/f", "--in-place"]
  tool.chmod(0o700)
  r = sh(tool, args)
  assert r.returncode == 0, r.stderr
  assert tool.stat().st_mode & 0o777 == 0o700, "the mode is kept"
  tool.chmod(0o555)
  before = tool.read_bytes()
  r = sh(tool, args)
  assert r.returncode == 2 and f"cannot rewrite {tool} in place" in r.stderr, r.stderr
  tool.chmod(0o755)
  home.chmod(0o555)
  try:
    r = sh(tool, args)
  finally:
    home.chmod(0o755)
  assert r.returncode == 2 and f"cannot write {tool}: its directory takes no new file" in r.stderr, r.stderr
  assert tool.read_bytes() == before and [p.name for p in home.iterdir()] == ["tool.amk"]


def test_a_write_names_one_destination(bundle, tmp_path):
  (tmp_path / "f").write_text("x\n")
  out = tmp_path / "o.amk"
  for args in (["--bundle-cp", "f", "/zip/f"], ["--bundle-rm", "lib/greet.mk"], ["--bundle-strip"],
               ["--bundle-cp", "f", "/zip/f", "--out", str(out), "--in-place"]):
    r = sh(bundle, args, cwd=tmp_path)
    assert r.returncode == 2 and "names one of --out DEST and --in-place" in r.stderr, r.stderr
  r = sh(bundle, ["--bundle-cp", "/zip/lib/greet.mk", "g", "--out", str(out)], cwd=tmp_path)
  assert r.returncode == 2 and "takes neither --out nor --in-place" in r.stderr, r.stderr
  r = sh(bundle, ["--bundle-cp", "f", "g"], cwd=tmp_path)
  assert r.returncode == 2 and "under /zip" in r.stderr, r.stderr
  r = sh(bundle, ["--bundle-cp", "f", "/zip/usr/f", "--out", str(out)], cwd=tmp_path)
  assert r.returncode == 2 and "belongs to the program itself" in r.stderr, r.stderr
  assert not out.exists()


def test_rm_removes_a_file(bundle, tmp_path):
  out = tmp_path / "u.amk"
  r = sh(bundle, ["--bundle-rm", "/zip/__main__.mk", "--out", str(out)])
  assert r.returncode == 0, r.stderr
  assert r.stdout.strip() == str(out)
  assert set(members(bundle)) - set(members(out)) == {"__main__.mk"}
  assert packed(out, "lib/greet.mk") == packed(bundle, "lib/greet.mk")
  (tmp_path / "Makefile").write_text("here:\n\t@echo from-disk\n")
  r = sh(out, ["-s"], cwd=tmp_path)
  assert r.returncode == 0, r.stderr
  assert r.stdout.strip() == "from-disk"


def test_rm_removes_a_directory(amk, tmp_path):
  out = tmp_path / "u.amk"
  r = sh(amk, ["--bundle-rm", "lib/", "bin/sed", "--out", str(out)])
  assert r.returncode == 0, r.stderr
  left = members(out)
  assert not [m for m in left if m.startswith("lib/") or m == "bin/sed"], left
  assert "bin/bash" in left and "__init__.mk" in left, left
  assert packed(out, "__init__.mk") == packed(amk, "__init__.mk")
  assert out.stat().st_size < amk.stat().st_size
  r = sh(out, ["--version"])
  assert r.returncode == 0 and "GNU Make" in r.stdout, r.stdout + r.stderr


def test_rm_refuses_a_name_it_cannot_take(amk, tmp_path):
  out = tmp_path / "u.amk"
  r = sh(amk, ["--bundle-rm", "lib/nope", "--out", str(out)])
  assert r.returncode == 2 and "no payload member" in r.stderr, r.stderr
  r = sh(amk, ["--bundle-rm", "usr", "--out", str(out)])
  assert r.returncode == 2 and "belongs to the program itself" in r.stderr, r.stderr
  r = sh(amk, ["--unbundle", "lib", "--out", str(out)])
  assert r.returncode != 0, "the old spelling is gone"
  assert not out.exists()


def test_bundle_strip_keeps_the_tools_and_the_programs_own_members(amk, tmp_path):
  out = tmp_path / "bare.amk"
  r = sh(amk, ["--bundle-strip", "--out", str(out)])
  assert r.returncode == 0, r.stderr
  left = members(out)
  assert left and all(m.startswith((".", "usr/", "bin/")) for m in left), left
  assert [m for m in left if m.startswith("bin/")] == [m for m in members(amk) if m.startswith("bin/")]
  assert packed(out, "bin/amk.sh") == packed(amk, "bin/amk.sh")
  assert out.stat().st_size < amk.stat().st_size
  mk = tmp_path / "tools.mk"
  mk.write_text("SHELL := bash\nall:\n\t@source /zip/bin/amk.sh && type sed\n")
  r = sh(out, ["-f", str(mk)])
  assert r.returncode == 0, r.stdout + r.stderr
  assert "/bin/sed" in r.stdout and "/usr/bin/sed" not in r.stdout, r.stdout


def test_a_stripped_binary_bundles_again(amk, tmp_path):
  bare, again = tmp_path / "bare.amk", tmp_path / "again.amk"
  assert sh(amk, ["--bundle-strip", "--out", str(bare)]).returncode == 0
  r = sh(bare, ["--bundle", "lib/greet.mk", "--out", str(again)], cwd=BUNDLE_SRC)
  assert r.returncode == 0, r.stderr
  assert packed(again, "__main__.mk").strip() == "greeting := hello"

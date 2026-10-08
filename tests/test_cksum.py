"""Pins the cksum builtins against the host's cksum utility.

`$(cksum text)` and `$(cksum.file path)` answer the checksum and length joined by a dash,
`$(cksum.hex text)` and `$(cksum.file.hex path)` seven hex digits of the checksum modulo
2^28; the star form reads a variable's dedented value. Every value is compared with what
the host's cksum prints over the same bytes, so the builtin can stand in for the pipe
`cksum | awk` without moving a cache key.
"""

import shutil
import subprocess

import pytest

from conftest import sh

CASES = {
  "empty": "",
  "byte": "a",
  "lines": "one\ntwo\nthree\n",
  "punct": "cost: $x, a, b",
}


def host_cksum(data):
  r = subprocess.run(["cksum"], input=data.encode(), capture_output=True, check=True)
  crc, size = r.stdout.split()[:2]
  return int(crc), int(size)


def dashed(data):
  crc, size = host_cksum(data)
  return f"{crc}-{size}"


def hexed(data):
  crc, _ = host_cksum(data)
  return f"{crc % 268435456:07x}"


def run(amk, tmp_path, text):
  mk = tmp_path / "cksum.mk"
  mk.write_text(text + "\nall:\n\ttrue\n")
  return sh(amk, ["-s", "-f", str(mk)], timeout=120)


needs_host = pytest.mark.skipif(shutil.which("cksum") is None, reason="no cksum on the host")


def test_cksum_is_a_feature(amk, tmp_path):
  r = run(amk, tmp_path, "$(info [$(filter cksum,$(.FEATURES))])")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[cksum]" in r.stdout, r.stdout


@needs_host
@pytest.mark.parametrize("case", CASES.keys())
def test_text_matches_the_host(amk, tmp_path, case):
  data = CASES[case]
  lines = ["define body"] + data.split("\n") + ["endef"]
  text = "\n".join(lines) + "\n$(info dash=[$(cksum $(value body))])\n$(info hex=[$(cksum.hex $(value body))])"
  r = run(amk, tmp_path, text)
  assert r.returncode == 0, r.stdout + r.stderr
  # a define's value drops the newline before endef, so the host hashes the same bytes
  assert f"dash=[{dashed(data)}]" in r.stdout, r.stdout
  assert f"hex=[{hexed(data)}]" in r.stdout, r.stdout


@needs_host
def test_file_matches_the_host(amk, tmp_path):
  big = tmp_path / "big.bin"
  big.write_bytes(bytes(range(256)) * 1024)
  empty = tmp_path / "empty"
  empty.write_bytes(b"")
  text = "\n".join([
    f"$(info big=[$(cksum.file {big})])",
    f"$(info bighex=[$(cksum.file.hex {big})])",
    f"$(info empty=[$(cksum.file {empty})])",
  ])
  r = run(amk, tmp_path, text)
  assert r.returncode == 0, r.stdout + r.stderr
  for path, tag, fmt in ((big, "big", "dash"), (big, "bighex", "hex"), (empty, "empty", "dash")):
    out = subprocess.run(["cksum"], stdin=open(path, "rb"), capture_output=True, check=True).stdout.split()
    crc, size = int(out[0]), int(out[1])
    want = f"{crc}-{size}" if fmt == "dash" else f"{crc % 268435456:07x}"
    assert f"{tag}=[{want}]" in r.stdout, r.stdout


def test_a_missing_file_is_empty_with_a_warning(amk, tmp_path):
  r = run(amk, tmp_path, f"$(info [$(cksum.file {tmp_path}/absent)])")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[]" in r.stdout, r.stdout
  assert "cksum.file" in r.stderr and "absent" in r.stderr, r.stderr


@needs_host
def test_star_reads_a_variable(amk, tmp_path):
  text = "define body\n    one\n    two\nendef\n$(info star=[$(cksum* body)])\n$(info hexstar=[$(cksum.hex* body)])"
  r = run(amk, tmp_path, text)
  assert r.returncode == 0, r.stdout + r.stderr
  assert f"star=[{dashed('one' + chr(10) + 'two')}]" in r.stdout, r.stdout
  assert f"hexstar=[{hexed('one' + chr(10) + 'two')}]" in r.stdout, r.stdout

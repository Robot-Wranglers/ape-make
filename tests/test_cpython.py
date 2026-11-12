"""Pins what the cpython engine adds over the shared state contract.

The standard library loads from the payload, including what micropython lacks; a one-shot
call runs in fresh globals beside the kept state; import lifts a dict, a list and a bool
the way every Python guest does; sys.exit settles to the command line's status; and a function that raises
fails the make call with the Python error.
"""

import pytest

from conformance import run
from conftest import sh

pytestmark = pytest.mark.engines("cpython")


def _define(name, body):
  return [f"define {name}"] + ["  " + line for line in body.splitlines()] + ["endef"]


def test_the_standard_library_loads_from_the_payload(amk, tmp_path):
  r = run(amk, tmp_path, [
    "$(info median=$(cpython import statistics; print(statistics.median([3, 7, 5]))))",
    "$(info frac=$(cpython from fractions import Fraction; print(Fraction(1, 3) + Fraction(1, 6))))",
  ])
  assert r.returncode == 0, r.stdout + r.stderr
  assert "median=5" in r.stdout, r.stdout + r.stderr
  assert "frac=1/2" in r.stdout, r.stdout + r.stderr


def test_zlib_compresses_and_the_modules_over_it_load(amk, tmp_path):
  prog = "\n".join([
    "import binascii, gzip, io, zipfile, zlib",
    "data = b'amk ' * 1000",
    "packed = zlib.compress(data)",
    "print('zlib', zlib.decompress(packed) == data, len(packed) < len(data))",
    "print('crc', zlib.crc32(data) == binascii.crc32(data))",
    "print('gzip', gzip.decompress(gzip.compress(data)) == data)",
    "buf = io.BytesIO()",
    "with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:",
    "  z.writestr('a.txt', data)",
    "print('zip', zipfile.ZipFile(buf).read('a.txt') == data, buf.tell() < len(data))",
  ])
  script = tmp_path / "z.py"
  script.write_text(prog + "\n")
  r = sh(amk, ["--cpython", str(script)], timeout=60)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.split("\n")[:4] == ["zlib True True", "crc True", "gzip True", "zip True True"], r.stdout + r.stderr


def test_ssl_loads_over_the_linked_openssl(amk, tmp_path):
  if sh(amk, ["--cpython", "import _ssl"], timeout=60).returncode != 0:
    pytest.skip("this build leaves openssl out")
  prog = "\n".join([
    "import hashlib, ssl",
    "print('version', ssl.OPENSSL_VERSION.split()[0], ssl.OPENSSL_VERSION_INFO[0])",
    "ctx = ssl.create_default_context()",
    "print('verify', ctx.verify_mode == ssl.CERT_REQUIRED, ctx.check_hostname)",
    "print('tls13', ssl.HAS_TLSv1_3)",
    "print('random', len(ssl.RAND_bytes(16)))",
    "print('pbkdf2', hashlib.pbkdf2_hmac('sha256', b'pw', b'salt', 1000).hex()[:16])",
    "print('paths', ssl.get_default_verify_paths().openssl_cafile)",
    "print('trusted', len(ctx.get_ca_certs()) > 100)",
  ])
  script = tmp_path / "s.py"
  script.write_text(prog + "\n")
  r = sh(amk, ["--cpython", str(script)], timeout=60)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.split("\n")[:7] == [
    "version OpenSSL 3", "verify True True", "tls13 True", "random 16",
    "pbkdf2 0a38253555ce37f5", "paths /zip/usr/share/ssl/cert.pem", "trusted True",
  ], r.stdout + r.stderr


def test_re_has_named_groups(amk, tmp_path):
  r = run(amk, tmp_path, _define("py.re", "import re\nprint(re.match(r'(?P<k>\\w+)=(?P<v>\\d+)', 'n=42')['v'])") + [
    "$(info v=$(cpython.exec* py.re))",
  ])
  assert r.returncode == 0, r.stdout + r.stderr
  assert "v=42" in r.stdout, r.stdout + r.stderr


def test_a_one_shot_call_does_not_see_the_kept_state(amk, tmp_path):
  r = run(amk, tmp_path, [
    "x := $(cpython.exec x = 41)",
    "$(info kept=$(cpython.exec print(x + 1)) fresh=$(cpython print('x' in globals())))",
  ])
  assert r.returncode == 0, r.stdout + r.stderr
  assert "kept=42 fresh=False" in r.stdout, r.stdout + r.stderr


def test_import_lifts_a_dict_a_list_and_a_bool(amk, tmp_path):
  r = run(amk, tmp_path, ["@cpython.import"] + _define("py.lib", "cfg = {'host': 'h', 'port': 80}\nxs = [1, 'two', 3]\non = True\noff = False") + [
    "$(info host=$(cfg.host) port=$(cfg.port) xs=$(xs) on=$(on) off=[$(off)])",
  ])
  assert r.returncode == 0, r.stdout + r.stderr
  assert "host=h port=80 xs=1 two 3 on=true off=[]" in r.stdout, r.stdout + r.stderr


def test_sys_exit_settles_to_its_status(amk):
  r = sh(amk, ["--cpython", "import sys; sys.exit(3)"], timeout=60)
  assert r.returncode == 3, r.stdout + r.stderr
  r = sh(amk, ["--cpython", "import sys; sys.exit('bye')"], timeout=60)
  assert r.returncode == 1, r.stdout + r.stderr
  assert "bye" in r.stderr, r.stderr


def test_a_function_that_raises_fails_the_call(amk, tmp_path):
  r = run(amk, tmp_path, ["@cpython.import"] + _define("py.lib", "def boom(s):\n  raise KeyError(s)") + [
    "$(info $(boom nope))",
  ])
  assert r.returncode != 0, r.stdout + r.stderr
  assert "KeyError" in r.stderr, r.stderr

"""Pins the payload's mip library: a package pinned in mip.manifest is fetched once, checked, and importable.

Pinned: the mip.install target publishes the package under its version with a stamp, micropy
imports it with no path setup of its own, a second run fetches nothing, and a wrong digest stops the build with the right one
named and nothing published. These reach GitHub. demos/json-rpc.mk uses mip; this file does not read it.
"""

import pytest

from conftest import sh

pytestmark = [pytest.mark.integration, pytest.mark.network, pytest.mark.engines("micropy", "jq")]

microdot_sha256 = "7abf80436064aff030fb123c2947260674c84001517322d7c8517b7f2425e01a"


def makefile(cache, digest):
  return "\n".join([
    f"mip.cache := {cache}",
    "include /zip/lib/mip.mk",
    "define mip.manifest",
    '  {"microdot": {"version": "v2.7.0",',
    '    "spec": "github:miguelgrinberg/microdot/src/microdot/microdot.py",',
    f'    "sha256": "{digest}"}}}}',
    "endef",
    "probe: mip.install",
    """\techo '$(micropy import microdot; print(microdot.Microdot.__name__))'""",
    "",
  ])


def build(amk, tmp_path, digest=microdot_sha256):
  (tmp_path / "mip.mk").write_text(makefile(tmp_path / "cache", digest))
  return sh(amk, ["-s", "-f", "mip.mk", "probe"], cwd=tmp_path, timeout=300)


def test_a_pinned_package_is_fetched_once_and_imports(amk, tmp_path):
  r = build(amk, tmp_path)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "Downloading github:miguelgrinberg/microdot" in r.stdout, r.stdout
  assert r.stdout.splitlines()[-1] == "Microdot", r.stdout
  assert (tmp_path / "cache" / "microdot" / "v2.7.0" / ".ok").is_file()
  r = build(amk, tmp_path)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "Microdot", r.stdout


def test_a_wrong_digest_stops_the_build_and_publishes_nothing(amk, tmp_path):
  r = build(amk, tmp_path, digest="0" * 64)
  assert r.returncode != 0, r.stdout
  assert f"mip: microdot digests to {microdot_sha256}" in r.stderr, r.stderr
  assert not (tmp_path / "cache" / "microdot" / "v2.7.0").exists()

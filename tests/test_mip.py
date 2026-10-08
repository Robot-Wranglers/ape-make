"""Pins the payload's mip library: a package named in a define under @mip.install is fetched once, checked, and importable.

Pinned: the define's name is a target that publishes the package under its version with a
stamp, micropy imports it with no path setup of its own, a second run fetches nothing, a wrong
digest stops the build with the right one named and nothing published, a package with no pin
installs with its digest named on stderr and kept in the stamp, and two manifests share the
cache. These reach GitHub, except the schema refusals, which stop before any fetch. demos/json-rpc.amk uses mip; this file does not read it.
"""

import pytest

from conftest import sh

pytestmark = [pytest.mark.integration, pytest.mark.network, pytest.mark.engines("micropy", "jq")]

microdot_sha256 = "7abf80436064aff030fb123c2947260674c84001517322d7c8517b7f2425e01a"


def manifest(name, digest):
  pin = f', "sha256": "{digest}"' if digest else ""
  return [
    "@mip.install", f"define {name}",
    '  {"microdot": {"version": "v2.7.0",',
    f'    "spec": "github:miguelgrinberg/microdot/src/microdot/microdot.py"{pin}}}}}',
    "endef",
  ]


def makefile(cache, digest, names=("deps",)):
  return "\n".join([
    f"mip.cache := {cache}",
    "$(amk.include mip)",
    *[line for n in names for line in manifest(n, digest)],
    "probe: " + " ".join(names),
    """\techo '$(micropy import microdot; print(microdot.Microdot.__name__))'""",
    "",
  ])


def build(amk, tmp_path, digest=microdot_sha256, names=("deps",)):
  (tmp_path / "mip.mk").write_text(makefile(tmp_path / "cache", digest, names))
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


@pytest.mark.engines("micropy", "jq", "sqlite")
@pytest.mark.parametrize("body,want", [
  ('{"microdot": {"spec": "github:x/y"}}', "Additional property microdot: Missing required: version"),
  ('{"microdot": {"version": "v1"}}', "Additional property microdot: Missing required: spec"),
  ('{"microdot": {"spec": "x", "version": "v1", "sha256": "abc"}}',
   "Additional property microdot: Property sha256: Does not match pattern ^[0-9a-f]{64}$"),
  ('{"microdot": {"spec": "x", "version": "v1/../.."}}',
   "Additional property microdot: Property version: Does not match pattern"),
  ('{"micro dot": {"spec": "x", "version": "v1"}}', "Property name 'micro dot': Does not match pattern"),
  ('{"microdot": {"spec": "x", "version": "v1", "pin": "y"}}',
   "Additional property microdot: Additional property 'pin' not allowed"),
  ("{}", "Less than minProperties 1"),
])
def test_a_manifest_is_checked_against_its_schema_before_anything_is_fetched(amk, tmp_path, body, want):
  (tmp_path / "mip.mk").write_text("\n".join([
    f"mip.cache := {tmp_path / 'cache'}", "$(amk.include mip)",
    "@mip.install", "define deps", body, "endef", "",
  ]))
  r = sh(amk, ["-s", "-f", "mip.mk", "deps"], cwd=tmp_path, timeout=60)
  assert r.returncode != 0, r.stdout + r.stderr
  assert "deps: does not meet schema/mip.json: " + want in r.stderr, r.stderr
  assert not (tmp_path / "cache").exists()


def test_a_wrong_digest_stops_the_build_and_publishes_nothing(amk, tmp_path):
  r = build(amk, tmp_path, digest="0" * 64)
  assert r.returncode != 0, r.stdout
  assert f"mip: microdot digests to {microdot_sha256}" in r.stderr, r.stderr
  assert not (tmp_path / "cache" / "microdot" / "v2.7.0").exists()


def test_a_package_with_no_pin_installs_and_names_its_digest(amk, tmp_path):
  r = build(amk, tmp_path, digest="")
  assert r.returncode == 0, r.stdout + r.stderr
  assert f"mip: microdot digests to {microdot_sha256}; pin it" in r.stderr, r.stderr
  assert r.stdout.splitlines()[-1] == "Microdot", r.stdout
  assert (tmp_path / "cache" / "microdot" / "v2.7.0" / ".ok").read_text() == microdot_sha256
  r = build(amk, tmp_path, digest="")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "digests to" not in r.stderr, r.stderr


def test_two_manifests_share_the_cache(amk, tmp_path):
  r = build(amk, tmp_path, names=("deps", "more"))
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.count("Downloading github:miguelgrinberg/microdot") == 1, r.stdout
  assert r.stdout.splitlines()[-1] == "Microdot", r.stdout

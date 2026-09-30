"""Pins `<name>.__version__`: every engine in the build has one, set before any makefile is read."""

import re

from conftest import sh


def test_every_engine_names_its_version(amk, engines, tmp_path):
  mk = tmp_path / "versions.mk"
  mk.write_text("show:\n" + "".join(f"\t@echo {e}=$({e}.__version__)\n" for e in engines))
  r = sh(amk, ["-s", "--warn-undefined-variables", "-f", str(mk), "show"], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stderr == "", r.stderr
  got = dict(line.split("=", 1) for line in r.stdout.split())
  assert sorted(got) == sorted(engines), got
  for name, version in got.items():
    assert re.fullmatch(r"\d[\d.-]*\d", version), f"{name}: {version!r}"

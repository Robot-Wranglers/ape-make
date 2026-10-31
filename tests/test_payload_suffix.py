"""Pins the payload's suffix contract: a `.mk` file is make alone, and amk's syntax lives in `.amk`.

Each `.mk` under payload/ is read by stock GNU make with a no-op goal, so a decorator line,
a `load` of an engine, or any other amk form fails the parse. An `amk.require` or other amk
call still parses, since stock make expands an unknown name to nothing."""

import re
import shutil
import subprocess

import pytest
from conftest import AMK_DIR

PAYLOAD = AMK_DIR / "payload"
MK_FILES = sorted(PAYLOAD.rglob("*.mk"))


def _stock_make():
  for name in ("gmake", "make"):
    path = shutil.which(name)
    if not path:
      continue
    version = subprocess.run([path, "--version"], capture_output=True, text=True).stdout
    if re.match(r"GNU Make 4\.", version):
      return path
  return None


STOCK_MAKE = _stock_make()


def test_payload_has_mk_files():
  assert MK_FILES, f"no .mk files under {PAYLOAD}"


@pytest.mark.skipif(STOCK_MAKE is None, reason="needs stock GNU make 4.x as gmake or make")
@pytest.mark.parametrize("mk", MK_FILES, ids=lambda p: str(p.relative_to(PAYLOAD)))
def test_mk_parses_under_stock_make(mk, tmp_path):
  r = subprocess.run(
    [STOCK_MAKE, "-s", "-f", str(mk), "--eval=__probe:;@:", "__probe"],
    cwd=tmp_path, capture_output=True, text=True, timeout=60,
  )
  assert r.returncode == 0, f"{mk.name} needs amk, rename it .amk:\n{r.stderr}"

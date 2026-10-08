"""Pins `$(amk.kwarg key, arg)`: the value of an argument written key=value.

The argument splits at its first `=`, both sides trimmed, and the value is the rest, so
a value may hold `=` or commas. A different key, or an argument with no `=`, gives nothing.
Pinned are a match, a mismatch, a bare word, an empty value, a value with `=` and commas,
and the form inside a call, reading one of its own arguments.
"""

import pytest

from conftest import sh


def run(amk, tmp_path, text):
  mk = tmp_path / "kwarg.mk"
  mk.write_text(text + "\nall:\n\ttrue\n")
  return sh(amk, ["-s", "-f", str(mk)], timeout=120)


@pytest.mark.parametrize("key, arg, want", [
  ("owned", "owned=jobs.sql", "jobs.sql"),
  ("owned", " owned = jobs.sql ", "jobs.sql"),
  ("shared", "owned=jobs.sql", ""),
  ("run", "run", ""),
  ("owned", "owned=", ""),
  ("q", "q=a=b,c", "a=b,c"),
])
def test_the_value_of_a_matching_key(amk, tmp_path, key, arg, want):
  r = run(amk, tmp_path, f"$(info got=[$(amk.kwarg {key},{arg})])")
  assert r.returncode == 0, r.stdout + r.stderr
  assert f"got=[{want}]" in r.stdout, r.stdout


def test_a_call_reads_its_own_argument(amk, tmp_path):
  r = run(amk, tmp_path, "f = $(or $(amk.kwarg owned, $(2)),none)\n$(info a=$(call f,x,owned=o.sql))\n$(info b=$(call f,x,run))")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "a=o.sql\nb=none" in r.stdout, r.stdout

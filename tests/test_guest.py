"""Pins the guest input path.

`$(awk program,input)` and the other builtins with input feed it to the guest's stdin
through a pipe the parent drives beside the guest's stdout. Pinned: an input past any
pipe buffer round-trips whole, a guest that exits without reading its input leaves make
standing, and the call leaves no file in the temp directory.
"""

import os

import pytest

from conftest import sh

# A parse-time input of 300 KiB, past the 64 KiB and 16 KiB pipe buffers, then one call over it.
makefile = "\n".join([
  "big := $(shell head -c 300000 /dev/zero | tr '\\0' x)",
  "$(info [$(strip $(awk { n += length($$0) } END { print n },$(big)))])",
  "$(info [$(strip $(awk BEGIN { print \"early\" ; exit },$(big)))])",
  "all:",
  "\ttrue",
  "",
])


@pytest.mark.engines("awk")
def test_input_past_the_pipe_buffer_round_trips_and_an_early_exit_is_survived(amk, tmp_path):
  mk = tmp_path / "guest.mk"
  mk.write_text(makefile)
  tmp = tmp_path / "tmp"
  tmp.mkdir()
  r = sh(amk, ["-s", "-f", str(mk)], env={"TMPDIR": str(tmp)}, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[300000]" in r.stdout, r.stdout + r.stderr
  assert "[early]" in r.stdout, r.stdout + r.stderr
  left = [name for name in os.listdir(tmp) if not name.startswith(".ape-")]
  assert left == [], f"a call left a file behind: {left}"

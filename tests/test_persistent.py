"""Pins the persistent builtins.

`$(lua.persistent program[,input])` runs in the make process against one Lua state kept
for its life, where `$(lua ...)` forks a fresh one per call. Pinned: state carries across
calls, input arrives as `amk.input`, an error leaves the state as it was, output is trimmed
like every builtin's even mid-expansion, print and io.write reach an unclosable result that
holds a megabyte whole, and a zygote's requests each start from what the parse left.
"""

import pytest

from conftest import sh

parse_time = "\n".join([
  "seed := $(lua.persistent n = 41)",
  "kept := $(lua.persistent print(n + 1))",
  "fresh := $(lua print(n))",
  "upper := $(lua.persistent print(amk.input:upper()),abc)",
  'none := $(lua.persistent print(amk.input == ""))',
  'oops := $(lua.persistent error("boom"))',
  "after := $(lua.persistent print(n))",
  'multi := $(lua.persistent print("a") print("b"))',
  'wrote := $(lua.persistent io.write("w") io.stdout:write("x") print("y"))',
  'closed := $(lua.persistent print((io.close(io.stdout))))',
  'big := $(lua.persistent io.write(string.rep("x", 1048576)))',
  'biglen := $(lua.persistent print(string.len(amk.input)),$(big))',
  'mixed := pre$(lua.persistent io.write("a\\n"))mid$(lua.persistent print())post',
  "$(info kept=[$(kept)] fresh=[$(fresh)] upper=[$(upper)] none=[$(none)] oops=[$(oops)] after=[$(after)] multi=[$(multi)] wrote=[$(wrote)] closed=[$(closed)] biglen=[$(biglen)] mixed=[$(mixed)])",
  "all:",
  "\ttrue",
  "",
])

served = "\n".join([
  "seed := $(lua.persistent n = 7)",
  "show:",
  "\t@echo n=$(lua.persistent n = n + 1; print(n))",
  "",
])


@pytest.mark.engines("lua")
def test_state_outlives_a_call(amk, tmp_path):
  mk = tmp_path / "persist.mk"
  mk.write_text(parse_time)
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "kept=[42]" in r.stdout, r.stdout
  assert "fresh=[nil]" in r.stdout, r.stdout
  assert "upper=[%s]" % "abc".upper() in r.stdout, r.stdout
  assert "none=[true]" in r.stdout, r.stdout
  assert "oops=[]" in r.stdout and "boom" in r.stderr, r.stdout + r.stderr
  assert "after=[41]" in r.stdout, r.stdout
  assert "multi=[a\nb]" in r.stdout, r.stdout
  assert "wrote=[wxy]" in r.stdout, r.stdout
  assert "closed=[nil]" in r.stdout, r.stdout
  assert "biglen=[1048576]" in r.stdout, r.stdout[-400:]
  assert "mixed=[preamidpost]" in r.stdout, r.stdout[-400:]


@pytest.mark.engines("lua")
def test_each_request_starts_from_the_parse(amk, tmp_path, zygote):
  mk = tmp_path / "served.mk"
  mk.write_text(served)
  sock = zygote(["-f", str(mk)], cwd=tmp_path)
  for _ in range(2):
    r = sh(amk, ["--client", str(sock), "show"], cwd=tmp_path, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.strip() == "n=8", r.stdout + r.stderr

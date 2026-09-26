"""Pins amk.acall: the deferred call, a fork that runs the call and a handle to collect it.

Pinned in every engine with a handle: the collected text is what the blocking call
answers, an unknown name raises the same error, a write the called function makes
through the handle lands when the call is collected, and two calls in flight overlap.
micropy awaits the handle through asyncio and js through a promise; lua and s7 collect
on the handle.
"""

import time

import pytest

from conftest import sh

engines = ["lua", "s7", "micropy", "js"]

# The persistent chunk per engine that begins the call, collects it, and prints the text.
collect = {
  "lua": [
    'local h = amk.acall("{name}", "x", "y")',
    "print(h.result())",
  ],
  "s7": [
    '(let ((h (amk-call-begin "{name}" "x" "y")))',
    "  (display (amk-call-end (car h))))",
  ],
  "micropy": [
    "import amk, asyncio",
    "async def main():",
    '  print(await amk.acall("{name}", "x", "y"))',
    "asyncio.run(main())",
  ],
  "js": [
    'print(await amk.acall("{name}", "x", "y"));',
  ],
}

# The same, with the error caught and printed.
catch = {
  "lua": [
    'local h = amk.acall("{name}", "x", "y")',
    "local ok, e = pcall(h.result)",
    "print(e)",
  ],
  "s7": [
    '(let ((h (amk-call-begin "{name}" "x" "y")))',
    "  (catch #t (lambda () (amk-call-end (car h))) (lambda (type info) (display info))))",
  ],
  "micropy": [
    "import amk, asyncio",
    "async def main():",
    "  try:",
    '    await amk.acall("{name}", "x", "y")',
    "  except Exception as e:",
    "    print(e)",
    "asyncio.run(main())",
  ],
  "js": [
    'try {{ await amk.acall("{name}", "x", "y"); }} catch (e) {{ print(e.message); }}',
  ],
}


def run(amk, tmp_path, engine, chunks, name):
  mk = tmp_path / "acall.mk"
  mk.write_text("\n".join([
    "pair = [$1|$2]",
    "define prog",
    *("  " + line.format(name=name) for line in chunks[engine]),
    "endef",
    f"$(info [$({engine}.exec* prog)])",
    "all:",
    "\ttrue",
    "",
  ]))
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  return r.stdout + r.stderr


every_engine = [pytest.param(e, marks=pytest.mark.engines(e), id=e) for e in engines]


@pytest.mark.parametrize("engine", every_engine)
def test_a_deferred_call_answers_the_blocking_calls_text(amk, tmp_path, engine):
  assert "[[x|y]]" in run(amk, tmp_path, engine, collect, "pair")


@pytest.mark.parametrize("engine", every_engine)
def test_a_deferred_call_raises_the_same_error(amk, tmp_path, engine):
  assert "no function or variable named 'nope.fn'" in run(amk, tmp_path, engine, catch, "nope.fn")


@pytest.mark.engines("lua")
def test_a_write_through_the_handle_lands_at_collect(amk, tmp_path):
  mk = tmp_path / "write.mk"
  mk.write_text("\n".join([
    "@lua.import",
    "define lua.methods",
    '  function mark(x) amk.var.seen = x return "ok" end',
    "endef",
    "define prog",
    '  local h = amk.acall("mark", "v")',
    '  print(h.result() .. "," .. tostring(amk.var.seen))',
    "endef",
    "$(info [$(lua.exec* prog)])",
    "all:",
    "\ttrue",
    "",
  ]))
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[ok,v]" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("micropy")
def test_awaited_calls_overlap_under_asyncio(amk, tmp_path):
  mk = tmp_path / "gather.mk"
  mk.write_text("\n".join([
    "slow = $(shell sleep 1; echo $1)",
    "define prog",
    "  import amk, asyncio",
    "  async def main():",
    '    print("".join(await asyncio.gather(amk.acall("slow", "a"), amk.acall("slow", "b"), amk.acall("slow", "c"))))',
    "  asyncio.run(main())",
    "endef",
    "$(info [$(micropy.exec* prog)])",
    "all:",
    "\ttrue",
    "",
  ]))
  start = time.monotonic()
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  elapsed = time.monotonic() - start
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[abc]" in r.stdout, r.stdout + r.stderr
  assert elapsed < 1.8, f"three one-second calls took {elapsed:.2f}s, so they ran one after the other"


@pytest.mark.engines("lua")
def test_two_deferred_calls_overlap(amk, tmp_path):
  mk = tmp_path / "overlap.mk"
  mk.write_text("\n".join([
    "slow = $(shell sleep 1; echo $1)",
    "define prog",
    '  local a = amk.acall("slow", "a")',
    '  local b = amk.acall("slow", "b")',
    "  print(a.result() .. b.result())",
    "endef",
    "$(info [$(lua.exec* prog)])",
    "all:",
    "\ttrue",
    "",
  ]))
  start = time.monotonic()
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  elapsed = time.monotonic() - start
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[ab]" in r.stdout, r.stdout + r.stderr
  assert elapsed < 1.8, f"two one-second calls took {elapsed:.2f}s, so they ran one after the other"

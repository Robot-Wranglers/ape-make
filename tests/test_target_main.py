"""Pins that a guest target inherits the engine's main namespace, and that `fresh` opts out.

An import at parse sets a global in main. A target of the same engine, run as a job, sees it,
since the job is a fork of the parsed image and runs the program in that state; a target whose
at line says `fresh` runs the engine's entry point instead and sees nothing. Its output
streams to the job's stdout, so a target that prints before it waits is read before the wait
ends.
"""

import pytest

from conftest import sh

CASES = {
  "js": (
    ["@js.import", "define marks.js", "  globalThis.marked = 'set at parse';", "endef"],
    ["  print(`target: ${typeof globalThis.marked}`);"],
  ),
  "lua": (
    ["@lua.import", "define marks", "  marked = 'set at parse'", "endef"],
    ["  print('target: ' .. type(marked))"],
  ),
  "micropy": (
    ["@micropy.import", "define marks.py", "  marked = 'set at parse'", "endef"],
    ["  print('target: ' + ('string' if 'marked' in globals() else 'undefined'))"],
  ),
  "s7": (
    ["@s7.import", "define marks", "  (define marked \"set at parse\")", "endef"],
    ["  (display (if (defined? 'marked) \"target: string\" \"target: undefined\"))", "  (newline)"],
  ),
}


def _run(amk, tmp_path, engine, flags):
  setup, body = CASES[engine]
  mk = tmp_path / "main.mk"
  lines = [f"$(amk.require {engine})", *setup, f"@{engine}.target {flags}".rstrip(), "define probe", *body, "endef"]
  mk.write_text("\n".join(lines) + "\n")
  return sh(amk, ["-s", "-f", str(mk), "probe"], cwd=tmp_path, timeout=120)


@pytest.mark.parametrize("engine", sorted(CASES))
def test_a_target_sees_what_an_import_set_at_parse(amk, engines, tmp_path, engine):
  if engine not in engines:
    pytest.skip(f"no {engine} in this build")
  r = _run(amk, tmp_path, engine, "")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "target: string" in r.stdout, r.stdout + r.stderr


@pytest.mark.parametrize("engine", sorted(CASES))
def test_a_fresh_target_sees_nothing_from_parse(amk, engines, tmp_path, engine):
  if engine not in engines:
    pytest.skip(f"no {engine} in this build")
  r = _run(amk, tmp_path, engine, "fresh")
  assert r.returncode == 0, r.stdout + r.stderr
  assert "target: undefined" in r.stdout or "target: nil" in r.stdout, r.stdout + r.stderr

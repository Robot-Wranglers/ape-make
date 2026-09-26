"""Pins the engine init chunk.

Before the makefiles are read, Lua runs one chunk in its persistent state: the text of
`AMK_LUA_INIT`, the file it names after an `@`, or the payload's `__init__.lua`. Pinned:
a global from each source is there at parse time, a hook the chunk registers hears the
first goals event, a zygote's requests inherit it, and a named path that is missing says so.
"""

import shutil
import subprocess
import zipfile

import pytest

from conftest import sh

reader = "\n".join([
  "$(info seen=[$(lua.exec print(seen))])",
  "all:",
  "\t@true",
  "",
])

init_text = "seen = 7 amk.on.goals = function(e) io.stderr:write('goals=' .. e.target .. '\\n') end"


@pytest.mark.engines("lua")
def test_the_environment_chunk_runs_before_the_parse(amk, tmp_path):
  mk = tmp_path / "reader.mk"
  mk.write_text(reader)
  r = sh(amk, ["-s", "-f", str(mk)], env={"AMK_LUA_INIT": init_text}, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "seen=[7]" in r.stdout, r.stdout + r.stderr
  assert "goals=all" in r.stderr, r.stderr


@pytest.mark.engines("micropy")
def test_the_micropy_environment_chunk_runs_before_the_parse(amk, tmp_path):
  mk = tmp_path / "reader-py.mk"
  mk.write_text("\n".join([
    "$(info seen=[$(micropy.exec print(seen))])",
    "all:",
    "\t@true",
    "",
  ]))
  chunk = "import amk, sys; seen = 7; amk.on['goals'] = lambda e: sys.stderr.write('goals=' + e['target'] + '\\n')"
  r = sh(amk, ["-s", "-f", str(mk)], env={"AMK_MICROPY_INIT": chunk}, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "seen=[7]" in r.stdout, r.stdout + r.stderr
  assert "goals=all" in r.stderr, r.stderr


@pytest.mark.engines("js")
def test_the_js_environment_chunk_runs_before_the_parse(amk, tmp_path):
  mk = tmp_path / "reader-js.mk"
  mk.write_text("\n".join([
    "$(info seen=[$(js.exec print(seen))])",
    "all:",
    "\t@true",
    "",
  ]))
  chunk = "var seen = 7; amk.on.goals = e => std.err.puts('goals=' + e.target + '\\n')"
  r = sh(amk, ["-s", "-f", str(mk)], env={"AMK_JS_INIT": chunk}, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "seen=[7]" in r.stdout, r.stdout + r.stderr
  assert "goals=all" in r.stderr, r.stderr


@pytest.mark.engines("s7")
def test_the_s7_environment_chunk_runs_before_the_parse(amk, tmp_path):
  mk = tmp_path / "reader-s7.mk"
  mk.write_text("\n".join([
    "$(info seen=[$(s7.exec (display seen))])",
    "all:",
    "\t@true",
    "",
  ]))
  chunk = "(define seen 7) (set! (amk-on 'goals) (lambda (e) (format *stderr* \"goals=~A~%\" (e 'target))))"
  r = sh(amk, ["-s", "-f", str(mk)], env={"AMK_S7_INIT": chunk}, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "seen=[7]" in r.stdout, r.stdout + r.stderr
  assert "goals=all" in r.stderr, r.stderr


@pytest.mark.engines("lua")
def test_an_at_path_names_the_chunk_and_a_missing_one_says_so(amk, tmp_path):
  mk = tmp_path / "reader.mk"
  mk.write_text(reader)
  init = tmp_path / "init.lua"
  init.write_text("seen = 'from file'\n")
  r = sh(amk, ["-s", "-f", str(mk)], env={"AMK_LUA_INIT": "@" + str(init)}, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "seen=[from file]" in r.stdout, r.stdout + r.stderr
  r = sh(amk, ["-s", "-f", str(mk)], env={"AMK_LUA_INIT": "@" + str(tmp_path / "absent.lua")}, timeout=120)
  assert "AMK_LUA_INIT: cannot read" in r.stderr, r.stderr
  assert "seen=[nil]" in r.stdout, r.stdout


@pytest.mark.engines("lua")
def test_a_zygote_runs_it_once_for_every_request(amk, tmp_path, zygote):
  mk = tmp_path / "served.mk"
  mk.write_text("\n".join(["show:", "\t@echo seen=$(lua.exec print(seen))", ""]))
  sock = zygote(["-f", str(mk)], cwd=tmp_path)
  r = sh(amk, ["--client", str(sock), "show"], cwd=tmp_path, timeout=60)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "seen=nil" in r.stdout, r.stdout


@pytest.mark.engines("lua")
def test_a_zygote_started_with_the_chunk_serves_it(amk, tmp_path, zygote, monkeypatch):
  mk = tmp_path / "served.mk"
  mk.write_text("\n".join(["show:", "\t@echo seen=$(lua.exec print(seen))", ""]))
  monkeypatch.setenv("AMK_LUA_INIT", "seen = 'zygote'")
  sock = zygote(["-f", str(mk)], cwd=tmp_path)
  monkeypatch.delenv("AMK_LUA_INIT")
  for _ in range(2):
    r = sh(amk, ["--client", str(sock), "show"], cwd=tmp_path, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "seen=zygote" in r.stdout, r.stdout


@pytest.mark.engines("lua")
def test_the_payload_chunk_runs(amk, tmp_path):
  if shutil.which("zip") is None:
    pytest.skip("no zip to add a payload member")
  if not zipfile.is_zipfile(amk):
    pytest.skip("this amk carries no payload, so it is the native build")
  mk = tmp_path / "reader.mk"
  mk.write_text(reader)
  (tmp_path / "__init__.lua").write_text("seen = 'payload'\n")
  packed = tmp_path / "with-init.ape"
  shutil.copy2(amk, packed)
  packed.chmod(0o755)
  subprocess.run(["zip", "-q", str(packed), "__init__.lua"], cwd=tmp_path, check=True)
  r = sh(packed, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "seen=[payload]" in r.stdout, r.stdout + r.stderr

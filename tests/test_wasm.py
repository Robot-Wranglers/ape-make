"""Pins the wasm state engine.

`$(wasm.import module)` loads a path or hex bytes into the kept runtime and lifts every export
make can spell as a make function; `$(wasm.exec [deadline ms] name args...)` calls one export.
Pinned: a lifted export answers its results, state carries across calls, a module reaches make
through its `amk` imports, a wasi stdout is the value, a deadline ends a runaway call from this
guest or another, a namespace holds its own runtime, and the command line is wasm3's own.
"""

from pathlib import Path

import pytest

from conftest import sh

pytestmark = pytest.mark.engines("wasm")


def uleb(n):
  out = bytearray()
  while True:
    b = n & 0x7F
    n >>= 7
    if n:
      out.append(b | 0x80)
    else:
      out.append(b)
      return bytes(out)


def section(sid, body):
  return bytes([sid]) + uleb(len(body)) + body


def vec(items):
  return uleb(len(items)) + b"".join(items)


def name(s):
  return uleb(len(s)) + s.encode()


def functype(params, results):
  return b"\x60" + vec([bytes([t]) for t in params]) + vec([bytes([t]) for t in results])


def body(code):
  return uleb(len(code) + 1) + b"\x00" + code


I32 = 0x7F

# A module with a mutable global and six exports: set and show carry state, add does arithmetic, spin calls show forever, greet prints through amk.print, and read_len asks amk.var_get for cf_var.
TYPES = [
  functype([I32, I32], []),
  functype([I32, I32, I32, I32], [I32]),
  functype([], [I32]),
  functype([I32, I32], [I32]),
  functype([], []),
  functype([I32], []),
]
IMPORTS = [name("amk") + name("print") + b"\x00" + uleb(0), name("amk") + name("var_get") + b"\x00" + uleb(1)]
FUNCS = [5, 2, 3, 4, 4, 2]
EXPORTS = [name("set") + b"\x00" + uleb(2), name("show") + b"\x00" + uleb(3), name("add") + b"\x00" + uleb(4),
           name("spin") + b"\x00" + uleb(5), name("greet") + b"\x00" + uleb(6), name("read_len") + b"\x00" + uleb(7),
           name("memory") + b"\x02" + uleb(0)]
CODES = [
  body(b"\x20\x00\x24\x00\x0b"),
  body(b"\x23\x00\x41\x01\x6a\x0b"),
  body(b"\x20\x00\x20\x01\x6a\x0b"),
  body(b"\x03\x40\x10\x03\x1a\x0c\x00\x0b\x0b"),
  body(b"\x41\x10\x41\x02\x10\x00\x0b"),
  body(b"\x41\x00\x41\x06\x41\xc0\x00\x41\xc0\x00\x10\x01\x0b"),
]
DATA = [b"\x00\x41\x00\x0b" + name("cf_var"), b"\x00\x41\x10\x0b" + name("hi")]

MODULE = (b"\x00asm\x01\x00\x00\x00"
          + section(1, vec(TYPES))
          + section(2, vec(IMPORTS))
          + section(3, vec([uleb(t) for t in FUNCS]))
          + section(5, vec([b"\x00\x01"]))
          + section(6, vec([bytes([I32, 0x01]) + b"\x41\x00\x0b"]))
          + section(7, vec(EXPORTS))
          + section(10, vec(CODES))
          + section(11, vec(DATA)))

# A wasi module whose _start exits 0 and whose quit exits 3, both through proc_exit.
EXIT_MODULE = (b"\x00asm\x01\x00\x00\x00"
               + section(1, vec([functype([I32], []), functype([], [])]))
               + section(2, vec([name("wasi_snapshot_preview1") + name("proc_exit") + b"\x00" + uleb(0)]))
               + section(3, vec([uleb(1), uleb(1)]))
               + section(5, vec([b"\x00\x01"]))
               + section(7, vec([name("_start") + b"\x00" + uleb(1), name("quit") + b"\x00" + uleb(2),
                                 name("memory") + b"\x02" + uleb(0)]))
               + section(10, vec([body(b"\x41\x00\x10\x00\x0b"), body(b"\x41\x03\x10\x00\x0b")])))

fib = Path(__file__).resolve().parents[1] / "src/wasm3-0.9.0/test/lang/fib32.wasm"
wasi = Path(__file__).resolve().parents[1] / "src/wasm3-0.9.0/test/wasi/simple/test.wasm"


def run(amk, tmp_path, lines):
  mod = tmp_path / "cf.wasm"
  mod.write_bytes(MODULE)
  mk = tmp_path / "wasm.mk"
  mk.write_text("\n".join([f"module := {mod}"] + lines + ["all:", "\t@true", ""]))
  return sh(amk, ["-s", "-f", str(mk)], cwd=tmp_path, timeout=60)


def test_import_lifts_the_exports_and_exec_calls_one(amk, tmp_path):
  r = run(amk, tmp_path, [
    "names := $(wasm.import $(module))",
    "$(info names=[$(names)] fxns=[$(wasm.__fxns__)])",
    "$(info add=$(add 2 3) exec=$(wasm.exec add 40 2))",
  ])
  assert r.returncode == 0, r.stdout + r.stderr
  assert "names=[set show add spin greet read_len] fxns=[set show add spin greet read_len]" in r.stdout, r.stdout
  assert "add=5 exec=42" in r.stdout, r.stdout


def test_state_carries_across_calls(amk, tmp_path):
  r = run(amk, tmp_path, [
    "loaded := $(wasm.import $(module))",
    "x := $(set 41)",
    "$(info show=$(wasm.exec show) again=$(wasm.exec show))",
  ])
  assert r.returncode == 0, r.stdout + r.stderr
  assert "show=42 again=42" in r.stdout, r.stdout


def test_the_handle_reaches_make_through_the_amk_imports(amk, tmp_path):
  r = run(amk, tmp_path, [
    "cf_var := hello",
    "loaded := $(wasm.import $(module))",
    "$(info greet=$(wasm.exec greet) len=$(wasm.exec read_len))",
  ])
  assert r.returncode == 0, r.stdout + r.stderr
  assert "greet=hi len=5" in r.stdout, r.stdout


def test_a_module_loads_from_hex(amk, tmp_path):
  r = run(amk, tmp_path, [
    "hex := $(shell od -An -v -tx1 $(module))",
    "names := $(wasm.import $(hex))",
    "$(info names=[$(names)] add=$(add 1 1))",
  ])
  assert r.returncode == 0, r.stdout + r.stderr
  assert "names=[set show add spin greet read_len] add=2" in r.stdout, r.stdout


def test_a_deadline_ends_a_runaway_call_and_the_state_works_after(amk, tmp_path):
  r = run(amk, tmp_path, [
    "loaded := $(wasm.import $(module))",
    "spun := $(wasm.exec deadline 100 spin)",
    "ontime := $(wasm.exec deadline 1000 add 2 3)",
    "$(info spun=[$(spun)] ontime=[$(ontime)] after=[$(add 3 4)])",
  ])
  assert r.returncode == 0, r.stdout + r.stderr
  assert "spun=[] ontime=[5] after=[7]" in r.stdout, r.stdout
  assert "wasm: deadline: 100 ms" in r.stderr, r.stderr


@pytest.mark.engines("lua")
def test_a_deadline_set_in_lua_ends_a_wasm_call(amk, tmp_path):
  r = run(amk, tmp_path, [
    "loaded := $(wasm.import $(module))",
    "crossed := $(lua.exec local ok, e = pcall(amk.deadline, 100, function() return amk.call('spin') end) print(e))",
    "$(info crossed=[$(crossed)] after=[$(add 3 4)])",
  ])
  assert r.returncode == 0, r.stdout + r.stderr
  assert "crossed=[deadline: 100 ms] after=[7]" in r.stdout, r.stdout


def test_a_namespace_holds_its_own_runtime(amk, tmp_path):
  r = run(amk, tmp_path, [
    "$(wasm.ns W, create)",
    "loaded := $(W.import $(module))",
    "x := $(W.exec set 41)",
    "$(info show=$(W.exec show))",
    "main := $(wasm.exec show)",
  ])
  assert r.returncode != 0, r.stdout + r.stderr
  assert "show=42" in r.stdout, r.stdout
  assert "wasm: show: no modules loaded" in r.stderr, r.stderr
  assert "wasm.mk:6: *** wasm.exec: wasm exec exited with status" in r.stderr, r.stderr


def test_an_init_chunk_loads_a_module_before_the_parse(amk, tmp_path):
  mod = tmp_path / "cf.wasm"
  mod.write_bytes(MODULE)
  mk = tmp_path / "init.mk"
  mk.write_text("$(info add=$(add 20 22))\nall:\n\t@true\n")
  r = sh(amk, ["-s", "-f", str(mk)], cwd=tmp_path, env={"AMK_WASM_INIT": str(mod)}, timeout=60)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "add=42" in r.stdout, r.stdout


@pytest.mark.parametrize("lines, message, line", [
  (["none := $(wasm.import nowhere.wasm)"], "wasm.import: cannot read nowhere.wasm", "wasm.mk:2: *** wasm.import"),
  (["loaded := $(wasm.import $(module))", "few := $(wasm.exec add 1)"],
   "wasm: add: argument count mismatch", "wasm.mk:3: *** wasm.exec"),
])
def test_a_missing_module_and_a_bad_call_stop_make(amk, tmp_path, lines, message, line):
  r = run(amk, tmp_path, lines + ["$(info after)"])
  assert r.returncode != 0, r.stdout + r.stderr
  assert message in r.stderr, r.stderr
  assert line in r.stderr, r.stderr
  assert "after" not in r.stdout, r.stdout


@pytest.mark.skipif(not fib.exists(), reason="needs wasm3's unpacked test modules")
def test_a_module_from_wasm3s_tree(amk, tmp_path):
  r = run(amk, tmp_path, [
    f"names := $(wasm.import {fib})",
    "$(info names=[$(names)] fib=$(fib 20))",
  ])
  assert r.returncode == 0, r.stdout + r.stderr
  assert "names=[fib] fib=6765" in r.stdout, r.stdout


@pytest.mark.skipif(not wasi.exists(), reason="needs wasm3's unpacked test modules")
def test_a_wasi_start_writes_its_stdout_into_the_value(amk, tmp_path):
  r = run(amk, tmp_path, [
    f"loaded := $(wasm.import {wasi})",
    "out := $(wasm.exec _start test.wasm hello)",
    "$(info out=[$(out)])",
  ])
  assert r.returncode == 0, r.stdout + r.stderr
  assert "Hello world" in r.stdout and "Args: test.wasm; hello;" in r.stdout, r.stdout
  assert "\n]" not in r.stdout, r.stdout


def test_a_wasi_exit_of_zero_succeeds_and_another_code_stops_make(amk, tmp_path):
  mod = tmp_path / "exit.wasm"
  mod.write_bytes(EXIT_MODULE)
  r = run(amk, tmp_path, [
    f"loaded := $(wasm.import {mod})",
    "started := $(wasm.exec _start)",
    "$(info started=[$(started)])",
    "quit := $(wasm.exec quit)",
    "$(info quit=[$(quit)])",
  ])
  assert r.returncode != 0, r.stdout + r.stderr
  assert "started=[]" in r.stdout and "quit=[" not in r.stdout, r.stdout
  assert "trap" not in r.stderr, r.stderr
  assert "wasm: quit: exit 3" in r.stderr, r.stderr
  assert "wasm.mk:5: *** wasm.exec: wasm exec exited with status" in r.stderr, r.stderr


@pytest.mark.skipif(not fib.exists(), reason="needs wasm3's unpacked test modules")
def test_the_command_line_is_wasm3s_own(amk, tmp_path):
  r = sh(amk, ["--wasm", "--func", "fib", str(fib), "20"], cwd=tmp_path, timeout=60)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "Result: 6765" in r.stderr, r.stdout + r.stderr

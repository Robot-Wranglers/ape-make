"""Pins the wasm factory: a toolchain made into a stacked engine.

A toolchain is a compile command over make's source and module dollars, with a Dockerfile
define for an image or none for the host. Pinned: the import decorator builds and lifts,
the namespace handle answers, the module is content-addressed under the project so a rerun
builds nothing and a changed input builds again, the target decorator makes a target, and a
missing toolchain or define stops make with a message naming it.
"""

from pathlib import Path

import pytest

from conftest import sh

pytestmark = pytest.mark.engines("wasm")

fib = Path(__file__).resolve().parents[1] / "src/wasm3-0.9.0/test/lang/fib32.wasm"
wasi = Path(__file__).resolve().parents[1] / "src/wasm3-0.9.0/test/wasi/simple/test.wasm"
needs_fib = pytest.mark.skipif(not fib.exists(), reason="needs wasm3's unpacked test modules")

HEAD = [
  "load wasm",
  "define cp.build",
  "  cp MODULE $@",
  "endef",
  "$(amk.engine cp, guest=wasm, aliases=src)",
]


def run(amk, tmp_path, lines, module=None, head=HEAD):
  mk = tmp_path / "factory.mk"
  mk.write_text("\n".join([l.replace("MODULE", str(module or fib)) for l in head] + lines + ["all:", "\t@true", ""]))
  return sh(amk, ["-f", str(mk)], cwd=tmp_path, timeout=120)


@needs_fib
def test_the_import_decorator_builds_lifts_and_gives_a_namespace(amk, tmp_path):
  r = run(amk, tmp_path, [
    "@cp.import",
    "define fib.src",
    "  dollar names like $n stay the source's own",
    "endef",
    "$(info fib=$(fib 20) exec=$(cp.exec fib 10) version=[$(cp.__version__)] stacked=[$(amk.stacked.engines)])",
  ])
  assert r.returncode == 0, r.stdout + r.stderr
  assert "fib=6765 exec=55 version=[" in r.stdout and "stacked=[amklang cp]" in r.stdout, r.stdout + r.stderr
  where = list((tmp_path / ".amk" / "wasm" / "cp").glob("*"))
  assert len(where) == 1, where
  names = sorted(p.name for p in where[0].iterdir())
  assert names == ["build.sh", "fib.src", "fib.wasm"], names
  assert "$n" in (where[0] / "fib.src").read_text()
  assert str((where[0] / "fib.wasm").relative_to(tmp_path)) in (where[0] / "build.sh").read_text()


@needs_fib
def test_a_rerun_builds_nothing_and_a_changed_input_builds_again(amk, tmp_path):
  copy = tmp_path / "fib.wasm"
  copy.write_bytes(fib.read_bytes())
  lines = ["@cp.import", "define fib.src", "  one", "endef", "$(info fib=$(fib 10))"]
  r = run(amk, tmp_path, lines, module=copy)
  assert r.returncode == 0, r.stdout + r.stderr
  built = next((tmp_path / ".amk" / "wasm" / "cp").glob("*/fib.wasm"))
  stamp = built.stat().st_mtime_ns
  copy.unlink()
  r = run(amk, tmp_path, lines, module=copy)
  assert r.returncode == 0 and "fib=55" in r.stdout, r.stdout + r.stderr
  assert built.stat().st_mtime_ns == stamp, "the module was rebuilt"
  r = run(amk, tmp_path, ["@cp.import", "define fib.src", "  two", "endef"], module=copy)
  assert r.returncode != 0, r.stdout + r.stderr
  assert len(list((tmp_path / ".amk" / "wasm" / "cp").glob("*"))) == 2, "a changed source is a new directory"


@pytest.mark.skipif(not wasi.exists(), reason="needs wasm3's unpacked test modules")
def test_the_target_decorator_makes_a_target_that_builds_on_demand_and_runs_the_program(amk, tmp_path):
  lines = [
    "@cp.target",
    "define hello.src",
    "  one",
    "endef",
    "$(info built=[$(wildcard .amk/wasm/cp/*/hello.wasm)])",
  ]
  r = run(amk, tmp_path, lines, module=wasi)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "built=[]" in r.stdout, r.stdout + r.stderr
  r = sh(amk, ["-f", str(tmp_path / "factory.mk"), "hello"], cwd=tmp_path, timeout=60)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "Hello world" in r.stdout, r.stdout + r.stderr
  assert list((tmp_path / ".amk" / "wasm" / "cp").glob("*/hello.wasm")), "the target built the module"


@pytest.mark.skipif(not wasi.exists(), reason="needs wasm3's unpacked test modules")
def test_the_one_shot_form_runs_the_program_and_answers_its_stdout(amk, tmp_path):
  r = run(amk, tmp_path, [
    "define hello.src",
    "  one",
    "endef",
    "out := $(cp hello.src)",
    "$(info out=[$(firstword $(out))] built=$(words $(wildcard .amk/wasm/cp/*/hello.wasm)))",
  ], module=wasi)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "out=[Hello] built=1" in r.stdout, r.stdout + r.stderr


@needs_fib
def test_load_reaches_a_user_engine_by_its_extension_or_alias(amk, tmp_path):
  (tmp_path / "fib.src").write_text("the toolchain ignores this and copies a module\n")
  (tmp_path / "lib" / "cp").mkdir(parents=True)
  (tmp_path / "lib" / "cp" / "shadow.cp").write_text("one\n")
  r = run(amk, tmp_path, [
    "load ./fib.src",
    "load ./fib.src",
    "$(info fib=$(fib 20) [$(.LOADED)] [$(amk.loaded)])",
  ])
  assert r.returncode == 0, r.stdout + r.stderr
  assert "fib=6765 [/zip/lib/amk/wasm.mk ./fib.src] [wasm ./fib.src ./fib.src]" in r.stdout, r.stdout + r.stderr
  run(amk, tmp_path, ["load shadow.cp", "$(info [$(.LOADED)])"])
  r = sh(amk, ["-f", str(tmp_path / "factory.mk")], cwd=tmp_path, env={"AMKPATH": str(tmp_path / "lib")}, timeout=60)
  assert r.returncode == 0, r.stdout + r.stderr
  assert f"[/zip/lib/amk/wasm.mk {tmp_path}/lib/cp/shadow.cp]" in r.stdout, r.stdout + r.stderr
  r = run(amk, tmp_path, ["load ./fib.src"], head=["load wasm"])
  assert r.returncode != 0, r.stdout + r.stderr
  assert "load: ./fib.src: no engine claims the extension" in r.stderr, r.stderr
  r = run(amk, tmp_path, ["-load ./missing.src", "$(info ok [$(.LOADED)])"])
  assert r.returncode == 0, r.stdout + r.stderr
  assert "ok [/zip/lib/amk/wasm.mk]" in r.stdout, r.stdout + r.stderr


def test_the_standard_library_toolchains_register_on_load(amk, tmp_path):
  r = run(amk, tmp_path, [
    "load zig wat golang",
    "$(info [$(amk.engines)] go=$(amk.engine.ext.go) tinygo=$(origin amk.engine.ext.tinygo) zig=$(amk.engine.ext.zig) wat=$(amk.engine.ext.wat)"
    " guest=$(amk.engine.golang.guest) lang=$(amk.engine.zig.language) version=$(golang.__version__)"
    " env=$(amk.engine.wat.jit.env) build=$(amk.engine.wat.jit.build) [$(.LOADED)])",
  ], head=[])
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[amklang zig wat golang] go=golang tinygo=undefined zig=zig wat=wat guest=wasm lang=Zig version=0.39.0" in r.stdout, r.stdout + r.stderr
  assert "env=Dockerfile.wat build=wat.build [/zip/lib/amk/wasm.mk /zip/lib/amk/zig.amk /zip/lib/amk/wat.amk /zip/lib/amk/golang.amk]" in r.stdout, r.stdout + r.stderr


def test_a_wasm_engine_without_a_command_stops_make(amk, tmp_path):
  r = run(amk, tmp_path, ["$(amk.engine rustc, guest=wasm)"])
  assert r.returncode != 0, r.stdout + r.stderr
  assert "amk.engine: rustc: a wasm guest imports modules; give jit.build=" in r.stderr, r.stderr

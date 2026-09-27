"""Pins the persistent builtins, for lua and micropy alike.

`$(<name>.persistent program[,input])` runs in the make process against one state kept
for its life, where `$(<name> ...)` forks a fresh one per call. Pinned: state carries
across calls, input arrives as `amk.input`, an error leaves the state as it was, output is
trimmed like every builtin's even mid-expansion and holds a megabyte whole, and a zygote's
requests each start from what the parse left.
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


coded = "\n".join([
  "fail:",
  "\t@: $(lua.persistent amk.exit_code(70)); exit 1",
  "",
])


@pytest.mark.engines("lua")
def test_a_guest_names_the_exit_code(amk, tmp_path, zygote):
  """A failed recipe is make's exit 2, unless a guest named the status; a served client hears the same."""
  mk = tmp_path / "coded.mk"
  mk.write_text(coded)
  r = sh(amk, ["-f", str(mk), "fail"], cwd=tmp_path, timeout=60)
  assert r.returncode == 70, r.stdout + r.stderr
  sock = zygote(["-f", str(mk)], cwd=tmp_path)
  r = sh(amk, ["--client", str(sock), "fail"], cwd=tmp_path, timeout=60)
  assert r.returncode == 70, r.stdout + r.stderr


micropy_parse_time = "\n".join([
  "seed := $(micropy.persistent n = 41)",
  "kept := $(micropy.persistent print(n + 1))",
  'fresh := $(micropy print(globals().get("n")))',
  "upper := $(micropy.persistent import amk; print(amk.input.upper()),abc)",
  'none := $(micropy.persistent import amk; print(repr(amk.input)))',
  'oops := $(micropy.persistent raise ValueError("boom"))',
  "after := $(micropy.persistent print(n))",
  'multi := $(micropy.persistent print("a"); print("b"))',
  'wrote := $(micropy.persistent import sys; sys.stdout.write("w"); print("y"))',
  'big := $(micropy.persistent import sys; sys.stdout.write("x" * 1048576))',
  "biglen := $(micropy.persistent import amk; print(len(amk.input)),$(big))",
  'mixed := pre$(micropy.persistent print("a"))mid$(micropy.persistent print())post',
  "$(info kept=[$(kept)] fresh=[$(fresh)] upper=[$(upper)] none=[$(none)] oops=[$(oops)] after=[$(after)] multi=[$(multi)] wrote=[$(wrote)] biglen=[$(biglen)] mixed=[$(mixed)])",
  "all:",
  "\ttrue",
  "",
])

micropy_served = "\n".join([
  "seed := $(micropy.persistent n = 7)",
  "show:",
  "\t@echo n=$(micropy.persistent n = n + 1; print(n))",
  "",
])


@pytest.mark.engines("micropy")
def test_micropy_state_outlives_a_call(amk, tmp_path):
  mk = tmp_path / "persist-py.mk"
  mk.write_text(micropy_parse_time)
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "kept=[42]" in r.stdout, r.stdout
  assert "fresh=[None]" in r.stdout, r.stdout
  assert "upper=[ABC]" in r.stdout, r.stdout
  assert "none=['']" in r.stdout, r.stdout
  assert "oops=[]" in r.stdout and "boom" in r.stderr, r.stdout + r.stderr
  assert "after=[41]" in r.stdout, r.stdout
  assert "multi=[a\nb]" in r.stdout, r.stdout
  assert "wrote=[wy]" in r.stdout, r.stdout
  assert "biglen=[1048576]" in r.stdout, r.stdout[-400:]
  assert "mixed=[preamidpost]" in r.stdout, r.stdout[-400:]


js_parse_time = "\n".join([
  "seed := $(js.persistent var n = 41)",
  "kept := $(js.persistent print(n + 1))",
  "fresh := $(js print(typeof n))",
  "upper := $(js.persistent print(amk.input.toUpperCase()),abc)",
  "none := $(js.persistent print(JSON.stringify(amk.input)))",
  'oops := $(js.persistent throw new Error("boom"))',
  "after := $(js.persistent print(n))",
  'multi := $(js.persistent print("a"); print("b"))',
  'wrote := $(js.persistent std.out.puts("w"); print("y"))',
  'big := $(js.persistent std.out.puts("x".repeat(1048576)))',
  "biglen := $(js.persistent print(amk.input.length),$(big))",
  'mixed := pre$(js.persistent print("a"))mid$(js.persistent print())post',
  "$(info kept=[$(kept)] fresh=[$(fresh)] upper=[$(upper)] none=[$(none)] oops=[$(oops)] after=[$(after)] multi=[$(multi)] wrote=[$(wrote)] biglen=[$(biglen)] mixed=[$(mixed)])",
  "all:",
  "\ttrue",
  "",
])


@pytest.mark.engines("js")
def test_js_state_outlives_a_call(amk, tmp_path):
  mk = tmp_path / "persist-js.mk"
  mk.write_text(js_parse_time)
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "kept=[42]" in r.stdout, r.stdout
  assert "fresh=[undefined]" in r.stdout, r.stdout
  assert "upper=[ABC]" in r.stdout, r.stdout
  assert 'none=[""]' in r.stdout, r.stdout
  assert "oops=[]" in r.stdout and "boom" in r.stderr, r.stdout + r.stderr
  assert "after=[41]" in r.stdout, r.stdout
  assert "multi=[a\nb]" in r.stdout, r.stdout
  assert "wrote=[wy]" in r.stdout, r.stdout
  assert "biglen=[1048576]" in r.stdout, r.stdout[-400:]
  assert "mixed=[preamidpost]" in r.stdout, r.stdout[-400:]


@pytest.mark.engines("js")
def test_js_requests_start_from_the_parse(amk, tmp_path, zygote):
  mk = tmp_path / "served-js.mk"
  mk.write_text("\n".join([
    "seed := $(js.persistent var n = 7)",
    "show:",
    "\t@echo n=$(js.persistent n = n + 1; print(n))",
    "",
  ]))
  sock = zygote(["-f", str(mk)], cwd=tmp_path)
  for _ in range(2):
    r = sh(amk, ["--client", str(sock), "show"], cwd=tmp_path, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.strip() == "n=8", r.stdout + r.stderr


s7_parse_time = "\n".join([
  "seed := $(s7.persistent (define n 41))",
  "kept := $(s7.persistent (display (+ n 1)))",
  "fresh := $(s7 (display (defined? 'n)))",
  "upper := $(s7.persistent (display (string-upcase amk-input)),abc)",
  "none := $(s7.persistent (write amk-input))",
  "oops := $(s7.persistent (error 'kaput \"boom\"))",
  "after := $(s7.persistent (display n))",
  'multi := $(s7.persistent (display "a") (newline) (display "b"))',
  'wrote := $(s7.persistent (write-string "w") (display "y"))',
  'big := $(s7.persistent (display (apply string-append (make-list 131072 "abcdefgh"))))',
  "biglen := $(s7.persistent (display (length amk-input)),$(big))",
  'mixed := pre$(s7.persistent (display "a") (newline))mid$(s7.persistent (newline))post',
  "$(info kept=[$(kept)] fresh=[$(fresh)] upper=[$(upper)] none=[$(none)] oops=[$(oops)] after=[$(after)] multi=[$(multi)] wrote=[$(wrote)] biglen=[$(biglen)] mixed=[$(mixed)])",
  "all:",
  "\ttrue",
  "",
])


@pytest.mark.engines("s7")
def test_s7_state_outlives_a_call(amk, tmp_path):
  mk = tmp_path / "persist-s7.mk"
  mk.write_text(s7_parse_time)
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "kept=[42]" in r.stdout, r.stdout
  assert "fresh=[#f]" in r.stdout, r.stdout
  assert "upper=[ABC]" in r.stdout, r.stdout
  assert 'none=[""]' in r.stdout, r.stdout
  assert "oops=[]" in r.stdout and "boom" in r.stderr, r.stdout + r.stderr
  assert "after=[41]" in r.stdout, r.stdout
  assert "multi=[a\nb]" in r.stdout, r.stdout
  assert "wrote=[wy]" in r.stdout, r.stdout
  assert "biglen=[1048576]" in r.stdout, r.stdout[-400:]
  assert "mixed=[preamidpost]" in r.stdout, r.stdout[-400:]


@pytest.mark.engines("s7")
def test_s7_requests_start_from_the_parse(amk, tmp_path, zygote):
  mk = tmp_path / "served-s7.mk"
  mk.write_text("\n".join([
    "seed := $(s7.persistent (define n 7))",
    "show:",
    "\t@echo n=$(s7.persistent (set! n (+ n 1)) (display n))",
    "",
  ]))
  sock = zygote(["-f", str(mk)], cwd=tmp_path)
  for _ in range(2):
    r = sh(amk, ["--client", str(sock), "show"], cwd=tmp_path, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.strip() == "n=8", r.stdout + r.stderr


@pytest.mark.engines("micropy")
def test_micropy_requests_start_from_the_parse(amk, tmp_path, zygote):
  mk = tmp_path / "served-py.mk"
  mk.write_text(micropy_served)
  sock = zygote(["-f", str(mk)], cwd=tmp_path)
  for _ in range(2):
    r = sh(amk, ["--client", str(sock), "show"], cwd=tmp_path, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.strip() == "n=8", r.stdout + r.stderr

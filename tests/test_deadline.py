"""Pins amk.deadline in lua, js, micropy, and s7, the deadline word of wasm.exec, and the --deadline option of sqlite.

`amk.deadline(ms, fn, ...)`, `(amk-deadline ms fn ...)` in s7, runs fn with its arguments and answers its result, or raises
`deadline: <ms> ms` at the call once ms milliseconds pass. Pinned per guest: a runaway loop
ends with that error, a catch inside the run does not keep it going, a nested deadline
keeps the tighter one, a run on time answers its result, and the state works afterwards.
"""

import json
from pathlib import Path

import pytest

from conftest import sh

lua_cases = "\n".join([
  "runaway := $(lua.exec local ok, e = pcall(amk.deadline, 100, function() while true do end end) print(e))",
  "caught := $(lua.exec local ok, e = pcall(amk.deadline, 100, function() while true do pcall(function() while true do end end) end end) print(e))",
  "inner := $(lua.exec local ok, e = pcall(amk.deadline, 5000, function() return amk.deadline(100, function() while true do end end) end) print(e))",
  "outer := $(lua.exec local ok, e = pcall(amk.deadline, 100, function() return amk.deadline(5000, function() while true do end end) end) print(e))",
  "ontime := $(lua.exec print(amk.deadline(1000, function(a, b) return a + b end, 2, 3)))",
  "after := $(lua.exec print('still'))",
  "all:",
  "\t@echo '[$(runaway)] [$(caught)] [$(inner)] [$(outer)] [$(ontime)] [$(after)]'",
  "",
])

js_cases = "\n".join([
  "runaway := $(js.exec try { amk.deadline(100, () => { for (;;); }); } catch (e) { print(e.message); })",
  "caught := $(js.exec try { amk.deadline(100, () => { for (;;) try { for (;;); } catch (_) {} }); } catch (e) { print(e.message); })",
  "inner := $(js.exec try { amk.deadline(5000, () => amk.deadline(100, () => { for (;;); })); } catch (e) { print(e.message); })",
  "outer := $(js.exec try { amk.deadline(100, () => amk.deadline(5000, () => { for (;;); })); } catch (e) { print(e.message); })",
  "ontime := $(js.exec print(amk.deadline(1000, (a, b) => a + b, 2, 3)))",
  "after := $(js.exec print('still'))",
  "all:",
  "\t@echo '[$(runaway)] [$(caught)] [$(inner)] [$(outer)] [$(ontime)] [$(after)]'",
  "",
])

py_cases = "\n".join([
  "define py_seed",
  "import amk",
  "def spin():",
  "    while True:",
  "        pass",
  "def swallow():",
  "    while True:",
  "        try:",
  "            spin()",
  "        except BaseException:",
  "            pass",
  "def report(f):",
  "    try:",
  "        print(f())",
  "    except RuntimeError as e:",
  "        print(e)",
  "endef",
  "seed := $(micropy.exec* py_seed)",
  "runaway := $(micropy.exec report(lambda: amk.deadline(100, spin)))",
  "caught := $(micropy.exec report(lambda: amk.deadline(100, swallow)))",
  "inner := $(micropy.exec report(lambda: amk.deadline(5000, lambda: amk.deadline(100, spin))))",
  "outer := $(micropy.exec report(lambda: amk.deadline(100, lambda: amk.deadline(5000, spin))))",
  "ontime := $(micropy.exec report(lambda: amk.deadline(1000, lambda a, b: a + b, 2, 3)))",
  "after := $(micropy.exec print('still'))",
  "all:",
  "\t@echo '[$(runaway)] [$(caught)] [$(inner)] [$(outer)] [$(ontime)] [$(after)]'",
  "",
])

s7_cases = "\n".join([
  "define s7_seed",
  "(define (spin) (let loop ((i 0)) (set! i (+ i 1)) (loop i)))",
  "(define (swallow) (let loop () (catch #t spin (lambda a #f)) (loop)))",
  "(define (report thunk) (display (catch 'deadline thunk (lambda (t i) (car i)))))",
  "endef",
  "seed := $(s7.exec* s7_seed)",
  "runaway := $(s7.exec (report (lambda () (amk-deadline 100 spin))))",
  "caught := $(s7.exec (report (lambda () (amk-deadline 100 swallow))))",
  "inner := $(s7.exec (report (lambda () (amk-deadline 5000 (lambda () (amk-deadline 100 spin))))))",
  "outer := $(s7.exec (report (lambda () (amk-deadline 100 (lambda () (amk-deadline 5000 spin))))))",
  "ontime := $(s7.exec (report (lambda () (amk-deadline 1000 + 2 3))))",
  "after := $(s7.exec (display \"still\"))",
  "all:",
  "\t@echo '[$(runaway)] [$(caught)] [$(inner)] [$(outer)] [$(ontime)] [$(after)]'",
  "",
])

expected = "[deadline: 100 ms] [deadline: 100 ms] [deadline: 100 ms] [deadline: 100 ms] [5] [still]"


@pytest.mark.parametrize("engine, cases", [
  pytest.param("lua", lua_cases, marks=pytest.mark.engines("lua"), id="lua"),
  pytest.param("js", js_cases, marks=pytest.mark.engines("js"), id="js"),
  pytest.param("micropy", py_cases, marks=pytest.mark.engines("micropy"), id="micropy"),
  pytest.param("s7", s7_cases, marks=pytest.mark.engines("s7"), id="s7"),
])
def test_a_deadline_ends_the_run_and_answers_the_same_in_each_guest(amk, tmp_path, engine, cases):
  mk = tmp_path / f"{engine}.mk"
  mk.write_text(cases)
  r = sh(amk, ["-s", "-f", str(mk)], timeout=30)
  assert r.returncode == 0, r.stdout + r.stderr
  assert expected in r.stdout, r.stdout + r.stderr


def test_the_engine_listing_says_how_each_engine_takes_a_deadline(amk):
  r = sh(amk, ["--list-engines"], timeout=30)
  assert r.returncode == 0, r.stderr
  kinds = {e["name"]: e["deadline"] for e in json.loads(r.stdout)["engines"]}
  want = {"awk": None, "jq": None, "lua": "handle", "s7": "handle", "micropy": "handle", "js": "handle", "wasm": "handle", "sqlite": "option"}
  assert {k: v for k, v in want.items() if k in kinds} == {k: kinds[k] for k in want if k in kinds}


crossed = "\n".join([
  "$(amk.require lua, js, micropy)",
  "seed_lua := $(lua.exec amk.func('lua_spin', function() while true do end end) amk.func('lua_ok', function() return 'ok' end))",
  "seed_js := $(js.exec amk.func('js_spin', () => { for (;;); }); amk.func('js_ok', () => 'ok'))",
  "define py_seed",
  "import amk",
  "def spin():",
  "    while True:",
  "        pass",
  "def report(f):",
  "    try:",
  "        print(f())",
  "    except RuntimeError as e:",
  "        print(e)",
  "amk.func('py_spin', spin)",
  "amk.func('py_ok', lambda: 'ok')",
  "endef",
  "seed_py := $(micropy.exec* py_seed)",
  "lua_js := $(lua.exec local ok, e = pcall(amk.deadline, 100, amk.call, 'js_spin') print(e))",
  "lua_py := $(lua.exec local ok, e = pcall(amk.deadline, 100, amk.call, 'py_spin') print(e))",
  "js_lua := $(js.exec try { amk.deadline(100, () => amk.call('lua_spin')); } catch (e) { print(e.message); })",
  "js_py := $(js.exec try { amk.deadline(100, () => amk.call('py_spin')); } catch (e) { print(e.message); })",
  "py_lua := $(micropy.exec report(lambda: amk.deadline(100, amk.call, 'lua_spin')))",
  "py_js := $(micropy.exec report(lambda: amk.deadline(100, amk.call, 'js_spin')))",
  "outer := $(js.exec try { amk.deadline(100, () => { amk.deadline(5000, () => 1); return amk.call('lua_spin'); }); } catch (e) { print(e.message); })",
  "after := $(lua.exec print(amk.call('js_ok') .. amk.call('py_ok'))) $(micropy.exec print(amk.call('lua_ok')))",
  "all:",
  "\t@echo '[$(lua_js)] [$(lua_py)] [$(js_lua)] [$(js_py)] [$(py_lua)] [$(py_js)] [$(outer)] [$(after)]'",
  "",
])


@pytest.mark.engines("lua", "js", "micropy")
def test_a_deadline_stops_a_callee_in_another_guest_and_raises_in_the_caller(amk, tmp_path):
  """Each direction between lua, js and micropy through amk.call; an outer deadline still holds after an inner one returns; every guest answers afterwards."""
  mk = tmp_path / "crossed.mk"
  mk.write_text(crossed)
  r = sh(amk, ["-s", "-f", str(mk)], timeout=60)
  assert r.returncode == 0, r.stdout + r.stderr
  want = " ".join(["[deadline: 100 ms]"] * 7) + " [okok ok]"
  assert want in r.stdout, r.stdout + r.stderr


fib = Path(__file__).resolve().parents[1] / "src/wasm3-0.9.0/test/lang/fib32.wasm"

wasm_cases = "\n".join([
  f"loaded := $(wasm.import {fib})",
  "slow := $(wasm.exec deadline 100 fib 45)",
  "quick := $(wasm.exec deadline 1000 fib 20)",
  "after := $(fib 10)",
  "all:",
  "\t@echo '[$(slow)] [$(quick)] [$(after)]'",
  "",
])

sqlite_cases = "\n".join([
  "$(sqlite.ns w, create)",
  "spin := $(w.get --deadline 100 WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM c) SELECT count(*) AS n FROM c)",
  "sum := $(w.get --deadline 1000 SELECT 2+3 AS n)",
  "after := $(w.get SELECT 'still' AS s)",
  "all:",
  "\t@echo '[$(spin)] [$(sum)] [$(after)]'",
  "",
])


@pytest.mark.engines("wasm")
@pytest.mark.skipif(not fib.exists(), reason="needs wasm3's unpacked test modules")
def test_a_wasm_deadline_ends_the_run(amk, tmp_path):
  """wasm3 asks the host before every call, so the deadline ends the call in place and the runtime works after."""
  mk = tmp_path / "wasm.mk"
  mk.write_text(wasm_cases)
  r = sh(amk, ["-s", "-f", str(mk)], timeout=30)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "wasm: deadline: 100 ms" in r.stderr, r.stderr
  assert "[] [6765] [55]" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("sqlite")
def test_a_sqlite_deadline_ends_the_statement_and_keeps_the_workspace(amk, tmp_path):
  mk = tmp_path / "sqlite.mk"
  mk.write_text(sqlite_cases)
  r = sh(amk, ["-s", "-f", str(mk)], timeout=30)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "sqlite.get: deadline: 100 ms" in r.stderr, r.stderr
  assert '[] [{"n":5}] [{"s":"still"}]' in r.stdout, r.stdout + r.stderr

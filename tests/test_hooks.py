"""Pins the hooks.

make announces the goal list and each recipe's start and end to every engine with a hook
entry. Lua hears them as `amk.on.<event>(e)` in its persistent state. Pinned: the three
events fire in order with the target and status, a failing recipe under -k reports as
failed with its exit code, and a hook that errors reports on stderr without stopping make.
"""

import pytest

from conftest import sh

subscribe = " ".join([
  "log = {} n = 0",
  "local function note(s) n = n + 1 log[n] = s end",
  "amk.on.goals = function(e) note(e.event .. '=' .. e.target) end",
  "amk.on.recipe_start = function(e) note(e.target .. '?') end",
  "amk.on.recipe_end = function(e) note(e.target .. ':' .. e.status .. '/' .. e.code) end",
])

dump = "local s = '' for i in pairs(log) do s = s .. log[i] .. ' ' end print(s)"

makefile = "\n".join([
  "seed := $(lua.persistent %s)" % subscribe,
  "all: a b c",
  "a:",
  "\t@true",
  "b:",
  "\t@exit 3",
  "c:",
  "\t@echo [$(lua.persistent %s)]" % dump,
  "",
])

erring = "\n".join([
  "seed := $(lua.persistent amk.on.recipe_start = function(e) error('no ' .. e.target) end)",
  "all:",
  "\t@echo ran",
  "",
])


@pytest.mark.engines("lua")
def test_events_fire_in_order(amk, tmp_path):
  mk = tmp_path / "hooks.mk"
  mk.write_text(makefile)
  r = sh(amk, ["-s", "-k", "-f", str(mk)], timeout=120)
  assert r.returncode == 2, r.stdout + r.stderr
  assert "[goals=all a? a:success/0 b? b:failed/3 ]" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("lua")
def test_a_hook_error_reports_and_make_goes_on(amk, tmp_path):
  mk = tmp_path / "erring.mk"
  mk.write_text(erring)
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "ran", r.stdout
  assert "lua hook recipe_start" in r.stderr and "no all" in r.stderr, r.stderr


micropy_subscribe = "; ".join([
  "import amk",
  "log = []",
  "amk.on['goals'] = lambda e: log.append(e['event'] + '=' + e['target'])",
  "amk.on['recipe_start'] = lambda e: log.append(e['target'] + '?')",
  "amk.on['recipe_end'] = lambda e: log.append(e['target'] + ':' + e['status'] + '/' + str(e['code']))",
])

micropy_makefile = "\n".join([
  "seed := $(micropy.persistent %s)" % micropy_subscribe,
  "all: a b c",
  "a:",
  "\t@true",
  "b:",
  "\t@exit 3",
  "c:",
  "\t@echo [$(micropy.persistent print(' '.join(log)))]",
  "",
])

micropy_erring = "\n".join([
  "seed := $(micropy.persistent import amk; amk.on['recipe_start'] = lambda e: 1 / 0)",
  "all:",
  "\t@echo ran",
  "",
])


js_subscribe = "; ".join([
  "var log = []",
  "amk.on.goals = e => log.push(e.event + '=' + e.target)",
  "amk.on.recipe_start = e => log.push(e.target + '?')",
  "amk.on.recipe_end = e => log.push(e.target + ':' + e.status + '/' + e.code)",
])


@pytest.mark.engines("js")
def test_js_events_fire_in_order(amk, tmp_path):
  mk = tmp_path / "hooks-js.mk"
  mk.write_text("\n".join([
    "seed := $(js.persistent %s)" % js_subscribe,
    "all: a b c",
    "a:",
    "\t@true",
    "b:",
    "\t@exit 3",
    "c:",
    "\t@echo [$(js.persistent print(log.join(' ')))]",
    "",
  ]))
  r = sh(amk, ["-s", "-k", "-f", str(mk)], timeout=120)
  assert r.returncode == 2, r.stdout + r.stderr
  assert "[goals=all a? a:success/0 b? b:failed/3]" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("js")
def test_a_js_hook_error_reports_and_make_goes_on(amk, tmp_path):
  mk = tmp_path / "erring-js.mk"
  mk.write_text("\n".join([
    "seed := $(js.persistent amk.on.recipe_start = e => { throw new Error('no ' + e.target) })",
    "all:",
    "\t@echo ran",
    "",
  ]))
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "ran", r.stdout
  assert "js hook recipe_start" in r.stderr and "no all" in r.stderr, r.stderr


s7_subscribe = " ".join([
  "(define log ())",
  "(define (note s) (set! log (append log (list s))))",
  "(set! (amk-on 'goals) (lambda (e) (note (string-append (e 'event) \"=\" (e 'target)))))",
  "(set! (amk-on 'recipe_start) (lambda (e) (note (string-append (e 'target) \"?\"))))",
  "(set! (amk-on 'recipe_end) (lambda (e) (note (format #f \"~A:~A/~A\" (e 'target) (e 'status) (e 'code)))))",
])


@pytest.mark.engines("s7")
def test_s7_events_fire_in_order(amk, tmp_path):
  mk = tmp_path / "hooks-s7.mk"
  mk.write_text("\n".join([
    "seed := $(s7.persistent %s)" % s7_subscribe,
    "all: a b c",
    "a:",
    "\t@true",
    "b:",
    "\t@exit 3",
    "c:",
    "\t@echo [$(s7.persistent (format #t \"~{~A~^ ~}\" log))]",
    "",
  ]))
  r = sh(amk, ["-s", "-k", "-f", str(mk)], timeout=120)
  assert r.returncode == 2, r.stdout + r.stderr
  assert "[goals=all a? a:success/0 b? b:failed/3]" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("s7")
def test_an_s7_hook_error_reports_and_make_goes_on(amk, tmp_path):
  mk = tmp_path / "erring-s7.mk"
  mk.write_text("\n".join([
    "seed := $(s7.persistent (set! (amk-on 'recipe_start) (lambda (e) (error 'no (e 'target)))))",
    "all:",
    "\t@echo ran",
    "",
  ]))
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "ran", r.stdout
  assert "s7 hook recipe_start" in r.stderr and "all" in r.stderr, r.stderr


@pytest.mark.engines("micropy")
def test_micropy_events_fire_in_order(amk, tmp_path):
  mk = tmp_path / "hooks-py.mk"
  mk.write_text(micropy_makefile)
  r = sh(amk, ["-s", "-k", "-f", str(mk)], timeout=120)
  assert r.returncode == 2, r.stdout + r.stderr
  assert "[goals=all a? a:success/0 b? b:failed/3]" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("micropy")
def test_a_micropy_hook_error_reports_and_make_goes_on(amk, tmp_path):
  mk = tmp_path / "erring-py.mk"
  mk.write_text(micropy_erring)
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "ran", r.stdout
  assert "micropy hook recipe_start" in r.stderr and "ZeroDivisionError" in r.stderr, r.stderr

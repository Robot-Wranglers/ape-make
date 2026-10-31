"""Pins the two ways a payload library is reached, per guest, as `payload/lib/README.md` tables them.

A topic under `lib/<name>/` is a module of the engine's `amk` handle. An engine folder,
`lib/<eng>/`, is on that engine's own import path and is reached by the language's plain
import: `import foo` in micropy, `require` in lua, a bare specifier in js, `load` in s7.
"""

import pytest

from conftest import sh


def run(amk, tmp_path, body):
  mk = tmp_path / "lib.mk"
  mk.write_text(body + "\nall:\n\t@true\n")
  r = sh(amk, ["-s", "-f", str(mk)], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  return r.stdout + r.stderr


@pytest.mark.engines("micropy", "sqlite")
def test_micropy_reaches_a_topic_through_amk_and_a_package_by_plain_import(amk, tmp_path):
  out = run(amk, tmp_path, "\n".join([
    "load tspace",
    "define py",
    "import utemplate",
    "import amk",
    "on = amk.tspace.on",
    "print('pkg', utemplate.__name__, 'topic', on.__name__)",
    "try:",
    "    import tspace",
    "except ImportError:",
    "    print('bare topic refused')",
    "endef",
    "$(info $(micropy.exec* py))",
  ]))
  assert "pkg utemplate topic on" in out and "bare topic refused" in out, out


@pytest.mark.engines("lua", "sqlite")
def test_lua_reaches_a_topic_through_amk_and_a_package_by_require(amk, tmp_path):
  out = run(amk, tmp_path, "\n".join([
    "load tspace",
    'x := $(lua.exec print(type(require("dkjson").encode), type(amk.tspace.out), pcall(require, "tspace")))',
    "$(info [$(x)])",
  ]))
  assert "[function\tfunction\tfalse\tmodule 'tspace' not found" in out, out


@pytest.mark.engines("js")
def test_js_reaches_a_topic_through_amk_and_a_package_by_bare_specifier(amk, tmp_path):
  out = run(amk, tmp_path, "\n".join([
    'x := $(js.exec const m = await import("effection"); print(typeof m.sleep, typeof amk.plex.sleep))',
    "$(info [$(x)])",
  ]))
  assert "[function function]" in out, out


@pytest.mark.engines("s7")
def test_s7_loads_a_package_from_its_load_path_and_a_topic_by_symbol(amk, tmp_path):
  (tmp_path / "greet.scm").write_text('(define (greet) "hi from the load path")\n')
  out = run(amk, tmp_path, "\n".join([
    f'x := $(s7.exec (set! *load-path* (cons "{tmp_path}" *load-path*)) (load "greet.scm") (display (list (greet) (member "/zip/lib/s7" *load-path*))))',
    "$(info [$(x)])",
  ]))
  assert '[("hi from the load path" ("/zip/lib/s7"' in out, out


# A missing field of the handle that names a make builtin calls it, dotted names nest, a name make lacks stays missing, and a topic file still wins.
BUILTIN_AS_ATTRIBUTE = {
  "lua": '$(lua.exec print(amk.sys("uname") == amk.call("amk.sys", "uname"), amk.pool.held("goals"), amk.nothing_here == nil))',
  "micropy": '$(micropy.exec import amk; print(amk.sys("uname") == amk.call("amk.sys", "uname"), amk.pool.held("goals"), getattr(amk, "nothing_here", None) is None))',
  "js": '$(js.exec print(amk.sys("uname") === amk.call("amk.sys", "uname"), amk.pool.held("goals"), amk.nothing_here === undefined))',
  "s7": '$(s7.exec (display (list (string=? (amk-sys "uname") (amk-call "amk.sys" "uname")) (amk-pool-held "goals") (catch #t (lambda () (amk-nothing-here) #f) (lambda args #t)))))',
}

WANT = {"lua": "true\t0\ttrue", "micropy": "True 0 True", "js": "true 0 true", "s7": '(#t "0" #t)'}


@pytest.mark.parametrize("engine", sorted(BUILTIN_AS_ATTRIBUTE))
def test_a_builtin_is_reached_as_an_attribute_of_amk(amk, tmp_path, engine, engines):
  if engine not in engines:
    pytest.skip(f"no {engine} in this build")
  out = run(amk, tmp_path, f"$(info [{BUILTIN_AS_ATTRIBUTE[engine]}])")
  assert f"[{WANT[engine]}]" in out, out


@pytest.mark.engines("lua", "sqlite")
def test_a_topic_file_wins_over_a_builtin_of_the_same_name(amk, tmp_path):
  out = run(amk, tmp_path, "\n".join([
    "load tspace",
    '$(info [$(lua.exec print(type(amk.tspace), type(amk.tspace.out), type(amk.sys)))])',
  ]))
  assert "[table\tfunction\ttable]" in out, out

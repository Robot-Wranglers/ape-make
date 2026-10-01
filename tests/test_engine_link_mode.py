"""Pins cross-guest calls: a function one guest gives make is callable from any other guest.

Every persistent engine registers a tag function and a via function. Via expands a
call to another engine's tag through make, so each caller reaches each callee,
itself included. Calls nest through several engines, and a one-shot guest in its
fork reaches functions the persistent states registered.
"""

import itertools

import pytest

from conftest import sh

linked = ["lua", "s7", "micropy", "js"]

# Per engine: a define that registers tag, which wraps its argument, and via, which expands a call to the named engine's tag.
bodies = {
  "lua": [
    '  amk.func("lua_tag", function(s) return "lua(" .. s .. ")" end)',
    '  amk.func("lua_via", function(callee, s) return "lua<" .. amk.expand("$(" .. callee .. "_tag " .. s .. ")") .. ">" end)',
  ],
  "s7": [
    '  (amk-func \'s7_tag (lambda (s) (string-append "s7(" s ")")))',
    '  (amk-func \'s7_via (lambda (callee s) (string-append "s7<" (amk-expand (string-append "$(" callee "_tag " s ")")) ">")))',
  ],
  "micropy": [
    "  import amk",
    '  amk.func("micropy_tag", lambda s: "micropy(" + s + ")")',
    '  amk.func("micropy_via", lambda callee, s: "micropy<" + amk.expand("$(%s_tag %s)" % (callee, s)) + ">")',
  ],
  "js": [
    '  amk.func("js_tag", s => "js(" + s + ")")',
    '  amk.func("js_via", (callee, s) => "js<" + amk.expand("$(" + callee + "_tag " + s + ")") + ">")',
  ],
}

pairs = list(itertools.product(linked, repeat=2))


def makefile(lines):
  defines = [ln for e, body in bodies.items()
             for ln in [f"@{e}.persistent", f"define {e}.reg", *body, "endef"]]
  return "\n".join([*defines, *lines, "all:", "\ttrue", ""])


def run(amk, tmp_path, name, lines):
  mk = tmp_path / name
  mk.write_text(makefile(lines))
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  return r


@pytest.mark.engines(*linked)
def test_every_guest_calls_every_guest(amk, tmp_path):
  r = run(amk, tmp_path, "pairs.mk",
          [f"$(info {c}->{d}=[$({c}_via {d},x)])" for c, d in pairs])
  for c, d in pairs:
    assert f"{c}->{d}=[{c}<{d}(x)>]" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines(*linked)
def test_calls_nest_through_several_guests(amk, tmp_path):
  r = run(amk, tmp_path, "chain.mk", [
    "$(info chain=[$(lua_via s7,$$(micropy_via js,y))])",
    "$(info back=[$(js_via micropy,$$(s7_via lua,y))])",
  ])
  assert "chain=[lua<s7(micropy<js(y)>)>]" in r.stdout, r.stdout + r.stderr
  assert "back=[js<micropy(s7<lua(y)>)>]" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines(*linked)
def test_a_one_shot_guest_calls_persistent_guests(amk, tmp_path):
  r = run(amk, tmp_path, "oneshot.mk", [
    'one := $(lua print(amk.expand("$$(s7_via micropy,z)")))',
    "$(info oneshot=[$(one)])",
  ])
  assert "oneshot=[s7<micropy(z)>]" in r.stdout, r.stdout + r.stderr

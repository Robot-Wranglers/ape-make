"""Pins the guest's one call surface.

`amk.call` resolves by the cascade, a make function, the name under `amk.`, a macro, and
refuses a name two layers answer; `amk.fxn` and `amk.macro` take one layer; the async
forms answer the same text; the predicates answer in make and through the handle; a
missing handle attribute stands for what the cascade resolves.
"""

import pytest

from conftest import sh

engines = ["lua", "s7", "micropy", "js"]

PRELUDE = "\n".join([
  "greet = hi $(1)",
  "amk.shout = loud $(1)",
  "double = $(1)$(1)",
  "$(amk.fxn! twice, double)",
  "dual = macro $(1)",
  "amk.dual = under $(1)",
  "all:",
  "\t@true",
])

# One line each: the cascade's layers, the ambiguity, the explicit forms, their refusals, the fallback, the predicates, the async forms.
PROGRAMS = {
  "lua": "\n".join([
    "local function try(f, ...) local ok, e = pcall(f, ...) return e end",
    "print(amk.call('twice', 'ab'), amk.call('shout', 'x'), amk.call('greet', 'x'))",
    "print(try(amk.call, 'dual', 'x'))",
    "print(amk.fxn('twice', 'ab'), amk.macro('greet', 'x'))",
    "print(try(amk.fxn, 'greet', 'x'))",
    "print(try(amk.macro, 'twice', 'ab'))",
    "print(amk.shout('x'), amk.twice('ab'))",
    "print(amk['fxn?']('twice'), amk['macro?']('greet'), amk['goal?']('all'))",
    "print(amk.afxn('twice', 'ab').result(), amk.amacro('greet', 'x').result(), amk.acall('shout', 'x').result())",
  ]),
  "micropy": "\n".join([
    "import amk, asyncio",
    "def try_(f, *a):",
    "    try:",
    "        return f(*a)",
    "    except Exception as e:",
    "        return str(e)",
    "print(amk.call('twice', 'ab'), amk.call('shout', 'x'), amk.call('greet', 'x'))",
    "print(try_(amk.call, 'dual', 'x'))",
    "print(amk.fxn('twice', 'ab'), amk.macro('greet', 'x'))",
    "print(try_(amk.fxn, 'greet', 'x'))",
    "print(try_(amk.macro, 'twice', 'ab'))",
    "print(amk.shout('x'), amk.twice('ab'))",
    "print(getattr(amk, 'fxn?')('twice'), getattr(amk, 'macro?')('greet'), getattr(amk, 'goal?')('all'))",
    "async def main():",
    "    print(await amk.afxn('twice', 'ab'), await amk.amacro('greet', 'x'), await amk.acall('shout', 'x'))",
    "asyncio.run(main())",
  ]),
  "js": "\n".join([
    "const attempt = (f, ...a) => { try { return f(...a); } catch (e) { return e.message; } };",
    "print(amk.call('twice', 'ab'), amk.call('shout', 'x'), amk.call('greet', 'x'));",
    "print(attempt(amk.call, 'dual', 'x'));",
    "print(amk.fxn('twice', 'ab'), amk.macro('greet', 'x'));",
    "print(attempt(amk.fxn, 'greet', 'x'));",
    "print(attempt(amk.macro, 'twice', 'ab'));",
    "print(amk.shout('x'), amk.twice('ab'));",
    "print(amk['fxn?']('twice'), amk['macro?']('greet'), amk['goal?']('all'));",
    "print(await amk.afxn('twice', 'ab'), await amk.amacro('greet', 'x'), await amk.acall('shout', 'x'));",
  ]),
  "s7": "\n".join([
    "(define (attempt thunk) (catch #t thunk (lambda (type info) (apply format #f info))))",
    "(define (line . xs) (for-each (lambda (x) (display x) (display \" \")) xs) (newline))",
    "(line (amk-call \"twice\" \"ab\") (amk-call \"shout\" \"x\") (amk-call \"greet\" \"x\"))",
    "(line (attempt (lambda () (amk-call \"dual\" \"x\"))))",
    "(line (amk-fxn \"twice\" \"ab\") (amk-macro \"greet\" \"x\"))",
    "(line (attempt (lambda () (amk-fxn \"greet\" \"x\"))))",
    "(line (attempt (lambda () (amk-macro \"twice\" \"ab\"))))",
    "(line (amk-shout \"x\") (amk-twice \"ab\"))",
    "(line (amk-fxn? \"twice\") (amk-macro? \"greet\") (amk-goal? \"all\"))",
    "(line (amk-call-end (car (amk-afxn \"twice\" \"ab\"))) (amk-call-end (car (amk-amacro \"greet\" \"x\"))) (amk-call-end (car (amk-call-begin \"shout\" \"x\"))))",
  ]),
}


def run(amk, tmp_path, engine):
  mk = tmp_path / "surface.mk"
  mk.write_text("\n".join([PRELUDE, "define prog", PROGRAMS[engine], "endef", f"$(info $({engine}* prog))", ""]))
  r = sh(amk, ["-s", "-f", str(mk)], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  return [line.split() for line in r.stdout.splitlines() if line.strip()]


@pytest.mark.parametrize("engine", [pytest.param(e, marks=pytest.mark.engines(e), id=e) for e in engines])
def test_the_surface_resolves_refuses_and_answers_the_same_in_every_guest(amk, tmp_path, engine):
  lines = run(amk, tmp_path, engine)
  assert lines[0] == ["abab", "loud", "x", "hi", "x"], lines[0]
  assert "ambiguous" in " ".join(lines[1]) and "'dual'" in " ".join(lines[1]), lines[1]
  assert lines[2] == ["abab", "hi", "x"], lines[2]
  assert "no function named 'greet'" in " ".join(lines[3]), lines[3]
  assert "no macro named 'twice'" in " ".join(lines[4]), lines[4]
  assert lines[5] == ["loud", "x", "abab"], lines[5]
  assert lines[6] == ["1", "1", "1"], lines[6]
  assert lines[7] == ["abab", "hi", "x", "loud", "x"], lines[7]


def test_the_predicates_answer_in_make(amk, tmp_path):
  mk = tmp_path / "predicates.mk"
  mk.write_text("\n".join([
    PRELUDE,
    "$(info [$(amk.call? twice)][$(amk.fxn? twice)][$(amk.macro? greet)][$(amk.goal? all)]"
    "[$(amk.fxn? greet)][$(amk.macro? twice)][$(amk.goal? nope)][$(amk.call? dual)][$(amk.call? nope)])",
    "",
  ]))
  r = sh(amk, ["-s", "-f", str(mk)], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[1][1][1][1][][][][][]" in r.stdout, r.stdout


@pytest.mark.engines("lua")
def test_an_ambiguous_name_is_refused_with_both_layers_named(amk, tmp_path):
  mk = tmp_path / "ambiguous.mk"
  mk.write_text("\n".join([
    PRELUDE,
    "$(info [$(lua.exec local ok, e = pcall(amk.call, 'dual', 'x') print(e))])",
    "",
  ]))
  r = sh(amk, ["-s", "-f", str(mk)], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "'dual' is ambiguous" in r.stdout and "'amk.dual'" in r.stdout and "amk.fxn or amk.macro" in r.stdout, r.stdout

"""Pins the define decorator rewrite.

A column-0 `@name`, `@name(args)`, or `@name args` above a define is dropped, and one line
after the endef calls the twin macro `name_star` with the define's name and the arguments,
or errors naming the macro; a define closed by endef on the same line is split into the
block first. Pinned: the printed text, stacking, marks, the one-line define, what is left alone
including an at line no define follows, includes and evaluated text, and the disable knob.
"""

import pytest

from conftest import sh

call = "$(eval amk.decorator = {f}:{l}: @{n}{w})$(eval amk.decorator.deps = {d})$(eval amk.decorator.argc := {c}){e}$(eval amk.decorator.kws = {k})$(if $(filter-out undefined,$(origin {n}.__schema__)),$(amk.val.schema {s}, $({n}.__schema__)))$(if $(filter-out undefined,$(origin {n}_star)),$(if $(call {n}_star,{s}{a}),),$(error {f}:{l}: @{n}: no macro {n}_star))"


def at(els=(), opts=(), deps="", **k):
  pieces = "".join(f"$(eval amk.decorator.{i} = {v})$(eval amk.decorator.{i}.key = {key})" for i, (v, key) in enumerate(els, 1))
  pieces += "".join(f"$(eval amk.decorator.kw.{key} = {v})" for key, v in opts)
  return call.format(w=" " + k["a"][1:] if k["a"] else "", d=deps, c=len(els), e=pieces, k=" ".join(key for key, _ in opts), **k)


def pre(amk, tmp_path, text, name="in.mk"):
  mk = tmp_path / name
  mk.write_text(text)
  r = sh(amk, ["--preprocessor", str(mk)], cwd=tmp_path, timeout=60)
  return r, str(mk)


def test_the_at_line_moves_below_the_endef_as_a_twin_call(amk, tmp_path):
  r, f = pre(amk, tmp_path, "x := 1\n@lua.import\ndefine chunk\n  y = 2\nendef\nz := 3\n")
  assert r.returncode == 0, r.stderr
  assert r.stdout == "x := 1\ndefine chunk\n  y = 2\nendef\n" + at(n="lua.import", s="chunk", a="", f=f, l=2) + "\nz := 3\n"


def test_parens_and_the_space_form_give_the_same_call(amk, tmp_path):
  a, f = pre(amk, tmp_path, "@lua.import.target(hello, flags)\ndefine prog\nendef\n")
  b, _ = pre(amk, tmp_path, "@lua.import.target hello, flags\ndefine prog\nendef\n")
  assert a.returncode == 0 and b.returncode == 0, a.stderr + b.stderr
  assert "$(call lua.import.target_star,prog,hello, flags)" in a.stdout and "$(call lua.import.target_star,prog,hello, flags)" in b.stdout, a.stdout + b.stdout
  assert at(n="lua.import.target", s="prog", a=",hello, flags", f=f, l=1, els=[("hello", ""), ("flags", "")]) in a.stdout


@pytest.mark.parametrize("slash,long", [
  ("@fb.proc/lua (next > next numbers)", "@fb.proc (lua next > next numbers)"),
  ("@g1.actor/micropy {kind=goal restart=never}", "@g1.actor micropy {kind=goal restart=never}"),
  ("@shop.reflex/lua (order item=str)", "@shop.reflex lua order item=str"),
  ("@g1.actor/s7", "@g1.actor s7"),
])
def test_a_slash_engine_is_the_first_argument(amk, tmp_path, slash, long):
  a, _ = pre(amk, tmp_path, slash + "\ndefine d\nendef\n")
  b, _ = pre(amk, tmp_path, long + "\ndefine d\nendef\n")
  assert a.returncode == 0 and b.returncode == 0, a.stderr + b.stderr
  assert a.stdout == b.stdout, a.stdout + b.stdout


def test_the_arguments_are_parsed_into_elements_keys_and_prerequisites(amk, tmp_path):
  r, f = pre(amk, tmp_path, "@shop.reflex lua (refund \"big order\" item=str) : first second\ndefine h\nendef\n")
  assert r.returncode == 0, r.stderr
  assert at(n="shop.reflex", s="h", a=",lua (refund \"big order\" item=str) : first second", f=f, l=1,
            els=[("lua", ""), ("refund", ""), ("big order", ""), ("str", "item")], deps="first second") in r.stdout


def test_a_macro_reads_the_parsed_pieces(amk, tmp_path):
  mk = tmp_path / "pieces.mk"
  mk.write_text("\n".join([
    "probe_star = $(info [$(amk.decorator.argc)] [$(amk.decorator.2)] [$(amk.decorator.3.key)] [$(amk.decorator.kw.opt)] [$(amk.decorator.kws)] [$(amk.decorator.deps)])",
    "@probe --flag (one 'two words' item=str){opt=yes}",
    "define h",
    "endef",
    "deps_star = $(info [$(amk.decorator.argc)] [$(amk.decorator.deps)])",
    "@deps: dep",
    "define g",
    "endef",
    "all:",
    "\ttrue",
    "",
  ]))
  r = sh(amk, ["-s", "-f", str(mk)], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.splitlines() == ["[4] [one] [] [yes] [opt] []", "[0] [dep]"], r.stdout + r.stderr


@pytest.mark.parametrize("at, error", [
  ("@x (a) (b)", "one group of each kind"),
  ("@x {flag}", "an option in braces is key=value, not flag"),
  ("@x (a", "an unterminated group"),
  ("@x ({a})", "a group does not nest"),
])
def test_a_malformed_argument_list_is_refused(amk, tmp_path, at, error):
  r, f = pre(amk, tmp_path, f"{at}\ndefine d\nendef\n")
  assert r.returncode == 76, r.stderr
  assert f"amk (preprocess) error: {f}:1: @x: {error}" in r.stderr, r.stderr


def test_the_amk_target_line_becomes_a_rule_in_place(amk, tmp_path):
  r, f = pre(amk, tmp_path, "@amk.target{join=;} : first\ndefine report\n  # a comment\n  echo one\n  echo two\nendef\n")
  assert r.returncode == 0, r.stderr
  assert r.stdout.splitlines() == [
    "define report", "  # a comment", "  echo one", "  echo two", "endef",
    "amk.goal := $(.DEFAULT_GOAL)", ".PHONY: report", "report: first",
    "\t$(if $(filter-out undefined,$(origin report.preamble)),$(report.preamble) ;) \\",
    "\techo one ; \\", "\techo two", ".DEFAULT_GOAL := $(amk.goal)",
  ], r.stdout


def test_a_space_style_amk_line_is_a_rule_and_calls_its_twin(amk, tmp_path):
  r, f = pre(amk, tmp_path, "@shop.amk: first\ndefine report\n  echo one\nendef\n")
  assert r.returncode == 0, r.stderr
  assert at(n="shop.amk", s="report", a=",: first", f=f, l=1, deps="first") in r.stdout
  assert "report: first" in r.stdout.splitlines() and "\techo one" in r.stdout.splitlines(), r.stdout


def test_stacked_lines_apply_nearest_first(amk, tmp_path):
  r, f = pre(amk, tmp_path, "@outer\n@inner(1)\ndefine d\nendef\n")
  assert r.returncode == 0, r.stderr
  lines = r.stdout.splitlines()
  assert lines[:2] == ["define d", "endef"]
  assert lines[2] == at(n="inner", s="d", a=",1", f=f, l=2, els=[("1", "")])
  assert lines[3] == at(n="outer", s="d", a="", f=f, l=1)


def test_the_postfix_mark_is_accepted_and_other_kinds_refused(amk, tmp_path):
  ok, f = pre(amk, tmp_path, "@lua.import ::: postfix\ndefine d\nendef\n")
  assert ok.returncode == 0, ok.stderr
  assert at(n="lua.import", s="d", a="", f=f, l=1) in ok.stdout
  bad, f = pre(amk, tmp_path, "@lua.import(x) ::: around\ndefine d\nendef\n")
  assert bad.returncode == 76, bad.stderr
  assert f"amk (preprocess) error: {f}:1: @lua.import ::: around: a define decorator takes only postfix" in bad.stderr, bad.stderr


def test_a_one_line_define_becomes_the_block(amk, tmp_path):
  r, _ = pre(amk, tmp_path, "define noisy {} endef\nexport define n := a b endef  \ndefine empty endef\nx := 1\n")
  assert r.returncode == 0, r.stderr
  assert r.stdout == "define noisy\n{}\nendef\nexport define n :=\na b\nendef\ndefine empty\nendef\nx := 1\n"


def test_a_one_line_define_under_an_at_line_calls_its_twin(amk, tmp_path):
  r, f = pre(amk, tmp_path, "@actor.group\ndefine noisy { \"backend\": \"s7\" } endef\n")
  assert r.returncode == 0, r.stderr
  assert r.stdout == "define noisy\n{ \"backend\": \"s7\" }\nendef\n" + at(n="actor.group", s="noisy", a="", f=f, l=1) + "\n"


def test_a_one_line_define_inside_a_body_keeps_the_nesting(amk, tmp_path):
  r, _ = pre(amk, tmp_path, "@lua.import\ndefine outer\ndefine inner x endef\n  y\nendef\n")
  assert r.returncode == 0, r.stderr
  assert r.stdout.splitlines()[:6] == ["define outer", "define inner", "x", "endef", "  y", "endef"], r.stdout


def test_a_define_line_without_the_closing_word_is_left_alone(amk, tmp_path):
  text = "define a =\nendef\ndefine b # note\nendef\ndefine c\nendef\ndefine d endef # late\nendef\n"
  r, _ = pre(amk, tmp_path, text)
  assert r.returncode == 0, r.stderr
  assert r.stdout == text


@pytest.mark.engines("lua")
def test_a_one_line_define_is_a_variable_make_reads(amk, tmp_path):
  mk = tmp_path / "main.mk"
  mk.write_text("define greeting hello world endef\n$(info [$(greeting)])\nall:\n\ttrue\n")
  r = sh(amk, ["-s", "-f", str(mk)], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[hello world]" in r.stdout, r.stdout


def test_an_assignment_and_a_body_line_are_left_alone(amk, tmp_path):
  text = "@name := 1\n@other = 2\ndefine py\n@decorator\ndef f(): pass\nendef\n"
  r, _ = pre(amk, tmp_path, text)
  assert r.returncode == 0, r.stderr
  assert r.stdout == text


def test_an_at_line_with_no_define_after_it_is_left_alone(amk, tmp_path):
  text = "\n@log(hi)\n@retry ::: around\n\n# a note\nall:\n\ttrue\n@lua.import\n"
  r, _ = pre(amk, tmp_path, text)
  assert r.returncode == 0, r.stderr
  assert r.stdout == text


def test_a_text_with_no_at_line_is_printed_as_it_is(amk, tmp_path):
  text = "a := 1\nall:\n\t@echo $(a)\n"
  r, _ = pre(amk, tmp_path, text)
  assert r.returncode == 0, r.stderr
  assert r.stdout == text


@pytest.mark.engines("lua")
def test_an_included_makefile_and_evaluated_text_are_rewritten(amk, tmp_path):
  (tmp_path / "inc.mk").write_text("@lua.import\ndefine chunk\nx = 41 + 1\nendef\n")
  mk = tmp_path / "main.mk"
  mk.write_text("\n".join([
    "include inc.mk",
    "define later",
    "@lua.import",
    "define chunk2",
    "y = x + 1",
    "endef",
    "endef",
    "$(eval $(later))",
    "$(info [$(x)] [$(y)])",
    "all:",
    "\ttrue",
    "",
  ]))
  r = sh(amk, ["-s", "-f", str(mk)], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[42] [43]" in r.stdout, r.stdout


def test_an_included_makefile_has_its_target_decorators_rewritten(amk, tmp_path):
  (tmp_path / "inc.mk").write_text("log = echo [$(1)]\n@log(hi)\nall:\n\techo [body]\n")
  mk = tmp_path / "main.mk"
  mk.write_text("include inc.mk\n")
  r = sh(amk, ["-s", "-f", str(mk)], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.splitlines() == ["[hi]", "[body]"], r.stdout


def test_an_included_makefile_has_its_one_line_defines_rewritten(amk, tmp_path):
  (tmp_path / "inc.mk").write_text("define greeting hello world endef\n")
  mk = tmp_path / "main.mk"
  mk.write_text("include inc.mk\n$(info [$(greeting)])\nall:\n\ttrue\n")
  r = sh(amk, ["-s", "-f", str(mk)], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "[hello world]" in r.stdout, r.stdout


@pytest.mark.engines("lua")
def test_the_disable_knob_hands_the_line_to_make(amk, tmp_path):
  mk = tmp_path / "main.mk"
  mk.write_text("@lua.import\ndefine chunk\nx = 1\nendef\nall:\n\ttrue\n")
  r = sh(amk, ["-s", "-f", str(mk)], cwd=tmp_path, timeout=120, env={"AMK_DISABLE_PREPROCESS": "1"})
  assert r.returncode != 0
  assert "missing separator" in r.stderr, r.stderr
  r = sh(amk, ["-s", "-f", str(mk)], cwd=tmp_path, timeout=120, env={"AMK_DISABLE_PREPROCESS": "0"})
  assert r.returncode == 0, r.stdout + r.stderr

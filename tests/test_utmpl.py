"""Pins the payload's utmpl library: a template in a define is a target that renders json with the bundled utemplate.

Pinned: the target renders stdin, name/var renders the json in var, the function form renders
at parse time, an object's keys are the template's names unless the template has its own args
line, a dollar in a template is literal, the at line leaves the default goal alone, a bad
input or a template that raises stops make, and parallel renders keep their lines whole.
"""

import pytest

from conftest import sh

pytestmark = pytest.mark.engines("micropy")

release = [
  "$(amk.include utmpl)",
  "@utmpl.import.target",
  "define release.md",
  "{{project}} {{version}}",
  "{% for e in engines %}",
  "- {{e}}",
  "{% endfor %}",
  "endef",
  'release.data = {"project": "amk", "version": "0.1", "engines": ["jq", "micropy"]}',
]


def run(amk, tmp_path, lines, args=(), stdin=None):
  (tmp_path / "t.mk").write_text("\n".join(lines + [""]))
  return sh(amk, ["-s", "-f", "t.mk", *args], cwd=tmp_path, timeout=120, stdin=stdin)


def ok(r):
  assert r.returncode == 0, r.stdout + r.stderr
  return r.stdout


def test_an_include_splices_a_template_file_by_path(amk, tmp_path):
  (tmp_path / "part.tpl").write_text("part {{x}}\n")
  lines = [
    "$(amk.include utmpl)",
    'd = {"x": 1}',
    "@utmpl d",
    "define page",
    "  before",
    '  {% include "part.tpl" %}',
    "  after",
    "endef",
    "$(info [$(page)])",
    "all:",
    "\ttrue",
  ]
  assert ok(run(amk, tmp_path, lines)) == "[before\npart 1\nafter]\n"
  lines[5] = '  {% include "missing.tpl" %}'
  r = run(amk, tmp_path, lines)
  assert r.returncode != 0, r.stdout
  assert "utmpl: page includes a file it cannot read" in r.stderr, r.stderr


def test_a_goal_word_takes_a_recipe_targets_output(amk, tmp_path):
  lines = [
    "$(amk.include utmpl)",
    "downstream1:",
    "\techo arbitrary data from any target",
    "@utmpl.target name=world d1=>>downstream1<<",
    "define render",
    "  hello {{name}}: {{d1}}",
    "endef",
  ]
  assert ok(run(amk, tmp_path, lines, ("render",), stdin="")).strip() == "hello world: arbitrary data from any target"


def test_name_slash_var_renders_the_json_in_var(amk, tmp_path):
  assert ok(run(amk, tmp_path, release, ["release.md/release.data"])) == "amk 0.1\n- jq\n- micropy\n"


def test_the_target_renders_stdin(amk, tmp_path):
  out = ok(run(amk, tmp_path, release, ["release.md"], stdin='{"project": "p", "version": "2", "engines": []}'))
  assert out == "p 2\n"


def test_the_function_renders_at_parse_time(amk, tmp_path):
  out = ok(run(amk, tmp_path, release + ["$(info [$(utmpl.render release.md, release.data)])", "all:", "\ttrue"]))
  assert out == "[amk 0.1\n- jq\n- micropy\n]\n"


def test_the_function_trims_its_names(amk, tmp_path):
  out = ok(run(amk, tmp_path, release + ["$(info [$(utmpl.render release.md, release.data )])", "all:", "\ttrue"]))
  assert out == "[amk 0.1\n- jq\n- micropy\n]\n"


def test_a_template_with_its_own_args_takes_the_data_whole(amk, tmp_path):
  lines = [
    "$(amk.include utmpl)",
    "@utmpl.import.target",
    "define t",
    "{% args d %}",
    '{{d["a"]}}/{{len(d)}}',
    "endef",
    'obj = {"a": "x", "b": 1}',
    "arr = [1, 2, 3]",
    "@utmpl.import.target",
    "define n",
    "{% args xs %}",
    "{{len(xs)}}",
    "endef",
  ]
  assert ok(run(amk, tmp_path, lines, ["t/obj"])) == "x/2\n"
  assert ok(run(amk, tmp_path, lines, ["n/arr"])) == "3\n"


def test_a_dollar_in_a_template_is_literal(amk, tmp_path):
  lines = [
    "$(amk.include utmpl)",
    "@utmpl.import.target",
    "define t",
    "{{a}} costs $5, not $(shell touch ran)",
    "endef",
    'obj = {"a": "x"}',
  ]
  assert ok(run(amk, tmp_path, lines, ["t/obj"])) == "x costs $5, not $(shell touch ran)\n"
  assert not (tmp_path / "ran").exists()


def test_the_at_line_leaves_the_default_goal_alone(amk, tmp_path):
  assert ok(run(amk, tmp_path, release + ["all:", "\techo all ran"])) == "all ran\n"


@pytest.mark.parametrize("args,stdin,message", [
  (["release.md/nope"], None, "utmpl: no variable named nope holds the data"),
  (["release.md"], "not json", "utmpl: stdin is not json"),
  (["release.md/bad"], None, "utmpl: release.md did not render: TypeError"),
], ids=["a missing variable", "stdin that is not json", "a template that raises"])
def test_a_bad_input_stops_make(amk, tmp_path, args, stdin, message):
  r = run(amk, tmp_path, release + ['bad = {"project": 1, "version": 2, "engines": 3}'], args, stdin)
  assert r.returncode != 0, r.stdout
  assert message in r.stderr, r.stderr


scores = ['scores = {"who": "world", "n": 3}']


def show(name):
  return [f"$(info [{name}])", "all:", "\ttrue"]


def test_the_inline_form_renders_text_with_the_data_in_a_variable(amk, tmp_path):
  out = ok(run(amk, tmp_path, ["$(amk.include utmpl)", *scores, *show("$(utmpl hi {{who}}, {{n}}, scores)")]))
  assert out == "[hi world, 3]\n"


def test_the_decorator_renders_the_define_into_its_own_name(amk, tmp_path):
  lines = ["$(amk.include utmpl)", *scores, "@utmpl scores", "define t", "{{who}} {{n}}", "endef"]
  assert ok(run(amk, tmp_path, lines + show("$(t)"))) == "[world 3]\n"


def test_the_decorator_renders_into_a_named_variable(amk, tmp_path):
  lines = ["$(amk.include utmpl)", *scores, "@utmpl scores {into=out}", "define t", "{{who}}", "endef"]
  assert ok(run(amk, tmp_path, lines + show("$(out)"))) == "[world]\n"


@pytest.mark.parametrize("words,out", [
  ("who=word n=7", "[word/7]"),
  ("scores n=9", "[world/9]"),
  ("n=9 scores", "[world/9]"),
  ("scores more", "[there/3]"),
], ids=["name=value words", "a word over data", "words win in any order", "data merges left to right"])
def test_the_decorator_takes_data_and_words(amk, tmp_path, words, out):
  lines = ["$(amk.include utmpl)", *scores, 'more = {"who": "there"}', f"@utmpl {words}", "define t", "{{who}}/{{n}}", "endef"]
  assert ok(run(amk, tmp_path, lines + show("$(t)"))) == out + "\n"


def test_import_makes_a_function_that_renders(amk, tmp_path):
  lines = ["$(amk.include utmpl)", *scores, "@utmpl.import", "define t", "* {{who}}", "endef"]
  assert ok(run(amk, tmp_path, lines + show("$(t scores)"))) == "[* world]\n"


def test_an_indented_template_is_dedented(amk, tmp_path):
  lines = ["$(amk.include utmpl)", *scores, "@utmpl scores", "define t", "    - {{who}}", "      x{{n}}", "endef"]
  assert ok(run(amk, tmp_path, lines + show("$(t)"))) == "[- world\n  x3]\n"


@pytest.mark.parametrize("decorator,message", [
  ("@utmpl scores", "utmpl: t did not render: NameError"),
  ("@utmpl who=word", "utmpl: t did not render: NameError"),
  ("@utmpl nope", "utmpl: no variable named nope holds the data"),
  ("@utmpl junk", "utmpl: junk is not json"),
  ("@utmpl arr n=1", "utmpl: arr holds no json object to merge"),
  ("@utmpl.argv who=word", "stacked engine utmpl does not define @utmpl.argv"),
], ids=["a name the data lacks", "a name the words lack", "a missing variable", "data that is not json",
  "a list to merge", "argv is gone"])
def test_a_bad_in_place_render_stops_make(amk, tmp_path, decorator, message):
  lines = ["$(amk.include utmpl)", *scores, "junk = not json", "arr = [1]", decorator, "define t", "{{who}} {{n}} {{x}}", "endef"]
  r = run(amk, tmp_path, lines + show("$(t)"))
  assert r.returncode != 0, r.stdout
  assert message in r.stderr, r.stderr


@pytest.mark.parametrize("lines,message", [
  (["$(utmpl.ns a, exec, b)"], "stacked engine utmpl does not define utmpl.ns"),
  (["$(utmpl.exec b)"], "stacked engine utmpl does not define utmpl.exec"),
  (["@utmpl.exec", "define t", "endef"], "stacked engine utmpl does not define @utmpl.exec"),
], ids=["ns", "exec", "the exec decorator"])
def test_a_form_utmpl_lacks_stops_make(amk, tmp_path, lines, message):
  r = run(amk, tmp_path, ["$(amk.include utmpl)", *lines, "all:", "\ttrue"])
  assert r.returncode != 0, r.stdout
  assert message in r.stderr, r.stderr


target_words = [
  "$(amk.include utmpl)",
  *scores,
  "define ver.py",
  r"""import sys; sys.stdout.write(r'{"q": "a\"\"b", "e": ""}')""",
  "endef",
  "$(micropy.import.target ver,$(value ver.py))",
]


@pytest.mark.parametrize("decorator,args,out", [
  ("@utmpl.target scores n=9", ["t"], "world/9"),
  ("@utmpl.target scores n=9", ["t/more"], "there/9"),
  ("@utmpl.target who=word n=1", ["t"], "word/1"),
  ("@utmpl.target scores n=>>ver<<", ["t"], r'world/{"q": "a\"\"b", "e": ""}'),
], ids=["words over data", "name/var over the decorator's data", "words alone read no stdin", "a goal's value as a word"])
def test_target_words(amk, tmp_path, decorator, args, out):
  lines = [*target_words, 'more = {"who": "there"}', decorator, "define t", "{{who}}/{{n}}", "endef"]
  assert ok(run(amk, tmp_path, lines, args, stdin="")) == out + "\n"


def test_a_goal_word_on_the_in_place_form_stops_make(amk, tmp_path):
  lines = ["$(amk.include utmpl)", "@utmpl who=>>ver<<", "define t", "{{who}}", "endef"]
  r = run(amk, tmp_path, lines + show("$(t)"))
  assert r.returncode != 0, r.stdout
  assert "who=>>ver<< needs @utmpl.target" in r.stderr, r.stderr


def test_parallel_renders_keep_their_lines_whole(amk, tmp_path):
  lines = [
    "$(amk.include utmpl)",
    "@utmpl.import.target",
    "define row",
    "{% for i in range(n) %}",
    "{{tag}}-{{i}}",
    "{% endfor %}",
    "endef",
    *[f'd{t} = {{"tag": "{t}", "n": 400}}' for t in "abcd"],
    "all: " + " ".join(f"row/d{t}" for t in "abcd"),
  ]
  out = ok(run(amk, tmp_path, lines, ["-j4"])).splitlines()
  assert sorted(out) == sorted(f"{t}-{i}" for t in "abcd" for i in range(400))
  assert len([i for i in range(1, len(out)) if out[i][0] != out[i - 1][0]]) == 3

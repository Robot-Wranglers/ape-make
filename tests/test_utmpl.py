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
  "include /zip/lib/utmpl.mk",
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


def test_name_slash_var_renders_the_json_in_var(amk, tmp_path):
  assert ok(run(amk, tmp_path, release, ["release.md/release.data"])) == "amk 0.1\n- jq\n- micropy\n"


def test_the_target_renders_stdin(amk, tmp_path):
  out = ok(run(amk, tmp_path, release, ["release.md"], stdin='{"project": "p", "version": "2", "engines": []}'))
  assert out == "p 2\n"


def test_the_function_renders_at_parse_time(amk, tmp_path):
  out = ok(run(amk, tmp_path, release + ["$(info [$(utmpl.render release.md,release.data)])", "all:", "\ttrue"]))
  assert out == "[amk 0.1\n- jq\n- micropy\n]\n"


def test_a_template_with_its_own_args_takes_the_data_whole(amk, tmp_path):
  lines = [
    "include /zip/lib/utmpl.mk",
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
    "include /zip/lib/utmpl.mk",
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


def test_parallel_renders_keep_their_lines_whole(amk, tmp_path):
  lines = [
    "include /zip/lib/utmpl.mk",
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

"""Pins the store's import.

`$(jq.import name,text)` makes the store namespace name, handles included, and loads the
text as its value; its star form takes a variable's name and value, so `@jq.import` above a
define gives the define's name a store. Pinned: the at line, the plain form, a second import
replacing the value, the handles still writing, and the fatal cases: a star argument naming
no variable, a call with no text, and a text that does not load.
"""

import pytest

from conftest import sh


def _run(amk, tmp_path, lines, goal="all"):
  mk = tmp_path / "import.mk"
  mk.write_text("\n".join(lines) + "\n")
  return sh(amk, ["-s", "-f", str(mk), goal], timeout=120)


@pytest.mark.engines("jq")
def test_at_line_makes_a_store(amk, tmp_path):
  r = _run(amk, tmp_path, [
    "@jq.import",
    "define cfg",
    '  {"name": "a b", "tags": [1, 2]}',
    "endef",
    "all:",
    "\t@echo \"$(cfg.get -r .name) $(cfg.get .tags | length)\"",
  ])
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "a b 2", r.stdout + r.stderr


@pytest.mark.engines("jq")
def test_plain_form_and_handles_write(amk, tmp_path):
  r = _run(amk, tmp_path, [
    "$(jq.import stack,[1, 2])",
    "top := $(stack.update .[:-1], .[-1])",
    "all:",
    "\t@echo \"$(top) $(stack.get length)\"",
  ])
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "2 1", r.stdout + r.stderr


@pytest.mark.engines("jq")
def test_second_import_replaces_the_value(amk, tmp_path):
  r = _run(amk, tmp_path, [
    "$(jq.import box,[1, 2, 3])",
    "$(jq.import box,[9])",
    "all:",
    "\t@echo \"$(box.get length)\"",
  ])
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip() == "1", r.stdout + r.stderr


@pytest.mark.engines("jq")
@pytest.mark.parametrize("line, words", [
  ("$(jq.import* missing)", "missing names no variable"),
  ("$(jq.import lonely)", "no text"),
  ("$(jq.import bad,{not json)", "did not load"),
])
def test_fatal_cases(amk, tmp_path, line, words):
  r = _run(amk, tmp_path, [line, "all: ; @echo reached"])
  assert r.returncode != 0, r.stdout + r.stderr
  assert "reached" not in r.stdout, r.stdout + r.stderr
  assert words in r.stderr, r.stdout + r.stderr

"""Pins `$(amk.args [start:stop])`: the innermost call's arguments as a json array.

Indexes are make's own, so `2` is `$(2)` and the name in `$(0)` never appears; the stop
is exclusive, a negative counts from the end, and a slice past the arguments clamps.
Pinned are each slice form, an argument with spaces and quotes, a nested call that has
fewer arguments than its caller, the empty array outside any call, a refused spec, and a
guest's amk.call reaching a macro with every argument it sent.
"""

import json
import re

import pytest

from conftest import sh


def run(amk, tmp_path, text):
  mk = tmp_path / "args.mk"
  mk.write_text(text + "\nall:\n\ttrue\n")
  return sh(amk, ["-s", "-f", str(mk)], timeout=120)


def shown(r):
  return {k: json.loads(v) for k, v in re.findall(r"^(\w+)=(.*)$", r.stdout, re.M)}


def test_slices(amk, tmp_path):
  specs = {"all": "", "colon": ":", "rest": "2:", "mid": "2:4", "last": "-1:", "head": ":-1", "past": "9:", "none": "3:2"}
  text = "\n".join(f"{k} = $(amk.args {s})\n$(info {k}=$(call {k},a,b c,d))" for k, s in specs.items())
  r = run(amk, tmp_path, text)
  assert r.returncode == 0, r.stdout + r.stderr
  assert shown(r) == {
    "all": ["a", "b c", "d"],
    "colon": ["a", "b c", "d"],
    "rest": ["b c", "d"],
    "mid": ["b c", "d"],
    "last": ["d"],
    "head": ["a", "b c"],
    "past": [],
    "none": [],
  }, r.stdout


def test_quotes_and_backslashes_escape(amk, tmp_path):
  r = run(amk, tmp_path, "f = $(amk.args 1:)\n$(info got=$(call f,say \"hi\",a\\b))")
  assert r.returncode == 0, r.stdout + r.stderr
  assert shown(r) == {"got": ['say "hi"', "a\\b"]}, r.stdout


def test_nested_call_sees_only_its_own(amk, tmp_path):
  text = "\n".join([
    "inner = $(amk.args)",
    "outer = $(amk.args)|$(call inner,x)|$(amk.args)",
    "$(info got=[$(call outer,a,b,c)])",
  ])
  r = run(amk, tmp_path, text)
  assert r.returncode == 0, r.stdout + r.stderr
  assert '["a","b","c"]|["x"]|["a","b","c"]' in r.stdout, r.stdout


def test_outside_any_call_is_empty(amk, tmp_path):
  r = run(amk, tmp_path, "$(info got=$(amk.args))\n$(info rest=$(amk.args 2:))")
  assert r.returncode == 0, r.stdout + r.stderr
  assert shown(r) == {"got": [], "rest": []}, r.stdout


@pytest.mark.parametrize("spec", ["2", "a:", "1:b", "1:2:3"])
def test_a_bad_slice_is_fatal(amk, tmp_path, spec):
  r = run(amk, tmp_path, f"f = $(amk.args {spec})\n$(info $(call f,a,b))")
  assert r.returncode != 0, r.stdout
  assert "is not a slice" in r.stderr, r.stderr


@pytest.mark.engines("lua")
def test_a_guest_call_carries_every_argument(amk, tmp_path):
  text = "\n".join([
    "f = $(amk.args 2:)",
    "$(info got=$(lua.exec print(amk.call(\"f\", \"verb\", \"a\", \"b c\", \"7\", \"d\", \"e\", \"f\", \"g\", \"h\", \"i\", \"j\"))))",
  ])
  r = run(amk, tmp_path, text)
  assert r.returncode == 0, r.stdout + r.stderr
  assert shown(r) == {"got": ["a", "b c", "7", "d", "e", "f", "g", "h", "i", "j"]}, r.stdout

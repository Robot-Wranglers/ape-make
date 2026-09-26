"""Pins the jq store.

`$(jq.persistent op name prog[,input])` runs a jq program in the make process over one named
JSON value the process holds, with no fork. Pinned: update stores and get reads back, take splits
an output into the new value and the rest, names stay distinct and a missing one is null,
load and dump round-trip a file, a bad program leaves the value alone, and a zygote serves
each request from the store the parse left.
"""

import json

import pytest

from conftest import sh

parse_time = "\n".join([
  "three := [1,2,3]",
  "take.prog := [.[:-1], .[-1]]",
  "bound.prog := --arg w x --argjson n 10 -r [.[0] + $$n, $$w] | join(\" \")",
  "rest.prog := -r [\"a\", \"b\", \"c\"] | (., .[0], .[1])",
  "one := $(jq.persistent update S . // [] + [1])",
  "len := $(jq.persistent get S length)",
  "seeded := $(jq.persistent update S $(three))",
  "top := $(jq.persistent take S $(take.prog))",
  "left := $(jq.persistent get S .)",
  "a := $(jq.persistent update A {\"k\": 1})",
  "b := $(jq.persistent update B {\"k\": 2})",
  "ak := $(jq.persistent get A .k)",
  "bk := $(jq.persistent get B .k)",
  "c := $(jq.persistent get C .)",
  "bad := $(jq.persistent update S .[)",
  "bad.status := $(.SHELLSTATUS)",
  "after := $(jq.persistent get S .)",
  "bound := $(jq.persistent get S $(bound.prog))",
  "many := $(jq.persistent get S .[])",
  "rest := $(jq.persistent update S $(rest.prog))",
  "$(info len=[$(len)] top=[$(top)] left=[$(left)] ak=[$(ak)] bk=[$(bk)] c=[$(c)] bad=[$(bad)] bad.status=[$(bad.status)] after=[$(after)] bound=[$(bound)] many=[$(many)] rest=[$(rest)])",
  "all:",
  "\ttrue",
  "",
])

files = "\n".join([
  "loaded := $(jq.persistent load D $(src))",
  "dumped := $(jq.persistent dump D)",
  "missing := $(jq.persistent load E $(src).absent)",
  "missing.status := $(.SHELLSTATUS)",
  "inline := $(jq.persistent load F,{\"x\": [1, 2]})",
  "$(info dumped=[$(dumped)] missing=[$(missing.status)] inline=[$(jq.persistent dump F)])",
  "all:",
  "\ttrue",
  "",
])

served = "\n".join([
  "seed := $(jq.persistent update N 7)",
  "show:",
  "\t@echo n=$(jq.persistent update N . + 1 | (., .))",
  "",
])


@pytest.mark.engines("jq")
def test_a_store_outlives_a_call(amk, tmp_path):
  mk = tmp_path / "store.mk"
  mk.write_text(parse_time)
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "len=[1]" in r.stdout, r.stdout
  assert "top=[3]" in r.stdout, r.stdout
  assert "left=[[1,2]]" in r.stdout, r.stdout
  assert "ak=[1] bk=[2] c=[null]" in r.stdout, r.stdout
  assert "bad=[] bad.status=[3]" in r.stdout and "compile error" in r.stderr, r.stdout + r.stderr
  assert "after=[[1,2]]" in r.stdout, r.stdout
  assert "bound=[11 x]" in r.stdout, r.stdout
  assert "many=[1\n2]" in r.stdout, r.stdout
  assert "rest=[a\nb]" in r.stdout, r.stdout


@pytest.mark.engines("jq")
def test_load_and_dump_round_trip_a_file(amk, tmp_path):
  src = tmp_path / "d.json"
  doc = {"name": "cmk", "tags": ["a", "b"], "n": 3, "nested": {"ok": True, "none": None}}
  src.write_text(json.dumps(doc, indent=2))
  mk = tmp_path / "files.mk"
  mk.write_text(files)
  r = sh(amk, ["-s", "-f", str(mk), f"src={src}"], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  line = next(ln for ln in r.stdout.splitlines() if ln.startswith("dumped=["))
  dumped = line[len("dumped=["):line.index("] missing=[")]
  assert json.loads(dumped) == doc, dumped
  assert "missing=[2]" in r.stdout and "cannot read" in r.stderr, r.stdout + r.stderr
  assert 'inline=[{"x":[1,2]}]' in r.stdout, r.stdout


@pytest.mark.engines("jq")
def test_each_request_starts_from_the_parse(amk, tmp_path, zygote):
  mk = tmp_path / "served.mk"
  mk.write_text(served)
  sock = zygote(["-f", str(mk)], cwd=tmp_path)
  for _ in range(2):
    r = sh(amk, ["--client", str(sock), "show"], cwd=tmp_path, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.strip() == "n=8", r.stdout + r.stderr

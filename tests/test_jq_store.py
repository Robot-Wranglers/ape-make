"""Pins the jq store.

A jq namespace is one JSON value the make process holds; `get`, `update` and `load` run over
it with no fork, in `main` through `$(jq.<op> ...)` and in a created one through its handles.
The pins are that update keeps its first output and returns the rest, so a stream pops, that
names stay apart and a new one is null, that load takes a file's text, that a bad program
leaves the value alone with jq's status, and that a zygote serves each request from the parse.
"""

import json

import pytest

from conftest import sh

parse_time = "\n".join([
  "three := [1,2,3]",
  "pop.prog := .[:-1], .[-1]",
  "bound.prog := --arg w x --argjson n 10 -r [.[0] + $$n, $$w] | join(\" \")",
  "rest.prog := -r [\"a\", \"b\", \"c\"] | (., .[0], .[1])",
  "$(jq.ns S, create)",
  "$(jq.ns A, create)",
  "$(jq.ns B, create)",
  "$(jq.ns C, create)",
  "one := $(S.update . // [] + [1])",
  "len := $(S.get length)",
  "seeded := $(S.update $(three))",
  "top := $(S.update* pop.prog)",
  "left := $(S.get .)",
  "a := $(A.update {\"k\": 1})",
  "b := $(B.update {\"k\": 2})",
  "ak := $(A.get .k)",
  "bk := $(B.get .k)",
  "c := $(C.get .)",
  "main := $(jq.get .)",
  "bad := $(S.update .[)",
  "bad.status := $(.SHELLSTATUS)",
  "after := $(S.get .)",
  "bound := $(S.get* bound.prog)",
  "many := $(S.get .[])",
  "rest := $(S.update* rest.prog)",
  "$(info len=[$(len)] top=[$(top)] left=[$(left)] ak=[$(ak)] bk=[$(bk)] c=[$(c)] main=[$(main)] bad=[$(bad)] bad.status=[$(bad.status)] after=[$(after)] bound=[$(bound)] many=[$(many)] rest=[$(rest)])",
  "all:",
  "\ttrue",
  "",
])

files = "\n".join([
  "$(jq.ns D, create)",
  "$(jq.ns F, create)",
  "loaded := $(D.load $(file <$(src)))",
  "dumped := $(D.get .)",
  "bad := $(F.load {\"x\": [1, 2)",
  "bad.status := $(.SHELLSTATUS)",
  "inline := $(F.load {\"x\": [1, 2]})",
  "$(info dumped=[$(dumped)] bad=[$(bad.status)] inline=[$(F.get .)])",
  "all:",
  "\ttrue",
  "",
])

served = "\n".join([
  "$(jq.ns N, create)",
  "seed := $(N.update 7)",
  "show:",
  "\t@echo n=$(N.update . + 1 | (., .))",
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
  assert "ak=[1] bk=[2] c=[null] main=[null]" in r.stdout, r.stdout
  assert "bad=[] bad.status=[3]" in r.stdout and "compile error" in r.stderr, r.stdout + r.stderr
  assert "after=[[1,2]]" in r.stdout, r.stdout
  assert "bound=[11 x]" in r.stdout, r.stdout
  assert "many=[1\n2]" in r.stdout, r.stdout
  assert "rest=[a\nb]" in r.stdout, r.stdout


@pytest.mark.engines("jq")
def test_load_takes_a_files_text_and_get_gives_it_back(amk, tmp_path):
  src = tmp_path / "d.json"
  doc = {"name": "cmk", "tags": ["a", "b"], "n": 3, "nested": {"ok": True, "none": None}}
  src.write_text(json.dumps(doc, indent=2))
  mk = tmp_path / "files.mk"
  mk.write_text(files)
  r = sh(amk, ["-s", "-f", str(mk), f"src={src}"], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  line = next(ln for ln in r.stdout.splitlines() if ln.startswith("dumped=["))
  dumped = line[len("dumped=["):line.index("] bad=[")]
  assert json.loads(dumped) == doc, dumped
  assert "bad=[2]" in r.stdout and "jq.load:" in r.stderr, r.stdout + r.stderr
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

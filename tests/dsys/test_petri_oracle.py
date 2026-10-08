"""Pins the base time evolution of `lib/dsys/petri.amk` against a reference simulator.

The reference is a place/transition net stepped in Python under petri's one policy: the
first transition in declaration order whose every input place holds its arc's weight fires,
taking the weights and giving its outputs, until none is enabled or the firing cap is
reached. Nets are generated from a seed, so nothing on the expected side is written by hand:
the trace, the final marking and the cap error all come from the reference.
"""

import json
import random

import pytest

from conftest import sh

pytestmark = pytest.mark.engines("jq")

CAP = 40


def generate(seed):
  rng = random.Random(seed)
  places = [f"p{i}" for i in range(rng.randint(3, 7))]
  transitions = [f"t{i}" for i in range(rng.randint(2, 6))]
  arcs = []
  for t in transitions:
    for p in rng.sample(places, rng.randint(1, min(3, len(places)))):
      arcs.append([p, t, rng.randint(1, 2)])
    for p in rng.sample(places, rng.randint(0, min(3, len(places)))):
      arcs.append([t, p, rng.randint(1, 2)])
  marking = {p: rng.randint(0, 3) for p in places}
  return {"places": marking, "transitions": transitions, "arcs": arcs}


def reference(net, cap):
  marking = dict(net["places"])
  inputs = {t: [(a[0], a[2]) for a in net["arcs"] if a[1] == t] for t in net["transitions"]}
  outputs = {t: [(a[1], a[2]) for a in net["arcs"] if a[0] == t] for t in net["transitions"]}
  trace = []
  while True:
    if len(trace) >= cap:
      return trace, marking, "cap"
    enabled = next((t for t in net["transitions"]
                    if all(marking[p] >= w for p, w in inputs[t])), None)
    if enabled is None:
      return trace, marking, "quiet"
    for p, w in inputs[enabled]:
      marking[p] -= w
    for p, w in outputs[enabled]:
      marking[p] += w
    trace.append(enabled)


def run(amk, tmp_path, net):
  mk = tmp_path / "net.mk"
  mk.write_text("\n".join([
    "load dsys/petri", f"petri.max_firings := {CAP}",
    "@petri", "define n", json.dumps(net), "endef",
    "show: n.__main__", "\t@echo 'trace=[$(n.trace)] marking=[$(n.marking )]'", "",
  ]))
  return sh(amk, ["-s", "-f", str(mk), "show"], cwd=tmp_path, timeout=120)


@pytest.mark.parametrize("seed", range(40))
def test_the_run_matches_the_reference_on_a_generated_net(amk, tmp_path, seed):
  net = generate(seed)
  trace, marking, end = reference(net, CAP)
  r = run(amk, tmp_path, net)
  if end == "cap":
    assert r.returncode != 0, r.stdout + r.stderr
    assert f"n: {CAP} firings and still enabled" in r.stderr, r.stderr
    return
  assert r.returncode == 0, r.stdout + r.stderr
  want = " ".join(f"{p}={marking[p]}" for p in net["places"])
  assert f"trace=[{' '.join(trace)}] marking=[{want}]" in r.stdout, r.stdout


def test_the_generator_covers_both_endings():
  ends = {reference(generate(seed), CAP)[2] for seed in range(40)}
  assert ends == {"cap", "quiet"}, ends


def pnml(net):
  lines = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<pnml xmlns="http://www.pnml.org/version-2009/grammar/pnml">',
           '  <net id="n" type="http://www.pnml.org/version-2009/grammar/ptnet">',
           '    <name><text>generated</text></name>', '    <page id="p">']
  for p, n in net["places"].items():
    lines += [f'      <place id="{p}">', f'        <name><text>{p}</text></name>',
              '        <graphics><position x="1" y="2"/></graphics>',
              f'        <initialMarking><text>\n          {n}\n        </text></initialMarking>',
              '      </place>']
  for t in net["transitions"]:
    lines += [f'      <transition id="{t}"><name><text>{t}</text></name></transition>']
  for i, (s, d, w) in enumerate(net["arcs"]):
    lines += [f'      <arc id="a{i}" source="{s}" target="{d}">',
              f'        <inscription><text>{w}</text></inscription>',
              '        <toolspecific tool="x" version="1"><text>9</text></toolspecific>',
              '      </arc>']
  lines += ['    </page>', '  </net>', '</pnml>', '']
  return "\n".join(lines)


def run_file(amk, tmp_path, name, text):
  (tmp_path / name).write_text(text)
  stem = name.split(".")[0]
  mk = tmp_path / "net.mk"
  mk.write_text("\n".join([
    "load dsys/petri", f"petri.max_firings := {CAP}", f"load {tmp_path}/{name}",
    f"show: {stem}.__main__",
    f"\t@echo 'trace=[$({stem}.trace)] marking=[$({stem}.marking )]'", "",
  ]))
  return sh(amk, ["-s", "-f", str(mk), "show"], cwd=tmp_path, timeout=120)


@pytest.mark.engines("jq", "awk")
@pytest.mark.parametrize("seed", range(10))
def test_a_net_loaded_from_pnml_matches_the_reference(amk, tmp_path, seed):
  net = generate(seed)
  trace, marking, end = reference(net, CAP)
  r = run_file(amk, tmp_path, "m.pnml", pnml(net))
  if end == "cap":
    assert r.returncode != 0 and f"m: {CAP} firings and still enabled" in r.stderr, r.stderr
    return
  assert r.returncode == 0, r.stdout + r.stderr
  want = " ".join(f"{p}={marking[p]}" for p in net["places"])
  assert f"trace=[{' '.join(trace)}] marking=[{want}]" in r.stdout, r.stdout


@pytest.mark.engines("jq", "awk")
def test_the_pnml_export_loads_back_as_the_same_net(amk, tmp_path):
  net = generate(3)
  mk = tmp_path / "trip.mk"
  mk.write_text("\n".join([
    "load dsys/petri", "@petri", "define n", json.dumps(net), "endef",
    f"$(file > {tmp_path}/back.pnml,$(n.pnml))", f"load {tmp_path}/back.pnml",
    "$(info $(if $(filter $(n.exec .),$(back.exec .)),same,differ) $(back.exec .))",
    "all:", "\t@true", "",
  ]))
  r = sh(amk, ["-s", "-f", str(mk)], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.startswith("same "), r.stdout
  assert json.loads(r.stdout.split(" ", 1)[1]) == net, r.stdout

"""Pins the fsm lowering against lxsc, the scxml interpreter in the Lua guest.

A seeded machine in one of the modes (flat, nested, parallel, always, finals, stay, wild, done)
is written as the config and as scxml, and a seeded word of events is fed to both, one event
per macrostep. lxsc fires and steps; the net gets the event's token, steps to quiescence, and
drops a token no transition took, as the scxml queue drops an unmatched event. The active state
after each event and the transitions fired must agree. No guest body runs.
"""

import json
import random

import pytest

from conftest import sh

pytestmark = pytest.mark.engines("lua", "jq")


def generate(seed, mode="flat"):
  rng = random.Random(seed)
  states = [f"s{i}" for i in range(rng.randint(3, 6))]
  events = [f"e{i}" for i in range(1, rng.randint(3, 5))]
  if mode == "wild":
    events += ["*", "e0.*"]
  finals = states[-2:] if mode == "finals" else states[-1:]
  paths = {s: s for s in states}
  children, regions = {}, {}
  if mode in ("nested", "done"):
    for s in states[:-1]:
      if rng.random() < 0.5:
        children[s] = [f"{s}c{j}" for j in range(rng.randint(2, 3))] + ([f"{s}f"] if mode == "done" else [])
        for c in children[s]:
          paths[c] = f"{s}.{c}"
  if mode == "parallel":
    p = states[rng.randint(0, len(states) - 2)]
    regions[p] = {f"{p}r{i}": [f"{p}r{i}c{j}" for j in range(rng.randint(2, 3))] for i in range(2)}
    for r, cs in regions[p].items():
      paths[r] = f"{p}.{r}"
      for c in cs:
        paths[c] = f"{p}.{r}.{c}"
  outside = [s for s in states]

  def on(pool):
    return {e: ({} if mode == "stay" and rng.random() < 0.4 else f"#m.{paths[rng.choice(pool)]}")
            for e in events if rng.random() < 0.7}

  config = {"id": "m", "initial": states[0], "states": {}}
  for i, s in enumerate(states):
    if s in finals:
      config["states"][s] = {"type": "final"}
    elif mode == "always" and i > 0 and rng.random() < 0.5:
      config["states"][s] = {"on": on(states), "always": states[rng.randint(i + 1, len(states) - 1)]}
    elif s in children:
      pool = list(paths)
      config["states"][s] = {"initial": children[s][0], "on": on(pool),
                             "states": {c: ({"type": "final"} if c.endswith("f") else {"on": on(pool)}) for c in children[s]}}
      if mode == "done":
        config["states"][s]["onDone"] = f"#m.{paths[rng.choice(outside)]}"
    elif s in regions:
      config["states"][s] = {"type": "parallel", "on": on(outside), "states": {
        r: {"initial": cs[0], "states": {c: {"on": on(cs + outside)} for c in cs}}
        for r, cs in regions[s].items()}}
    else:
      pool = list(paths) if mode != "parallel" else outside + [c for cs in regions[list(regions)[0]].values() for c in cs]
      config["states"][s] = {"on": on(pool)}
  fed = [e for e in events if "*" not in e] + (["e0.x", "e0.y.z", "q"] if mode == "wild" else [])
  word = [rng.choice(fed) for _ in range(rng.randint(3, 8))]
  return config, word


def scxml(config):
  def state(sid, body, depth):
    pad = "  " * depth
    if body.get("type") == "final":
      return [f'{pad}<final id="{sid}"/>']
    tag = "parallel" if body.get("type") == "parallel" else "state"
    head = f'{pad}<{tag} id="{sid}"' + (f' initial="{body["initial"]}"' if "initial" in body else "") + ">"
    lines = [head]
    if "onDone" in body:
      lines.append(f'{pad}  <transition event="done.state.{sid}" target="{body["onDone"].rsplit(".", 1)[-1]}"/>')
    if "always" in body:
      lines.append(f'{pad}  <transition target="{body["always"]}"/>')
    for e, t in sorted(body.get("on", {}).items(), key=lambda kv: (kv[0] == "*", "*" in kv[0], -len(kv[0]))):
      target = "" if t == {} else f' target="{t.rsplit(".", 1)[-1].lstrip("#")}"'
      lines.append(f'{pad}  <transition event="{e}"{target}/>')
    for c, cb in body.get("states", {}).items():
      lines += state(c, cb, depth + 1)
    return lines + [f"{pad}</{tag}>"]

  lines = ['<scxml xmlns="http://www.w3.org/2005/07/scxml" version="1.0"'
           f' initial="{config["initial"]}" name="{config["id"]}">']
  for s, body in config["states"].items():
    lines += state(s, body, 1)
  lines.append("</scxml>")
  return "\n".join(lines)


def run(amk, tmp_path, config, word):
  lines = ["load dsys/fsm", "@fsm", "define m", json.dumps(config), "endef",
           "define doc", scxml(config), "endef"]
  for e in word:
    lines += [f"$(m.send {e})",
              "$(info N $(foreach i,1 2 3 4 5 6,$(m.step )) $(m.marking ))",
              f"$(foreach p,$(call fsm.route,m,{e}),$(if $(amk.pool.consume m.$(p), 0),))"]
  lines += [
    "@lua.target", "define probe",
    '  local m = require("lxsc"):parse(amk.var["doc"])',
    "  m:start()",
    "  m.onTransition = function(t) print('L fired ' .. (rawget(t, '_event') or 'always') .. ' ' .. (rawget(t, '_target') or '')) end",
    f"  for _, e in ipairs({{{', '.join(repr(e) for e in word)}}}) do",
    "    m:fireEvent(e); m:step()",
    "    print('L ' .. table.concat(m:activeAtomicIds(), ','))",
    "  end",
    "endef",
    "show: probe", "\t@true", "",
  ]
  mk = tmp_path / "oracle.mk"
  mk.write_text("\n".join(lines))
  return sh(amk, ["-s", "-f", str(mk), "show"], cwd=tmp_path, timeout=120)


def active(marking):
  held = [p.split("=")[0] for p in marking.split() if p.endswith("=1") and not p.startswith("ev.")]
  assert held, marking
  return sorted(h.rsplit(".", 1)[-1] for h in held)


@pytest.mark.parametrize("mode", ["flat", "nested", "parallel", "always", "finals", "stay", "wild", "done"])
@pytest.mark.parametrize("seed", range(20))
def test_the_net_follows_lxsc_macrostep_by_macrostep(amk, tmp_path, seed, mode):
  config, word = generate(seed, mode)
  r = run(amk, tmp_path, config, word)
  assert r.returncode == 0, r.stdout + r.stderr
  net = [ln[2:].split() for ln in r.stdout.splitlines() if ln.startswith("N ")]
  lua = [ln[2:] for ln in r.stdout.splitlines() if ln.startswith("L ") and not ln.startswith("L fired")]
  fired = [ln.split()[2] for ln in r.stdout.splitlines() if ln.startswith("L fired")]
  assert len(net) == len(word) == len(lua), r.stdout
  for step, (n, l) in enumerate(zip(net, lua)):
    marking = " ".join(w for w in n if "=" in w)
    assert active(marking) == sorted(l.split(",")), f"step {step}: net {n!r}, lxsc {l!r}\n{r.stdout}"
  if mode not in ("parallel", "wild", "done"):
    finals = tuple(f"{s}." for s, body in config["states"].items() if body.get("type") == "final")
    net_fired = [w for n in net for w in n if "=" not in w and not w.startswith(finals)]
    assert [t.rsplit(".", 1)[1] for t in net_fired] == fired, r.stdout

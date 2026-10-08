"""Fetch the W3C scxml-irp core tests and write them to core.json, instantiated for a Lua datamodel.

Run it from the repository as `make -C via/amk w3c`. The groups are the manifest's chapter 3
sections, raise in 4.2, if in 4.3 and the null datamodel in B.1. The conformance attributes
are rewritten as lxsc's suite runner rewrites them, so lxsc runs each file as its authors did.
"""

import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

BASE = "https://www.w3.org/Voice/2013/scxml-irp/"
SECTIONS = ("4.2", "4.3", "B.1")


def cmp(a, quote=False, var=False):
  x, op, y = re.split(r"([=<>]=?)", a, maxsplit=1)
  op = "==" if op == "=" else op
  rhs = f"testvar{y}" if var else (f"'{y}'" if quote else y)
  return f"testvar{x} {op} {rhs}"


ATTRS = {
  "datamodel": lambda a: ("datamodel", "lua"),
  "targetpass": lambda a: ("target", "pass"),
  "targetfail": lambda a: ("target", "fail"),
  "inState": lambda a: ("cond", f"In('{a}')"),
  "true": lambda a: ("cond", "true"),
  "false": lambda a: ("cond", "false"),
  "idVal": lambda a: ("cond", cmp(a)),
  "idQuoteVal": lambda a: ("cond", cmp(a, quote=True)),
  "compareIDVal": lambda a: ("cond", cmp(a, var=True)),
  "eventNameVal": lambda a: ("cond", f"_event.name == '{a}'"),
  "eventdataVal": lambda a: ("cond", f"_event.data == {a}"),
  "emptyEventData": lambda a: ("cond", "_event.data == nil"),
  "unboundVar": lambda a: ("cond", f"testvar{a}==nil"),
  "isBound": lambda a: ("cond", f"testvar{a} ~= nil"),
  "id": lambda a: ("id", f"testvar{a}"),
  "expr": lambda a: ("expr", a),
  "quoteExpr": lambda a: ("expr", f"'{a}'"),
  "varExpr": lambda a: ("expr", f"testvar{a}"),
  "eventName": lambda a: ("expr", "_event.name"),
  "location": lambda a: ("location", f"testvar{a}"),
  "invalidLocation": lambda a: ("location", ""),
  "delay": lambda a: ("delay", f"{100 * int(a)}ms"),
  "eventExpr": lambda a: ("eventexpr", f"testvar{a}"),
  "name": lambda a: ("name", f"testvar{a}"),
  "namelist": lambda a: ("namelist", f"testvar{a}"),
  "illegalTarget": lambda a: ("target", "xxxxxxxxx"),
}


def convert(text):
  text = text.replace("<conf:pass/>", '<final id="pass"/>').replace("<conf:fail/>", '<final id="fail"/>')
  text = re.sub(r"<conf:incrementID id=\"(\d+)\"\s*/>",
                lambda m: f"<assign location='testvar{m[1]}' expr='testvar{m[1]}+1'/>", text)
  text = re.sub(r"<conf:sumVars id1=\"(\d+)\" id2=\"(\d+)\"\s*/>",
                lambda m: f"<assign location='testvar{m[1]}' expr='testvar{m[1]}+testvar{m[2]}'/>", text)

  def attr(m):
    name, value = m[1], m[2]
    if name not in ATTRS:
      raise SystemExit(f"no rule for conf:{name}")
    k, v = ATTRS[name](value)
    return f'{k}="{v}"'

  return re.sub(r'conf:([A-Za-z]+)="([^"]*)"', attr, text)


def fetch(url):
  with urllib.request.urlopen(url, timeout=60) as r:
    return r.read().decode("utf-8")


def main(out):
  manifest = ET.fromstring(fetch(BASE + "manifest.xml"))
  tests = {}
  for a in manifest.iter("assert"):
    section = a.get("specnum") or ""
    if not (section.startswith("3.") or section in SECTIONS):
      continue
    for t in a.iter("test"):
      uri = t.find("start").get("uri")
      stem = Path(uri).stem
      for part in ("a", "b", "c") if stem.endswith("a") else ("",):
        name = stem[:-1] + part if part else stem
        tests[name] = {"section": section, "manual": t.get("manual") == "true",
                       "uri": uri.replace(stem, name)}
  docs = {}
  for name, meta in sorted(tests.items()):
    try:
      text = fetch(BASE + meta["uri"])
    except Exception as e:  # noqa: BLE001
      print(f"skip {name}: {e}", file=sys.stderr)
      continue
    docs[name] = {**meta, "scxml": convert(text)}
  Path(out).write_text(json.dumps(docs, indent=1, sort_keys=True))
  print(f"{len(docs)} tests written to {out}")


if __name__ == "__main__":
  main(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).with_name("core.json"))

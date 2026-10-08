# tspace/__init__.py: amk.tspace for micropython, the tuple space of init.amk, with python's own types as formals and object as any.
import json
import sys
import amk

_formals = {object: "?", str: "?str", int: "?int", float: "?float", (int, float): "?number", bool: "?bool", type(None): "?null", list: "?list", dict: "?dict"}


def _field(f):
    if isinstance(f, (type, tuple)):
        if f not in _formals:
            raise TypeError("amk.tspace: no formal for %r" % f)
        return _formals[f]
    return json.dumps(f)


def _call(space, verb, fields):
    text = amk.call(space + "." + verb, *[_field(f) for f in fields])
    return [json.loads(line)["t"] for line in text.split("\n") if line]


# One space by its workspace name, made in make by tspace.create; indexing a handle by a name is on.
class on:
    def __init__(self, space):
        self.space = space

    def __getitem__(self, name):
        return on(name)

    # An attribute a handle lacks is the make function of that name under tspace.
    def __getattr__(self, name):
        if name.startswith("__") or getattr(amk, "fxn?")("tspace." + name) != "1":
            raise AttributeError(name)
        return lambda *vals: amk.call("tspace." + name, *vals)

    def out(self, *fields):
        _call(self.space, "out", fields)

    def read(self, *pattern):
        return _call(self.space, "read", pattern)

    def inp(self, *pattern):
        found = _call(self.space, "inp", pattern)
        return found[0] if found else None

    # The blocking verbs, in_ for Linda's in since in is a keyword; the owner answers each once its condition holds.
    def in_(self, *pattern):
        return _call(self.space, "in", pattern)[0]

    def rd(self, *pattern):
        return _call(self.space, "rd", pattern)[0]

    def no(self, *pattern):
        _call(self.space, "no", pattern)
        return True

    # The one-shot copies, the absence test as a boolean, the whole space, the bulk forms over tuples as lists, and the uniform forms.
    def rdp(self, *pattern):
        found = _call(self.space, "rdp", pattern)
        return found[0] if found else None

    def nop(self, *pattern):
        try:
            _call(self.space, "nop", pattern)
        except Exception:
            return False
        return True

    def all(self):
        return _call(self.space, "all", ())

    def set(self, *tuples):
        _call(self.space, "set", tuples)

    def out_all(self, *tuples):
        _call(self.space, "out_all", tuples)

    def in_all(self, *pattern):
        return _call(self.space, "in_all", pattern)

    def urdp(self, *pattern):
        found = _call(self.space, "urdp", pattern)
        return found[0] if found else None

    def uinp(self, *pattern):
        found = _call(self.space, "uinp", pattern)
        return found[0] if found else None

    def urd(self, *pattern):
        return _call(self.space, "urd", pattern)[0]

    def uin(self, *pattern):
        return _call(self.space, "uin", pattern)[0]

    # Handlers: register a make function by name with its pattern; list them; remove one by name.
    def out_s(self, *fields):
        _call(self.space, "out_s", fields)

    def rd_s(self):
        return _call(self.space, "rd_s", ())

    def in_s(self, name):
        found = _call(self.space, "in_s", (name,))
        return found[0] if found else None


# A routed field arrives as text; each type word reads it back as python's own value.
_reads = {"int": int, "float": float, "number": float, "bool": lambda v: v == "1", "null": lambda v: None,
          "list": json.loads, "dict": json.loads, "table": json.loads}


# The define name as a make function: its body compiled with the space and the named fields as parameters.
def bind(space, name, spec):
    fields = [w.split(":") for w in spec.split()]
    params = [space] + [n for n, t in fields if n != "-"]
    lines = amk.call("amk.dedent*", name).split("\n")
    scope = {"amk": amk}
    exec("def _body(%s):\n" % ", ".join(params) + "".join("    " + l + "\n" for l in lines) + "    pass\n", scope)
    body = scope["_body"]

    def handler(*args):
        body(on(space), *[_reads[t](a) if t in _reads else a for (n, t), a in zip(fields, args) if n != "-"])
        return ""
    amk.func(name, handler)


# The verbs are make functions, so a makefile that never loaded the space fails here rather than at the first verb.
if amk.origin("tspace.spaces") == "undefined":
    raise ImportError("amk.tspace: the makefile has no tuple space; add load tspace")

on.on = on
_default = on("tuplespace")
_default.bind = bind
sys.modules["amk.tspace"] = _default
out, read, inp, in_, rd, no = _default.out, _default.read, _default.inp, _default.in_, _default.rd, _default.no
rdp, nop, all, set, out_all, in_all = _default.rdp, _default.nop, _default.all, _default.set, _default.out_all, _default.in_all
urdp, uinp, urd, uin = _default.urdp, _default.uinp, _default.urd, _default.uin
out_s, rd_s, in_s = _default.out_s, _default.rd_s, _default.in_s

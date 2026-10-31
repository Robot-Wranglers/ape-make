# actor/__init__.py: amk.actor for micropython, the handle a bound member reads its group through, answering from the group's data as it is now.
import json
import amk


def _data(group):
    return json.loads(amk.call(group + ".get", "."))


# A member's entry, its keys as attributes.
class _entry:
    def __init__(self, d):
        self._d = d

    def __getattr__(self, key):
        if key in self._d:
            return self._d[key]
        raise AttributeError(key)

    def __getitem__(self, key):
        return self._d[key]


# One member's view of its group: its id, the config, its siblings' entries now, and every member's entry under its id.
class on:
    def __init__(self, group, id):
        self._group, self.id = group, id

    def __getattr__(self, key):
        d = _data(self._group)
        if key == "config":
            return d
        if key in d["children"]:
            return _entry(d["children"][key])
        raise AttributeError(key)

    def siblings(self):
        return {k: _entry(v) for k, v in _data(self._group)["children"].items() if k != self.id}

    def cast(self, to, msg):
        return amk.call(self._group + ".cast", to, msg)

    def recv(self):
        return amk.call(self._group + ".recv", self.id)

    def ask(self, to, msg):
        return amk.call(self._group + ".ask", self.id, to, msg)

    def reply(self, req, answer):
        return amk.call(self._group + ".reply", req, answer)


# The define name as a make function: its body compiled with the group's handle as a parameter of the group's name, and as __group__.
def bind(group, name):
    lines = amk.call("amk.dedent*", name).split("\n")
    scope = {"amk": amk}
    exec("def _body(%s, __group__):\n" % group + "".join("    " + l + "\n" for l in lines) + "    pass\n", scope)
    body = scope["_body"]

    def member(*args):
        h = on(group, name)
        answer = body(h, h)
        return "done" if answer is None else str(answer)
    amk.func(name, member)

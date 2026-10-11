# utmpl.mk: utemplate templates held in defines, each one an imported target under an at line; the target renders json from stdin, and name/var renders the json held in the variable var.
$(amk.require micropy)

# The renderer, run once here to register the functions and again by every target's program, since a target runs in its own job.
define utmpl.py
import amk, io, json, os, sys
from utemplate.source import Compiler

_cache = {}

# A json object's keys arrive as plain names, unless the template has its own args line and takes the data whole.
def _compile(name, keys):
  text = amk.var.raw[name + ".tpl"]
  k = (name, text, keys)
  if k not in _cache:
    src = io.StringIO()
    c = Compiler(io.StringIO(text), src)
    named = ", ".join(keys + ("**_",)) if keys is not None else c.args
    c.args = named
    c.compile()
    ns = {}
    exec(src.getvalue(), ns)
    _cache[k] = (ns["render"], keys is not None and c.args == named)
  return _cache[k]

def _fail(msg):
  amk.expand("$(error utmpl: %s)" % msg)

def _render(name, data):
  keys = tuple(sorted(data)) if isinstance(data, dict) else None
  fn, splat = _compile(name, keys)
  try:
    return "".join(fn(**data) if splat else fn(data))
  except Exception as e:
    _fail("%s did not render: %s: %s" % (name, type(e).__name__, e))

def _data(var):
  if var:
    text = amk.var[var]
    if text is None:
      _fail("no variable named %s holds the data" % var)
  else:
    var, text = "stdin", sys.stdin.read()
  try:
    return json.loads(text)
  except ValueError as e:
    _fail("%s is not json: %s" % (var, e))

# A define loses its last newline, so a target puts one back.
def _run(name):
  out = _render(name, _data(os.getenv("UTMPL_DATA") or ""))
  sys.stdout.write(out if out.endswith("\n") else out + "\n")
endef

@micropy.exec
define micropy.utmpl
  import amk
  exec(amk.var.raw["utmpl.py"])

  # The template moves aside to name.tpl, since the imported target keeps its program as the variable name.
  def _import_target(name, *flags):
    amk.var.raw[name + ".tpl"] = amk.var.raw[name]
    prog = 'import amk\nexec(amk.var.raw["utmpl.py"])\n_run("%s")\n' % name
    amk.call("micropy.import.target", name, prog, *([" ".join(flags)] if flags else []))
    amk.eval("%s/%%: export UTMPL_DATA = $*\n%s/%%:\n\t$(amk) %s\n" % (name, name, name))
    return ""

  amk.func("utmpl.render", lambda name, var: _render(name, _data(var)))
  amk.func("utmpl.import.target*", _import_target)
endef

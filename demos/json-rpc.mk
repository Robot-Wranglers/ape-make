#!/usr/bin/env -S amk -f

PORT ?= 18090

include /zip/lib/mip.mk

@lua.import
define lua.methods
  function add(a, b) return tonumber(a) + tonumber(b) end
  function sorted(xs)
    local t = {}
    for x in xs:gmatch("%S+") do t[#t + 1] = tonumber(x) end
    table.sort(t)
    return table.concat(t, " ")
  end
endef

@js.import
define js.methods
  function shout(s) { return s.toUpperCase() + "!"; }
  function report(sorted, total) {
    return JSON.stringify({
      sorted: sorted.split(" ").map(Number),
      total: Number(total) }); }
endef

@s7.import
define s7.methods
  (define (fact n)
    (let loop
      ((n (string->number n)) (acc 1)) \
      (if (< n 2) acc (loop (- n 1) (* n acc)))))
  (define (total xs)
    (apply + (with-input-from-string (string-append "(" xs ")") read)))
endef

# Another method, composed on host, made up of different guests
stats = $(report $(sorted $1),$(total $1))

# Register the host method directly and all guests via reflection
rpc.methods = stats $(amk.fxns? lua, js, s7)

# HTTP server via mip
define mip.manifest
  { "microdot": {
      "version": "v2.7.0",
      "spec": "github:miguelgrinberg/microdot/src/microdot/microdot.py",
      "sha256": "7abf80436064aff030fb123c2947260674c84001517322d7c8517b7f2425e01a"
    }
  }
endef

@micropy.import
define rpc.server
  import amk, json, sys

  # Read-from-host: published methods from top-level registry
  methods = amk.var["rpc.methods"].split()

  def _val(s):
    try: return json.loads(s)
    except ValueError: return s

  def _arg(p):
    return " ".join(map(str, p)) \
      if isinstance(p, list) else str(p)

  def serve(port):
    from microdot import Microdot
    app = Microdot()

    @app.post("/")
    async def rpc(req):
      q = req.json
      reply = dict(jsonrpc="2.0", id=q["id"])
      if q["method"] not in methods:
        reply["error"] = dict(code=-32601, message="No Such Method")
        return reply
      params = [_arg(p) for p in q["params"]]

      # Async-call dispatch back into amk: `amk.acall`
      reply["result"] = _val(await amk.acall(q["method"], *params))
      return reply

    print("http://127.0.0.1:%s/" % port, file=sys.stderr)
    print("Methods: %s" % " ".join(methods), file=sys.stderr)
    app.run(port=int(port))
endef

__main__:
	echo "json-rpc: methods $(rpc.methods)"
	echo "run it with: $(amk) serve PORT=$(PORT)"

serve: mip.install
	$(serve $(PORT))

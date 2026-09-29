#!/usr/bin/env -S amk -f

# via/amk/demos/rpc-1.mk: a JSON-RPC server over HTTP; Python serves it with microdot from mip, every method lives in another language, and make is the switchboard between them.
goal.dir := build/rpc-1
PORT ?= 18090

# A target that fails leaves no value behind, so the next run builds it again.
.DELETE_ON_ERROR:

$(amk.require lua, s7, micropy, js, jq)

# One function per language, each imported as a make function.
@lua.import
define lua.methods
  function add(a, b) return tonumber(a) + tonumber(b) end
endef

@js.import
define js.methods
  function shout(s) { return s.toUpperCase() + "!"; }
endef

@s7.import
define myfact
  (define (fact n) 
    (let loop 
      ((n (string->number n)) (acc 1)) \
      (if (< n 2) acc (loop (- n 1) (* n acc)))))
endef

# An at line above a define makes the define an engine's target.
@js.import.target
define report
  print(JSON.stringify(
    { sorted: "@sorted@".split(" ").map(Number), total: @total@ }
  ));
endef

# A three-language chain as goals: lua sorts, s7 sums, js reports, each cached under goal.dir.
@lua.import.target
define sorted
  local xs = {}
  for x in ("@nums.txt@"):gmatch("%S+") do xs[#xs + 1] = tonumber(x) end
  table.sort(xs)
  print(table.concat(xs, " "))
endef

@s7.import.target
define total
  (format #t "~A" (apply + (list @sorted@)))
endef

# The input is written per request, so an empty rule names it as a target a reference can resolve.
$(goal.dir)/nums.txt: ;

# The method table: a JSON-RPC name maps to a make macro, and a list param arrives as one argument of words.
rpc.methods := $(amk.__fxns__)stats
rpc.add = $(add $1,$2)
rpc.shout = $(shout $1)
rpc.fact = $(fact $1)
rpc.stats = $(file >$(goal.dir)/nums.txt,$1)$(goal report)

# The transport is microdot, from GitHub by way of the payload's mip library.
include /zip/lib/mip.mk
define mip.manifest
  {
    "microdot": {
      "version": "v2.7.0",
      "spec": "github:miguelgrinberg/microdot/src/microdot/microdot.py",
      "sha256": "7abf80436064aff030fb123c2947260674c84001517322d7c8517b7f2425e01a"
    }
  }
endef

@micropy.import
define rpc.server
  import amk, json, sys

  def _val(s):
    try:
      return json.loads(s)
    except ValueError:
      return s

  def serve(port):
    sys.path.extend(amk.expand("$(mip.path)").split())
    from microdot import Microdot
    app = Microdot()

    @app.post("/")
    async def rpc(req):
      q = req.json
      args = ",".join(" ".join(map(str, p)) if isinstance(p, list) else str(p) for p in q["params"])
      return {"jsonrpc": "2.0", "id": q["id"], "result": _val(amk.expand("$(call rpc.%s,%s)" % (q["method"], args)))}

    app.run(port=int(port))
endef

__main__: test

serve: $(mip.stamps)
	echo "json-rpc on http://127.0.0.1:$(PORT)/ -- methods: $(rpc.methods)"
	$(serve $(PORT))

# Each request and its expected reply, against a server started for the test and stopped after it.
test: $(mip.stamps)
	${amk} serve >/dev/null & pid=$$!; sleep 1; \
	rpc() { curl -s -H 'Content-Type: application/json' -d "$$1" http://127.0.0.1:$(PORT)/; }; \
	trap 'kill $$pid' EXIT; set -e; \
	test "$$(rpc '{"jsonrpc":"2.0","id":1,"method":"add","params":[40,2]}')" = '{"result": 42, "id": 1, "jsonrpc": "2.0"}'; \
	test "$$(rpc '{"jsonrpc":"2.0","id":2,"method":"shout","params":["hi"]}')" = '{"result": "HI!", "id": 2, "jsonrpc": "2.0"}'; \
	test "$$(rpc '{"jsonrpc":"2.0","id":3,"method":"fact","params":[20]}')" = '{"result": 2432902008176640000, "id": 3, "jsonrpc": "2.0"}'; \
	test "$$(rpc '{"jsonrpc":"2.0","id":4,"method":"stats","params":[[3,1,4,1,5]]}')" = '{"result": {"sorted": [1, 1, 3, 4, 5], "total": 14}, "id": 4, "jsonrpc": "2.0"}'
	echo "microdot from mip in python, methods in lua, js, and s7, chained through goals"

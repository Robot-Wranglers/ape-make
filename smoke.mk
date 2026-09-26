noop:
	true

hello:
	echo "served by pid $$$$, level $(MAKELEVEL)"

define nl


endef

define lua.sum
local n = 0
for line in io.lines() do n = n + tonumber(line:match("%d+")) end
print("sum=" .. n)
endef

define s7.sum
(let loop ((n 0))
  (let ((line (read-line)))
    (if (eof-object? line)
        (format #t "sum=~A" n)
        (loop (+ n (string->number (substring line (+ 1 (char-position #\space line)))))))))
endef

define micropy.sum
import sys
n = 0
for line in sys.stdin:
    n += int(line.split()[1])
print("sum=%d" % n)
endef

define js.sum
let n = 0, line;
while ((line = std.in.getline()) !== null) n += parseInt(line.split(" ")[1]);
print("sum=" + n);
endef

define js.json
const d = JSON.parse(std.in.readAsString());
d.k += 1;
print(JSON.stringify(d));
endef

# A builtin drops one trailing newline and keeps the rest, so its output still chains.
trim.one := $(awk BEGIN { print "x" })
trim.inner := $(awk BEGIN { print "a"; print "b" })
trim.blank := $(awk BEGIN { print "a"; print "" })

# Option lists quoted as a shell would take them: a spaced value, an empty one, an escaped quote, a bare escape.
argv.awk.quoted = -v 'msg=hello world'
argv.jq.quoted = -n -r --arg a 'k/a k/b' --arg e "" --arg q "say \"hi\"" --arg s x\ y
argv.jq.join = [$$a,$$e,$$q,$$s] | join("|")

# Each payload tool resolves to the cache directory the binary put first on PATH; sed is GNU sed, and bash is the shell make itself forks.
tools ?= sed bash
path: SHELL := bash
path:
	for t in $(tools); do case "$$(command -v $$t)" in */amk/*/bin/$$t) echo "$$t on PATH: $$(command -v $$t)";; *) echo "$$t is not the payload's: $$(command -v $$t)" >&2; exit 1;; esac; done
	sed --version | head -1 | grep -q 'GNU sed'
	test "$$(printf 'x"y"\n' | sed 's/"\?y//')" = 'x"'
	test "$${BASH_VERSINFO[0]}" -ge 5
	echo "shell: bash $${BASH_VERSION} at $$(command -v bash)"

# With AMK_NO_PATH set, no payload tool is on PATH.
path.off:
	for t in $(tools); do case "$$(command -v $$t)" in */amk/*/bin/$$t) echo "$$t is on PATH despite AMK_NO_PATH" >&2; exit 1;; esac; done
	echo "AMK_NO_PATH: PATH left alone"

# json.bash answers under each of its names: jb builds an object, jb-array an array, and json.bash sources by name from PATH.
jb: SHELL := bash
jb:
	for t in jb jb-array json.bash; do case "$$(command -v $$t)" in */amk/*/bin/$$t) ;; *) echo "$$t is not the payload's: $$(command -v $$t)" >&2; exit 1;; esac; done
	test "$$(jb msg=hi n:number=41)" = '{"msg":"hi","n":41}'
	test "$$(jb-array a :number=1)" = '["a",1]'
	source json.bash && test "$$(json k=v)" = '{"k":"v"}'
	echo "jb: $$(jb --version)"

# The build passes the libraries it zipped in; gmsl is read in place from the payload and finds its helper file beside itself.
libs ?=
ifneq ($(filter gmsl,$(libs)),)
include /zip/lib/gmsl
endif

define lua.dkjson
local json = require("dkjson")
local d = json.decode('{"k": 41}')
d.k = d.k + 1
print(json.encode(d))
endef

libs:
	$(if $(filter gmsl,$(libs)),test "$(wildcard /zip/lib/gmsl)" = /zip/lib/gmsl)
	$(if $(filter gmsl,$(libs)),test "$(__gmsl_root)" = /zip/lib/)
	$(if $(filter gmsl,$(libs)),test "$(call uc,hello)" = HELLO)
	$(if $(filter gmsl,$(libs)),test "$(call int_decode,$(call int_plus,$(call int_encode,2),$(call int_encode,3)))" = 5)
	$(if $(filter gmsl,$(libs)),echo "gmsl: $(call uc,hello) from $(__gmsl_root) at version $(gmsl_version)")
	$(if $(filter dkjson,$(libs)),test "$(wildcard /zip/lib/dkjson.lua)" = /zip/lib/dkjson.lua)
	$(if $(filter dkjson,$(libs)),test '$(strip $(lua ${lua.dkjson}))' = '{"k":42}')
	$(if $(filter dkjson,$(libs)),echo "dkjson: $(strip $(lua print(require("dkjson").version)))")
	$(if $(libs),,test -z "$(wildcard /zip/lib/gmsl)")
	echo "libs: $(or $(libs),none)"

# The build passes the engines it selected; each one must be present and each one left out absent.
engines ?= awk jq lua s7 micropy js
# A wasi module from the wasm3 tree: it prints a fixed greeting, then its argv.
wasm.test ?= src/wasm3-0.9.0/test/wasi/simple/test.wasm

builtins:
	test "$(filter $(engines),$(.FEATURES))" = "$(engines)"
	test -z "$(filter-out $(engines),$(filter awk jq lua s7 micropy wasm js,$(.FEATURES)))"
	test "$(.ENGINES)" = "$(engines)"
	echo "features: $(filter $(engines),$(.FEATURES))"
	echo "engines: $(.ENGINES)"
	$(if $(filter awk,$(engines)),echo "awk: $(strip $(awk { s += $$2 } END { print "sum=" s },alpha 1$(nl)beta 2$(nl)gamma 3))")
	$(if $(filter awk,$(engines)),test "$(strip $(awk { s += $$2 } END { print "sum=" s },alpha 1$(nl)beta 2$(nl)gamma 3))" = "sum=6")
	$(if $(filter jq,$(engines)),echo "jq:  $(strip $(jq .n+1,{"n": 41}))")
	$(if $(filter jq,$(engines)),test "$(strip $(jq .n+1,{"n": 41}))" = "42")
	$(if $(filter jq,$(engines)),test '$(strip $(jq .name | ascii_upcase,{"name": "cmk"}))' = '"CMK"')
	$(if $(filter awk,$(engines)),test "$(strip $(awk.argv -v mul=10 -F:,{ s += $$2 * mul } END { print s },a:1$(nl)b:2$(nl)c:3))" = "60")
	$(if $(filter awk,$(engines)),test '$(trim.one)' = 'x')
	$(if $(filter awk,$(engines)),test '$(subst $(nl),|,$(trim.inner))' = 'a|b')
	$(if $(filter awk,$(engines)),test '$(subst $(nl),|,$(trim.blank))' = 'a|')
	$(if $(filter awk,$(engines)),test '$(awk END { print NR },$(trim.inner))' = '2')
	$(if $(filter awk,$(engines)),echo "trim: one trailing newline dropped and the rest kept")
	$(if $(filter jq,$(engines)),test "$(strip $(jq.argv -r,.name,{"name": "cmk"}))" = "cmk")
	$(if $(filter awk,$(engines)),test "$(strip $(awk.argv ${argv.awk.quoted},BEGIN { print msg }))" = "hello world")
	$(if $(filter jq,$(engines)),test '$(strip $(jq.argv ${argv.jq.quoted},${argv.jq.join}))' = 'k/a k/b||say "hi"|x y')
	$(if $(filter lua,$(engines)),echo "lua: $(strip $(lua print(41 + 1)))")
	$(if $(filter lua,$(engines)),echo "lua: $(strip $(lua ${lua.sum},alpha 1$(nl)beta 2$(nl)gamma 3))")
	$(if $(filter s7,$(engines)),echo "s7:  $(strip $(s7 (display (+ 41 1))))")
	$(if $(filter s7,$(engines)),echo "s7:  $(strip $(s7 ${s7.sum},alpha 1$(nl)beta 2$(nl)gamma 3))")
	$(if $(filter micropy,$(engines)),echo "micropy: $(strip $(micropy print(41 + 1)))")
	$(if $(filter micropy,$(engines)),test "$(strip $(micropy print(41 + 1)))" = "42")
	$(if $(filter micropy,$(engines)),echo "micropy: $(strip $(micropy ${micropy.sum},alpha 1$(nl)beta 2$(nl)gamma 3))")
	$(if $(filter micropy,$(engines)),test "$(strip $(micropy ${micropy.sum},alpha 1$(nl)beta 2$(nl)gamma 3))" = "sum=6")
	$(if $(filter js,$(engines)),echo "js:  $(strip $(js print(41 + 1)))")
	$(if $(filter js,$(engines)),test "$(strip $(js print(41 + 1)))" = "42")
	$(if $(filter js,$(engines)),echo "js:  $(strip $(js ${js.sum},alpha 1$(nl)beta 2$(nl)gamma 3))")
	$(if $(filter js,$(engines)),test "$(strip $(js ${js.sum},alpha 1$(nl)beta 2$(nl)gamma 3))" = "sum=6")
	$(if $(filter js,$(engines)),test '$(strip $(js ${js.json},{"k": 41}))' = '{"k":42}')
	$(if $(filter js,$(engines)),test "$(strip $(js print(os.getpid() > 0)))" = "true")
	$(if $(filter js,$(engines)),test "$(strip $(js print(await Promise.resolve(7))))" = "7")
	$(if $(filter wasm,$(engines)),echo "wasm: $(firstword $(wasm ${wasm.test} hello))")
	$(if $(filter wasm,$(engines)),test "$(findstring Hello world,$(wasm ${wasm.test} hello))" = "Hello world")
	$(if $(filter wasm,$(engines)),test "$(findstring Args: test.wasm; hello;,$(wasm ${wasm.test} hello))" = "Args: test.wasm; hello;")

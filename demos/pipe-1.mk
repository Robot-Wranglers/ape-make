#!/usr/bin/env -S amk -f

# via/amk/demos/pipe-1.mk: every engine in one shell pipe, each stage adding its own version to a json object.

stages := s7 awk jq lua micropy js
$(amk.require $(stages))

__main__:
	${amk} s7.seed </dev/null | ${amk} awk.add | ${amk} jq.add | ${amk} lua.add \
	  | ${amk} micropy.add | ${amk} js.add | ${amk} jq.check

# Every stage is a target: its engine is the name's prefix, its program the define of the same name, and its input stdin.
s7.seed awk.add jq.add lua.add micropy.add js.add jq.check:
	@$(info $(or $(call $(firstword $(subst ., ,$@)),$(amk.dedent $($@)),$(file </dev/stdin)),$(error $@: no output)))

define s7.seed
  (format #t "{\"s7\": \"~A\"}" (*s7* 'version))
endef

define awk.add
  BEGIN { while ((getline line) > 0) s = s line
          print substr(s, 1, length(s) - 1) ", \"awk\": \"" PROCINFO["version"] "\"}" }
endef

define jq.add
  . + {jq: "$(jq.argv --version,.)"}
endef

define lua.add
  local json = require("dkjson")
  local d = json.decode(io.read("a"))
  d.lua = _VERSION
  print(json.encode(d))
endef

define micropy.add
  import sys, json
  d = json.load(sys.stdin)
  d["micropy"] = sys.version
  print(json.dumps(d))
endef

define js.add
  const d = JSON.parse(std.in.readAsString());
  d.js = "quickjs on " + os.platform;
  print(JSON.stringify(d));
endef

# The last stage fails unless every stage left a key.
define jq.check
  if (keys | length) == $(words $(stages)) then . else error("expected $(words $(stages)) stages, got \(keys)") end
endef

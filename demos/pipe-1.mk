# via/amk/demos/pipe-1.mk: every engine in one shell pipe, each stage adding its own version to a json object.
SHELL := bash
.SHELLFLAGS ?= -euo pipefail -c
MAKEFLAGS = -s -S --warn-undefined-variables
.DEFAULT_GOAL := all
self := $(lastword $(MAKEFILE_LIST))

# Stock make's feature list carries no engine word, so this demo stops before it reaches an engine.
ifeq ($(filter jq s7,$(.FEATURES)),)
  $(error $(self) needs amk -- run it as ./amk -f $(self), not under stock make)
endif

# wasm takes a module rather than program text, so it has no stage here.
engines := $(filter-out wasm,$(.ENGINES))

# One pattern rule per engine: the target names the program variable, stdin is the input, and no output is a failure.
define stage
$1.%:
	$$(info $$(or $$($1 $$($$@),$$(file </dev/stdin)),$$(error $$@: no output)))
endef
$(foreach e,$(.ENGINES),$(eval $(call stage,$e)))

all:
	$(MAKE) -f $(self) s7.seed </dev/null \
	  $(foreach e,$(filter-out s7,$(engines)),| $(MAKE) -f $(self) $e.add) \
	  | $(MAKE) -f $(self) jq.check

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

# The last stage parses what the others built and fails unless every engine left a key.
define jq.check
if (keys | length) == $(words $(engines)) then . else error("expected $(words $(engines)) engines, got \(keys)") end
endef

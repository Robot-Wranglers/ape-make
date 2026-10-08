#!/usr/bin/env -S amk -f

# via/amk/demos/jq-1.mk: jq as a generator, building json from make's own values with no input at all.

$(amk.require jq)

__main__:
	${amk} jq.check

export engines := $(.ENGINES)

# With --null-input jq reads nothing: its value comes from the program alone, here make's engine list through the environment.
@jq.import.target --null-input --compact-output
define jq.manifest
  {name: "amk", engines: (env.engines | split(" "))}
endef

# A second generator reads the first through @jq.manifest@, which splices its value in as json.
@jq.import.target --null-input --raw-output
define jq.check
  (@jq.manifest@)
  | if (.engines | index("jq")) then "manifest: \(.engines | length) engines"
    else error("jq is missing from \(.engines)") end
endef

#!/usr/bin/env -S amk -f

# via/amk/demos/jq-2.mk: jq as a filter over a stream, and --null-input with inputs to fold the stream into one value.

$(amk.require jq)

__main__:
	${amk} jq.events | ${amk} jq.errors | ${amk} jq.summary

# A stream of log events, one json value per line.
@jq.import.target --null-input --compact-output
define jq.events
  {level: "info", ms: 12}, {level: "error", ms: 40}, {level: "error", ms: 7}, {level: "info", ms: 3}
endef

# With no flags jq runs once per value on standard input, as any jq filter does.
@jq.import.target --compact-output
define jq.errors
  select(.level == "error")
endef

# With --null-input the program runs once and pulls the stream itself through inputs.
@jq.import.target --null-input --raw-output
define jq.summary
  reduce inputs as $e ({n: 0, ms: 0}; .n += 1 | .ms += $e.ms)
  | if .n == 2 and .ms == 47 then "errors: \(.n), \(.ms) ms"
    else error("expected 2 errors and 47 ms, got \(.)") end
endef

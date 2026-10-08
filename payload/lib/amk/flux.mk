#
# payload/lib/amk/flux.mk:
#  the safe core of flux, the workflow library: the knobs, macros, and
#  targets that read only make and m5.  The rest lives in compose.mk, since
#  each piece reads its logging, io, or stream namespaces.
#
flux.goal := $(.DEFAULT_GOAL)

# How flux recurses into the program; compose.mk rebinds it to its own make.
flux.reentrant=${amk}

FLUX_POLL_DELTA?=5

# Retry bounds: an attempt cap, and the seconds between tries.
$(call m5.declare, FLUX_RETRY_N ?= 100, FLUX_RETRY_DELAY ?= 0.1)

# A constructor for binary partials; see demos/partials.mk.
__flux.partial__=$(eval $(m5[1])/%:; ${flux.reentrant} $(m5[2])/$(m5[3]),$${*})

# Runs comma-listed targets in sequence, stopping at the first failure.
flux.and=${flux.reentrant} $(subst $(comma), && ${flux.reentrant} ,$(m5.__nargs__))
flux.all=$(call flux.and,$(m5.__nargs__))
flux.all/% flux.and/%:
	@# Runs the named comma-delimited targets in sequence, failing fast.
	@# Unlike plain make, a duplicate target runs again.
	@#
	@# USAGE: ./compose.mk flux.and/<t1>,<t2>
	$(call flux.and,${*})

flux.echo=echo "${1}"
flux.echo/%:
	@# Echoes the argument.
	$(call flux.echo,${*})

flux.indent/%:
	@# Runs the given target, indenting both its stdout and stderr.
	${flux.reentrant} flux.indent.sh cmd="${flux.reentrant} ${*}"

flux.indent.sh:
	@# Runs the shell command in the cmd env-var, indenting its stdout and stderr.
	$${cmd} 1> >(sed 's/^/  /') 2> >(sed 's/^/  /' >&2)

flux.negate=! ${flux.reentrant} $(m5.__nargs__)
flux.negate/%:
	@# Negates the status for the given target.
	@#
	@# USAGE: ./compose.mk flux.negate/flux.fail
	$(call flux.negate,${*})

flux.noop=true
flux.noop:
	@# No-op, mostly used for testing.  Similar to `flux.ok` but without logging.
	$(call flux.noop)

# Runs comma-listed targets until the first one succeeds.
flux.or=${flux.reentrant} $(subst $(comma), || ${flux.reentrant} ,$(m5.__nargs__))
flux.any=$(call flux.or,$(m5.__nargs__))
flux.or/%:
	@# Runs the named comma-delimited targets until one of them succeeds.
	@#
	@# USAGE: ./compose.mk flux.or/flux.fail,flux.ok
	$(call flux.or,${*})
flux.any/%:
	$(call flux.any,${*})

# Loops a shell command until it succeeds, capped by the second argument.
flux.retry.sh=_n=$(or $(m5[2]?),${FLUX_RETRY_N}); _r=0; _rc=1; while [ $$_r -lt $$_n ]; do { $(1); } && { _rc=0; break; }; _r=$$(($$_r+1)); [ $$_r -lt $$_n ] && sleep $${interval:-${FLUX_RETRY_DELAY}}; done; ( exit $$_rc )

flux.stream.obliviate/%:
	@# Runs the given target, sending all of its output to /dev/null.
	$(call _sh.obliviate, ${flux.reentrant} ${*})

# Like flux.and, over targets separated by commas or colons.
flux.wrap=$(call flux.and,$(subst :,$(comma),$(m5.__nargs__)))
flux.wrap/%:
	@# Same as flux.and, but also splits on colons, for args that keep commas.
	$(call flux.wrap,${*})

_sh.obliviate=${1} 2>/dev/null > /dev/null

# A library's targets never become the includer's default goal.
.DEFAULT_GOAL := $(flux.goal)

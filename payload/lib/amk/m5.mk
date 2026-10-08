#
# payload/lib/amk/m5.mk:
#  m5, the templating substrate of the platform-independent make runtime.
#  First the constants: the literals make cannot write bare inside a
#  function call, the quiet, trace, and NO_COLOR flags, and the terminal
#  colors.  Then the macro engine: read, eval and write poles, positional
#  accessors, origin predicates, memo cells, and hole fills.  It reads only
#  make builtins and itself.
#
##░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
## BEGIN: m5 :: The string-templating macro engine (an m4 in make)
##
## Notation simulates a type system: ? read, ! force/eval, % fill one hole, /
## fold over a context, [..] index.  Two changequote domains: ${X} vs @@X@@.
##
## * m5? :: Read pole — a var's raw value
## * m5! :: Eval pole — evaluate text as makefile
## * m5.self! :: Establish the m5.self context (receiver) at a constructor head
## * m5.set / m5.set.op :: Implicit-self setattr via m5!: set(name,val) / set.op(name,op,val)
## * m5.def! :: Write pole — freeze a body into a named define
## * m5.def.! :: Write, live — the name self-evals its template on each use
## * m5.ctx? :: Read a kwarg from a k=v list (quote-aware, strips)
## * m5.at / m5.rest :: List ops: element at a dynamic index; the list minus its head
## * m5.select / m5.pluck :: Keep (or read) list elements whose %-patterned var is defined
## * m5[1] / m5[2..4] :: Inline positional arg accessors (expand in-frame)
## * m5[1][KEY] / m5[def|namespace|file] :: Arg-1 kwarg accessors (quote-aware)
## * m5[1].gensym / m5.gensym :: codegen kwarg accessors from a key list
## * m5[__self__] :: The receiver (= m5[1]); the self that m5.set stamps onto
## * m5.__splat__ :: All positional call args, space-joined (undefined dropped)
## * m5.tmpl% :: Fill one ${X} hole (make domain)
## * m5.quasi% :: Fill one @@X@@ hole (awk domain)
## * m5.splice! :: Join a list of block values, newline-separated
##
## * m5.tmpl/% :: Fold a fill over a context (→ a thunk).
##     seed[.self] / seed.ns build seed / ns-prefixed tmpls; !=eval.
##░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░

# Literals, per the make manual, Syntax of Functions, Special Characters.
empty:=
space:= $(empty) $(empty)
define nl


endef
comma=,

# Pre-declared empty, so a read is safe under undefined-variable warnings.
quiet ?=
trace ?=
NO_COLOR ?=

# Terminal colors, all empty when NO_COLOR is 1, per https://no-color.org/
ifeq ($(NO_COLOR),1)
no_ansi =
green =
yellow =
dim =
underline =
bold =
ital =
no_color =
red =
cyan =
else
no_ansi = \033[0m
green = \033[92m
yellow = \033[33m
blue = \033[38;5;27m
dim = \033[2m
underline = \033[4m
bold = \033[1m
ital = \033[3m
no_color = \e[39m
red = \033[91m
cyan = \033[96m
endif
dim_red = ${dim}${red}
dim_yellow = ${dim}${yellow}
bold_red = ${bold}${red}
bold_yellow = ${bold}${yellow}
dim_cyan = ${dim}${cyan}
bold_cyan = ${bold}${cyan}
bold_green = ${bold}${green}
bold.underline = ${bold}${underline}
dim_green = ${dim}${green}
dim_ital = ${dim}${ital}
dim_ital_cyan = ${dim}${ital}${cyan}
no_ansi_dim = ${no_ansi}${dim}
cyan_flow_right = ${no_ansi_dim}⋙${dim}${cyan}⋙${no_ansi}${bold_cyan}⋙${no_ansi}
sep = ${no_ansi}//

# The macro engine.

# m5.declare: run each comma-separated argument, trimmed, as one assignment.
m5.declare.slots := 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32
m5.declare = $(foreach _n,$(m5.declare.slots),$(eval $(strip $(if $(filter undefined,$(origin $(_n))),,$($(_n))))))
# m5.declare!: the same, exported; an empty slot is skipped, never export-all.
m5.declare! = $(foreach _n,$(m5.declare.slots),$(if $(strip $(if $(filter undefined,$(origin $(_n))),,$($(_n)))),$(eval export $(strip $($(_n))))))

# Log glyphs: _GLYPH_* are raw marks, GLYPH_* their colorized wrappers.
$(call m5.declare, \
	_GLYPH_COMPOSE = ${bold}≣${no_ansi}, _GLYPH.DOCKER = ${bold}≣${no_ansi}, \
	_GLYPH_MK = ${bold}✱${no_ansi}, _GLYPH_IO = ${bold}⇄${no_ansi}, \
	_GLYPH_TUI = ${bold}⏣${no_ansi}, _GLYPH_FLUX = ${bold}Φ${no_ansi}, \
	_GLYPH_WARN = ${bold}⚠${no_ansi}, _GLYPH_ERROR = ${bold}🛇${no_ansi}, _GLYPH_LANG_OFF = ∅)
$(call m5.declare, \
	GLYPH_COMPOSE = ${green}${_GLYPH_COMPOSE}${dim_green}, GLYPH.DOCKER = ${green}${_GLYPH.DOCKER}${dim_green}, \
	GLYPH_MK = ${green}${_GLYPH_MK}${dim_green}, GLYPH_IO = ${green}${_GLYPH_IO}${dim_green}, \
	GLYPH_TUI = ${green}${_GLYPH_TUI}${dim_green}, GLYPH_FLUX = ${green}${_GLYPH_FLUX}${dim_green}, \
	GLYPH_WARN = ${yellow}${_GLYPH_WARN}${dim_yellow}, GLYPH_ERROR = ${red}${_GLYPH_ERROR}${dim_red}, \
	GLYPH_LANG_OFF = ${yellow}${_GLYPH_LANG_OFF}${no_ansi_dim})
m5? = $(value $(1))
m5! = $(eval $(1))
m5.def! = $(eval define $(m5[1])$(nl)$(2)$(nl)endef)
m5.def.! = $(eval $(m5[1]) = $$(eval $$(call $(m5[2]),$$(strip $$(1)))))
m5.self! = $(eval m5.self := $(1))
m5.set = $(call m5!,$(m5.self).$(1) := $(2))
m5.set.op = $(call m5!,$(m5.self).$(1) $(2) $(3))
# Save/restore stack: a scalar plus a shadow list, ꙮ standing in for an empty value.
m5.stack.push = $(or $(1),ꙮ) $(2)
m5.stack.top = $(patsubst ꙮ,,$(firstword $(1)))
# m5[N]/m5[N]?: in-frame strip-normalized arg accessors, codegen 1..9
$(foreach _n,1 2 3 4 5 6 7 8 9,$(eval m5[$(_n)] = $$(strip $$($(_n))))$(eval m5[$(_n)]? = $$(if $$(filter undefined,$$(origin $(_n))),,$$(m5[$(_n)]))))
# m5[N][i]: one-based numeric subscript (word i of arg N's list), codegen 1..9 x 1..16
$(foreach _n,1 2 3 4 5 6 7 8 9,$(foreach _i,1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16,$(eval m5[$(_n)][$(_i)] = $$(word $(_i),$$(m5[$(_n)])))))
# m5[N] dot-accessors over arg N; the m5.__acc__ list is the vocabulary the compiler consumes
m5.__acc__ := len first last rest
$(foreach _n,1 2 3 4 5 6 7 8 9,$(eval m5[$(_n)].len = $$(words $$(m5[$(_n)])))$(eval m5[$(_n)].first = $$(firstword $$(m5[$(_n)])))$(eval m5[$(_n)].last = $$(lastword $$(m5[$(_n)])))$(eval m5[$(_n)].rest = $$(wordlist 2,$$(words $$(m5[$(_n)])),$$(m5[$(_n)]))))
# m5.at list i: the element of a list at a dynamic one-based index.  m5.rest: the list minus its first word.
m5.at = $(word $(m5[2]),$(m5[1]))
m5.rest = $(wordlist 2,$(words $(1)),$(1))
m5[__self__] = $(m5[1])
# Origin predicates (ifdef/ifndef); m5| = read-or-default (eager).
m5.defined? = $(filter-out undefined,$(origin $(m5[1])))
m5.undefined? = $(filter undefined,$(origin $(m5[1])))
m5.given? = $(or $(findstring environment,$(origin $(m5[1]))),$(findstring command,$(origin $(m5[1]))))
m5| = $(if $(call m5.defined?,${1}),$($(m5[1])),${2})
# m5.__nargs__: a variadic call's arguments as one comma string, a,b,c.
m5.__nargs__=$(subst $(space),,$(if $(filter-out undefined,$(origin 1)),$(1))$(foreach _n,2 3 4 5 6 7 8 9 10 11 12,$(if $(call m5.defined?,$(_n)),$(if $(strip $($(_n))),$(comma)$(strip $($(_n)))))))
# m5.engine? names: the running make carries every named engine; a make with no engine list answers no instead of failing.
m5.engine? = $(if $(filter-out $(call m5|,.ENGINES,),$(m5[1])),,$(m5[1]))
# m5.select list pat / m5.pluck list pat: keep (or read) the elements whose pat-named var is defined.
m5.select = $(strip $(foreach _m5s_e,$(m5[1]),$(if $(call m5.defined?,$(subst %,$(_m5s_e),$(m5[2]))),$(_m5s_e))))
m5.pluck = $(strip $(foreach _m5s_e,$(call m5.select,${1},${2}),$($(subst %,$(_m5s_e),$(m5[2])))))
m5.__splat__=$(strip $(foreach _as,1 2 3 4 5 6 7 8 9,$(if $(filter-out undefined,$(origin $(_as))),$($(_as)))))
# m5.marm cellvar: arm a var to self-memoize its own value (run-once); dollars are doubled so the := keeps them literal.
m5.marm = $(eval $(strip $(m5[1])) = $$(eval $(strip $(m5[1])) := $$(subst $$$$,$$$$$$$$,$(value $(strip $(m5[1])))))$$($(strip $(m5[1]))))
# m5.memoize var: cache _var.detect into var on first read.
m5.memoize = $(eval $(strip $(m5[1])) = $$(_$(strip $(m5[1])).detect))$(call m5.marm,$(strip $(m5[1])))
# m5.memoize.fn cache fn arg: cache fn's result keyed by arg.
m5.memoize.fn = $(if $(call m5.defined?,$(strip $(m5[1]))[$(strip $(m5[3]))]),,$(eval $(strip $(m5[1]))[$(strip $(m5[3]))] := $(call $(strip $(m5[2])),$(m5[3]))))$($(strip $(m5[1]))[$(strip $(m5[3]))])
m5.tmpl% = $(subst $${$(m5[2])},$(m5[3]),$(1))
m5.quasi% = $(subst @@$(m5[2])@@,${3},${1})
m5.tmpl/%  = $(if $(m5[2]),$(call m5.tmpl/%,$(call m5.tmpl%,$(1),body$(words x $(3)),$(firstword $(2))),$(wordlist 2,$(words $(2)),$(2)),x $(3)),$(1))
m5.tmpl/seed = $(call m5.tmpl/%,$(call m5.tmpl%,$(call m5.tmpl%,$(call m5?,$(1)),1,$(2)),self,$(firstword $(3))),$(3),)
m5.tmpl/seed.ns =$(call m5.tmpl%,$(call m5.tmpl%,$(call m5.tmpl%,$(call m5?,$(1)),1,$(2)),self,$(3)),body1,$(4))
m5.tmpl! = $(eval $(if $(filter undefined,$(origin 4)),$(call m5.tmpl/seed,$(1),$(m5[2]?),$(m5[3]?)),$(call m5.tmpl/seed.ns,$(1),$(2),$(3),$(4))))
m5.quasi/% = $(if $(m5[2]),$(call m5.quasi/%,$(call m5.quasi%,$1,$(firstword $2),$($(m5[3]).$(firstword $2))),$(wordlist 2,$(words $2),$2),$3),$1)
m5.splice! = $(foreach _qq,${1},$(call m5?,$(strip ${_qq}))$(nl))
# list ops: reverse, and dedup keeping the first; m5.table below uses uniq.
m5.lex.rev=$(if $(m5[1]),$(call m5.lex.rev,$(wordlist 2,$(words ${1}),${1})) $(firstword ${1}))
m5.lex.uniq = $(if $(m5[1]),$(firstword $(1)) $(call m5.lex.uniq,$(filter-out $(firstword $(1)),$(wordlist 2,$(words $(1)),$(1)))))
# m5.table: key=value subscript table; .dispatch/.call = jump table.
define m5.table
$(eval $(strip $(1)).__all__ :=)
$(eval $(strip $(1)).__default__ := $(m5[3]?))
$(foreach _m5t_e,$(2),$(eval _m5t_k := $(strip $(word 1,$(subst =,$(space),$(_m5t_e)))))$(eval _m5t_v := $(strip $(word 2,$(subst =,$(space),$(_m5t_e)))))$(eval $(strip $(1))[$(_m5t_k)] := $(_m5t_v))$(eval $(strip $(1)).rev[$(_m5t_v)] := $(strip $(call m5.lex.uniq,$(call m5|,$(strip $(1)).rev[$(_m5t_v)],) $(_m5t_k))))$(eval $(strip $(1)).__all__ += $(_m5t_k)))
$(eval $(strip $(1)).resolve = $$(call m5|,$(strip $(1))[$$(strip $$(m5[1]))],$$(or $$(m5[2]?),$($(strip $(1)).__default__))))
$(eval $(strip $(1)).reverse = $$(call m5|,$(strip $(1)).rev[$$(strip $$(m5[1]))],$$(m5[2]?)))
$(eval $(strip $(1)).has? = $$(if $$(call m5.defined?,$(strip $(1))[$$(strip $$(m5[1]))]),$$(strip $$(m5[1])),))
$(eval $(strip $(1)).dispatch = $$(call $$(call $(strip $(1)).resolve,$$(m5[1])),$$(m5[2]?),$$(m5[3]?),$$(m5[4]?)))
$(eval $(strip $(1)).call = $$(if $$(call $(strip $(1)).has?,$$(m5[1]))$($(strip $(1)).__default__),$$(call $(strip $(1)).dispatch,$$(m5[1]),$$(m5[2]?),$$(m5[3]?),$$(m5[4]?)),$$(call mk.error, no dispatch handler for `$$(strip $$(m5[1]))` in table $(strip $(1)), errno=NOT_CALLABLE)))
endef

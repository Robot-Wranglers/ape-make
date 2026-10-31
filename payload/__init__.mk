#
# payload/__init__.mk:
#  the prelude amk reads before every makefile: the shell and its flags,
#  quiet make, the amk command, the amk.fxn! decorator, and m5.
#  each value is a default, and a later assignment in a makefile wins.
#
__bash__ := $(firstword $(wildcard $(addsuffix /bash,$(subst :, ,$(PATH)))))
SHELL := $(or $(value AMK_SHELL),$(if $(__bash__),bash,/bin/sh))

# The flags follow SHELL when a recipe runs, so sh gets flags sh takes.
amk.shellflags = $(if $(filter bash %/bash,$(SHELL)),-euo pipefail -c,-eu -c)
.SHELLFLAGS = $(or $(value AMK_SHELLFLAGS),$(amk.shellflags))
MAKEFLAGS = -s -S --warn-undefined-variables
.DEFAULT_GOAL := $(value AMK_GOAL)
__file__ ?= $(firstword $(MAKEFILE_LIST))
amk = $(MAKE) -f $(abspath $(__file__))

# The decorator @amk.fxn! above a define makes it a make function of its name.
amk.fxn!_star = $(amk.fxn! $(1))

# A define named by its JSON body, read as JSON5 when this amk has sqlite.
amk.val.json5 = $(if $(filter sqlite,$(.FEATURES)), \
  $(amk.json5 $(value $(1))),$(value $(1)))
$(amk.fxn! amk.val.json5)

# JSON text checked under a label against a schema file found as load finds a name, by io's schema.jq, fatal on an error; a no-op in an amk without it.
amk.schema.jq = $(amk.lib.find io/schema.jq)
amk.schema.prog := include "schema"; . as [$$d, $$s] | .[2:] as $$o | $$d | schema_errors($$s; $$o) | join("; ")
amk.schema.file = $(or $(amk.lib.find $(1)),$(error $(2): no schema file $(1) under $(amk.lib.roots)))
amk.schema.siblings = $(filter-out $(1),$(wildcard $(dir $(1))*.json))
amk.schema.name = $(lastword $(subst /, ,$(dir $(1))))/$(notdir $(1))
amk.schema.input = [$(1),$(file < $(2))$(foreach f,$(call amk.schema.siblings,$(2)),,$(file < $(f)))]
amk.schema.errors = $(jq.argv -r -L $(dir $(amk.schema.jq)),$(amk.schema.prog),$(call amk.schema.input,$(1),$(2)))
amk.schema.refuse = $(if $(m5[3]),$(error $(1): does not meet $(call amk.schema.name,$(2)): $(m5[3])))
amk.schema.check = $(call amk.schema.refuse,$(1),$(3),$(call amk.schema.errors,$(2),$(3)))
amk.schema.text = $(if $(amk.schema.jq),$(call amk.schema.check,$(1),$(2),$(call amk.schema.file,$(3),$(1))))
$(amk.fxn! amk.schema.text)

# A define checked the same way, its body read as JSON5; an empty body is no data.
amk.val.schema = $(if $(strip $(value $(1))),$(amk.schema.text $(1), $(amk.val.json5 $(1)), $(2)))
$(amk.fxn! amk.val.schema)

# The value marks above a target: a file, or output kept for one run only.
amk.file = .AMK_FILE: $(1)
amk.nocache = .AMK_NOCACHE: $(1)

# amk is a stacked engine, named like a row for a library to find.
amk.__version__ := $(.AMK_VERSION)

# The stacked-engine interface: decorator and function suffixes, - for none.
amk.stacked.decorators := .target .import.target - .argv .import .exec
amk.stacked.functions := - .exec .ns
amk.stacked.engines :=
amk.data.engines :=

# A stacked engine defining every workspace function is of the data variety.
amk.stacked.data.functions := .create .version .wait
amk.stacked.has.data = $(if $(strip $(foreach f,$(amk.stacked.data.functions), \
  $(if $(call amk.stacked.has.fn,$(1),$(f)),,$(f)))),,$(1))
amk.stacked.name = $(1)$(patsubst -,,$(2))
amk.stacked.has.dec = $(or \
  $(filter $(call amk.stacked.name,$(1),$(2))*,$(amk.__fxns__)), \
  $(filter-out undefined,$(origin $(call amk.stacked.name,$(1),$(2))_star)))
amk.namespaces :=
amk.stacked.has.fn = $(or \
  $(filter $(call amk.stacked.name,$(1),$(2)),$(amk.__fxns__)), \
  $(amk.fxn? $(call amk.stacked.name,$(1),$(2))), \
  $(filter-out undefined,$(origin amk.fxn.$(call amk.stacked.name,$(1),$(2)))), \
  $(and $(filter .exec,$(2)),$(filter $(1),$(amk.namespaces))))
amk.stacked.missing = $(error stacked engine $(1) does not define $(2))
amk.stacked.stub = $$(call amk.stacked.missing,$(1),@$(2))
amk.stacked.alias = $(if $(call amk.stacked.has.dec,$(1),.$(2)),, \
  $(eval $(1).$(2)_star = $(value $(1).$(3)_star)))
# A stub is unexported, since exporting it to a recipe would expand it.
amk.stacked.fill.dec = $(if $(call amk.stacked.has.dec,$(1),$(2)),, \
  $(eval $(call amk.stacked.name,$(1),$(2))_star = \
    $(call amk.stacked.stub,$(1),$(call amk.stacked.name,$(1),$(2)))) \
  $(eval unexport $(call amk.stacked.name,$(1),$(2))_star))
amk.stacked.fill.fn = $(if $(call amk.stacked.has.fn,$(1),$(2)),, \
  $(amk.fxn! $(call amk.stacked.name,$(1),$(2)),amk.stacked.missing,$(1), \
    $(call amk.stacked.name,$(1),$(2))))

# The interface check: a target form present, the two aliased, every other form stubbed.
amk.engine.check = $(strip \
  $(if $(or $(call amk.stacked.has.dec,$(1),.target), \
    $(call amk.stacked.has.dec,$(1),.import.target)),, \
    $(error stacked engine $(1) does not define @$(1).target)) \
  $(call amk.stacked.alias,$(1),target,import.target) \
  $(call amk.stacked.alias,$(1),import.target,target) \
  $(foreach f,$(amk.stacked.decorators),$(call amk.stacked.fill.dec,$(1),$(f))) \
  $(foreach f,$(amk.stacked.functions),$(call amk.stacked.fill.fn,$(1),$(f))))

# A user-defined engine's row: the keys the registration takes, and one keyword argument recorded under the row after its key is checked.
amk.engines :=
amk.engine.keys := guest aliases language implementation version deadline jit.env jit.build
amk.engine.key = $(if $(findstring =,$(1)),$(firstword $(subst =, ,$(1))))
amk.engine.take = $(foreach k,$(call amk.engine.key,$(2)), \
  $(if $(filter $(k),$(amk.engine.keys)),$(eval amk.engine.$(1).$(k) := $(patsubst $(k)=%,%,$(2))), \
    $(error amk.engine: $(1): unknown key $(k); one of $(amk.engine.keys))))
amk.engine.arg = $(if $(call amk.engine.key,$(2)),$(call amk.engine.take,$(1),$(2)), \
  $(error amk.engine: $(1): $(2) is not key=value; the keys are $(amk.engine.keys)))

# A field's default when the keyword was not given: a define that exists by convention, or nothing.
amk.engine.define = $(if $(filter undefined,$(origin $(1))),,$(1))
amk.engine.default = $(if $(filter undefined,$(origin amk.engine.$(1).$(2))),$(eval amk.engine.$(1).$(2) := $(3)))

# A library registers its engine once, after its definitions: the row's fields as keywords, the guest it runs on, and, for a guest that imports modules, the jit interface. A jit guest's library makes the namespace and the decorators before the interface check.
define amk.engine
$(strip \
  $(if $(filter $(1),$(.ENGINES) $(amk.engines)),$(error amk.engine: $(1) is already an engine)) \
  $(foreach i,2 3 4 5 6 7 8 9,$(if $(filter undefined,$(origin $(i))),,$(if $(strip $($(i))),$(call amk.engine.arg,$(1),$(strip $($(i))))))) \
  $(if $(filter undefined,$(origin amk.engine.$(1).guest)),$(error amk.engine: $(1): guest= is required, the engine it runs on)) \
  $(foreach g,$(amk.engine.$(1).guest), \
    $(if $(filter $(g),$(.ENGINES) amk),,$(error amk.engine: $(1): guest $(g) is not an engine in this build; one of $(.ENGINES) amk)) \
    $(call amk.engine.default,$(1),aliases,) \
    $(call amk.engine.default,$(1),language,$(1)) \
    $(call amk.engine.default,$(1),implementation,$(g)) \
    $(call amk.engine.default,$(1),version,$($(g).__version__)) \
    $(call amk.engine.default,$(1),deadline,) \
    $(call amk.engine.default,$(1),jit.env,$(call amk.engine.define,Dockerfile.$(1))) \
    $(call amk.engine.default,$(1),jit.build,$(call amk.engine.define,$(1).build)) \
    $(foreach e,$(1) $(amk.engine.$(1).aliases), \
      $(if $(filter-out undefined,$(origin amk.engine.ext.$(e))),$(error amk.engine: $(1): $(e) is already claimed by $(amk.engine.ext.$(e)))) \
      $(if $(and $(filter-out $(1),$(e)),$(filter-out undefined,$(origin $(e).__version__))),$(error amk.engine: $(1): alias $(e) is an engine already)) \
      $(eval amk.engine.ext.$(e) := $(1))) \
    $(if $(filter undefined,$(origin $(1).__version__)),$(eval $(1).__version__ := $(amk.engine.$(1).version))) \
    $(if $(filter wasm,$(g)), \
      $(if $(amk.engine.$(1).jit.build),,$(error amk.engine: $(1): a wasm guest imports modules; give jit.build=, the compile command, or define $(1).build)) \
      $(if $(filter undefined,$(origin wasm.engine)),$(error amk.engine: $(1): load wasm before a wasm guest)) \
      $(call wasm.engine,$(1)), \
      $(if $(or $(amk.engine.$(1).jit.env),$(amk.engine.$(1).jit.build)),$(error amk.engine: $(1): jit is for a guest that imports modules, and $(g) imports text))) \
    $(call amk.engine.check,$(1)) \
    $(if $(call amk.stacked.has.data,$(1)),$(eval amk.data.engines += $(1))) \
    $(eval amk.engines += $(1)) \
    $(eval amk.stacked.engines += $(1))))
endef
$(amk.fxn! amk.engine)

# The decorator form: the row as a json object in a define named after the engine, its keys the registration's, read by jq into the same call.
amk.engine.spec.argv := -r
amk.engine.spec.jq := to_entries | map("\(.key)=\(.value)") | join(", ")
amk.engine.spec.line = $$(amk.engine $(1), $(amk.engine.spec.kvs))
define amk.engine.spec_star
$(strip \
  $(if $(filter jq,$(.ENGINES)),,$(error @amk.engine.spec: $(1): the jq engine is not in this build)) \
  $(eval amk.engine.spec.kvs := $(jq.argv* amk.engine.spec.argv, amk.engine.spec.jq, $(1))) \
  $(if $(amk.engine.spec.kvs),,$(error @amk.engine.spec: $(1): the body is not a json object)) \
  $(eval $(call amk.engine.spec.line,$(1))))
endef

# Make itself is the engine amklang; both target names are the amk.target rewrite, so these macros only mark the forms defined and are never called.
amklang.target_star =
amklang.import.target_star =
amklang.import_star = $(eval $(amk.val.dedent $(1)))
# The exec and argv decorators run the define at parse time in a fork and print what it printed; nothing comes back into this make.
amklang.print = $(if $(1),$(info $(1)))
amklang.exec_star = $(call amklang.print,$(amklang.exec $(amk.val.dedent $(1))))
amklang.argv_star = $(call amklang.print,$(amklang.argv $(2),$(amk.val.dedent $(1))))
$(amk.engine amklang, guest=amk, language=make, implementation=amk)

# A payload library by name, once: make's own under lib/amk/, else a topic, else topic/part a part of one; load shares the lookup.
amk.lib.roots = $(amk.lib.roots )
amk.lib.path = $(firstword $(foreach r,$(amk.lib.roots), \
  $(wildcard $(r)/amk/$(1).amk) $(wildcard $(r)/amk/$(1).mk) $(wildcard $(r)/$(1)/init.amk) \
  $(if $(findstring /,$(1)),$(wildcard $(r)/$(1).amk))))
amk.lib = $(or $(call amk.lib.path,$(1)), \
  $(error amk.include: no library named $(1) in the payload))
amk.included :=
amk.loaded :=
amk.include.names = $(strip $(foreach i,1 2 3 4 5 6 7 8 9, \
  $(if $(filter undefined,$(origin $(i))),,$($(i)))))
amk.include = $(foreach n,$(amk.include.names), \
  $(if $(filter $(n),$(amk.included)),, \
    $(eval amk.included += $(n))$(eval include $(call amk.lib,$(n)))))
$(amk.fxn! amk.include)

# A topic's parts from the folder of the init including them, never another root's, each once and recorded as loaded.
amk.include.submodules = $(foreach d,$(dir $(lastword $(MAKEFILE_LIST))),$(foreach p,$(2), \
  $(if $(filter $(1)/$(p),$(amk.included)),, \
    $(eval amk.included += $(1)/$(p)) \
    $(eval .LOADED += $(d)$(p).amk) \
    $(eval include $(d)$(p).amk))))
$(amk.fxn! amk.include.submodules)

# m5, the templating substrate, for every makefile and for what decorators emit.
$(amk.include m5)

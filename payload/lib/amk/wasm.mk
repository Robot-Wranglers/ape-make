#
# payload/lib/amk/wasm.mk:
#  the jit interface behind a user-defined engine whose guest is wasm. The
#  row amk.engine recorded names a Dockerfile define and a compile command
#  over make's own $< and $@; wasm.engine gives the engine a namespace and
#  its two decorators, each source define built once under wasm.dir. Those
#  two are the interface; a member spelled wasm._x is the library's own.
#
$(amk.require wasm)

wasm.dir ?= .amk/wasm

# The row's jit fields: the Dockerfile define, if any, and the command define.
wasm._env = $(amk.engine.$(1).jit.env)
wasm._cmd = $(amk.engine.$(1).jit.build)

# The module's directory, named by the inputs' checksum, and its files.
wasm._key = $(cksum.hex \
  $(if $(call wasm._env,$(1)),$(value $(call wasm._env,$(1)))) \
  $(value $(call wasm._cmd,$(1))) \
  $(value $(2)))
wasm._where = $(wasm.dir)/$(1)/$(call wasm._key,$(1),$(2))
wasm._module = $(call wasm._where,$(1),$(2))/$(basename $(2)).wasm
wasm._goal = $(1).build/$(notdir $(call wasm._where,$(1),$(2)))/$(basename $(2))

# The container the command runs in, cwd mounted at its own path, or none.
wasm._in = $(if $(call wasm._env,$(1)), \
  docker run -i --rm -v "$(CURDIR):$(CURDIR)" -w "$(CURDIR)" \
    `docker build -q - < $(2)/Dockerfile`)

# The command with the source and the module in place of its dollars.
wasm._script = $(subst $$<,$(2)/$(3), \
  $(subst $$@,$(call wasm._module,$(1),$(3)), \
    $(amk.val.dedent $(call wasm._cmd,$(1)))))

# One module's rules: the file in its directory, and a goal answering its path.
define wasm._rules
.AMK_FILE: $(3)
$(3): $(2)/$(4)
	$(call wasm._in,$(1),$(2)) sh $(2)/build.sh
$(call wasm._goal,$(1),$(4)): $(3)
	echo $$<
endef

# The inputs in the module's directory, written when absent, then the rules.
define wasm._prepare
$(strip \
  $(if $(filter undefined,$(origin $(2))), \
    $(error $(1).import: no define named $(2))) \
  $(foreach d,$(call wasm._where,$(1),$(2)), \
    $(shell mkdir -p $(d)) \
    $(if $(call wasm._env,$(1)), \
      $(if $(wildcard $(d)/Dockerfile),, \
        $(file >$(d)/Dockerfile,$(amk.val.dedent $(call wasm._env,$(1)))))) \
    $(if $(wildcard $(d)/$(2)),,$(file >$(d)/$(2),$(amk.val.dedent $(2)))) \
    $(if $(wildcard $(d)/build.sh),, \
      $(file >$(d)/build.sh,$(call wasm._script,$(1),$(d),$(2)))) \
    $(eval $(call wasm._rules,$(1),$(d),$(call wasm._module,$(1),$(2)),$(2)))))
endef

# The import decorator: the module built as needed, then imported.
define wasm._import
$(strip \
  $(call wasm._prepare,$(1),$(2)) \
  $(if $(amk.goal $(call wasm._goal,$(1),$(2))),) \
  $(wasm.ns $(1), import, $(call wasm._module,$(1),$(2))))
endef

# The target decorator: a phony target of the stem that builds and runs it.
wasm._run = $(basename $(2)): $(call wasm._module,$(1),$(2)) ; \
  $$(MAKE) --wasm $$<
define wasm._target
$(strip \
  $(call wasm._prepare,$(1),$(2)) \
  $(eval $(call wasm._run,$(1),$(2))))
endef

# The one-shot form: the define built as needed and run as a program, stdout the value.
define wasm._oneshot
$(strip \
  $(call wasm._prepare,$(1),$(2)) \
  $(if $(amk.goal $(call wasm._goal,$(1),$(2))),) \
  $(wasm $(call wasm._module,$(1),$(2))))
endef

# The jit implementation amk.engine calls for a wasm guest.
define wasm.engine
$(strip \
  $(wasm.ns.create $(1)) \
  $(amk.fxn! $(1),wasm._oneshot,$(1)) \
  $(eval amk.fxn.$(1) := wasm._oneshot) \
  $(eval $(1).import_star = $$(call wasm._import,$(1),$$(1))) \
  $(eval $(1).target_star = $$(call wasm._target,$(1),$$(1))))
endef

# via/amk: amk, make with gawk, jq and lua linked in, as an actually portable executable.
SHELL := bash
.SHELLFLAGS ?= -euo pipefail -c
MAKEFLAGS = -s -S --warn-undefined-variables
HERE := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))

# The version the banner and .AMK_VERSION carry comes from the nearest v-tag; make's own stays 4.4.1 on the first line.
amk.describe := $(shell git -C $(HERE) describe --tags --always --dirty --match 'v*' 2>/dev/null)
amk.version  ?= $(or $(patsubst v%,%,$(filter v%,$(amk.describe))),0.0.0-$(or $(amk.describe),dev))

# Every input is pinned by version and digest; upstream ships no checksum files.
make.version := 4.4.1
make.tarball := make-$(make.version).tar.gz
make.url     := https://ftp.gnu.org/gnu/make/$(make.tarball)
make.sha256  := dd16fb1d67bfab79a72f5e8390735c49e3e8e70b4945a15ab1f81ddb78658fb3

gawk.version := 5.3.1
gawk.tarball := gawk-$(gawk.version).tar.xz
gawk.url     := https://ftp.gnu.org/gnu/gawk/$(gawk.tarball)
gawk.sha256  := 694db764812a6236423d4ff40ceb7b6c4c441301b72ad502bb5c27e00cd56f78

jq.version := 1.7.1
jq.tarball := jq-$(jq.version).tar.gz
jq.url     := https://github.com/jqlang/jq/releases/download/jq-$(jq.version)/$(jq.tarball)
jq.sha256  := 478c9ca129fd2e3443fe27314b455e211e0d8c60bc8ff7df703873deeee580c2

lua.version := 5.4.8
lua.tarball := lua-$(lua.version).tar.gz
lua.url     := https://www.lua.org/ftp/$(lua.tarball)
lua.sha256  := 4f18ddae154e793e46eeab727c59ef1c0c0c2b744e7b94219710d76f530629ae

# The ccrma tarball is a rolling snapshot, so s7 pins a commit archive from its gitlab instead.
s7.version := 11.9
s7.commit  := 6ce8ff093a6e1059c1f95f481286a9cf051f0a69
s7.tarball := s7-$(s7.version).tar.gz
s7.url     := https://cm-gitlab.stanford.edu/bil/s7/-/archive/$(s7.commit)/s7-$(s7.commit).tar.gz
s7.sha256  := bdf49850444252e7ffada4b6497278697b335580d5611cb1f336a6084828b8fb

micropython.version := 1.29.0
micropython.tarball := micropython-$(micropython.version).tar.xz
micropython.url     := https://github.com/micropython/micropython/releases/download/v$(micropython.version)/$(micropython.tarball)
micropython.sha256  := d925a7c664e79a2bdf3dfcb285ba5e2237041cc35a0bd4ee573b6c5711efeca0

wasm3.version := 0.9.0
wasm3.tarball := wasm3-$(wasm3.version).tar.gz
wasm3.url     := https://github.com/wasm3/wasm3/archive/refs/tags/v$(wasm3.version).tar.gz
wasm3.sha256  := cab79ce74bcac25bbf80b5ebe14af9795b9bac30b05ee8f620a3bc8002f3b8e6

quickjs.version := 2026-06-04
quickjs.tarball := quickjs-$(quickjs.version).tar.xz
quickjs.url     := https://bellard.org/quickjs/$(quickjs.tarball)
quickjs.sha256  := b376e839b322978313d929fd20663b11ba58b75df5a46c126dd19ea2fa70ad2a

cosmocc.version := 4.0.2
cosmocc.zip     := cosmocc-$(cosmocc.version).zip
cosmocc.url     := https://cosmo.zip/pub/cosmocc/$(cosmocc.zip)
cosmocc.sha256  := 85b8c37a406d862e656ad4ec14be9f6ce474c1b436b9615e91a55208aced3f44

# Tools are released cosmos binaries, zipped into the payload unchanged; patch 0012 puts them first on PATH.
cosmos.version := 4.0.2
tools          := sed bash
sed.file       := sed-$(cosmos.version).ape
sed.url        := https://cosmo.zip/pub/cosmos/v/$(cosmos.version)/bin/sed
sed.sha256     := 343f00b93739d4ff145c44e28a07889591425cb766bcf7d9e4534708d6fc6cd8
# The shell every makefile under amk names as bash, and the one core forks by default.
bash.file      := bash-$(cosmos.version).ape
bash.url       := https://cosmo.zip/pub/cosmos/v/$(cosmos.version)/bin/bash
bash.sha256    := 5de7cab218c12583413c541363848bc278e8f48dba07d96b9f5790ef40b72e3e

# Libraries are makefiles zipped into the payload under lib/ and read in place by an include; none loads unless a makefile asks.
gmsl.version := 1.2.4
gmsl.tarball := gmsl-$(gmsl.version).tar.gz
gmsl.url     := https://github.com/jgrahamc/gmsl/archive/refs/tags/v$(gmsl.version).tar.gz
gmsl.sha256  := 8f1d7a6a4bb76f4e934b2a1376a9ab0da0d84971e19edf0005689d67feb98a60
gmsl.files   := gmsl __gmsl

# amk's own payload members: the prelude patch 0034 reads before every makefile.
payload.files := payload/__init__.mk
# The mip library needs the micropython and jq engines, so it ships only in a build that has both.
payload.mip = $(if $(filter-out $(engines),micropython jq),,payload/lib/mip.mk)

# dkjson is one lua file, and its "tarball" is that file; it lands in the payload for require.
dkjson.version := 2.8
dkjson.tarball := dkjson-$(dkjson.version).lua
dkjson.url     := http://dkolf.de/dkjson-lua/$(dkjson.tarball)
dkjson.sha256  := eb3bf160688fb395a2db6bc52eeff4f7855a6321d2b41bdc754554d13f4e7d44
dkjson.files   := dkjson.lua
libs.all     := gmsl dkjson

# The default set is linked in; with adds an opt-in engine to a build, and without leaves any engine out of one.
engines.all   := gawk jq lua s7 micropython wasm3 quickjs
engines.optin := wasm3
with          ?=
without       ?=
ifneq ($(filter-out $(engines.all),$(with) $(filter-out $(libs.all),$(without))),)
  $(error with or without names $(filter-out $(engines.all),$(with) $(filter-out $(libs.all),$(without))), which is not an engine or library -- choose from $(engines.all), or leave out $(libs.all))
endif
libs := $(filter-out $(without),$(libs.all))
engines.default := $(filter-out $(engines.optin),$(engines.all))
engines         := $(filter-out $(without),$(filter $(engines.default) $(with),$(engines.all)))
ifeq ($(engines),)
  $(error without leaves no engine -- amk is make with guests linked in, and without is not the way to build stock make)
endif

# An engine left out is absent from the builtins and from the feature list, not a stub that fails late.
gawk.define := AMK_ENGINE_GAWK
jq.define   := AMK_ENGINE_JQ
lua.define  := AMK_ENGINE_LUA
s7.define   := AMK_ENGINE_S7
micropython.define := AMK_ENGINE_MICROPY
wasm3.define := AMK_ENGINE_WASM3
quickjs.define := AMK_ENGINE_QUICKJS
gawk.feature := awk
jq.feature   := jq
lua.feature  := lua
s7.feature   := s7
micropython.feature := micropy
wasm3.feature := wasm
quickjs.feature := js
# Only the ones that carry a cli answer to a name of their own; the binary holds the others as libraries.
gawk.alias := awk
jq.alias   := jq
wasm3.alias := wasm3
engines.defs     = $(foreach e,$(engines),-D$($(e).define))
version.defs     = -DAMK_VERSION=$(amk.version) $(if $(flavor),-DAMK_FLAVOR=$(flavor))
engines.features = $(foreach e,$(engines),$($(e).feature))
engines.aliases  = $(foreach e,$(engines),$($(e).alias))

tools.files := $(foreach t,$(tools),$($(t).file))
libs.tarballs := $(foreach l,$(libs),$($(l).tarball))
deps.files  := $(make.tarball) $(foreach e,$(engines),$($(e).tarball)) $(tools.files) $(libs.tarballs) $(cosmocc.zip)

# The toolchain unpacks beside the downloads; name an installed copy here to skip that.
cosmocc.dir ?= $(HERE)cosmocc
cosmocc.env = PATH="$(cosmocc.dir)/bin:$$PATH" CC=cosmocc AR=cosmoar RANLIB=cosmoranlib
sha256   := $(shell command -v sha256sum 2>/dev/null || echo 'shasum -a 256')
# GNU patch everywhere, strict: macOS names it gpatch, and a hunk that needs fuzz fails instead of landing near its mark.
PATCH    ?= $(shell command -v gpatch 2>/dev/null || echo patch) --fuzz=0
jobs     := $(shell nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)
# A consumer fits make to itself with a series of its own applied after this one; flavor names that build so it shares the guests but not the patched tree or the artifact.
patch.dirs ?= patches
flavor     ?=
ifneq ($(filter-out patches,$(patch.dirs))$(flavor),)
  ifeq ($(filter-out patches,$(patch.dirs)),)
    $(error flavor $(flavor) names no series -- patch.dirs must add a directory after patches)
  endif
  ifeq ($(flavor),)
    $(error patch.dirs adds $(filter-out patches,$(patch.dirs)) without a flavor -- name the build so it does not overwrite the plain one)
  endif
endif
suffix   := $(if $(flavor),-$(flavor))
patches  := $(foreach d,$(patch.dirs),$(abspath $(wildcard $(d)/*.patch)))
make.src := src/make-$(make.version)$(suffix)
gawk.src := src/gawk-$(gawk.version)
jq.src   := src/jq-$(jq.version)
lua.src  := src/lua-$(lua.version)
s7.src   := src/s7-$(s7.version)
micropython.src := src/micropython-$(micropython.version)
wasm3.src := src/wasm3-$(wasm3.version)
quickjs.src := src/quickjs-$(quickjs.version)
gmsl.src  := src/gmsl-$(gmsl.version)
dkjson.src := src/dkjson-$(dkjson.version)
# The native make is the debug loop by default; pass native.cflags=-O2 to compare it fairly.
native.cflags ?= -O0 -g

# A guest is hidden, not renamed: one visible entry point, exit routed to make's amk_exit.
guest.cflags = -O2 -fno-common -fvisibility=hidden -Wno-implicit-function-declaration \
  -Dmain=__attribute__\(\(visibility\(\"default\"\)\)\)$(1)_main -Dexit=amk_exit
gawk.configure := --disable-dependency-tracking --disable-nls --disable-mpfr --without-readline --disable-extensions
jq.configure   := --disable-dependency-tracking --disable-shared --enable-static --with-oniguruma=builtin --disable-docs --disable-maintainer-mode
gawk.objdirs   := . support support/malloc
jq.objdirs     := src src/decNumber modules/oniguruma/src
lua.objdirs    := .
# Lua ships no configure: its rule compiles the library by hand, less the two files with a main.
lua.cflags     := -DLUA_USE_POSIX
lua.exclude    := lua.c luac.c
s7.objdirs     := .
# s7 is one translation unit and ships no main of its own; its c loader wants dlopen, which an ape has not.
s7.cflags      := -DWITH_C_LOADER=0
# MicroPython compiles through its own makefiles, driven by guest/micropy.mk, and its objects land in these directories of the build tree.
micropython.objdirs := . py extmod shared/runtime shared/libc shared/timeutils ports/unix extmod/mbedtls lib/mbedtls/library lib/mbedtls_errors
# Python-side modules zipped as source under lib/, as payload path and tarball path: asyncio's Python half, and ssl, requests, and mip from micropython-lib.
micropython.pylib := $(foreach f,__init__ core event funcs lock stream task,asyncio/$(f).py:extmod/asyncio/$(f).py) \
  ssl.py:lib/micropython-lib/python-stdlib/ssl/ssl.py \
  requests/__init__.py:lib/micropython-lib/python-ecosys/requests/requests/__init__.py \
  mip/__init__.py:lib/micropython-lib/micropython/mip/mip/__init__.py
# wasm3's own cli is the guest, built the way its cosmopolitan script builds it, with the built-in wasi and no libuv.
wasm3.objdirs  := .
wasm3.cflags   := -fno-strict-aliasing -fomit-frame-pointer -fno-stack-check -fno-stack-protector \
                  -Dd_m3PreferStaticAlloc -Dd_m3HasTypedRefs=1 -Dd_m3HasWASI
# quickjs ships a Makefile that only builds its cli, so its rule compiles the engine and its std library by hand, less the programs with a main.
quickjs.objdirs := .
quickjs.cflags  := -D_GNU_SOURCE -DCONFIG_VERSION=\"$(quickjs.version)\" -fwrapv
quickjs.exclude := qjs.c qjsc.c run-test262.c unicode_gen.c
# cosmocc refuses an argument with a space, and jq passes its package string on the command line.
gawk.defs :=
jq.defs = DEFS="$$(sed -n 's/^DEFS = //p' Makefile | sed 's/jq\\ $(jq.version)/jq-$(jq.version)/')"
gawk.objcheck := *.o
jq.objcheck   := src/*.o
lua.objcheck  := *.o
s7.objcheck   := *.o
micropython.objcheck := py/*.o
wasm3.objcheck := *.o
quickjs.objcheck := *.o
# Per-guest hooks on the partial link and the guest compile: extra ld flags, compile flags in place of the shared ones, objcopy renames, and objects to leave out as alternatives appended to the conftest filter.
gawk.ldflags   :=
jq.ldflags     :=
lua.ldflags    :=
s7.ldflags     :=
micropython.ldflags :=
wasm3.ldflags  :=
quickjs.ldflags :=
gawk.guestflags :=
jq.guestflags   :=
lua.guestflags  :=
s7.guestflags   :=
micropython.guestflags :=
wasm3.guestflags :=
quickjs.guestflags :=
gawk.objrename :=
jq.objrename   :=
lua.objrename  :=
s7.objrename   :=
micropython.objrename :=
wasm3.objrename :=
quickjs.objrename :=
gawk.objskip   :=
jq.objskip     :=
lua.objskip    :=
s7.objskip     :=
micropython.objskip :=
wasm3.objskip  :=
quickjs.objskip :=

# out/bin and out/bin-native each hold one artifact beside its argv[0] aliases; everything rebuildable stays under build/.
guests.ape    := build/guests/ape
guests.host   := build/guests/native
bin           := out/bin$(suffix)
bin.host      := out/bin-native$(suffix)
artifact.ape  := $(bin)/amk
artifact.host := $(bin.host)/amk
# The deliverable lands beside this Makefile, where a caller can find it without knowing the layout.
deliverable   := amk

# Where install lands: the user's own bin, or the system bin every login shell searches; either takes a bindir override on the command line.
os := $(shell uname -s)
install.os    := $(filter Darwin Linux FreeBSD OpenBSD NetBSD,$(os))
bindir.user   ?= $(HOME)/.local/bin
bindir.global ?= /usr/local/bin

# Progress speaks on stderr under one label, leaving stdout to whatever a target produces.
tty.bold := $(shell test -t 2 && tput bold 2>/dev/null)
tty.dim  := $(shell test -t 2 && tput dim 2>/dev/null)
tty.red  := $(shell test -t 2 && tput setaf 1 2>/dev/null)
tty.off  := $(shell test -t 2 && tput sgr0 2>/dev/null)
log  = printf '$(tty.dim)via/amk$(tty.off) $(tty.bold)%s$(tty.off) %s\n' "$(strip $(1))" "$(strip $(2))" >&2
die  = { printf '$(tty.red)via/amk $(strip $(1)) failed$(tty.off) %s\n' "$(strip $(2))" >&2; exit 1; }
# One row of the stat report: kind, path, size if it exists, and what it is.
show = printf '%-8s %-24s %-6s %s\n' '$(strip $(1))' '$(strip $(2))' \
         "$$(du -sh '$(strip $(2))' 2>/dev/null | cut -f1 || echo -)" '$(strip $(3))'

.PHONY: amk deps verify toolchain patch build build.native guests guests.native smoke smoke.native smoke.readme smoke.demos test test.native build.docker smoke.docker install install.user install.global release release.preflight release.watch stat st status clean help FORCE
.DEFAULT_GOAL := amk

help:
	@# List the targets.
	$(call log, help, usage: make amk for the deliverable -- make stat says what is built)
	$(call log, help, engines $(engines.default) are linked in by default and $(engines.optin) on request -- with='$(firstword $(engines.optin))' adds one and without='$(firstword $(engines.all))' leaves one out)
	grep -E '^[a-z][a-z. ]*:([^=]|$$)' $(lastword $(MAKEFILE_LIST)) | cut -d: -f1 | tr ' ' '\n' | sort | tr '\n' ' '; echo

#░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░

amk:
	@# The deliverable, from nothing: a clean rebuild that lands ./amk once smoke passes.
	$(call log, amk, clean rebuild of $(deliverable) -- expect several minutes)
	$(MAKE) clean
	$(MAKE) deps patch build smoke
	install -m 0755 $(artifact.ape) $(deliverable)
	$(call log, amk, build succeeded -- landed at ./$(deliverable))

install: install.user
	@# The user's bin by default; install.global takes the system bin and asks for sudo when it needs it.
install.user install.global: install.%:
	$(call log, install, $(deliverable) into $(bindir.$*) on $(os))
	[ -x $(deliverable) ] || $(call die, install, no ./$(deliverable) here -- run make $(deliverable) first)
	[ -n "$(install.os)" ] || $(call die, install, $(os) is not a system this knows -- pass bindir.$*=DIR to say where)
	as=; [ -w "$(bindir.$*)" ] || [ -w "$$(dirname "$(bindir.$*)")" ] || { [ $* = global ] && as=sudo; }; \
	$$as mkdir -p "$(bindir.$*)" && $$as install -m 0755 $(deliverable) "$(bindir.$*)/$(notdir $(deliverable))" \
	  || $(call die, install, could not write $(bindir.$*)/$(notdir $(deliverable)))
	case ":$$PATH:" in *":$(bindir.$*):"*) ;; *) $(call log, install, $(bindir.$*) is not on PATH -- add it in the shell rc);; esac
	$(call log, install, $(bindir.$*)/$(notdir $(deliverable)) is ready)

#░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░

deps: $(deps.files) verify
	@# Fetch every pinned input that is not already here, then verify all of them.

$(make.tarball): url := $(make.url)
$(gawk.tarball): url := $(gawk.url)
$(jq.tarball): url := $(jq.url)
$(lua.tarball): url := $(lua.url)
$(s7.tarball): url := $(s7.url)
$(micropython.tarball): url := $(micropython.url)
$(wasm3.tarball): url := $(wasm3.url)
$(quickjs.tarball): url := $(quickjs.url)
$(sed.file): url := $(sed.url)
$(bash.file): url := $(bash.url)
$(gmsl.tarball): url := $(gmsl.url)
$(dkjson.tarball): url := $(dkjson.url)
$(cosmocc.zip): url := $(cosmocc.url)
$(deps.files):
	$(call log, deps, fetching $@ from $(url))
	curl -fsSL "$(url)" -o "$@.part" \
	  || $(call die, deps, could not fetch $(url) -- partial file left at $@.part)
	mv "$@.part" "$@"

verify:
	@# Check every download against its pinned digest.
	$(call log, verify, checking $(words $(deps.files)) downloads against their pinned digests)
	printf '%s  %s\n' \
	  $(make.sha256) $(make.tarball) \
	  $(foreach e,$(engines),$($(e).sha256) $($(e).tarball)) \
	  $(foreach t,$(tools),$($(t).sha256) $($(t).file)) \
	  $(foreach l,$(libs),$($(l).sha256) $($(l).tarball)) \
	  $(cosmocc.sha256) $(cosmocc.zip) \
	| $(sha256) -c - \
	  || $(call die, verify, a download does not match its pin -- remove the file named above and rerun make deps)

toolchain: $(cosmocc.dir)/bin/cosmocc
	@# Unpack cosmocc beside the downloads unless cosmocc.dir names an installed copy.
$(HERE)cosmocc/bin/cosmocc: $(cosmocc.zip)
	$(call log, toolchain, unpacking $(cosmocc.zip) into $(HERE)cosmocc)
	mkdir -p $(HERE)cosmocc
	unzip -q -o $(cosmocc.zip) -d $(HERE)cosmocc
	chmod +x $(HERE)cosmocc/bin/*
	touch $@

#░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░

patch: $(make.src)
	@# Unpack make and apply the patch series in order, into a fresh tree.
$(make.src): $(make.tarball) $(patch.dirs) $(patches)
	$(call log, patch, unpacking $(make.tarball) into $@$(if $(flavor), for flavor $(flavor)))
	rm -rf $@ && mkdir -p $@
	tar xzf $(make.tarball) -C $@ --strip-components=1
	for p in $(patches); do \
	  $(call log, patch, applying $${p#$(HERE)}); \
	  $(PATCH) -d $@ -p1 -l -i "$$p" \
	    || $(call die, patch, $${p#$(HERE)} does not apply to make $(make.version) -- rerun after make clean); \
	done
	touch $@

$(gawk.src): $(gawk.tarball)
	$(call log, patch, unpacking $(gawk.tarball) into $@ unpatched)
	mkdir -p src && tar xJf $(gawk.tarball) -C src && touch $@
$(jq.src): $(jq.tarball)
	$(call log, patch, unpacking $(jq.tarball) into $@ unpatched)
	mkdir -p src && tar xzf $(jq.tarball) -C src && touch $@
$(lua.src): $(lua.tarball)
	$(call log, patch, unpacking $(lua.tarball) into $@ unpatched)
	mkdir -p src && tar xzf $(lua.tarball) -C src && touch $@
$(s7.src): $(s7.tarball)
	$(call log, patch, unpacking $(s7.tarball) into $@ unpatched)
	mkdir -p $@ && tar xzf $(s7.tarball) -C $@ --strip-components=1 && touch $@
# The release tarball carries every port and vendored library; amk's port needs the core, the modules, the shared helpers, six in-tree libraries with mbedtls for ssl, and what it borrows from unix.
micropython.parts := py extmod shared ports/unix/modos.c ports/unix/modtime.c ports/unix/modsocket.c ports/unix/mbedtls lib/mbedtls lib/mbedtls_errors lib/re1.5 lib/uzlib lib/crypto-algorithms lib/oofatfs $(foreach p,$(micropython.pylib),$(lastword $(subst :, ,$(p)))) LICENSE
$(micropython.src): $(micropython.tarball)
	$(call log, patch, unpacking $(words $(micropython.parts)) parts of $(micropython.tarball) into $@ unpatched)
	mkdir -p src && tar xJf $(micropython.tarball) -C src $(addprefix micropython-$(micropython.version)/,$(micropython.parts)) && touch $@
$(wasm3.src): $(wasm3.tarball) $(wildcard patches/wasm3/*.patch)
	$(call log, patch, unpacking $(wasm3.tarball) into $@ and applying patches/wasm3)
	rm -rf $@ && mkdir -p src && tar xzf $(wasm3.tarball) -C src
	for p in patches/wasm3/*.patch; do \
	  $(call log, patch, applying $$p); \
	  $(PATCH) -d $@ -p1 -l -i "$(HERE)$$p" \
	    || $(call die, patch, $$p does not apply to wasm3 $(wasm3.version)); \
	done
	touch $@
$(quickjs.src): $(quickjs.tarball)
	$(call log, patch, unpacking $(quickjs.tarball) into $@ unpatched)
	mkdir -p src && tar xJf $(quickjs.tarball) -C src && touch $@
$(gmsl.src): $(gmsl.tarball)
	$(call log, patch, unpacking $(gmsl.tarball) into $@ unpatched)
	mkdir -p src && tar xzf $(gmsl.tarball) -C src && touch $@
$(dkjson.src): $(dkjson.tarball)
	$(call log, patch, placing $(dkjson.tarball) into $@ unpatched)
	mkdir -p $@ && install -m 0644 $(dkjson.tarball) $@/dkjson.lua && touch $@

#░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░

guests: $(foreach e,$(engines),$(guests.ape)/$(e).o)
	@# Each guest as one fat relocatable with one global symbol, an input to the ape link.
guests.native: $(foreach e,$(engines),$(guests.host)/$(e).o)
	@# The same for the host toolchain.

# Lua's library files, our entry point, and nothing that carries a main of its own.
lua.compile = for c in $(HERE)$(lua.src)/src/*.c $(HERE)guest/lua_main.c; do \
                case " $(lua.exclude) " in *" $$(basename $$c) "*) continue;; esac; \
                $(1) $(call guest.cflags,lua) $(lua.cflags) -I$(HERE)$(lua.src)/src -I$(HERE)guest \
                  -c "$$c" -o "$$(basename $$c .c).o" || exit 1; \
              done

# s7's one source file and our entry point, both against the header beside them.
s7.compile = for c in $(HERE)$(s7.src)/s7.c $(HERE)guest/s7_main.c; do \
               $(1) $(call guest.cflags,s7) $(s7.cflags) -I$(HERE)$(s7.src) -I$(HERE)guest \
                 -c "$$c" -o "$$(basename $$c .c).o" || exit 1; \
             done

# MicroPython's own makefiles generate its headers and compile its objects, driven by guest/micropy.mk from guest/ where its config lives; the env, the compiler and the build dir are the arguments, and the version is told rather than asked of the enclosing checkout.
micropython.make = cd guest && env $(1) MAKEFLAGS=-s MICROPY_GIT_TAG=v$(micropython.version) make -f micropy.mk -j$(jobs) CC=$(2) \
                     MICROPYTHON_TOP=$(HERE)$(micropython.src) BUILD=$(HERE)$(3) \
                     CFLAGS_EXTRA='$(call guest.cflags,micropython)' objects
micropython.inputs := guest/micropy.mk guest/micropy_main.c guest/mpconfigport.h guest/mphalport.h guest/amk_guest.h

# wasm3's interpreter sources and its cli, whose main is renamed and kept visible like gawk's.
wasm3.compile = for c in $(HERE)$(wasm3.src)/source/*.c $(HERE)$(wasm3.src)/platforms/app/main.c; do \
                  $(1) $(call guest.cflags,wasm3) $(wasm3.cflags) -I$(HERE)$(wasm3.src)/source \
                    -c "$$c" -o "$$(basename $$c .c).o" || exit 1; \
                done

# quickjs's engine, its std library, and our entry point, less the programs that carry a main of their own.
quickjs.compile = for c in $(HERE)$(quickjs.src)/*.c $(HERE)guest/js_main.c; do \
                    case " $(quickjs.exclude) " in *" $$(basename $$c) "*) continue;; esac; \
                    $(1) $(call guest.cflags,quickjs) $(quickjs.cflags) -I$(HERE)$(quickjs.src) -I$(HERE)guest \
                      -c "$$c" -o "$$(basename $$c .c).o" || exit 1; \
                  done

build/gawk-ape/Makefile: $(gawk.src) $(cosmocc.dir)/bin/cosmocc
	$(call log, configure, gawk $(gawk.version) for cosmocc in $(@D))
	rm -rf $(@D) && mkdir -p $(@D)
	cd $(@D) && env $(cosmocc.env) $(HERE)$(gawk.src)/configure $(gawk.configure)
build/gawk-native/Makefile: $(gawk.src)
	$(call log, configure, gawk $(gawk.version) for the host compiler in $(@D))
	rm -rf $(@D) && mkdir -p $(@D)
	cd $(@D) && $(HERE)$(gawk.src)/configure $(gawk.configure)
build/jq-ape/Makefile: $(jq.src) $(cosmocc.dir)/bin/cosmocc
	$(call log, configure, jq $(jq.version) for cosmocc in $(@D))
	rm -rf $(@D) && mkdir -p $(@D)
	cd $(@D) && env $(cosmocc.env) RANLIB=true $(HERE)$(jq.src)/configure $(jq.configure)
build/jq-native/Makefile: $(jq.src)
	$(call log, configure, jq $(jq.version) for the host compiler in $(@D))
	rm -rf $(@D) && mkdir -p $(@D)
	cd $(@D) && $(HERE)$(jq.src)/configure $(jq.configure)

# A guest's own executable cannot link once main is renamed and hidden; only its objects are wanted.
build/%-native/.built: build/%-native/Makefile
	$(call log, guest, compiling $* for the host compiler -- log at $(@D)/build.log)
	cd $(@D) && MAKEFLAGS=-s make -k -j$(jobs) CFLAGS='$(call guest.cflags,$*)' $($*.defs) >build.log 2>&1 || true
	ls $(@D)/$($*.objcheck) >/dev/null 2>&1 \
	  || $(call die, guest, $* compiled no objects -- see the tail of $(@D)/build.log)
	touch $@
build/%-ape/.built: build/%-ape/Makefile
	$(call log, guest, compiling $* for cosmocc -- log at $(@D)/build.log)
	cd $(@D) && env $(cosmocc.env) MAKEFLAGS=-s make -k -j$(jobs) CFLAGS='$(or $($*.guestflags),$(call guest.cflags,$*))' $($*.defs) >build.log 2>&1 || true
	ls $(@D)/$($*.objcheck) >/dev/null 2>&1 \
	  || $(call die, guest, $* compiled no objects -- see the tail of $(@D)/build.log)
	touch $@

build/lua-native/.built: $(lua.src) guest/lua_main.c guest/amk_guest.h
	$(call log, guest, compiling lua for the host compiler -- log at $(@D)/build.log)
	rm -rf $(@D) && mkdir -p $(@D)
	cd $(@D) && $(call lua.compile,$${CC:-cc}) >build.log 2>&1 \
	  || $(call die, guest, lua did not compile -- see the tail of $(@D)/build.log)
	touch $@
build/lua-ape/.built: $(lua.src) guest/lua_main.c guest/amk_guest.h $(cosmocc.dir)/bin/cosmocc
	$(call log, guest, compiling lua for cosmocc -- log at $(@D)/build.log)
	rm -rf $(@D) && mkdir -p $(@D)
	cd $(@D) && env $(cosmocc.env) sh -c '$(call lua.compile,cosmocc)' >build.log 2>&1 \
	  || $(call die, guest, lua did not compile -- see the tail of $(@D)/build.log)
	touch $@

build/s7-native/.built: $(s7.src) guest/s7_main.c guest/amk_guest.h
	$(call log, guest, compiling s7 for the host compiler -- log at $(@D)/build.log)
	rm -rf $(@D) && mkdir -p $(@D)
	cd $(@D) && $(call s7.compile,$${CC:-cc}) >build.log 2>&1 \
	  || $(call die, guest, s7 did not compile -- see the tail of $(@D)/build.log)
	touch $@
build/s7-ape/.built: $(s7.src) guest/s7_main.c guest/amk_guest.h $(cosmocc.dir)/bin/cosmocc
	$(call log, guest, compiling s7 for cosmocc -- log at $(@D)/build.log)
	rm -rf $(@D) && mkdir -p $(@D)
	cd $(@D) && env $(cosmocc.env) sh -c '$(call s7.compile,cosmocc)' >build.log 2>&1 \
	  || $(call die, guest, s7 did not compile -- see the tail of $(@D)/build.log)
	touch $@

build/micropython-native/.built: $(micropython.src) $(micropython.inputs)
	$(call log, guest, compiling micropython for the host compiler -- log at $(@D)/build.log)
	rm -rf $(@D) && mkdir -p $(@D)
	( $(call micropython.make,,$${CC:-cc},$(@D)) ) >$(@D)/build.log 2>&1 \
	  || $(call die, guest, micropython did not compile -- see the tail of $(@D)/build.log)
	touch $@
build/micropython-ape/.built: $(micropython.src) $(micropython.inputs) $(cosmocc.dir)/bin/cosmocc
	$(call log, guest, compiling micropython for cosmocc -- log at $(@D)/build.log)
	rm -rf $(@D) && mkdir -p $(@D)
	( $(call micropython.make,$(cosmocc.env),cosmocc,$(@D)) ) >$(@D)/build.log 2>&1 \
	  || $(call die, guest, micropython did not compile -- see the tail of $(@D)/build.log)
	touch $@

build/wasm3-native/.built: $(wasm3.src)
	$(call log, guest, compiling wasm3 for the host compiler -- log at $(@D)/build.log)
	rm -rf $(@D) && mkdir -p $(@D)
	cd $(@D) && $(call wasm3.compile,$${CC:-cc}) >build.log 2>&1 \
	  || $(call die, guest, wasm3 did not compile -- see the tail of $(@D)/build.log)
	touch $@
build/wasm3-ape/.built: $(wasm3.src) $(cosmocc.dir)/bin/cosmocc
	$(call log, guest, compiling wasm3 for cosmocc -- log at $(@D)/build.log)
	rm -rf $(@D) && mkdir -p $(@D)
	cd $(@D) && env $(cosmocc.env) sh -c '$(call wasm3.compile,cosmocc)' >build.log 2>&1 \
	  || $(call die, guest, wasm3 did not compile -- see the tail of $(@D)/build.log)
	touch $@

build/quickjs-native/.built: $(quickjs.src) guest/js_main.c guest/amk_guest.h
	$(call log, guest, compiling quickjs for the host compiler -- log at $(@D)/build.log)
	rm -rf $(@D) && mkdir -p $(@D)
	cd $(@D) && $(call quickjs.compile,$${CC:-cc}) >build.log 2>&1 \
	  || $(call die, guest, quickjs did not compile -- see the tail of $(@D)/build.log)
	touch $@
build/quickjs-ape/.built: $(quickjs.src) guest/js_main.c guest/amk_guest.h $(cosmocc.dir)/bin/cosmocc
	$(call log, guest, compiling quickjs for cosmocc -- log at $(@D)/build.log)
	rm -rf $(@D) && mkdir -p $(@D)
	cd $(@D) && env $(cosmocc.env) sh -c '$(call quickjs.compile,cosmocc)' >build.log 2>&1 \
	  || $(call die, guest, quickjs did not compile -- see the tail of $(@D)/build.log)
	touch $@

# Apple ld -r localizes hidden symbols on its own; the cosmo pair needs objcopy, once per architecture.
$(guests.host)/%.o: build/%-native/.built
	$(call log, link, partial-linking $* into link input $@)
	mkdir -p $(@D)
	cd build/$*-native && ld -r $(foreach d,$($*.objdirs),$(d)/*.o) -o $(HERE)$@
$(guests.ape)/%.o: build/%-ape/.built
	$(call log, link, partial-linking $* into link input $@ for x86_64 and aarch64)
	mkdir -p $(@D)/.aarch64
	cd build/$*-ape \
	  && $(cosmocc.dir)/bin/x86_64-linux-cosmo-ld -r $($*.ldflags) \
	       $$(ls $(foreach d,$($*.objdirs),$(d)/*.o) | grep -vE 'conftest$($*.objskip)') -o $(HERE)$@ \
	  && $(cosmocc.dir)/bin/aarch64-linux-cosmo-ld -r $($*.ldflags) \
	       $$(ls $(foreach d,$($*.objdirs),$(d)/.aarch64/*.o) | grep -vE 'conftest$($*.objskip)') -o $(HERE)$(@D)/.aarch64/$*.o \
	  && $(cosmocc.dir)/bin/x86_64-linux-cosmo-objcopy $($*.objrename) --localize-hidden $(HERE)$@ \
	  && $(cosmocc.dir)/bin/aarch64-linux-cosmo-objcopy $($*.objrename) --localize-hidden $(HERE)$(@D)/.aarch64/$*.o

#░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░

# The engine list and the version are build inputs like any source, so changing either has to force the relink.
build/.engines$(suffix): FORCE
	mkdir -p $(@D)
	printf '%s\n' '$(engines) $(version.defs)' | cmp -s - $@ || printf '%s\n' '$(engines) $(version.defs)' > $@
build/.libs: FORCE
	mkdir -p $(@D)
	printf '%s\n' '$(libs)' | cmp -s - $@ || printf '%s\n' '$(libs)' > $@
FORCE:

build: $(artifact.ape)
	@# The fat ape, make with the selected guests, built with cosmocc out of tree.
$(artifact.ape): $(make.src) $(cosmocc.dir)/bin/cosmocc build/.engines$(suffix) build/.libs $(foreach e,$(engines),$(guests.ape)/$(e).o) $(tools.files) $(foreach l,$(libs),$($(l).src)) $(payload.files) $(payload.mip)
	$(call log, build, make $(make.version) with $(engines) for cosmocc -- this is the slow one)
	rm -rf build/ape$(suffix) && mkdir -p build/ape$(suffix) $(bin)
	cd build/ape$(suffix) \
	  && export MAKEFLAGS=-s \
	  && env $(cosmocc.env) $(HERE)$(make.src)/configure --disable-dependency-tracking --disable-load CPPFLAGS="$(engines.defs) $(version.defs)" \
	  && env $(cosmocc.env) make -j$(jobs) LIBS="$(foreach e,$(engines),$(HERE)$(guests.ape)/$(e).o) -lm"
	$(call log, build, zipping $(tools) into the payload under bin/ and $(or $(libs),no library) under lib/ with the prelude)
	rm -rf build/payload$(suffix) && mkdir -p build/payload$(suffix)/bin build/payload$(suffix)/lib
	$(foreach t,$(tools),install -m 0755 $($(t).file) build/payload$(suffix)/bin/$(t);)
	$(foreach l,$(libs),$(foreach f,$($(l).files),install -m 0644 $($(l).src)/$(f) build/payload$(suffix)/lib/$(f);))
	$(if $(filter micropython,$(engines)),$(foreach p,$(micropython.pylib),mkdir -p $(dir build/payload$(suffix)/lib/$(firstword $(subst :, ,$(p)))) && install -m 0644 $(micropython.src)/$(lastword $(subst :, ,$(p))) build/payload$(suffix)/lib/$(firstword $(subst :, ,$(p)));))
	$(foreach f,$(payload.files),install -m 0644 $(f) build/payload$(suffix)/$(notdir $(f));)
	$(foreach f,$(payload.mip),install -m 0644 $(f) build/payload$(suffix)/lib/$(notdir $(f));)
	@# zip names an archive without an extension by appending one, so the payload goes into an .ape copy.
	cp build/ape$(suffix)/make build/payload$(suffix)/amk.ape
	cd build/payload$(suffix) && zip -q -r amk.ape bin $(if $(libs)$(filter micropython,$(engines)),lib) $(notdir $(payload.files))
	rm -f $@ && install -m 0755 build/payload$(suffix)/amk.ape $@
	$(foreach n,$(engines.aliases),ln -sf amk $(bin)/$(n);)
	$(call log, build, artifact $@ is ready -- $(bin) holds the $(engines.aliases) names for it)

build.native: $(artifact.host)
	@# The same with the host compiler, unoptimized, for the fast loop.
$(artifact.host): $(make.src) build/.engines$(suffix) $(foreach e,$(engines),$(guests.host)/$(e).o)
	$(call log, build.native, make $(make.version) with $(engines) at $(native.cflags))
	rm -rf build/native$(suffix) && mkdir -p build/native$(suffix) $(bin.host)
	cd build/native$(suffix) \
	  && export MAKEFLAGS=-s \
	  && $(HERE)$(make.src)/configure --disable-dependency-tracking CFLAGS="$(native.cflags)" CPPFLAGS="$(engines.defs) $(version.defs)" \
	  && make -j$(jobs) LIBS="$(foreach e,$(engines),$(HERE)$(guests.host)/$(e).o) -lm"
	rm -f $@ && install -m 0755 build/native$(suffix)/make $@
	$(foreach n,$(engines.aliases),ln -sf amk $(bin.host)/$(n);)
	$(call log, build.native, artifact $@ is ready -- $(bin.host) holds the $(engines.aliases) names for it)

# The gmsl suite against the payload copy, from a directory that holds the suite but not the library, both ways upstream runs it; gmsl reads unset arguments by design, so it runs without this file's undefined-variable warnings.
gmsl.tests = cd build/gmsl && for mode in EXPORT_ALL= EXPORT_ALL=1; do \
	  out=$$(env MAKEFLAGS=-s sh -c "$(abspath $(artifact.ape)) -I /zip/lib -f gmsl-tests $$mode"); \
	  echo "gmsl-tests $$mode: $$(echo "$$out" | tail -1)"; \
	  case "$$out" in *'; 0 tests failed'*) ;; *) echo "$$out" >&2; exit 1;; esac; \
	done

smoke: $(artifact.ape) smoke.readme smoke.demos
	@# Builtins cold, the multi-call names, then one zygote and three clients.
	$(call log, smoke, the version banner and .AMK_VERSION)
	sh -c "$(artifact.ape) --version" | sed -n 2p | grep -x 'Built for x86_64 and aarch64 as an actually portable executable (amk $(amk.version)$(if $(flavor), $(flavor)): $(engines.features))'
	sh -c "$(artifact.ape) --version" | sed -n 1p | grep -x 'GNU Make $(make.version)'
	sh -c "$(artifact.ape) -f /dev/null -p" | grep -x '.AMK_VERSION := $(amk.version)'
	$(call log, smoke, every engine and every flag in the README command line table is in --help)
	sh -c "$(artifact.ape) --help" > build/help.txt
	for f in $(engines.features); do grep -q -- "--$$f ARGS" build/help.txt || { echo "--$$f is missing from --help" >&2; exit 1; }; done
	awk -F'|' '/^\| `--/ { print $$2 }' README.md | grep -o -- '--[a-z-]*' | grep -v -- '--<' | sort -u \
	  | while read -r f; do grep -q -- "$$f" build/help.txt || { echo "$$f is in the README table but missing from --help" >&2; exit 1; }; done
	grep -qx 'This program is amk $(amk.version)$(if $(flavor), $(flavor)) ($(engines.features))' build/help.txt
	$(call log, smoke, the builtins cold)
	sh -c "$(artifact.ape) -f smoke.mk builtins engines='$(engines.features)' wasm.test=$(wasm3.src)/test/wasi/simple/test.wasm"
	$(call log, smoke, the multi-call names and flags)
	$(if $(filter gawk,$(engines)),sh -c "$(bin)/awk 'BEGIN { print \"awk by name: ok\" }'")
	$(if $(filter jq,$(engines)),printf '{"n":41}' | sh -c "$(bin)/jq -c .n+1")
	$(if $(filter gawk,$(engines)),sh -c "$(artifact.ape) --awk 'BEGIN { print \"awk by flag: ok\" }'")
	$(if $(filter wasm3,$(engines)),sh -c "$(bin)/wasm3 --func fib $(wasm3.src)/test/lang/fib32.wasm 20" 2>&1 | grep -x 'Result: 6765')
	$(if $(filter wasm3,$(engines)),sh -c "$(artifact.ape) --wasm --func fib $(wasm3.src)/test/lang/fib32.wasm 20" 2>&1 | grep -x 'Result: 6765')
	$(call log, smoke, the payload tools first on PATH)
	sh -c "$(artifact.ape) -f smoke.mk path tools='$(tools)'"
	env AMK_NO_PATH=1 sh -c "$(artifact.ape) -f smoke.mk path.off tools='$(tools)'"
	$(call log, smoke, the payload libraries read in place from /zip/lib)
	env MAKEFLAGS=-s sh -c "$(artifact.ape) -f smoke.mk libs libs='$(libs)'"
	$(if $(filter gmsl,$(libs)),rm -rf build/gmsl && mkdir -p build/gmsl && install -m 0644 $(gmsl.src)/gmsl-tests build/gmsl/)
	$(if $(filter gmsl,$(libs)),$(gmsl.tests))
	$(call log, smoke, one zygote and three clients -- expect three distinct pids)
	sock=$$(mktemp -d)/probe.sock; \
	sh -c "$(artifact.ape) --serve $$sock -f smoke.mk noop" & sleep 1; \
	for i in 1 2 3; do sh -c "$(artifact.ape) --client $$sock hello"; done; \
	pkill -f -- "--serve $$sock"
	$(call log, smoke, a bundle whose default entry is its own makefile)
	rm -rf build/bundle && mkdir -p build/bundle/away
	cd tests/fixtures/bundle && sh -c "$(abspath $(artifact.ape)) --bundle main.mk lib/ --out $(HERE)build/bundle/b.amk"
	unzip -Z1 $(artifact.ape) | sort > build/bundle/base.list && unzip -Z1 build/bundle/b.amk | sort > build/bundle/b.list
	test "$$(comm -13 build/bundle/base.list build/bundle/b.list | tr '\n' ' ')" = "__main__.mk lib/greet.mk lib/sub/deep.mk "
	unzip -tq build/bundle/b.amk
	cd build/bundle/away && sh -c "../b.amk entry" && sh -c "../b.amk recurse"
	cd build/bundle/away && env -i HOME="$$HOME" AMK_NO_PATH=1 PATH=/nonexistent /bin/sh -c "../b.amk entry"
	sh -c "build/bundle/b.amk -f smoke.mk noop"
	cd tests/fixtures/bundle && sh -c "$(HERE)build/bundle/b.amk --bundle lib/greet.mk --out $(HERE)build/bundle/c.amk"
	test "$$(unzip -p build/bundle/c.amk __main__.mk)" = "greeting := hello"
	test "$$(unzip -Z1 build/bundle/c.amk | wc -l)" = "$$(unzip -Z1 build/bundle/b.amk | wc -l)"
	sock=$$(mktemp -d)/bundle.sock; \
	sh -c "build/bundle/b.amk --serve $$sock" & sleep 1; \
	served=$$(sh -c "build/bundle/b.amk --client $$sock served") || true; \
	pkill -f -- "--serve $$sock"; \
	echo "$$served"; \
	case "$$served" in 'served by pid '*) ;; *) echo "bundle: the zygote did not serve the request" >&2; exit 1;; esac
	$(call log, smoke, every check passed)
smoke.readme: $(artifact.ape)
	@# The make blocks under the two guest sections of README.md, extracted and run against the artifact with the values readme.mk holds them to.
	$(call log, smoke.readme, extracting the make blocks under the guest sections of README.md)
	rm -rf build/readme && mkdir -p build/readme
	awk '/^## (Standard|Special) Guests/ { s = 1; next } /^## / { s = 0 } s && /^```make$$/ { f = 1; next } s && /^```$$/ { f = 0 } s && f' README.md > build/readme/examples.mk
	ln -s ../../src build/readme/src
	printf '{"version":"1.2.3"}\n' > build/readme/package.json
	$(call log, smoke.readme, running $$(grep -c ':=' build/readme/examples.mk) assignments and the check target)
	cd build/readme && env MAKEFLAGS=-s sh -c "$(abspath $(artifact.ape)) -f ../../readme.mk readme"
	$(call log, smoke.readme, every example holds)
# The wasm demo needs the opt-in engine and docker, so a build without wasm3 leaves it out.
demos.skip := $(if $(filter wasm3,$(engines)),,demos/wasm-1.mk)
demos := $(filter-out $(demos.skip),$(wildcard demos/*.mk))
smoke.demos: $(artifact.ape)
	@# Every makefile under demos/ runs its default goal and must exit zero; each demo checks itself.
	$(call log, smoke.demos, running $(words $(demos)) demos$(if $(demos.skip), and skipping $(demos.skip)))
	for demo in $(demos); do echo "$$demo"; sh -c "$(artifact.ape) -f $$demo" || exit 1; done
	$(call log, smoke.demos, every demo exited zero)
smoke.native: $(artifact.host)
	@# The builtins and the multi-call names through the host build.
	$(call log, smoke.native, the builtins cold)
	$(artifact.host) -f smoke.mk builtins engines='$(engines.features)' wasm.test=$(wasm3.src)/test/wasi/simple/test.wasm
	$(call log, smoke.native, the multi-call names and flags)
	$(if $(filter gawk,$(engines)),$(bin.host)/awk 'BEGIN { print "awk by name: ok" }')
	$(if $(filter jq,$(engines)),printf '{"n":41}' | $(bin.host)/jq -c .n+1)
	$(if $(filter jq,$(engines)),$(artifact.host) --jq -n '"jq by flag: ok"')
	$(call log, smoke.native, every check passed)

# The pytest suite under tests/ needs the binary and pytest, nothing else; pytest= names a runner that is not on PATH, and pytest.args= adds flags.
pytest      ?= $(shell command -v pytest 2>/dev/null || echo python3 -m pytest)
pytest.args ?=
test: $(artifact.ape)
	@# The pytest suite against the fat ape: the resident roles, the argv builtins, ape-unpack, and bundles.
	$(call log, test, pytest under tests/ against $(artifact.ape) -- expect about a minute)
	env AMK_BIN=$(abspath $(artifact.ape)) $(pytest) tests $(pytest.args)
test.native: $(artifact.host)
	@# The same suite through the host build.
	$(call log, test.native, pytest under tests/ against $(artifact.host))
	env AMK_BIN=$(abspath $(artifact.host)) $(pytest) tests $(pytest.args)

# The image: docker execs an entrypoint without the shell an ape needs, so the context holds a native executable per arch; BuildKit is required, since the legacy builder leaves the target arch empty.
docker.dir    := build/docker$(suffix)
docker.arches := amd64 arm64
docker.image  ?= amk
docker.tag    ?= $(amk.version)$(suffix)$(foreach e,$(filter $(engines.optin),$(engines)),-$(e))
assimilate.amd64 := -x
assimilate.arm64 := -a
# Inside the image the artifact is the installed one; the wasm demo builds its module with docker, which the image does not carry.
docker.smoke.args = -o /usr/local/bin/amk artifact.ape=/usr/local/bin/amk bin=/usr/local/bin demos.skip=demos/wasm-1.mk \
  $(foreach v,amk.version with without flavor patch.dirs,$(v)='$($(v))')

build.docker: $(docker.dir)/.context
	@# The image from the artifact make build lands, for this platform, tagged $(docker.image):$(docker.tag).
	$(call log, build.docker, building $(docker.image):$(docker.tag) from $(docker.dir))
	DOCKER_BUILDKIT=1 docker build -q -f Dockerfile --target amk -t $(docker.image):$(docker.tag) $(docker.dir) >/dev/null
	$(call log, build.docker, image $(docker.image):$(docker.tag) is ready -- $(docker.dir) is its context for every arch)
$(docker.dir)/.context: $(artifact.ape) $(cosmocc.dir)/bin/cosmocc
	$(call log, build.docker, assimilating $(artifact.ape) to an ELF for each of $(docker.arches))
	rm -rf $(docker.dir) && mkdir -p $(addprefix $(docker.dir)/,$(docker.arches))
	$(foreach a,$(docker.arches), \
	  sh $(cosmocc.dir)/bin/assimilate -e $(assimilate.$(a)) -o $(docker.dir)/$(a)/amk $(artifact.ape) >/dev/null \
	  && chmod 0755 $(docker.dir)/$(a)/amk \
	  $(foreach n,$(engines.aliases),&& ln -sf amk $(docker.dir)/$(a)/$(n));)
	touch $@

smoke.docker: build.docker
	@# The same smoke, run inside the image against the amk it installs, from this checkout mounted as the work tree.
	$(call log, smoke.docker, make smoke inside $(docker.image):$(docker.tag) driven by a stock make as on the host)
	DOCKER_BUILDKIT=1 docker build -q -f Dockerfile --target smoke -t $(docker.image):$(docker.tag)-smoke $(docker.dir) >/dev/null
	docker run --rm --user "$$(id -u):$$(id -g)" -e HOME=/tmp -v "$(HERE):$(HERE)" -w "$(HERE)" \
	  --entrypoint make $(docker.image):$(docker.tag)-smoke smoke $(docker.smoke.args)
	$(call log, smoke.docker, the image passes smoke)

st status: stat
	@# Aliases for stat.
stat:
	@# What is built here: the artifacts, their aliases, and the inputs kept to stay incremental.
	$(call log, stat, out/ is artifacts only -- build/ keeps the inputs that are slow to remake)
	printf '%-8s %-24s %-6s %s\n' kind path size what
	$(call show, deliver, $(deliverable), the copy make amk lands for a caller)
	$(call show, artifact, $(artifact.ape), the fat ape for release and for smoke -- its awk and jq names beside it)
	$(call show, artifact, $(artifact.host), host build at $(native.cflags) for the debug loop -- its names beside it)
	$(call show, input, $(guests.ape), guest relocatables both arches -- the slow half of a build)
	$(call show, input, $(guests.host), the same from the host compiler)
	$(call show, input, src, unpacked sources -- make patched and the guests pristine)
	$(call show, input, cosmocc, the unpacked toolchain)

#░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░

# A release is a v-tag pushed from any branch; the Release workflow builds and publishes it.
version ?=
release.remote ?= origin
release.tag     = v$(version)
release.branch  = $$(git branch --show-current)

release: release.preflight
	@# Tag the head commit v$(version), push the branch and then the tag, and watch the run when gh is on PATH.
	$(call log, release, tagging $(release.tag) on $(release.branch))
	git tag -a $(release.tag) -m "amk $(release.tag)"
	git push $(release.remote) "$(release.branch)"
	git push $(release.remote) $(release.tag)
	$(call log, release, pushed $(release.tag) -- the Release workflow builds and publishes it)
	if command -v gh >/dev/null; then $(MAKE) release.watch version=$(version); else $(call log, release, gh is not on PATH -- watch the run under Actions); fi

release.preflight:
	@# The version is X.Y.Z, the tree is committed, and the tag is free both locally and on the remote.
	printf '%s' '$(version)' | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.]+)?$$' \
	  || $(call die, release, version=X.Y.Z is required -- got '$(version)')
	[ -z "$$(git status --porcelain --untracked-files=no)" ] \
	  || { git status --short --untracked-files=no >&2; $(call die, release, the working tree has uncommitted changes); }
	! git rev-parse -q --verify refs/tags/$(release.tag) >/dev/null \
	  || $(call die, release, $(release.tag) already exists locally)
	! git ls-remote --exit-code --tags $(release.remote) refs/tags/$(release.tag) >/dev/null 2>&1 \
	  || $(call die, release, $(release.tag) already exists on $(release.remote))
	$(call log, release, preflight ok -- $(release.tag) on $(release.branch) is committed and the tag is free)

release.watch:
	@# Stream the Release run for v$(version) to completion; rerun this alone to reattach.
	rid=; for i in $$(seq 1 30); do \
	  rid=$$(gh run list --workflow release.yml --branch $(release.tag) --limit 1 --json databaseId --jq '.[0].databaseId'); \
	  if [ -n "$$rid" ]; then break; fi; sleep 5; \
	done; \
	[ -n "$$rid" ] || $(call die, release, no Release run found for $(release.tag)); \
	$(call log, release, streaming run $$rid); gh run watch "$$rid" --exit-status

clean:
	@# Drop the landed deliverable, the unpacked sources, build trees, and outputs.
	$(call log, clean, dropping $(deliverable) src build out -- this costs a full rebuild)
	$(call log, clean, the downloads and $(cosmocc.dir) stay)
	rm -rf $(deliverable) src build out

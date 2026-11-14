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
make.mirror  := https://mirrors.kernel.org/gnu/make/$(make.tarball)
make.sha256  := dd16fb1d67bfab79a72f5e8390735c49e3e8e70b4945a15ab1f81ddb78658fb3

gawk.version := 5.3.1
gawk.tarball := gawk-$(gawk.version).tar.xz
gawk.url     := https://ftp.gnu.org/gnu/gawk/$(gawk.tarball)
gawk.mirror  := https://mirrors.kernel.org/gnu/gawk/$(gawk.tarball)
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

# Trilog tags no releases, so its version is the commit it pins.
trilog.commit  := c3f7dcbd506bbf8bf073ebf6976aae7e855ce8ea
trilog.short   := $(shell printf %.7s $(trilog.commit))
trilog.version := 0.2.0
trilog.tarball := trilog-$(trilog.short).tar.gz
trilog.url     := https://github.com/mattvonrocketstein/trilog/archive/$(trilog.commit).tar.gz
trilog.sha256  := 8bebc1530c7613770730f52406c97b25ce8e8f4386db6cc16c5d1c53a1bafdf3

micropython.version := 1.29.0
micropython.tarball := micropython-$(micropython.version).tar.xz
micropython.url     := https://github.com/micropython/micropython/releases/download/v$(micropython.version)/$(micropython.tarball)
micropython.sha256  := d925a7c664e79a2bdf3dfcb285ba5e2237041cc35a0bd4ee573b6c5711efeca0

# TinyCC's last release predates its arm64 backend, so its version is the mob commit it pins, served as an archive from the GitHub mirror.
tcc.commit  := 2d3eea205cb6c0f796d01d7d0858eb6c6c1d993f
tcc.short   := $(shell printf %.7s $(tcc.commit))
tcc.version := 0.9.28rc
tcc.tarball := tinycc-$(tcc.short).tar.gz
tcc.url     := https://github.com/TinyCC/tinycc/archive/$(tcc.commit).tar.gz
tcc.sha256  := 65f1c795d10a04d90fb8b0f66f4578bbffe49bc27367214ba49104fe08af61a1

wasm3.version := 0.9.0
wasm3.tarball := wasm3-$(wasm3.version).tar.gz
wasm3.url     := https://github.com/wasm3/wasm3/archive/refs/tags/v$(wasm3.version).tar.gz
wasm3.sha256  := cab79ce74bcac25bbf80b5ebe14af9795b9bac30b05ee8f620a3bc8002f3b8e6

quickjs.version := 2026-06-04
quickjs.tarball := quickjs-$(quickjs.version).tar.xz
quickjs.url     := https://bellard.org/quickjs/$(quickjs.tarball)
quickjs.sha256  := b376e839b322978313d929fd20663b11ba58b75df5a46c126dd19ea2fa70ad2a

graphqlite.version := 0.12.0
graphqlite.tarball := graphqlite-$(graphqlite.version).tar.gz
graphqlite.url     := https://github.com/colliery-io/graphqlite/archive/refs/tags/v$(graphqlite.version).tar.gz
graphqlite.sha256  := 694da13c31f3404a6dff81fda6623613ed0e96bb1cb2473e430cfc71362cd819

# sqlite is the amalgamation, one C file; its guest is a workspace row whose state is an in-memory database.
sqlite.version := 3.53.4
sqlite.release := 3530400
sqlite.tarball := sqlite-amalgamation-$(sqlite.release).zip
sqlite.url     := https://sqlite.org/2026/$(sqlite.tarball)
sqlite.sha256  := 1e71ddf93849c6a6ecf58b827c0692073d2dd7ee40196158068f7b29f422e87d

cosmocc.version := 4.0.2
cosmocc.zip     := cosmocc-$(cosmocc.version).zip
cosmocc.url     := https://github.com/jart/cosmopolitan/releases/download/$(cosmocc.version)/$(cosmocc.zip)
cosmocc.mirror  := https://cosmo.zip/pub/cosmocc/$(cosmocc.zip)
cosmocc.sha256  := 85b8c37a406d862e656ad4ec14be9f6ce474c1b436b9615e91a55208aced3f44

# Tools are released cosmos binaries, zipped into the payload unchanged; patch 0012 puts them first on PATH.
cosmos.version := 4.0.2
tools.all      := sed bash jb cat ls
tools.optout   := jb cat ls
# A cosmos tool pins a digest and nothing else: its file and both urls follow from its name.
cosmos.tools   := sed bash cat ls
# The release zip GitHub hosts answers build hosts that cosmo.zip does not, so it goes first; a url written as zip#member is one file out of that zip.
cosmos.url     := https://github.com/jart/cosmopolitan/releases/download/$(cosmos.version)/cosmos-$(cosmos.version).zip\#bin
cosmos.mirror  := https://cosmo.zip/pub/cosmos/v/$(cosmos.version)/bin
sed.sha256     := 343f00b93739d4ff145c44e28a07889591425cb766bcf7d9e4534708d6fc6cd8
# The two a script reaches for first on a payload file: built with cosmo, so they see /zip where the host's do not.
cat.sha256     := d91c6d0fdd049953a866f3a6f9ae371ca3da5003b1882c3d9fb95f606bbf71d3
ls.sha256      := 91aed87ef3763e23fc625aeb91042849bb608df20f0b9290dc262e06b1762a42
# The shell every makefile under amk names as bash, and the one core forks by default.
bash.sha256    := 5de7cab218c12583413c541363848bc278e8f48dba07d96b9f5790ef40b72e3e
# What that release reports, for the engine row bash takes without being linked in.
bash.version   := 5.2.0
# json.bash is one bash script that picks object or array output from the name it runs as, so it lands under each of its names.
jb.version     := 0.3.0
jb.file        := json.bash-$(jb.version)
jb.url         := https://raw.githubusercontent.com/h4l/json.bash/v$(jb.version)/json.bash
jb.sha256      := 04c9708dcb985a907419c6581438b8972a47607b4779473f4fde1267bdb9fbf7
jb.names       := jb jb-array json.bash
tool.names      = $(if $(filter-out undefined,$(origin $(1).names)),$($(1).names),$(1))

# Libraries are makefiles zipped into the payload under lib/ and read in place by an include; none loads unless a makefile asks.
gmsl.version := 1.2.4
gmsl.tarball := gmsl-$(gmsl.version).tar.gz
gmsl.url     := https://github.com/jgrahamc/gmsl/archive/refs/tags/v$(gmsl.version).tar.gz
gmsl.sha256  := 8f1d7a6a4bb76f4e934b2a1376a9ab0da0d84971e19edf0005689d67feb98a60
gmsl.files   := gmsl __gmsl
gmsl.dir     := gmsl/

# amk's own payload members: the prelude patch 0034 reads before every makefile.
payload.files := payload/__init__.mk $(addprefix payload/lang/amk/awklib/,globals.awk functions.awk joinbody.awk callforms.awk) $(addprefix payload/lang/amk/comp/,definedecorators.awk targetdecorators.awk)
# The mip library needs the micropython and jq engines, so it ships only in a build that has both.
payload.mip = $(if $(filter-out $(engines),micropython jq),,payload/lib/amk/mip.amk payload/lib/amk/schema/mip.json)
# The utmpl library needs the micropython engine and the utemplate library.
payload.utmpl = $(if $(and $(filter micropython,$(engines)),$(filter utemplate,$(libs))),payload/lib/amk/utmpl.amk)
# The bash library names the bash engine, so it ships with the tool.
payload.bash = $(if $(filter bash,$(tools)),payload/lib/amk/bash.amk)
# A topic of amk's own ships its whole folder, one subfolder deep, once the topic can run; a binding whose engine is absent is never loaded.
payload.topic = $(filter-out $(patsubst %/,%,$(wildcard payload/lib/$(1)/*/)),$(wildcard payload/lib/$(1)/* payload/lib/$(1)/*/*))
# The tuple space needs the sqlite engine.
payload.tspace = $(if $(filter sqlite,$(engines)),$(call payload.topic,tspace))
# The effection shim needs the quickjs engine and the effection library, and lands beside the library's build.
payload.effection = $(if $(and $(filter quickjs,$(engines)),$(filter effection,$(libs))),payload/lib/js/effection/init.js)
# Every library amk ships of its own, each landing under lib/ at its path below payload/.
payload.actor = $(if $(and $(payload.effection),$(filter jq,$(engines))),$(call payload.topic,actor))
# The dsys topic is the decorator and locks over the pool builtins, merged with jq over a baseline; the builtins themselves need no engine.
payload.dsys = $(if $(filter jq,$(engines)),$(call payload.topic,dsys))
# The jobman topic is each guest's handle on a pool of jobs and the pools' baseline; dsys/jobman opens them.
payload.jobman = $(if $(filter jq,$(engines)),$(call payload.topic,jobman))
# The io topic is JSON defines: schema.jq checks every decorator's schema in jq, and io/json requires sqlite too.
payload.io = $(if $(filter jq,$(engines)),$(call payload.topic,io))
# The plex library spans the guests: a cooperative ready list of continuations in stock s7, and effection republished in js.
payload.plex = $(if $(or $(filter s7,$(engines)),$(payload.effection)),$(call payload.topic,plex))
# The engine's own folder is stock s7 with no amk in it: amb over delimited control after Filinski, and a JSON reader.
payload.amb = $(if $(filter s7,$(engines)),$(call payload.topic,s7))
# m5, the templating substrate, needs no engine, so every build ships it.
payload.trilog = $(if $(filter trilog,$(engines)),$(addprefix payload/lib/amk/,trilog.amk prolog.amk) $(call payload.topic,trilog))
# The sqlite and cypher libraries add handles to their workspaces, so each ships with its engine.
payload.sqlite = $(if $(filter sqlite,$(engines)),payload/lib/amk/sqlite.amk)
payload.cypher = $(if $(filter graphqlite,$(engines)),payload/lib/amk/cypher.amk)
# The graph library compiles a json document to Cypher, so it needs the cypher and jq engines.
payload.graph = $(if $(filter-out $(engines),graphqlite jq),,$(call payload.topic,graph))

# The gmsl topic is the loader beside the vendored library, so it ships only with that library.
payload.gmsl = $(if $(filter gmsl,$(libs)),payload/lib/gmsl/init.amk)
payload.m5 = payload/lib/amk/m5.mk
# flux's safe core reads only make and m5, so every build ships it too.
payload.flux = payload/lib/amk/flux.mk
# The wasm library builds modules through docker or the host and imports them, so it ships only with the wasm3 engine.
payload.wasm = $(if $(filter wasm3,$(engines)),$(addprefix payload/lib/amk/,wasm.mk zig.amk wat.amk golang.amk))
# Every payload.<name> above is a library, and a topic folder with an init.amk and no gate of its own ships whole.
payload.helpers := payload.files payload.topic payload.topics payload.helpers payload.dest payload.lib
payload.topics = $(patsubst payload/lib/%/init.amk,%,$(wildcard payload/lib/*/init.amk))
payload.lib = $(sort $(foreach v,$(filter-out $(payload.helpers),$(filter payload.%,$(.VARIABLES))),$($(v))) \
  $(foreach t,$(payload.topics),$(if $(filter undefined,$(origin payload.$(t))),$(call payload.topic,$(t)))))
payload.dest = build/payload$(suffix)/$(1:payload/%=%)
pylib.dest = $(call payload.dest,lib/micropy/$(firstword $(subst :, ,$(1))))

# dkjson is one lua file, and its "tarball" is that file; it lands in lib/lua/, on lua's search path, for require.
dkjson.version := 2.8
dkjson.tarball := dkjson-$(dkjson.version).lua
dkjson.url     := http://dkolf.de/dkjson-lua/$(dkjson.tarball)
dkjson.sha256  := eb3bf160688fb395a2db6bc52eeff4f7855a6321d2b41bdc754554d13f4e7d44
dkjson.files   := dkjson.lua
dkjson.dir     := lua/
# lxsc is a Lua scxml interpreter, its one-file build with its xml parser inside; it lands in lib/lua/ as lxsc.lua, for require.
lxsc.version := 0.14
lxsc.tarball := lxsc-flat-$(lxsc.version).lua
lxsc.url     := https://raw.githubusercontent.com/Phrogz/LXSC/master/compiled/$(lxsc.tarball)
lxsc.sha256  := 4f39e76bbfa24aedda0e2ed8e2f36036a2d037c8eb7a6a9392b1ded05c9560c2
lxsc.files   := lxsc.lua
lxsc.dir     := lua/
# A library lands under lib/ at its own dir, when it names one.
lib.dir = $(if $(filter-out undefined,$(origin $(1).dir)),$($(1).dir))
# utemplate is a micropython package from its PyPI sdist, the one release archive it publishes; it lands in lib/micropy/, on micropython's path, for import.
utemplate.version := 1.4.1
utemplate.tarball := utemplate-$(utemplate.version).tar.gz
utemplate.url     := https://files.pythonhosted.org/packages/ba/93/5eca962e6d576b8f50bb11bc9506becc11ce4587a56b707095c3073bda06/$(utemplate.tarball)
utemplate.sha256  := 43fde7c8b38dda1ff9c82cd829d22ec445f1e9d631455de705873051f83a0b20
utemplate.files   := utemplate/source.py utemplate/compiled.py utemplate/recompile.py
utemplate.dir     := micropy/
# effection is structured concurrency for js, its npm tarball's esm build; it lands in lib/js/effection/, beside the init.js that shims its host globals, and lib/plex/init.js republishes it as amk.plex.
effection.version := 4.2.0
effection.tarball := effection-$(effection.version).tgz
effection.url     := https://registry.npmjs.org/effection/-/$(effection.tarball)
effection.sha256  := 08764bbf6d3be9f87f3917dde739769435e2da476fc3ade58aa16b19dd2340b0
effection.files   := mod.js experimental.js _dnt.polyfills.js _dnt.shims.js $(addprefix lib/,$(addsuffix .js, \
  abort-signal action all-settled all api-internal api async box call callcc channel constant context contexts \
  coroutine do each ensure events future interval lazy-promise lift main maybe mod priority-queue queue race \
  reducer resource result run scope-internal scope scoped signal sleep spawn suspend task-group task trap types \
  until using with-resolvers))
effection.dir     := js/effection/
libs.all     := gmsl dkjson lxsc utemplate effection

# The default set is linked in; with adds an opt-in engine to a build, and without leaves any engine out of one.
engines.all   := gawk jq lua s7 trilog micropython wasm3 quickjs sqlite graphqlite tcc cpython
engines.optin := cpython
with          ?=
without       ?=
# The linked libraries, and which of them each engine needs.
clibs.all     := openssl
gawk.needs    :=
jq.needs      :=
lua.needs     :=
s7.needs      :=
trilog.needs  :=
micropython.needs :=
wasm3.needs   :=
quickjs.needs :=
sqlite.needs  :=
graphqlite.needs :=
tcc.needs     :=
cpython.needs := openssl
# A distribution is a named choice of what is linked in, built beside the default one: omnibus has every opt-in engine and linked library, and with and without still apply over it.
dists.all     := omnibus
dist          ?=
dist.omnibus.with := $(engines.optin) $(clibs.all)
ifneq ($(filter-out $(dists.all),$(dist)),)
  $(error dist names $(dist), which is not a distribution -- choose from $(dists.all), or leave it out for the default)
endif
ifneq ($(dist),)
  override with := $(strip $(dist.$(dist).with) $(with))
endif
ifneq ($(filter-out $(engines.all) $(clibs.all),$(with) $(filter-out $(libs.all) $(tools.optout),$(without))),)
  $(error with or without names $(filter-out $(engines.all) $(clibs.all),$(with) $(filter-out $(libs.all) $(tools.optout),$(without))), which is not an engine, library, or optional tool -- choose from $(engines.all) $(clibs.all), or leave out $(libs.all) $(tools.optout))
endif
libs := $(filter-out $(without),$(libs.all))
tools := $(filter-out $(filter $(tools.optout),$(without)),$(tools.all))
engines.default := $(filter-out $(engines.optin),$(engines.all))
engines         := $(filter-out $(without),$(filter $(engines.default) $(with),$(engines.all)))
# A linked library is built when an engine in the build needs it or with names it; without leaves it out, and an engine that needs it builds without what it gave.
clibs           := $(filter-out $(without),$(filter $(with) $(foreach e,$(engines),$($(e).needs)),$(clibs.all)))
ifeq ($(engines),)
  $(error without leaves no engine -- amk is make with guests linked in, and without is not the way to build stock make)
endif
ifeq ($(filter graphqlite,$(engines))$(filter sqlite,$(engines)),graphqlite)
  $(error graphqlite is a graph layer over sqlite -- leave both out, or neither)
endif
# The link inputs: every engine but graphqlite, which is inside sqlite's.
engines.linked := $(filter-out graphqlite,$(engines))

# An engine left out is absent from the builtins and from the feature list, not a stub that fails late.
gawk.define := AMK_ENGINE_GAWK
jq.define   := AMK_ENGINE_JQ
lua.define  := AMK_ENGINE_LUA
s7.define   := AMK_ENGINE_S7
trilog.define := AMK_ENGINE_TRILOG
micropython.define := AMK_ENGINE_MICROPY
wasm3.define := AMK_ENGINE_WASM3
quickjs.define := AMK_ENGINE_QUICKJS
sqlite.define := AMK_ENGINE_SQLITE
graphqlite.define := AMK_ENGINE_GRAPHQLITE
tcc.define := AMK_ENGINE_TCC
gawk.feature := awk
jq.feature   := jq
lua.feature  := lua
s7.feature   := s7
trilog.feature := trilog
micropython.feature := micropy
wasm3.feature := wasm
quickjs.feature := js
sqlite.feature := sqlite
graphqlite.feature := cypher
tcc.feature := tcc
# bash is a tool with a row: no link input, the last engine listed.
tools.engines    = $(filter bash,$(tools))
engines.defs     = $(foreach e,$(engines),-D$($(e).define)=$($(e).version)) $(if $(tools.engines),-DAMK_ENGINE_BASH=$(bash.version))
version.defs     = -DAMK_VERSION=$(amk.version) $(if $(flavor),-DAMK_FLAVOR=$(flavor))
engines.features = $(strip $(foreach e,$(engines),$($(e).feature)) $(tools.engines))
# The names the given binary answers to, every engine's own and its aliases, as its engine listing reports them.
engines.names    = $(1) --list-engines | awk -F'"' '/"(name|aliases)":/ { for (i = 4; i < NF; i += 2) print $$i }'

# Pinned inputs a linked library brings with it for the payload, by name.
clibs.deps  := $(if $(filter openssl,$(clibs)),cacert)
# Every pinned input by name; the file, urls, and digest of each come from its own variables, so a new input needs no line anywhere else.
deps.names  := make $(engines) $(clibs) $(clibs.deps) $(tools) $(libs) cosmocc
dep.get      = $(if $(filter-out undefined,$(origin $(1))),$($(1)))
dep.cosmos   = $(filter $(1),$(cosmos.tools))
dep.file     = $(if $(call dep.cosmos,$(1)),$(1)-$(cosmos.version).ape,$(or $(call dep.get,$(1).tarball),$(call dep.get,$(1).file),$(call dep.get,$(1).zip)))
dep.urls     = $(if $(call dep.cosmos,$(1)),$(cosmos.url)/$(1) $(cosmos.mirror)/$(1),$($(1).url) $(call dep.get,$(1).mirror))
tools.files := $(foreach t,$(tools),$(call dep.file,$(t)))
libs.tarballs := $(foreach l,$(libs),$($(l).tarball))
# These two are read late, since the optional build pins its inputs in a section of its own further down.
clibs.files  = $(foreach n,$(clibs.deps),$(call dep.file,$(n)))
deps.files   = $(foreach n,$(deps.names),$(call dep.file,$(n)))

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
# A flavor has a patched tree of its own; a distribution shares the tree and differs from the link on, so only the flavor names the tree.
flavor.suffix := $(if $(flavor),-$(flavor))
suffix   := $(flavor.suffix)$(if $(dist),-$(dist))
patches  := $(foreach d,$(patch.dirs),$(abspath $(wildcard $(d)/*.patch)))
make.src := src/make-$(make.version)$(flavor.suffix)
gawk.src := src/gawk-$(gawk.version)
jq.src   := src/jq-$(jq.version)
lua.src  := src/lua-$(lua.version)
s7.src   := src/s7-$(s7.version)
trilog.src := src/trilog-$(trilog.short)
micropython.src := src/micropython-$(micropython.version)
wasm3.src := src/wasm3-$(wasm3.version)
quickjs.src := src/quickjs-$(quickjs.version)
sqlite.src := src/sqlite-amalgamation-$(sqlite.release)
graphqlite.src := src/graphqlite-$(graphqlite.version)
tcc.src := src/tinycc-$(tcc.short)
# The archives of the linked libraries an engine needs and the build has, for its partial link; each library installs under a root of its own.
needs.built    = $(foreach n,$(filter $(clibs),$($(1).needs)),build/$(n)-ape/.built)
needs.archives = $(foreach n,$(filter $(clibs),$($(1).needs)),$(addprefix $(HERE)$($(n).root)/,$($(n).archives)))
guest.archive  = $(call dep.get,$(1).archive)
gmsl.src  := src/gmsl-$(gmsl.version)
dkjson.src := src/dkjson-$(dkjson.version)
lxsc.src := src/lxsc-$(lxsc.version)
utemplate.src := src/utemplate-$(utemplate.version)
effection.src := src/effection-$(effection.version)

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
trilog.objdirs := .
# Trilog builds as its library's sources for posix with libc, the dev variant that boots from boot/core.pl; the guest's entry point replaces its cli.
trilog.patches := $(abspath $(wildcard guest/patches/trilog/*.patch))
trilog.cflags  := -std=c11 -D_POSIX_C_SOURCE=200809L
trilog.sources := $(addprefix src/kernel/,fmt.c heap.c unify.c term.c solve.c parse.c arena.c gc.c mem.c embedded_none.c image_none.c) \
                  src/io/io.c src/io/streams.c src/trilog.c src/platform/posix.c src/platform/libc.c
trilog.includes := include src/kernel src/io src/platform
# MicroPython compiles through its own makefiles, driven by guest/micropy.mk, and its objects land in these directories of the build tree.
micropython.objdirs := . py extmod shared/runtime shared/readline shared/libc shared/timeutils ports/unix extmod/mbedtls lib/mbedtls/library lib/mbedtls_errors
# Python-side modules zipped as source under lib/micropy/, on micropython's path, as payload path and tarball path: asyncio's Python half, and ssl, requests, and mip from micropython-lib.
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
sqlite.objdirs := . $(if $(filter graphqlite,$(engines)),../graphqlite-ape)
# TinyCC builds as libtcc's one translation unit against the guest's own config.h, its predefined macros generated as strings by its c2str tool on the host.
tcc.objdirs := .
tcc.patches := $(abspath $(wildcard guest/patches/tinycc/*.patch))
tcc.cflags  := -D_COSMO_SOURCE -DONE_SOURCE=1
quickjs.cflags  := -D_GNU_SOURCE -DCONFIG_VERSION=\"$(quickjs.version)\" -fwrapv
quickjs.exclude := qjs.c qjsc.c run-test262.c unicode_gen.c
# cosmocc refuses an argument with a space, and jq passes its package string on the command line.
gawk.defs :=
jq.defs = DEFS="$$(sed -n 's/^DEFS = //p' Makefile | sed 's/jq\\ $(jq.version)/jq-$(jq.version)/')"
gawk.objcheck := *.o
jq.objcheck   := src/*.o
lua.objcheck  := *.o
s7.objcheck   := *.o
trilog.objcheck := *.o
micropython.objcheck := py/*.o
wasm3.objcheck := *.o
quickjs.objcheck := *.o
sqlite.objcheck := *.o
tcc.objcheck := *.o
# Per-guest hooks on the partial link and the guest compile: extra ld flags, compile flags in place of the shared ones, objcopy renames, and objects to leave out as alternatives appended to the conftest filter.
gawk.ldflags   :=
jq.ldflags     :=
lua.ldflags    :=
s7.ldflags     :=
trilog.ldflags :=
micropython.ldflags :=
wasm3.ldflags  :=
quickjs.ldflags :=
sqlite.ldflags :=
tcc.ldflags :=
gawk.guestflags :=
jq.guestflags   :=
lua.guestflags  :=
s7.guestflags   :=
trilog.guestflags :=
micropython.guestflags :=
wasm3.guestflags :=
quickjs.guestflags :=
sqlite.guestflags :=
tcc.guestflags :=
gawk.objrename :=
jq.objrename   :=
lua.objrename  :=
s7.objrename   :=
trilog.objrename :=
micropython.objrename :=
wasm3.objrename :=
quickjs.objrename :=
sqlite.objrename :=
tcc.objrename :=
gawk.objskip   :=
jq.objskip     :=
lua.objskip    :=
s7.objskip     :=
trilog.objskip :=
micropython.objskip :=
wasm3.objskip  :=
quickjs.objskip :=
sqlite.objskip :=
tcc.objskip :=
# A file of amk's own compiled beside a configured guest's objects, so the partial link takes it; the compiler is the argument.
gawk.extra  =
jq.extra    = $(1) $(call guest.cflags,jq) -I$(HERE)$(jq.src)/src -I$(HERE)guest -c $(HERE)guest/jq_main.c -o src/jq_main.o
lua.extra   =
s7.extra    =
trilog.extra =
micropython.extra =
wasm3.extra =
quickjs.extra =
sqlite.extra =
tcc.extra =

# out/bin holds the artifact beside its argv[0] aliases; everything rebuildable stays under build/.
guests.ape    := build/guests/ape
bin           := out/bin$(suffix)
artifact.ape  := $(bin)/amk
# The deliverable lands beside this Makefile, where a caller can find it without knowing the layout.
deliverable   := amk$(if $(dist),-$(dist))

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

.PHONY: amk deps verify w3c toolchain patch build repack guests smoke smoke.demos itest test test.integration test.upstream build.docker smoke.docker install install.user install.global release release.preflight release.watch stat st status vscode clean help FORCE
.DEFAULT_GOAL := amk

# The docs goals run in docs/docs.amk under the built amk, which a docs goal never rebuilds.
.PHONY: docs
docs: | $(artifact.ape)
	$(artifact.ape) -C $(HERE) -f docs/docs.amk $@
docs.%: | $(artifact.ape)
	$(artifact.ape) -C $(HERE) -f docs/docs.amk $@

help:
	@# List the targets.
	$(call log, help, usage: make amk for the deliverable -- make stat says what is built)
	$(call log, help, engines $(engines.default) are linked in by default$(if $(engines.optin), and $(engines.optin) on request -- with='$(firstword $(engines.optin))' adds one) -- without='$(firstword $(engines.all))' leaves one out)
	$(call log, help, distributions: dist='$(firstword $(dists.all))' builds $(dist.omnibus.with) in as well and lands beside the default build -- choose from $(dists.all))
	grep -hE '^[a-z][a-z. ]*:([^=]|$$)' $(HERE)Makefile $(HERE)docs/docs.amk | cut -d: -f1 | tr ' ' '\n' | sort | tr '\n' ' '; echo

#░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░

# The optional build, whole: everything the cpython engine and the openssl library need beyond their names in the engine and library lists above. The default build reads this section and uses none of it.

# CPython is real Python with its standard library, at several times the size of the rest of amk.
cpython.version := 3.12.15
cpython.tarball := Python-$(cpython.version).tar.xz
cpython.url     := https://www.python.org/ftp/python/$(cpython.version)/$(cpython.tarball)
cpython.sha256  := c2c4321961fab0fb999d66e0cecf521c2ab3994c7992873ea99e306c1094fd5a
cpython.define  := AMK_ENGINE_CPYTHON
cpython.feature := cpython
cpython.src     := src/Python-$(cpython.version)

# OpenSSL is a linked library: C code an engine links against, built once under cosmocc; 3.5 is the long-term support line.
openssl.version := 3.5.9
openssl.tarball := openssl-$(openssl.version).tar.gz
openssl.url     := https://github.com/openssl/openssl/releases/download/openssl-$(openssl.version)/$(openssl.tarball)
openssl.sha256  := 603f5602e2eef00d77fbd429d34dcd5822bb301757a1bc9cdb24c670f1eb859a
openssl.src     := src/openssl-$(openssl.version)
# Its headers and static archives install under this root, each archive with its aarch64 twin in .aarch64/ beside it.
openssl.root     := build/openssl-ape/root
openssl.archives := lib/libssl.a lib/libcrypto.a
# Portable C with no loadable parts; the certificate directory is a payload path, so a bundle shipped there is found with no setup.
openssl.configure := linux-generic64 no-shared no-asm no-tests no-apps no-docs no-module no-engine no-legacy no-dso \
                     --prefix=$(HERE)$(openssl.root) --libdir=lib --openssldir=/zip/usr/share/ssl

# The certificate authorities OpenSSL trusts by default: Mozilla's set as curl publishes it by date, shipped in the payload at the path the library reads.
cacert.version := 2026-11-05
cacert.file    := cacert-$(cacert.version).pem
cacert.url     := https://curl.se/ca/$(cacert.file)
cacert.sha256  := 427c064216761a1e72a8b30f0d954d08cb6e4435a82091fb865afd20c8497285
cacert.dest    := usr/share/ssl/cert.pem

# CPython cross-configures for cosmocc against a build python of its own, with its extension modules built in; the host's vendor field differs from any build machine's, so an x86_64 Linux builder cross-compiles too.
cpython.configure = --build=$$($(HERE)$(cpython.src)/config.guess) --host=x86_64-cosmo-linux-gnu \
                    --with-build-python=$(HERE)$(cpython.hostpy) --disable-shared --disable-ipv6 \
                    --without-ensurepip --disable-test-modules MODULE_BUILDTYPE=static \
                    ac_cv_file__dev_ptmx=no ac_cv_file__dev_ptc=no $(cpython.zlib) $(cpython.nopkg) \
                    $(if $(filter openssl,$(clibs)),--with-openssl=$(HERE)$(openssl.root) --with-openssl-rpath=no)
# cosmo's libc carries zlib under a header directory of its own, so configure is told where the header is and that no further library is needed.
cpython.zlib    = ZLIB_CFLAGS=-I$(cosmocc.dir)/include/third_party/zlib ZLIB_LIBS=-lc
# The builder's pkg-config describes libraries for the builder's own libc, such as libffi, so configure gets none and finds only what cosmocc can compile against.
cpython.nopkg  := PKG_CONFIG=false
cpython.hostpy  = build/cpython-host/python$(if $(filter Darwin,$(os)),.exe)
# The standard library less its tests, its gui, and what installs packages, as excludes on the copy into lib/python3.12/.
cpython.libskip := test idlelib tkinter turtledemo lib2to3 __pycache__

# The per-guest hooks every engine carries. CPython names struct members main and links no main of its own, so its compile flags are the shared ones less the rename.
cpython.objdirs    := .
cpython.objcheck   := libpython3.12.a
cpython.ldflags    :=
cpython.guestflags := -O2 -fno-common -fvisibility=hidden -Wno-implicit-function-declaration -Dexit=amk_exit
# libpython marks its api visible, so everything but the entry point is localized by name.
cpython.objrename  := $(addprefix --keep-global-symbol=cpython_,run_main tool_main create exec import hook)
cpython.objskip    :=
cpython.extra       =
# Static libraries the partial link takes whole, beside the objects, since this guest's build ends in them; each has its aarch64 twin in .aarch64/ beside it.
cpython.archive := libpython3.12.a Modules/expat/libexpat.a Modules/_decimal/libmpdec/libmpdec.a Modules/_hacl/libHacl_Hash_SHA2.a

# What the artifact's payload gains: the standard library under lib/python3.12/ and the certificate bundle, with the top-level directories they land in.
define optin.payload
$(if $(filter cpython,$(engines)),mkdir -p $(call payload.dest,lib/python3.12) && tar cf - $(addprefix --exclude ,$(cpython.libskip)) -C $(cpython.src)/Lib . | tar xf - -C $(call payload.dest,lib/python3.12))
$(if $(filter cpython,$(engines)),install -m 0644 build/cpython-ape/$$(cat build/cpython-ape/pybuilddir.txt)/_sysconfigdata_*.py $(call payload.dest,lib/python3.12/))
$(if $(filter cpython,$(engines)),echo ../ensurepip/_bundled/$(notdir $(wildcard $(cpython.src)/Lib/ensurepip/_bundled/pip-*.whl)) >$(call payload.dest,lib/python3.12/site-packages/ensurepip-pip.pth))
$(if $(filter cpython,$(engines)),$(foreach n,pip pip3,install -m 0755 build/cpython-ape/pip build/payload$(suffix)/bin/$(n);))
$(if $(clibs.files),mkdir -p $(dir $(call payload.dest,$(cacert.dest))) && install -m 0644 $(cacert.file) $(call payload.dest,$(cacert.dest)))
endef
optin.payload.dirs = $(if $(filter cpython,$(engines)),lib) $(if $(clibs.files),usr)

$(openssl.src): $(openssl.tarball)
	$(call log, patch, unpacking $(openssl.tarball) into $@ unpatched)
	mkdir -p src && tar xzf $(openssl.tarball) -C src && touch $@
$(cpython.src): $(cpython.tarball)
	$(call log, patch, unpacking $(cpython.tarball) into $@ unpatched)
	mkdir -p src && tar xJf $(cpython.tarball) -C src && touch $@
# The cross build freezes its bootstrap modules with a python of the same version, built here for the host with its native compiler.
build/cpython-host/.built: $(cpython.src)
	$(call log, guest, compiling the host python cpython's cross build needs -- log at $(@D)/build.log)
	rm -rf $(@D) && mkdir -p $(@D)
	cd $(@D) && ( $(HERE)$(cpython.src)/configure --without-ensurepip --disable-test-modules && make -j$(jobs) ) >build.log 2>&1 \
	  || $(call die, guest, the host python did not compile -- see the tail of $(@D)/build.log)
	touch $@
# OpenSSL's own configure and make under cosmocc, then its development install into the root, with the aarch64 archives copied beside the ones the install knows of.
build/openssl-ape/.built: $(openssl.src) $(cosmocc.dir)/bin/cosmocc
	$(call log, guest, compiling openssl $(openssl.version) for cosmocc -- log at $(@D)/build.log)
	rm -rf $(@D) && mkdir -p $(@D)
	cd $(@D) && ( env $(cosmocc.env) $(HERE)$(openssl.src)/Configure $(openssl.configure) \
	  && env $(cosmocc.env) make -j$(jobs) build_libs && env $(cosmocc.env) make install_dev ) >build.log 2>&1 \
	  || $(call die, guest, openssl did not compile -- see the tail of $(@D)/build.log)
	mkdir -p $(openssl.root)/lib/.aarch64 && cp $(addprefix $(@D)/.aarch64/,$(notdir $(openssl.archives))) $(openssl.root)/lib/.aarch64/
	touch $@
build/cpython-ape/Makefile: $(cpython.src) build/cpython-host/.built $(cosmocc.dir)/bin/cosmocc $(call needs.built,cpython)
	$(call log, configure, cpython $(cpython.version) for cosmocc in $(@D))
	rm -rf $(@D) && mkdir -p $(@D)
	cd $(@D) && env $(cosmocc.env) CXX=cosmoc++ $(HERE)$(cpython.src)/configure $(cpython.configure)
# libpython with every module built in, then the entry point against its headers; the archive is the partial link's input, whole.
build/cpython-ape/.built: build/cpython-ape/Makefile guest/cpython_main.c guest/amk_guest.h
	$(call log, guest, compiling cpython for cosmocc -- log at $(@D)/build.log)
	cd $(@D) && env $(cosmocc.env) MAKEFLAGS=-s make -j$(jobs) EXTRA_CFLAGS='$(cpython.guestflags)' $(cpython.archive) pybuilddir.txt >build.log 2>&1 \
	  || $(call die, guest, cpython did not compile -- see the tail of $(@D)/build.log)
	cd $(@D) && env $(cosmocc.env) cosmocc $(cpython.guestflags) -I. -I$(HERE)$(cpython.src)/Include -I$(HERE)guest \
	  -c $(HERE)guest/cpython_main.c -o cpython_main.o >>build.log 2>&1 \
	  || $(call die, guest, cpython's entry point did not compile -- see the tail of $(@D)/build.log)
	touch $@
# The payload's pip and pip3: pip run by the python3 beside them, written once the guest has built.
build/cpython-ape/pip: build/cpython-ape/.built
	printf '%s\n' '#!/usr/bin/env bash' 'exec "$${0%/*}/python3" -m pip "$$@"' >$@ && chmod 0755 $@

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
	[ -x $(artifact.ape) ] || $(call die, install, no $(artifact.ape) here -- run make build first)
	[ -n "$(install.os)" ] || $(call die, install, $(os) is not a system this knows -- pass bindir.$*=DIR to say where)
	as=; [ -w "$(bindir.$*)" ] || [ -w "$$(dirname "$(bindir.$*)")" ] || { [ $* = global ] && as=sudo; }; \
	$$as mkdir -p "$(bindir.$*)" && $$as install -m 0755 $(artifact.ape) "$(bindir.$*)/$(notdir $(deliverable))" \
	  || $(call die, install, could not write $(bindir.$*)/$(notdir $(deliverable)))
	case ":$$PATH:" in *":$(bindir.$*):"*) ;; *) $(call log, install, $(bindir.$*) is not on PATH -- add it in the shell rc);; esac
	$(call log, install, $(bindir.$*)/$(notdir $(deliverable)) is ready)

#░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░

deps: $(deps.files) verify
	@# Fetch every pinned input that is not already here, then verify all of them.

url   = $(strip $(foreach n,$(deps.names),$(if $(filter $@,$(call dep.file,$(n))),$(call dep.urls,$(n)))))
fetch = curl -fsSL --connect-timeout 30 --retry 3 --retry-all-errors
$(deps.files):
	@# The first url is the home of the input; any after it are mirrors, tried in turn, and verify checks the digest whichever answered.
	$(call log, deps, fetching $@ from $(firstword $(url)))
	for u in $(url); do \
	  case "$$u" in \
	    *'#'*) zip=$${u%%#*}; kept=$${zip##*/}; \
	      { [ -f "$$kept" ] || { $(fetch) "$$zip" -o "$$kept.part" && mv "$$kept.part" "$$kept"; }; } \
	        && unzip -p "$$kept" "$${u#*#}" > "$@.part";; \
	    *) $(fetch) "$$u" -o "$@.part";; \
	  esac && break; \
	  $(call log, deps, $$u did not answer); false; done \
	  || $(call die, deps, could not fetch $@ from $(words $(url)) url(s) -- partial file left at $@.part)
	mv "$@.part" "$@"

verify:
	@# Check every download against its pinned digest.
	$(call log, verify, checking $(words $(deps.files)) downloads against their pinned digests)
	printf '%s  %s\n' \
	  $(foreach n,$(deps.names),$($(n).sha256) $(call dep.file,$(n))) \
	| $(sha256) -c - \
	  || $(call die, verify, a download does not match its pin -- remove the file named above and rerun make deps)

w3c:
	@# The W3C scxml conformance tests, the core groups, fetched and written as tests/fixtures/w3c/core.json for the fsm suite.
	$(call log, w3c, fetching the scxml-irp core groups into tests/fixtures/w3c/core.json)
	python3 tests/fixtures/w3c/fetch.py

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
	@# Unpack make, add amk's own sources, and apply the patch series in order, into a fresh tree.
# amk's own sources have no stock counterpart, so they are copied in whole rather than carried as patches.
amk.sources := $(wildcard src/amk/*)
$(make.src): $(make.tarball) $(patch.dirs) $(patches) $(amk.sources)
	$(call log, patch, unpacking $(make.tarball) into $@$(if $(flavor), for flavor $(flavor)))
	rm -rf $@ && mkdir -p $@
	tar xzf $(make.tarball) -C $@ --strip-components=1
	cp $(amk.sources) $@/src/
	$(call apply.series,$@,$(patches),make $(make.version))
	touch $@

# One series into an unpacked tree, in order, each patch by its absolute path: the tree, the patches, and what the tree is, for the error.
apply.series = for p in $(2); do \
	  $(call log, patch, applying $$(basename $$p)); \
	  $(PATCH) -d $(1) -p1 -l -i "$$p" \
	    || $(call die, patch, $$(basename $$p) does not apply to $(3) -- rerun after make clean); \
	done

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
# The commit archive carries the paper pdfs and the pico port beside the engine; the guest needs its sources and its core library.
$(trilog.src): $(trilog.tarball) $(trilog.patches)
	$(call log, patch, unpacking $(trilog.tarball) into $@)
	rm -rf $@ && mkdir -p $@ && tar xzf $(trilog.tarball) -C $@ --strip-components=1 \
	  $(addprefix trilog-$(trilog.commit)/,src include boot lib LICENSE)
	$(call apply.series,$@,$(trilog.patches),trilog $(trilog.short))
	touch $@
# The release tarball carries every port and vendored library; amk's port needs the core, the modules, the shared helpers, six in-tree libraries with mbedtls for ssl, and what it borrows from unix.
micropython.parts := py extmod shared ports/unix/modos.c ports/unix/modtime.c ports/unix/modsocket.c ports/unix/main.c ports/unix/input.c ports/unix/input.h ports/unix/stack_size.h ports/unix/mbedtls lib/mbedtls lib/mbedtls_errors lib/re1.5 lib/uzlib lib/crypto-algorithms lib/oofatfs $(filter-out extmod/%,$(foreach p,$(micropython.pylib),$(lastword $(subst :, ,$(p))))) LICENSE
$(micropython.src): $(micropython.tarball)
	$(call log, patch, unpacking $(words $(micropython.parts)) parts of $(micropython.tarball) into $@ unpatched)
	mkdir -p src && tar xJf $(micropython.tarball) -C src $(addprefix micropython-$(micropython.version)/,$(micropython.parts)) && touch $@
$(wasm3.src): $(wasm3.tarball)
	$(call log, patch, unpacking $(wasm3.tarball) into $@ unpatched)
	rm -rf $@ && mkdir -p src && tar xzf $(wasm3.tarball) -C src && touch $@
$(sqlite.src): $(sqlite.tarball)
	$(call log, patch, unpacking $(sqlite.tarball) into $@ unpatched)
	mkdir -p src && unzip -q -o $(sqlite.tarball) -d src && touch $@
# The release carries bindings, docs and a sample database beside the engine; the guest needs its sources and its license.
$(graphqlite.src): $(graphqlite.tarball)
	$(call log, patch, unpacking $(graphqlite.tarball) into $@ unpatched)
	mkdir -p src && tar xzf $(graphqlite.tarball) -C src $(addprefix graphqlite-$(graphqlite.version)/,src LICENSE) && touch $@
$(tcc.src): $(tcc.tarball) $(tcc.patches)
	$(call log, patch, unpacking $(tcc.tarball) into $@)
	rm -rf $@ && mkdir -p $@ && tar xzf $(tcc.tarball) -C $@ --strip-components=1
	$(call apply.series,$@,$(tcc.patches),tinycc $(tcc.short))
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
$(lxsc.src): $(lxsc.tarball)
	$(call log, patch, placing $(lxsc.tarball) into $@ unpatched)
	mkdir -p $@ && install -m 0644 $(lxsc.tarball) $@/lxsc.lua && touch $@
$(utemplate.src): $(utemplate.tarball)
	$(call log, patch, unpacking $(utemplate.tarball) into $@ unpatched)
	mkdir -p src && tar xzf $(utemplate.tarball) -C src && touch $@
$(effection.src): $(effection.tarball)
	$(call log, patch, unpacking the esm build of $(effection.tarball) into $@ unpatched)
	mkdir -p $@ && tar xzf $(effection.tarball) -C $@ --strip-components=2 package/esm && touch $@

#░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░

guests: $(foreach e,$(engines.linked),$(guests.ape)/$(e).o)
	@# Each guest as one fat relocatable with one global symbol, an input to the ape link.

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

# Trilog's library sources and our entry point; its version header names the pinned commit.
trilog.compile = printf "\#define TRILOG_BUILD_VERSION \"$(trilog.version) ($(trilog.short))\"\n" >version.h && \
                 for c in $(addprefix $(HERE)$(trilog.src)/,$(trilog.sources)) $(HERE)guest/trilog_main.c; do \
                   $(1) $(call guest.cflags,trilog) $(trilog.cflags) -I. $(addprefix -I$(HERE)$(trilog.src)/,$(trilog.includes)) -I$(HERE)guest \
                     -c "$$c" -o "$$(basename $$c .c).o" || exit 1; \
                 done

# MicroPython's own makefiles generate its headers and compile its objects, driven by guest/micropy.mk from guest/ where its config lives; the env, the compiler and the build dir are the arguments, and the version is told rather than asked of the enclosing checkout.
micropython.make = cd guest && env $(1) MAKEFLAGS=-s MICROPY_GIT_TAG=v$(micropython.version) make -f micropy.mk -j$(jobs) CC=$(2) \
                     MICROPYTHON_TOP=$(HERE)$(micropython.src) BUILD=$(HERE)$(3) \
                     CFLAGS_EXTRA='$(call guest.cflags,micropython)' objects
micropython.inputs := guest/micropy.mk guest/micropy_main.c guest/mpconfigport.h guest/mphalport.h guest/amk_guest.h

# wasm3's interpreter sources, its cli, whose main is renamed and kept visible like gawk's, and the kept state in guest/wasm_main.c.
wasm3.compile = for c in $(HERE)$(wasm3.src)/source/*.c $(HERE)$(wasm3.src)/platforms/app/main.c $(HERE)guest/wasm_main.c; do \
                  $(1) $(call guest.cflags,wasm3) $(wasm3.cflags) -I$(HERE)$(wasm3.src)/source -I$(HERE)guest \
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
build/jq-ape/Makefile: $(jq.src) $(cosmocc.dir)/bin/cosmocc
	$(call log, configure, jq $(jq.version) for cosmocc in $(@D))
	rm -rf $(@D) && mkdir -p $(@D)
	cd $(@D) && env $(cosmocc.env) RANLIB=true $(HERE)$(jq.src)/configure $(jq.configure)

# A guest's own executable cannot link once main is renamed and hidden; only its objects are wanted.
build/%-ape/.built: build/%-ape/Makefile
	$(call log, guest, compiling $* for cosmocc -- log at $(@D)/build.log)
	cd $(@D) && env $(cosmocc.env) MAKEFLAGS=-s make -k -j$(jobs) CFLAGS='$(or $($*.guestflags),$(call guest.cflags,$*))' $($*.defs) >build.log 2>&1 || true
	ls $(@D)/$($*.objcheck) >/dev/null 2>&1 \
	  || $(call die, guest, $* compiled no objects -- see the tail of $(@D)/build.log)
	$(if $(value $*.extra),cd $(@D) && env $(cosmocc.env) sh -c '$(call $*.extra,cosmocc)' >>build.log 2>&1 \
	  || $(call die, guest, $*'s extra file did not compile -- see the tail of $(@D)/build.log))
	touch $@
# The extra file is a build input of its guest.
build/jq-ape/.built: guest/jq_main.c guest/amk_guest.h

build/lua-ape/.built: $(lua.src) guest/lua_main.c guest/amk_guest.h $(cosmocc.dir)/bin/cosmocc
	$(call log, guest, compiling lua for cosmocc -- log at $(@D)/build.log)
	rm -rf $(@D) && mkdir -p $(@D)
	cd $(@D) && env $(cosmocc.env) sh -c '$(call lua.compile,cosmocc)' >build.log 2>&1 \
	  || $(call die, guest, lua did not compile -- see the tail of $(@D)/build.log)
	touch $@

build/s7-ape/.built: $(s7.src) guest/s7_main.c guest/amk_guest.h $(cosmocc.dir)/bin/cosmocc
	$(call log, guest, compiling s7 for cosmocc -- log at $(@D)/build.log)
	rm -rf $(@D) && mkdir -p $(@D)
	cd $(@D) && env $(cosmocc.env) sh -c '$(call s7.compile,cosmocc)' >build.log 2>&1 \
	  || $(call die, guest, s7 did not compile -- see the tail of $(@D)/build.log)
	touch $@

build/trilog-ape/.built: $(trilog.src) guest/trilog_main.c guest/amk_guest.h $(cosmocc.dir)/bin/cosmocc
	$(call log, guest, compiling trilog for cosmocc -- log at $(@D)/build.log)
	rm -rf $(@D) && mkdir -p $(@D)
	cd $(@D) && env $(cosmocc.env) sh -c '$(call trilog.compile,cosmocc)' >build.log 2>&1 \
	  || $(call die, guest, trilog did not compile -- see the tail of $(@D)/build.log)
	touch $@

build/micropython-ape/.built: $(micropython.src) $(micropython.inputs) $(cosmocc.dir)/bin/cosmocc
	$(call log, guest, compiling micropython for cosmocc -- log at $(@D)/build.log)
	rm -rf $(@D) && mkdir -p $(@D)
	( $(call micropython.make,$(cosmocc.env),cosmocc,$(@D)) ) >$(@D)/build.log 2>&1 \
	  || $(call die, guest, micropython did not compile -- see the tail of $(@D)/build.log)
	touch $@

build/wasm3-ape/.built: $(wasm3.src) guest/wasm_main.c guest/amk_guest.h $(cosmocc.dir)/bin/cosmocc
	$(call log, guest, compiling wasm3 for cosmocc -- log at $(@D)/build.log)
	rm -rf $(@D) && mkdir -p $(@D)
	cd $(@D) && env $(cosmocc.env) sh -c '$(call wasm3.compile,cosmocc)' >build.log 2>&1 \
	  || $(call die, guest, wasm3 did not compile -- see the tail of $(@D)/build.log)
	touch $@

build/quickjs-ape/.built: $(quickjs.src) guest/js_main.c guest/amk_guest.h $(cosmocc.dir)/bin/cosmocc
	$(call log, guest, compiling quickjs for cosmocc -- log at $(@D)/build.log)
	rm -rf $(@D) && mkdir -p $(@D)
	cd $(@D) && env $(cosmocc.env) sh -c '$(call quickjs.compile,cosmocc)' >build.log 2>&1 \
	  || $(call die, guest, quickjs did not compile -- see the tail of $(@D)/build.log)
	touch $@

# The amalgamation, the guest file, and sqlite's own shell, size-optimized with the extensions and the shared cache left out; the shell's main is renamed so the guest file can wrap it.
sqlite.cflags := -Os -DSQLITE_THREADSAFE=0 -DSQLITE_OMIT_LOAD_EXTENSION -DSQLITE_OMIT_DEPRECATED -DSQLITE_OMIT_SHARED_CACHE -DSQLITE_DQS=0 -DSQLITE_DEFAULT_MEMSTATUS=0
# GraphQLite and the cypher guest compile in their own directory, then join sqlite's partial link, since both call sqlite's api, which the link keeps private; sqlite knows nothing of them. The Cypher parser is bison 3 and flex output, generated from the release's grammar in the Dockerfile's parser stage, so the host build needs neither tool.
graphqlite.parser  := build/graphqlite-parser
graphqlite.grammar := $(graphqlite.src)/src/backend/parser
graphqlite.cflags := -DSQLITE_CORE -Wno-sign-compare -Wno-unused-but-set-variable -I$(HERE)$(graphqlite.src)/src/include -I$(HERE)$(graphqlite.parser)
graphqlite.sources = $$(find $(HERE)$(graphqlite.src)/src $(HERE)$(graphqlite.parser) -name '*.c' ! -name main.c)
graphqlite.compile = for c in $(graphqlite.sources); do \
                   $(1) $(call guest.cflags,sqlite) $(sqlite.cflags) $(graphqlite.cflags) -I$(HERE)$(sqlite.src) -c "$$c" -o "$$(basename $$c .c).o" || exit 1; \
                 done && \
                 $(1) $(call guest.cflags,sqlite) $(sqlite.cflags) -I$(HERE)$(sqlite.src) -I$(HERE)guest -c $(HERE)guest/cypher_main.c -o cypher_main.o
build/graphqlite-ape/.built: $(graphqlite.src) $(graphqlite.parser)/.built guest/cypher_main.c guest/sqlite_guest.h guest/amk_guest.h $(cosmocc.dir)/bin/cosmocc
	$(call log, guest, compiling graphqlite and the cypher guest for cosmocc -- log at $(@D)/build.log)
	rm -rf $(@D) && mkdir -p $(@D)
	cd $(@D) && env $(cosmocc.env) sh -c '$(call graphqlite.compile,cosmocc)' >build.log 2>&1 \
	  || $(call die, guest, graphqlite did not compile -- see the tail of $(@D)/build.log)
	touch $@
$(graphqlite.parser)/.built: $(graphqlite.src) Dockerfile
	$(call log, guest, generating GraphQLite's parser with bison and flex in a container)
	mkdir -p $(@D)
	DOCKER_BUILDKIT=1 docker build -q -f Dockerfile --target parser -t $(docker.image):parser $(@D) >/dev/null
	docker run --rm --user "$$(id -u):$$(id -g)" -v "$(HERE):$(HERE)" -w "$(HERE)" $(docker.image):parser sh -c \
	  'bison -d -o $(graphqlite.parser)/cypher_gram.tab.c $(graphqlite.grammar)/cypher_gram.y \
	   && flex -o $(graphqlite.parser)/cypher_scanner.c --header=$(graphqlite.parser)/cypher_flex.h $(graphqlite.grammar)/cypher_scanner.l'
	touch $@
sqlite.compile = for c in $(HERE)$(sqlite.src)/sqlite3.c $(HERE)guest/sqlite_main.c; do \
                   $(1) $(call guest.cflags,sqlite) $(sqlite.cflags) -I$(HERE)$(sqlite.src) -I$(HERE)guest -c "$$c" -o "$$(basename $$c .c).o" || exit 1; \
                 done && \
                 $(1) $(call guest.cflags,sqlite_shell) $(sqlite.cflags) -I$(HERE)$(sqlite.src) -c $(HERE)$(sqlite.src)/shell.c -o shell.o
build/sqlite-ape/.built: $(sqlite.src) guest/sqlite_main.c guest/sqlite_guest.h guest/amk_guest.h $(cosmocc.dir)/bin/cosmocc
	$(call log, guest, compiling sqlite for cosmocc -- log at $(@D)/build.log)
	rm -rf $(@D) && mkdir -p $(@D)
	cd $(@D) && env $(cosmocc.env) sh -c '$(call sqlite.compile,cosmocc)' >build.log 2>&1 \
	  || $(call die, guest, sqlite did not compile -- see the tail of $(@D)/build.log)
	touch $@

# libtcc and our entry point, after the host builds c2str and turns tinycc's predefined macros into the header libtcc includes.
tcc.compile = cc -DC2STR $(HERE)$(tcc.src)/conftest.c -o c2str && ./c2str $(HERE)$(tcc.src)/include/tccdefs.h tccdefs_.h && \
              for c in $(HERE)$(tcc.src)/libtcc.c $(HERE)guest/tcc_main.c; do \
                $(1) $(call guest.cflags,tcc) $(tcc.cflags) -I. -I$(HERE)guest/tcc -I$(HERE)$(tcc.src) -I$(HERE)guest \
                  -c "$$c" -o "$$(basename $$c .c).o" || exit 1; \
              done
build/tcc-ape/.built: $(tcc.src) guest/tcc_main.c guest/tcc/config.h guest/amk_guest.h $(cosmocc.dir)/bin/cosmocc
	$(call log, guest, compiling tinycc for cosmocc -- log at $(@D)/build.log)
	rm -rf $(@D) && mkdir -p $(@D)
	cd $(@D) && env $(cosmocc.env) sh -c '$(call tcc.compile,cosmocc)' >build.log 2>&1 \
	  || $(call die, guest, tinycc did not compile -- see the tail of $(@D)/build.log)
	touch $@

# The cosmo ld -r keeps hidden symbols global, so objcopy localizes them, once per architecture.
$(guests.ape)/sqlite.o: $(if $(filter graphqlite,$(engines)),build/graphqlite-ape/.built)
$(guests.ape)/%.o: build/%-ape/.built
	$(call log, link, partial-linking $* into link input $@ for x86_64 and aarch64)
	mkdir -p $(@D)/.aarch64
	cd build/$*-ape \
	  && $(cosmocc.dir)/bin/x86_64-linux-cosmo-ld -r $($*.ldflags) \
	       $$(ls $(foreach d,$($*.objdirs),$(d)/*.o) | grep -vE 'conftest$($*.objskip)') \
	       $(if $(call guest.archive,$*),--whole-archive $(call guest.archive,$*) --no-whole-archive) $(call needs.archives,$*) -o $(HERE)$@ \
	  && $(cosmocc.dir)/bin/aarch64-linux-cosmo-ld -r $($*.ldflags) \
	       $$(ls $(foreach d,$($*.objdirs),$(d)/.aarch64/*.o) | grep -vE 'conftest$($*.objskip)') \
	       $(if $(call guest.archive,$*),--whole-archive $(join $(dir $(call guest.archive,$*)),$(addprefix .aarch64/,$(notdir $(call guest.archive,$*)))) --no-whole-archive) \
	       $(foreach a,$(call needs.archives,$*),$(dir $(a)).aarch64/$(notdir $(a))) -o $(HERE)$(@D)/.aarch64/$*.o \
	  && $(cosmocc.dir)/bin/x86_64-linux-cosmo-objcopy $($*.objrename) --localize-hidden $(HERE)$@ \
	  && $(cosmocc.dir)/bin/aarch64-linux-cosmo-objcopy $($*.objrename) --localize-hidden $(HERE)$(@D)/.aarch64/$*.o

#░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░

# The engine list and the version are build inputs like any source, so changing either has to force the relink.
build/.engines$(suffix): FORCE
	mkdir -p $(@D)
	printf '%s\n' '$(engines) $(version.defs)' | cmp -s - $@ || printf '%s\n' '$(engines) $(version.defs)' > $@
build/.libs: FORCE
	mkdir -p $(@D)
	printf '%s\n' '$(libs) $(tools)' | cmp -s - $@ || printf '%s\n' '$(libs) $(tools)' > $@
FORCE:

build: $(artifact.ape)
	@# The fat ape, make with the selected guests, built with cosmocc out of tree, then the payload zipped over it.
compiled.ape := build/ape$(suffix)/make
$(compiled.ape): $(make.src) $(cosmocc.dir)/bin/cosmocc build/.engines$(suffix) $(foreach e,$(engines.linked),$(guests.ape)/$(e).o)
	$(call log, build, make $(make.version) with $(engines) for cosmocc -- this is the slow one)
	rm -rf build/ape$(suffix) && mkdir -p build/ape$(suffix)
	cd build/ape$(suffix) \
	  && export MAKEFLAGS=-s \
	  && env $(cosmocc.env) $(HERE)$(make.src)/configure --disable-dependency-tracking --disable-load CPPFLAGS="$(engines.defs) $(version.defs)" \
	  && env $(cosmocc.env) make -j$(jobs) LIBS="$(foreach e,$(engines.linked),$(HERE)$(guests.ape)/$(e).o) -lm"

repack:
	@# The artifact from the engine already compiled: the payload staged and zipped over it, seconds; a change to the prelude, a library, a tool or amk.sh needs no compile.
	[ -x $(compiled.ape) ] || { $(call log, repack, no compiled engine at $(compiled.ape) -- run make build first); exit 1; }
	$(MAKE) $(artifact.ape)

$(artifact.ape): $(compiled.ape) build/.libs $(tools.files) $(clibs.files) $(foreach l,$(libs),$($(l).src)) $(payload.files) $(payload.lib) guest/amk.sh $(if $(filter cpython,$(engines)),build/cpython-ape/pip)
	$(call log, build, zipping $(tools) into the payload under bin/ and $(or $(libs),no library) under lib/ with the prelude)
	mkdir -p $(bin)
	rm -rf build/payload$(suffix) && mkdir -p build/payload$(suffix)/bin build/payload$(suffix)/lib
	$(foreach t,$(tools),$(foreach n,$(call tool.names,$(t)),install -m 0755 $(call dep.file,$(t)) build/payload$(suffix)/bin/$(n);))
	@# The call channel's shell side rides in bin/ too, so a recipe sources it by name from PATH.
	install -m 0644 guest/amk.sh build/payload$(suffix)/bin/amk.sh
	$(foreach l,$(libs),$(foreach f,$(addprefix $(call lib.dir,$(l)),$($(l).files)),mkdir -p $(dir $(call payload.dest,lib/$(f))) && install -m 0644 $($(l).src)/$(f:$(call lib.dir,$(l))%=%) $(call payload.dest,lib/$(f));))
	$(if $(filter micropython,$(engines)),$(foreach p,$(micropython.pylib),mkdir -p $(dir $(call pylib.dest,$(p))) && install -m 0644 $(micropython.src)/$(lastword $(subst :, ,$(p))) $(call pylib.dest,$(p));))
	$(if $(filter trilog,$(engines)),mkdir -p $(call payload.dest,lib/trilog/boot) $(call payload.dest,lib/trilog/lib) \
	  && install -m 0644 $(trilog.src)/boot/core.pl $(trilog.src)/LICENSE $(call payload.dest,lib/trilog/boot/) \
	  && install -m 0644 $(trilog.src)/lib/*.pl $(call payload.dest,lib/trilog/lib/))
	$(optin.payload)
	$(foreach f,$(payload.files),mkdir -p $(dir $(call payload.dest,$(f))) && install -m 0644 $(f) $(call payload.dest,$(f));)
	$(foreach f,$(payload.lib),mkdir -p $(dir $(call payload.dest,$(f))) && install -m 0644 $(f) $(call payload.dest,$(f));)
	@# zip names an archive without an extension by appending one, so the payload goes into an .ape copy.
	cp build/ape$(suffix)/make build/payload$(suffix)/amk.ape
	cd build/payload$(suffix) && zip -q -r amk.ape bin $(if $(libs)$(filter micropython trilog,$(engines))$(strip $(payload.lib))$(filter lib,$(optin.payload.dirs)),lib) $(filter-out lib,$(optin.payload.dirs)) $(patsubst payload/%,%,$(payload.files))
	rm -f $@ && install -m 0755 build/payload$(suffix)/amk.ape $@
	for n in $$($(call engines.names,$@)); do ln -sf amk $(bin)/$$n; done
	$(call log, build, artifact $@ is ready -- $(bin) holds every engine name and alias for it)

# The gmsl suite against the payload copy, from a directory that holds the suite but not the library, both ways upstream runs it; gmsl reads unset arguments by design, so the prelude's undefined-variable warnings are shown only when the suite fails.
gmsl.tests = cd build/gmsl && for mode in EXPORT_ALL= EXPORT_ALL=1; do \
	  out=$$(sh -c "$(abspath $(artifact.ape)) -I /zip/lib/gmsl -f gmsl-tests $$mode" 2>&1); \
	  echo "gmsl-tests $$mode: $$(echo "$$out" | tail -1)"; \
	  case "$$out" in *'; 0 tests failed'*) ;; *) echo "$$out" >&2; exit 1;; esac; \
	done

smoke: $(artifact.ape) smoke.demos
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
	$(if $(filter jb,$(tools)),sh -c "$(artifact.ape) -f smoke.mk jb")
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
	test "$$(comm -13 build/bundle/base.list build/bundle/b.list | tr '\n' ' ')" = "__main__.mk lib/greet.mk lib/js/dup.js lib/lua/dup.lua lib/sub/deep.mk "
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
# The wasm demos need the opt-in engine and docker, so a build without wasm3 leaves them out.
demos.wasm := $(wildcard demos/wasm-*.amk)
# The trilog demos need trilog, so a build without it leaves them out.
demos.trilog := $(wildcard demos/trilog-*.amk)
# The tcc demos need tcc, so a build without it leaves them out.
demos.tcc := $(wildcard demos/tcc-*.amk)
demos.skip := $(if $(filter wasm3,$(engines)),,$(demos.wasm)) $(if $(filter trilog,$(engines)),,$(demos.trilog)) $(if $(filter tcc,$(engines)),,$(demos.tcc))
# Smoke opts demos in by name: the wasm ones, whose toolchain images are heavy downloads.
demos.smoke := $(demos.wasm)
demos := $(filter-out $(demos.skip),$(demos.smoke))
# Integration takes the rest at run time: every committed demo at the top of demos/, so a file under demos/experimental/ is never collected.
demos.committed = $(filter $(wildcard demos/*.amk),$(shell git -C $(HERE) ls-files demos))
demos.integration = $(filter-out $(demos.skip) $(demos.smoke),$(demos.committed))
# Each demo runs its default goal and must exit zero; each demo checks itself.
demos.run = for demo in $(2); do echo "$$demo"; sh -c "$(artifact.ape) -f $$demo" || exit 1; done; \
  $(call log, $(1), every demo exited zero)
smoke.demos: $(artifact.ape)
	@# The demos named by demos.smoke.
	$(call log, smoke.demos, running $(words $(demos)) demos$(if $(demos.skip), and skipping $(demos.skip)))
	$(call demos.run,smoke.demos,$(demos))
itest: $(artifact.ape)
	@# Every committed demo that smoke does not name, found at run time.
	$(call log, itest, running $(words $(demos.integration)) demos$(if $(demos.skip), and skipping $(demos.skip)))
	$(call demos.run,itest,$(demos.integration))

# The pytest suite under tests/ needs the binary and pytest, nothing else; pytest= names a runner that is not on PATH, and pytest.args= adds flags.
pytest      ?= $(or $(wildcard $(HERE).venv/bin/pytest),$(shell command -v pytest 2>/dev/null || echo python3 -m pytest))
pytest.args ?=
test: $(artifact.ape)
	@# The pytest suite against the fat ape: the resident roles, the argv builtins, ape-unpack, and bundles.
	$(call log, test, pytest under tests/ against $(artifact.ape) -- expect about a minute)
	env AMK_BIN=$(abspath $(artifact.ape)) $(pytest) tests $(pytest.args)
test.upstream: $(artifact.ape)
	@# GNU make's own regression suite from the patched source, against the fat ape; the pytest wrapper pins the per-script pass counts to tests/fixtures/make-suite.txt.
	$(call log, test.upstream, make $(make.version)'s suite under $(make.src)/tests against $(artifact.ape) -- expect several minutes; log in build/make-suite.log)
	env AMK_BIN=$(abspath $(artifact.ape)) $(pytest) tests -p no:xdist -m upstream $(pytest.args)
test.integration: $(artifact.ape)
	@# The tests that start servers, hold ports, or reach the network, one at a time; network= left empty skips the ones that fetch.
	$(call log, test.integration, the integration tests against $(artifact.ape) one at a time -- the network ones fetch from GitHub)
	env AMK_BIN=$(abspath $(artifact.ape)) $(pytest) tests -p no:xdist -m '$(if $(network),integration,integration and not network)' $(pytest.args)
network ?= 1

# The image: docker execs an entrypoint without the shell an ape needs, so the context holds an assimilated executable per arch; BuildKit is required, since the legacy builder leaves the target arch empty.
docker.dir    := build/docker$(suffix)
docker.arches := amd64 arm64
docker.image  ?= amk
docker.tag    ?= $(amk.version)$(suffix)$(if $(dist),,$(foreach e,$(filter $(engines.optin),$(engines)),-$(e)))
assimilate.amd64 := -x
assimilate.arm64 := -a
# Inside the image the artifact is the installed one; the wasm demos build their modules with docker, which the image does not carry.
docker.smoke.args = -o /usr/local/bin/amk artifact.ape=/usr/local/bin/amk bin=/usr/local/bin demos.skip='$(demos.wasm)' \
  $(foreach v,amk.version with without dist flavor patch.dirs,$(v)='$($(v))')

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
	  && for n in $$($(call engines.names,$(artifact.ape))); do ln -sf amk $(docker.dir)/$(a)/$$n; done;)
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
	$(call show, input, $(guests.ape), guest relocatables both arches -- the slow half of a build)
	$(call show, input, src, unpacked sources -- make patched and the guests pristine)
	$(call show, input, cosmocc, the unpacked toolchain)

#░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░

vscode.stage = out/vscode
vscode.vsix  = out/amk.vsix

vscode:
	@# Generate the editor grammars, pack them as $(vscode.vsix), and install that with code.
	for t in node zip code; do command -v $$t >/dev/null || $(call die, vscode, $$t is not on PATH); done
	rm -rf $(vscode.stage) $(vscode.vsix)
	$(call log, vscode, generating the injection grammars from vscode/build.js into $(vscode.stage))
	node $(HERE)vscode/build.js $(vscode.stage)
	$(call log, vscode, bodies under $$(node -e 'const {ENGINES}=require("$(HERE)vscode/build.js"); console.log(Object.keys(ENGINES).map((e) => "@" + e).join(" "))') take their language -- plus the decorator grammar and the make references inside a body)
	$(call log, vscode, packing $(vscode.stage) as $(vscode.vsix))
	cd $(vscode.stage) && zip -qrX $(abspath $(vscode.vsix)) '[Content_Types].xml' extension.vsixmanifest extension
	$(call log, vscode, $$(du -h $(vscode.vsix) | cut -f1) -- installing with code --install-extension --force)
	NODE_NO_WARNINGS=1 code --install-extension $(vscode.vsix) --force >/dev/null
	$(call log, vscode, installed $$(code --list-extensions --show-versions 2>/dev/null | grep -i '[.]amk@' || echo the extension) -- the .amk extension opens in Makefile mode with the amk grammars injected; reload the window to pick it up)

#░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░

# A release is a push to main; the Release workflow chooses the next version, builds, and publishes it.
release.remote ?= origin
release.branch  = $$(git branch --show-current)

release: release.preflight
	@# Push main and watch the Release run for the head commit when gh is on PATH.
	git push $(release.remote) main
	$(call log, release, pushed main -- the Release workflow numbers, builds, and publishes it)
	if command -v gh >/dev/null; then $(MAKE) release.watch; else $(call log, release, gh is not on PATH -- watch the run under Actions); fi

release.preflight:
	@# The branch is main and the tree is committed.
	[ "$(release.branch)" = main ] \
	  || $(call die, release, a release is cut from main -- this is $(release.branch))
	[ -z "$$(git status --porcelain --untracked-files=no)" ] \
	  || { git status --short --untracked-files=no >&2; $(call die, release, the working tree has uncommitted changes); }
	$(call log, release, preflight ok -- main is committed)

release.watch:
	@# Stream the Release run for the head commit to completion; rerun this alone to reattach.
	sha=$$(git rev-parse HEAD); rid=; for i in $$(seq 1 30); do \
	  rid=$$(gh run list --workflow release.yml --commit $$sha --limit 1 --json databaseId --jq '.[0].databaseId'); \
	  if [ -n "$$rid" ]; then break; fi; sleep 5; \
	done; \
	[ -n "$$rid" ] || $(call die, release, no Release run found for $$sha -- a commit that changes only docs or images starts none); \
	$(call log, release, streaming run $$rid); gh run watch "$$rid" --exit-status

clean:
	@# Drop the landed deliverable, the unpacked sources, build trees, and outputs; src/amk is amk's own source and stays.
	$(call log, clean, dropping $(deliverable) src build out -- this costs a full rebuild)
	$(call log, clean, the downloads, $(cosmocc.dir) and src/amk stay)
	rm -rf $(deliverable) $(filter-out src/amk,$(wildcard src/*)) build out

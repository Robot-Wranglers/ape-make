<!-- header amk "amk" | Overview #overview | Install #install | Bundling #bundling | Guests #guests | Special Guests #special-guests | Zygote #zygote | CLI #cli | Dev #dev -->
<p align="right"><a id="amk"></a><a href="#amk"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.amk.title.dark.svg"><img align=left src="docs/img/hdr/readme.amk.title.svg" alt="amk"></picture></a><a href="#overview"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.amk.0.dark.svg"><img src="docs/img/hdr/readme.amk.0.svg" alt="Overview"></picture></a><a href="#install"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.amk.1.dark.svg"><img src="docs/img/hdr/readme.amk.1.svg" alt="Install"></picture></a><a href="#bundling"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.amk.2.dark.svg"><img src="docs/img/hdr/readme.amk.2.svg" alt="Bundling"></picture></a><a href="#guests"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.amk.3.dark.svg"><img src="docs/img/hdr/readme.amk.3.svg" alt="Guests"></picture></a><a href="#special-guests"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.amk.4.dark.svg"><img src="docs/img/hdr/readme.amk.4.svg" alt="Special Guests"></picture></a><a href="#zygote"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.amk.5.dark.svg"><img src="docs/img/hdr/readme.amk.5.svg" alt="Zygote"></picture></a><a href="#cli"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.amk.6.dark.svg"><img src="docs/img/hdr/readme.amk.6.svg" alt="CLI"></picture></a><a href="#dev"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.amk.7.dark.svg"><img src="docs/img/hdr/readme.amk.7.svg" alt="Dev"></picture></a><br clear="all"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/_rule.dark.svg"><img width=2000 height=1 src="docs/img/hdr/_rule.svg" alt=""></picture></p>
<!-- /header -->

<p align="center"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/icon-dark.svg"><img src="docs/img/icon.svg" width="60%" alt="amk"></picture></p>

<p><strong>amk</strong> is ape-make, an actually portable cosmopolitan <code>make</code>.  It's a drop in replacement forked from make-4.4.1, but with enough brand new superpowers that it's a distinct dialect.</p>

Broadly, `amk` transforms what is already your default choice for a *coordination language* into a **small-but-powerful polyglot VM**.  Huh?  Ok.. `amk` stays close to shell if you need that, but is also effectively a portable, multi-language scripting environment without any need for docker.  Besides embedding support for [python](#micropy), [lua](#lua), [lisp](#s7), and [wasm](#wasm), it also provides other support for bidirectional FFI, can handle modules, package external tools, and can output a bundle as a portable artifact.

One consequence of this is that Makefile *(and a small, optional extension of the baseline grammar)* remains an incremental computing toolkit suitable for DAGs and builds, but also turns into a more powerful **polyglot data-flow language**.  Huh?  Ok.. Think of it as something like a notebook where downstream cells can update when the prerequisites change.

Hater who thinks `make` is only a build tool?  Now it's definitely not.  Enthusiast who loves `make`, but sort of wishes it was a Real Language(tm)?  Now it definitely is.

## Just Show Me

Here's a JSON-RPC server where every method lives in a different language and `amk` glues them together.  Transport works via HTTP, using a python guest, serving with microdot *(like flask, but smaller)* from mip *(like pip, but micropython)*.

```Makefile
#!/usr/bin/env -S amk -f

PORT ?= 18090

include /zip/lib/mip.mk

@lua.import
define lua_namespace
  function add(a, b) return tonumber(a) + tonumber(b) end
  function sorted(xs)
    local t = {}
    for x in xs:gmatch("%S+") do t[#t + 1] = tonumber(x) end
    table.sort(t)
    return table.concat(t, " ")
  end
endef

@js.import
define js_namespace
  function shout(s) { return s.toUpperCase() + "!"; }
  function report(sorted, total) {
    return JSON.stringify({
      sorted: sorted.split(" ").map(Number),
      total: Number(total) }); }
endef

@s7.import
define s7_namespace
  (define (fact n)
    (let loop
      ((n (string->number n)) (acc 1)) \
      (if (< n 2) acc (loop (- n 1) (* n acc)))))
  (define (total xs)
    (apply + (with-input-from-string (string-append "(" xs ")") read)))
endef

# Another method, composed on host, made up of different guests
stats = $(report $(sorted $1),$(total $1))

# Register the host method directly and all guests via reflection
rpc.methods = stats $(amk.fxns? lua, js, s7)

# HTTP server deps (caching after first run)
define mip.manifest
  { "microdot": {
      "version": "v2.7.0",
      "spec": "github:miguelgrinberg/microdot/src/microdot/microdot.py",
      "sha256": "7abf80436064aff030fb123c2947260674c84001517322d7c8517b7f2425e01a"
    }
  }
endef

@micropy.import
define rpc.server
  import amk, json, sys

  # Read-from-host: published methods from top-level registry
  methods = amk.var["rpc.methods"].split()

  def _val(s):
    try: return json.loads(s)
    except ValueError: return s

  def _arg(p):
    return " ".join(map(str, p)) \
      if isinstance(p, list) else str(p)

  def serve(port):
    from microdot import Microdot
    app = Microdot()

    @app.post("/")
    async def rpc(req):
      q = req.json
      reply = dict(jsonrpc="2.0", id=q["id"])
      if q["method"] not in methods:
        reply["error"] = dict(code=-32601, message="No Such Method")
        return reply
      params = [_arg(p) for p in q["params"]]

      # Async-call dispatch back into other guests: `amk.acall`
      reply["result"] = _val(await amk.acall(q["method"], *params))
      return reply

    print("http://127.0.0.1:%s/" % port, file=sys.stderr)
    print("Methods: %s" % " ".join(methods), file=sys.stderr)
    app.run(port=int(port))
endef

__main__:
	echo "json-rpc: methods $(rpc.methods)"
	echo "run it with: $(amk) serve PORT=$(PORT)"

serve: mip.install
	$(serve $(PORT))
```

Run it with `amk -f demos/json-rpc.mk serve`, then post a request:

```bash
curl -s -X POST \
  -H 'Content-Type: application/json' http://127.0.0.1:18090/ \
  -d '{ "jsonrpc":"2.0","id":1, "method":"stats","params":["3 1 2"]}'
# {"jsonrpc": "2.0", "id": 1, "result": {"sorted": [1, 2, 3], "total": 6}}
```

A toy example, but what do you think?  Not so far away from useful FAAS or MCP, eh?  The whole thing is in the repo [here](demos/json-rpc.mk), runnable from a checkout.  Highlights:

* Optional [extended grammar](#extended-grammar) with `@lua.import` and friends
* [Simple reflection](docs/FFI.md#reflection) with `amk.fxns?`
* [Bundled builtin libs](#builtin-libraries), via `include /zip/..`
* [Guest handle](#bridge-mode), as seen in `amk.var`, `amk.acall`

For smaller demos jump to [this section](#misc-examples), and for a larger one more in the notebook / dataflow style, see [here](demos/dataflow-1.mk).  With that out of the way.. back to the docs.

<a id="overview"></a><br/>

## Overview

The main use-cases:

1. **[Bundling & Distribution](#bundling):**  Solves for *bundles anything* as well as *runs anywhere*.  Did you know that all APEs are at once bins and zip files?  Besides just being platform-agnostic `amk` leverages this into a working *quasi-compiler* for Makefile, i.e. producing new executables by shipping source file(s) with a copy of the interpreter.  Code involved *does not* actually need to be Makefile either.. a layered approach to bootstrap permits any language that `amk` embeds to work, or, several can be involved.  **Shipping monoliths composed of modules is easy.**

1. **[Standard Guests](#guests)** are the other part of (1), meaning that besides `make`, the *rest* of the toolchain can also be APE'd riders.  Could be anything, but the usual thing is the shell toolkit;  No worries if `make` is available **or** which `awk` is available, or if either is available.  **Portable scripting environment, no containers.**

1. **[Special Guests](#special-guests):** Basically a **polyglot VM in miniature!** Shell remains a fist-class citizen, but `amk` also exposes embedded engines for things like **[python](#micropy), [lua](#lua), [lisp](#s7), and [wasm](#wasm),** with a familiar coordination language already in place to switch between them.  **A tiny Graal, but without JDK.**

1. **[Zygote / Resident Mode](#zygote):**  Useful to avoid cold-start penalties in many circumstances.  Side-effect free?  Execution freezes a program, then runs and re-runs against the same base without a re-parse.  Keep most of the "incremental computing" model, get extras for **improved recursion, FP, workflows, dataflows.**

Besides the major features above, there's a grab-bag of other extras: [built-in profiler](docs/dev.md#profiling), new [built-in functions](#functions) for things like regex, and [syntax-highlighting support](docs/syntax-hl.md).

<a id="install"></a><br/>

## Quick Start

Just grab a release.

```bash
curl -fsSLO \
  https://github.com/Robot-Wranglers/ape-make/releases/latest/download/amk
chmod +x amk
mkdir -p ~/.local/bin && mv amk ~/.local/bin/
amk --version
```

Apple silicon's first run may need a C compiler.. run `xcode-select --install` if `cc` is missing.  (Annoying, but it's an upstream thing about code-signing, see [cosmo docs](https://github.com/jart/cosmopolitan/blob/master/tool/cosmocc/README.md#gotchas))

Each release carries a checksum beside the binary:

```bash
curl -fsSLO \
  https://github.com/Robot-Wranglers/ape-make/releases/latest/download/amk.sha256

# linux:
sha256sum -c amk.sha256   

# on macOS: 
shasum -a 256 -c amk.sha256
```

A first run, with lua doing the arithmetic:

```bash
printf 'hello:\n\techo $(lua print(6 * 7))\n' | amk -f - hello
# 42
```

### Docker

```bash
docker run --rm -v "$PWD:/work" \
  ghcr.io/robot-wranglers/amk:latest <target>
```

Use the `wasm3` tag for the build with the [wasm](#wasm) engine.  Also of interest, `amk` on your host is typically usable from from *any* container if you want to bind-mount the binary.

<a id="bundling"></a><br/>
<a id="payloads"></a><br/>

## Bundling & Distribution

The typical use-case for bundling is creating a new standalone executable.  This works by cloning the `amk` runtime, bundling extras, and setting the new entrypoint:

<a id="bundles"></a>

```bash
# first file is the entry; a directory adds everything under it
amk --bundle main.mk lib/ --out my.tool

# artifact proxies to entrypoint in main.mk, from any directory
./my.tool my.target      

# a bundle is still a full amk
./my.tool -f other.mk                   

# spin-offs: add new entrypoint, keep same lib/
./my.tool --bundle another.mk --out second.tool

# artifact extraction: copy things outside of 
# the bundle using `--ape-unpack NAME` or `-x`
./my.tool -x main.mk
```

Extraction prints the path and skips the copy when one is already current.  Among other things this means that a "quasi-compiled" artifact from `amk` can still act as a normal library in any vanilla `make` / Makefile setup, like so:

```Makefile
include $(shell ./my.tool --ape-unpack=lib/greet.mk)
```

Inside a bundle, `include` can resolve against the payload and `$(MAKE)` reaches the same program.

- Run `--bundle` from the directory your includes are relative to; archive members keep those names.
- A file of the same name in the working directory shadows a payload include.
- Bundling needs nothing but amk: no compiler, no external `zip` tool.

<a id="guests"></a><br/>

## Standard Guests

Standard guests are bundled tools and a few libraries that ride along in the payload.

The problem this solves is that certain platforms (looking at you MacOS, but also minimal containers) may default to having *other* utilities besides `make` which are missing by default, or non-GNU, or pinned to incredibly ancient versions.  Usual suspects might include things like *bash, awk, sed, jq*.  Luckily this is solvable with some combination of APEs and bundling, so, `amk` ships with those and a few more.

<a id="tools"></a><br/>

### Bundled Tools

| tool | version | from | run as |
| --- | --- | --- | --- |
| sed | GNU sed 4.9 (cosmos 4.0.2) | [cosmo.zip](https://cosmo.zip/pub/cosmos/v/4.0.2/bin/) |
| bash | 5.2.0 (cosmos 4.0.2) | [cosmo.zip](https://cosmo.zip/pub/cosmos/v/4.0.2/bin/) |
| awk | gawk 5.3.1 | [ftp.gnu.org](https://ftp.gnu.org/gnu/gawk/) | 
| jq | 1.7.1 | [github.com/jqlang](https://github.com/jqlang/jq/releases/tag/jq-1.7.1) | 
| jb | json.bash 0.3.0 | [github.com/h4l](https://github.com/h4l/json.bash/tree/v0.3.0) | 

Bundled tools are on `PATH` for any recipe, on any host, ahead of the system path, so reference by name just works.  For example.. a modern bash on MacOS, and a working bash even in a container where it doesn't ship.

```Makefile
SHELL:=bash
check:
	echo "$${BASH_VERSINFO[0]}"
```

In a few cases the standard guests are also [*special guests*](#special-guests), which we'll discuss in more detail [later](#tool-mode).  Briefly though, `jq` and `awk` are *linked* as well as bundled.  Thus `jq` is available via libjq, and via `$(jq ..)` from Makefiles, with no penalty for forking a subprocess.  Great!, now JSON is a native "type" and your portable, compiled Makefile looks to have suddenly grown sophisticated datastructures, and a query-language, with no speed penalty.

### Builtin Libraries

A library is portable if its platform is, so it only needs to ride in the payload.  Your own libraries [bundle](#bundling) the same way, so the builtin list stays short: things almost always needed, or needed at bootstrap.

| library | version | from | use as |
| --- | --- | --- | --- |
| gmsl | 1.2.4 | [github.com/jgrahamc](https://github.com/jgrahamc/gmsl/tree/v1.2.4) | `include /zip/lib/gmsl` for sets, associative arrays, stacks, and integer and string ops in pure make |
| dkjson | 2.8 | [dkolf.de](http://dkolf.de/dkjson-lua/) | `require("dkjson")` inside [`$(lua)`](#lua) for JSON |
| mip | micropython-lib | [github.com/micropython](https://github.com/micropython/micropython-lib) | `include /zip/lib/mip.mk` for pinned [micropy](#micropy) packages, through `mip.manifest` and `mip.install` |

<!-- header special-guests "Special Guests" | Tool #tool-mode | Eval #eval-mode | Exec #exec-mode | Import #import-mode | Bridge #bridge-mode | Engine API #engine-api | Examples #misc-examples -->
<p align="right"><a id="special-guests"></a><a href="#special-guests"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.special-guests.title.dark.svg"><img align=left src="docs/img/hdr/readme.special-guests.title.svg" alt="Special Guests"></picture></a><a href="#tool-mode"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.special-guests.0.dark.svg"><img src="docs/img/hdr/readme.special-guests.0.svg" alt="Tool"></picture></a><a href="#eval-mode"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.special-guests.1.dark.svg"><img src="docs/img/hdr/readme.special-guests.1.svg" alt="Eval"></picture></a><a href="#exec-mode"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.special-guests.2.dark.svg"><img src="docs/img/hdr/readme.special-guests.2.svg" alt="Exec"></picture></a><a href="#import-mode"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.special-guests.3.dark.svg"><img src="docs/img/hdr/readme.special-guests.3.svg" alt="Import"></picture></a><a href="#bridge-mode"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.special-guests.4.dark.svg"><img src="docs/img/hdr/readme.special-guests.4.svg" alt="Bridge"></picture></a><a href="#engine-api"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.special-guests.5.dark.svg"><img src="docs/img/hdr/readme.special-guests.5.svg" alt="Engine API"></picture></a><a href="#misc-examples"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.special-guests.6.dark.svg"><img src="docs/img/hdr/readme.special-guests.6.svg" alt="Examples"></picture></a><br clear="all"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/_rule.dark.svg"><img width=2000 height=1 src="docs/img/hdr/_rule.svg" alt=""></picture></p>
<!-- /header -->

Special guests are the embedded engines that are linked into `amk` directly.

| engine | version | from | adds | default |
| --- | --- | --- | --- | --- |
| [gawk](#awk-jq) | 5.3.1 | [ftp.gnu.org](https://ftp.gnu.org/gnu/gawk/) | 1.3 MB | on |
| [jq](#awk-jq) | 1.7.1 | [github.com/jqlang](https://github.com/jqlang/jq/releases/tag/jq-1.7.1) | 1.9 MB | on |
| [lua](#lua) | 5.4.8 | [lua.org](https://www.lua.org/ftp/) | 0.5 MB | on |
| [s7](#s7) | 11.9 | [ccrma.stanford.edu](https://ccrma.stanford.edu/software/s7/) | 4.1 MB | on |
| [micropython](#micropy) | 1.29.0 | [github.com/micropython](https://github.com/micropython/micropython/releases/tag/v1.29.0) | 0.8 MB | on |
| [quickjs](#js) | 2026-06-04 | [bellard.org](https://bellard.org/quickjs/) | 2.0 MB | on |
| [wasm3](#wasm) | 0.9.0 | [github.com/wasm3](https://github.com/wasm3/wasm3/tree/v0.9.0) | 0.4 MB | off |

Besides the choice of guest, two other concepts that relate to the engine API are **Interface Style** and **Access Mode**.  This section is an overview of each mode / style with examples, but it's a quick guide, and not a full reference.  See the [full FFI documentation](docs/FFI.md) for the gory details.

<!-- Each guest backend has a more or less unified interface, so there's not a demo in every language for every mode.  Just switch out the engine name (i.e. `eng` below) for whatever you're interested in (e.g. `micropy`, `lua`, `s7`, `js`, etc).  That said.. backend implementation details can differ, and so details for FFI support can also differ.  In particular `wasm` and `jq` are misfits: `wasm` takes a [module](#wasm) rather than program text, and `jq` keeps its state in a [store](docs/FFI.md#the-jq-store).  The [capabilities table](docs/FFI.md#capabilities-by-engine) has the per-engine breakdown. -->

**Interface Style:**

1. [Pass by Value](#pass-by-value):
1. [Pass by Reference](#pass-by-reference):
1. [Extended Grammar](#extended-grammar):

**Guest Access Modes:**

1. [Tool Mode](#tool-mode): A CLI interface you can script against directly.
1. [Eval Mode](#eval-mode): Stateless compute in guest.  Usually lifting vals into host
1. [Exec Mode](#exec-mode):  Stateful engine / persistent guests
1. [Import Mode](#import-mode): Lift whole namespaces (functions + variables)
1. [Bridge Mode](#bridge-mode): Guest-to-host actions or reads; Guest-to-guest calls

<!-- header engine-api "Engine API" | By value #pass-by-value | By reference #pass-by-reference | Grammar #extended-grammar -->
<p align="right"><a id="engine-api"></a><a href="#engine-api"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.engine-api.title.dark.svg"><img align=left src="docs/img/hdr/readme.engine-api.title.svg" alt="Engine API"></picture></a><a href="#pass-by-value"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.engine-api.0.dark.svg"><img src="docs/img/hdr/readme.engine-api.0.svg" alt="By value"></picture></a><a href="#pass-by-reference"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.engine-api.1.dark.svg"><img src="docs/img/hdr/readme.engine-api.1.svg" alt="By reference"></picture></a><a href="#extended-grammar"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.engine-api.2.dark.svg"><img src="docs/img/hdr/readme.engine-api.2.svg" alt="Grammar"></picture></a><br clear="all"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/_rule.dark.svg"><img width=2000 height=1 src="docs/img/hdr/_rule.svg" alt=""></picture></p>
<!-- /header -->

#### Interface Style

##### Pass by Value

Passing literals is the most basic thing you can do for each engine mode.

```Makefile
# Eval-mode
$(eng program, [input])
$(eng.argv argv, program, [input])

# Exec-mode: an operation in the namespace main, one argument, so the program keeps its commas
$(eng.exec program)
$(eng.ns workspace, create)
$(eng.ns workspace, exec, program)
$(workspace.exec program)

# Import-mode
$(eng.import program)
$(eng.import.target program)
```

See [Misc Examples](#misc-examples) for concrete examples, and the extended documentation [here](docs/FFI.md#pass-by-value) for every form by engine.

<a name=star-mode></a>
<a id="pass-by-reference"></a>

##### Pass by Reference

Star-mode version of the API.  The trouble with literals is that it breaks down for multi-lines, escaping or quoting hazards etc.  In that case you'll want star-mode calls, where we try to dereference variables to grab values and *fall back* to literal mode only if no variables are available.

```Makefile
# Eval-mode
$(eng* program_var, [input_var])
$(eng.argv* argv, program_var, [input_var])

# Exec-mode: only the program is dereferenced; the workspace and the op pass as written
$(eng.exec* program_var)
$(eng.ns* workspace, exec, program_var)
$(workspace.exec* program_var)

# Import-mode
$(eng.import* program_var)
$(eng.import.target* program_var)
```

See the extended documentation [here](docs/FFI.md#pass-by-reference) for every form by engine.

##### Extended Grammar

We met the optional, extended Makefile grammar already in the [server example](#) in the introduction.  This section describes how it works, and why it's simpler than it looks.

First, recall the [pass-by-reference](#pass-by-reference) interface style from the last section.  The usual thing is to put guest code in a `define my_prog .. endef` block then use an API call like `$(my_engine.import* my_prog)` on that same block, dereferencing the value from the var and passing it into the engine.

Much more readable to flip it though, which is exactly what the decorator-style idiom does, now dropping the star since it's implied.  No extra semantics, just syntactic sugar:

```Makefile
@my_engine.import
define my_prog
  ..guest program, optionally indented..
endef
```

Note that this also works the same way for the full pass-by-reference API *(i.e. everything that ends with star)*, and not just `<eng>.import`.

The only other piece of optional grammar is `@goal@` substitution, a useful trick for dataflow.  See the full documentation [here](docs/dataflow.md).

### Access Mode

#### Tool Mode

As a degenerate kind of [eval mode](#eval-mode) where special-guests meet standard-guests.. tool mode maybe isn't that interesting, but we introduce it for completeness.

```bash
# Flag first, then the rest goes to the tool
./amk --awk 'BEGIN { print "hello" }'

# Same for jq, lua, python, etc
printf '{"n":41}' | ./amk --jq .n+1

# Names matter!
# So a symlink named for the tool works the way you'd expect.
ln -s amk awk && ./awk 'BEGIN { print "hello" }'
```

From inside a Makefile, every other mode is better than tool-mode. A tool call is a fork you can avoid by using an engine!  But if you insist:

```Makefile
#! /usr/bin/env amk -f

# bundled jq and awk are on PATH already, just use them.
my_target:; jq ...

# equivalently, and introducing the way amk calls itself.
my_other_target:; ${amk} --jq ...
```

#### Eval Mode

Eval-mode is useful for many things, but most often it's a way to "lift" computed values from guests into the host.  For example, working around the impoverished Makefile primitives, getting real numbers, regex, or string operations done easily.

```Makefile
answer.lua := $(lua print(6 * 7))
```

Works fine with simple stuff, and not so simple.  Besides values, you could also code-gen targets, avoiding the eval/foreach type of pure-Makefile loops.  Despite the "eval" name.. nothing prevents importing modules in the guest, etc.  

Since line-feeds and escaping gets annoying quickly, using multiline data and multiline programs is common.

```Makefile
define words
  the quick brown fox
  jumps over the lazy dog
endef

define lua.count
  local n = 0
  for line in io.lines() do
    for _ in line:gmatch("%S+") do n = n + 1 end
  end
  print(n)
endef

count := $(lua ${lua.count}, $(words))

# or, using star-mode
count := $(lua* lua.count, words)
```

<!-- header exec-mode "Exec Mode" | Persistent state docs/FFI.md#persistent-state | Init docs/FFI.md#init -->
<p align="right"><a id="exec-mode"></a><a href="#exec-mode"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.exec-mode.title.dark.svg"><img align=left src="docs/img/hdr/readme.exec-mode.title.svg" alt="Exec Mode"></picture></a><a href="docs/FFI.md#persistent-state"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.exec-mode.0.dark.svg"><img src="docs/img/hdr/readme.exec-mode.0.svg" alt="Persistent state"></picture></a><a href="docs/FFI.md#init"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.exec-mode.1.dark.svg"><img src="docs/img/hdr/readme.exec-mode.1.svg" alt="Init"></picture></a><br clear="all"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/_rule.dark.svg"><img width=2000 height=1 src="docs/img/hdr/_rule.svg" alt=""></picture></p>
<!-- /header -->

Exec-mode gives a persistent stateful engine on the backend instead of a one-shot eval.  Each `exec` runs in the same state, and `ns` makes more of them:

```Makefile
$(lua.exec total = 40)
$(lua.exec total = total + 2)

# 42
answer := $(lua.exec print(total))

# a second workspace, reached through its handle
$(lua.ns work, create)
$(work.exec total = 1)

# 1 42
both := $(work.exec print(total)) $(lua.exec print(total))
```

#### Import Mode

Import runs a chunk in the engine's persistent state and lifts every global it defines into make.  Guest functions map onto make functions, any other value a variable.  The [decorator](#extended-grammar) form is the usual way to write it:

```Makefile
@lua.import
define lua.lib
  version = "1.2.3"
  pkg = { name = "abc" }
  function bump(v) return (v:gsub("%d+$", function(n) return n + 1 end)) end
endef

# abc 1.2.4
next := $(pkg.name) $(bump $(version))
```

See [registering make functions](docs/FFI.md#registering-make-functions) for the conversion rules per engine.

##### Import as a Target

`import.target` turns a guest program into a target instead of a set of globals.  The define's name becomes a phony target, and its body runs in that engine on the job's own stdin and stdout, every time the target runs.

```Makefile
@lua.import.target
define hello
  print("hello from lua")
endef

@micropy.import.target
define count
  import sys
  print(len(sys.stdin.read().split()))
endef
```

```bash
amk hello
# hello from lua

echo "a b c" | amk count
# 3
```

See [defining a target in an engine](docs/FFI.md#defining-a-target-in-an-engine) for targets that keep their value between goals.

<!-- header bridge-mode "Bridge Mode" | Guest handle docs/FFI.md#the-guest-handle | Functions docs/FFI.md#registering-make-functions | Hooks docs/FFI.md#hooks -->
<p align="right"><a id="bridge-mode"></a><a href="#bridge-mode"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.bridge-mode.title.dark.svg"><img align=left src="docs/img/hdr/readme.bridge-mode.title.svg" alt="Bridge Mode"></picture></a><a href="docs/FFI.md#the-guest-handle"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.bridge-mode.0.dark.svg"><img src="docs/img/hdr/readme.bridge-mode.0.svg" alt="Guest handle"></picture></a><a href="docs/FFI.md#registering-make-functions"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.bridge-mode.1.dark.svg"><img src="docs/img/hdr/readme.bridge-mode.1.svg" alt="Functions"></picture></a><a href="docs/FFI.md#hooks"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.bridge-mode.2.dark.svg"><img src="docs/img/hdr/readme.bridge-mode.2.svg" alt="Hooks"></picture></a><br clear="all"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/_rule.dark.svg"><img width=2000 height=1 src="docs/img/hdr/_rule.svg" alt=""></picture></p>
<!-- /header -->

Since `amk` is an extension of `make` and since Makefile (or the [extended grammar](#extended-grammar)) is the obvious choice for the coordination language, host-to-guest is the obvious choice for the primary direction of *control-flow and orchestration*.

But! This actually isn't required.  In most cases, the bridge is *bidirectional,* allowing guests to call into `amk` as well as the other way around, for example to directly define targets, read variables, or call other guests.

```Makefile
greeting := hello

@js.import
define js_namespace
  function shout(s) { return s.toUpperCase() + "!"; }
endef

# lua reads a make variable, calls a js function through make,
# then defines a target with the result
$(lua amk.eval("hi: ; echo " .. amk.call("shout", amk.var.greeting)))
```

```bash
amk hi
# HELLO!
```

<!-- header misc-examples "Misc Examples" | awk and jq #awk-jq | lua #lua | s7 #s7 | micropy #micropy | js #js | wasm #wasm -->
<p align="right"><a id="misc-examples"></a><a href="#misc-examples"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.misc-examples.title.dark.svg"><img align=left src="docs/img/hdr/readme.misc-examples.title.svg" alt="Misc Examples"></picture></a><a href="#awk-jq"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.misc-examples.0.dark.svg"><img src="docs/img/hdr/readme.misc-examples.0.svg" alt="awk and jq"></picture></a><a href="#lua"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.misc-examples.1.dark.svg"><img src="docs/img/hdr/readme.misc-examples.1.svg" alt="lua"></picture></a><a href="#s7"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.misc-examples.2.dark.svg"><img src="docs/img/hdr/readme.misc-examples.2.svg" alt="s7"></picture></a><a href="#micropy"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.misc-examples.3.dark.svg"><img src="docs/img/hdr/readme.misc-examples.3.svg" alt="micropy"></picture></a><a href="#js"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.misc-examples.4.dark.svg"><img src="docs/img/hdr/readme.misc-examples.4.svg" alt="js"></picture></a><a href="#wasm"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.misc-examples.5.dark.svg"><img src="docs/img/hdr/readme.misc-examples.5.svg" alt="wasm"></picture></a><br clear="all"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/_rule.dark.svg"><img width=2000 height=1 src="docs/img/hdr/_rule.svg" alt=""></picture></p>
<!-- /header -->

<a id="awk-jq"></a>

#### awk and jq

Another simple inline, enjoy floats

```Makefile
percent := $(awk BEGIN { print 100 * 3 / 8 })
```

An example with an argv

```Makefile
longest := $(awk.argv -v RS=[[:space:]]+,length > n { n = length; w = $$0 } END { print w },make awk portable jq)
```

Complex datastructures, fast and no tools required.  Make helpers and you're well on your way to stacks and other fun.

```Makefile
pkg := {"name": "cmk", "version": "1.2.3"}
pkg.version := $(jq.argv -r,.version,$(pkg))
```

Quoting or commas in calls may need a variable in the middle.

```Makefile
opts = -n -r --arg alts 'k/a k/b' --arg none ""
frame := $(jq.argv ${opts},$$alts + "|" + $$none)
```

<a id="lua"></a>
#### lua

Lua 5.4 with its standard libraries, plus the bundled `dkjson` for JSON. The input is
standard input, read with `io.read` or `io.lines`.

```Makefile
# inline, string patterns: 2026
year := $(lua print(("released 2026-10-05"):match("%d%d%d%d")))

# multiline chunk from a define, JSON input from a variable: bob
define lua.top
  local json = require("dkjson")
  local best, top = -1
  for name, n in pairs(json.decode(io.read("a"))) do
    if n > best then best, top = n, name end
  end
  print(top)
endef
scores := {"ada": 3, "bob": 7, "cy": 5}
top := $(lua ${lua.top},$(scores))
```

<a id="s7"></a>
#### s7

The input is the current input port, for `read-line` or `read`. An error reports on
stderr and the call expands to nothing.

```Makefile
# inline: 42
answer.s7 := $(s7 (display (* 6 7)))

# a function defined and used: 20! is 2432902008176640000
define s7.fact
  (define (fact n) (if (= n 0) 1 (* n (fact (- n 1)))))
  (display (fact 20))
endef
big := $(s7 ${s7.fact})
```

<a id="micropy"></a>
#### micropy

MicroPython: Python 3 with `sys`, `os`, `io`, `json`, `re`, `time`, `math`, `random`,
`struct`, `collections`, `hashlib`, `binascii`, `deflate`, `select` and `errno`. The input
is `sys.stdin`. There is no `input`, `asyncio`, threads or `machine`.

```Makefile
# inline, a comma inside ( ): 7
answer.py := $(micropy print(max(3, 7)))

# multiline chunk from a define, dedented by the star form, JSON input from a variable: bob
define py.top
  import json, sys
  d = json.load(sys.stdin)
  print(max(d, key=d.get))
endef
scores := {"ada": 3, "bob": 7, "cy": 5}
top := $(micropy* py.top,scores)
```

<a id="js"></a>
#### js

QuickJS: ES2023 JavaScript with `JSON`, `RegExp`, `BigInt`, `Promise` and the rest of
the language builtins, plus the qjs `std` and `os` modules bound as globals. The input
is `std.in`, read with `getline` or `readAsString`, and `print` writes the result. A
top-level `await` is allowed. There is no `require`, `console` beyond `console.log`,
`fetch` or `setTimeout` past what `os` provides.

```Makefile
# inline: 42
answer.js := $(js print(6 * 7))

# multiline chunk from a define, JSON input from a variable: cmk
define js.newest
  const pkgs = JSON.parse(std.in.readAsString());
  print(pkgs.sort((a, b) => b.year - a.year)[0].name);
endef
pkgs := [{"name": "make", "year": 1976}, {"name": "cmk", "year": 2024}]
newest := $(js ${js.newest},$(pkgs))
```

<a id="wasm"></a>
#### wasm

Off by default; build `with=wasm3`. The first argument is a module path and its
arguments, not program text. What the module's `_start` writes to stdout is the result.

```Makefile
# a WASI module with an argument
module := src/wasm3-0.9.0/test/wasi/simple/test.wasm
echoed := $(findstring Args: test.wasm; hello;,$(wasm ${module} hello))

# an exported function by name; its return value is the result, as a Result: line
$(wasm.argv --func fib,src/wasm3-0.9.0/test/lang/fib32.wasm 20)
```

The wasm3 command line, repl included, is `amk --wasm`:

```bash
# prints "Result: 6765"
./amk --wasm --func fib src/wasm3-0.9.0/test/lang/fib32.wasm 20
```

The repl takes a module from its input rather than a path, as `:load-hex <bytes>` followed
by the module in hex, and then one call per line. A make variable holds the hex, so the
module never has to touch disk; [demos/wasm-1.mk](demos/wasm-1.mk) compiles one in a
container and calls it three times this way.

```Makefile
# the module as hex in a variable, then three calls in one session: 55 6765 832040
hex := $(shell od -An -v -tx1 src/wasm3-0.9.0/test/lang/fib32.wasm)
define session
:load-hex $(words $(hex))
$(hex)
fib 10
fib 20
fib 30

endef
fibs := $(subst Result: ,,$(wasm.argv --repl,,$(session)))
```

### Further Reading

The [FFI docs](docs/FFI.md) cover the rest of the bridge:

| topic | what it gives |
| --- | --- |
| [Persistent state](docs/FFI.md#persistent-state) | one engine state kept for the life of the make process |
| [The jq store](docs/FFI.md#the-jq-store) | named JSON values, updated in the make process with no fork |
| [Calls from a recipe](docs/FFI.md#calls-from-a-recipe) | the jq store from a running recipe's shell |
| [Init](docs/FFI.md#init) | a chunk run in each persistent state before the parse |
| [Hooks](docs/FFI.md#hooks) | goal and recipe events delivered to a guest |
| [The guest handle](docs/FFI.md#the-guest-handle) | variable reads and writes, expansion, and eval from a guest |
| [Registering make functions](docs/FFI.md#registering-make-functions) | guest functions and values as make functions and variables |

<a id="zygote"></a><br/>

## Resident Dispatch

**Background, briefly.** For resident mode, the idea is that a large program should parse *only once*, regardless of how many times it's calling itself recursively.  Obvious right?, and completely standard for a Real Programming Language(tm), but for various reasons this is **not** what a build-system like `make` typically wants or needs.  Since `amk` has optional extra use-cases that may be very far away from just a build-system.. it has optional extra support that works around this whole bottleneck.

**Architecture, briefly.**  A server (the zygote) reads makefiles once and waits on a unix socket.  Each client request runs as an ordinary make in a fresh copy of that parsed state, with the client's working directory, arguments, environment and terminal.  

**Usage.**  Although client / server pieces are *involved* these don't actually need to run separately.  The simplest form is one command (see example below), starting a private zygote on its own arguments, runs the goal through it, and reaps it on exit.  During execution, any recursion via e.g. `$(MAKE)` or `${amk}`, reuses the zygote.

```bash
./amk --resident -f program.mk hello
```

You might already know about the jobserver capabilities for classical `make`.  The zygote is a different kind of animal, but, it **is** related to concurrency as well as recursion.  For exploring that sort of thing, you'll want more direct control over the client/server mode:

```bash
# the zygote
./amk --serve /tmp/amk.sock -f program.mk &

# a request
./amk --client /tmp/amk.sock hello

# another, against the same parse
./amk --client /tmp/amk.sock hello
```

A request that passes an option the zygote was not started with is declined, and the
client runs the cold command given after `--` instead, so a refusal costs a slower run
rather than a wrong answer:

```bash
./amk --client /tmp/amk.sock -- make -f program.mk hello
```

A client whose socket is missing runs cold at once. Two environment variables adjust
that:

- `AMK_ZYGOTE` names the pid of a zygote that is still starting, and the client waits a
  bounded time for its socket instead of running cold.
- `AMK_REARM` lists variables to recompute per request, for values a makefile sets at
  parse time that a shared parse would otherwise freeze.

<a id="functions"></a><br/>

## Functions

Primitive functions amk adds beside the engines. 

| function | answers | feature |
| --- | --- | --- |
| `$(cksum text)`, `$(cksum.file path)` | the checksum and byte length the cksum utility prints, joined by a dash | `cksum` |
| `$(cksum.hex text)`, `$(cksum.file.hex path)` | seven hex digits of that checksum modulo 2^28 | `cksum` |
| `$(cksum* var)`, `$(cksum.hex* var)` | the same over a variable's dedented value | `cksum` |
| `$(amk.sys name)` | `pid`, `ppid`, `uid`, `uname`, `arch`, `hostname`, `epoch` or `uuid` from the kernel; an unknown name is fatal | `sys` |
| `$(amk.match re,text)`, `$(amk.match.file re,path)` | the lines an extended regular expression matches, joined by newlines; a bad pattern is fatal, a missing file is empty with a warning | `match` |
| `$(amk.match* re, var)` | the same with either argument read from a variable | `match` |
| `$(amk.dedent text)`, `$(amk.val.dedent var)`, `$(amk.dedent* var)` | the block indent removed from the text, or from a variable's unexpanded value | always |
| `$(amk.require names...)` | empty, or fatal naming the features this amk lacks | always |
| `$(goal name)` | the goal brought up to date in a fork, and its value | always |
| `$(amk.stdin text)` | the text fed to the recipe line's command on its standard input | always |
 
Each function names its feature in `.FEATURES`, so a makefile can guard on it and keep a shell for a stock make.  See [reflection](#) for more details.

`AMK_PROFILE=<file>` or `-` in the environment times every function, `call` macro and
recursive variable by name and appends the table when the process dies.  See [profiler docs](#) for more details.

<a id="cli"></a><br/>

## Command Line

Several new flags are added by `amk` to defaults for `make`, each read ahead of other option decoding.  Other sections above have more details, but this section is the catalog.  See also  `amkk --help`.

| flag | takes | does |
| --- | --- | --- |
| `--<engine>` | the engine's arguments | runs that engine with the rest of the line: `--awk`, `--jq`, `--lua`, `--s7`, `--micropy`, `--js`, `--wasm` |
| `--list-engines` | | prints one engine per line, the builtin name and then its multi-call names, if any |
| `--serve SOCK` | a socket path, then make's arguments | parses once and answers requests on the socket as the [zygote](#zygote) |
| `--client SOCK` | a socket path, then the request, optionally `-- <cold command>` | runs the request against a zygote, or the cold command when refused |
| `--resident` | make's arguments | one command served by a zygote it starts and reaps itself |
| `--ape-unpack NAME`, `-x NAME`, `--ape-unpack=NAME [DEST]` | a payload member, an optional destination | copies the member out and prints its [path](#payloads) |
| `--force` | | with `--ape-unpack`, overwrites a destination that exists |
| `--ape-list` | | prints every payload member, one per line, sorted, as `--ape-unpack` names them |
| `--bundle FILES... --out DEST` | makefiles and directories, the output path | writes a copy of amk whose default entry is that [program](#bundles) |
| `--profile`, `--profile=FILE` | an optional output file | sets `AMK_PROFILE` to FILE, or to stderr without one, from anywhere on the line |

<a id="dev"></a><br/>

## Developers

[Building](docs/dev.md#building), [Testing](docs/dev.md#testing), [Dependencies](docs/dev.md#dependencies), [Patch Series](docs/dev.md#patches), [Release Process](docs/dev.md#releases), [Tree layout](docs/dev.md#layout), and [Payload Internals](docs/dev.md#payload-internals) are all in the [main developer docs](docs/dev.md).

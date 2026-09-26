<!-- header amk "amk" | Overview #overview | Install #install | Bundling #bundling | Guests #guests | Special Guests #special-guests | Zygote #zygote | CLI #cli | Dev #dev -->
<p align="right"><a id="amk"></a><a href="#amk"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.amk.title.dark.svg"><img align=left src="docs/img/hdr/readme.amk.title.svg" alt="amk"></picture></a><a href="#overview"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.amk.0.dark.svg"><img src="docs/img/hdr/readme.amk.0.svg" alt="Overview"></picture></a><a href="#install"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.amk.1.dark.svg"><img src="docs/img/hdr/readme.amk.1.svg" alt="Install"></picture></a><a href="#bundling"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.amk.2.dark.svg"><img src="docs/img/hdr/readme.amk.2.svg" alt="Bundling"></picture></a><a href="#guests"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.amk.3.dark.svg"><img src="docs/img/hdr/readme.amk.3.svg" alt="Guests"></picture></a><a href="#special-guests"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.amk.4.dark.svg"><img src="docs/img/hdr/readme.amk.4.svg" alt="Special Guests"></picture></a><a href="#zygote"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.amk.5.dark.svg"><img src="docs/img/hdr/readme.amk.5.svg" alt="Zygote"></picture></a><a href="#cli"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.amk.6.dark.svg"><img src="docs/img/hdr/readme.amk.6.svg" alt="CLI"></picture></a><a href="#dev"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.amk.7.dark.svg"><img src="docs/img/hdr/readme.amk.7.svg" alt="Dev"></picture></a><br clear="all"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/_rule.dark.svg"><img width=2000 height=1 src="docs/img/hdr/_rule.svg" alt=""></picture></p>
<!-- /header -->

<p><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/icon-dark.svg"><img align=middle src="docs/img/icon.svg" width="200" alt="amk"></picture>
<strong>amk</strong> is ape-make, an actually portable cosmopolitan <code>make</code>.  It's a drop in replacement forked from make-4.4.1, but with enough brand new superpowers that it's a distinct dialect.</p>


Broadly, `amk` turns what is already your default *coordination language* into a **small-but-powerful polyglot VM**: close to shell when you want that, and a portable, multi-language scripting environment with no need for docker.  Makefile stays an incremental computing toolkit for DAGs and builds, and also becomes a **polyglot data-flow language**, something like a notebook where downstream cells update when their prerequisites change.

Hater who thinks `make` is only a build tool?  Now it's definitely not.  Enthusiast who loves `make`, but sort of wishes it was a Real Language(tm)?  Now it definitely is.

## Just Show Me

Here's a JSON-RPC server where every method lives in a different language and `amk` glues them together.  Transport works via HTTP, using a python guest, serving with microdot *(like flask, but smaller)* from mip *(like pip, but micropython)*.

```Makefile
#!/usr/bin/env -S amk -f

PORT ?= 18090

include /zip/lib/mip.mk

@lua.import
define lua.methods
  function add(a, b) return tonumber(a) + tonumber(b) end
  function sorted(xs)
    local t = {}
    for x in xs:gmatch("%S+") do t[#t + 1] = tonumber(x) end
    table.sort(t)
    return table.concat(t, " ")
  end
endef

@js.import
define js.methods
  function shout(s) { return s.toUpperCase() + "!"; }
  function report(sorted, total) { 
    return JSON.stringify({ 
      sorted: sorted.split(" ").map(Number), 
      total: Number(total) }); }
endef

@s7.import
define s7.methods
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

# Using mip to handle dependencies
define mip.manifest
  {
    "microdot": {
      "version": "v2.7.0",
      "spec": "github:miguelgrinberg/microdot/src/microdot/microdot.py",
      "sha256": "7abf80436064aff030fb123c2947260674c84001517322d7c8517b7f2425e01a"
    }
  }
endef

@micropy.import
define rpc.server
  import amk, json, sys
  from microdot import Microdot
  
  # read-from-host: published methods from top-level registry 
  methods = amk.var["rpc.methods"].split()
  
  def _val(s):
    try: return json.loads(s)
    except ValueError: return s

  def _arg(p):
    return " ".join(map(str, p)) if isinstance(p, list) else str(p)

  def serve(port):
    app = Microdot()
    
    @app.post("/")
    async def rpc(req):
      q = req.json
      reply = dict(jsonrpc="2.0", id=q["id"])
      if q["method"] not in methods:
        reply["error"] = dict(code=-32601, message="Method not found")
        return reply
      params = [_arg(p) for p in q["params"]]
      
      # `amk.acall`: async-call dispatch back into amk.
      reply["result"] = _val(await amk.acall(q["method"], *params))
      return reply

    print("json-rpc on http://127.0.0.1:%s/" % port, file=sys.stderr)
    print("methods: %s" % " ".join(methods), file=sys.stderr)
    app.run(port=int(port))
endef

__main__:
	@echo "json-rpc: a server over the methods $(rpc.methods); run it with: $(MAKE) -f $(firstword $(MAKEFILE_LIST)) serve PORT=$(PORT)"

serve: mip.install
	$(serve $(PORT))
```

Run it with `amk -f demos/json-rpc.mk serve`, then post a request:

```bash
curl -s -X POST -H 'Content-Type: application/json' http://127.0.0.1:18090/ \
  -d '{"jsonrpc":"2.0","id":1,"method":"stats","params":["3 1 2"]}'
# {"jsonrpc": "2.0", "id": 1, "result": {"sorted": [1, 2, 3], "total": 6}}
```

A toy example, but what do you think?  Not so far away from useful FAAS or MCP, eh?

What's going on:

| piece | what it does |
| --- | --- |
| `@lua.import` and friends | the [extended grammar](#extended-grammar): every function in the block becomes a [make function](docs/FFI.md#registering-make-functions), so `$(sorted ...)` is lua and `$(report ...)` is js |
| `stats = ...` | an ordinary make function, composed from functions in two other languages |
| `$(amk.fxns? lua, js, s7)` | lists the functions those engines gave make, so the server publishes them all |
| `include /zip/lib/mip.mk` | a [builtin library](#builtin-libraries): `mip.manifest` pins micropython packages and `mip.install` fetches them |
| `amk.var`, `amk.acall` | the [guest handle](#bridge-mode): python reads a make variable and calls back into make |
| `__main__`, `serve` | the default goal when the command line names none, which here only says how to start the server, and the goal that starts it |

<a id="overview"></a>

## Overview 

The main use-cases:

1. **[Bundling & Distribution](#bundling):**  *Runs anywhere* and *bundles anything*.  Every APE is at once a binary and a zip file, so `amk` works as a *quasi-compiler* for Makefile: ship your sources with a copy of the interpreter as one new executable.  The code doesn't even need to be Makefile; any language `amk` embeds can drive it, or several.  **Shipping monoliths composed of modules is easy.**

1. **[Standard Guests](#guests):**  Besides `make`, the *rest* of the shell toolkit rides along as APEs too.  No worries about which `awk` the host has, or whether it has one.  **Portable shell-scripting environment, no containers.**

1. **[Special Guests](#special-guests):**  A **polyglot VM in miniature!**  Shell stays a first-class citizen, and embedded engines for **[python](#micropy), [lua](#lua), [lisp](#s7), and [wasm](#wasm)** sit behind the coordination language you already know.  **A tiny Graal, but without JDK.**

1. **[Zygote / Resident Mode](#zygote):**  Useful to avoid cold-start penalties in many circumstances.  Side-effect free?  Execution freezes a program, then runs and re-runs against the same base without a re-parse.  Keep most of the "incremental computing" model, get **improved recursion, FP, workflows, dataflows.**

<a id="install"></a>

## Quick Start

Just grab a release, and check it against the checksum beside it.

```bash
url=https://github.com/Robot-Wranglers/ape-make/releases/latest/download
curl -fsSLO $url/amk -O $url/amk.sha256

# on macOS: shasum -a 256 -c amk.sha256
sha256sum -c amk.sha256

chmod +x amk
mkdir -p ~/.local/bin && mv amk ~/.local/bin/
amk --version
```

A first run, with lua doing the arithmetic:

```bash
printf 'hello:\n\techo $(lua print(6 * 7))\n' | amk -f - hello
# 42
```

<a id="ape"></a>

### Gotchas

- **Apple silicon** may need a C compiler on first run: `xcode-select --install` if `cc` is
  missing. This is upstream code-signing, see the
  [cosmo docs](https://github.com/jart/cosmopolitan/blob/master/tool/cosmocc/README.md#gotchas).
- **Keep the exec bit**, even to run it as `sh ./amk`. Without it the first run on macOS fails
  with `gzip: (stdin): unexpected end of file`. A copy that loses its mode, such as a CI
  artifact, needs `chmod +x`.
- **Run it through a shell.** An ape's header is a shell script that installs a small loader
  in `$TMPDIR` on first run, so a bare `execve` fails. `sh`, `make`, and shell wrappers are
  fine; Python `subprocess` needs `sh -c`. The same holds for the [bundled tools](#tools).

### Docker

```bash
docker run --rm -v "$PWD:/work" \
  ghcr.io/robot-wranglers/amk:latest <target>
```

The image runs `amk` in `/work`. Use the `wasm3` tag for the build with the [wasm](#wasm) engine.

<a id="bundling"></a>

## Bundling & Distribution

A bundle is a copy of amk that carries your files in its zip payload and runs them by
default. The result is one executable that runs anywhere amk does.

<a id="bundles"></a>

```bash
# the first file is the entry; a directory adds everything under it
amk --bundle main.mk lib/ --out my.amk

./my.amk deploy                        # runs main.mk, from any directory
./my.amk -f other.mk                   # a bundle is still a full amk
./my.amk --bundle v2.mk --out my2.amk  # new entry, same lib/
```

Inside a bundle, includes resolve against the payload and `$(MAKE)` reaches the same program:

```Makefile
include lib/greet.mk

deploy:
	$(MAKE) build
```

- Run `--bundle` from the directory your includes are relative to; members keep those names.
- A file of the same name in the working directory shadows a payload include.
- Bundling needs nothing but amk: no compiler, no `zip`.

<a id="payloads"></a>

### Payloads

Any file can ride in the payload, and amk gives it two more uses.

**Extract a member** with `--ape-unpack NAME`, or `-x NAME`. It prints the path and skips
the copy when one is already current, so it is cheap to call on every parse:

```Makefile
include $(shell ./my.amk --ape-unpack=lib/greet.mk)
```

**Boot with a script** by bundling a `__main__.sh`. It replaces the make run: amk hands it
to the host's bash with the binary's path as `$0` and the caller's arguments after it.
Export `AMK_BOOTED=1` before calling `"$0"`, so the inner run is a plain make:

```bash
# __main__.sh
export AMK_BOOTED=1
echo "booting" >&2
exec "$0" "$@"
```

```bash
amk --bundle main.mk __main__.sh --out my.amk
./my.amk deploy
```

A host without bash skips the script and runs the bundle as a plain make.

<a id="guests"></a>

## Standard Guests

Standard guests are **bundled tools** and a few **libraries** that ride along in the payload.

They answer the problem that certain platforms (looking at you MacOS, but also minimal containers) ship the usual suspects missing, non-GNU, or pinned to incredibly ancient versions.  Hmm, but that's another problem solvable with some combination of APEs and bundling.. So, `amk` ships them.

<a id="tools"></a>

### Bundled Tools

| tool | version | from | run as |
| --- | --- | --- | --- |
| sed | GNU sed 4.9 (cosmos 4.0.2) | [cosmo.zip](https://cosmo.zip/pub/cosmos/v/4.0.2/bin/) | `sed` on `PATH` |
| bash | 5.2.0 (cosmos 4.0.2) | [cosmo.zip](https://cosmo.zip/pub/cosmos/v/4.0.2/bin/) | `bash` on `PATH` |
| jb | json.bash 0.3.0 | [github.com/h4l](https://github.com/h4l/json.bash/tree/v0.3.0) | `jb`, `jb-array` on `PATH`, `source json.bash` |

Bundled tools are on `PATH` for any recipe, on any host, ahead of the system path, so reference by name just works.  For example.. a modern bash on MacOS, and a working bash even in a container where it doesn't ship.  They unpack once per binary to `~/.cache/amk/`, and `make build without=jb` leaves json.bash out.

```Makefile
SHELL:=bash 
check:
	echo "$${BASH_VERSINFO[0]}"
```

`awk` and `jq` are on `PATH` too, but they are better than bundled: they are *linked* [special guests](#special-guests).  `$(jq ..)` runs libjq inside make with no fork, so JSON becomes a native "type" and your portable Makefile suddenly has datastructures and a query language.  As tools, they run as `amk --awk` or `amk --jq`, or as amk under the name `awk` or `jq`.

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

| engine | version | from | gives | adds | default |
| --- | --- | --- | --- | --- | --- |
| [gawk](#awk-jq) | 5.3.1 | [ftp.gnu.org](https://ftp.gnu.org/gnu/gawk/) | `$(awk)`, `$(awk.argv)` | 1.3 MB | on |
| [jq](#awk-jq) | 1.7.1 | [github.com/jqlang](https://github.com/jqlang/jq/releases/tag/jq-1.7.1) | `$(jq)`, `$(jq.argv)` | 1.9 MB | on |
| [lua](#lua) | 5.4.8 | [lua.org](https://www.lua.org/ftp/) | `$(lua)` | 0.5 MB | on |
| [s7](#s7) | 11.9 | [ccrma.stanford.edu](https://ccrma.stanford.edu/software/s7/) | `$(s7)` | 4.1 MB | on |
| [micropython](#micropy) | 1.29.0 | [github.com/micropython](https://github.com/micropython/micropython/releases/tag/v1.29.0) | `$(micropy)` | 0.8 MB | on |
| [quickjs](#js) | 2026-06-04 | [bellard.org](https://bellard.org/quickjs/) | `$(js)` | 2.0 MB | on |
| [wasm3](#wasm) | 0.9.0 | [github.com/wasm3](https://github.com/wasm3/wasm3/tree/v0.9.0) | `$(wasm)`, `$(wasm.argv)` | 0.4 MB | off |

Individual guests and guest-access modes aren't mutually exclusive, but a mode-split is helpful to organize the docs around:

1. [Tool Mode](#tool-mode): A CLI interface you can script against directly.
1. [Eval Mode](#eval-mode): Stateless compute in guest.  Usually lifting vals into host
1. [Exec Mode](#exec-mode):  Stateful engine / persistent guests
1. [Import Mode](#import-mode): Lift whole namespaces (functions + variables)
1. [Bridge Mode](#bridge-mode): Guest-to-host actions or reads; Guest-to-guest calls

This section is an overview of each mode with examples, but it's a quick guide, and not a full reference.  The [Engine API](#engine-api) after the modes sums up every form, and the [full FFI documentation](docs/FFI.md) has the gory details.

### Tool Mode

As a degenerate kind of [eval mode](#eval-mode), tool mode maybe isn't that interesting, but we introduce it for completeness.  

```bash
# Flag first, then the rest goes to the tool
./amk --awk 'BEGIN { print "hello" }'

# Same for jq, lua, python, etc
printf '{"n":41}' | ./amk --jq .n+1

# Names matter!
# So a symlink named for the tool works the way you'd expect.
ln -s amk awk && ./awk 'BEGIN { print "hello" }'
```

From inside a Makefile, every other mode is better than tool-mode, since a tool is a fork you can avoid by using an engine.  But if you insist:

```Makefile
#! /usr/bin/env amk -f

# bundled jq and awk are on PATH already, just use them.
my_target:; jq ...

# equivalently, and introducing the way amk calls itself.
my_other_target:; ${amk} --jq ...
```

### Eval Mode

Eval-mode is usually a way to "lift" computed values from guests into the host.  

The typical use-case is working around the impoverished Makefile primitives, getting real numbers, regex, or string operations done easily.  For example:

```Makefile
answer.lua := $(lua print(6 * 7))
```

Works fine with simple stuff, and not so simple.  Besides values, you could also code-gen targets, avoiding the eval/foreach type of pure-Makefile loops.  

Despite the "eval" name.. nothing prevents importing modules in the guest, etc.  But since line-feeds and escaping gets annoying quickly, using multiline data and multiline programs is common.

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

# a second state, reached through its handle
$(lua.ns work, create)
$(work.exec total = 1)
# 1 42
both := $(work.exec print(total)) $(lua.exec print(total))
```

### Import Mode

Import runs a chunk in the engine's persistent state and lifts every global it defines into make: a function becomes a make function, any other value a variable, and a table one variable per key.  The [decorator](#extended-grammar) form is the usual way to write it:

```Makefile
@lua.import
define lua.lib
  version = "1.2.3"
  pkg = { name = "cmk" }
  function bump(v) return (v:gsub("%d+$", function(n) return n + 1 end)) end
endef

# cmk 1.2.4
next := $(pkg.name) $(bump $(version))
```

See [registering make functions](docs/FFI.md#registering-make-functions) for the conversion rules per engine.

<!-- header bridge-mode "Bridge Mode" | Guest handle docs/FFI.md#the-guest-handle | Functions docs/FFI.md#registering-make-functions | Hooks docs/FFI.md#hooks -->
<p align="right"><a id="bridge-mode"></a><a href="#bridge-mode"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.bridge-mode.title.dark.svg"><img align=left src="docs/img/hdr/readme.bridge-mode.title.svg" alt="Bridge Mode"></picture></a><a href="docs/FFI.md#the-guest-handle"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.bridge-mode.0.dark.svg"><img src="docs/img/hdr/readme.bridge-mode.0.svg" alt="Guest handle"></picture></a><a href="docs/FFI.md#registering-make-functions"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.bridge-mode.1.dark.svg"><img src="docs/img/hdr/readme.bridge-mode.1.svg" alt="Functions"></picture></a><a href="docs/FFI.md#hooks"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.bridge-mode.2.dark.svg"><img src="docs/img/hdr/readme.bridge-mode.2.svg" alt="Hooks"></picture></a><br clear="all"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/_rule.dark.svg"><img width=2000 height=1 src="docs/img/hdr/_rule.svg" alt=""></picture></p>
<!-- /header -->

Since `amk` is an extension of `make` and since Makefile (or the [extended grammar](#extended-grammar)) is the obvious choice for the coordination language, host-to-guest is the obvious choice for the primary direction of *control-flow and orchestration*.

But! This actually isn't required.  In most cases, the bridge is *bidirectional,* allowing guests to call into `amk` as well as the other way around, for example to directly define targets, read variables, or call other guests.

```Makefile
greeting := hello

@js.import
define js.methods
  function shout(s) { return s.toUpperCase() + "!"; }
endef

# lua reads a make variable, calls a js function through make, and defines a target with the result
$(lua amk.eval("hi: ; echo " .. amk.call("shout", amk.var.greeting)))
```

```bash
amk hi
# HELLO!
```

<!-- header engine-api "Engine API" | Literals #engine-literals | Reference #engine-reference | Grammar #extended-grammar -->
<p align="right"><a id="engine-api"></a><a href="#engine-api"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.engine-api.title.dark.svg"><img align=left src="docs/img/hdr/readme.engine-api.title.svg" alt="Engine API"></picture></a><a href="#engine-literals"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.engine-api.0.dark.svg"><img src="docs/img/hdr/readme.engine-api.0.svg" alt="Literals"></picture></a><a href="#engine-reference"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.engine-api.1.dark.svg"><img src="docs/img/hdr/readme.engine-api.1.svg" alt="Reference"></picture></a><a href="#extended-grammar"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/readme.engine-api.2.dark.svg"><img src="docs/img/hdr/readme.engine-api.2.svg" alt="Grammar"></picture></a><br clear="all"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/hdr/_rule.dark.svg"><img width=2000 height=1 src="docs/img/hdr/_rule.svg" alt=""></picture></p>
<!-- /header -->

Each guest backend has a more or less unified interface, so there's not a demo in every language for every mode.  Just switch out the engine name (i.e. `eng` below) for whatever you're interested in (e.g. `micropy`, `lua`, `s7`, `js`, etc).  That said.. backend implementation details can differ, and so details for FFI support can also differ.  In particular `wasm` and `jq` are misfits: `wasm` takes a [module](#wasm) rather than program text, and `jq` keeps its state in a [store](docs/FFI.md#the-jq-store).  The [capabilities table](docs/FFI.md#capabilities-by-engine) has the per-engine breakdown.

#### Engine Literals

Passing literals is the most basic thing you can do for each engine mode.

```Makefile
# Eval-mode
$(eng program, [input])
$(eng.argv argv, program, [input])

# Exec-mode: an operation in the namespace main, one argument, so the program keeps its commas
$(eng.exec program)
$(eng.ns name, create)
$(eng.ns name, exec, program)
$(name.exec program)

# Import-mode 
$(eng.import program)
$(eng.import.target program)
```

See [Misc Examples](#misc-examples) for concrete examples.

<a name=star-mode></a>
<a id="engine-reference"></a>

#### Engine By-Reference

Star-mode version of the API.  The trouble with literals is that it breaks down for multi-lines, escaping or quoting hazards etc.  In that case you'll want star-mode calls, where we try to dereference variables to grab values and *fall back* to literal mode only if no variables are available.

```Makefile
# Eval-mode
$(eng* program_var, [input_var])
$(eng.argv* argv, program_var, [input_var])

# Exec-mode: only the program is dereferenced; the name and the op pass as written
$(eng.exec* program_var)
$(eng.ns* name, exec, program_var)
$(name.exec* program_var)

# Import-mode 
$(eng.import* program_var)
$(eng.import.target* program_var)
```

See [star forms](docs/FFI.md#star-forms) for concrete examples.

#### Extended Grammar

Optional extensions to Makefile's default grammar are minimal, but extremely useful. 

The usual thing for [star-mode](#star-mode) is pass-by-reference to put guest code in a `define..endef` block then using an API call on that same block.  Much more readable to flip it, and use a decorator-style idiom:

```Makefile 
@my_engine.import
define my_prog
  ..guest program, optionally indented..
endef
```

No special extra semantics, which is why it's optional.. exactly/only syntactic sugar.

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

# multiline chunk from a define, JSON input from a variable: bob
define py.top
import json, sys
d = json.load(sys.stdin)
print(max(d, key=d.get))
endef
scores := {"ada": 3, "bob": 7, "cy": 5}
top := $(micropy ${py.top},$(scores))
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

<a id="zygote"></a>

## Resident Dispatch

A server, the zygote, reads the makefiles once and waits on a unix socket. Each client
request runs as an ordinary make in a fresh copy of that parsed state, with the client's
working directory, arguments, environment and terminal, so a large program pays its parse
cost once rather than on every run.

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

<a id="load"></a>

## The Load Directive

[`load`](https://www.gnu.org/software/make/manual/html_node/load-Directive.html) is the
one place `amk` departs from stock make. An ape cannot `dlopen`, so nothing is ever
loadable, and `load` reports the platform does not support it. The `-load` form, which
stock make treats as a request to
[rebuild the object and try again](https://www.gnu.org/software/make/manual/html_node/Remaking-Loaded-Objects.html),
instead answers that the object will never be rebuilt, so a makefile that guards a
loadable with `-load` continues without it rather than looping.

<a id="cli"></a>

## Command Line

Every flag amk adds to make's own, each read ahead of option decoding. The sections above
describe them; this is the one list, and `--help` ends with the same one. The smoke test
holds the two together: a flag in this table that `--help` does not name fails the build.

| flag | takes | does |
| --- | --- | --- |
| `--<engine>` | the engine's arguments | runs that engine with the rest of the line: `--awk`, `--jq`, `--lua`, `--s7`, `--micropy`, `--js`, `--wasm` |
| `--list-engines` | | prints one engine per line, the builtin name and then its multi-call names, if any |
| `--serve SOCK` | a socket path, then make's arguments | parses once and answers requests on the socket as the [zygote](#zygote) |
| `--client SOCK` | a socket path, then the request, optionally `-- <cold command>` | runs the request against a zygote, or the cold command when refused |
| `--resident` | make's arguments | one command served by a zygote it starts and reaps itself |
| `--ape-unpack NAME`, `-x NAME`, `--ape-unpack=NAME [DEST]` | a payload member, an optional destination | copies the member out and prints its [path](#payloads) |
| `--force` | | with `--ape-unpack`, overwrites a destination that exists |
| `--bundle FILES... --out DEST` | makefiles and directories, the output path | writes a copy of amk whose default entry is that [program](#bundles) |

<a id="dev"></a>
## Developers

[Building](docs/dev.md#building), [testing](docs/dev.md#testing), pinned
[dependencies](docs/dev.md#dependencies), the [patch series](docs/dev.md#patches),
[releases](docs/dev.md#releases), the build tree's [layout](docs/dev.md#layout), and
[payload internals](docs/dev.md#payload-internals) are in the [developer docs](docs/dev.md).

<table width="100%">
  <tr>
    <td id="title"><strong>amk</strong></td>
    <td id="mini-toc" align=right><a href="#overview">Overview</a> | <a href="#install">Install</a> | <a href="#bundling">Bundling</a> | <a href="#guests">Guests</a> | <a href="#special-guests">Special Guests</a> | <a href="#zygote">Zygote</a> | <a href="#payloads">Payloads</a> | <a href="#dev">Dev</a></td>
  </tr>
  <tr>
    <td id="logo"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/icon-dark.svg"><img src="docs/img/icon.svg" width="200" alt="amk"></picture></td>
    <td id="blurb">
    <strong>amk</strong> is ape-make, an actually portable cosmopolitan <code>make</code>.  It's a drop in replacement forked from make-4.4.1, but with enough brand new superpowers that it's a distinct dialect.
    </td>
  </tr>
</table>

Broadly, `amk` transforms what is already your default choice for a *coordination language* into a **small-but-powerful polyglot VM**.  Huh?  Ok.. `amk` stays close to shell if you need that, but is also effectively a portable, multi-language scripting environment without any need for docker. Besides embedding support for [python](#micropy), [lua](#lua), [lisp](#s7), and [wasm](#wasm)**.. it also provides other support for bidirectional FFI, can handle modules, package external tools, and output a bundle as a portable artifact.

One consequence of this is that Makefile *(and a small, optional extension of the baseline grammar)* remains an incremental computing toolkit suitable for DAGs and builds, but also turns into a more powerful **polyglot data-flow language**.  Huh?  Ok.. Think of it as something like a notebook where downstream cells can update when their prerequisites change.

Hater who thinks `make` is only a build tool?  Now it's definitely not.  Enthusiast who loves `make`, but sort of wishes it was a Real Language(tm)?  Now it definitely is.

<a id="overview"></a>

## Overview 

The main use-cases:

1. **[Bundling & Distribution](#bundling):**  Solves for *bundles anything* as well as *runs anywhere*.  Did you know that all APEs are at once bins and zip files?  Besides being platform-agnostic `amk` leverages this into a working *quasi-compiler* for Makefile, i.e. producing new executables by shipping source file(s) with a copy of the interpreter.  Code involved *does not* actually need to be Makefile either.. a layered approach to bootstrap permits any language that `amk` embeds to work, or, several can be involved.  Shipping monoliths composed of modules is easy.

1. **[Standard Guests](#guests)** are the other part of (1), meaning that besides `make`, the *rest* of the toolchain can also be APE'd riders.  Could be anything, but the usual thing is the shell toolkit.  No worries if `make` is available **or** which `awk` is available, or if either is available.  Portable shell-scripting environment, no containers.

1. **[Special Guests](#special-guests):** Basically a **polyglot VM in miniature!**  Shell remains a fist-class citizen, but `amk` also exposes embedded engines for things like **[python](#micropy), [lua](#lua), [lisp](#s7), and [wasm](#wasm),** with a familiar coordination language already in place to switch between them.  A tiny Graal, but without JDK.

1. **[Zygote / Resident Mode](#zygote):**  Useful to avoid cold-start penalties in many circumstances.  Side-effect free?  Execution freezes a program, then runs and re-runs against the same base without a re-parse.  Keep most of the "incremental computing" model, get improved recursion, FP, workflows, dataflows.

<a id="install"></a>

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

# linux 
sha256sum -c amk.sha256   

# on macOS: 
shasum -a 256 -c amk.sha256
```

### Docker

```bash
docker run --rm -v "$PWD:/work" \
  ghcr.io/robot-wranglers/amk:latest <target>
```

The image runs `amk` in `/work`. Use the `wasm3` tag for the build with the [wasm](#wasm) engine.

<a id="bundling"></a>

## Bundling & Distribution

The typical use-case for bundling is creating a new standalone executable (pseudo-compilation). 

This works by cloning the `amk` runtime, bundling extras, and setting the new entrypoint:

```bash
# make the bundle
amk --bundle my.Makefile my.lib/ --out my.tool

# run it anywhere
./my.tool
```

Makefile-as-script was historically a bad idea, the kind of (ab)use that inviting a lot of *"It's a build tool, not a scripting language!"* objections.  Why not both?  Worth revisiting, for a few reasons.  Vanilla Makefile was already a superset of bash that encourages more structured programming.  After *runs-anywhere* and *bundle-anything* is solved, monolithic scripts can become libraries, and problems with working-directory assumptions just kind of disappear.

<a id="guests"></a>
## Standard Guests

Standard guests are the default riders which are mostly **bundled tools**, but there's also a few libraries that are useful enough to get a place.

The previously show-stopping problem was certain platforms (looking at you MacOS, but also minimal containers) may default to having *other* utilities missing by default, or non-GNU, or pinned to incredibly ancient versions.  Besides `make`, that'd be.. *bash / awk / sed / jq*.  Hmm, but that's another problem solvable with some combination of APEs and bundling.. So, `amk` ships with exactly those tools, and a few more.

| tool | version | from | run as |
| --- | --- | --- | --- |
| [sed](#tools) | GNU sed 4.9 (cosmos 4.0.2) | [cosmo.zip](https://cosmo.zip/pub/cosmos/v/4.0.2/bin/) | `sed` on `PATH` |
| awk | gawk 5.3.1 | [ftp.gnu.org](https://ftp.gnu.org/gnu/gawk/) | `amk --awk`, or amk under the name `awk` |
| [bash](#tools) | 5.2.0 (cosmos 4.0.2) | [cosmo.zip](https://cosmo.zip/pub/cosmos/v/4.0.2/bin/) | `bash` on `PATH` |
| jq | 1.7.1 | [github.com/jqlang](https://github.com/jqlang/jq/releases/tag/jq-1.7.1) | `amk --jq`, or amk under the name `jq` |
| [jb](#tools) | json.bash 0.3.0 | [github.com/h4l](https://github.com/h4l/json.bash/tree/v0.3.0) | `jb`, `jb-array` on `PATH`, `source json.bash` |
| gmsl | 1.2.4 | [github.com/jgrahamc](https://github.com/jgrahamc/gmsl/tree/v1.2.4) | `include /zip/lib/gmsl` |
| dkjson | 2.8 | [dkolf.de](http://dkolf.de/dkjson-lua/) | `require("dkjson")` inside `$(lua)` |

Bundled tools are available by default on PATH for any recipe, for any host, before the system path.  Reference by name just works, getting a modern bash on MacOS, working bash even in a container where it doesn't ship.

```Makefile
SHELL:=bash 
check:
	echo "$${BASH_VERSINFO[0]}"
```

In several cases the standard guests are also *special guests*.  Thus not just bundled, but where applicable also *linked* so that e.g. jq is available via libjq, and via `$(jq ..)` from Makefiles, with no penalty for forking a subprocess.  Great!, now JSON is a native "type" and your portable, compiled Makefile looks to have suddenly grown sophisticated datastructures, and a query-language, with no speed penalty.  See the next section for more details.

### Builtin Libraries

GMSL, the GNU Make Standard Library, adds datastructures and other primitives.  Any bundle can write `include lib/gmsl` and use it from anywhere to enjoy *sets, associative arrays, stacks, and integer and strings* written efficiently in make.

There's a laundry-list of other curated stuff, but just a few examples to give a feel for the type of out-of-the-box thing we're looking to support.  

* [Embedded lua](#lua) needs [dkjson](http://dkolf.de/dkjson-lua/) to work with JSON
* [micropython](#micropy) needs MIP to be able to handle packages.

<a id="special-guests"></a>

<table width="100%">
  <tr>
    <td><h3>Special Guests</h3></td>
    <td align=right><a href="#engine-api">Engine API</a> | <a href="#tool-mode">Tool</a> | <a href="#eval-mode">Eval</a> | <a href="#interpreter-mode">Interpreter</a> | <a href="#bridge-mode">Bridge</a> | <a href="#misc-examples">Examples</a></td>
  </tr>
</table>

Special guests have a "tool mode" in common with standard guests, but are also *embedded engines*, i.e. linked into `amk` directly.  

| engine | version | from | gives | adds | default |
| --- | --- | --- | --- | --- | --- |
| [gawk](#awk-jq) | 5.3.1 | [ftp.gnu.org](https://ftp.gnu.org/gnu/gawk/) | `$(awk)`, `$(awk.argv)` | 1.3 MB | on |
| [jq](#awk-jq) | 1.7.1 | [github.com/jqlang](https://github.com/jqlang/jq/releases/tag/jq-1.7.1) | `$(jq)`, `$(jq.argv)` | 1.9 MB | on |
| [lua](#lua) | 5.4.8 | [lua.org](https://www.lua.org/ftp/) | `$(lua)` | 0.5 MB | on |
| [s7](#s7) | 11.9 | [ccrma.stanford.edu](https://ccrma.stanford.edu/software/s7/) | `$(s7)` | 4.1 MB | on |
| [micropython](#micropy) | 1.29.0 | [github.com/micropython](https://github.com/micropython/micropython/releases/tag/v1.29.0) | `$(micropy)` | 0.8 MB | on |
| [quickjs](#js) | 2026-06-04 | [bellard.org](https://bellard.org/quickjs/) | `$(js)` | 2.0 MB | on |
| [wasm3](#wasm) | 0.9.0 | [github.com/wasm3](https://github.com/wasm3/wasm3/tree/v0.9.0) | `$(wasm)`, `$(wasm.argv)`, `amk --wasm` | 0.4 MB | off |

Individual guests and guest-access modes aren't mutually exclusive, but a mode-split is helpful to organize the docs around:

1. [Tool Mode](#tool-mode): A CLI tool you can script against
1. [Eval Mode](#eval-mode): A make-function, for callable one-shots
1. [Interpreter Mode](#interpreter-mode):  Engine with persistent state
1. [Import Mode](docs/FFI.md#registering-make-functions): Import guest *namespaces* into make (functions + variables)
1. [Bridge Mode](#bridge-mode): Flip it: Guest-to-host action or read; Guest-to-guest calls

This section is an overview of each mode with examples, but it's a quick guide, and not a full reference.  See the [full FFI documentation](docs/FFI.md) for the gory details.

<a id="engine-api"></a>

<table width="100%">
  <tr>
    <td><h3>Engine API</h3></td>
    <td align=right><a href="#engine-literals">Literals</a> | <a href="#engine-reference">Reference</a> | <a href="#extended-grammar">Grammar</a></td>
  </tr>
</table>

Each guest backend has a more or less unified interface.  Not every language gets a demo for every mode, but you can switch out the engine name (i.e. `eng` below) for whatever you're interested in (e.g. `micropy`, `js`, `lua`, `jq`).  That said.. `wasm` in particular must work differently, and the exact details for the FFI support may differ somewhat by engine.

#### Engine Literals

Passing literals is the most basic thing you can do for each mode.

```Makefile
# Eval-mode
$(eng program, [input])
$(eng.argv argv, program, [input])

# Interpreter-mode
$(eng.persistent program, [input])

# Import-mode 
$(eng.import program)
$(eng.import.target program)
```

See [Misc Examples](#misc-examples) for concrete examples.

#### Engine Reference

Star-mode version of the API.  The trouble with literals is that it breaks down for multi-lines, escaping or quoting hazards etc.  In that case you'll want star-mode calls, where we try to dereference variables to grab values and *fall back* to literal mode only if no variables are available.

```Makefile
# Eval-mode
$(eng* program_var, [input_var])
$(eng.argv* argv, program_var, [input_var])

# Interpreter-mode
$(eng.persistent* program_var, [input_var])

# Import-mode 
$(eng.import* program_var)
$(eng.import.target* program_var)
```

See [star forms](docs/FFI.md#star-forms) for concrete examples.

#### Extended Grammar

The extensions to Makefile's default grammar are minimal, but useful. 

The typical way to use star-mode is:

1. Put guest code in a `define..endef` block.
1. Use an API call on the block.

Flipping this with a decorator-style preamble is useful:

```Makefile 
@my_engine.import
define my_prog
  ..guest program, optionally indented..
endef
```

See [defining a target in an engine](docs/FFI.md#defining-a-target-in-an-engine) for concrete examples.

### Tool Mode

Least interesting but quickest and simplest mode.. engines are available directly via the `amk` CLI.

```bash
# Flag first, then the rest goes to the tool
./amk --awk 'BEGIN { print "hello" }'

# Same for jq, lua, python, etc
printf '{"n":41}' | ./amk --jq .n+1

# Names matter!
# So a symlink named for the tool works the way you'd expect.
ln -s amk awk && ./awk 'BEGIN { print "hello" }'
```

### Eval Mode

Eval-mode is a way to "lift" computed values from guests into the host.  

The typical use-case is working around the impoverished Makefile primitives, getting real numbers, regex, or string operations done easily.  For example:

```Makefile
answer.lua := $(lua print(6 * 7))
```

That approach works fine with simple stuff, and not so simple.  Besides values, you could also code-gen targets, avoiding the eval/foreach type of pure-Makefile loops.  

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

<a id="interpreter-mode"></a>

<table width="100%">
  <tr>
    <td><h3>Interpreter Mode</h3></td>
    <td align=right><a href="#lua">lua</a> | <a href="docs/FFI.md#persistent-state">Persistent state</a> | <a href="docs/FFI.md#init">Init</a></td>
  </tr>
</table>

Interpreter-mode gives you a persistent stateful engine on the backend instead of a one-shot eval.  Here's the API:

A quick example:

```Makefile
$(lua.persistent total = 40)
$(lua.persistent total = total + 2)

# 42
answer := $(lua.persistent print(total))
```

Past simple usage, the naive approach above can into problems with multiline inputs, commas, and dollar-signs that Makefile doesn't want to parse correctly.  There's two ways to solve this:


Since guests are linked anyway, why not make them available directly too?  So, you can reach them from the `amk` CLI like so:

```bash
# List engines
./amk --list-engines

# Every engine answers its own flag
./amk --lua 'print(6 * 7)'
./amk --s7 '(display (* 6 7))'
./amk --micropy 'print(6 * 7)'
./amk --js 'print(6 * 7)'
```

Again, see the main [FFI docs](docs/FFI.md) for details, but included below you can see small examples per engine.

<a id="lua"></a>
#### lua


<a id="bridge-mode"></a>

<table width="100%">
  <tr>
    <td><h3>Bridge Mode</h3></td>
    <td align=right><a href="docs/FFI.md#the-guest-handle">Guest handle</a> | <a href="docs/FFI.md#registering-make-functions">Functions</a> | <a href="docs/FFI.md#hooks">Hooks</a></td>
  </tr>
</table>

Since `amk` is an extension of `make` and Makefile (or the [extended grammar](#extended-grammar)) is the obvious choice for the coordination language, host-to-guest is the obvious choice for the primary direction of *control-flow and orchestration*.

But! This actually isn't required.  In most cases, the bridge is *bidirectional,* allowing guests to call into `amk` as well as the other way around, for example to directly define targets, read variables, or call other guests.


<a id="misc-examples"></a>

<table width="100%">
  <tr>
    <td><h3>Misc Examples</h3></td>
    <td align=right><a href="#awk-jq">awk and jq</a> | <a href="#s7">s7</a> | <a href="#micropy">micropy</a> | <a href="#js">js</a> | <a href="#wasm">wasm</a></td>
  </tr>
</table>

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

#### Beyond one-shot calls

Each call above forks a fresh engine. The [FFI docs](docs/FFI.md) cover the rest of the bridge:

| topic | what it gives |
| --- | --- |
| [Persistent state](docs/FFI.md#persistent-state) | one engine state kept for the life of the make process |
| [The jq store](docs/FFI.md#the-jq-store) | named JSON values, updated in the make process with no fork |
| [Calls from a recipe](docs/FFI.md#calls-from-a-recipe) | the jq store from a running recipe's shell |
| [Init](docs/FFI.md#init) | a chunk run in each persistent state before the parse |
| [Hooks](docs/FFI.md#hooks) | goal and recipe events delivered to a guest |
| [The guest handle](docs/FFI.md#the-guest-handle) | variable reads and writes, expansion, and eval from a guest |
| [Registering make functions](docs/FFI.md#registering-make-functions) | guest functions and values as make functions and variables |

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

<a id="payloads"></a>
## Payloads

An ape is also a zip file. amk reads three things from its payload: a boot script, files
to unpack, and tools for `PATH`. [Bundles](#bundles) write one.

**Boot.** A `__main__.sh` in the payload runs on start, under the host's bash:

```bash
# $0 is the binary's absolute path, and the caller's arguments follow
echo 'echo "booted $0 with $*"' > __main__.sh
cp amk my.ape && zip -q my.ape __main__.sh && mv my.ape my.amk
./my.amk hello
```

A recursive make does not boot again, an empty script does not boot, and a host without
bash runs a plain make.

**Unpack.** `--ape-unpack`, or `-x`, copies one payload member out and prints the path:

```bash
# writes ./compose.mk
./amk --ape-unpack compose.mk

# writes vendor/c.mk, creating vendor/
./amk --ape-unpack=compose.mk vendor/c.mk

# rewrites a copy that is newer than the binary
./amk --ape-unpack compose.mk --force
```

```Makefile
# a current copy is left alone, so this is cheap on every parse
include $(shell cmk --ape-unpack=compose.mk)
```

<a id="tools"></a>

### Tools

GNU sed, bash 5.2, and json.bash are unpacked to a cache under `${XDG_CACHE_HOME:-$HOME/.cache}/amk/`,
keyed by the binary, and put first on `PATH` before any makefile is read:

```Makefile
__main__:
	# prints ~/.cache/amk/<key>/bin/sed
	command -v sed
	
  # prints sed (GNU sed) 4.9
	sed --version | head -1
	
  # prints 5.2.0(1)-release
	echo $$BASH_VERSION
	
  # prints {"msg":"hi","n":41}
	jb msg=hi n:number=41
	
  # prints ["a",1]
	jb-array a :number=1
```

A tool is an ape, so the [execve rule](#ape) applies: Python `subprocess`
starting `sed` without a shell fails on macOS.

jb is [json.bash](https://github.com/h4l/json.bash), a bash script that runs under the
payload bash. It lands as `jb`, `jb-array`, and `json.bash`, so a recipe can also
`source json.bash` and call its `json` function without a fork. Build `without=jb` to
leave it out.

<a id="bundles"></a>
### Bundles

```bash
# the first file is the entry; a directory adds every file under it
./amk --bundle main.mk lib/ --out my.amk

# from any directory, runs as amk -f /zip/__main__.mk -I /zip
./my.amk deploy

# the caller's own makefile wins, and the copy is a plain amk
./my.amk -f other.mk

# bundling a bundle replaces the entry and keeps lib/
./my.amk --bundle v2.mk --out my2.amk
```

```Makefile
# inside main.mk: found in the payload, recursion reaches the same program
include lib/greet.mk

deploy:
	$(MAKE) build
```

- Members keep the names they were given, so run `--bundle` from the directory the
  includes are relative to. A leading `./` is dropped; absolute and `..` names are refused.
- A directory skips names that start with a dot and does not follow symlinked
  directories.
- A file of the same name in the caller's working directory shadows a payload include.
- Keep `--out` outside a directory being bundled.
- Bundling needs only amk: no compiler, no `zip`, and no shell at run time. A payload that
  also holds `__main__.sh` [boots](#payloads) first.

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

<a id="ape"></a>
## Running an APE

A shell runs an ape where a bare `execve` cannot: the file's header is a shell script
that installs a small loader in `$TMPDIR` on first run. `sh`, `make`, and any shell-based
wrapper all go through one. Python `subprocess` does not; wrap the call in `sh -c`.

The file must keep its exec bit even when run as `sh ./amk`: the header finds itself with
`command -v`, which on macOS skips a file that is not executable, and the first run then fails
with `gzip: (stdin): unexpected end of file`. Anything that copies it without its mode, such as
a CI artifact, needs a `chmod +x` first.

<a id="dev"></a>
## Developers

### Building

Simple builds:

```bash
# overview 
make help

# creates ./amk with the default engines
make           
```

Opting in and out:

```bash
# the default engines plus $(wasm)
make amk with=wasm3

# no $(s7), and no s7 download
make amk without=s7

# neither scripting engine
make amk without='s7 lua'
```

`with` adds an engine that is off by default, `without` leaves any engine out, and
`without` wins where the two name the same one. A name that is not an engine stops the
build, and leaving out every engine stops it too. An engine left out is absent, not
stubbed: its builtin does not exist, its name is not in `.FEATURES`, its multi-call alias
is not created, and `make deps` does not download it. The engines, what each gives, and
its size are in the table under [Special guests](#special-guests). Of the default build's
14.1 MB, the two payload tools are about 5 MB. An engine's size is that build against the
same build without it, or with it for one that is off.

Development flow:

```bash
# fetch every pinned input not already here, verify all of them
make deps

# unpack make into src/ and apply patches/ in order
make patch

# out/bin/amk, the fat ape with the selected engines linked in
make build

# the builtins, the commands, the payload tools, a zygote, and a bundle
make smoke

# what is built here, and which of it is an artifact
make stat

# ./amk into ~/.local/bin, or into /usr/local/bin with install.global; bindir.user= and bindir.global= override
make install
```

Additionally `make build.native` builds the same sources with the host compiler, make at `-O0 -g`,
as `out/bin-native/amk`; `make smoke.native` runs the builtins through it. Guests build
on their own with `make guests` and `make guests.native`.

### Testing

`make smoke` runs the builtins cold, the multi-call names, the payload tools, one zygote
with three clients, and a bundle.

`make test` runs the pytest suite under `tests/` against `out/bin/amk`. It pins what a
smoke script cannot: the resident role parses once however deep the recursion goes and
reaps after an interrupt, a signalled client exits as a cold make does, a refused
request falls back to the caller's command, `--ape-unpack` honors its staleness rule
and rejects a climbing name, and a bundle runs, recurses, and serves with nothing else
on disk. The suite needs pytest and the binary, nothing else.

```bash
# the suite against out/bin/amk; test.native takes the host build
make test

# a runner that is not on PATH, and flags through to pytest
make test pytest=../../.venv/bin/pytest pytest.args='-k resident -v'

# any binary at all, run from tests/ directly
AMK_BIN=/usr/local/bin/amk pytest tests
```

Docker Desktop's Rosetta layer segfaults every ape, so `--platform linux/amd64`
containers on an arm64 Mac are not a test of the x86_64 half; `arch -x86_64` on the
host is.

### Releases

A release is a pushed tag that starts with `v`, and the tag is the version: the Makefile
reads `amk.version` from the nearest `v` tag with `git describe`, so the banner and
`.AMK_VERSION` say `0.2.0` at the tag and something like `0.2.0-3-gabc1234-dirty` on a
build past it. One command cuts a release from any branch:

```bash
version=0.2.0 make release
```

It refuses to run unless the version is `X.Y.Z`, every tracked change is committed, and
`v0.2.0` exists neither locally nor on `origin`. Then it tags the head, pushes the branch
and the tag, and streams the workflow run when `gh` is installed; `make release.watch
version=0.2.0` reattaches to a run. `release.remote=` names another remote.

The `Release` workflow builds `amk` from a clean tree on Linux, runs `make smoke`, checks
that the banner names the tag, runs
the built file on x86_64 Linux, arm64 Linux, and macOS without rebuilding it, and
publishes `amk` and `amk.sha256` as a GitHub Release named after the tag, and the
container image to `ghcr.io/robot-wranglers/amk` after smoking it on amd64. Running the
workflow by hand on a branch is a dry run: it builds and checks, builds the image for both
platforms, and pushes nothing. Every push and pull request runs the same build through the `Build` workflow and
keeps the result as a workflow artifact. A weekly `Pins` workflow fetches every input cold
and verifies it, so a digest that moved upstream surfaces before it breaks a release.

### Layout

`out/` holds artifacts only. Everything else this directory produces stays under
`build/`, and `make stat` prints the whole list with sizes. `st` and `status` are aliases.

| path | what it is |
| --- | --- |
| `./amk` | the deliverable, the copy `make amk` lands for a caller |
| `out/bin/amk` | the artifact: make with its guests, both architectures, one file |
| `out/bin/{awk,jq,wasm3}` | symlinks to `amk` beside them, the names its argv[0] dispatch answers to |
| `out/bin-native/amk` | the same sources built by the host compiler, for the debug loop |
| `out/bin-native/{awk,jq,wasm3}` | the same names for the host build |
| `build/.engines` | the engine list the artifacts were built from, so a change to it relinks |

`build/guests/ape/` and `build/guests/native/` hold each guest partial-linked into one
relocatable, the inputs the final link consumes. They are the expensive half of a build,
so nothing removes them on the way to `out/bin/amk`: cosmocc compiles every guest for both
architectures, and a rebuild that reuses them takes a fraction of the time. `build/` also
keeps each configure tree and a `build.log` per guest, which is where a compile failure
is reported.

`make clean` drops `./amk` along with `src build out`, which discards those relocatables
and costs a full rebuild. The downloads and the unpacked toolchain always stay.

### Payload Internals

The payload tools are the released cosmos binaries, unchanged, as the payload members
`bin/sed` and `bin/bash`, plus the json.bash script as `bin/jb`, `bin/jb-array`, and
`bin/json.bash`, unpacked to `${XDG_CACHE_HOME:-$HOME/.cache}/amk/<size>-<mtime>/bin`.
A recursive make finds that directory already first on `PATH` and leaves `PATH` alone. A
tool is added by pinning its release in the Makefile beside `sed` and naming it in
`tools.all`, with a `.names` list when it lands under more than one name, and in
`tools.optout` when `without` may drop it; nothing compiles it.

bash is a separate binary rather than a guest linked into amk because a shell forks
constantly, and a fork inside a large cosmo image can lose part of its text on Apple
Silicon; the small standalone build does not.

`--bundle` edits the zip in place rather than rebuilding: everything ahead of the central
directory is kept, new members are appended stored, and a new directory drops any member
they replace. `--ape-unpack` and `--bundle` both write beside the destination and rename
into place. A zygote started from a bundle holds the entry among its own options, so its
clients match it.

### Dependencies

Every input is pinned by version and sha256 in the Makefile. Upstream ships no
checksum files, so the digests are ours. The guests' versions are in the
[standard guests](#guests) and [special guests](#special-guests) tables; the
rest of the build is make itself and its toolchain:

| input | version | from |
| --- | --- | --- |
| make | 4.4.1 | [ftp.gnu.org](https://ftp.gnu.org/gnu/make/) |
| cosmocc | 4.0.2 | [cosmo.zip](https://cosmo.zip/pub/cosmocc/) |

s7 is the one input whose url carries no version, so its digest is the whole pin and
moves whenever upstream publishes. A digest mismatch there is a new release, not a
tampered download: check what changed, then update `s7.version` and `s7.sha256` together.

`deps` downloads into this directory and leaves what is already present alone. It fetches
and verifies only the engines this build selects, so `without` also skips the download and
an opt-in engine is fetched only `with` it. The
toolchain unpacks to `cosmocc/` on first use; set `cosmocc.dir=/opt/cosmocc` to use
an installed copy instead. Invoke cosmocc through `PATH`, never through a symlink:
it locates `mktemper` and its siblings beside its own path.

### Patches

Only make is patched; guests stay pristine. `patches/` is a numbered series applied in
order, and [patches/README.md](patches/README.md) describes the series, the engine table
each engine adds a row to, and how a guest is hidden inside the link. Each patch file opens
with a note on what it does and any exception it makes for its guest.

A consumer that needs make fitted to itself keeps a series of its own and applies it after
this one, without forking the tree. `patch.dirs` names the directories in order, and
`flavor` names the build so its patched tree and artifact land beside the plain ones:

```bash
make build flavor=cmk patch.dirs='patches ../ape/patches'
# src/make-4.4.1-cmk, build/ape-cmk, out/bin-cmk/amk; the guests are shared
```

Both must be given together. The overlay's patches are written against the tree this series
leaves, so they say which amk version they apply to and are rebased when it moves.

### The APE Loader

An ape's header installs its loader at `$TMPDIR/.ape-1.10` on first run. A caller that
cannot go through a shell can name that loader explicitly.

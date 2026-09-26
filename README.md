# amk

`amk` is ape-make, an actually portable cosmopolitan `make`. 

A drop in replacement, but also with brand new superpowers.


**Overview:** [Install](#install) | [Bundling & Distribution](#bundling--distribution) | [Standard Guests](#standard-guests) | [Special Guests](#special-guests) | [Zygote / Resident Mode](#resident-dispatch)

**Details:** [Payloads](#payloads) | [The load directive](#the-load-directive) | [Command line](#command-line) | [Running an ape](#running-an-ape) | [Developers](#developers)

## Overview 

This build / fork starts from make-4.4.1 and creates one file that runs on Linux, macOS, and the BSDs.  We're backwards compat as a drop-in replacement[**](#the-load-directive), but can also offer a bunch of new features.  

The main use-cases:

1. **[Bundling & Distribution](#bundling--distribution):** Besides solving for *runs anywhere*, this also solves *bundles anything*.  APEs are bins and zip files at once, so `amk` is also a way to [distribute payloads](#payloads). Corollary: we can also *bundle and distribute* Makefile-as-scripts, and it works with more than one Makefile too.  Now you've got modules/libraries.

1. **[Standard Guests](#standard-guests)** are the other part of (1), meaning that the *rest* of the shell toolchain can also be APE'd riders.  Now you don't care which `awk` is available *or* which `make` is available, or if either are available.  Now you've got a portable shell-scripting environment, without containers.

1. **[Special Guests](#special-guests):** Basically a **polyglot VM in miniature!**  Shell remains a fist-class citizen, but `amk` also exposes embedded engines for things like **[python](#micropy), [lua](#lua), [lisp](#s7), and [wasm](#wasm),** with a familiar coordination language already in place to switch between them.  Now you've got graal, without JDK.

1. **[Zygote / Resident Mode](#resident-dispatch):**  Useful to avoid cold-start penalties in many circumstances.  Side-effect free?  Execution freezes a program, then runs and re-runs against the same base without a re-parse.  Now you can opt in to trade the incremental computing model for massively improved recursion and FP.

Put this stuff together, and it's a kind of *pseudo-compilation* over a make-dialect that can produce a platform-independent binary, can link libraries into something like Makefile-as-modules for code-reuse, and indeed even supports a kind of bidirectional FFI.  

Have fun.

## Install

One file runs on Linux, macOS, and the BSDs:

```bash
curl -fsSLO https://github.com/Robot-Wranglers/ape-make/releases/latest/download/amk
chmod +x amk
mkdir -p ~/.local/bin && mv amk ~/.local/bin/
amk --version
```

On Apple silicon the first run needs a C compiler; run `xcode-select --install` if `cc` is missing.

### Verifying the download

Each release carries a checksum beside the binary:

```bash
curl -fsSLO https://github.com/Robot-Wranglers/ape-make/releases/latest/download/amk.sha256
sha256sum -c amk.sha256   # on macOS: shasum -a 256 -c amk.sha256
```

### Docker

```bash
docker run --rm -v "$PWD:/work" ghcr.io/robot-wranglers/amk:latest <target>
```

The image runs `amk` in `/work`. Use the `wasm3` tag for the build with the [wasm](#wasm) engine.

## Bundling & Distribution

The typical use-case for bundling is creating a new standalone. This works by cloning the `amk` runtime, bundling extras, and setting the new entrypoint:

```bash
# make the bundle
amk --bundle my.Makefile my.lib/ --out my.tool

# run it anywhere
./my.tool
```

Makefile-as-script was historically a bad idea, the kind of (ab)use that encourages a lot of *"It's a build tool, not a scripting language!"* objections.  

Why not both?  Worth revisiting now!  Vanilla Makefile was already a superset of bash that encourages more structured programming.  After *runs-anywhere* and *bundle-anything* is solved, monolithic scripts can become libraries, and problems with working directory disappear.

The only problem is that certain platforms (looking at you, MacOS) might default to having *other* utilities besides `make` (like *bash / awk / sed / jq*) which may be missing by default, non-GNU, or incredibly ancient.  Hmm, but that's another problem solvable with some combination of APEs and bundling..

So, `amk` ships with exactly those tools.  They are not only bundled, but where applicable are also *linked*.  Thus e.g. jq is available via libjq, and via `$(jq ..)` from Makefiles, with no penalty for forking a subprocess.  Great!, now JSON is a native "type" and your portable, compiled Makefile looks to have grown sophisticated datastructures, and a query-language, with no speed penalty.  See the [standard guests](#standard-guests) section for more details.

## Standard Guests

Standard guests are mostly **bundled tools**, plus two libraries.  

Tools are themselves portable APEs, and they usual suspects; the goal is no more ambiguity about whether sed/awk are GNU, no more wondering if bash is modern.

| tool | version | from | run as |
| --- | --- | --- | --- |
| gmsl | 1.2.4 | [github.com/jgrahamc](https://github.com/jgrahamc/gmsl/tree/v1.2.4) | `include /zip/lib/gmsl` |
| dkjson | 2.8 | [dkolf.de](http://dkolf.de/dkjson-lua/) | `require("dkjson")` inside `$(lua)` |
| awk | gawk 5.3.1 | [ftp.gnu.org](https://ftp.gnu.org/gnu/gawk/) | `amk --awk`, or amk under the name `awk` |
| jq | 1.7.1 | [github.com/jqlang](https://github.com/jqlang/jq/releases/tag/jq-1.7.1) | `amk --jq`, or amk under the name `jq` |
| [sed](#tools) | GNU sed 4.9 (cosmos 4.0.2) | [cosmo.zip](https://cosmo.zip/pub/cosmos/v/4.0.2/bin/) | `sed` on `PATH` |
| [bash](#tools) | 5.2.0 (cosmos 4.0.2) | [cosmo.zip](https://cosmo.zip/pub/cosmos/v/4.0.2/bin/) | `bash` on `PATH` |

Tools are bundled internally, available by default on PATH for any recipe, for any host.

```make
SHELL := bash

check:
	test "$${BASH_VERSINFO[0]}" -ge 5
```

Since awk and jq are standard *and* [special](#special-guests), they are also available as part of `amk` itself.

```bash
# Flag first, then the rest goes to the tool
./amk --awk 'BEGIN { print "hello" }'

# Same for jq
printf '{"n":41}' | ./amk --jq .n+1

# Every engine answers its own flag the same way, with the rest of the line as its arguments
./amk --lua 'print(6 * 7)'
./amk --s7 '(display (* 6 7))'
./amk --micropy 'print(6 * 7)'
./amk --js 'print(6 * 7)'

# One engine per line: its builtin name, then the names it answers to, if any
./amk --list-engines
```

Since `amk` knows the name it's called by, a symlink named for the tool works the same.

```bash
ln -s amk awk && ./awk 'BEGIN { print "hello" }'
```

GMSL, the GNU Make Standard Library, adds datastructures and other primitives.  Any bundle can write `include lib/gmsl` and use it from anywhere to enjoy *sets, associative arrays, stacks, and integer and strings* written efficiently in make.

## Special Guests

Special guests are embedded engines, linked into `amk` directly and callable as make functions: 

```Makefile
# Calling an engine with a program
$(engine_name program[,input])
```
Each runs in-process with the input on stdin and returns its output less one trailing
newline, so a one-line result is ready to use. `$(strip)` folds a multi-line result into
words.

| engine | version | from | gives | adds | default |
| --- | --- | --- | --- | --- | --- |
| [gawk](#awk-and-jq) | 5.3.1 | [ftp.gnu.org](https://ftp.gnu.org/gnu/gawk/) | `$(awk)`, `$(awk.argv)` | 1.3 MB | on |
| [jq](#awk-and-jq) | 1.7.1 | [github.com/jqlang](https://github.com/jqlang/jq/releases/tag/jq-1.7.1) | `$(jq)`, `$(jq.argv)` | 1.9 MB | on |
| [lua](#lua) | 5.4.8 | [lua.org](https://www.lua.org/ftp/) | `$(lua)` | 0.5 MB | on |
| [s7](#s7) | 11.9 | [ccrma.stanford.edu](https://ccrma.stanford.edu/software/s7/) | `$(s7)` | 4.1 MB | on |
| [micropython](#micropy) | 1.29.0 | [github.com/micropython](https://github.com/micropython/micropython/releases/tag/v1.29.0) | `$(micropy)` | 0.8 MB | on |
| [quickjs](#js) | 2026-06-04 | [bellard.org](https://bellard.org/quickjs/) | `$(js)` | 2.0 MB | on |
| [wasm3](#wasm) | 0.9.0 | [github.com/wasm3](https://github.com/wasm3/wasm3/tree/v0.9.0) | `$(wasm)`, `$(wasm.argv)`, `amk --wasm` | 0.4 MB | off |

#### Passing programs and input

make expands `$` and splits on commas before an engine sees its arguments:

```make
# inline: a literal $ is written $$
shout := $(awk { print toupper($$0) },hello)

# inline: commas inside ( ) are safe
head := $(awk BEGIN { print substr("hello", 1, 4) })

# a top-level comma would end the program early, so the program goes in a define
define awk.pair
BEGIN { printf "%s-%s", "a", "b" }
endef
pair := $(awk $(value awk.pair))

# $(value) passes a define raw, so $2 stays $2
define awk.second
{ print $2 }
endef
second := $(awk $(value awk.second),alpha beta gamma)
```

`shout` is `HELLO`, `head` is `hell`, `pair` is `a-b`, and `second` is `beta`. Braces do
not protect a comma the way parentheses do, and the last argument, the input, may hold
any commas.

#### awk and jq

`$(awk.argv argv,program[,input])` and `$(jq.argv argv,program[,input])` put the tool's
options first. The option list splits like a shell command line, quotes included.

```make
# make has no arithmetic: 37.5
pct := $(awk BEGIN { print 100 * 3 / 8 })

# options first, here a regex record separator: portable
longest := $(awk.argv -v RS=[[:space:]]+,length > n { n = length; w = $$0 } END { print w },make awk portable jq)

# JSON input from a variable, printed raw: 1.2.3
pkg := {"name": "cmk", "version": "1.2.3"}
pkg.version := $(jq.argv -r,.version,$(pkg))

# an option list with spaces and quotes, from a variable
opts = -n -r --arg alts 'k/a k/b' --arg none ""
frame := $(jq.argv ${opts},$$alts + "|" + $$none)
```

#### lua

The input is read with `io.read` or `io.lines`. What the chunk prints is the result.

```make
# inline: 42
answer.lua := $(lua print(6 * 7))

# multiline chunk and multiline input, each a define: 9 words
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
count := $(lua ${lua.count},$(words))
```

#### Persistent state

Every engine call runs in a fresh child and forgets everything at the end. An engine may
also offer a persistent form, `$(<name>.persistent ...)`, that runs in the make process
against one state kept for the life of that process, so a global one call sets is there
for the next. Its result is what the chunk prints. Init and hooks both live on this state.
Under a zygote the state is forked with the parse, so each request starts from what the
parse left. Persist, init and hooks are three entries on an engine's row: init comes with
persist, and a hook entry is written per guest. Today lua supplies both.

#### Init

Every engine with persistent state runs one chunk in that state before make reads any
makefile, in every make process, so what the chunk defines is present for the parse and a
hook it registers hears the first `goals` event. The chunk comes from `AMK_<NAME>_INIT`,
as text or as `@path`, or from `__init__.<name>` at the root of a bundled payload. Under a
zygote the chunk runs once and every request inherits the result, which is how a
distribution loads its guest code without paying for it per request. The lookup is per
engine, so `__init__.lua` and `__init__.micropy` would each go to their own state.

#### Hooks

make announces three moments: `goals`, once the goal list is known, and `recipe_start`
and `recipe_end` around each target's recipe. Every engine that supplies a hook entry
hears them, with the event name, the target (or the space-joined goals), the recipe's
status word and exit code, and the pid. How a guest subscribes is its own spelling: in
Lua, a function at `amk.on.<event>` in the persistent state. Hooks observe; they cannot
veto or replace a recipe. Anything a hook prints goes to stderr, and an error in a hook is
reported there and does not stop make.

#### s7

The input is the current input port, for `read-line` or `read`. An error reports on
stderr and the call expands to nothing.

```make
# inline: 42
answer.s7 := $(s7 (display (* 6 7)))

# a function defined and used: 20! is 2432902008176640000
define s7.fact
(define (fact n) (if (= n 0) 1 (* n (fact (- n 1)))))
(display (fact 20))
endef
big := $(s7 ${s7.fact})
```

#### micropy

MicroPython: Python 3 with `sys`, `os`, `io`, `json`, `re`, `time`, `math`, `random`,
`struct`, `collections`, `hashlib`, `binascii`, `deflate`, `select` and `errno`. The input
is `sys.stdin`. There is no `input`, `asyncio`, threads or `machine`.

```make
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

#### js

QuickJS: ES2023 JavaScript with `JSON`, `RegExp`, `BigInt`, `Promise` and the rest of
the language builtins, plus the qjs `std` and `os` modules bound as globals. The input
is `std.in`, read with `getline` or `readAsString`, and `print` writes the result. A
top-level `await` is allowed. There is no `require`, `console` beyond `console.log`,
`fetch` or `setTimeout` past what `os` provides.

```make
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

#### wasm

Off by default; build `with=wasm3`. The first argument is a module path and its
arguments, not program text. What the module's `_start` writes to stdout is the result.

```make
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

```make
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

### Feature words

`.FEATURES` carries `awk jq lua s7 micropy js`, plus `wasm` when it is built in, and
`.ENGINES` carries the same names on their own. Stock make has no `.ENGINES`, so testing
it gives a clean no rather than an error, and one makefile can run under either.
`.AMK_VERSION` carries amk's own version, while `$(MAKE_VERSION)` stays make's.

`--version` keeps make's first line for everything that parses it, and its second line
names amk, the flavor when the build has one, and the engines linked in:

```
GNU Make 4.4.1
Built for x86_64 and aarch64 as an actually portable executable (amk 0.1.0: awk jq lua s7 micropy js)
```

Gating on an engine, so a makefile takes its fallback under stock make:

```make
ifneq ($(filter jq,$(.FEATURES)),)
  version := $(jq.argv -r,.version,$(file < package.json))
else
  version := $(shell jq -r .version package.json)
endif
```

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

```make
# a current copy is left alone, so this is cheap on every parse
include $(shell cmk --ape-unpack=compose.mk)
```

### Tools

GNU sed and bash 5.2 are unpacked to a cache under `${XDG_CACHE_HOME:-$HOME/.cache}/amk/`,
keyed by the binary, and put first on `PATH` before any makefile is read:

```bash
./amk -f /dev/stdin <<'EOF'
SHELL := bash
all:
	# prints ~/.cache/amk/<key>/bin/sed
	command -v sed
	# prints sed (GNU sed) 4.9
	sed --version | head -1
	# prints 5.2.0(1)-release
	echo $$BASH_VERSION
EOF

# keep the host's PATH instead
AMK_NO_PATH=1 ./amk
```

A tool is an ape, so the [execve rule](#running-an-ape) applies: Python `subprocess`
starting `sed` without a shell fails on macOS.

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

```make
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

## The load directive

[`load`](https://www.gnu.org/software/make/manual/html_node/load-Directive.html) is the
one place `amk` departs from stock make. An ape cannot `dlopen`, so nothing is ever
loadable, and `load` reports the platform does not support it. The `-load` form, which
stock make treats as a request to
[rebuild the object and try again](https://www.gnu.org/software/make/manual/html_node/Remaking-Loaded-Objects.html),
instead answers that the object will never be rebuilt, so a makefile that guards a
loadable with `-load` continues without it rather than looping.

## Command line

Every flag amk adds to make's own, each read ahead of option decoding. The sections above
describe them; this is the one list, and `--help` ends with the same one. The smoke test
holds the two together: a flag in this table that `--help` does not name fails the build.

| flag | takes | does |
| --- | --- | --- |
| `--<engine>` | the engine's arguments | runs that engine with the rest of the line: `--awk`, `--jq`, `--lua`, `--s7`, `--micropy`, `--js`, `--wasm` |
| `--list-engines` | | prints one engine per line, the builtin name and then its multi-call names, if any |
| `--serve SOCK` | a socket path, then make's arguments | parses once and answers requests on the socket as the [zygote](#resident-dispatch) |
| `--client SOCK` | a socket path, then the request, optionally `-- <cold command>` | runs the request against a zygote, or the cold command when refused |
| `--resident` | make's arguments | one command served by a zygote it starts and reaps itself |
| `--ape-unpack NAME`, `-x NAME`, `--ape-unpack=NAME [DEST]` | a payload member, an optional destination | copies the member out and prints its [path](#payloads) |
| `--force` | | with `--ape-unpack`, overwrites a destination that exists |
| `--bundle FILES... --out DEST` | makefiles and directories, the output path | writes a copy of amk whose default entry is that [program](#bundles) |

## Running an ape

A shell runs an ape where a bare `execve` cannot: the file's header is a shell script
that installs a small loader in `$TMPDIR` on first run. `sh`, `make`, and any shell-based
wrapper all go through one. Python `subprocess` does not; wrap the call in `sh -c`.

The file must keep its exec bit even when run as `sh ./amk`: the header finds itself with
`command -v`, which on macOS skips a file that is not executable, and the first run then fails
with `gzip: (stdin): unexpected end of file`. Anything that copies it without its mode, such as
a CI artifact, needs a `chmod +x` first.

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
with three clients, and a bundle. It includes `make smoke.readme`, which extracts every
make block under [Guests](#guests) and runs it against the built binary, with
`readme.mk` asserting the value each one promises.

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

A release is a pushed tag that starts with `v`. The tag is the version; nothing is stamped
into the binary.

```bash
git tag v0.1.0 && git push origin v0.1.0
```

The `Release` workflow builds `amk` from a clean tree on Linux, runs `make smoke`, runs
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

### Payload internals

The payload tools are the released cosmos binaries, unchanged, as the payload members
`bin/sed` and `bin/bash`, unpacked to `${XDG_CACHE_HOME:-$HOME/.cache}/amk/<size>-<mtime>/bin`.
A recursive make finds that directory already first on `PATH` and leaves `PATH` alone. A
tool is added by pinning its cosmos release in the Makefile beside `sed` and naming it in
`tools`; nothing compiles it.

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
[standard guests](#standard-guests) and [special guests](#special-guests) tables; the
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

### The ape loader

An ape's header installs its loader at `$TMPDIR/.ape-1.10` on first run. A caller that
cannot go through a shell can name that loader explicitly.

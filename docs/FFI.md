# The FFI

[Overview](#overview) | [Calling a guest from make](#calling-a-guest-from-make) | [Calling make from a guest](#calling-make-from-a-guest) | [Events](#events) | [Processes](#processes) | [Output](#output) | [Per-engine notes](#per-engine-notes) | [Writing a new guest](#writing-a-new-guest) | [Demos](#demos) | [Reference](#reference) | [Engine API](#engine-api)

## Overview

### Directions of the bridge

### Features and Version Info

`.FEATURES` is a standard builtin var for `make` which `amk` honors and extends.  You can consult to find out what's available in the current runtime, for use with `ifeq..endefs` guards and so on.  Default values with the default `amk` build would include default engine names, e.g. `awk jq lua s7 micropy js`, plus e.g. `wasm` if/when it is built in.

`.ENGINES` is similar, but `amk` specific, thus the *mere presence* can confirm/deny whether the runtime is `amk`.  

Also available and related.. `.AMK_VERSION` carries amk's own version, while `$(MAKE_VERSION)` stays make's.

From the CLI, `--version` details everything like so:

```
GNU Make 4.4.1
Built for x86_64 and aarch64 as an actually portable executable (amk 0.1.0: awk jq lua s7 micropy js)
```

Typical pattern for guards is something like:

```make
ifneq ($(filter jq,$(.FEATURES)),)
  version := $(jq.argv -r,.version,$(file < package.json))
else
  version := $(shell jq -r .version package.json)
endif
```

#### Capabilities by Engine

The goal is a unified interface for all engines, but what can be done easily depends on what the upstream embedded projects actually expose.  Among other things, the variations on this theme includes questions like

* CLI / argv exposed for runtime config, or code only?
* Exec vs Eval: persistent kernel or one-shot only?
* Singleton kernel or many possible?

The most interesting question is around whether FFI is *bidirectional* yet, i.e. whether `amk` can simply run the guest or if the guest can actually reach into the `amk` runtime to change it, or possibly to *call other guests*.

This table tracks the current breakdown of per-engine support:

| engine | `$(name ...)` | `.argv` | `.import.target` | `.persistent` | init | hooks | handle reads | handle writes | `amk.func` | `.import` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| awk | yes | yes | yes | - | - | - | - | - | - | - |
| jq | yes | yes | yes | store | yes | - | - | - | - | - |
| lua | yes | - | yes | yes | yes | yes | yes | yes | yes | yes |
| s7 | yes | - | yes | yes | yes | yes | yes | yes | yes | yes |
| micropy | yes | - | yes | yes | yes | yes | yes | yes | yes | yes |
| js | yes | - | yes | yes | yes | yes | yes | yes | yes | yes |
| wasm | module | yes | - | - | - | - | - | - | - | - |

Handle reads are `amk.var` and `amk.expand`; handle writes are `amk.var` assignment and
`amk.eval`. Init, hooks, `amk.func`, and `.import` all need the persistent state, so a
row gains them together once it has a persistent entry. jq is the exception: its
persistent entry is a store of named JSON values, which runs an init chunk but has no
hooks or handle.

## Calling a guest from make

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

### Persistent state

`$(<name>.persistent program[,input])` runs in the make process against one state kept
for the life of that process, where `$(<name> ...)` forks a fresh one per call. A global
one call sets is there for the next, the input arrives as `amk.input`, an error leaves
the state as it was, and the result is what the chunk prints, trimmed like every
builtin's. Under a zygote the state is forked with the parse, so each request starts from
what the parse left. lua, s7, micropy, and js supply persistent entries.

A one-shot call runs in a forked child that inherits the parent's persistent state, so
each engine's one-shot entry starts its own state and does not see it as persistent.

### The jq store

`$(jq.persistent op name prog)` holds named JSON values for the life of the make process
and runs jq programs over them in that process, with no fork. The store is a map from name
to value; a missing name is `null`, and a name is any word, so a caller scopes names to a
run the way it would name files. Every call names the entry it works on:

| call | runs | stores | returns |
| --- | --- | --- | --- |
| `get NAME PROG` | the program over the value | nothing | every output |
| `update NAME PROG` | the program over the value | the first output | the rest |
| `take NAME PROG` | a program yielding `[new, out...]` | `new` | `out...` |
| `load NAME PATH` | | the one JSON text in the file | nothing |
| `load NAME,TEXT` | | the one JSON text given as the input | nothing |
| `dump NAME` | | nothing | the value as compact JSON |
| `filter [OPTS] PROG,TEXT` | the program over every JSON text in the input | nothing | every output |

Words before the program bind variables as the jq tool does, `--arg k v` for a string,
`--argjson k v` for a value, `--slurpfile k path` for every JSON text in a file as an
array and `--rawfile k path` for a file's text, and `-r` prints a string output bare. A
value with a space or a quote inside it travels quoted as a shell would write it, and
inside double quotes `\n` reads as a newline. A program compiles once
per text and set of bound names, so a loop that binds a new value each turn never
recompiles. A program error is a nonzero `.SHELLSTATUS` with jq's message on stderr, never
a make error, and the value stays as it was.

```Makefile
# a stack in the store: push, then pop the top and keep the rest
seed  := $(jq.persistent update stack [1] + [2])
push  := $(jq.persistent update stack --argjson v 3 . + [$$v])
pop.prog := [.[:-1], .[-1]]
pop   := $(jq.persistent take stack $(pop.prog))
depth := $(jq.persistent get stack length)
# a string output printed bare
name := $(jq.persistent update who {"name": "a b"})
who  := $(jq.persistent get who -r .name)
```

`pop` is `3`, `depth` is `2` and `who` is `a b`. A comma at the top level of a program ends
the argument, as for every builtin, so a program with one goes in a variable and the call
names the variable, as `pop.prog` does. Under a zygote each request starts from the store
the parse left.

### Init

Every engine with persistent state runs one chunk in that state before make reads any
makefile, in every make process, so what the chunk defines is present for the parse and a
hook it registers hears the first `goals` event. The chunk comes from `AMK_<NAME>_INIT`,
as text or as `@path`, or from `__init__.<name>` at the root of a bundled payload. Under a
zygote the chunk runs once and every request inherits the result, which is how a
distribution loads its guest code without paying for it per request. The lookup is per
engine, so `__init__.lua` and `__init__.micropy` would each go to their own state.

#### Defining a target in an engine

`@<engine>.import.target` above `define name` through `endef` makes the body a program
for that engine and the name a phony target that runs it on the job's own input and
output, every time. Only a target that some body references as `@name@` keeps its value,
in `$(goal.dir)/name`, `.amk/goals` by default, and its name prints that. With no
reference in any body, `goal.dir` is never read and no directory is made.

### Values between goals

`$(goal name)` answers the value of a goal: it brings the goal up to date, in a fork of
the parsed image the way the spawn api runs a goal list, then reads its value, trimmed
of one trailing newline like every builtin. An imported target's value is what its
program printed, kept or not. A plain file target has a value too, the file itself,
read where it is and never copied.

An imported body reaches its engine as written, so `$` is the guest's. Its one form is
`@x@`, the value of goal x spliced in raw: a name of letters, digits and `_ . - /`, in
any case, that must match exactly one target a makefile names; a file needs a rule,
even an empty one. Each is a prerequisite on x's value file, so a kept value reruns only
when a value it reads is newer, and independent targets run at once under `-j`. Names
resolve after the makefiles are read, so a reference may come first. `$(goal ...)`
belongs in recipes, and a plain rule names the goal as a prerequisite.

An imported target's job is a fork of make with no exec, so the guest handle reads make
state there; its writes end with the job. The fork splices the values into the program
and runs the engine on it, a kept value's output on its file. No file carries the
program and no argument limit bounds its size. A failed target keeps what it wrote, as
any recipe does, unless the makefile names `.DELETE_ON_ERROR:`.

### Feeding a job's standard input

`$(job.stdin text)` expands to nothing and feeds the text to the command on the recipe
line it appears in, through a pipe a detached helper fills, so the text may be any
size. The pipe is bound to that line of that target, so two lines each get their own
and targets that interleave under `-j` never cross. A line whose command never runs
drops its pipe when the target's job ends. Outside a recipe the function is an error.

Every text engine's flag form reads its program from standard input when its argument
is a lone dash: `amk --lua -`, and the same for s7, micropy, and js. awk and jq keep
their own command lines, so a recipe hands awk `-f -` and jq `-n -f /dev/stdin`, which
also gives jq the null input it needs to run without data.

### Calls from a recipe

A builtin expands before a recipe runs, so a value that changes while the recipe runs, a stack popped in a loop, needs a call at recipe time. Every make process names two descriptors to its recipes, `AMK_CALL` and `AMK_REPLY`, a request pipe and a reply pipe, and answers on them from the jq store while the recipe's shell runs. Everything is line framed and carries JSON as it is: a request is one line, the store call; a reply is a `STATUS N` line, then N lines, one output each. Shell builtins do the whole exchange, so a call costs a write and a read and never a fork:

```Makefile
define ask
printf '%s\n' "$(1)" >&$$AMK_CALL && read -r st n <&$$AMK_REPLY && { [ "$$n" = 0 ] || IFS= read -r $(2) <&$$AMK_REPLY; }
endef

drain:
	$(call ask,update S [3$(,) 1$(,) 2],x)
	while :; do $(call ask,take S [.[:-1]$(,) .[-1]],top); \
	  $(call ask,get S length,n); echo "popped $$top"; [ "$$n" != 0 ] || break; done
, := ,
```

The status is the store's, `0` when the program ran clean. A sub-make and a spawned job
hold no store of their own: each inherits a live pair and sends every request up it, its own
`$(jq.persistent)` expansions included, so every process of a run reads and writes the same
entries. A request served by a zygote starts as an owner, from the store the parse left.

**Tags.** Recipe shells of one process share its pair, so two callers running at once, two
stages of one pipeline or two lines under `-j`, would read each other's replies. A request
that opens with `@TAG` is answered instead into a private FIFO, `$AMK_REPLY_DIR/TAG`, which
the answering process makes and removes; one empty line on `AMK_REPLY` says the FIFO is
there before the caller opens it. `$BASHPID` is a tag no other caller holds. Hops forked
from one parse share the directory, and the one that answers after a sibling took it down
makes it again.

**The shell side, once.** `amk.sh` sits on `PATH` beside the payload tools, so a recipe
runs `source amk.sh` and has two functions. `amk.call REQUEST [LINE...]` sends a tagged
request, with input lines after it, prints the reply lines and returns the status.
`jq.pipe [OPTS] PROG` reads stdin and runs the program over it in the make process, so a
pipeline converts by replacing the command word:

```Makefile
names:
	source amk.sh; printf '{"n":"a"}\n{"n":"b"}\n' | jq.pipe -r .n | sort -r
	source amk.sh; amk.call 'get S length'
```

`jq.pipe` sends `filter N [OPTS] PROG` and then N input lines; the outputs come back as
jq would print them. OPTS is exactly `-r -c -e -n -s --arg --argjson --slurpfile
--rawfile`, and any other option is status 2 with nothing run, so a site that needs more
fails when it converts rather than later. `amk.words ARG...` writes its arguments as
words for a request line, so a caller building `get` or `update` by hand quotes its
option values with it and passes the program raw. jq's messages go to make's stderr.

## Calling make from a guest

### The guest handle

Lua, micropy, s7, and js each carry a handle into make: the same four calls, spelled the
way each language expects.

| | lua | micropy | s7 | js |
| --- | --- | --- | --- | --- |
| read | `amk.var.CC`, `amk.var["a.b"]` | `amk.var.CC`, `amk.var["a.b"]` | `(amk-var 'CC)`, `(amk-var "a.b")` | `amk.var.CC`, `amk.var["a.b"]` |
| write | `amk.var.CC = "cc"` | `amk.var.CC = "cc"` | `(set! (amk-var 'CC) "cc")` | `amk.var.CC = "cc"` |
| expand | `amk.expand(text)` | `amk.expand(text)` | `(amk-expand text)` | `amk.expand(text)` |
| eval | `amk.eval(text)` | `amk.eval(text)` | `(amk-eval text)` | `amk.eval(text)` |
| undefined | `nil` | `None` | `#f` | `undefined` |

`amk` is bound in every state, so micropy needs no import, though `import amk` still
works. A dotted or hyphenated name goes through the item form, since attribute syntax
cannot spell it. Under an engine flag, `amk --lua ...`, there is no makefile and every
call of the handle raises.

```Makefile
CC := clang
flags = -O2 $(EXTRA)

# reads and expansion, from a one-shot call: clang, -O2, and 3
seen := $(lua print(amk.var.CC, amk.expand("$$(strip $$(flags))"), amk.expand("$$(words a b c)")))

# a write from a one-shot call lands once the call returns, so the next line sees it
$(micropy import amk; amk.var.EXTRA = "-g"; amk.eval("debug: ; @echo $$(flags)"))
now := $(flags)
```

`now` is `-O2 -g` and `debug` is a target.

### Expansion and variable reads

A read of a variable answers it expanded as a reference would be, and answers the
language's own nothing for a name make has never seen, which expansion alone cannot say.
Expand runs any text through make, functions included.

### Variable writes and eval

A write defines a simple variable holding the literal text, at file origin, so a
command-line override still wins. Eval reads text as makefile syntax, rules included. A
[persistent](#persistent-state) call runs in the make process and its writes apply at
once, visible to the same chunk's expand.

### Registering make functions

`amk.func(name, fn)`, or `(amk-func 'name fn)` in s7, from the persistent state of lua,
s7, micropy, or js, gives make a
function `$(name ...)`: its arguments, expanded, reach `fn` as strings, and what `fn`
returns is the result. A nil, None, undefined, or null result is empty, an error reports
on stderr and answers empty, and a second `amk.func` of the same name replaces the
function. A name make already has, builtin or otherwise, is refused. As with any make
function, a call needs at least a space after the name, since `$(name)` alone is a
variable reference.

```Makefile
$(lua.persistent amk.func("shout", function(s) return s:upper() end))
$(micropy.persistent amk.func("glue", lambda *a: "+".join(a)))

# make functions now: HELLO, and A+B
loud := $(shout hello)
joined := $(shout $(glue a,b))
```

`$(<name>.import chunk)` does the same without the calls: it runs the chunk in the
persistent state and imports every global the chunk defined or rebound, a callable as a
make function and any other value as a simple variable, in name order. A string or
number is its text, a boolean is `true` or empty, a list or array is its items as words,
and a table, dict, or object is one variable per key as `name.key`, recursing. A leading
underscore keeps a name private, as do nil, None, null, undefined, modules, and classes.
In js only `var` and function declarations reach the global object; `let` and `const` do
not, and a chunk that looks like a module is not exported at all. The result is the
imported names, and whatever the chunk prints goes to stderr.

```Makefile
define micropy.build
cc = "clang"
flags = ["-O2", "-Wall"]
debug = True
targets = {"lib": "core c", "app": "core c ui"}
def shorten(s): return s[:3]
endef
built := $(micropy.import $(value micropy.build))

# cc debug flags shorten targets.app targets.lib, and clang -O2 -Wall true lib: core c
summary := $(cc) $(flags) $(debug) $(shorten library): $(targets.lib)
```

### Writes from a forked guest

A one-shot call runs in a forked child, so its writes are queued and applied, in order,
when the call completes; the chunk that made them cannot read them back, so it keeps its
own copy of anything it needs again.

## Events

### Hooks

make announces three moments: `goals`, once the goal list is known, and `recipe_start`
and `recipe_end` around each target's recipe. Every engine with a hook entry hears them
with the event name, the target or the space-joined goals, the recipe's status word and
exit code, the signal, and the pid. The spelling is each language's own: lua, a function
at `amk.on.<event>` called with a table; micropy, a callable at `amk.on["<event>"]`
called with a dict; js, a function at `amk.on.<event>` called with an object; s7, a
procedure set with `(set! (amk-on 'event) fn)` and called with a let. The keys are
`event`, `target`, `status`, `code`, `signal`, and `pid` in all four. Hooks observe
and cannot veto a recipe. What a hook prints goes to stderr, and an error in a hook is
reported there and does not stop make.

### The goal list and recipe events

## Processes

### Spawn

### Wait, kill, and foreground

### Captured standard output

### Mail

## Output

### Sinks

### Standard output capture

## Per-engine notes

### lua

### s7

The persistent state is one interpreter kept for the process. A chunk is read in the
rootlet under a catch, so every top-level `define` persists and an error reports on
stderr with the state left as it was; `amk-input` is a rootlet string set per call.
The handle is `amk-expand`, `amk-eval`, `(amk-func 'name fn)`, and two dilambdas, so
`(set! (amk-var 'CC) "cc")` writes a variable and `(set! (amk-on 'goals) (lambda (e)
...))` subscribes a hook; the event is a let, read as `(e 'target)`. Output is captured
at the descriptor and reaches the sink when the chunk ends. Export walks the rootlet: a
procedure becomes a make function, a list or vector its items as words, a hash table or
let one variable per key, `#t` is `true` and `#f` empty, and a string, symbol, or number
its text.

### micropy

### js

The persistent state is one QuickJS runtime and context kept for the process, with the
std and os modules bound as globals and `amk` built by a prelude over raw C calls, so
`amk.var` is a Proxy and `amk.on` a plain object. Output is captured at the descriptor,
since `print` and `std.out` write it directly, and reaches the sink when the chunk ends.
A persistent chunk that looks like a module runs as one; an export chunk always runs as a
global script, since a module's top level never reaches the global object. Pending jobs
and timers run after each chunk, as they do after a one-shot call.

### wasm

# Engine API

## Builtins

| form | direction | engines | patch |
| --- | --- | --- | --- |
| `$(<engine_name> program[,input])` | make to guest | all; wasm takes a module | [0002] |
| `$(<engine_name>.argv args...)` | make to guest | awk, jq, wasm | [0002], [0011] |
| `$(<engine_name>* var[,input])` | make to guest | every non-argv builtin | [0038] |
| `$(<engine_name>.persistent chunk[,input])` | make to guest | lua, s7, micropy, js | [0018], [0028], [0030], [0031] |
| `$(jq.persistent op name program)` | make to guest | jq: `get`, `update`, `take`, `load`, `dump`, `filter` | [0046] |
| `$(<engine_name>.import chunk)` | guest to make | lua, s7, micropy, js | [0029] |
| `$(goal name)` | make | any | [0032] |
| `$(job.stdin text)` | make to recipe | any | [0033] |
| `$(amk.require names...)` | make | any | [0036] |
| `$(amk.dedent text)`, `$(amk.val.dedent var)`, `$(amk.dedent* var)` | make | any | [0037], [0038] |
| `$(amk.fxns? engines)`, `$(amk.vars? engines)` | make | lua, s7, micropy, js | [0040] |

## Grammar

| form | direction | engines | patch |
| --- | --- | --- | --- |
| `@<engine_name>.import.target` above `define` | make to guest | all | [0039], [0042], [0044] |
| `@name@` in an imported body | goal to guest | all | [0043] |
| `__main__` target | make | any | [0035] |

## Variables

| form | direction | engines | patch |
| --- | --- | --- | --- |
| `.FEATURES`, `.ENGINES` | make | all | [0002] |
| `.AMK_VERSION`, `<engine_name>.__version__` | make | all | [0016], [0045] |
| `<engine_name>.__fxns__`, `<engine_name>.__vars__`, `amk.__fxns__`, `amk.__vars__` | make | lua, s7, micropy, js | [0040] |

## Guest handle

| form | direction | engines | patch |
| --- | --- | --- | --- |
| `amk.var` read and write | guest to make | lua, s7, micropy, js | [0027] |
| `amk.expand` | guest to make | lua, s7, micropy, js | [0027] |
| `amk.eval` | guest to make | lua, s7, micropy, js | [0027] |
| `amk.func` | guest to make | lua, s7, micropy, js | [0018] |
| `amk.input` | make to guest | lua, s7, micropy, js | [0018] |
| `amk.on`: `goals`, `recipe_start`, `recipe_end` | make to guest | lua, s7, micropy, js | [0019] |
| `amk.spawn(goals[, opts])` | guest to make | lua | [0020], [0023] |
| `amk.wait([pid[, block]])` | guest to make | lua | [0020], [0024] |
| `amk.kill`, `amk.foreground` | guest to make | lua | [0021] |
| `amk.send(text)` | job to parent | lua | [0024] |
| `amk.exit_code(n)` | guest to make | lua | [0050] |

## Recipe environment and init

| form | direction | engines | patch |
| --- | --- | --- | --- |
| `AMK_MAIL` | job to parent | any | [0024] |
| `AMK_CALL`, `AMK_REPLY`, `amk.call`, `amk.words`, `jq.pipe` | recipe to make | jq store | [0047] |
| `AMK_<ENGINE_NAME>_INIT`, `__init__.<engine_name>` | make to guest | jq, lua, s7, micropy, js | [0022] |
| `__init__.mk`, `AMK_NO_PRELUDE` | make | any | [0034] |

## Command line

| form | direction | engines | patch |
| --- | --- | --- | --- |
| `--<engine_name>`, multi-call names, `--<engine_name> -` | shell to guest | all | [0003], [0033] |
| `--list-engines`, `--version`, `--help` | shell | all | [0003], [0016], [0017] |
| `--serve`, `--client` | shell to make | any | [0001] |
| `--bundle`, `--ape-unpack` | shell | any | [0008], [0013] |

[0001]: ../patches/0001-socket-mode.patch
[0002]: ../patches/0002-builtins.patch
[0003]: ../patches/0003-multicall.patch
[0008]: ../patches/0008-ape-unpack.patch
[0011]: ../patches/0011-wasm3.patch
[0013]: ../patches/0013-bundle.patch
[0016]: ../patches/0016-version.patch
[0017]: ../patches/0017-usage.patch
[0018]: ../patches/0018-api-persistent.patch
[0019]: ../patches/0019-api-hooks.patch
[0020]: ../patches/0020-api-spawn.patch
[0021]: ../patches/0021-api-signals.patch
[0022]: ../patches/0022-api-init.patch
[0023]: ../patches/0023-api-spawn-stdout.patch
[0024]: ../patches/0024-api-mail.patch
[0027]: ../patches/0027-api-var.patch
[0028]: ../patches/0028-micropy-persistent.patch
[0029]: ../patches/0029-api-export.patch
[0030]: ../patches/0030-js-persistent.patch
[0031]: ../patches/0031-s7-persistent.patch
[0032]: ../patches/0032-api-goal.patch
[0033]: ../patches/0033-api-job-stdin.patch
[0034]: ../patches/0034-prelude.patch
[0035]: ../patches/0035-main-goal.patch
[0036]: ../patches/0036-api-require.patch
[0037]: ../patches/0037-api-dedent.patch
[0038]: ../patches/0038-api-star.patch
[0039]: ../patches/0039-grammar-at.patch
[0040]: ../patches/0040-api-bindings.patch
[0042]: ../patches/0042-import-fork.patch
[0043]: ../patches/0043-grammar-goal-ref.patch
[0044]: ../patches/0044-import-kept.patch
[0045]: ../patches/0045-api-version.patch
[0046]: ../patches/0046-api-jq-store.patch
[0047]: ../patches/0047-api-call.patch
[0050]: ../patches/0050-api-exit-code.patch

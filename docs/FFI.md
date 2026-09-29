# The FFI

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

| engine | `$(name ...)` | `.argv` | `define.<name>` | `.persistent` | init | hooks | handle reads | handle writes | `amk.func` | `.export` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| awk | yes | yes | yes | - | - | - | - | - | - | - |
| jq | yes | yes | yes | - | - | - | - | - | - | - |
| lua | yes | - | yes | yes | yes | yes | yes | yes | yes | yes |
| s7 | yes | - | yes | - | - | - | yes | yes | - | - |
| micropy | yes | - | yes | yes | yes | yes | yes | yes | yes | yes |
| js | yes | - | yes | - | - | - | yes | yes | - | - |
| wasm | module | yes | - | - | - | - | - | - | - | - |

Roughly: handle reads are `amk.var` and `amk.expand`; handle writes are `amk.var` assignment and `amk.eval`. Init, hooks, `amk.func`, and `.export` all need the persistent state, so a row gains them together once it has a persistent entry.

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

### Init

#### Defining a target in an engine

A small grammar change to vanilla Makefiles allows `amk` Makefiles to **automatically** declare targets-in-engines.

```make
# a lua target: reachable with `amk greet`
define.lua greet
print("hello from " .. _VERSION)
endef

# a lisp target: reachable with `amk answer`
define.s7 answer
(display (* 6 7))
endef
```

This is just a convenience to avoid some plumbing, so you can do iit anywyay *without* opting in to the new grammar.  But it's tidy!

### Values between goals

`$(goal name)` answers the value of a goal: it brings `$(goal.dir)/name` up to date, in
a fork of the parsed image the way the spawn api runs a goal list, then reads the file,
trimmed of one trailing newline like every builtin. A define cell's value is what its
program printed. A plain file target has a value too, the file itself, copied into the
value directory by a pattern rule the first define enters.

Inside a define cell every `$(goal x)` is also a prerequisite on x's value file, so
referencing a value declares the edge: a cell reruns only when a value it reads is
newer, and independent cells run at once under `-j`. A plain rule that reads a value at
recipe time names the goal as a prerequisite itself. At parse time the fork sees only
the rules read so far, so `$(goal ...)` belongs in recipes and cell bodies.

A cell's program is expanded with the recipe, so its value references resolve in the
make process, and it reaches the engine on the job's standard input: the rule make
writes is `@$(job.stdin ${name})$(MAKE) --<engine> - >$@`. No file carries the
program and no argument limit bounds its size.

### Feeding a job's standard input

`$(job.stdin text)` expands to nothing and feeds the text to the command on the recipe
line it appears in, through a pipe a detached helper fills, so the text may be any
size. The pipe is bound to that line of that target, so two lines each get their own
and targets that interleave under `-j` never cross. A line whose command never runs
drops its pipe when the target's job ends. Outside a recipe the function is an error.

Every text engine's flag form reads its program from standard input when its argument
is a lone dash: `amk --lua -`, and the same for s7, micropy, and js. awk and jq keep
their own command lines, so a cell hands awk `-f -` and jq `-n -f /dev/stdin`, which
also gives a jq cell the null input it needs to run without data.

## Calling make from a guest

### The guest handle

### Expansion and variable reads

### Variable writes and eval

### Registering make functions

`amk.func(name, fn)`, or `(amk-func 'name fn)` in s7, from the persistent state of lua,
s7, micropy, or js, gives make a
function `$(name ...)`: its arguments, expanded, reach `fn` as strings, and what `fn`
returns is the result. A nil, None, undefined, or null result is empty, an error reports
on stderr and answers empty, and a second `amk.func` of the same name replaces the
function. A name make already has, builtin or otherwise, is refused.

`$(<name>.export chunk)` does the same without the calls: it runs the chunk in the
persistent state and exports every global the chunk defined or rebound, a callable as a
make function and any other value as a simple variable, in name order. A string or
number is its text, a boolean is `true` or empty, a list or array is its items as words,
and a table, dict, or object is one variable per key as `name.key`, recursing. A leading
underscore keeps a name private, as do nil, None, null, undefined, modules, and classes.
In js only `var` and function declarations reach the global object; `let` and `const` do
not, and a chunk that looks like a module is not exported at all.

### Writes from a forked guest

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

## Writing a new guest

### The guest header

### Hiding a guest

### The patch series an engine touches

## Demos

## Reference

### C api summary

### Environment variables

### Related patches

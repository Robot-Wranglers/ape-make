# The FFI

## Overview

### Directions of the bridge

### Terms

## Engines and rows

### The engine row

### Feature words

### Capabilities by engine

Engines do not all support the same forms. One row per engine, one column per
capability; a dash means not yet.

| engine | `$(name ...)` | `.argv` | `define.<name>` | `.persistent` | init | hooks | handle reads | handle writes | `amk.func` | `.export` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| awk | yes | yes | yes | - | - | - | - | - | - | - |
| jq | yes | yes | yes | - | - | - | - | - | - | - |
| lua | yes | - | yes | yes | yes | yes | yes | yes | yes | yes |
| s7 | yes | - | yes | yes | yes | yes | yes | yes | yes | yes |
| micropy | yes | - | yes | yes | yes | yes | yes | yes | yes | yes |
| js | yes | - | yes | yes | yes | yes | yes | yes | yes | yes |
| wasm | module | yes | - | - | - | - | - | - | - | - |

Handle reads are `amk.var` and `amk.expand`; handle writes are `amk.var` assignment and
`amk.eval`. Init, hooks, `amk.func`, and `.export` all need the persistent state, so a
row gains them together once it has a persistent entry.

## Calling a guest from make

### One-shot calls

### Passing programs and input

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

### Defining a target in an engine

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

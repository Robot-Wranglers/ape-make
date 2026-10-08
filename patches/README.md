# Patches

amk is GNU make 4.4.1 with its own code beside make's. That code lives in two places:

- `src/amk/`, plain sources with no counterpart in stock make: `amk.h` and one module per
  concern. `make patch` copies them into make's `src/` after unpacking.
- This directory: one hook patch per make file, each a diff against stock make 4.4.1, which
  calls into the modules from where make needs it. `make patch` applies them in order with
  GNU patch (`gpatch` on macOS) and `-p1 -l --fuzz=0`.

A change to amk's behavior is an edit to a module. A patch changes only when make needs a new
hook, or an existing hook moves. Each patch opens with a note naming every hook it carries.

## Modules

| module | what it holds |
| --- | --- |
| `amk.h` | the engine row, the events, the sinks, and every name the modules and make's files share |
| `amk_engine.c` | the engine table, hooks and init chunks, the one-shot guest in a fork, the engine builtins, the sinks, and the ledger of what each engine gave make |
| `amk_ns.c` | namespaces: kept states by name, the operations that run in them, create and its handles, and the builtins that reach them |
| `amk_workspace.c` | workspaces: backings, the ask channel's entry points, and imports |
| `amk_guest.c` | the guest handle's make side: variable reads and writes, eval, the write queue, the collector, `$(amk.goal)`, `$(amk.stdin)`, and the make functions guests define |
| `amk_chan.c` | the ask channel: the request and reply pairs, the per-child pair, serving, waiting, and forwarding |
| `amk_spawn.c` | spawned goal lists: slots, mail, the fork, process groups and the terminal, the deferred call, wait, and the sweep at exit |
| `amk_pool.c` | pools: named semaphores generalizing the jobserver into colored tokens for control structures and bounded concurrency, each a ledger of a size over the jobserver's verbs; the `amk.pool` builtins, and the held count returned at exit |
| `amk_serve.c` | resident dispatch: the request wire format, environment import, option negotiation, the stale watch, the serve loop, the client, and the resident run |
| `amk_payload.c` | the payload: boot, `--ape-unpack`, `--ape-list`, the tools on `PATH`, and `--bundle` |
| `amk_goal.c` | goal references in imported bodies, their resolution after the parse, and the values spliced into a body |
| `amk_mode.c` | the mode table, the `amk.mode` builtin and its setter, and the setting lookup modes share |
| `amk_dataflow.c` | the `dataflow` mode: value records, failed values moved aside, kept files, early cutoff, and body freshness |
| `amk_builtins.c` | `amk.require`, `amk.sys`, `amk.dedent`, `cksum`, `re.match`, `amk.args`, `amk.kwarg`, and the argument trim and key=value split builtins share |
| `amk_profile.c` | the function profiler |

Code that reads one of make's own statics stays in make's file as a bridge, so that static
stays static: the served child's goal handling in `main.c`, the function-table bridges in
`function.c`, the imported target's rule in `read.c`, and the imported target's job in
`job.c`.

## Hook patches

| patch | what it hooks |
| --- | --- |
| `0001-makefile-in.patch` | the modules join make's object list |
| `0002-commands.patch` | the target variable of a recipe run for its value file; a recipe line naming amk or make is recursive; a fatal signal reaches every spawned job |
| `0003-expand.patch` | the profiler times recursive variable expansion |
| `0004-file.patch` | the table of files is shared; a served child never removes intermediates |
| `0005-filedef.patch` | an imported target's fields on the file, the value a target keeps, the value kinds, and the goal reference type |
| `0006-function.patch` | builtin rows, the star builtin, handles, engine registration, the profiler around builtins and `call`, the argument count of `call` for `amk.args`, the bindings ledger, and the guest handle's call |
| `0007-job.patch` | the blocking wait, spawned children, halt, recipe events, the imported target's job, a kept recipe value's output, and each child's call pair and stdin pipe |
| `0008-job-h.patch` | a recipe child's call pair |
| `0009-load.patch` | a `load` line is amk's, since an ape cannot `dlopen`: the file goes to the engine that claims its extension, and is never rebuilt |
| `0010-main.patch` | the flags settled ahead of option decoding, the resident roles, the variables amk defines, the hooks around the parse and the goal run, the served child, usage and the banner, and die |
| `0011-makeint.patch` | whether this process is a served or spawned child |
| `0012-posixos.patch` | the jobserver's state as a ledger, make's own being one of them, with every verb taking the ledger; the wait serves call requests too |
| `0013-read.patch` | the prelude, the at line above a define, the remembered first-rule goal, the imported target's rule, and the `./` a load line keeps |
| `0014-mode.patch` | the event sites a mode listens on: the settled parse, a failed target before its deletion, and an imported target's job start |

## Overlays

A second series, applied after this one by naming its directory in `patch.dirs` with a
`flavor` for the build. An overlay is diffed against the tree this series leaves, not
against stock make, so it depends on the amk version and moves with it. An overlay written
against the older numbered series must be rebased onto this tree. Everything here stays as
it is: an overlay is the consumer's business, and a change it needs in the base belongs
upstream, in a module or a hook.

## The engine table

`src/amk/amk.h` declares a row: the builtin name, which is also the feature word and the
`--flag`, the multi-call names, the entry point, the argv shape, and the kept-state entries.
The table lives in `amk_engine.c`, and everything that asks which engines exist reads it:
the `$(name)` and `$(name.argv)` registration, `.FEATURES` and `.ENGINES`, the multi-call
dispatch, and `--list-engines`. Each row sits behind `#ifdef AMK_ENGINE_<NAME>`, and its
externs go in `amk.h`. The build passes a define per selected engine, so `without` needs no
change to the sources: the preprocessor decides what survives. Adding an engine means
adding that row alongside the four entries in the Makefile that name it.

## How a guest is hidden

Guests are hidden rather than renamed: each compiles with `-fvisibility=hidden`, its `main`
renamed to `<guest>_main` and marked visible, its `exit` renamed to `amk_exit`; its objects
partial-link into one relocatable, and `objcopy --localize-hidden` (Apple `ld -r` on its
own) leaves that one global. The guest's own executable cannot link this way and is not
wanted, so the guest build keeps going past it. Ticket 92985662e2 has the design.

Each of these guests departs from that recipe in one way:

- **Lua** has no main to rename. The guest build skips `lua.c` and `luac.c` and compiles
  `guest/lua_main.c`, where `lua_run_main` lives. Lua ships no configure, so its rule
  compiles the sources directly.
- **s7** is one translation unit with no main, so `guest/s7_main.c` supplies the only
  visible symbol. It builds with the C loader disabled, since that reaches for `dlopen`. Its
  entry hands a chunk a string port over its input instead of s7's own stdin, whose
  read-line keeps the newline and splits lines past 1023 bytes.
- **MicroPython** is a port, not a program. `guest/micropy.mk`, with `mpconfigport.h` and
  `mphalport.h`, lays it out the way `ports/unix` is, and `guest/micropy_main.c` holds the
  entry and the hal. The gc and non-local return go through `setjmp`, so one source serves
  both architectures. The unpack takes only the parts the build needs, and the version is
  passed in from the pin.
- **QuickJS** is a library plus a cli. The guest build skips `qjs.c`, `qjsc.c` and the
  generators and compiles `guest/js_main.c`, which binds the std and os modules as globals
  and runs a module chunk as a module. Its Makefile builds only programs, so its rule
  compiles the sources directly.
- **wasm3** builds the way its cosmopolitan script does: every file under `source` with the
  cli's `main.c`, the built-in wasi, static allocation and typed references, and compiles
  `guest/wasm_main.c`, the kept state over wasm3's embedding api. Its main and exit are
  handled like gawk's.

No guest tree is patched: a guest's own behaviour lives in its `guest/*_main.c` file.

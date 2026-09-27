# Patches

A numbered series applied to make 4.4.1 in order with GNU patch (`gpatch` on macOS) and `-p1 -l --fuzz=0`, by `make patch`.
Each file opens with a note on what it does, and a guest's exceptions are written on the
patch that adds that guest.

| patch | what it adds |
| --- | --- |
| `0001-socket-mode.patch` | resident dispatch: `--serve` and `--client`, with the cmsg layout block for Cosmopolitan on Darwin and the BSDs |
| `0002-builtins.patch` | the engine table with its awk and jq rows, the one dispatcher behind every `$(name)` and `$(name.argv)`, `.ENGINES`, and the pieces every engine shares |
| `0003-multicall.patch` | the names and flags read from the table, dispatched before option decoding, and `--list-engines` |
| `0004-load-noerror.patch` | `-load` answers that the object will never be rebuilt, since an ape cannot `dlopen` |
| `0005-lua.patch` | `$(lua)` |
| `0006-payload-boot.patch` | boot into a payload's entry script |
| `0007-s7.patch` | `$(s7)` |
| `0008-ape-unpack.patch` | `--ape-unpack`, one payload member copied out to the host |
| `0010-micropython.patch` | `$(micropy)` |
| `0011-wasm3.patch` | `$(wasm)` with its `.argv` companion, and the `wasm3` name and `--wasm` flag |
| `0012-payload-path.patch` | the payload's `bin/` tools unpacked to a cache and put first on `PATH` |
| `0013-bundle.patch` | `--bundle`, a copy of the binary with a makefile program as its default entry |
| `0014-output-trim.patch` | every builtin drops one trailing newline from its output |
| `0015-quickjs.patch` | `$(js)` |
| `0016-version.patch` | the second line of `--version` names amk, its version, the flavor and the engines, and `.AMK_VERSION` carries the version |
| `0017-usage.patch` | `--help` ends with the options amk adds: the engine flags from the table, the rest from one array a new flag joins |
| `0018-api-persistent.patch` | a persist entry on the row, and `$(name.persistent)` for every row that has one: the engine in this process against a state kept for its life; Lua takes it |
| `0019-api-hooks.patch` | the events make announces, the goal list and each recipe's start and end, and a hook entry on the row that hears them; Lua routes them to `amk.on` |
| `0020-api-spawn.patch` | a goal list run in a fork of this parsed image, and the wait that collects it even when make's own reaping saw it first; Lua exposes them as `amk.spawn` and `amk.wait` |
| `0021-api-signals.patch` | every spawned job a process group with make's fatal handlers of its own and no hold on a served request's connection: fatal signals forwarded, a running job swept at exit, the terminal handed to a foreground job and taken back, a stopped job reported; Lua adds the foreground option, `amk.kill` over the group and `amk.foreground` |
| `0022-api-init.patch` | one chunk per engine with a persist entry, from `AMK_<NAME>_INIT` or the payload's `__init__.<name>`, run in the persistent state before the makefiles are read |
| `0023-api-spawn-stdout.patch` | a spawned job's standard output to a file the caller names, so what a goal printed can be read once the job is collected |
| `0024-api-mail.patch` | a pipe from every spawned job to its parent, written by recipes through `AMK_MAIL` and by the job's guest, read whole by the parent once the job is collected |
| `0025-api-sink.patch` | an engine's persist entry writes to a sink make passes in, and a persistent call's sink appends straight into the expansion make is building: no temp file, no copy, no size limit |
| `0026-grammar-define-engine.patch` | `define.<engine> name` through `endef`: the define is stored as usual, and a phony target of that name hands the body to the engine and prints the result |
| `0027-api-var.patch` | the guest handle's make side: a variable read that tells undefined from empty, a predicate for whether make has built its tables, a variable write and an eval, and the queue that carries a forked guest's writes back to the parent |
| `0028-micropy-persistent.patch` | the micropy row gains persist and hook entries, so its persistent form, init chunk, and hooks run against one interpreter kept for the make process |

An `api` patch shapes what a guest sees of make: an entry on the engine row, an event, or a
call into make. The series before it fits make to guests; an api patch fits guests to make,
and its contract is the part a guest author reads. A `grammar` patch changes what a
makefile can say: a new directive or a new form of one, read by the parser itself.

## Overlays

A second series, applied after this one by naming its directory in `patch.dirs` with a
`flavor` for the build. The overlay is diffed against the tree this series leaves, not
against stock make, so it depends on the amk version and moves with it. Everything here
stays as it is: an overlay is the consumer's business, and a change it needs in the base
series belongs upstream as a patch of its own.

## The engine table

`src/amk.h` declares a row: the builtin name, which is also the feature word and the
`--flag`, the multi-call names, the entry point, and three bits for the argv shape. The
table lives in `function.c`, and everything that asks which engines exist reads it: the
`$(name)` and `$(name.argv)` registration, `.FEATURES` and `.ENGINES`, the multi-call
dispatch, and `--list-engines`. An engine's patch adds one row behind
`#ifdef AMK_ENGINE_<NAME>` and one extern in the header. The build passes a define per
selected engine, so `without` needs no change to the series: a patch always applies, and
the preprocessor decides what survives. Adding an engine means adding that row alongside
the four entries in the Makefile that name it.

## How a guest is hidden

Guests are hidden rather than renamed: each
compiles with `-fvisibility=hidden`, its `main` renamed to `<guest>_main` and marked
visible, its `exit` renamed to `amk_exit`; its objects partial-link into one
relocatable, and `objcopy --localize-hidden` (Apple `ld -r` on its own) leaves that
one global. The guest's own executable cannot link this way and is not wanted, so the
guest build keeps going past it. Ticket 92985662e2 has the design.

Lua, s7, MicroPython and QuickJS each depart from that recipe in one way, described on
their patch.

## Guest patches

A guest that needs a change of its own takes a series under `patches/<guest>/`, applied to
that guest's tree when it unpacks. Only wasm3 has one:

| patch | what it changes |
| --- | --- |
| `wasm3/0001-results-on-stdout.patch` | a called function's result prints on stdout, so a builtin expansion carries it, and the repl prompt appears only on a terminal |

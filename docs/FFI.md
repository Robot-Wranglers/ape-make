<a id="the-ffi"></a>

# The FFI

An engine is a guest linked into amk: a command line, and at most one of two kept-state
interfaces. The interface decides which builtins answer for the engine; every other
builtin name exists too, and stops make with an error naming the engine.

| interface | what a guest gives | engines |
| --- | --- | --- |
| [command line](#the-command-line) | an entry point and its argv shape | every engine |
| [state](#the-state-interface) | a kept state that runs code and lifts what it defines into make | lua, s7, micropy, js |
| [workspace](#the-workspace-interface) | a kept state that holds data, read and changed by programs | jq, sqlite |

The members of an interface are the verbs a makefile uses, by the same names. amk
implements each verb once over the members, and adds what every engine shares:
[namespaces](#namespaces), handles, backings, the [call channel](#calls-from-a-recipe),
and the refusals.

<a id="capabilities-by-engine"></a>

## Capabilities by Engine

| engine | aliases | command line | `.argv` | interface | optional members |
| --- | --- | --- | --- | --- | --- |
| [awk](../README.md#awk-jq) | `gawk` | yes | yes | - | |
| [wasm](../README.md#wasm) | `wasm3` | a module | yes | - | |
| [lua](../README.md#lua) | | yes | - | state | `hook` |
| [s7](../README.md#s7) | `lisp` | yes | - | state | `hook` |
| [micropy](../README.md#micropy) | | yes | - | state | `hook` |
| [js](../README.md#js) | | yes | - | state | `hook` |
| [jq](../README.md#awk-jq) | | yes | yes | workspace | `filter` |
| [sqlite](../README.md#sqlite) | `sqlite3` | yes, sqlite's own shell | yes | workspace | |

The rows live in `src/amk/amk_engine.c`. At startup `amk_engines_check` refuses a row
without a command line, with both interfaces, or missing a required member.

```Makefile
# each of these stops make, naming the engine and what it has
$(awk.ns w, create)          # awk has no state or workspace interface
x := $(sqlite.exec 1)        # sqlite has no such operation; one of get update load
$(lua.ns w, create)
y := $(w.get 1)              # lua has no such operation; one of exec import
```

<a id="the-command-line"></a>

## The command line

Every engine has one. It answers the builtin, an imported target's job, and the
multi-call names.

<a id="pass-by-value"></a>

### Pass by Value

| form | engines |
| --- | --- |
| `$(eng prog[, input])` | every engine; wasm takes a module |
| `$(eng.argv argv, prog[, input])` | awk, wasm, jq, sqlite |
| `$(eng.import.target target, prog[, flags])` | every engine but wasm |
| `@eng.import.target [flags]` above `define target` | every engine but wasm |

A workspace engine with a `filter` runs the plain form in the make process. Every other
call forks the engine's entry point. An imported target passes its flags ahead of the
program, so the engine's own options apply:

```Makefile
@jq.import.target --null-input --compact-output
define jq.events
  {level: "info"}, {level: "error"}
endef

@sqlite.import.target -json
define sq.sum
  .import --csv /dev/stdin t
  SELECT sum(v) AS total FROM t;
endef
```

<a id="defining-a-target-in-an-engine"></a>

#### Defining a target in an engine

`import.target` keeps the program as the variable `target` and makes `target` a rule
whose job runs it. Its output is the target's value, which another imported body
splices in as `@target@`.

<a id="pass-by-reference"></a>

### Pass by Reference

Every builtin has a star form whose arguments may name variables.

| form | engines |
| --- | --- |
| `$(eng* program_var[, input_var])` | every engine |
| `$(eng.argv* argv, program_var[, input_var])` | awk, wasm, jq, sqlite |
| `$(eng.import.target* program_var[, flags])` | every engine but wasm |
| `$(eng.ns* name, op, program_var)` | state and workspace engines |
| `$(name.op* program_var)` | state and workspace engines |

<a id="command-line"></a>

### Command line

| form | does |
| --- | --- |
| `amk --eng args...`, or the binary under an engine's name | runs that engine's command line |
| an alias, such as `lisp` for s7 | every form under that name too: `$(lisp ...)`, `$(lisp.exec ...)`, `@lisp.import`, `amk --lisp`, and the binary named `lisp`, all in the same engine and kept state |
| `amk --eng -` | reads the program from standard input |
| `amk --list-engines` | every engine as JSON, with its capabilities read from the build |

`amk --sqlite` is sqlite's own shell. After `--`, its database is in memory unless one
was named before it, and each argument may mix statements with dot commands.

<a id="namespaces"></a>

## Namespaces

A namespace is a named kept state, held by one engine for the life of the make process.
Every state and workspace engine has the namespace `main`; `create` makes another, with a
handle per operation.

| form | does |
| --- | --- |
| `$(eng.ns name, create)` | makes the namespace and its handles |
| `$(eng.ns name, op, prog)` | runs the operation in the namespace |
| `$(name.op prog)` | the same, through the handle |
| `$(eng.op prog)` | the operation in `main` |

A handle exists for every operation name; one the engine's interface lacks stops make.
A name belongs to the engine that created it, and another engine's `create` of it fails.
micropython has one heap, so it has `main` only.

<a id="persistent-state"></a>

### Persistent state

What one call leaves in a namespace, the next call finds:

```Makefile
$(lua.ns work, create)
$(work.exec x = 41)
answer := $(work.exec print(x + 1))
```

<a id="the-state-interface"></a>

## The state interface

| member | verb | does |
| --- | --- | --- |
| `kept.create` | `create` | a fresh state |
| `exec` | `exec` | runs code in the state, its output at the call's place |
| `import` | `import` | runs code, then lifts the functions and variables it defined into make |
| `hook`, optional | | hears every [event](#hooks) in `main` |

`$(eng.import prog)` and `@eng.import` above a define both run in `main`; the define's
name is only a carrier for its body.

<a id="init"></a>

### Init

Before the parse, each state engine runs one chunk in `main`, its output on stderr. The
chunk is `AMK_<ENGINE>_INIT`, as text or as `@path`; without it, the payload's
`__init__.<engine>`.

<a id="hooks"></a>

### Hooks

A state's `hook` hears `goals`, `recipe_start` and `recipe_end` in `main`. Each guest
subscribes through its handle:

```Makefile
$(lua.exec amk.on.goals = function(e) io.stderr:write("goals\n") end)
```

<a id="the-guest-handle"></a>

### The guest handle

| | lua | micropy | s7 | js |
| --- | --- | --- | --- | --- |
| read | `amk.var.CC`, `amk.var["a.b"]` | `amk.var.CC`, `amk.var["a.b"]` | `(amk-var 'CC)`, `(amk-var "a.b")` | `amk.var.CC`, `amk.var["a.b"]` |
| write | `amk.var.CC = "cc"` | `amk.var.CC = "cc"` | `(set! (amk-var 'CC) "cc")` | `amk.var.CC = "cc"` |
| read raw | `amk.var.raw.CC` | `amk.var.raw.CC` | `((amk-var 'raw) 'CC)` | `amk.var.raw.CC` |
| write raw | `amk.var.raw.CC = "$(cc)"` | `amk.var.raw.CC = "$(cc)"` | `(set! ((amk-var 'raw) 'CC) "$(cc)")` | `amk.var.raw.CC = "$(cc)"` |
| expand | `amk.expand(text)` | `amk.expand(text)` | `(amk-expand text)` | `amk.expand(text)` |
| eval | `amk.eval(text)` | `amk.eval(text)` | `(amk-eval text)` | `amk.eval(text)` |
| call | `amk.call(name, ...)` | `amk.call(name, *values)` | `(amk-call 'name value ...)` | `amk.call(name, ...values)` |
| acall | `amk.acall(name, ...)`, a handle with `pid`, `fd`, and `result()` | `await amk.acall(name, *values)` | `(amk-call-begin 'name value ...)` answers `(pid fd)`, `(amk-call-end pid)` collects | `await amk.acall(name, ...values)` |
| define a function | `amk.func(name, fn)` | `amk.func(name, fn)` | `(amk-func 'name fn)` | `amk.func(name, fn)` |
| events | `amk.on[event]` | `amk.on[event]` | `(amk-on 'event)` | `amk.on[event]` |
| undefined | `nil` | `None` | `#f` | `undefined` |

A raw read returns the text as stored, never expanded, and a raw write defines a recursive
variable, as a define does; `amk.var` expands on read and stores its value literally.

lua's handle also has `amk.spawn`, `amk.wait`, `amk.kill`, `amk.foreground`, `amk.send` and
`amk.exit_code`.

```Makefile
CC := clang
flags = -O2 $(EXTRA)

# reads and expansion, from a one-shot call: clang, -O2, and 3
seen := $(lua print(amk.var.CC, amk.expand("$$(strip $$(flags))"), amk.expand("$$(words a b c)")))

# a write from a one-shot call lands once the call returns, so the next line sees it
$(micropy import amk; amk.var.EXTRA = "-g"; amk.eval("debug: ; @echo $$(flags)"))
now := $(flags)
```

```Makefile
pair = [$1|$2]

# [x,y|$(shell id)], with nothing run: both values arrive whole
both := $(micropy import amk; print(amk.call("pair", "x,y", "$$(shell id)")))

# a;b, from the builtin with a comma in a value
swapped := $(lua print(amk.call("subst", ",", ";", "a,b")))
```

<a id="registering-make-functions"></a>

### Registering make functions

A function a guest defines with `amk.func`, or one `import` lifts, becomes a make
function that answers in the state that defined it:

```Makefile
@lua.import
define lua.methods
  function add(a, b) return a + b end
endef

@js.import
define js.methods
  function shout(s) { return s + "!"; }
endef

sum := $(add 1,2)
loud := $(shout hi)
```

<a id="the-workspace-interface"></a>

## The workspace interface

| member | verb | does |
| --- | --- | --- |
| `kept.create` | `create` | a fresh, empty state |
| `get` | `get` | runs a program over the state and prints its output; the state is left as it was |
| `update` | `update` | runs a program that may change the state |
| `load` | `load` | replaces the whole state with a text, all or nothing |
| `dump` | `dump` | prints the whole state as the text `load` takes back |
| `filter`, optional | `filter` | runs a program over an input text, with no state |

Every output is a sequence of lines, which the call channel counts. A workspace can be
seeded by `import`, kept in a file by a backing, and reached from a recipe.

| form | does |
| --- | --- |
| `$(eng.import name, text)`, `@eng.import` above `define name` | creates `name` with its handles and loads the text; importing again replaces it |
| `$(eng.ns name, create, run)` | the default: the state lives in the make process alone |
| `$(eng.ns name, create, owned path)` | loads the file at first use, writes it after every `update` and `load` |
| `$(eng.ns name, create, shared path)` | also reloads the file whenever it changed since the last load |

```Makefile
$(sqlite.ns edges, create, owned edges.sql)
$(edges.update CREATE TABLE IF NOT EXISTS e(a, b))
```

<a id="jq-workspaces"></a>

### jq workspaces

The state is one JSON value.

| verb | runs | stores | prints |
| --- | --- | --- | --- |
| `get prog` | `prog` over the value | nothing | every output |
| `update prog` | `prog` over the value | the first output | the rest |
| `load text` | | the one JSON text, once it parses | nothing |
| `dump` | `.` | nothing | the value |

```Makefile
# a stack in a workspace: push, then pop the top and keep the rest
$(jq.ns stack, create)
seed  := $(stack.update [1] + [2])
push  := $(stack.update --argjson v 3 . + [$$v])
pop   := $(stack.update .[:-1], .[-1])
depth := $(stack.get length)
# a string output printed bare
$(jq.ns who, create)
name := $(who.update {"name": "a b"})
who  := $(who.get -r .name)
```

<a id="sqlite-workspaces"></a>

### sqlite workspaces

The state is one in-memory database. A program is one or more statements, and each
result row prints as a JSON object on a line. `--arg name value` binds `:name` as text;
`--argjson name json` binds the value its JSON names.

| verb | runs | prints |
| --- | --- | --- |
| `get prog` | the statements; one that writes is refused | each row |
| `update prog` | the statements, writes included | each row |
| `load text` | drops every table, view and trigger, then replays the text, in one transaction | nothing |
| `dump` | | schema and rows, as statements |

```Makefile
@sqlite.import
define edges
  CREATE TABLE e(a INTEGER, b INTEGER);
  INSERT INTO e VALUES(1,2),(2,3),(3,1);
endef

seen := $(edges.get WITH RECURSIVE r(x) AS (SELECT 1 UNION SELECT b FROM e, r WHERE a = x) SELECT json_group_array(x) AS seen FROM r)
$(edges.update --arg a 3 INSERT INTO e VALUES(:a, 4))
```

<a id="calls-from-a-recipe"></a>

### Calls from a recipe

A recipe reaches the make process's workspaces through a descriptor pair, `AMK_CALL` for
requests and `AMK_REPLY` for answers. A request is one line, `op name program`; the reply
is `status count`, then `count` lines of output. A sub-make forwards to its caller's pair,
so a run has one set of workspaces.

| request | does |
| --- | --- |
| `get name prog`, `update name prog` | the verb in the namespace, made on first use |
| `create name backing` | declares the namespace's backing |
| `load name path` | loads the file's text |
| `dump name` | prints the whole state |
| `filter engine count prog` | the engine's `filter`, over the `count` lines after the request; an engine without one is refused by name |
| `halt` | no more recipe lines or goals; make exits 112 |

`source amk.sh` in a recipe gives shell helpers over the pair:

| helper | does |
| --- | --- |
| `amk.call 'line' [input...]` | one request; prints the output, returns the status |
| `amk.ns op name [options] -- prog` | one operation, a bound value quoted for the line |
| `amk.words args...` | quotes words for a request line |
| `amk.filter engine [options] prog` | `filter` over standard input, in the named engine |
| `jq.pipe [options] prog` | `amk.filter jq` |

```Makefile
SHELL := bash
$(sqlite.ns D, create)
count:
	@source amk.sh; amk.ns update D -- 'CREATE TABLE t(k); INSERT INTO t VALUES(1)'
	@source amk.sh; amk.ns get D -- 'SELECT count(*) AS n FROM t'
```

<a id="reflection"></a>

## Reflection

| variable | holds |
| --- | --- |
| `.FEATURES`, `.ENGINES` | amk's features, and the engines in this build |
| `.AMK_VERSION`, `<engine>.__version__` | amk's version, and each engine's |
| `<engine>.__fxns__`, `<engine>.__vars__` | the functions and variables that engine gave make |
| `amk.__fxns__`, `amk.__vars__` | the same for every engine |

```Makefile
# the functions lua and js gave make, either way
methods := $(amk.fxns? lua, js)
methods := $(amk.fxns? lua js)
```

<a id="reference"></a>

## Reference

Where each part of the FFI lives. Modules are under `src/amk/`; a hook patch is under
`patches/` and holds the code that must read one of make's own statics.

| form | module |
| --- | --- |
| the engine rows, `amk_engines_check`, `$(eng ...)`, `.argv`, init, hooks | `amk_engine.c` |
| namespaces, handles, workspace verbs, backings, `import`, the refusals | `amk_workspace.c` |
| `$(eng.import.target ...)` | `amk_workspace.c`, with its rule in `0013-read.patch` and its job in `0007-job.patch` |
| registering the builtins, the star forms | `0006-function.patch` |
| `@builtin` above `define`, the prelude, `AMK_NO_PRELUDE` | `0013-read.patch` |
| `@name@` in an imported body | `amk_goal.c` |
| the guest handle, `$(goal name)`, `$(amk.stdin text)` | `amk_guest.c` |
| `AMK_CALL`, `AMK_REPLY`, forwarding, `halt` | `amk_chan.c` |
| `amk.spawn`, `amk.wait`, `amk.kill`, `amk.foreground`, `AMK_MAIL` | `amk_spawn.c` |
| `--serve`, `--client` | `amk_serve.c` |
| `--bundle`, `--ape-unpack`, `--ape-list` | `amk_payload.c` |
| multi-call names, `--list-engines`, `--version`, `--help`, `__main__` | `0010-main.patch`, `amk_engine.c` |
| `$(amk.require ...)`, `$(amk.sys ...)`, `$(amk.dedent ...)`, `$(cksum ...)`, `$(amk.match ...)` | `amk_builtins.c` |
| `$(amk.fxns? ...)`, `$(amk.vars? ...)` | `amk_engine.c` |
| each guest's members | `guest/<engine>_main.c` |

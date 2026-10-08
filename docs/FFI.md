# The FFI

## Calling a guest from make

### Pass by Value

| form | [awk](../README.md#awk-jq) | [jq](../README.md#awk-jq) | [lua](../README.md#lua) | [s7](../README.md#s7) | [micropy](../README.md#micropy) | [js](../README.md#js) | [wasm](../README.md#wasm) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `$(eng prog[, input])` | yes | yes | yes | yes | yes | yes | module |
| `$(eng.argv argv, prog[, input])` | yes | yes | - | - | - | - | yes |
| `$(eng.exec prog)` | - | - | yes | yes | yes | yes | - |
| `$(eng.import prog)` | - | - | yes | yes | yes | yes | - |
| `$(eng.import.target prog)` | yes | yes | yes | yes | yes | yes | - |
| `$(eng.ns workspace, op[, prog])` | - | yes | yes | yes | yes | yes | - |
| `$(workspace.<op> prog)` | - | yes | yes | yes | yes | yes | - |
| `$(jq.get prog)`, `$(jq.update prog)` | - | yes | - | - | - | - | - |
| `$(jq.load text)` | - | yes | - | - | - | - | - |

### Pass by Reference

| form | [awk](../README.md#awk-jq) | [jq](../README.md#awk-jq) | [lua](../README.md#lua) | [s7](../README.md#s7) | [micropy](../README.md#micropy) | [js](../README.md#js) | [wasm](../README.md#wasm) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `$(eng* program_var[, input_var])` | yes | yes | yes | yes | yes | yes | yes |
| `$(eng.argv* argv, program_var[, input_var])` | yes | yes | - | - | - | - | yes |
| `$(eng.exec* program_var)` | - | - | yes | yes | yes | yes | - |
| `$(eng.import* program_var)` | - | - | yes | yes | yes | yes | - |
| `$(eng.import.target* program_var)` | yes | yes | yes | yes | yes | yes | - |
| `$(eng.ns* workspace, op, program_var)` | - | yes | yes | yes | yes | yes | - |
| `$(workspace.<op>* program_var)` | - | yes | yes | yes | yes | yes | - |
| `$(jq.get* program_var)`, `$(jq.update* program_var)` | - | yes | - | - | - | - | - |
| `$(jq.load* text_var)` | - | yes | - | - | - | - | - |

### Persistent state

### The jq store

| call | runs | stores | returns |
| --- | --- | --- | --- |
| `$(workspace.get prog)` | prog over the value | nothing | every output |
| `$(workspace.update prog)` | prog over the value | the first output | the rest |
| `$(workspace.load text)` | | the one JSON text | nothing |

```Makefile
# a stack in the store: push, then pop the top and keep the rest
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

### Init

#### Defining a target in an engine

### Calls from a recipe

## Calling make from a guest

### The guest handle

| | lua | micropy | s7 | js |
| --- | --- | --- | --- | --- |
| read | `amk.var.CC`, `amk.var["a.b"]` | `amk.var.CC`, `amk.var["a.b"]` | `(amk-var 'CC)`, `(amk-var "a.b")` | `amk.var.CC`, `amk.var["a.b"]` |
| write | `amk.var.CC = "cc"` | `amk.var.CC = "cc"` | `(set! (amk-var 'CC) "cc")` | `amk.var.CC = "cc"` |
| expand | `amk.expand(text)` | `amk.expand(text)` | `(amk-expand text)` | `amk.expand(text)` |
| eval | `amk.eval(text)` | `amk.eval(text)` | `(amk-eval text)` | `amk.eval(text)` |
| call | `amk.call(name, ...)` | `amk.call(name, *values)` | `(amk-call 'name value ...)` | `amk.call(name, ...values)` |
| acall | `amk.acall(name, ...)`, a handle with `pid`, `fd`, and `result()` | `await amk.acall(name, *values)` | `(amk-call-begin 'name value ...)` answers `(pid fd)`, `(amk-call-end pid)` collects | `await amk.acall(name, ...values)` |
| undefined | `nil` | `None` | `#f` | `undefined` |

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

### Registering make functions

## Reflection

### Capabilities by Engine

| engine | [`$(name ...)`](#builtins) | [`.argv`](#builtins) | [`.import.target`](#defining-a-target-in-an-engine) | [`.exec`](#persistent-state) | [init](#init) | [hooks](#hooks) | [handle reads](#the-guest-handle) | [handle writes](#the-guest-handle) | [`amk.func`](#registering-make-functions) | [`.import`](#registering-make-functions) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [awk](../README.md#awk-jq) | yes | yes | yes | - | - | - | - | - | - | - |
| [jq](../README.md#awk-jq) | yes | yes | yes | store | yes | - | - | - | - | - |
| [lua](../README.md#lua) | yes | - | yes | yes | yes | yes | yes | yes | yes | yes |
| [s7](../README.md#s7) | yes | - | yes | yes | yes | yes | yes | yes | yes | yes |
| [micropy](../README.md#micropy) | yes | - | yes | yes | yes | yes | yes | yes | yes | yes |
| [js](../README.md#js) | yes | - | yes | yes | yes | yes | yes | yes | yes | yes |
| [wasm](../README.md#wasm) | module | yes | - | - | - | - | - | - | - | - |

### Functions and variables from guests

```Makefile
@lua.import
define lua.methods
  function add(a, b) return a + b end
endef

@js.import
define js.methods
  function shout(s) { return s + "!"; }
endef

# add shout, either way
methods := $(amk.fxns? lua, js)
methods := $(amk.fxns? lua js)
```

| variable | holds |
| --- | --- |
| `<engine_name>.__fxns__` | the functions that engine gave make |
| `<engine_name>.__vars__` | the variables that engine gave make |
| `amk.__fxns__` | `$(amk.fxns? $(.ENGINES))`, every engine's functions |
| `amk.__vars__` | `$(amk.vars? $(.ENGINES))`, every engine's variables |

## Events

### Hooks

## Engine API

### Builtins

| form | direction | engines | patch |
| --- | --- | --- | --- |
| `$(<engine_name> prog[,input])` | make to guest | all; wasm takes a module | [0002] |
| `$(<engine_name>.argv args...)` | make to guest | awk, jq, wasm | [0002], [0011] |
| `$(<builtin>* args...)` | make to guest | every engine builtin | [0038], [0057] |
| `$(<engine_name>.exec prog)`, `$(<engine_name>.ns workspace, op[, prog])`, `$(workspace.<op> prog)` | make to guest | lua, s7, micropy, js | [0018], [0028], [0030], [0031], [0063] |
| `$(jq.<op> prog)`, `$(jq.ns workspace, op[, prog])`, `$(workspace.<op> prog)` | make to guest | jq: `get`, `update`, `load` | [0046], [0063] |
| `$(<engine_name>.import prog)` | guest to make | lua, s7, micropy, js | [0029] |
| `$(goal name)` | make | any | [0032] |
| `$(amk.stdin text)` | make to recipe | any | [0033] |
| `$(amk.require names...)` | make | any | [0036] |
| `$(amk.dedent text)`, `$(amk.val.dedent var)`, `$(amk.dedent* var)` | make | any | [0037], [0038] |
| `$(amk.fxns? engines...)`, `$(amk.vars? engines...)` | make | lua, s7, micropy, js | [0040], [0059] |
| `$(cksum text)`, `$(cksum.hex text)`, `$(cksum.file path)`, `$(cksum.file.hex path)`, `$(cksum* var)`, `$(cksum.hex* var)` | make | any | [0067] |
| `$(amk.sys name)` | make | any | [0068] |
| `$(amk.match re,text)`, `$(amk.match.file re,path)`, `$(amk.match* re, var)` | make | any | [0069] |

### Grammar

| form | direction | engines | patch |
| --- | --- | --- | --- |
| `@<engine_name>.import.target` above `define` | make to guest | all | [0039], [0042], [0044] |
| `@name@` in an imported body | goal to guest | all | [0043] |
| `__main__` target | make | any | [0035] |

### Variables

| form | direction | engines | patch |
| --- | --- | --- | --- |
| `.FEATURES`, `.ENGINES` | make | all | [0002] |
| `.AMK_VERSION`, `<engine_name>.__version__` | make | all | [0016], [0045] |
| `<engine_name>.__fxns__`, `<engine_name>.__vars__`, `amk.__fxns__`, `amk.__vars__` | make | lua, s7, micropy, js | [0040] |

### Guest handle

| form | direction | engines | patch |
| --- | --- | --- | --- |
| `amk.var` read and write | guest to make | lua, s7, micropy, js | [0027] |
| `amk.expand` | guest to make | lua, s7, micropy, js | [0027] |
| `amk.eval` | guest to make | lua, s7, micropy, js | [0027] |
| `amk.call(name, values...)` | guest to make | lua, s7, micropy, js | [0058] |
| `amk.acall(name, values...)`: the call in a fork, collected through the guest's own reactor | guest to make | lua, s7, micropy, js | [0061] |
| `amk.func` | guest to make | lua, s7, micropy, js | [0018] |
| `amk.on`: `goals`, `recipe_start`, `recipe_end` | make to guest | lua, s7, micropy, js | [0019] |
| `amk.spawn(goals[, opts])` | guest to make | lua | [0020], [0023] |
| `amk.wait([pid[, block]])` | guest to make | lua | [0020], [0024] |
| `amk.kill`, `amk.foreground` | guest to make | lua | [0021] |
| `amk.send(text)` | job to parent | lua | [0024] |
| `amk.exit_code(n)` | guest to make | lua | [0050] |

### Recipe environment and init

| form | direction | engines | patch |
| --- | --- | --- | --- |
| `AMK_MAIL` | job to parent | any | [0024] |
| `AMK_CALL`, `AMK_REPLY`, `amk.call`, `amk.words`, `jq.pipe` | recipe to make | jq store | [0047] |
| a pair per recipe child; a served request forwards up its caller's pair | recipe to make | jq store | [0062], [0065] |
| `halt` on the call channel: no more recipe lines or goals, status 112, taken up by a parent make | recipe to make | any | [0064] |
| `AMK_<ENGINE_NAME>_INIT`, `__init__.<engine_name>` | make to guest | jq, lua, s7, micropy, js | [0022] |
| `__init__.mk`, `AMK_NO_PRELUDE` | make | any | [0034] |

### Command line

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
[0033]: ../patches/0033-api-amk-stdin.patch
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
[0057]: ../patches/0057-star-args.patch
[0058]: ../patches/0058-api-handle-call.patch
[0059]: ../patches/0059-bindings-args.patch
[0061]: ../patches/0061-api-acall.patch
[0062]: ../patches/0062-call-pairs.patch
[0063]: ../patches/0063-api-namespace.patch
[0064]: ../patches/0064-api-halt.patch
[0065]: ../patches/0065-served-request-forwards.patch
[0067]: ../patches/0067-api-cksum.patch
[0068]: ../patches/0068-api-sys.patch
[0069]: ../patches/0069-api-match.patch

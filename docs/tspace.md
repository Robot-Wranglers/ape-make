<!-- header # tuple-space "`mod :: amk.tspace`" | Concepts #concepts | Syntax #syntax | Strategy #strategy | API #api | Usage #usage | Fields #fields | Errors #errors | Demos #demos | Refs #references | Schema #schema -->
<h1><a id="tuple-space"></a><a href="../README.md#module-index"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-tspace.tuple-space.up.dark.svg"><img src="img/hdr/docs-tspace.tuple-space.up.svg" alt="up to the module index"></picture></a><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-tspace.tuple-space.title.dark.svg"><img src="img/hdr/docs-tspace.tuple-space.title.svg" alt="mod :: amk.tspace"></picture><a href="#schema"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-tspace.tuple-space.9.dark.svg"><img align=right src="img/hdr/docs-tspace.tuple-space.9.svg" alt="Schema"></picture></a><a href="#references"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-tspace.tuple-space.8.dark.svg"><img align=right src="img/hdr/docs-tspace.tuple-space.8.svg" alt="Refs"></picture></a><a href="#demos"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-tspace.tuple-space.7.dark.svg"><img align=right src="img/hdr/docs-tspace.tuple-space.7.svg" alt="Demos"></picture></a><a href="#errors"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-tspace.tuple-space.6.dark.svg"><img align=right src="img/hdr/docs-tspace.tuple-space.6.svg" alt="Errors"></picture></a><a href="#fields"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-tspace.tuple-space.5.dark.svg"><img align=right src="img/hdr/docs-tspace.tuple-space.5.svg" alt="Fields"></picture></a><a href="#usage"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-tspace.tuple-space.4.dark.svg"><img align=right src="img/hdr/docs-tspace.tuple-space.4.svg" alt="Usage"></picture></a><a href="#api"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-tspace.tuple-space.3.dark.svg"><img align=right src="img/hdr/docs-tspace.tuple-space.3.svg" alt="API"></picture></a><a href="#strategy"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-tspace.tuple-space.2.dark.svg"><img align=right src="img/hdr/docs-tspace.tuple-space.2.svg" alt="Strategy"></picture></a><a href="#syntax"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-tspace.tuple-space.1.dark.svg"><img align=right src="img/hdr/docs-tspace.tuple-space.1.svg" alt="Syntax"></picture></a><a href="#concepts"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-tspace.tuple-space.0.dark.svg"><img align=right src="img/hdr/docs-tspace.tuple-space.0.svg" alt="Concepts"></picture></a><br clear="all"></h1>
<!-- /header -->

<a id="overview"></a>
Tuplespaces are a kind of "shared blackboard" where the usual idea is pattern-matching over typed data, safe concurrent reads/writes, decent helpers for things like uniform random samples, and so on.

For `amk` tuplespaces are implemented on top of an in-process [sqlite workspace](data-engines.md#sqlite-workspaces), , describing a [stacked engine](FFI.md#stacked-engines) built on a [data-engine](data-engines.md).  It's .  Indirectly tuplespaces are also the backbone of the [reactor model](runtime.md#tuplespace-reactor) that's available as a runtime [concurrency flavor](runtime.md).  Like the backing store, [in-memory](#usage-basic) is default but [filesystem-backed](#usage-filesystem) is another option.

Tuplespaces in `amk` support a standard instruction set of [CRUD and other operations](#verbs), including things like uniform random sampling, but also [pattern-matching dispatch](#routed-bound-workers) with guest-handlers bound to the space.  Besides turning any space into an event-loop / reactor pattern, tuplespaces can be used with other concurrency models.  See the [actors example here](#usage-actors).

All of that works from the host, from every guest language, and from any recipes/targets with more or less [the same interface](#verbs)

Some references: Linda[^linda], TuCSoN, and its ReSpecT language[^respect] for spaces with pattern-matching reflexes.  Schmidt's Reactor pattern[^reactor], for handlers registered against events and dispatched by one demultiplexer.

{# A space is an sqlite workspace holding the tuple schema. Including the library makes the
default space, `tuplespace`, and `tspace` is its verbs. `tspace.create` makes another, with
any backing the workspace takes, and promotes its verbs under its name. #}

A world ticks the sky through a day, and two sailors watch the same sky. Each is a
[reflex](#reflexes) in its own guest: the world takes each `tick` tuple and puts that
tick's sky and the next tick. The space's reflexes are [shared](#strategy), so every sky
reaches both sailors, and each keeps a feeling of its own between skies. The space is
seeded with the first tick, and `SKY.__main__` runs it: every stored tuple a reflex
matches goes to its reflexes, which is all `__main__` needs.

```Makefile
load tspace

@tspace
define SKY
  { "strategy": { "reflexes": "shared" }, "seed": [["tick", 1]] }
endef

__main__: SKY.__main__

# The world: each tick puts its sky, then the next tick, until nightfall.
@SKY.reflex/js (tick, t=int)
define world
  const days = [["blue", "morning"], ["red", "morning"], ["grey", "noon"],
                ["red", "night"], ["blue", "night"]];
  if (t > days.length) return;
  const [colour, when] = days[t - 1];
  print(`tick ${t}: a ${colour} sky at ${when}`);
  SKY.out("sky", t, colour, when);
  SKY.out("tick", t + 1);
endef

# A sailor who starts out alert, in lua.
@SKY.reflex/lua (sky, t=int, colour=str, when=str)
define sailor1
  mood1 = mood1 or "alert"
  if colour == "red" and when == "morning" then mood1 = "alert" end
  if colour == "red" and when == "night" then mood1 = "relaxed" end
  print("  sailor1 is feeling " .. mood1)
endef

# A sailor who starts out relaxed, in micropy.
@SKY.reflex/micropy (sky, t=int, colour=str, when=str)
define sailor2
  global mood2
  try:
    mood2
  except NameError:
    mood2 = "relaxed"
  if colour == "red":
    mood2 = {"morning": "alert", "night": "relaxed"}.get(when, mood2)
  print("  sailor2 is feeling " + mood2)
endef
```

```
tick 1: a blue sky at morning
  sailor1 is feeling alert
  sailor2 is feeling relaxed
tick 2: a red sky at morning
  sailor1 is feeling alert
  sailor2 is feeling alert
tick 3: a grey sky at noon
  sailor1 is feeling alert
  sailor2 is feeling alert
tick 4: a red sky at night
  sailor1 is feeling relaxed
  sailor2 is feeling relaxed
tick 5: a blue sky at night
  sailor1 is feeling relaxed
  sailor2 is feeling relaxed
```

<a id="concepts"></a>

## Concepts

| Term | Meaning |
| --- | --- |
| Tuple | an ordered list of json values, stored in a space |
| Actual | a concrete value in a field; every field `out` takes is one, see [actuals](#actuals) |
| Formal | a typed placeholder, `?int` and the like, that only a pattern may hold, see [formals](#formals) |
| Pattern | a tuple of actuals and formals; it matches tuples of the same length whose fields it matches |
| Space | an sqlite [workspace](data-engines.md#sqlite-workspaces) holding the tuple schema, made by `@tspace` or `tspace.create`, see [declaring a space](#syntax) |
| `tuplespace` | the default space, made when the library loads, whose verbs are `tspace`, see [`@tspace.target`](#syntax) |
| Owner | the process that parsed the makefile; it holds every space |
| Forwarder | any process that inherited a live ask channel from the owner, and sends every request up, see [blocking verbs](#blocking) |
| Handler | a make function bound to a space and a pattern, which takes the `out`s that match it, see [the reactor](#routed-bound-workers) |
| Reflex | a handler declared by `@<space>.reflex/<engine> (<fields...>)` above a define, see [reflexes](#reflexes) |
| Version | a counter each change to a space moves, which `wait` blocks on |

<a id="syntax"></a>
<a id="engine-api"></a>

## Syntax

`tspace` is a [stacked engine](FFI.md#stacked-engines) of the data variety, and its forms
follow the [data engines](data-engines.md) where they can; the [FFI](FFI.md) covers engine
APIs in general. This one has two layers: decorators that declare a space and attach code
to it, shown here, and the make functions underneath them, cataloged under [API](#api).

The typical case declares a space with `@tspace` above a define named after it. The body is
json: `seed` is a json array of tuples, `strategy` is how its reflexes route, see
[strategy](#strategy), and every other key is the [backing](data-engines.md#backings). The body
is expanded first, so a value can name a make variable, and an empty body makes an empty
space in memory.

A seed is written only by the create that makes the space. A space that already exists,
such as a file from an earlier run, is never reseeded, so the seed is safe to leave in place.
A seed is stored before any reflex exists, so it routes nowhere until the space runs: the
target `<space>.__main__` routes every stored tuple a reflex matches, oldest first. Each
space then gets decorators of its own:

```Makefile
# declare a space: its backing and seed, as json
@tspace
define jobs
  {"owned": "$(JOBS_DB)", "seed": [["job", 1], ["job", 2]]}
endef

# a guest import with the space bound by name; lifts count_jobs into make
@jobs.lua
define jobs_lib
  function count_jobs() return #jobs.read("job", "integer") end
endef

# a shell target whose recipe has every space's verbs
@jobs.amk
define fill
  jobs.out job 3
endef

# a guest target with the space bound by name
@jobs.micropy.target: fill
define report
  print("jobs:", len(jobs.read("job", int)))
endef

# a target that runs its body as SQL on the default space
@tspace.target
define tally
  SELECT count(*) AS n FROM tspace
endef
```

The guest forms, `@<space>.<engine>` and `@<space>.<engine>.target`, exist for lua,
micropy, js and s7, for every space, the default `tuplespace` included. The binding is the
guest's handle, as `amk.tspace[name]` answers it:

| Engine | Bound As |
| --- | --- |
| lua | a local, `local SHOP = amk.tspace["SHOP"]` |
| micropy | a global, after `import amk` |
| js | a property of `globalThis` that import does not lift |
| s7 | `(define SHOP (amk-tspace-on "SHOP"))` |

<a id="handlers"></a>
<a id="reflexes"></a>

### Reflexes

A reflex is a handler declared by decorator: a body that runs once for each tuple its
pattern matches.

```Makefile
@shop.reflex/lua (order, item=str, qty=int)
define price
  shop.out("priced", item, qty, qty * 3)
endef
```

| # | Signature | Does |
| --- | --- | --- |
| B1 | `@<space>.reflex/<engine> (<field...>) [: prereqs]` above `define <name>` | Compiles the define as the body of the make function `<name>` in the engine, then registers it for the pattern the fields spell; the fields are under [fields](#fields-in-a-decorator). `tspace.create` makes one for every space; lua, js, s7 and micropy compile, `amk` makes the define a make function that takes the tuple by position, and every other engine is refused. |
| B2 | the body | Runs once per routed tuple, in the engine of B1, with the space's handle under the space's own name and each named field as a parameter. Its helpers are its own locals, so nothing else reaches make. |

The engine follows a slash, outside the pattern, and the parentheses hold only the pattern's
fields; they and the commas are optional, so `@shop.reflex/lua order item=str qty=int` is
the same reflex. The engine may also be the first positional, `@shop.reflex lua (...)`; see
[decorator arguments](grammar.md#decorator-arguments). B1 refuses a missing engine, an engine that cannot compile a reflex, a type
outside the field types, a field named after its space, and a field name used twice.

<a id="strategy"></a>

## Strategy

A space's strategy says how its reflexes route. With `reflexes` set to `exclusive`, the
default, a reflex is the only destination of the tuples it matches, so a second reflex whose
pattern overlaps it is refused. With `shared`, reflexes may overlap, and a matching tuple
calls every one of them, in the order they were declared:

```Makefile
@tspace
define SKY
  { "strategy": { "reflexes": "shared" } }
endef

@SKY.reflex/lua (sky, t=int, colour=str, when=str)
define sailor1
  print("sailor1 sees a " .. colour .. " sky")
endef

@SKY.reflex/micropy (sky, t=int, colour=str, when=str)
define sailor2
  print("sailor2 sees a " + colour + " sky")
endef
```

| Form | Strategy |
| --- | --- |
| `{ "strategy": { "reflexes": "shared" } }` in an `@tspace` body | shared, beside `seed` and the backing keys |
| `$(tspace.create SKY, reflexes=shared)` | the same, as an option beside the backing's |
| Neither | exclusive |

The space records its strategy, so a file-backed space keeps the one it was last declared
with. `reflexes` is the one axis, and its values are `exclusive` and `shared`; anything else
is refused. A space whose name is not an identifier in the
engine cannot be bound.

<a id="api"></a>

## API

<a id="spaces"></a>

### Spaces and Handles

| Caller | Default Space | Named Space |
| --- | --- | --- |
| make | `$(tspace read, k, ?int)` | `$(jobs.read k, ?int)` |
| Recipe | `tspace read k ?int` | `jobs.read k ?int` |
| lua, micropy, js | `amk.tspace.read(...)` | `amk.tspace["jobs"].read(...)`, or `amk.tspace.on("jobs")` |
| s7 | `(amk-tspace-read ...)` | `((amk-tspace-on "jobs") 'read ...)` |

In lua, micropy and js, `amk.tspace[name]` is the handle of a named space, the same object
`on(name)` answers, so it can be kept in a variable or used in place. A handle indexes the
same way, so `jobs["done"]` is the `done` space. A field a handle lacks is the make function
of that name under `tspace`, so `amk.tspace.create("jobs")` and `amk.tspace.version("jobs")`
reach `tspace.create` and `tspace.version`. Creating a space belongs in the makefile, in the
owner. A `create` from a forwarder makes the space in the owner, but its verbs only in the
forwarder that made it, so no other process reaches it through a handle.

A space made from a file keeps its tuples across runs; the schema is applied only where it
is missing.

<a id="api-make"></a>

### make

Under the decorators is the low-level API, plain make functions. Every space is also an
sqlite [workspace](data-engines.md#sqlite-workspaces), so it answers the workspace handles as well
as the tuple verbs:

| # | Form | Does |
| --- | --- | --- |
| L1 | `$(tspace.create name[, backing[, seed]])` | Makes the space, as `@tspace` does, from its arguments |
| L2 | `$(tspace <verb>, fields...)` | One [verb](#operations) on the default space, `tuplespace` |
| L3 | `$(<space>.<verb> fields...)` | One verb on a named space |
| L4 | `$(tspace.exec name, sql)` | Runs the SQL against the space's store and answers its rows, one json object per line |
| L5 | `$(<space>.get sql)`, `$(<space>.update sql)` | The workspace handles: SQL that reads, or SQL that writes and moves the version |
| L6 | `$(<space>.get* var)`, `$(<space>.update* var)` | The same, with the SQL taken from the variable `var` |
| L7 | `$(<space>.load sql)`, `$(<space>.load* var)` | Replaces the whole store with the statements, the tuple schema included |
| L8 | `$(tspace.version name)` | The space's version, moved by each change |
| L9 | `$(tspace.wait name, version)` | The version, once it is past the one given; from a recipe or guest only |
| L10 | `${tspace.sh}` | The recipe side: a shell function per space and verb, over the ask channel |

Each form is a make function, so make splits its arguments at commas. The verbs and
`tspace.exec` join the pieces again, which keeps a string literal's text but may change the
whitespace after a comma inside it. The `*` forms take their SQL from a variable, so it
reaches the space whole; `@tspace` passes its seed whole the same way.

<a id="operations"></a>
<a id="ops"></a>
<a id="verbs"></a>

### Operations on Spaces

| Verb | Takes | Answers |
| --- | --- | --- |
| `out` | actuals only | nothing |
| `read` | a pattern | every matching tuple, oldest first |
| `inp` | a pattern | the oldest matching tuple, removed, or nothing |
| `in` | a pattern | the oldest matching tuple, removed, once there is one |
| `rd` | a pattern | the oldest matching tuple, once there is one |
| `no` | a pattern | true, once no tuple matches |
| `rdp` | a pattern | the oldest matching tuple, or nothing |
| `nop` | a pattern | status 0 when no tuple matches, a refusal otherwise; a boolean in the bindings |
| `all` | nothing | every tuple, oldest first; TuCSoN's `get`, whose name every workspace handle already uses |
| `set` | tuples | the space replaced by them, in one request |
| `out_all` | tuples | all added, in one request |
| `in_all` | a pattern | every matching tuple, removed |
| `urdp`, `uinp` | a pattern | a random matching tuple, copied or removed, or nothing |
| `urd`, `uin` | a pattern | a random matching tuple, copied or removed, once there is one |
| `out_s` | a name, then a pattern | the make function of that name registered as a [handler](#handlers) for the pattern, the raw form of `@<space>.reflex amk (...)`; a name already taken is replaced, and a pattern another handler's overlaps is refused, see [R1](runtime.md#reactions) |
| `rd_s` | nothing | every handler as `[name, pattern]`, oldest first |
| `in_s` | a name | the handler, removed, or nothing |
| `react` | nothing | nothing; every stored tuple a handler matches is taken and routed to it, oldest first, the rest left stored. `<space>.__main__` is a target that runs it |

In a recipe or from make, a tuple for `set` and `out_all` is one json array, `'["k", 1]'`;
in a binding it is the language's list.

| Caller | Spelling |
| --- | --- |
| make | `$(tspace read, prime, ?int, ?str)` |
| Recipe | `${tspace.sh} ; tspace read prime ?int ?str` |
| lua | `amk.tspace.read("prime", "integer", "string")` |
| micropy | `amk.tspace.read("prime", int, str)` |
| js | `amk.tspace.read("prime", Number.isInteger, String)` |
| s7 | `(amk-tspace-read "prime" integer? string?)` |

<a id="blocking"></a>

### Blocking Verbs

`in`, `rd` and `no` block their caller until the space answers. Each is one request that
the owner holds when its condition fails, and runs again after every change to the space,
in arrival order: the first `in` held on a pattern takes the tuple a later `out` matches,
inside the owner and atomically. They belong in a recipe, a guest target or a spawned job,
which run in their own process. Make refuses them in an expansion, since an expansion in
the owner would wait on itself. `in` is a keyword in lua and python, so those bindings
spell it `in_`. In js the three are promises over `amk.acall`, so timers and other tasks
keep running while one waits. When the owner exits, every held request is answered with
status 3 and the caller ends.

The owner is the process that parsed the makefile; it holds every space. A forwarder is any
process that inherited a live ask channel from it, a recipe, a guest target, a sub-make or a
spawned job: it holds no space of its own and sends every request up. A held request blocks
only its caller. A forwarder relays its children's requests upward without waiting on them,
so a sibling's `out` reaches the owner while a request is held.

Two channel ops serve a caller whose condition the space cannot express:

| Op on a Workspace Namespace | From a Recipe | Answers |
| --- | --- | --- |
| `version` | `amk.ns version jobs` | the namespace's version, moved by each change |
| `wait` | `amk.ns wait jobs -- 7` | the version, once it is past 7; status 3 when the owner exits first |

How a request asks to be held: its operation answers the park status, 4. In SQL, a
statement that calls `amk_sqlite_park()` does that for the whole request, the way
`amk_sqlite_error()` refuses it; this is how a workspace of any schema gets a blocking verb.

| Caller | Spelling |
| --- | --- |
| Recipe | `${tspace.sh} ; tspace in job ?int` |
| lua | `amk.tspace.in_("job", "integer")` |
| micropy | `amk.tspace.in_("job", int)` |
| js | `await amk.tspace.in("job", Number.isInteger)` |
| s7 | `(amk-tspace-in "job" integer?)` |

<a id="usage"></a>

## Usage

<a id="usage-basic"></a>

### Basic

Below, the `@tspace` decorator creates a space and seeds it, make reads from it, python and
js targets work on it, and SQL counts what is left. The define's name names the space and
its body configures it; see the [overview](#overview).

```Makefile
load tspace

# The define names the space; its json is the backing plus the seed.
@tspace
define SHOP
  {
    "run": true,
    // tuples in the space before any reflex runs
    "seed": [
      ["stock", "tea", 10],
      ["stock", "cake", 4],
      ["order", "tea", 3],
    ],
  }
endef

__main__: report

$(info stock: $(SHOP.read stock, ?str, ?int))

# Python takes each order out of the space and ships it; SHOP is bound for it.
@SHOP.micropy.target
define orders
  order = SHOP.inp("order", str, int)
  while order:
    print("took:", order)
    SHOP.out("shipped", order[1], order[2])
    order = SHOP.inp("order", str, int)
endef

# The define runs as SQL on the default space, so this counts nothing yet.
@tspace.target
define tally
  SELECT count(*) AS default_space FROM tspace
endef

# JS reports what is left, and counts it in SQL through tspace.exec.
@js.target: orders tally
define report
  const shop = amk.tspace["SHOP"];
  for (const t of shop.all()) print("left:", JSON.stringify(t));
  print("count:", amk.tspace.exec("SHOP", "SELECT count(*) AS n FROM tspace"));
endef
```

| Guest   | Handle |
| ---     | --- |
| lua     | `amk.tspace` |
| micropy | `amk.tspace` |
| js      | `amk.tspace` |
| s7      | `amk-tspace-out`, `amk-tspace-read`, `amk-tspace-inp` |

<a id="routed-bound-workers"></a>

### Reactor

A space becomes a reactor when handlers are bound to it. A handler is a make function bound
to a space and a pattern: an `out` whose tuple matches is routed to the handler instead of
being stored, so no `in` or `rd` ever sees it. The handler runs on the space's owner after
the `out` commits, with the tuple's fields as named arguments. A handler's own `out` may
route on to the next handler, so a chain of guests can process one tuple in turn, and a
tuple no handler matches is stored as usual.

Below, handlers in three guests and make route an order through a space: lua prices it, js
ships it, micropy logs a refund, and a make function prints the log. The owner's role and
how a reaction compares to TuCSoN's are in [the reactor](runtime.md#tuplespace-reactor); the reflex
form is under [reflexes](#reflexes), and the guarantees under
[reactions](runtime.md#reactions).

```Makefile
load tspace

@tspace
define SHOP
endef

__main__: report

# An order is priced in lua, which routes on to shipping in js.
@SHOP.reflex/lua (order, item=str, qty=int)
define price
  local prices = { tea = 4, cake = 7 }
  SHOP.out("priced", item, qty, prices[item] * qty)
endef

@SHOP.reflex/js (priced, item=str, qty=int, total=int)
define ship
  SHOP.out("shipped", item, total);
  SHOP.out("log", `shipped ${qty} ${item}`);
endef

# A refund only logs.
@SHOP.reflex/micropy (refund, item=str)
define refund
  SHOP.out("log", "refunded " + item)
endef

# The log line is a make function, which takes the tuple by position.
@SHOP.reflex/amk (log, _)
define log
$(info log: $(2))
endef

@SHOP.amk
define orders
  SHOP.out order tea 3
  SHOP.out order cake 2
  SHOP.out refund tea
  SHOP.out note 'no handler, so stored'
endef

@SHOP.amk: orders
define report
  printf 'handlers:\n'
  SHOP.rd_s
  printf 'stored:\n'
  SHOP.all
endef
```

<a id="usage-actors"></a>

### Actors

A space can also be a set of mailboxes for an [actor group](runtime.md#actor-model), with no
handlers bound. A message is the tuple `["mail", to, from, body]`: sending is `out`, and
receiving is a blocking `in` on the actor's own address, so an actor waits until mail
arrives. Matching on the sender as well is a selective receive: the actor takes the reply it
expects and leaves other mail in its mailbox. Mail nobody receives stays in the space after
the group ends. A blocking receive belongs in an actor with a process of its own, so the
actors below are python [goal](actor.md#kinds) members.

```Makefile
load tspace
load actor

__main__: report

# The mailboxes: one space for every actor, in memory.
@tspace
define MAIL
endef

# The charter: the Effection backend, members joining by at line.
@actor.group
define shop
  { "backend": "effection", "restart": "never" }
endef

# A counter: a python goal in its own process, serving mail until stopped.
@shop.actor/micropy {kind=goal}
define counter
  import amk
  mail, count = amk.tspace["MAIL"], 0
  while True:
    _, _, sender, body = mail.in_("mail", "counter", str, object)
    if body == "stop":
      break
    if body == "inc":
      count += 1
    if body == "get":
      mail.out("mail", sender, "counter", count)
endef

# A client: it sends, then waits for the counter's reply alone.
@shop.actor/micropy {kind=goal}
define client
  import amk
  mail = amk.tspace["MAIL"]
  mail.out("mail", "client", "nobody", "a letter the client never reads")
  for body in ["inc", "inc", "inc", "get"]:
    mail.out("mail", "counter", "client", body)
  _, _, _, count = mail.in_("mail", "client", "counter", object)
  print("client: counter says", count)
  mail.out("mail", "counter", "client", "stop")
endef

# Mail nobody received stays in the space after the group ends.
@MAIL.micropy.target: shop.__main__
define report
  for t in MAIL.all():
    print("unread:", t)
endef
```

<a id="usage-filesystem"></a>

### Filesystem

A space with an `owned` backing lives in an sqlite file, so its tuples outlive the run that
wrote them. The file is loaded at first use and written after every change, and each later
run opens the same file and sees what earlier runs left. Below, a todo list keeps its items
in `.amk/todo.db` and publishes `add`, `rm`, `list` and `purge` as targets over it.

```Makefile
load tspace

# The store, owned by this run and kept between runs.
TODO_DB ?= .amk/todo.db
$(shell mkdir -p $(dir $(TODO_DB)))

@tspace
define TODO
  {"owned": "$(TODO_DB)"}
endef

__main__: list

# Each item is the tuple ["todo", text]; adding one twice keeps one.
@TODO.micropy.target
define add
  item = amk.var["item"].strip()
  if not item:
    raise SystemExit("add: give item='...'")
  if not TODO.rdp("todo", item):
    TODO.out("todo", item)
  print("added:", item)
endef

@TODO.micropy.target
define rm
  item = amk.var["item"].strip()
  print("removed:" if TODO.inp("todo", item) else "not found:", item)
endef

@TODO.micropy.target
define list
  items = TODO.read("todo", str)
  for n, (_, item) in enumerate(items, 1):
    print("%d. %s" % (n, item))
  if not items:
    print("nothing to do")
endef

@TODO.micropy.target
define purge
  print("purged:", len(TODO.in_all("todo", str)))
endef
```

```
$ ./demos/tuplespace-todo.amk add item='buy tea'
added: buy tea
$ ./demos/tuplespace-todo.amk add item='call mom'
added: call mom
$ ./demos/tuplespace-todo.amk rm item='buy tea'
removed: buy tea
$ ./demos/tuplespace-todo.amk
1. call mom
```

<a id="fields"></a>

## Fields

Every verb takes its fields the same way, whoever calls it. A field is either an actual, a
concrete value, or a formal, a typed placeholder that only a pattern may hold. These
subsections give how each caller spells both, and how text from make and the shell is read.

<a id="formals"></a>

### Formals

A pattern is a tuple whose fields are actuals or formals. An actual matches a field by type
and value, as described under [actuals](#actuals). A formal is a placeholder that matches any
value of its type, so the pattern `prime ?int ?str` matches every three-field tuple whose
first field is the string `prime`, whatever integer and string follow. A pattern matches
only tuples with the same number of fields. Make and recipes spell a formal as a word that
begins with `?`. Each guest spells it as its own type, a type name or predicate, as the
table shows. Formals belong in patterns only, and `out` refuses them.

| Formal | Matches | lua | micropy | js | s7 |
| --- | --- | --- | --- | --- | --- |
| `?` | anything | `"any"` | `object` | `undefined` | `amk-tspace-any` |
| `?int` | integer | `"integer"` | `int` | `Number.isInteger` | `integer?` |
| `?float` | float | `"float"` | `float` | | `float?` |
| `?number` | integer or float | `"number"` | `(int, float)` | `Number` | `real?` |
| `?str` | string | `"string"` | `str` | `String` | `string?` |
| `?bool` | true or false | `"boolean"` | `bool` | `Boolean` | `boolean?` |
| `?null` | null | `"nil"` or `nil` | `type(None)` | `null` | `amk-tspace-null?` |
| `?list` | array | | `list` | `Array` | `vector?` |
| `?dict` | object | | `dict` | `Object` | `hash-table?` |
| `?table` | array or object | `"table"` | | | |

<a id="actuals"></a>

### Actuals

An actual is a concrete value: every field of a tuple passed to `out`, and any field of a
pattern that is not a [formal](#formals). Each actual is stored as json, and in a pattern
it matches a field only when both the type and the value agree, so the integer `7` and the
string `"7"` are different tuples. The first table says how a caller's argument becomes
json. Make and recipes pass text, so a word that parses as json keeps that type and any
other word is a string. Guests pass their own values. The second table says what each json
type becomes when a guest reads a tuple back.

| Caller | An Argument Becomes |
| --- | --- |
| make, recipe | its json type when it parses as json, a string otherwise |
| lua, micropy, js, s7 | the json of the language's own value |

| Json | lua | micropy | js | s7 |
| --- | --- | --- | --- | --- |
| integer | integer | `int` | number | integer |
| float | float | `float` | number | real |
| string | string | `str` | string | string |
| true, false | boolean | `bool` | boolean | `#t`, `#f` |
| null | `nil` | `None` | `null` | `'null` |
| array | table | `list` | array | vector |
| object | table | `dict` | object | hash table |
| Awhole tuple | table | `list` | array | list |

<a id="fields-in-a-decorator"></a>

### Fields in a Decorator

A reflex spells its pattern as fields on the decorator line, after its engine, without the
`?` a formal takes elsewhere. The fields are the decorator's elements, as the FFI doc
describes, and the parens around them are optional.

| # | Field | Means |
| --- | --- | --- |
| F1 | a word or a `"quoted literal"` | an actual in the pattern, bound to no name; `_` is the formal `?` |
| F2 | `name=type` | the formal `?type`, bound to the parameter `name` and read back from text by its type; `name=` is `name=any` |
| F3 | `type` in F2 | one of `any`, `str`, `int`, `float`, `bool`, `null`, `list`, `dict`, `number`, `table`: a [formal](#formals) without its `?` |

<a id="rules"></a>

### Rules

A field written as text could be read more than one way, so these rules settle each case.
Make and recipe callers write every field as a word, and the space must decide whether a
word is a formal, a number, or a string. A guest's value can also lose its type on the way
to json. The table gives each case and how it is read or refused.

| Rule | |
| --- | --- |
| Aformal in `out` | refused: `out takes actuals only` |
| Anunknown `?` formal | refused: `unknown formal` |
| Astring beginning with `?` in a pattern | read as a formal |
| Alua type name in a pattern | read as a formal; in `out`, a string |
| Ajs float with no fraction, such as `7.0` | sent as `7`, stored as an integer |

<a id="errors"></a>

## Errors

| Condition | Message |
| --- | --- |
| Aformal in `out` | `out takes actuals only` |
| Anunknown `?` formal | `unknown formal` |
| Ablocking verb in an expansion, in the owner | `the operation parked, and the owner would wait on itself` |
| Aguest reaching `amk.tspace` with no space loaded | `amk.tspace: the makefile has no tuple space; add load tspace` |
| Areflex with no engine | `body: @shop.reflex needs an engine` |
| Areflex in an engine that cannot compile one | `awk cannot compile a reflex` |
| A`reflexes` strategy other than `exclusive` or `shared` | `SKY: reflexes is exclusive or shared, not maybe` |
| Astrategy axis other than `reflexes`, or another key the [schema](#schema) refuses | `SHOP: does not meet schema/tspace.json: Property strategy: Additional property 'pick' not allowed` |
| Areflex overlapping another on an exclusive space | `a handler is refused: its pattern overlaps another`, with the at lines, a witness tuple and the fields |
| Afield type outside the field types | `float32 is not a type` |
| Afield named after its space | `a field cannot be named after its space` |
| Afield name used twice | `a field name is used twice` |
| Ahandler pattern overlapping another's | `overlaps`, naming both at lines, a witness tuple and the fields |
| Aheld request when the owner exits | status 3, and the caller ends |

<a id="demos"></a>

## Demos

| Demo | Shows |
| --- | --- |
| [`tuplespace-1.amk`](../demos/tuplespace-1.amk) | a Linda tuple space shared by workers in four guests under `-j4`, each taking typed candidates through one atomic pattern match |
| [`tuplespace-basic.amk`](../demos/tuplespace-basic.amk) | `@tspace` creating and seeding a space, read from make, python and js, counted in SQL; embedded under [basic](#usage-basic) |
| [`tuplespace-reactor.amk`](../demos/tuplespace-reactor.amk) | handlers in three guests and make routing an order through a space; embedded under [reactor](#routed-bound-workers) |
| [`tuplespace-sailors.amk`](../demos/tuplespace-sailors.amk) | a js world reflex ticking a sky through a day, watched by a lua sailor and a micropy sailor on a space whose reflexes are shared, each keeping a feeling of its own; embedded under the [overview](#overview) |
| [`tuplespace-actors.amk`](../demos/tuplespace-actors.amk) | a space as mailboxes for python goal actors, with a selective receive; embedded under [actors](#usage-actors) |
| [`tuplespace-todo.amk`](../demos/tuplespace-todo.amk) | a todo list in an `owned` space that keeps its items across runs; embedded under [filesystem](#usage-filesystem) |

<a id="references"></a>

## References

- [Data engines](data-engines.md#sqlite-workspaces), the sqlite workspace a space is.
- [The runtime](runtime.md#tuplespace-reactor), where the reactor sits among the concurrency flavors.
- [Pool](pool.md), the other way to hold tokens, and [workspace pools](data-engines.md#workspace-pools) for when a space is one.
- [Tuple space](https://en.wikipedia.org/wiki/Tuple_space), [Linda](https://en.wikipedia.org/wiki/Linda_(coordination_language)) and the [Reactor pattern](https://en.wikipedia.org/wiki/Reactor_pattern), on Wikipedia.
- [TuCSoN](https://apice.unibo.it/bin/view/TuCSoN/) and [ReSpecT](https://apice.unibo.it/bin/view/ReSpecT/), at apice.unibo.it.

[^linda]: David Gelernter, "Generative Communication in Linda", ACM Transactions on Programming Languages and Systems 7(1), 1985, [doi:10.1145/2363.2433](https://doi.org/10.1145/2363.2433).
[^respect]: Andrea Omicini and Enrico Denti, "From Tuple Spaces to Tuple Centres", Science of Computer Programming 41(3), 2001, [doi:10.1016/S0167-6423(01)00011-9](https://doi.org/10.1016/S0167-6423(01)00011-9); TuCSoN is the coordination model built on ReSpecT tuple centres.
[^reactor]: Douglas C. Schmidt, "Reactor: An Object Behavioral Pattern for Demultiplexing and Dispatching Handles for Synchronous Events", in Pattern Languages of Program Design, Addison-Wesley, 1995, [pdf](https://www.dre.vanderbilt.edu/~schmidt/PDF/reactor-siemens.pdf).

<a id="schema"></a>

## Schema

The full form of the json under `@tspace`, as a JSON Schema,
[`schema/tspace.json`](../payload/lib/tspace/schema/tspace.json). The body is expanded
before it is read, and an empty body is a space with no seed, the default strategy and no
backing; see [backings](data-engines.md#backings) for where each one keeps the space. Every
non-empty `@tspace` body is checked against the schema as the makefile is read.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "tspace.json",
  "title": "@tspace",
  "description": "a space under @tspace: its seed, its strategy, and at most one backing; the body is expanded first, and an empty body is the default space's shape",
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "seed": {
      "description": "tuples written by the create that makes the space; a space that already exists keeps its own",
      "type": "array",
      "items": {
        "description": "a tuple: an ordered list of json values, its first the tuple's type",
        "type": "array",
        "minItems": 1
      },
      "default": []
    },
    "strategy": {
      "description": "how the space's reflexes route",
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "reflexes": {
          "description": "exclusive: a reflex is the only destination of the tuples it matches, and an overlapping one is refused; shared: every matching reflex is called, in the order declared",
          "enum": ["exclusive", "shared"],
          "default": "exclusive"
        }
      }
    },
    "run": {
      "description": "the backing: in memory, in the host process",
      "const": true
    },
    "owned": {
      "description": "the backing: a file the space is, held by this process alone",
      "type": "string"
    },
    "shared": {
      "description": "the backing: a file the space is, owners on one host taking turns",
      "type": "string"
    }
  },
  "not": {
    "anyOf": [
      { "required": ["run", "owned"] },
      { "required": ["run", "shared"] },
      { "required": ["owned", "shared"] }
    ]
  }
}
```

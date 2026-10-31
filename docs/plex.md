<!-- header # plex "`mod :: amk.plex`" |Concepts #concepts | Syntax #syntax | API #api | Uses #plex-uses | Choice #choice | Errors #errors | Demos #demos | Refs #references -->
<h1><a id="plex"></a><a href="../README.md#module-index"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-plex.plex.up.dark.svg"><img src="img/hdr/docs-plex.plex.up.svg" alt="up to the module index"></picture></a><a href="../README.md#module-index"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-plex.plex.mod.dark.svg"><img src="img/hdr/docs-plex.plex.mod.svg" alt="mod"></picture></a><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-plex.plex.title.dark.svg"><img src="img/hdr/docs-plex.plex.title.svg" alt=" :: amk.plex"></picture><a href="#references"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-plex.plex.7.dark.svg"><img align=right src="img/hdr/docs-plex.plex.7.svg" alt="Refs"></picture></a><a href="#demos"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-plex.plex.6.dark.svg"><img align=right src="img/hdr/docs-plex.plex.6.svg" alt="Demos"></picture></a><a href="#errors"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-plex.plex.5.dark.svg"><img align=right src="img/hdr/docs-plex.plex.5.svg" alt="Errors"></picture></a><a href="#choice"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-plex.plex.4.dark.svg"><img align=right src="img/hdr/docs-plex.plex.4.svg" alt="Choice"></picture></a><a href="#plex-uses"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-plex.plex.3.dark.svg"><img align=right src="img/hdr/docs-plex.plex.3.svg" alt="Uses"></picture></a><a href="#api"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-plex.plex.2.dark.svg"><img align=right src="img/hdr/docs-plex.plex.2.svg" alt="API"></picture></a><a href="#syntax"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-plex.plex.1.dark.svg"><img align=right src="img/hdr/docs-plex.plex.1.svg" alt="Syntax"></picture></a><a href="#concepts"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-plex.plex.0.dark.svg"><img align=right src="img/hdr/docs-plex.plex.0.svg" alt="Concepts"></picture></a><br clear="all"></h1>
<!-- /header -->

<a id="overview"></a>
The plex is a multiplexer of control: many coroutines on one thread of an engine, each
handed the thread at its yield and given it back when the next one yields. It is the
layer the [actor model](actor.md) schedules on, and it is usable alone: `amk.plex` is
the library, one binding per engine that has first-class control. lua
and micropy have none, since a coroutine that cannot yield to a scheduler is not a plex
task.

There is no `load` line: the plex has no make side. A js guest reaches it as `amk.plex`, a
module the handle loads on first use, and an s7 guest loads its file by path:

```scheme
(load "/zip/lib/plex/init.scm" (rootlet))
```

Where the plex sits among the concurrency flavors, and the layers under and over it, is in
[the runtime](runtime.md#control-multiplexer).

<a id="concepts"></a>

## Concepts

| Term | Meaning |
| --- | --- |
| Task | one coroutine on the plex: a generator run as an operation in js, a thunk in s7 |
| Yield | the point where a task hands the thread to the next ready task |
| Ready List | the s7 plex's queue of continuations waiting for the thread; a stack under `lifo` |
| Scope | in js, the owner of the tasks spawned in it; cancellation runs down from it and its resources are released when it ends |
| Cooperative | a task that does not yield holds the thread, and every other task waits |

<a id="syntax"></a>

## Syntax

The plex adds no decorator, callform or at line; a guest calls it as a library.

<a id="api"></a>
<a id="plex-runtime"></a>

## API

<a id="api-js"></a>

### js

| `amk.plex` is | Unit | Verbs |
| --- | --- | --- |
| Effection[^effection], bundled and republished whole | a generator, run as an operation | `run`, `spawn`, `scoped`, `sleep`, `until`, `race`, `all`, `resource`, `ensure`, `createChannel`, and the rest of Effection's exports |

<a id="api-s7"></a>

### s7

| `amk.plex` is | Unit | Verbs |
| --- | --- | --- |
| `make-plex`, a ready list of continuations in stock s7, a queue, or a stack under `(make-plex 'lifo)` | a thunk, a continuation at its yield | a procedure of a verb: `fork`, `fork-all`, `yield`, `done`, `run`, `finish`, `pending`, `order` |

Effection is structured concurrency and effects: a scope owns its tasks, cancellation runs
down the tree, a resource is released when its scope ends, and the loop underneath is
quickjs's own, reached only through instructions like `sleep` or a `until` over a host
future such as `amk.exited`. The s7 plex has no clock and no descriptors, so a run is the
same every time; a nested run has a ready list of its own. Both are cooperative: a task
that does not yield holds the thread, and a waiting `amk.pool.acquire` inside a task holds
the whole plex, so a task polls with `ms` 0 between sleeps instead.

<a id="plex-uses"></a>

## Uses

A group under a charter is one use of the plex. These need no charter:

| Use | js | s7 |
| --- | --- | --- |
| A process with a scoped lifetime, killed when its scope ends | `spawn` a task that `until`s `amk.exited(pid)`, `ensure` the kill | none, no processes |
| A deadline or a race around an ask | `race([until(amk.acall(..)), sleep(ms)])` | none, no clock |
| Several asks in flight, joined | `all` over `until(amk.acall(..))` | `fork` each, `run` |
| Cleanup bound to a scope, a socket or a workspace owner | `resource`, `ensure` | none |
| A stream over a workspace | `createChannel` fed by a handler, `each` | a loop that yields |
| A hand-rolled supervisor | `demos/supervise-1.amk`, one-for-one over the tuple space | [the actor backend's own code](../payload/lib/actor/init.scm) |

A js guest writes these from the primitives in the
Effection documentation[^effection-docs]; nothing of a group is
required.

<a id="choice"></a>

## Choice

[`load amb`](amb.md) gives `amb`, nondeterministic choice by backtracking over delimited
continuations: `shift` captures the rest of the body, and `amb` runs it once per option,
depth first, in a loop of its own. It needs no plex and uses none. The relation to the plex
is a theorem rather than a kinship: `amb` is `amb-fork` onto a plex whose ready list is a
stack, with tasks that never yield. `(amb-fork plex options)` hands the same `shift` to a
plex, one task per option; on `(make-plex 'lifo)` the leaves come in `amb`'s order, and on
a fifo plex the branches interleave, each start before any end, so a choice becomes a task
that can yield, carry a deadline, and share the plex with other work. Choice is an s7
matter: a js generator cannot be resumed twice, so Effection has no `shift`.
`demos/stdlib-amb-2.amk` shows all three.

<a id="errors"></a>

## Errors

| Condition | Message |
| --- | --- |
| An s7 plex verb it lacks | `plex: no verb spawn` |
| An s7 `shift` with no enclosing `reset` | `shift outside reset` |

A js plex raises what Effection raises; its documentation[^effection-docs]
has them.

<a id="demos"></a>

## Demos

| Demo | Shows |
| --- | --- |
| [`stdlib-amb-2.amk`](../demos/stdlib-amb-2.amk) | choice on the plex: counters interleaving, `amb-fork` breadth-first on a fifo plex, and depth-first on a lifo plex agreeing with `amb` |
| [`supervise-1.amk`](../demos/supervise-1.amk) | the plex without a charter: a one-for-one supervisor written by hand in js over the tuple space |
| [`race-1.amk`](../demos/race-1.amk) | fork-join over goals through `amk.agoal`: `race` takes the first goal to finish, `all` joins them, and `all` over a failing one ends at the failure |

<a id="references"></a>

## References

- [The runtime](runtime.md#control-multiplexer), where the plex sits among the concurrency flavors.
- [Actor](actor.md), the supervisors that run on a plex.
- [amb](amb.md), choice by delimited control, which `amb-fork` runs on a plex.
- [Coroutines](https://en.wikipedia.org/wiki/Coroutine), [cooperative multitasking](https://en.wikipedia.org/wiki/Cooperative_multitasking) and [structured concurrency](https://en.wikipedia.org/wiki/Structured_concurrency), on Wikipedia.

[^effection]: Effection, structured concurrency and effects for JavaScript, [frontside.com/effection](https://frontside.com/effection).
[^effection-docs]: The Effection documentation, [frontside.com/effection/docs](https://frontside.com/effection/docs).

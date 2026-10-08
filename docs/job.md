<!-- header # job "`mod :: dsys/job`" |Concepts #concepts | Syntax #syntax | API #api | Errors #errors | Demos #demos | Refs #references -->
<h1><a id="job"></a><a href="dsys.md"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-job.job.up.dark.svg"><img src="img/hdr/docs-job.job.up.svg" alt="up to dsys"></picture></a><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-job.job.title.dark.svg"><img src="img/hdr/docs-job.job.title.svg" alt="mod :: dsys/job"></picture><a href="#references"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-job.job.5.dark.svg"><img align=right src="img/hdr/docs-job.job.5.svg" alt="Refs"></picture></a><a href="#demos"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-job.job.4.dark.svg"><img align=right src="img/hdr/docs-job.job.4.svg" alt="Demos"></picture></a><a href="#errors"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-job.job.3.dark.svg"><img align=right src="img/hdr/docs-job.job.3.svg" alt="Errors"></picture></a><a href="#api"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-job.job.2.dark.svg"><img align=right src="img/hdr/docs-job.job.2.svg" alt="API"></picture></a><a href="#syntax"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-job.job.1.dark.svg"><img align=right src="img/hdr/docs-job.job.1.svg" alt="Syntax"></picture></a><a href="#concepts"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-job.job.0.dark.svg"><img align=right src="img/hdr/docs-job.job.0.svg" alt="Concepts"></picture></a><br clear="all"></h1>
<!-- /header -->

<a id="overview"></a>
A job is a [fork of this parsed image](zygote.md#fork-and-the-fresh-copy), the same fork the [zygote](zygote.md) makes per request, made at the moment of the spawn, running one thing.
The noun says what runs, and `spawn` puts it in a job: `amk.goal.spawn` for one goal,
`amk.goals.spawn` for a goal list, or `amk.job.spawn kind=name` for either by kind.
Everything after the spawn is under `amk.job`: the [host handle's](FFI.md#host-handle) wait
on a pid or a set, its peek, and its signals, plus a job table, the pids of a job and of its
spawner, and mail written from make.

```Makefile
load dsys/job

all:
	@echo '$(amk.job.all $(amk.goal.spawn lint) $(amk.goal.spawn test))'
```

It needs no engine. The verbs are make functions, so every guest reaches them as fields of
`amk.job`. It is part of [the dsys module](dsys.md); the
[jobman](jobman.md) builds its pools of jobs, each a host plex that
owns its members, on these verbs.

<a id="concepts"></a>

## Concepts

| Term | Meaning |
| --- | --- |
| Job | a fork of this image as it stands at the spawn, its own process group, running one kind; see [jobs](runtime.md#jobs) |
| Kind | what a job runs: `goal`, one target brought up to date, `goals`, a goal list as one make run, or `call`, one function call |
| Record | the json object a wait answers: `pid`, `code`, `signal`, `status`, `mail` and `kind`; see [the host handle](FFI.md#host-handle) |
| Value | what a call answers; its record flags it with `"value": true` and never holds it, since it may be any size, and `amk.job.value` reads it |
| Job Table | the pids spawned through a noun's `spawn` in this process and not yet finished |
| Spawner | the process that spawned this job; empty at the top |

A job sees a snapshot: the parse, the variables and every guest's state as they stood when
it was spawned, so a variable changed before the spawn is changed in the job too.

A stopped job stays in the table: its record reports `stopped`, and the record that ends
it comes later.

<a id="syntax"></a>

## Syntax

`dsys/job` adds no decorator. Its forms are make functions, the spawns under
the noun of what runs and the rest under `amk.job`:

```Makefile
load dsys/job

slow:
	@sleep 1
fast:
	@true $(amk.job.send done)

all:
	@echo 'live=$(eval a := $(amk.goal.spawn slow))$(eval b := $(amk.job.spawn goal=fast))$(amk.job.list)'
	@echo 'first=$(amk.job.any $(a) $(b))'
	@echo 'rest=$(amk.job.wait $(a))'
# live=4242 4243
# first={"pid": 4243, "code": 0, "signal": 0, "status": "success", "mail": "done"}
# rest={"pid": 4242, "code": 0, "signal": 0, "status": "success", "mail": "", "kind": "goal"}
```

<a id="api"></a>

## API

| Call | Does | Answers |
| --- | --- | --- |
| `$(amk.goal.spawn name[, foreground=1][, stdout=path])` | spawns one goal and enters the pid in the table; more than one word is refused | the pid |
| `$(amk.goals.spawn goals[, foreground=1][, stdout=path])` | spawns a goal list as one make run, as `amk.spawn` does, and enters the pid in the table | the pid |
| `$(amk.call.spawn name[, args...])` | calls the function, macro or engine `name` in a job | the pid; the record says `"kind": "call"` and `"value": true` |
| `$(amk.job.value pid)` | reads a call's value to its end and takes it, once; the job stays for its wait | the value as text, or empty when none is left |
| `$(amk.job.spawn kind=name[, ...])` | spawns by kind: `goal=x` as `amk.goal.spawn x`, `goals=x y` as `amk.goals.spawn x y`, `call=fn, arg` as `amk.call.spawn fn, arg` entered in the table; another kind, or no `kind=`, is refused | the pid |
| `$(amk.goals goals[, ...])` | spawns the goal list and waits for it | the record |
| `$(amk.job.list)`, `$(amk.job)` | reads the table, in spawn order | the live pids |
| `$(amk.job.wait [pids[, block]])` | waits as `amk.wait` does; a finished job leaves the table | the record, or empty when `block` is `0` and none is ready |
| `$(amk.job.peek pid)` | `$(amk.wait pid, peek)`: reads the job's record without consuming it; the next wait answers the same record | the record, or empty while the job runs |
| `$(amk.job.any pids[, block])` | waits for the first of the set to report; no job outside the set is reaped, and an empty set answers empty | the record, or empty when `block` is `0` and none is ready |
| `$(amk.job.all pids)` | waits for every job of the set | a json array of records, in the set's order |
| `$(amk.job.kill pid[, sig])`, `$(amk.job.stop pid)`, `$(amk.job.resume pid)`, `$(amk.job.foreground pid)` | signals as the host handle does | `1`, or empty for a pid that is not a live job |
| `$(amk.job.reaped pid)` | drops a job reaped outside the table, as by `amk.exited`, from the table | empty |
| `$(amk.job.send text)` | writes text to the parent's mail, from inside a job; a guest sends with its own `amk.send` | `1`, or empty outside a job |
| `$(amk.job.self)` | reads this process's pid | the pid |
| `$(amk.job.parent)` | reads the spawner's pid | the pid, or empty at the top |

A guest calls the same verbs as fields: `amk.job.wait(amk.goal.spawn('fast'))` in lua,
micropy and js, and `(amk-call 'amk.job.wait pid)` in s7. Each answers text, the record as
json text, as the make function does.

The table holds the jobs these spawns made, the [jobmen's](jobman.md) included. A job
from a raw `amk.spawn` or `amk.agoal` reaches `amk.job.wait` and `amk.job.any`, but never
`amk.job.list`. The holding is in `amk.wait` itself: a wait on a set reaps no job outside it,
and a peeked record stays for the next wait, so a raw `amk.wait` and these verbs never take
each other's records.

<a id="errors"></a>

## Errors

The verbs pass the host handle's errors through: a pid or signal that is not a number, or a
spawn of no goals, fails naming the host function, as under
[the host handle](FFI.md#host-handle).

| Condition | Answer |
| --- | --- |
| Await for a pid that is not a job of this process | empty, as `amk.wait` |
| `amk.job.spawn` without `kind=`, or with an unknown kind | `amk.job.spawn: give kind=name, one of goal=.. goals=.. call=..; got 'fast'` |
| `amk.goal.spawn` of more than one goal | `amk.goal.spawn: one goal, got 'a b'; use amk.goals.spawn for a list` |
| `amk.job.send` outside a job | empty |

<a id="demos"></a>

## Demos

None yet; [`tests/dsys/test_job.py`](../tests/dsys/test_job.py) pins every verb.

<a id="references"></a>

## References

- [The dsys module](dsys.md), and the [host handle](FFI.md#host-handle), the job verbs this wraps.
- [Jobman](jobman.md), pools of jobs over the same verbs, and [the runtime](runtime.md#multiprocessing).
- [The zygote](zygote.md#fork-and-the-fresh-copy), the fork a job is.

<!-- header # dataflow "Dataflow" | Values #values | Modes #modes | Dataflow Mode #dataflow-mode | Commands #bash-values | Refs #references -->
<h1><a id="dataflow"></a>Dataflow<a href="#references"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-dataflow.dataflow.4.dark.svg"><img align=right src="img/hdr/docs-dataflow.dataflow.4.svg" alt="Refs"></picture></a><a href="#bash-values"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-dataflow.dataflow.3.dark.svg"><img align=right src="img/hdr/docs-dataflow.dataflow.3.svg" alt="Commands"></picture></a><a href="#dataflow-mode"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-dataflow.dataflow.2.dark.svg"><img align=right src="img/hdr/docs-dataflow.dataflow.2.svg" alt="Dataflow Mode"></picture></a><a href="#modes"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-dataflow.dataflow.1.dark.svg"><img align=right src="img/hdr/docs-dataflow.dataflow.1.svg" alt="Modes"></picture></a><a href="#values"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-dataflow.dataflow.0.dark.svg"><img align=right src="img/hdr/docs-dataflow.dataflow.0.svg" alt="Values"></picture></a><br clear="all"></h1>
<!-- /header -->

Values between goals, and the `dataflow` mode that makes a makefile of them safe to rerun.

<a id="values"></a>

## Values between goals

A target's value is what it printed: an imported target's program output, or a recipe
target's standard output, line by line. `$(amk.goal name)` answers it from a recipe: it brings
the goal up to date in a fork of the parsed image, then reads the value, trimmed of one
trailing newline like every builtin. A target that is a file has the file as its value,
read where it is and never copied: one with no recipe, such as a source on disk given an
empty rule, or one marked `@amk.file` because its recipe writes `$@`.

A goal that fails stops make at the expansion. `$(amk.goal.maybe name)` runs it the same way
but answers its value, or empty when it failed or left none, and sets `amk.goal.maybe.status`
to `success` or `failed`, so the run goes on and the caller decides:

```Makefile
report:
	echo "tests: $(amk.goal.maybe test) ($(amk.goal.maybe.status))"
```

An imported body reaches its engine as written, so `$` is the guest's. Its one form is
`>>x<<`, the value of goal `x` spliced in raw: a name of letters, digits and `_ . - /`, in any
case, that must match exactly one target a makefile names. The closing `<<` is what makes
it a reference, so a shell's `>>file` or a guest's shift operator pass through untouched.
Since case is free, `>>X<<` reads as a module global in most guests. A file needs a rule,
even an empty one. Names resolve after the makefiles are read, so a reference may come first.

```Makefile
@amk.file
numbers.txt:
	printf '3 1 2' > $@

@awk.target
define sorted
  BEGIN { n = split(">>numbers.txt<<", a, " "); asort(a); for (i = 1; i <= n; i++) print a[i] }
endef

@lua.target
define total
  local t = 0
  for n in (">>sorted<<"):gmatch("%S+") do t = t + n end
  print(t)
endef
```

A target some body references keeps its value in a file under the value directory, and its
name waits on that file. Each `>>x<<` is a prerequisite of the value file, so a kept value
reruns only when a value it reads is newer, and independent targets run at once under `-j`.
The prerequisites a makefile writes on the name, `sorted: numbers.txt`, are the value's inputs
too. Within one run every reader sees one computation. An imported target's name is phony,
so a file of the same name in the working directory never satisfies it. Run as a goal on
the command line, a name prints its kept value.

The job is a fork of make with no exec, so the guest handle reads make state there, and its
writes end with the job. The fork splices the values into the program and runs the engine on
it, a kept value's output onto its file. No file carries the program and no argument limit
bounds its size. A recipe target's lines run as make runs any recipe, with `$@` the name as
written and standard output onto the value file.

<a id="marks"></a>

### Marks

Two decorators above a target say what its value is when the default is wrong. Each lowers
to a special target, so a makefile without the preprocessor writes that line instead.

| Decorator | Special target | Meaning |
| --- | --- | --- |
| `@amk.file` | `.AMK_FILE: x` | the value is the file `x` writes |
| `@amk.nocache` | `.AMK_NOCACHE: x` | the value is its output, computed once per run and never reused across runs |

A `.PHONY` target is no-cache by itself. A recipe target that writes `$@` and prints nothing
fails when something reads it, with `x wrote its file but printed nothing; mark it
@amk.file`.

The policy, as it stands:

| # | Rule |
| --- | --- |
| P1 | A target's value is its output: an imported target's always, a recipe target's when some body reads it. |
| P2 | A target with no recipe, or marked `@amk.file`, is its file. |
| P3 | A kept value with no inputs is computed once per value directory, in every mode; `@amk.nocache` and `.PHONY` make it once per run. |
| P4 | A recipe target nothing reads runs as make always ran it, and `$(amk.goal x)` on it captures one run's output. |

<a id="modes"></a>

## Modes

In `amk` the runtime is always in some "mode", and the `default` mode is in effect unless another one is set.  

If nothing is set, mode semantics are the same as classical Makefile *(a failed target keeps what it wrote, as any recipe does, unless the Makefile sets mysterious values like `.DELETE_ON_ERROR` and `.PRECIOUS`, etc)*.  Generalizing, you could say that a mode is something that changes *runtime and storage*, but never changes parsing, so that a Makefile (or amk-lang script) means the same thing with or without it.

You can set a different mode by calling `$(amk.mode ..)` or setting the environment variable `AMK_MODE=..`

<a id="setting-a-mode"></a>

## Dataflow Mode

| Setter | Form |
| --- | --- |
| makefile     | `$(amk.mode dataflow)`, before any file target is defined |
| command line | `amk.mode=dataflow` |
| environment  | `AMK_MODE=dataflow` |

The command line wins over the makefile, and the makefile over the environment. A mode covers the whole make process, whoever sets it and in whichever included file. Setting one after a file target is defined is fatal, naming that target, so a mode always precedes the rules it governs. A build that wants the mode for one part runs that part as its own sub-make. `$(amk.mode)` with no argument answers the active mode's name, and an unknown name is fatal and lists the modes.

<a id="dataflow-mode"></a>

## The dataflow mode

```Makefile
$(amk.mode dataflow)
amk.dataflow_dir := build/values
```

Under `dataflow`, every imported target is a kept value, read or not, as is every recipe
target some body reads, and each value `name` has files beside it in the value directory:

| File | Holds |
| --- | --- |
| `name` | the value, the program's or the recipe's standard output |
| `name.json` | the record: engine, or `recipe`, exit status, the body's checksum, and the checksum of each input |
| `name.err` | the engine's standard error, from the last run |
| `name.failed` | the partial output of a failed run, moved aside |

The mode's behaviour, piece by piece:

- **Failure.** A failed value is moved aside to `name.failed`, never left in place, so the
  next run computes it again and nothing downstream reads a partial result. Its stderr log
  prints beside make's error.
- **Files that existed before.** A classic file target that the run created and then failed
  on is deleted, as under `.DELETE_ON_ERROR`. One that existed before the run comes back as
  it was, so a failed recipe never costs a hand-written file.
- **Early cutoff.** A value whose new content matches its old keeps the old file and mtime,
  so nothing downstream reruns.
- **Body freshness.** A value whose body differs from the one its record saw is stale,
  whatever the mtimes say, and reruns. The body is the program or the recipe as written,
  before expansion.
- **Opt-out.** `.PRECIOUS` keeps a target out of all of this, as in make, and a no-cache
  value is phony, so it has no record and no cutoff.

A value's inputs are exactly what it declares: its `>>name<<` references and its make
prerequisites. Data that reaches a program any other way, on stdin, through a variable the
program reads itself, or through a library's own convention, is not an input, and the value
is not cached on it. A value that declares no inputs is computed once per value directory.

<a id="value-directory"></a>
<a id="intermediates"></a>

### Values Directory

`amk.dataflow_dir` names it, and exists only under this mode. The default is
`.amk/dataflow-<pid>` under the working directory, with the pid of the top-level make,
exported as `AMK_DATAFLOW_DIR` so every sub-make of the run shares it. Each run therefore
starts cold. A makefile that wants early cutoff and body freshness to hold between runs
sets a fixed path.

<!-- A classic rule that names a kept value as a prerequisite, `page.html: sorted`, reruns every time, since the name is phony. Depend on the value file to stay `$(amk.dataflow_dir)/sorted`, to stay incremental. -->

<a id="bash-values"></a>

## Command values

The payload's bash library makes a shell command's standard output a value, computed once
per run and recorded like any other. It needs the lua engine.

```Makefile
$(amk.mode dataflow)
$(amk.include bash)

@bash.target
define engines
  amk --list-engines
endef

@lua.target
define count
  local n = 0
  for _ in (">>engines<<"):gmatch("[^\n]+") do n = n + 1 end
  print(n .. " engines total")
endef
```

The command runs under `bash -euo pipefail`, so a failing pipeline fails the target. A
parse-time `$(amk.bash ...)` stays available, but only a command under the at line takes part
in caching and dataflow.

<a id="references"></a>

## References

Related pages:

- [The runtime](runtime.md), where the task graph and its dataflow mode sit among the concurrency flavors.
- [Grammar](grammar.md#goal-substitution), for goal substitution in a target's name.
- [utmpl](utmpl.md), whose document targets re-render when their data changes.

Further reading:

- [Dataflow programming](https://en.wikipedia.org/wiki/Dataflow_programming) and [incremental computing](https://en.wikipedia.org/wiki/Incremental_computing), on Wikipedia.

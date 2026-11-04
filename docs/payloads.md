<!-- header # payloads "Payloads" | ^ ../README.md#payloads | Boot #boot | Unpack #unpack | Tools #tools | Bundles #bundles | Members #payload-members-with-a-meaning | Running #running-an-ape | Demos #demos | Reference #reference | Refs #references -->
<h1><a id="payloads"></a><a href="../README.md#payloads"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-payloads.payloads.up.dark.svg"><img src="img/hdr/docs-payloads.payloads.up.svg" alt="up"></picture></a>Payloads<a href="#references"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-payloads.payloads.8.dark.svg"><img align=right src="img/hdr/docs-payloads.payloads.8.svg" alt="Refs"></picture></a><a href="#reference"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-payloads.payloads.7.dark.svg"><img align=right src="img/hdr/docs-payloads.payloads.7.svg" alt="Reference"></picture></a><a href="#demos"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-payloads.payloads.6.dark.svg"><img align=right src="img/hdr/docs-payloads.payloads.6.svg" alt="Demos"></picture></a><a href="#running-an-ape"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-payloads.payloads.5.dark.svg"><img align=right src="img/hdr/docs-payloads.payloads.5.svg" alt="Running"></picture></a><a href="#payload-members-with-a-meaning"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-payloads.payloads.4.dark.svg"><img align=right src="img/hdr/docs-payloads.payloads.4.svg" alt="Members"></picture></a><a href="#bundles"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-payloads.payloads.3.dark.svg"><img align=right src="img/hdr/docs-payloads.payloads.3.svg" alt="Bundles"></picture></a><a href="#tools"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-payloads.payloads.2.dark.svg"><img align=right src="img/hdr/docs-payloads.payloads.2.svg" alt="Tools"></picture></a><a href="#unpack"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-payloads.payloads.1.dark.svg"><img align=right src="img/hdr/docs-payloads.payloads.1.svg" alt="Unpack"></picture></a><a href="#boot"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-payloads.payloads.0.dark.svg"><img align=right src="img/hdr/docs-payloads.payloads.0.svg" alt="Boot"></picture></a><br clear="all"></h1>
<!-- /header -->

<a id="overview"></a>

## Overview

An amk binary is also a zip file. The files in that zip are its payload: the tools,
libraries and prelude amk ships, plus anything you add. amk, and every tool it carries,
sees the payload as a read-only directory at `/zip`.

That makes amk a way to ship a program as one file, whether or not the program has
anything to do with make.

<a id="ship-a-script"></a>

### Ship a script

```bash
amk --bundle-main tool.sh plugins/ --out tool
./tool one two
```

`tool` is a single file. It runs `tool.sh` as written, under its own bash, with `jq`,
`sqlite3`, `awk`, `sed`, `cat` and `ls` first on `PATH`, on a host that has none of them.

<a id="capabilities"></a>

### What a payload gives you

| You want | You use | See |
| --- | --- | --- |
| A program that runs when the binary does | An entry, `__main__` with an engine's extension | [Boot](#boot) |
| Tools that are always there | The bundled tools and the tool engines | [Tools](#tools) |
| To read your files without unpacking | Paths under `/zip` | [Reading in place](#reading-the-payload-from-a-tool) |
| Real files on the host | A copy out | [Unpack](#unpack) |
| To add, replace or remove files | The flags that begin with `--bundle` | [Bundles](#bundles) |
| State that travels inside the binary | A write in place | [Writing in place](#in-place) |

<a id="limits"></a>

### Limits

- **Only amk's own tools see `/zip`.** A host program such as `/usr/bin/grep` does not.
  `cat` and `ls` are bundled for this reason, so `cat /zip/data | grep x` works.
- **Nothing executes from `/zip`.** Run a script member as `bash /zip/plugins/x.sh`. The
  tools under `bin/` are unpacked to a cache for the same reason.
- **`/zip` is read-only.** A change writes a new binary, or replaces this one for the
  next run. A running program keeps the view it started with.
- **A host with no loader needs a shell to start the binary**, see [running](#running-an-ape).

<a id="boot"></a>

## Boot

<a id="entry-script"></a>

A payload member named `__main__` with an engine's extension is the entry. It takes over
the run, and [`--bundle-main`](#bundles) writes one from a file.

| Entry | Runs as |
| --- | --- |
| `__main__.sh`, `__main__.bash` | The payload's bash on the member's path, the caller's arguments after it |
| `__main__.lua`, `.s7`, `.js`, `.micropy`, and each such engine's aliases | The member's text as that engine's program; arguments are not passed |
| `__main__.mk` | The makefile a bare run reads, when no other entry takes the run; what [`--bundle`](#bundles) writes |

A payload holds one entry besides `__main__.mk`. jq, sqlite and awk take no entry.

<a id="arguments-and-the-binarys-path"></a>

A shell entry sees:

| In the script | Holds |
| --- | --- |
| `$0` and `${BASH_SOURCE[0]}` | `/zip/__main__.sh` |
| `$1`, `$2`, ... | The caller's arguments, unchanged |
| `${COSMOPOLITAN_INIT_ZIPOS}` | The absolute path of the binary, to run it again |

<a id="when-boot-is-skipped"></a>

The entry is skipped when `AMK_BOOTED` is set, which is how a script that runs the binary
again as make keeps the child from booting, and when the member is empty.

Worked examples: [`tests/test_boot.py`](../tests/test_boot.py).

<a id="unpack"></a>

## Unpack

A copy out puts payload members on the host as real files, for a host tool, a container
mount, or anything that must be executed.

```bash
./tool --bundle-cp /zip/lib/greet.mk .
./tool --bundle-cp /zip/plugins ./plugins
```

`--ape-unpack NAME [DEST]`, also spelled `-x NAME`, is the older form for one member. It
prints the path and skips a copy that is already current, so a plain makefile can include
straight from a bundle:

```make
include $(shell ./tool --ape-unpack=lib/greet.mk)
```

`--force` overwrites a destination that exists. `--ape-list` is the older listing, with
names relative to the payload's root; [`--bundle-ls`](#bundles) prints them under `/zip`.

<a id="tools"></a>

## Tools

Every member under `bin/` is unpacked once to a cache and put first on `PATH`, so a
recipe or a script finds it by name on any host.

| Kind | Names | What it is |
| --- | --- | --- |
| Bundled tools | `bash`, `sed`, `cat`, `ls`, `jb` | Released binaries, unchanged; [versions](../README.md#tools) |
| Tool engines | `jq`, `sqlite3`, `sqlite`, `awk`, `gawk` | Links to amk itself, which has these linked in |

<a id="tool-engines"></a>

A tool engine's command line is the tool's own: `--version` and `--help` are the tool's,
and amk takes no option of its own from it. `amk --jq ARGS` is the same line without the
link. bash is an engine too, see [the README](../README.md#engines), but it runs as the
bundled file.

Each name shadows a host tool of the same name. `AMK_NO_PATH` set to any value leaves
`PATH` alone and unpacks nothing. The cache is keyed to the binary, see
[payload internals](dev.md#payload-internals).

<a id="reading-the-payload-from-a-tool"></a>

### Reading in place

A bundled tool tests, reads and sources a member where it is:

```make
all:
	[ -f /zip/__init__.mk ]
	source /zip/bin/amk.sh
	cat /zip/__init__.mk | grep SHELL
```

amk does this by exporting `COSMOPOLITAN_INIT_ZIPOS` with its own path. A child program
that carries a payload of its own then sees amk's; unset the variable for that child.

<a id="bundles"></a>

## Bundles

<a id="verbs"></a>

The flags that begin with `--bundle` treat the payload as a small filesystem. Three do
the work and three are shorthand.

| Flag | Does |
| --- | --- |
| `--bundle-ls` | Lists every member by its path under `/zip` |
| `--bundle-cp SRC... DEST` | Copies in or out; the side written under `/zip` is the payload |
| `--bundle-rm NAMES...` | Removes members; a directory takes everything under it |
| `--bundle FILES...` | Copies in, the first file as `__main__.mk` |
| `--bundle-main FILE FILES...` | Copies in, the first file as the [entry](#boot) for its extension |
| `--bundle-strip` | Removes everything but the tools under `bin/` and the program's own members |

```bash
amk --bundle main.mk lib/ --out my.tool
./my.tool --bundle-ls
./my.tool --bundle-cp settings.json /zip/etc/ --out configured.tool
./my.tool --bundle-rm /zip/lib --out smaller.tool
```

A flag that changes the payload says where the result goes, and prints that path:
`--out DEST` for a new copy, or `--in-place` for the binary itself. One of the two is
required. Every change keeps the file tight: a member that is replaced or removed gives
its bytes back.

<a id="copy"></a>

### Copy

One source lands at the destination; several land under it by their own names.

| Copy | Lands at |
| --- | --- |
| `--bundle-cp note.txt /zip/doc/readme` | `/zip/doc/readme` |
| `--bundle-cp note.txt /zip/doc/` | `/zip/doc/note.txt` |
| `--bundle-cp state/ /zip/state/` | The directory's files under `/zip/state/` |
| `--bundle-cp note.txt state /zip/kept/` | `/zip/kept/note.txt` and `/zip/kept/state/...` |

<a id="remove"></a><a id="strip"></a>

### Remove and strip

`--bundle-rm` takes a name as `--bundle-ls` prints it, or relative to the root. A name
that matches nothing fails and nothing is written.

The program's own members cannot be removed or written: any dot name, and everything
under `usr/`. Beyond that, amk does not check what still works. The prelude includes from
`lib/`, so a copy without `lib/` that keeps `__init__.mk` stops on every run.

`--bundle-strip` is the safe preset: plain make with the engines and the tools, and no
prelude, libraries or decorator rewrite. A makefile that sets `SHELL := bash` still gets
the payload's bash.

<a id="in-place"></a>

### Writing in place

`--in-place` lets a tool carry its own state from one run to the next:

```bash
"${COSMOPOLITAN_INIT_ZIPOS}" --bundle-cp state/ /zip/state/ --in-place
```

- **Safe to interrupt.** The result is written beside the binary, flushed, and renamed
  into place, so a crash leaves the old binary or the whole new one.
- **Safe to repeat at once.** Writers of one binary take turns, each reading what the one
  before it wrote. The turn is a lock on the binary itself; no lock file is left.
- **Respects permissions.** A binary or directory the user cannot write is refused, the
  binary's mode is kept, and a binary that belongs to another user is written with a
  warning that the result changes hands.

The lock needs a local filesystem; a network share or a directory shared with a container
may not honor it. For data that changes while the program runs, such as a database, keep
the live file outside the binary and copy a snapshot in.

Worked examples: [`tests/test_bundle.py`](../tests/test_bundle.py).

<a id="payload-members-with-a-meaning"></a>

## Payload members with a meaning

| Member | Meaning |
| --- | --- |
| `__main__.<ext>` | The [entry](#boot) |
| `__main__.mk` | The makefile a bare run reads, as `-f /zip/__main__.mk -I /zip` |
| `__init__.mk` | The [prelude](#prelude), read before any makefile |
| `__init__.<engine>` | An init chunk run in that engine's main state before the parse; `AMK_<ENGINE>_INIT` overrides it |
| `bin/` | The [tools](#tools) |
| `lib/<name>/` | A [module](#modules) |
| Dot names, `usr/` | The program's own, placed by the linker; protected |

<a id="prelude"></a>

### The prelude

Make reads `__init__.mk` before any makefile, the way it reads a `MAKEFILES` entry: a
missing member is silent, and a target in it never becomes the default goal. No shell is
involved and a start costs nothing extra. It sets the defaults every makefile under amk
would otherwise repeat, each one overridable by a later assignment or an environment
knob: `SHELL` from `AMK_SHELL` else bash, `.SHELLFLAGS` from `AMK_SHELLFLAGS` else
`-euo pipefail -c`, `MAKEFLAGS` as silent, stop on error and warn on undefined variables,
`.DEFAULT_GOAL` from `AMK_GOAL` when set, a `__file__` naming the entry
makefile, and `amk` to run it again. With patch 0035, a `__main__` target is the default goal whenever the makefile
names none itself, wherever it sits in the file. A host with no bash on `PATH` gets `/bin/sh` instead. The default flags follow `SHELL`: `-euo pipefail -c` while it names bash, `-eu -c` for any other shell, including one a makefile sets. Once read,
the prelude leaves `MAKEFILE_LIST` again, so the first word of that list still names the
entry makefile and a bundle or a distribution that spells it that way sees no change.
`AMK_NO_PRELUDE` skips it.

<a id="library-directory"></a><a id="modules"></a>

### Modules

An amk module is a directory `/zip/lib/<name>/` with one init file per guest. `amk.<name>`
loads that guest's file by its exact path, once; no search path is consulted, so a stdlib or
vendored module never answers as `amk.<name>`. A single file for one engine, taken by a
makefile's `load` line, is the other kind of [module](../README.md#modules); `load <name>`
with no extension reaches this directory's `init.amk` through `amk.include`.

| Guest | `amk.<name>` Loads | When Absent |
| --- | --- | --- |
| lua | `/zip/lib/<name>/init.lua` | `nil` |
| micropy | `/zip/lib/<name>/__init__.py`, as the module `amk.<name>` | `AttributeError` |
| js | `/zip/lib/<name>/init.js` | `undefined` |
| s7 | `/zip/lib/<name>/init.scm`, for `amk-<name>-...` | Unbound variable |

A name the handle lacks is looked up in this order in every guest: a module directory of
that name, then what `amk.call` resolves it to, the name itself or the name under `amk.`,
as a make function or a macro, see [the guest handle](FFI.md#guest-handle).
A directory under `lib/` therefore owns its name in every guest that has a file for it, so
no make function should be called `amk.<directory>`.

Vendored code sits on each guest's own search path and loads with a plain `require` or `import`.

| Guest | Search Path | Holds |
| --- | --- | --- |
| lua | `/zip/lib/lua/` | `dkjson` |
| micropy | `/zip/lib/micropy/` | `utemplate`, and `asyncio`, `ssl`, `requests`, `mip` from micropython's own tree |

<a id="running-an-ape"></a>

## Running an ape

The binary starts from a shell on every system. A parent that executes it directly, such
as Python's `subprocess` without a shell, fails with an exec format error on a host with
no loader registered. Go through `sh -c`, or name [the loader](dev.md#ape-loader).

amk reads some first arguments before the entry, so they never reach it: `-x`,
`--ape-list`, `--ape-unpack`, every flag that begins with `--bundle`, `--preprocessor`,
`--list-engines`, and every engine flag such as `--jq`. `--profile` is taken anywhere on
the line, except on a tool engine's own.

<a id="a-host-without-bash"></a>

A shell entry needs the payload's bash, since a host shell cannot read `/zip`. amk warns
on stderr, in red on a terminal unless `NO_COLOR` is set, whenever that bash is not the
one in use:

| Condition | What happens |
| --- | --- |
| Neither `HOME` nor `XDG_CACHE_HOME` is set | The tools are not unpacked; the host's are used |
| A tool cannot be written to the cache | `PATH` is left alone; the host's tools are used |
| `AMK_NO_PATH` is set and the payload has a shell entry | The host's bash is tried and cannot open the script |
| No `bash` is on `PATH` | amk exits 127 |

<a id="demos"></a>

## Demos

| Example | Shows |
| --- | --- |
| [`tests/fixtures/bundle/`](../tests/fixtures/bundle) | A makefile bundle with its own `lib/`, the one `make smoke` builds |
| [`demos/bash-1.amk`](../demos/bash-1.amk) | The bash engine: `$(bash ...)` and `@bash.target` |
| [`tests/test_boot.py`](../tests/test_boot.py) | Script entries, `--bundle-main`, and each startup warning |
| [`tests/test_bundle.py`](../tests/test_bundle.py) | Every `--bundle` flag, writes in place, and permissions |
| [`tests/test_tool_names.py`](../tests/test_tool_names.py) | The tool engines by name, and a script that calls them unmodified |

<a id="reference"></a>

## Reference

Flags are listed in [the README](../README.md#environment-and-cli) and by `amk --help`.

| Variable | Meaning |
| --- | --- |
| `COSMOPOLITAN_INIT_ZIPOS` | Set by amk to its own path and exported; names the binary to a script |
| `AMK_BOOTED` | Any value skips the entry |
| `AMK_NO_PATH` | Any value leaves `PATH` alone and unpacks no tool |
| `AMK_NO_PRELUDE` | Any value skips `__init__.mk` |
| `AMK_<ENGINE>_INIT` | An engine's init chunk, as text or as `@FILE` |
| `XDG_CACHE_HOME`, `HOME` | Where the tools are unpacked: `$XDG_CACHE_HOME`, else `$HOME/.cache` |
| `NO_COLOR` | Keeps warnings plain on a terminal |

<a id="references"></a>

## References

Related pages:

- [Bundling](../README.md#bundling) and [tools](../README.md#tools), what a payload carries from the user's side.
- [The zygote](zygote.md), the other process the same binary runs as.
- [Developers](dev.md#payload-internals), how the payload is assembled at build.

Further reading:

- [The ZIP file format](https://en.wikipedia.org/wiki/ZIP_(file_format)), which an ape's payload is, on Wikipedia.

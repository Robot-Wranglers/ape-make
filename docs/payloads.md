<!-- header # payloads "Payloads" | Boot #boot | Unpack #unpack | Tools #tools | Bundles #bundles | Members #payload-members-with-a-meaning | Running #running-an-ape | Demos #demos | Reference #reference | Refs #references -->
<h1><a id="payloads"></a>Payloads<a href="#references"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-payloads.payloads.8.dark.svg"><img align=right src="img/hdr/docs-payloads.payloads.8.svg" alt="Refs"></picture></a><a href="#reference"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-payloads.payloads.7.dark.svg"><img align=right src="img/hdr/docs-payloads.payloads.7.svg" alt="Reference"></picture></a><a href="#demos"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-payloads.payloads.6.dark.svg"><img align=right src="img/hdr/docs-payloads.payloads.6.svg" alt="Demos"></picture></a><a href="#running-an-ape"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-payloads.payloads.5.dark.svg"><img align=right src="img/hdr/docs-payloads.payloads.5.svg" alt="Running"></picture></a><a href="#payload-members-with-a-meaning"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-payloads.payloads.4.dark.svg"><img align=right src="img/hdr/docs-payloads.payloads.4.svg" alt="Members"></picture></a><a href="#bundles"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-payloads.payloads.3.dark.svg"><img align=right src="img/hdr/docs-payloads.payloads.3.svg" alt="Bundles"></picture></a><a href="#tools"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-payloads.payloads.2.dark.svg"><img align=right src="img/hdr/docs-payloads.payloads.2.svg" alt="Tools"></picture></a><a href="#unpack"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-payloads.payloads.1.dark.svg"><img align=right src="img/hdr/docs-payloads.payloads.1.svg" alt="Unpack"></picture></a><a href="#boot"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-payloads.payloads.0.dark.svg"><img align=right src="img/hdr/docs-payloads.payloads.0.svg" alt="Boot"></picture></a><br clear="all"></h1>
<!-- /header -->

<a id="overview"></a>

## Overview

<a id="an-ape-is-a-zip"></a>

### An ape is a zip

<a id="what-amk-reads-from-its-payload"></a>

### What amk reads from its payload

<a id="order-at-startup"></a>

### Order at startup

<a id="boot"></a>

## Boot

<a id="entry-script"></a>

### The entry script

<a id="arguments-and-the-binarys-path"></a>

### Arguments and the binary's path

<a id="when-boot-is-skipped"></a>

### When boot is skipped

<a id="a-host-without-bash"></a>

### A host without bash

<a id="unpack"></a>

## Unpack

<a id="naming-a-member"></a>

### Naming a member

<a id="destinations"></a>

### Destinations

<a id="freshness-and-force"></a>

### Freshness and force

<a id="unpack-from-a-makefile"></a>

### Unpack from a makefile

<a id="tools"></a>

## Tools

<a id="cache-and-its-key"></a>

### The cache and its key

<a id="order-on-the-path"></a>

### Order on the path

<a id="recursive-make"></a>

### Recursive make

<a id="turning-it-off"></a>

### Turning it off

With `AMK_NO_PATH` set to any value, amk leaves `PATH` as it found it and unpacks nothing
into the cache. A recipe then finds only the host's tools, and with no bash on the host
the prelude falls back to `/bin/sh`.

```bash
AMK_NO_PATH=1 amk -f Makefile
```

<a id="tools-are-apes"></a>

### Tools are apes

<a id="bundles"></a>

## Bundles

<a id="entry-and-its-members"></a>

### The entry and its members

<a id="how-a-bundle-runs"></a>

### How a bundle runs

<a id="naming-rules"></a>

### Naming rules

<a id="directories"></a>

### Directories

<a id="shadowing-by-the-working-directory"></a>

### Shadowing by the working directory

<a id="bundling-a-bundle"></a>

### Bundling a bundle

<a id="editing-the-zip-in-place"></a>

### Editing the zip in place

<a id="payload-members-with-a-meaning"></a>

## Payload members with a meaning

<a id="boot-script"></a>

### The boot script

<a id="entry-makefile"></a>

### The entry makefile

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

<a id="engine-init-chunks"></a>

### Engine init chunks

<a id="library-directory"></a>

### The library directory

<a id="modules"></a>

#### Modules

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
| s7 | `/zip/lib/<name>/init.scm`, for `amk-<name>-...` | unbound variable |

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

<a id="tools-directory"></a>

### The tools directory

<a id="interaction-with-other-features"></a>

## Interaction with other features

<a id="bundles-and-the-zygote"></a>

### Bundles and the zygote

<a id="bundles-and-standard-guests"></a>

### Bundles and standard guests

<a id="recursion-inside-the-binary"></a>

### Recursion inside the binary

<a id="running-an-ape"></a>

## Running an ape

<a id="loader"></a>

### The loader

<a id="exec-bit"></a>

### The exec bit

<a id="subprocess-without-a-shell"></a>

### Subprocess without a shell

<a id="demos"></a>

## Demos

<a id="reference"></a>

## Reference

<a id="cli"></a>

### Command line

<a id="environment-variables"></a>

### Environment variables

<a id="reserved-member-names"></a>

### Reserved member names

<a id="related-patches-and-tests"></a>

### Related patches and tests

<a id="references"></a>

## References

Related pages:

- [Bundling](../README.md#bundling) and [tools](../README.md#tools), what a payload carries from the user's side.
- [The zygote](zygote.md), the other process the same binary runs as.
- [Developers](dev.md#payload-internals), how the payload is assembled at build.

Further reading:

- [The ZIP file format](https://en.wikipedia.org/wiki/ZIP_(file_format)), which an ape's payload is, on Wikipedia.

<a id="payloads"></a>

# Payloads

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

<a id="the-entry-script"></a>

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

<a id="the-cache-and-its-key"></a>

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

<a id="the-entry-and-its-members"></a>

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

<a id="the-boot-script"></a>

### The boot script

<a id="the-entry-makefile"></a>

### The entry makefile

<a id="the-prelude"></a>

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

<a id="the-library-directory"></a>

### The library directory

<a id="the-tools-directory"></a>

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

<a id="the-loader"></a>

### The loader

<a id="the-exec-bit"></a>

### The exec bit

<a id="subprocess-without-a-shell"></a>

### Subprocess without a shell

<a id="demos"></a>

## Demos

<a id="reference"></a>

## Reference

<a id="command-line"></a>

### Command line

<a id="environment-variables"></a>

### Environment variables

<a id="reserved-member-names"></a>

### Reserved member names

<a id="related-patches-and-tests"></a>

### Related patches and tests

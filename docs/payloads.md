# Payloads

## Overview

### An ape is a zip

### What amk reads from its payload

### Order at startup

## Boot

### The entry script

### Arguments and the binary's path

### When boot is skipped

### A host without bash

## Unpack

### Naming a member

### Destinations

### Freshness and force

### Unpack from a makefile

## Tools

### The cache and its key

### Order on the path

### Recursive make

### Turning it off

### Tools are apes

## Bundles

### The entry and its members

### How a bundle runs

### Naming rules

### Directories

### Shadowing by the working directory

### Bundling a bundle

### Editing the zip in place

## Payload members with a meaning

### The boot script

### The entry makefile

### The prelude

Make reads `__init__.mk` before any makefile, the way it reads a `MAKEFILES` entry: a
missing member is silent, and a target in it never becomes the default goal. No shell is
involved and a start costs nothing extra. It sets the defaults every makefile under amk
would otherwise repeat, each one overridable by a later assignment or an environment
knob: `SHELL` from `AMK_SHELL` else bash, `.SHELLFLAGS` from `AMK_SHELLFLAGS` else
`-euo pipefail -c`, `MAKEFLAGS` as silent, stop on error and warn on undefined variables,
`.DEFAULT_GOAL` from `AMK_GOAL` when set, and an exported `__file__` naming the entry
makefile. With patch 0035, a `__main__` target is the default goal whenever the makefile
names none itself, wherever it sits in the file. A host with no bash on `PATH` gets `/bin/sh` with `-eu -c` instead. Once read,
the prelude leaves `MAKEFILE_LIST` again, so the first word of that list still names the
entry makefile and a bundle or a distribution that spells it that way sees no change.
`AMK_NO_PRELUDE` skips it.

### Engine init chunks

### The library directory

### The tools directory

## Interaction with other features

### Bundles and the zygote

### Bundles and standard guests

### Recursion inside the binary

## Running an ape

### The loader

### The exec bit

### Subprocess without a shell

## Demos

## Reference

### Command line

### Environment variables

### Reserved member names

### Related patches and tests

<!-- header # zygote "The Zygote" | ^ ../README.md#zygote | Roles #two-roles-on-one-binary | Lifecycle #lifecycle-of-a-request | Refusal #refusal-and-fallback | Environment #environment | Recursion #recursion | Signals #signals-and-the-terminal | State #state-shared-with-the-parent | Reference #reference | Refs #references -->
<h1><a id="zygote"></a><a href="../README.md#zygote"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-zygote.zygote.up.dark.svg"><img src="img/hdr/docs-zygote.zygote.up.svg" alt="up"></picture></a>The Zygote<a href="#references"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-zygote.zygote.8.dark.svg"><img align=right src="img/hdr/docs-zygote.zygote.8.svg" alt="Refs"></picture></a><a href="#reference"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-zygote.zygote.7.dark.svg"><img align=right src="img/hdr/docs-zygote.zygote.7.svg" alt="Reference"></picture></a><a href="#state-shared-with-the-parent"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-zygote.zygote.6.dark.svg"><img align=right src="img/hdr/docs-zygote.zygote.6.svg" alt="State"></picture></a><a href="#signals-and-the-terminal"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-zygote.zygote.5.dark.svg"><img align=right src="img/hdr/docs-zygote.zygote.5.svg" alt="Signals"></picture></a><a href="#recursion"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-zygote.zygote.4.dark.svg"><img align=right src="img/hdr/docs-zygote.zygote.4.svg" alt="Recursion"></picture></a><a href="#environment"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-zygote.zygote.3.dark.svg"><img align=right src="img/hdr/docs-zygote.zygote.3.svg" alt="Environment"></picture></a><a href="#refusal-and-fallback"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-zygote.zygote.2.dark.svg"><img align=right src="img/hdr/docs-zygote.zygote.2.svg" alt="Refusal"></picture></a><a href="#lifecycle-of-a-request"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-zygote.zygote.1.dark.svg"><img align=right src="img/hdr/docs-zygote.zygote.1.svg" alt="Lifecycle"></picture></a><a href="#two-roles-on-one-binary"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-zygote.zygote.0.dark.svg"><img align=right src="img/hdr/docs-zygote.zygote.0.svg" alt="Roles"></picture></a><br clear="all"></h1>
<!-- /header -->

<a id="overview"></a>

## Overview

<a id="why-parse-once"></a>

### Why parse once

<a id="what-a-request-is"></a>

### What a request is

<a id="two-roles-on-one-binary"></a>

## Two roles on one binary

<a id="serve"></a>

### Serve

<a id="client"></a>

### Client

<a id="selection-by-argv"></a>

### Selection by argv

<a id="lifecycle-of-a-request"></a>

## Lifecycle of a request

<a id="connect"></a>

### Connect

<a id="what-the-request-carries"></a>

### What the request carries

<a id="fork-and-the-fresh-copy"></a>

### Fork and the fresh copy

The same fork backs a [job](job.md): `amk.job.spawn` and its kin fork this parsed image once per job.

<a id="reply"></a>

### The reply

<a id="refusal-and-fallback"></a>

## Refusal and fallback

<a id="options-the-zygote-does-not-hold"></a>

### Options the zygote does not hold

<a id="cold-command"></a>

### The cold command

<a id="a-missing-socket"></a>

### A missing socket

<a id="environment"></a>

## Environment

<a id="handoff-from-a-loader"></a>

### Handoff from a loader

<a id="rearming-parse-time-values"></a>

### Rearming parse-time values

<a id="recursion"></a>

## Recursion

<a id="routing-by-path"></a>

### Routing by path

<a id="depth-and-parse-cost"></a>

### Depth and parse cost

<a id="signals-and-the-terminal"></a>

## Signals and the terminal

<a id="a-signalled-client"></a>

### A signalled client

<a id="interrupts-and-reaping"></a>

### Interrupts and reaping

<a id="foreground-jobs-under-a-served-request"></a>

### Foreground jobs under a served request

<a id="state-shared-with-the-parent"></a>

## State shared with the parent

<a id="files-and-intermediates"></a>

### Files and intermediates

<a id="persistent-guest-state-across-requests"></a>

### Persistent guest state across requests

<a id="init-and-hooks-in-the-zygote"></a>

### Init and hooks in the zygote

<a id="streams-and-descriptors"></a>

## Streams and descriptors

<a id="passing-the-three-descriptors"></a>

### Passing the three descriptors

<a id="platform-layout-of-the-control-message"></a>

### Platform layout of the control message

<a id="limits"></a>

## Limits

<a id="demos"></a>

## Demos

<a id="reference"></a>

## Reference

<a id="cli"></a>

### Command line

<a id="reply-protocol"></a>

### Reply protocol

<a id="exit-statuses"></a>

### Exit statuses

<a id="environment-variables"></a>

### Environment variables

<a id="related-patches-and-tests"></a>

### Related patches and tests

<a id="references"></a>

## References

Related pages:

- [Jobs](job.md) and [jobmen](jobman.md), jobs forked the same way as a served request.
- [Payloads](payloads.md), what the binary carries before it serves.
- [The runtime](runtime.md#multiprocessing), where forks sit among the concurrency flavors.

Further reading:

- [fork](https://en.wikipedia.org/wiki/Fork_(system_call)), [copy-on-write](https://en.wikipedia.org/wiki/Copy-on-write) and [Unix domain sockets](https://en.wikipedia.org/wiki/Unix_domain_socket), on Wikipedia.

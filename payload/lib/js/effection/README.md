# js/effection

[Effection](https://frontside.com/effection), structured concurrency for JavaScript, as
the quickjs engine runs it. This folder is engine-specific by design: the library is
JavaScript, and nothing of it spans the other guests.

## Vendored at Build Time

`init.js` is checked in. The rest lands from the pinned input in the Makefile:

| Package | Version | From | Lands As |
| --- | --- | --- | --- |
| effection | 4.2.0 | [npm](https://www.npmjs.com/package/effection), the esm build | `mod.js`, `experimental.js`, `_dnt.*.js`, `lib/*.js` |

## Why the shims live here

Effection's esm build assumes a browser or node: `setTimeout` and friends,
`AbortController`, `queueMicrotask`, the dispose symbols, a `self`, and `console.error`.
quickjs has none of them, so `init.js` defines each over the `os` and `std` modules before
it re-exports `mod.js`. The library does not load without them, which is why they are
part of this folder rather than of any user of it.

## Using it

Do not import this folder directly. `amk.plex`, from `lib/plex/init.js`, republishes
every export, and is the name the actor group backend and the demos use:

```js
const { run, spawn, scoped, sleep, until } = amk.plex;
```

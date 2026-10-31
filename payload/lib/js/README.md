# js

The quickjs engine's folder. A package here is a bare module specifier, a name with no
leading slash or dot, resolving to `lib/js/<name>/init.js`, else `lib/js/<name>.js`;
`std` and `os` stay the engine's builtins. That is the language's own import; from make,
a single `lib/js/<name>.js` file is a [module](../../../README.md#modules) that
`load <name>.js` imports into js's main state, while a package directory is not.

## Vendored at Build Time

`make build` installs these from the pinned inputs in the Makefile, beside the checked-in
shims that load them:

| Package | Version | From | Lands As |
| --- | --- | --- | --- |
| effection | 4.2.0 | [npm](https://www.npmjs.com/package/effection), the esm build | `effection/mod.js` and `effection/lib/*.js`, beside the checked-in `effection/init.js` |

[effection/README.md](effection/README.md) says why the shims live beside the build.
The topic that publishes it is [`plex/`](../plex/), as `amk.plex`.

## Usage

```js
import { sleep } from "effection";      // lib/js/effection/init.js
const m = await import("effection");    // the same, from a chunk
amk.tspace.out("k", 1);                 // lib/tspace/init.js, a topic
```

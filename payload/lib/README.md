# Overview

Libraries, and sometimes data, which `amk` ships inside its own binary, read in place
from `/zip/lib/` at run time.

A library is either a topic that spans the guests, or owned per engine.

| Path | Holds |
| --- | --- |
| `lib/<topic>/` | one concern for every guest that can host it: `init.amk` for make, and one binding per engine beside it |
| `lib/<eng>/` | one engine's own: vendored packages on its module path, and the one-engine library that cannot span |
| `lib/amk/<name>.amk`, `lib/amk/<name>.mk` | make's own: a library in make alone, read by `$(amk.include <name>)` or `load <name>`; `.amk` when it carries at lines, tried first |

**Topic folders span guests.** A folder under `lib/<topic>/` is the place for every
guest's binding of one concern, in that guest's own idiom. Bindings need not share api
spellings with their siblings. [tspace/](tspace/) spells `in` as `in_` where a language
needs it to avoid a keyword collision, and [plex/](plex/) offers Effection's names
in js but `fork`, `yield` and `done` in its `init.scm`.

**Engine folders hold what cannot span.** Vendored or home-grown, it belongs to one
language and not several. A vendored library may need shims or patches before an embedded
engine can load it at all: micropy has limited `os` and `re` modules, so `utemplate`
stands in for jinja to avoid patching. Small things are vendored directly, as lua's
`dkjson` is; large things land at build time instead, as [js/effection/](js/effection/)
does. Something built on top of a vendored library belongs in a topic, not beside it.

**Other policies:**

- **Stock libraries carry no amk.** [s7/amb.scm](s7/amb.scm) and [plex/](plex/)`init.scm`
  load in any s7; nothing in them names `amk-`. A library that reaches make through the
  ffi is a binding, and lives in a topic that has an `init.amk`.
- **A build ships what its engines can host.** The Makefile's `payload.<topic>` rule
  includes each binding only when its engine is in the build, and a topic that needs a
  library ships only when that library does; [actor/](actor/) needs `effection` and `jq`.
- **Every engine folder has a README**, since its contents are mostly not source: it says
  what lands there at build and what the folder's import spelling is. A topic gets one
  when it is a library in its own right.

## Catalog

| Path | Kind | Spans |
| --- | --- | --- |
| [tspace/](tspace/) | topic: tuple spaces over sqlite workspaces | make, lua, micropy, js, s7 |
| [actor/](actor/) | topic: actor groups and their backends | make; js under the effection backend, s7 under the s7 backend; lua and micropy as members |
| [plex/](plex/) | topic: the plex a backend schedules on, multiplexing tasks onto one thread of the engine | js, Effection republished; s7, a cooperative ready list of continuations |
| [jobman/](jobman/) | `amk.jobman.<pool>`, each guest's jobman, its handle on a pool of jobs: spawns under the pool's bound, waits, and maps goal lists. `load dsys/jobman` opens pools with `@jobman` above a JSON define, and the default `__jobs__` pool, sized by `AMK_MAX_JOBS` else `jobman.max_jobs` | lua, micropy, js, s7 |
| [dsys/](dsys/) | topic: structures built on the `amk.pool` builtins, which need no topic; `@pool` above a JSON define declares a pool over the baseline, `amk.mutex` and `amk.horcrux` make locks, and `amk.rendezvous` a channel whose send waits until received | make, with jq |
| [js/](js/) | engine: [effection/](js/effection/), the vendored Effection build and its host shims | js |
| [micropy/](micropy/) | engine: on micropython's path; `asyncio`, `mip`, `requests`, `utemplate` and `ssl` land here at build | micropy |
| [lua/](lua/) | engine: on lua's path; `dkjson.lua` lands here at build | lua |
| [s7/](s7/) | engine: on s7's load path; [amb.scm](s7/amb.scm), delimited control and choice | s7 |
| [amk/](amk/) | engine: make's own; `bash.amk`, `mip.amk` and `utmpl.amk`, each a library reached through make | make |

## Usage

A topic is reached by its name through the engine's `amk` handle. An engine folder is on
that engine's own import path and is reached by the language's plain import, and from
make a single file in it is a [module](../../README.md#modules) that `load` takes by bare
name. The two guest spellings do not meet: a package under `lib/micropy/foo/` is `foo`, never `amk.foo`, and
a topic's binding under `lib/foo/__init__.py` is `amk.foo`, never `foo`. Each form below
is pinned by `tests/test_libpath.py` against the built binary.

### make

`$(amk.include <name>)` reads `lib/amk/<name>.amk` or `.mk` when there is one, else the topic's
`lib/<name>/init.amk`. The `load` directive reads an engine folder's file into that engine
by bare name, and a bare name no engine claims falls back to the same lookup as
`amk.include`, so the two agree. `AMKPATH` adds roots laid out like this folder, searched
ahead of it by both; the full order is in [README.md#modules](../../README.md#modules):

```Makefile
$(amk.include utmpl)     # lib/amk/utmpl.amk, a library with at lines
$(amk.include tspace)    # lib/tspace/init.amk, the topic's make binding
load dkjson.lua          # lib/lua/dkjson.lua, imported into lua's main state
load tspace              # the same file as the include above, once
```

### lua

A topic is `amk.<name>`, from its `init.lua`. A module under `lib/lua/` is on
`package.path` as `/zip/lib/lua/?.lua`:

```lua
local json = require("dkjson")          -- lib/lua/dkjson.lua
amk.tspace.out("k", 1)                  -- lib/tspace/init.lua
require("tspace")                       -- fails: a topic is a module of amk alone
```

### micropy

A topic is `amk.<name>`, from its `__init__.py`, loaded on first use; it is an attribute of
`amk`, not an `import` statement. A package under `lib/micropy/` is on `sys.path`:

```python
import utemplate                        # lib/micropy/utemplate/
import amk
amk.tspace.out("k", 1)                  # lib/tspace/__init__.py
import tspace                           # fails: a topic is a module of amk alone
```

### js

A topic is `amk.<name>`, from its `init.js`, an es module. A package under `lib/js/` is a
bare specifier, a name with no leading slash or dot, resolving to `lib/js/<name>/init.js`
or else `lib/js/<name>.js`; `std` and `os` stay the engine's builtins:

```js
import { sleep } from "effection";      // lib/js/effection/init.js
const m = await import("effection");    // the same, from a chunk
amk.tspace.out("k", 1);                 // lib/tspace/init.js
```

### s7

A topic loads on the first unbound `amk-<name>-...` symbol, from its `init.scm`. A file
under `lib/s7/` is reached by name, since `/zip/lib/s7` is on `*load-path*`; a binding
that builds on one loads it under a guard, so a second loader is free:

```scheme
(load "amb.scm")                                   ; lib/s7/amb.scm
(amk-tspace-out "k" 1)                             ; lib/tspace/init.scm, loaded by the symbol
(unless (defined? 'amb) (load "amb.scm" (rootlet)))  ; inside a binding
```

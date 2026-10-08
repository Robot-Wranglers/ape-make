# lua

The lua engine's folder, on its `package.path` as `/zip/lib/lua/?.lua`. From make, a file
here is a [module](../../../README.md#modules): `load dkjson.lua` imports it into lua's
main state by bare name.

## Vendored at Build Time

Nothing here is checked in. `make build` installs these from the pinned inputs in the
Makefile:

| Package | Version | From | Lands As |
| --- | --- | --- | --- |
| dkjson | 2.8 | [dkolf.de](http://dkolf.de/dkjson-lua/) | `dkjson.lua` |

## Usage

```lua
local json = require("dkjson")          -- lib/lua/dkjson.lua
amk.tspace.out("k", 1)                  -- lib/tspace/init.lua, a topic
require("tspace")                       -- fails: a topic is a module of amk alone
```

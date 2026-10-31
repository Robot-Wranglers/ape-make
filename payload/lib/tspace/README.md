# tspace

Linda tuple spaces over sqlite workspaces, for make, recipes and every state engine. A
space holds tuples; a tuple is a json array of fields; a pattern is a tuple whose fields
may be formals such as `?int`, matched by type alone. The full reference is
[docs/tspace.md](../../../docs/tspace.md); this page is the folder.

| File | Guest | Reached As |
| --- | --- | --- |
| `init.amk` | make | `$(amk.include tspace)`, or `load tspace`, which reaches the same file by the same [lookup](../../../README.md#modules); the default space `tuplespace` and `$(tspace.create name[, backing])` for more |
| `init.lua` | lua | `amk.tspace`, and `amk.tspace["name"]` or `amk.tspace.on("name")` for a named space |
| `__init__.py` | micropy | `amk.tspace`, and `amk.tspace["name"]` or `amk.tspace.on("name")` |
| `init.js` | js | `amk.tspace`, and `amk.tspace["name"]` or `amk.tspace.on("name")` |
| `init.scm` | s7 | `amk-tspace-out` and the other verbs, and `(amk-tspace-on "name")` |

The schema and every verb live in `init.amk`; each binding is a thin spelling of the same
requests in its own language, with that language's types as formals. The space's owner is
the parse process, and a recipe, guest target or spawned job reaches it through the ask
channel, so one run has one set of spaces.

## Verbs

| Verb | Does |
| --- | --- |
| `out` | stores a tuple |
| `read`, `rdp`, `inp` | every match, one match, one match taken; none of them waits |
| `in`, `rd`, `no` | take one, read one, wait for absence; each waits until the space answers, so only from a process of its own |
| `all`, `set`, `out_all`, `in_all` | the whole space, replaced, added to, taken by pattern |
| `urdp`, `uinp`, `urd`, `uin` | the uniform forms, a random match rather than the oldest |
| `out_s`, `rd_s`, `in_s` | a handler registered by name with its pattern, the registry, one removed |

A handler is a make function a matching `out` is routed to instead of storing the tuple;
`@space.reflex <engine> (field=type, ...)` above a define registers its body as one.

```Makefile
$(amk.include tspace)
$(tspace.create shop)

@shop.reflex lua (order, item=str, qty=int)
define price
  shop.out("priced", item, qty * 4)
endef

report:
	${tspace.sh} && shop.out order tea 3 && shop.all
```

`${tspace.sh}` in a recipe defines `tspace` and one shell function per space and verb over
the ask channel. `demos/tuplespace-1.amk` and `tuplespace-reactor.amk` show the verbs and
handlers in three guests, `tuplespace-todo.amk` a file-backed space, and
`tuplespace-actors.amk` actors whose mailboxes are a space.

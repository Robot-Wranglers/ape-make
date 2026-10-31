<!-- header # io "`mod :: amk.io`" |JSON #json | Builtins #builtins | Errors #errors | Demos #demos | Refs #references -->
<h1><a id="io"></a><a href="../README.md#module-index"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-io.io.up.dark.svg"><img src="img/hdr/docs-io.io.up.svg" alt="up to the module index"></picture></a><a href="../README.md#module-index"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-io.io.mod.dark.svg"><img src="img/hdr/docs-io.io.mod.svg" alt="mod"></picture></a><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-io.io.title.dark.svg"><img src="img/hdr/docs-io.io.title.svg" alt=" :: amk.io"></picture><a href="#references"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-io.io.4.dark.svg"><img align=right src="img/hdr/docs-io.io.4.svg" alt="Refs"></picture></a><a href="#demos"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-io.io.3.dark.svg"><img align=right src="img/hdr/docs-io.io.3.svg" alt="Demos"></picture></a><a href="#errors"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-io.io.2.dark.svg"><img align=right src="img/hdr/docs-io.io.2.svg" alt="Errors"></picture></a><a href="#builtins"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-io.io.1.dark.svg"><img align=right src="img/hdr/docs-io.io.1.svg" alt="Builtins"></picture></a><a href="#json"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-io.io.0.dark.svg"><img align=right src="img/hdr/docs-io.io.0.svg" alt="JSON"></picture></a><br clear="all"></h1>
<!-- /header -->

<a id="overview"></a>

The `io` module reads and checks data held in defines. Its first part is [`io/json`](json.md):
JSON written as JSON5, and JSON checked against a JSON Schema, both in this process with
engines amk already carries.

| Line | Brings | Needs |
| --- | --- | --- |
| `load io/json` | [`@json5`](json.md#syntax), [`@json.schema`](json.md#syntax) and [`json.validate`](json.md#api) | jq, sqlite |

<a id="json"></a>

## JSON

`load io/json` turns a define into checked JSON data. A define may be written as
JSON5, with comments, trailing commas and unquoted keys, and checked against a schema
that is itself a define:

```Makefile
load io/json

define order.schema
  { type: "object", required: ["qty"], properties: { qty: { type: "integer", minimum: 1 } } }
endef

@json.schema (order.schema)
@json5
define order
  { qty: 3, }  // checked as the makefile is read
endef
```

[The json page](json.md) is the reference:

| For | See |
| --- | --- |
| What JSON5, a schema define and a check are | [Concepts](json.md#concepts) |
| The two at lines and what each does to its define | [Syntax](json.md#syntax) |
| `json.validate`, the check on demand | [API](json.md#api) |
| Which schema keywords are checked | [Keywords](json.md#keywords) |

<a id="builtins"></a>

## Builtins

JSON5 is read by a builtin every amk with sqlite has, with or without `load io/json`:

| Form | Answers |
| --- | --- |
| `$(amk.json5 text)` | the text, JSON5, as plain JSON on one line; fatal when it does not parse |
| `$(amk.val.json5 name)` | the value of the define `name`, read the same way; the value unchanged in an amk without sqlite |

The decorators that read a define as JSON, [`@actor.group`](actor.md), [`@petri`](petri.md),
`@kahn`, `@workflow`, [`@pool`](dsys.md#pool-decorator), [`@jobman`](jobman.md#syntax),
[`@tspace`](tspace.md) and [`@mip.install`](mip.md), read it through these, so each of their bodies
may be JSON5.

<a id="errors"></a>

## Errors

See also [json errors](json.md#errors).

| Condition | Message |
| --- | --- |
| Text that is not JSON5 | `amk.json5: malformed JSON` |
| `amk.json5` in an amk without sqlite | `amk.json5: this amk has no sqlite, which parses JSON5` |

<a id="demos"></a>

## Demos

| Demo | Shows |
| --- | --- |
| [`json-schema.amk`](../demos/json-schema.amk) | a JSON5 schema, an order checked against it as it is read, and a bad order's errors on demand |
| [`supervise-3.amk`](../demos/supervise-3.amk) | an actor charter written as JSON5, with a comment on each key |

<a id="references"></a>

## References

- [JSON](json.md), the `io/json` reference.
- [Actors](actor.md#schema), [Petri nets](petri.md) and [tuple spaces](tspace.md), whose
  charters have schemas beside their decorators, as `lib/<topic>/schema/<decorator>.json`.
- [JSON5](https://json5.org/), the format.
- [JSON Schema](https://json-schema.org/), draft 2020-12.

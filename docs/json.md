<!-- header # json "`mod :: io/json`" |Concepts #concepts | Syntax #syntax | API #api | Keywords #keywords | Errors #errors | Demos #demos | Refs #references -->
<h1><a id="json"></a><a href="io.md"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-json.json.up.dark.svg"><img src="img/hdr/docs-json.json.up.svg" alt="up to io"></picture></a><a href="../README.md#module-index"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-json.json.mod.dark.svg"><img src="img/hdr/docs-json.json.mod.svg" alt="mod"></picture></a><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-json.json.title.dark.svg"><img src="img/hdr/docs-json.json.title.svg" alt=" :: io/json"></picture><a href="#references"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-json.json.6.dark.svg"><img align=right src="img/hdr/docs-json.json.6.svg" alt="Refs"></picture></a><a href="#demos"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-json.json.5.dark.svg"><img align=right src="img/hdr/docs-json.json.5.svg" alt="Demos"></picture></a><a href="#errors"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-json.json.4.dark.svg"><img align=right src="img/hdr/docs-json.json.4.svg" alt="Errors"></picture></a><a href="#keywords"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-json.json.3.dark.svg"><img align=right src="img/hdr/docs-json.json.3.svg" alt="Keywords"></picture></a><a href="#api"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-json.json.2.dark.svg"><img align=right src="img/hdr/docs-json.json.2.svg" alt="API"></picture></a><a href="#syntax"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-json.json.1.dark.svg"><img align=right src="img/hdr/docs-json.json.1.svg" alt="Syntax"></picture></a><a href="#concepts"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-json.json.0.dark.svg"><img align=right src="img/hdr/docs-json.json.0.svg" alt="Concepts"></picture></a><br clear="all"></h1>
<!-- /header -->

<a id="overview"></a>
`io/json` makes a define into JSON data that is checked when the makefile is
read. A body may be written as JSON5, and a schema is a define too, so the data and its
contract sit side by side in the makefile:

```Makefile
load io/json

define order.schema
  {
    type: "object",
    required: ["item", "qty"],
    additionalProperties: false,
    properties: {
      item: { enum: ["tea", "cake"] },
      qty: { type: "integer", minimum: 1 },  // never a fraction
    },
  }
endef

@json.schema (order.schema)
@json5
define order
  { item: 'tea', qty: 3, }
endef

all:
	echo '$(order)'
	echo '$(json.validate order, order.schema)'
```

The first line prints `{"item":"tea","qty":3}` and the second prints nothing, since the
order is valid. JSON5 is read by sqlite and schemas are checked by jq, both linked into
amk, so nothing runs in a shell. It is part of [the io module](io.md).

<a id="concepts"></a>

## Concepts

| Term | Meaning |
| --- | --- |
| JSON5 | JSON with comments, trailing commas, unquoted keys, single-quoted strings and hex numbers; see [json5.org](https://json5.org/) |
| Plain JSON | the same value written as strict JSON on one line, as sqlite's `json()` writes it |
| Schema Define | a define whose body is a [JSON Schema](https://json-schema.org/), draft 2020-12, in JSON or JSON5 |
| Check | the body read as JSON5 and validated against a schema define, answering every error |

<a id="syntax"></a>

## Syntax

| Form | Does |
| --- | --- |
| `@json5` above `define name ... endef` | rewrites the body as plain JSON, so every later reference to `$(name)` reads strict JSON |
| `@json.schema (schema)` above `define name ... endef` | checks the body against the define `schema` as the makefile is read; any error stops make |

Both read the body as JSON5, so they stack in either order, and `@json.schema` alone checks
a JSON5 body without rewriting it.

<a id="api"></a>

## API

| Form | Answers |
| --- | --- |
| `$(json.validate name, schema)` | the errors of the define `name` against the define `schema`, joined by `; `; nothing when it is valid |

Each error names its path, as in
`Property item: Value not in enum; Property qty: Less than minimum 1`. The check is
[schema.jq](https://github.com/yne/schema.jq), a validator written in jq, shipped as
`lib/io/schema.jq`.

<a id="keywords"></a>

## Keywords

| Keywords | Checked |
| --- | --- |
| `type`, `enum`, `const` | yes |
| `properties`, `required`, `additionalProperties`, `patternProperties`, `propertyNames`, `minProperties`, `maxProperties`, `dependentRequired`, `dependentSchemas` | yes |
| `items`, `prefixItems`, `contains`, `minContains`, `maxContains`, `minItems`, `maxItems`, `uniqueItems` | yes |
| `minimum`, `maximum`, `exclusiveMinimum`, `exclusiveMaximum`, `multipleOf`, `minLength`, `maxLength`, `pattern` | yes |
| `allOf`, `anyOf`, `oneOf`, `not`, `if`, `then`, `else` | yes |
| `$ref` within the schema, by pointer or anchor | yes; a ref that does not resolve is an error |
| `unevaluatedProperties`, `unevaluatedItems`, `$dynamicRef`, `$dynamicAnchor`, `format` | no |
| `default`, `description`, `title` | annotations, never checked |

<a id="errors"></a>

## Errors

See also [io errors](io.md#errors).

| Condition | Message |
| --- | --- |
| `@json.schema` with no schema named | `order: @json.schema needs a schema, as (name)` |
| A body that fails its schema | `order: does not meet order.schema: Missing required: qty` |
| A `$ref` that does not resolve | `Unresolved $ref nowhere.json`, among the errors |
| A body or schema that is not JSON5 | `amk.json5: malformed JSON` |
| An amk without jq or sqlite | `amk.require`'s message naming the missing one |

<a id="demos"></a>

## Demos

| Demo | Shows |
| --- | --- |
| [`json-schema.amk`](../demos/json-schema.amk) | a JSON5 schema, an order checked and rewritten as it is read, and a bad order's three errors from `json.validate` |

<a id="references"></a>

## References

- [The io module](io.md), and its JSON5 builtins.
- [Actors](actor.md#schema), whose charter schema is a model for one of your own.
- [JSON5](https://json5.org/) and [JSON Schema 2020-12](https://json-schema.org/draft/2020-12).
- [schema.jq](https://github.com/yne/schema.jq), the validator, under the two-clause Berkeley license.

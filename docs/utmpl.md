<!-- header # utemplate "`mod :: amk.utmpl`" |Concepts #concepts | Syntax #syntax | API #api | Usage #usage | Errors #errors | Demos #demos | Refs #references -->
<h1><a id="utemplate"></a><a href="../README.md#module-index"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-utmpl.utemplate.up.dark.svg"><img src="img/hdr/docs-utmpl.utemplate.up.svg" alt="up to the module index"></picture></a><a href="../README.md#module-index"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-utmpl.utemplate.mod.dark.svg"><img src="img/hdr/docs-utmpl.utemplate.mod.svg" alt="mod"></picture></a><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-utmpl.utemplate.title.dark.svg"><img src="img/hdr/docs-utmpl.utemplate.title.svg" alt=" :: amk.utmpl"></picture><a href="#references"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-utmpl.utemplate.6.dark.svg"><img align=right src="img/hdr/docs-utmpl.utemplate.6.svg" alt="Refs"></picture></a><a href="#demos"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-utmpl.utemplate.5.dark.svg"><img align=right src="img/hdr/docs-utmpl.utemplate.5.svg" alt="Demos"></picture></a><a href="#errors"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-utmpl.utemplate.4.dark.svg"><img align=right src="img/hdr/docs-utmpl.utemplate.4.svg" alt="Errors"></picture></a><a href="#usage"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-utmpl.utemplate.3.dark.svg"><img align=right src="img/hdr/docs-utmpl.utemplate.3.svg" alt="Usage"></picture></a><a href="#api"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-utmpl.utemplate.2.dark.svg"><img align=right src="img/hdr/docs-utmpl.utemplate.2.svg" alt="API"></picture></a><a href="#syntax"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-utmpl.utemplate.1.dark.svg"><img align=right src="img/hdr/docs-utmpl.utemplate.1.svg" alt="Syntax"></picture></a><a href="#concepts"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-utmpl.utemplate.0.dark.svg"><img align=right src="img/hdr/docs-utmpl.utemplate.0.svg" alt="Concepts"></picture></a><br clear="all"></h1>
<!-- /header -->

<a id="overview"></a>
Built-in, jinja-style templating is supported with the `utmpl.amk` module.  Besides being a module, `utmpl` is a *stacked engine*, i.e. it partially implements the interface for [amk's language-engine API](FFI.md#stacked-engines), which allows it to contribute new [decorator grammar](FFI.md#decorators).

```Makefile
load utmpl
```

<a id="see-also"></a>

It builds on:

* upstream utemplate library[^utemplate] (1.4.1 bundled by default)
* amk's [micropy engine](../README.md#micropy)
* utmpl [module source](../payload/lib/amk/utmpl.amk), a thin wrapper on the above, providing the grammar

<a id="concepts"></a>

## Concepts

| Term | Meaning |
| --- | --- |
| Template | a define's body, or inline text, rendered by utemplate with jinja-style statements and expressions |
| Data Variable | a make variable holding json, named on a decorator line or passed to a render form |
| Merge | the data variables on one line combine left to right, a target's `name/var` after them |
| `name=value` word | one name set as a string, on top of the merged data |
| Goal Word | `name=>>goal<<`, a name whose value is a goal's, on `@utmpl.target` only |
| In Place | rendered once at parse time, the result held under the define's name |

<a id="syntax"></a>
<a id="forms"></a>

## Syntax

The decorator form renders a define in place, with its data on the decorator line:

```Makefile
load utmpl

@utmpl name=world
define greeting
  Hello, {{ name }}!
endef

$(info $(greeting))     # Hello, world!
```

| Form | Renders | When |
| --- | --- | --- |
| `@utmpl.target var... name=value...`, also `@utmpl.import.target` | the define as a target: `name/var` adds the json in `var`, and `name` with no words reads stdin | when the target runs |
| `@utmpl var... name=value...` | the define, in place; its name then holds the result | at parse time, once |
| `@utmpl.import` | nothing yet: `$(name var)` becomes a make function that renders the define | each call |

The words on an `@utmpl` or `@utmpl.target` line build the data. Each data variable holds
a json object, and they merge left to right; a target's `name/var` merges after them. Each
`name=value` word then sets one name, as a string. A lone source of data may hold any json,
for a template with its own `{% args %}` line.

On `@utmpl.target`, a word's value may be a goal, `name=>>goal<<`: the goal becomes a
prerequisite, and its value, as a string, is the name's. A plain recipe target that prints
is a goal like any other; see [values](dataflow.md#values). A value passes intact unless it
holds three double quotes in a row, which json never does.
`@utmpl` renders at parse time, before any goal runs, so a goal word there stops make.

A define's template is dedented before it compiles, so indent it like any other body.
Inline text is expanded by make first; a define's template is used as written, so a dollar
in it is literal. An include statement, `{% include "path" %}`, splices another
template file into the define, rendered with the same data; the path is read from the
working directory, and the included file is used as written, not dedented.

<a id="api"></a>

## API

The render forms are make functions. utmpl has no guest binding: it runs in the
[micropy engine](../README.md#micropy), and a guest reaches these through `amk.call` like
any make function.

<a id="api-make"></a>

### make

| Form | Renders | When |
| --- | --- | --- |
| `$(utmpl.render name, var)` | a target's template, with the json in `var` | at parse time |
| `$(utmpl text, var)` | inline text, with the json in `var` | at parse time |
| `$(name var)`, after `@utmpl.import` | the define, with the json in `var` | each call |

<a id="usage"></a>
<a id="examples"></a>

## Usage

<a id="inline"></a>
<a id="in-place"></a>

### Render in Place

The forms that render at parse time, before any goal runs: inline text, a decorated define
rendered in place, `name=value` words, words laid over a data variable, and a file included
by path.

```Makefile
load utmpl

define release.data
  { "project": "myproject", "version": "0.1",
    "engines": [
      {"name": "e1", "version": "v1"},
      {"name": "e2", "version": "v2"} ] }
endef

# Inline text is expanded by make first, then rendered with the data.
title := $(utmpl {{project}} {{version}}, release.data)

# A decorated define renders once, in place; its name then holds the result.
@utmpl release.data
define changelog.md
  ## {{project}}
  {% for e in engines %}
  - {{e["name"]}} {{e["version"]}}
  {% endfor %}
endef

# Words on the decorator line are the template's names, as strings.
@utmpl who=world mood=calm
define greeting
  hello {{who}}, stay {{mood}}
endef

# Words go on top of the data, so one field changes and the rest stays.
@utmpl release.data version=0.2
define next
  {{project}} {{version}}
endef

# An include statement splices a template file, by path, with the same data.
@utmpl release.data
define page.md
  {{project}} release notes
  {% include "demos/utmpl-footer.tpl" %}
endef

inline:
	test "$(title)" = "myproject 0.1"
	echo "inline: $(title)"

in-place:
	test "$(firstword $(changelog.md))" = "##"
	test -n "$(findstring e2 v2,$(changelog.md))"
	$(info in place: $(changelog.md))

words:
	test "$(greeting)" = "hello world, stay calm"
	echo "words: $(greeting)"

words-over-data:
	test "$(next)" = "myproject 0.2"
	echo "words over data: $(next)"

include:
	test "$(lastword $(page.md))" = "--"
	test -n "$(findstring rendered by amk,$(page.md))"
	$(info include: $(page.md))

__main__: inline in-place words words-over-data include
```

<a id="functions"></a>

### Functions

A define becomes a make function of its name; each call renders it with the data variable
it is given, so one template serves many data sets and composes with make's own functions.

```Makefile
load utmpl

release.data = {"project": "myproject", "version": "0.1"}
other.data = {"project": "other", "version": "9"}

# An imported template is a make function over any data variable.
@utmpl.import
define badge
  [{{project}}-{{version}}]
endef

# A function composes with make's own: here, one badge per data variable.
badges = $(foreach d,$(1),$(badge $(d)))

one:
	test "$(badge release.data)" = "[myproject-0.1]"
	echo "one call: $(badge release.data)"

many:
	test "$(call badges,release.data other.data)" = "[myproject-0.1] [other-9]"
	echo "two calls: $(call badges,release.data other.data)"

# A template with its own args line takes the data whole, so it may be any json.
@utmpl.import
define pair
  {% args d %}
  {{d[0]}}+{{d[1]}}
endef
pair.data = [1, 2]

own-args:
	test "$(pair pair.data)" = "1+2"
	echo "own args: $(pair pair.data)"

# utmpl defines no exec; registration made the form stop make with a message.
refused:
	out=$$(${amk} missing 2>&1 || true); case "$$out" in \
	  *"does not define utmpl.exec"*) echo "refused: utmpl.exec";; \
	  *) echo "$$out"; exit 1;; esac
missing:
	echo "$(utmpl.exec print(1))"

__main__: one many own-args refused
```

<a id="targets"></a>

### Targets

A define becomes a target that renders when it runs. The data comes from a stem,
`name/var`, from json on stdin, or the template renders at parse time through the render
form in [the API](#api-make). A command's json output feeds a target the same way.

```Makefile
load utmpl

@utmpl.target
define release.md
  {{project}} {{version}}
  ===
  {% for e in engines %}
  - {{e["name"]}} {{e["version"]}}
  {% endfor %}
endef

define release.data
  { "project": "myproject", "version": "0.1",
    "engines": [
      {"name": "e1", "version": "v1"},
      {"name": "e2", "version": "v2"} ] }
endef

# Data mode: the stem names the variable that holds the json.
stem:
	test "$$(${amk} release.md/release.data | head -1)" = "myproject 0.1"
	${amk} release.md/release.data

# Stream mode: json on stdin, so any producer can feed the template.
piped.data = {"project": "piped", "version": "0.2", "engines": []}
stdin:
	test "$$(echo '$(piped.data)' | ${amk} release.md | head -1)" = "piped 0.2"
	echo '$(piped.data)' | ${amk} release.md

# Library mode: the same template rendered at parse time, no target run.
render:
	test "$(words $(utmpl.render release.md, release.data))" = "9"
	echo "$(words $(utmpl.render release.md, release.data)) words at parse time"

# The listing is one json object; the template reads its engines key directly.
listing := $(amk.bash $(MAKE) --list-engines)

@utmpl.target
define engines.md
  | engine | implementation | version |
  | --- | --- | --- |
  {% for e in engines %}
  | {{e["name"]}} | {{e["implementation"]}} | {{e["version"]}} |
  {% endfor %}
endef

table:
	test "$$(${amk} engines.md/listing | grep -c '^|')" -gt 2
	${amk} engines.md/listing

__main__: stem stdin render table
```

<a id="doc-flow"></a>

### Doc Flow

When templates meet [dataflow-style](dataflow.md#dataflow), that's docflow.  It works by using [goal-substitution syntax](grammar.md#goal-substitution): a word on the decorator line names a goal, `name=>>goal<<`, the goal becomes a prerequisite, and its value is the name's. A goal is named on the decorator line, never inside the template: the body reaches the renderer as written, so `>>goal<<` in it stays text.

```Makefile
load utmpl

# A plain recipe target: what it prints is its value.
engines.list:
	echo $(.ENGINES)

# An imported target: a goal word in its body is the same substitution.
@micropy.target
define longest
  print(max(">>ENGINES.LIST<<".split(), key=len))
endef

# A goal word: the goal becomes a prerequisite and its value the name's.
@utmpl.target project=myproject engines=>>ENGINES.LIST<< longest=>>LONGEST<<
define summary.md
  {{project}} runs on {{ len(engines.split()) }} engines, {{longest}} longest
endef

# Two templates may read the same goal; it still runs once per run.
@utmpl.target engines=>>ENGINES.LIST<<
define banner.md
  == {{ engines.replace(" ", " | ") }} ==
endef

# A rendered template is a goal too, so a page can be built from parts.
@utmpl.target title=Release summary=>>SUMMARY.MD<< banner=>>BANNER.MD<<
define page.md
  {{title}} notes
  Summary: {{summary}}
  Banner: {{banner}}
endef

check.summary:
	test "$$(${amk} summary.md | cut -d' ' -f1,2,3)" = "myproject runs on"
	${amk} summary.md

check.banner:
	test "$$(${amk} banner.md | cut -d' ' -f1)" = "=="
	${amk} banner.md

check.page:
	test "$$(${amk} page.md | wc -l | tr -d ' ')" = "3"
	${amk} page.md

__main__: check.summary check.banner check.page
```

<a id="errors"></a>

## Errors

Each one stops make with a `utmpl:` message.

| Cause | Message |
| --- | --- |
| No variable holds the data | `utmpl: no variable named var holds the data` |
| The data is not json | `utmpl: var is not json: ...` |
| The template raises, a name the data lacks included | `utmpl: name did not render: NameError: ...` |
| A variable to merge holds no json object | `utmpl: var holds no json object to merge` |
| An included file cannot be read | `utmpl: name includes a file it cannot read: ...` |
| A goal word on `@utmpl` | `utmpl: @utmpl over name renders at parse time; k=>>goal<< needs @utmpl.target` |
| A form utmpl does not define: `@utmpl.argv`, `utmpl.exec`, `@utmpl.exec`, `utmpl.ns` | `stacked engine utmpl does not define utmpl.ns` |

<a id="demos"></a>

## Demos

One per use case; each section of [usage](#usage) embeds one of them.

| Demo | Shows |
| --- | --- |
| [`utmpl-inplace.amk`](../demos/utmpl-inplace.amk) | the forms that render at parse time; under [render in place](#in-place) |
| [`utmpl-functions.amk`](../demos/utmpl-functions.amk) | a define as a make function, one template over many data sets; under [functions](#functions) |
| [`utmpl-targets.amk`](../demos/utmpl-targets.amk) | a define as a target, its data from a stem, stdin or a command; under [targets](#targets) |
| [`utmpl-docflow.amk`](../demos/utmpl-docflow.amk) | templates over dataflow goals, by goal words; under [doc flow](#doc-flow) |

<a id="references"></a>

## References

- [micropy](../README.md#micropy), the engine templates render in.
- [Dataflow](dataflow.md#dataflow), for a document target that re-renders when its data changes.
- [Grammar](grammar.md#goal-substitution), for goal substitution in a target's name.
- [Template processors](https://en.wikipedia.org/wiki/Template_processor) and [Jinja](https://en.wikipedia.org/wiki/Jinja_(template_engine)), whose syntax utemplate follows, on Wikipedia.

[^utemplate]: utemplate, a micro template engine for MicroPython, [pypi.org/project/utemplate](https://pypi.org/project/utemplate/), with source at [github.com/pfalcon/utemplate](https://github.com/pfalcon/utemplate).

<!-- header # grammar-index "Grammar Index" | ^ ../README.md#extended-grammar | Decorators #define-block-decorators | Arguments #decorator-arguments | Goals #goal-substitution | Abbreviated #abbreviated-define-blocks | Refs #references -->
<h1><a id="grammar-index"></a><a href="../README.md#extended-grammar"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-grammar.grammar-index.up.dark.svg"><img src="img/hdr/docs-grammar.grammar-index.up.svg" alt="up"></picture></a>Grammar Index<a href="#references"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-grammar.grammar-index.4.dark.svg"><img align=right src="img/hdr/docs-grammar.grammar-index.4.svg" alt="Refs"></picture></a><a href="#abbreviated-define-blocks"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-grammar.grammar-index.3.dark.svg"><img align=right src="img/hdr/docs-grammar.grammar-index.3.svg" alt="Abbreviated"></picture></a><a href="#goal-substitution"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-grammar.grammar-index.2.dark.svg"><img align=right src="img/hdr/docs-grammar.grammar-index.2.svg" alt="Goals"></picture></a><a href="#decorator-arguments"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-grammar.grammar-index.1.dark.svg"><img align=right src="img/hdr/docs-grammar.grammar-index.1.svg" alt="Arguments"></picture></a><a href="#define-block-decorators"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-grammar.grammar-index.0.dark.svg"><img align=right src="img/hdr/docs-grammar.grammar-index.0.svg" alt="Decorators"></picture></a><br clear="all"></h1>
<!-- /header -->

The extended grammar that amk-lang provides over pure Makefile is small, mostly sugar, always optional.  It's introduced in several places, but only as needed, and abbreviated so that details won't distract.  This page serves as both a catalog and a more complete reference.

<a id="define-block-decorators"></a>

## Define Block Decorators

 The most important piece, documented on the main page [here](../README.md#extended-grammar).

Example Usage:

```Makefile 
@my_decorator
define my_block
 ...
endef
```

<a id="decorator-arguments"></a>

## Decorator Arguments

One grammar for every decorator, parsed by the preprocessor; what each piece means is the
decorator's own. The pieces a macro reads are in the [FFI doc](FFI.md#decorators).

```
@name[/engine] [word | "quoted"]... [(positional, group)] [{key=value ...}] [: prereqs] [::: mark]
```

An engine after a slash binds a late member to its handle's type: `/engine` is the first
positional, so each pair below is one decorator call. The forms that take it are
[`@<group>.actor`](actor.md#syntax), [`@<space>.reflex`](tspace.md#reflexes) and
[`@<kahn>.proc`](kahn.md#syntax).

```Makefile
@g1.actor/lua {kind=goal}              # @g1.actor lua {kind=goal}
@shop.reflex/js (order, item=str)      # @shop.reflex js order, item=str
@fb.proc/micropy (numbers > fizz buzz) # @fb.proc (micropy numbers > fizz buzz)
```

Positional, bare or in parens:

```Makefile
@jq.target --null-input --compact-output
@awk.target -v greeting=hi
@shop.bind.lua (order item=str qty=int)
@shop.bind.amk ("big order" n=int)
@lua.import.target(hello, flags)
```

Options, in braces:

```Makefile
@amk.target{join=;}
@ops.bind.js{kind=scoped restart=on-failure}
```

Prerequisites, after a colon:

```Makefile
@amk.target: workers
@jq.target --null-input : fetch
@shop.amk{join=none} : orders
```

A quoted colon or brace is text, not a trailer:

```Makefile
@jq.target --arg sep ':' --jsonargs '{}'
```

Refused, each with its line: two groups of one kind, a nested group, a brace entry with no
key, an unterminated quote or group, and a mark other than postfix above a define. A refusal
is one line on stderr, `amk (preprocess) error: FILE:LINE: @NAME: MESSAGE`, and the
preprocessor exits 76, the status compose.mk lists as `AMK_REFUSED`.

<a id="goal-substitution"></a>

## Goal Substitution

Part of dataflow style, documented [here](dataflow.md). `>>target<<` inside an imported body
splices in that target's value: what it printed, for an imported target or a plain recipe
alike. The name matches in any case, so `>>TARGET<<` names the same target; shouting it
marks the reference as a module global, which most guests read more clearly.

Example Usage:

```Makefile
target1:
	printf "hello world"

@lua.target
define target2
  print((">>TARGET1<<"):upper())
endef
```

<a id="abbreviated-define-blocks"></a>

## Abbreviated Define Blocks

One-liners aren't supported by stock `make`.  

Example Usage:

```Makefile
define my_data {} endef
```

<a id="references"></a>

## References

Related pages:

- [Extended grammar](../README.md#extended-grammar), the overview this page indexes.
- [The FFI](FFI.md#decorators), the engine forms decorators sugar.
- [Dataflow](dataflow.md), where goal substitution names values between goals.

Further reading:

- [Python's decorators](https://en.wikipedia.org/wiki/Python_syntax_and_semantics#Decorators), whose at-line shape the define-block decorators borrow, and [domain-specific languages](https://en.wikipedia.org/wiki/Domain-specific_language), on Wikipedia.

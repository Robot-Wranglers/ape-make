<!-- header # workflow "`mod :: dsys/workflow`" |Syntax #syntax | Reduction #reduction | API #api | Errors #errors | Demos #demos | Refs #references | Schema #schema -->
<h1><a id="workflow"></a><a href="dsys.md"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-workflow.workflow.up.dark.svg"><img src="img/hdr/docs-workflow.workflow.up.svg" alt="up to dsys"></picture></a><a href="../README.md#module-index"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-workflow.workflow.mod.dark.svg"><img src="img/hdr/docs-workflow.workflow.mod.svg" alt="mod"></picture></a><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-workflow.workflow.title.dark.svg"><img src="img/hdr/docs-workflow.workflow.title.svg" alt=" :: dsys/workflow"></picture><a href="#schema"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-workflow.workflow.6.dark.svg"><img align=right src="img/hdr/docs-workflow.workflow.6.svg" alt="Schema"></picture></a><a href="#references"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-workflow.workflow.5.dark.svg"><img align=right src="img/hdr/docs-workflow.workflow.5.svg" alt="Refs"></picture></a><a href="#demos"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-workflow.workflow.4.dark.svg"><img align=right src="img/hdr/docs-workflow.workflow.4.svg" alt="Demos"></picture></a><a href="#errors"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-workflow.workflow.3.dark.svg"><img align=right src="img/hdr/docs-workflow.workflow.3.svg" alt="Errors"></picture></a><a href="#api"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-workflow.workflow.2.dark.svg"><img align=right src="img/hdr/docs-workflow.workflow.2.svg" alt="API"></picture></a><a href="#reduction"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-workflow.workflow.1.dark.svg"><img align=right src="img/hdr/docs-workflow.workflow.1.svg" alt="Reduction"></picture></a><a href="#syntax"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-workflow.workflow.0.dark.svg"><img align=right src="img/hdr/docs-workflow.workflow.0.svg" alt="Syntax"></picture></a><br clear="all"></h1>
<!-- /header -->

<a id="overview"></a>

Part of the [dsys toolkit](dsys.md), the `@workflow` syntax declares a task graph as data and compiles it to a [Petri net](petri.md):

```Makefile
load dsys/workflow

@workflow
define release
  {"tasks": {"build": {"run": "build"}, "ship": {"run": "ship", "needs": ["build"]}}}
endef

build ship:
	@echo $@

__main__: release.__main__
```

* each task runs a target, in any [guest engine](FFI.md),
* `needs` orders tasks, and `when` picks which outcomes of the needs let a task run,
* `over` fans one task out across a list of items, and
* `pool` bounds how many firings of a task hold a [pool](pool.md) token at once.

The compiled net is an ordinary net: `<name>.__main__` and every other [petri call](petri.md#api) work on it.

<a id="syntax"></a>

## Syntax

| Form | Declares |
| --- | --- |
| `@workflow` above a define | a workflow of the define's name, compiled to a net of the same name, `<name>.__main__` its target |
| `$(workflow.compile name)` | the compiled net's JSON, without loading it |

A workflow is an object with one key, `tasks`, mapping each task name to its keys. A task name is `[a-z0-9_-]+`.

| Key | Value | Default |
| --- | --- | --- |
| `run` | the target the task runs | no step |
| `needs` | task names that run first | `[]` |
| `when` | `success`, `failed` or `done`: whether the task runs when all needs succeeded, when any failed, or always | `success` |
| `over` | a list of items, each 1 to 31 bytes with no whitespace; the task runs once per item | runs once |
| `pool` | a pool name; each firing holds one of its tokens | unbounded |

A task whose `when` does not hold is skipped, and its skip passes on as its outcome.

<a id="reduction"></a>

## Reduction

`workflow.jq` compiles the JSON once, at parse, and hands the net to `petri.load`:

| Task part | Becomes |
| --- | --- |
| A need | a labeled place `<need>.to.<task>`, its token the need's outcome |
| A task with no needs | a place `<task>.ready` holding one `success` token |
| The task | a transition guarded by `when`, its step of kind `goal.maybe`, its outcome the token's label |
| `when` other than `done` | a second transition `<task>.skip` guarded by the opposite |
| `over` | transitions `<task>.split` and `<task>.join` around places `<task>.items` and `<task>.results` |
| `pool` | an arc from the pool into the task and back |
| A task nothing needs | a place `<task>.end`; the final marking wants one token in each |

<a id="api"></a>

## API

| Call | Does | Answers |
| --- | --- | --- |
| `<name>.__main__` | runs the workflow as its net; typically `__main__: <name>.__main__` | a target |
| `$(<name>.net )` | reads back the compiled net | the net's JSON |
| `$(<name>.states )`, `$(<name>.trace)`, `$(<name>.step )` | as for [any net](petri.md#api) | words |
| `$(<name>.exec prog)` | a jq program over the net, the workflow's JSON as `$source` and the library as `workflow::` | what it prints |
| `$(<name>.version )` | the workflow's workspace version | a number |

`workflow` is a [stacked engine](FFI.md#stacked-engines) on jq, so `@workflow.target`,
`@workflow.import` and `@workflow.exec (name)` are its at lines and [`load ./release.workflow`](petri.md#loading)
reads a file as a workflow.

<a id="errors"></a>

## Errors

A body that fails the [schema](#schema) is refused first, with every error it has, as in
`release: does not meet schema/workflow.json: Property tasks: Additional property a: Property when: Value "always" not in enum; ...`.
That covers the keys, the task names, `when` and `over`. The compiler then refuses what a
schema cannot say, before any net exists:

| Condition | Message |
| --- | --- |
| A need that is no task | `t: needs n, which is no task` |
| A cycle in `needs` | `t: is on a cycle in needs` |

The `workflow.compile` function runs the compiler alone, without the schema, so a malformed
body given to it directly fails as a jq error.

<a id="demos"></a>

## Demos

| Demo | Shows |
| --- | --- |
| [`workflow-release.amk`](../demos/workflow-release.amk) | a release graph with a fan-out over guests, a pool of runners, and a task run only on failure |

<a id="references"></a>

## References

- [Petri nets](petri.md), what a workflow compiles to.
- [Kahn networks](kahn.md), the other form that compiles to a net.
- [dsys](dsys.md), the topic this module is a part of.

<a id="schema"></a>

## Schema

The full form, as a JSON Schema, is [`schema/workflow.json`](../payload/lib/dsys/schema/workflow.json),
and every `@workflow` body is checked against it before it compiles. A workflow is also refused for
what a schema cannot say, as [errors](#errors) lists: a need that names no task, or needs that form a cycle.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "workflow.json",
  "title": "@workflow",
  "description": "a task graph under @workflow, compiled by workflow.jq to a net; that each need names a task, and that needs hold no cycle, are checked by the compile",
  "type": "object",
  "additionalProperties": false,
  "required": ["tasks"],
  "properties": {
    "tasks": {
      "description": "each task by name, in declaration order",
      "type": "object",
      "minProperties": 1,
      "propertyNames": { "pattern": "^[a-z0-9_-]+$" },
      "additionalProperties": {
        "type": "object",
        "additionalProperties": false,
        "properties": {
          "run": { "description": "the target the task runs; without it, the task only passes its outcome on", "type": "string", "minLength": 1 },
          "needs": {
            "description": "the tasks that must end before this one starts",
            "type": "array",
            "items": { "type": "string" },
            "default": []
          },
          "when": {
            "description": "which outcomes of its needs let it run: success when all succeeded, failed when any failed, done either way; otherwise it is skipped",
            "enum": ["success", "failed", "done"],
            "default": "success"
          },
          "over": {
            "description": "items the task runs once per, each a label",
            "type": "array",
            "minItems": 1,
            "items": { "type": "string", "pattern": "^\\S{1,31}$" }
          },
          "pool": { "description": "an open pool whose tokens bound the task's runs in flight", "type": "string", "minLength": 1 }
        }
      }
    }
  }
}
```

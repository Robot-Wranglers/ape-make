<!-- header # mip "`mod :: amk.mip`" |Concepts #concepts | Syntax #syntax | API #api | Errors #errors | Demos #demos | Refs #references | Schema #schema -->
<h1><a id="mip"></a><a href="../README.md#module-index"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-mip.mip.up.dark.svg"><img src="img/hdr/docs-mip.mip.up.svg" alt="up to the module index"></picture></a><a href="../README.md#module-index"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-mip.mip.mod.dark.svg"><img src="img/hdr/docs-mip.mip.mod.svg" alt="mod"></picture></a><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-mip.mip.title.dark.svg"><img src="img/hdr/docs-mip.mip.title.svg" alt=" :: amk.mip"></picture><a href="#schema"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-mip.mip.6.dark.svg"><img align=right src="img/hdr/docs-mip.mip.6.svg" alt="Schema"></picture></a><a href="#references"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-mip.mip.5.dark.svg"><img align=right src="img/hdr/docs-mip.mip.5.svg" alt="Refs"></picture></a><a href="#demos"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-mip.mip.4.dark.svg"><img align=right src="img/hdr/docs-mip.mip.4.svg" alt="Demos"></picture></a><a href="#errors"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-mip.mip.3.dark.svg"><img align=right src="img/hdr/docs-mip.mip.3.svg" alt="Errors"></picture></a><a href="#api"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-mip.mip.2.dark.svg"><img align=right src="img/hdr/docs-mip.mip.2.svg" alt="API"></picture></a><a href="#syntax"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-mip.mip.1.dark.svg"><img align=right src="img/hdr/docs-mip.mip.1.svg" alt="Syntax"></picture></a><a href="#concepts"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-mip.mip.0.dark.svg"><img align=right src="img/hdr/docs-mip.mip.0.svg" alt="Concepts"></picture></a><br clear="all"></h1>
<!-- /header -->

<a id="overview"></a>
The `mip.amk` module installs pinned packages for the [micropy guest](../README.md#micropy). A define under `@mip.install` names the packages as JSON; the define's name becomes the target that fetches whatever is missing, and every package lands on the guest's import path.

```Makefile
load mip

@mip.install
define deps
  { "microdot": {
      "version": "v2.7.0",
      "spec": "github:miguelgrinberg/microdot/src/microdot/microdot.py" } }
endef
```

<a id="see-also"></a>

It builds on:

* micropython's own package installer, `mip`[^mip], bundled from micropython-lib
* amk's [micropy engine](../README.md#micropy) and jq
* mip [module source](../payload/lib/amk/mip.amk), a thin wrapper on the above, providing the grammar

<a id="concepts"></a>

## Concepts

| Term | Meaning |
| --- | --- |
| Manifest | the define under `@mip.install`: packages by name, each with a spec and a version |
| Spec | what mip installs: a micropython-lib name, `github:org/repo/path`, `gitlab:org/repo/path`, or an http or https URL |
| Cache | `mip.cache`, `~/.cache/amk/mip` by default; a package lives at `<cache>/<name>/<version>` |
| Stamp | the `.ok` file in a package's directory, holding its digest; a package with a stamp is installed |
| Pin | a package's `sha256`, the digest its install must match, over every file's path and bytes |

A version is fetched once and shared by every manifest that names it.

<a id="syntax"></a>

## Syntax

| Form | Declares |
| --- | --- |
| `@mip.install` above a define | a manifest of the define's name: its packages on `MICROPYPATH`, and a phony target of the same name that installs the missing ones |

The body may be JSON5, as [io](io.md) describes for every JSON define.

<a id="api"></a>

## API

| Call | Does | Answers |
| --- | --- | --- |
| `<manifest>` | installs every package without a stamp | a target |
| `mip.cache` | where packages are installed, `$(HOME)/.cache/amk/mip` unless set | a variable |
| `$(mip.path manifest)` | each package's directory, as added to `MICROPYPATH` | paths |
| `$(mip.missing manifest)` | the packages with no stamp yet | names |

Run the manifest's target before a guest imports from it, for example as a prerequisite:

```Makefile
serve: deps
	...
```

<a id="errors"></a>

## Errors

| Condition | Message |
| --- | --- |
| A manifest that breaks the schema | `deps: does not meet schema/mip.json: ...`, and nothing is fetched |
| An install whose digest does not match its pin | `mip: microdot digests to <sha>; pin it as its sha256 in deps`, and the build stops with nothing published |
| A package with no pin | the same line on stderr as a warning; the install completes and its digest is kept in the stamp |

<a id="demos"></a>

## Demos

| Demo | Shows |
| --- | --- |
| [`json-rpc.amk`](../demos/json-rpc.amk) | microdot under `@mip.install`, serving a JSON-RPC server whose methods live in several guests |

<a id="references"></a>

## References

- [The micropy engine](../README.md#micropy), the guest these packages are for.
- [Bundled libraries](../README.md#libraries), where mip sits among the payload's libraries.
- [io](io.md), the JSON5 reading every JSON define shares.

[^mip]: micropython-lib, "mip", [github.com/micropython/micropython-lib](https://github.com/micropython/micropython-lib).

<a id="schema"></a>

## Schema

Each manifest is checked against [`schema/mip.json`](../payload/lib/amk/schema/mip.json) before anything is fetched.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "mip.json",
  "title": "@mip.install",
  "description": "micropy packages under @mip.install, by name: each fetched once by mip into mip.cache/<name>/<version> and put on the guest's import path",
  "type": "object",
  "minProperties": 1,
  "propertyNames": {
    "description": "the package's name, its directory under mip.cache",
    "pattern": "^[A-Za-z0-9_.-]+$"
  },
  "additionalProperties": {
    "type": "object",
    "additionalProperties": false,
    "required": ["spec", "version"],
    "properties": {
      "spec": {
        "description": "what mip installs: a micropython-lib name, github:org/repo/path, gitlab:org/repo/path, or an http or https URL",
        "type": "string",
        "minLength": 1
      },
      "version": {
        "description": "the version mip fetches, a tag or branch; also the package's directory under its name",
        "type": "string",
        "pattern": "^[^/\\s]+$"
      },
      "sha256": {
        "description": "the digest the install must match, over every file's path and bytes; without it, the install names the digest to pin",
        "type": "string",
        "pattern": "^[0-9a-f]{64}$"
      }
    }
  }
}
```

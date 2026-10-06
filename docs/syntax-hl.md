# Syntax highlighting

## What it highlights

An at line names the engine a define is written for, and the editor extension reads it the
same way amk does: the body of that define takes the engine's own grammar, and the rest of
the file keeps the editor's makefile highlighting. A define with no at line stays plain
make, whatever its name, since a name is only a convention.

```make
@lua.import.target
# blank and comment lines may stand between the at line and its define
define sorted
  local xs = {}
  for x in ("@nums.txt@"):gmatch("%S+") do xs[#xs + 1] = tonumber(x) end
  print(table.concat(xs, " "))
endef
```

Here the body is lua up to its endef, even if the guest grammar is left mid-string. A body
reaches its engine unexpanded, so make references and goal references inside it are marked
on top of the guest grammar, strings included.

## Installing

```bash
make vscode
```

This generates the grammars, packs them as `out/amk.vsix`, and installs that with the
`code` command; reload the window afterwards. It needs `node`, `zip`, and `code` on PATH.

## Engines and grammars

| engine | grammar | ships with the editor |
| --- | --- | --- |
| lua | `source.lua` | yes |
| micropy | `source.python` | yes |
| js | `source.js` | yes |
| s7 | `source.scheme` | no |
| jq | `source.jq` | no |
| awk | `source.awk` | no |

A body whose grammar is missing is marked as embedded but shows uncolored until another
extension supplies that grammar. The table lives in `vscode/build.js`, which generates one
block of the injection grammar per row.

## Testing the grammars

The test tokenizes small makefiles with the same engine the editor uses, against the
makefile, lua, python, and javascript grammars of an installed VS Code, and checks the
scope given to each span.

```bash
cd vscode && npm install && npm test
```

Point `VSCODE_EXTENSIONS` at the extensions folder of an install outside the default macOS
location.

When a highlight looks wrong in the editor, run Developer: Inspect Editor Tokens and Scopes
on the token: the scopes it lists tell a grammar fault from a theme choice.

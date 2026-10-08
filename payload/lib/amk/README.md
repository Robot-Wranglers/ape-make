# amk

Make's folder: libraries reached through make that offer make forms. Nothing lands here
at build; every file is checked in. A `.mk` file is make alone and parses under stock GNU
make; a `.amk` file uses amk's own syntax, such as at lines or `load`. A library may require
an engine for its work, named by `amk.require` near its top.

| File | Requires | Offers |
| --- | --- | --- |
| `bash.amk` | lua | `@bash.target` and `@bash.import.target` above a define: the body is a shell command bash runs as an imported target, so its output is a value the dataflow mode records; registered as the engine `bash` through `@amk.engine.spec` |
| `mip.amk` | micropy, jq | `@mip.install` above a json define of packages by spec and version, with a sha256 to pin one: the define's name is the target that fetches what is missing into `mip.cache`, each on the guest's import path, naming the digest of a package that has no pin. The define is checked first against [`schema/mip.json`](schema/mip.json): every package needs a `spec` and a `version`, and a `sha256` is 64 lowercase hex characters |
| `wasm.mk` | wasm | the jit interface behind `$(amk.engine name, guest=wasm)`: the engine's namespace, `@name.import` and `@name.target` above a source define, the module built once in `.amk/wasm/` by the checksum of its inputs. A toolchain is `Dockerfile.<name>`, the image, and `<name>.build`, a command over make's `$<` and `$@`; without a Dockerfile the command runs on the host |
| `zig.amk` | wasm, jq | zig as an engine, its row a json spec under `@amk.engine.spec`: alpine's zig, a freestanding module with every exported function exported; `load zig`, then `@zig.import` or `load fib.zig` |
| `wat.amk` | wasm | wasm text as an engine: wabt's `wat2wasm` in a debian image; `load wat`, then `@wat.import` or `load fib.wat` |
| `golang.amk` | wasm, jq | go as an engine with `go` as its extension, its row a json spec under `@amk.engine.spec`: tinygo's image, a wasi module whose main is the start; `load golang`, then `@golang.import` or `load fib.go` |
| `utmpl.amk` | micropy, utemplate | `@utmpl.target` and `@utmpl.import.target` above a define holding a template: the target renders json from stdin, `name/var` renders the json in variable `var`, and `$(utmpl.render name, var)` does the same in an expansion |

## Usage

`$(amk.include <name>)` reads `lib/amk/<name>.amk` or `lib/amk/<name>.mk` when there is
one, `.amk` first, else the topic's `lib/<name>/init.amk`:

```Makefile
$(amk.include utmpl)     # lib/amk/utmpl.amk, a library with at lines
$(amk.include tspace)    # lib/tspace/init.amk, the topic's make binding

@utmpl.target
define greeting
Hello, {{name}}.
endef
```

`$(amk.include a, b)` takes several names, reads each once per run, and stops make with
`amk.include: no library named x in the payload` for a name it cannot find. It is a
statement: on a line of its own at parse time, never inside a recipe or an assignment.
The plain `include /zip/lib/...` of the path still works, and so does `load <name>`: a bare
name no engine claims reads the same file by the same lookup and the same guard, so
`load utmpl` is this folder's `utmpl.amk` once, however it was first asked for. The order,
with the engine libraries that `load` tries first, is in
[README.md#modules](../../../README.md#modules).

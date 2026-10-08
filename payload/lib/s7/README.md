# s7

The s7 engine's folder, on its `*load-path*` as `/zip/lib/s7`. Nothing lands here at
build; every file is checked in and loads in any s7, naming nothing of amk. From make, a
file here is a [module](../../../README.md#modules): `load amb` finds `amb.scm` through
the payload fallback, this folder naming the engine, and imports it into s7's main state.

| File | Holds |
| --- | --- |
| `amb.scm` | McCarthy's `amb` over delimited control after Filinski, in [the amb module](../../../docs/amb.md) |
| `json.scm` | `json-read`, a JSON reader, [below](#json) |

## Usage

A topic loads on the first unbound `amk-<name>-...` symbol, from its `init.scm`. A file
here is reached by name, since `/zip/lib/s7` is on `*load-path*`; a binding that builds on
one loads it under a guard, so a second loader is free:

```scheme
(load "amb.scm")                                   ; lib/s7/amb.scm
(amk-tspace-out "k" 1)                             ; lib/tspace/init.scm, loaded by the symbol
(unless (defined? 'amb) (load "amb.scm" (rootlet)))  ; inside a binding
```

# amb

McCarthy's `amb` for stock s7: loading it, delimited control, choice, writing a search,
the demos and the references are in [the amb module](../../../docs/amb.md).

# json

`json-read` turns JSON text into s7 values, for reading what a make function answers as
JSON. It reads by recursive descent and never evaluates the text, so a string's contents
stay data. One file, `json.scm`, with nothing of amk in it.

```scheme
(load "json.scm")
(define r (json-read "{\"pid\": 41, \"status\": \"success\", \"xs\": [1, true, null]}"))
(r 'status)                             ; "success"
(r 'xs)                                 ; #(1 #t ())
```

| JSON | s7 |
| --- | --- |
| object | a hash table keyed by symbol, so `(r 'key)` reads a field |
| array | a vector |
| string | a string, every escape decoded, `\u` and surrogate pairs as UTF-8 |
| number | an integer or a real |
| `true`, `false`, `null` | `#t`, `#f`, `()` |

A field that is `false` reads the same as a missing one, since an s7 hash table answers
`#f` for both. Malformed text, or anything but whitespace after the value, raises
`json-error` with the offset:

```scheme
(catch 'json-error
  (lambda () (json-read "{} x"))
  (lambda (type info) (apply format #f info)))   ; "json-read: text after the value at offset 3 of ..."
```

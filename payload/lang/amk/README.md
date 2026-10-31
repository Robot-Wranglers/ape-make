# lang/amk

The awk sources of amk's preprocessor, the pass that rewrites a makefile before make
parses it. They ship in the payload, and the engine reads them from the zip by path.

| Folder | Holds |
| --- | --- |
| `awklib/` | libraries: shared definitions (grammar symbols, helpers, common lowerings) loaded ahead of a program with `-f`, never run alone |
| `comp/` | programs: one rewrite per file, reading make source on stdin and writing it on stdout |

A program's header comment says what it rewrites and which libraries it runs behind.
Every program loads `awklib/globals.awk` first, then `awklib/functions.awk`, for example:

```sh
awk -f awklib/globals.awk -f awklib/functions.awk -f awklib/callforms.awk -f comp/targetdecorators.awk
```

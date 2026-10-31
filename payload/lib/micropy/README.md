# micropy

The micropython engine's folder, on its `sys.path` as `/zip/lib/micropy`. From make, a
single file here is a [module](../../../README.md#modules) that `load` reads by bare name;
`.py` is not an extension micropy claims, so `load ssl.py` arrives through the payload
fallback, which picks the engine from this folder and says so.

## Vendored at Build Time

Nothing here is checked in. `make build` installs these from the pinned inputs in the
Makefile:

| Package | Version | From | Lands As |
| --- | --- | --- | --- |
| utemplate | 1.4.1 | [PyPI](https://pypi.org/project/utemplate/) | `utemplate/` |
| asyncio | micropython 1.29.0 | the engine's own `extmod/asyncio`, the Python half | `asyncio/` |
| requests, ssl, mip | micropython 1.29.0 | micropython-lib, as bundled with the engine | `requests/`, `ssl.py`, `mip/` |

utemplate stands in for jinja, which micropython's `os` and `re` cannot carry. `mip` is
the package installer that `lib/amk/mip.amk` drives from make.

## Usage

```python
import utemplate                        # lib/micropy/utemplate/
import amk
amk.tspace.out("k", 1)                  # lib/tspace/__init__.py, a topic, on first use
import tspace                           # fails: a topic is a module of amk alone
```

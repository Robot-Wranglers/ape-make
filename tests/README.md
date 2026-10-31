<a id="the-amk-test-suite"></a>

# The amk test suite

The suite pins the behavior of one built amk. It needs that binary and pytest, nothing
else: no compose.mk, no docker, no network unless a test is marked for it.

<a id="the-binary"></a>

## The binary

`AMK_BIN` names the binary under test. Without it, the suite uses `./amk` beside this
directory, then `out/bin/amk`. A test with no binary skips and says how to get one.

```bash
make build
AMK_BIN=$PWD/out/bin/amk pytest tests/test_tspace.py -q
```

<a id="running"></a>

## Running

| # | Run | Covers |
| --- | --- | --- |
| R1 | one file, as above | the unit of feedback, seconds to a minute |
| R2 | `make test` | every file under `tests/`, against the fat ape, about a minute |
| R3 | `make test.integration` | tests marked `integration`: servers, ports, the network; serially |
| R4 | `make test.upstream` | GNU make's own regression suite, several minutes |

R2 to R4 are gates; run one file while working.

<a id="markers"></a>

## Markers

| marker | meaning |
| --- | --- |
| `engines(*names)` | needs every named engine linked in; skipped on a build without one |
| `integration` | starts a server, opens a port, or reaches the network; left out by default |
| `network` | fetches from the internet; always also `integration` |
| `upstream` | GNU make's own suite; left out by default |

<a id="layout"></a>

## Layout

| path | holds |
| --- | --- |
| `conftest.py` | the fixtures: `amk`, `engines`, `sh` and `popen` to run the binary, `zygote`, `bundle`, `installed`, and the leak checks |
| `conformance.py` | the engine contracts, with engines taken from the binary's own `--list-engines` |
| `fixtures/` | inputs a test reads: a bundle source, the upstream pass counts |
| `test_*.py` | one file per area, named for what it pins |
| `dsys/` | the dsys topic's files: pools, jobs, petri nets, workflows, state machines and their oracles |
| `experimental/` | a gitignored sandbox; see below |

<a id="rules"></a>

## Rules

A test pins behavior. It writes its own makefile into `tmp_path`, runs the binary on it,
and asserts on the output:

```python
@pytest.mark.engines("sqlite")
def test_inp_takes_the_oldest_match_once(amk, tmp_path):
  r = run(amk, tmp_path, recipe("tspace out k 1", "tspace inp k ?int"))
  assert r.returncode == 0, r.stdout + r.stderr
  assert tuples(r.stdout) == [["k", 1]], r.stdout
```

A test never reads `demos/`. Demos illustrate; they change, wait for polish, or stay
uncommitted, so a test that runs one breaks for reasons that are not defects. Pin the
behavior a demo shows with a test of its own.

<a id="experimental"></a>

## Experimental

`experimental/` holds tests that are not yet the suite's. It is gitignored and pytest does
not recurse into it, so `make test` never runs it; name it to run it:

```bash
AMK_BIN=$PWD/out/bin/amk pytest tests/experimental -q
```

A test leaves `experimental/` by moving into `tests/` once it pins behavior and follows the
rules above.

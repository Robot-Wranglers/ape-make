# Developers

Building, releasing, and the layout of the build tree. Testing, payload internals,
dependencies, and patches stay in the [README](../README.md#dev).

## Building

Simple builds:

```bash
# overview 
make help

# creates ./amk with the default engines
make           
```

Opting in and out:

```bash
# the default engines plus $(wasm)
make amk with=wasm3

# no $(s7), and no s7 download
make amk without=s7

# neither scripting engine
make amk without='s7 lua'
```

`with` adds an engine that is off by default, `without` leaves any engine out, and
`without` wins where the two name the same one. A name that is not an engine stops the
build, and leaving out every engine stops it too. An engine left out is absent, not
stubbed: its builtin does not exist, its name is not in `.FEATURES`, its multi-call alias
is not created, and `make deps` does not download it. The engines, what each gives, and
its size are in the table under [Special guests](../README.md#special-guests). Of the default build's
14.1 MB, the two payload tools are about 5 MB. An engine's size is that build against the
same build without it, or with it for one that is off.

Development flow:

```bash
# fetch every pinned input not already here, verify all of them
make deps

# unpack make into src/ and apply patches/ in order
make patch

# out/bin/amk, the fat ape with the selected engines linked in
make build

# the builtins, the commands, the payload tools, a zygote, and a bundle
make smoke

# what is built here, and which of it is an artifact
make stat

# ./amk into ~/.local/bin, or into /usr/local/bin with install.global; bindir.user= and bindir.global= override
make install
```

Additionally `make build.native` builds the same sources with the host compiler, make at `-O0 -g`,
as `out/bin-native/amk`; `make smoke.native` runs the builtins through it. Guests build
on their own with `make guests` and `make guests.native`.

## Testing

`make smoke` runs the builtins cold, the multi-call names, the payload tools, one zygote
with three clients, and a bundle.

`make test` runs the pytest suite under `tests/` against `out/bin/amk`. It pins what a
smoke script cannot: the resident role parses once however deep the recursion goes and
reaps after an interrupt, a signalled client exits as a cold make does, a refused
request falls back to the caller's command, `--ape-unpack` honors its staleness rule
and rejects a climbing name, and a bundle runs, recurses, and serves with nothing else
on disk. The suite needs pytest and the binary, nothing else.

```bash
# the suite against out/bin/amk; test.native takes the host build
make test

# a runner that is not on PATH, and flags through to pytest
make test pytest=../../.venv/bin/pytest pytest.args='-k resident -v'

# any binary at all, run from tests/ directly
AMK_BIN=/usr/local/bin/amk pytest tests
```

Docker Desktop's Rosetta layer segfaults every ape, so `--platform linux/amd64`
containers on an arm64 Mac are not a test of the x86_64 half; `arch -x86_64` on the
host is.

## Profiling

The profiler shows where a makefile spends its time while make expands it, broken down
by name. It times three kinds of expansion:

- `fn`: every builtin function, such as `shell`, `wildcard`, or an engine's `$(lua)`
- `call`: every macro reached through `call`
- `var`: every recursive variable as it expands

Turn it on with the flag or the environment variable. Both take a file, or send the
table to stderr without one:

```bash
# the table on stderr
amk --profile -f Makefile

# the table appended to prof.txt
amk --profile=prof.txt -f Makefile
AMK_PROFILE=prof.txt amk -f Makefile
```

The flag works anywhere on the command line and is removed before make, an engine, or a
zygote sees it. When the process exits, amk appends one table: a header with the pid,
the wall time, and the number of names, then one row per name, sorted by self time with
the largest first.

```text
# amk profile pid=83032 wall=0.035s names=17
   self_ms   total_ms    count  name
    28.558     28.559        4  fn shell
     0.066      0.066        1  fn wildcard
     0.011     57.163        6  fn call
     0.006     28.569        4  call once
     0.004     28.563        4  var once
     0.003     28.582        2  var twice
```

Self time is what a name spends on its own, with its children's time taken out. Total
time includes them. A macro that only dispatches shows a self time near zero, so its work
appears under the names it calls. In the table above, `twice` and `once` cost nothing
themselves, and the whole run is the four `shell` calls at the bottom. Read self time to
find the cost, and total time to find which caller leads to it.

A sub-make inherits the setting and appends its own table to the same file, so a
recursive build leaves one table per process. With profiling off, the cost is one check
per expansion. The profiler is patch `0070`, and the flag is patch `0071`.

## Dependencies

Every input is pinned by version and sha256 in the Makefile. Upstream ships no
checksum files, so the digests are ours. The guests' versions are in the
[standard guests](../README.md#guests) and [special guests](../README.md#special-guests) tables; the
rest of the build is make itself and its toolchain:

| input | version | from |
| --- | --- | --- |
| make | 4.4.1 | [ftp.gnu.org](https://ftp.gnu.org/gnu/make/) |
| cosmocc | 4.0.2 | [cosmo.zip](https://cosmo.zip/pub/cosmocc/) |

s7 is the one input whose url carries no version, so its digest is the whole pin and
moves whenever upstream publishes. A digest mismatch there is a new release, not a
tampered download: check what changed, then update `s7.version` and `s7.sha256` together.

`deps` downloads into this directory and leaves what is already present alone. It fetches
and verifies only the engines this build selects, so `without` also skips the download and
an opt-in engine is fetched only `with` it. The
toolchain unpacks to `cosmocc/` on first use; set `cosmocc.dir=/opt/cosmocc` to use
an installed copy instead. Invoke cosmocc through `PATH`, never through a symlink:
it locates `mktemper` and its siblings beside its own path.

## Patches

Only make is patched; guests stay pristine. `patches/` is a numbered series applied in
order, and [patches/README.md](../patches/README.md) describes the series, the engine table
each engine adds a row to, and how a guest is hidden inside the link. Each patch file opens
with a note on what it does and any exception it makes for its guest.

A consumer that needs make fitted to itself keeps a series of its own and applies it after
this one, without forking the tree. `patch.dirs` names the directories in order, and
`flavor` names the build so its patched tree and artifact land beside the plain ones:

```bash
make build flavor=cmk patch.dirs='patches ../ape/patches'
# src/make-4.4.1-cmk, build/ape-cmk, out/bin-cmk/amk; the guests are shared
```

Both must be given together. The overlay's patches are written against the tree this series
leaves, so they say which amk version they apply to and are rebased when it moves.

## Releases

A release is a pushed tag that starts with `v`, and the tag is the version: the Makefile
reads `amk.version` from the nearest `v` tag with `git describe`, so the banner and
`.AMK_VERSION` say `0.2.0` at the tag and something like `0.2.0-3-gabc1234-dirty` on a
build past it. One command cuts a release from any branch:

```bash
version=0.2.0 make release
```

It refuses to run unless the version is `X.Y.Z`, every tracked change is committed, and
`v0.2.0` exists neither locally nor on `origin`. Then it tags the head, pushes the branch
and the tag, and streams the workflow run when `gh` is installed; `make release.watch
version=0.2.0` reattaches to a run. `release.remote=` names another remote.

The `Release` workflow builds `amk` from a clean tree on Linux, runs `make smoke`, checks
that the banner names the tag, runs
the built file on x86_64 Linux, arm64 Linux, and macOS without rebuilding it, and
publishes `amk` and `amk.sha256` as a GitHub Release named after the tag, and the
container image to `ghcr.io/robot-wranglers/amk` after smoking it on amd64. Running the
workflow by hand on a branch is a dry run: it builds and checks, builds the image for both
platforms, and pushes nothing. Every push and pull request runs the same build through the `Build` workflow and
keeps the result as a workflow artifact. A weekly `Pins` workflow fetches every input cold
and verifies it, so a digest that moved upstream surfaces before it breaks a release.

## Layout

`out/` holds artifacts only. Everything else this directory produces stays under
`build/`, and `make stat` prints the whole list with sizes. `st` and `status` are aliases.

| path | what it is |
| --- | --- |
| `./amk` | the deliverable, the copy `make amk` lands for a caller |
| `out/bin/amk` | the artifact: make with its guests, both architectures, one file |
| `out/bin/{awk,jq,wasm3}` | symlinks to `amk` beside them, the names its argv[0] dispatch answers to |
| `out/bin-native/amk` | the same sources built by the host compiler, for the debug loop |
| `out/bin-native/{awk,jq,wasm3}` | the same names for the host build |
| `build/.engines` | the engine list the artifacts were built from, so a change to it relinks |

`build/guests/ape/` and `build/guests/native/` hold each guest partial-linked into one
relocatable, the inputs the final link consumes. They are the expensive half of a build,
so nothing removes them on the way to `out/bin/amk`: cosmocc compiles every guest for both
architectures, and a rebuild that reuses them takes a fraction of the time. `build/` also
keeps each configure tree and a `build.log` per guest, which is where a compile failure
is reported.

`make clean` drops `./amk` along with `src build out`, which discards those relocatables
and costs a full rebuild. The downloads and the unpacked toolchain always stay.

## Payload Internals

The payload tools are the released cosmos binaries, unchanged, as the payload members
`bin/sed` and `bin/bash`, plus the json.bash script as `bin/jb`, `bin/jb-array`, and
`bin/json.bash`, unpacked to `${XDG_CACHE_HOME:-$HOME/.cache}/amk/<size>-<mtime>/bin`.
A recursive make finds that directory already first on `PATH` and leaves `PATH` alone. A
tool is added by pinning its release in the Makefile beside `sed` and naming it in
`tools.all`, with a `.names` list when it lands under more than one name, and in
`tools.optout` when `without` may drop it; nothing compiles it.

bash is a separate binary rather than a guest linked into amk because a shell forks
constantly, and a fork inside a large cosmo image can lose part of its text on Apple
Silicon; the small standalone build does not.

`--bundle` edits the zip in place rather than rebuilding: everything ahead of the central
directory is kept, new members are appended stored, and a new directory drops any member
they replace. `--ape-unpack` and `--bundle` both write beside the destination and rename
into place. A zygote started from a bundle holds the entry among its own options, so its
clients match it.

## The APE Loader

An ape's header installs its loader at `$TMPDIR/.ape-1.10` on first run. A caller that
cannot go through a shell can name that loader explicitly.

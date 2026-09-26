"""Fixtures for the amk suite: the binary under test, a way to run it, and leak checks.

The suite runs against one built amk and nothing else: no compose.mk, no docker, no
python beyond pytest. `AMK_BIN` names the binary; without it the landed deliverable
beside this directory is used, then the release artifact under out/. A portable build
needs a shell in front on macOS, so every invocation goes through `sh`.
"""

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
AMK_DIR = HERE.parent
BUNDLE_SRC = HERE / "fixtures" / "bundle"
CANDIDATES = (AMK_DIR / "amk", AMK_DIR / "out" / "bin" / "amk")

# The reader the payload tools use, so a fidelity check reads what the binary holds.
SLURP = 'BEGIN{RS="^$"} {printf "%s", $0}'


def _binary():
  named = os.environ.get("AMK_BIN")
  if named:
    return Path(named).resolve()
  return next((p for p in CANDIDATES if p.exists()), CANDIDATES[0])


def sh(binary, args, cwd=None, env=None, timeout=300, stdin=None):
  """Run a binary through a shell, which is the only way an ape execs on macOS."""
  full = dict(os.environ)
  full.update(env or {})
  return subprocess.run(
    ["sh", "-c", '"$0" "$@"', str(binary), *args],
    capture_output=True, text=True, cwd=cwd, env=full, timeout=timeout, input=stdin,
  )


def popen(binary, args, cwd=None, env=None, **kw):
  """The background form of `sh`, for a zygote or a run that a test will signal."""
  full = dict(os.environ)
  full.update(env or {})
  return subprocess.Popen(["sh", "-c", '"$0" "$@"', str(binary), *args],
                          cwd=cwd, env=full, **kw)


def packed(binary, member):
  """One payload member's bytes, read the way the payload tools read it."""
  r = sh(binary, ["--awk", SLURP, f"/zip/{member}"])
  assert r.returncode == 0, r.stderr
  return r.stdout


@pytest.fixture(scope="session")
def amk():
  """The binary under test, or a skip that says how to get one."""
  binary = _binary()
  if not binary.exists():
    pytest.skip(f"no amk at {binary} (run make build in via/amk, or set AMK_BIN)")
  r = sh(binary, ["--version"], timeout=60)
  assert "GNU Make" in r.stdout, f"{binary} is not a make: {r.stderr[-500:]}"
  return binary


@pytest.fixture(scope="session")
def engines(amk):
  """The engines this build carries, from its own feature list."""
  r = sh(amk, ["-f", "/dev/null", "-pqn"])
  line = next((ln for ln in r.stdout.splitlines() if ln.startswith(".ENGINES")), "")
  return line.split("=", 1)[-1].split()


@pytest.fixture(autouse=True)
def _needs_engines(request, engines):
  """Honor the engines marker: a build without one of the named engines skips."""
  marker = request.node.get_closest_marker("engines")
  if marker:
    missing = [e for e in marker.args if e not in engines]
    if missing:
      pytest.skip(f"this amk carries no {' '.join(missing)}")


def _run_dirs():
  roots = {Path("/tmp"), Path(os.environ.get("TMPDIR", "/tmp"))}
  return sorted({d for root in roots for d in root.glob("amk-resident.*")})


def _live_zygotes():
  ps = subprocess.run(["ps", "-axo", "args="], capture_output=True, text=True).stdout
  return [ln for ln in ps.splitlines() if "--serve" in ln and "amk-resident." in ln]


@pytest.fixture
def no_leftovers():
  """Compares against what was already there, so an unrelated stray is not ours."""
  before = set(_run_dirs())
  yield
  new = set(_run_dirs()) - before
  assert not new, f"run directories survived: {sorted(new)}"
  assert not _live_zygotes(), f"zygotes survived: {_live_zygotes()}"


@pytest.fixture
def sock(request):
  """A socket path short enough to bind; a pytest tmp path is over the unix cap."""
  name = request.node.name.replace("[", ".").replace("]", "")
  path = Path(f"/tmp/amk-t.{os.getpid()}.{name}.sock")
  path.unlink(missing_ok=True)
  yield path
  path.unlink(missing_ok=True)


@pytest.fixture
def zygote(amk, sock):
  """Start a zygote on the given makefile args and return its socket; killed on teardown."""
  started = []

  def start(args, cwd):
    z = popen(amk, ["--serve", str(sock), *args], cwd=cwd, stdin=subprocess.DEVNULL,
              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    started.append(z)
    deadline = time.time() + 60
    while time.time() < deadline and not sock.is_socket():
      time.sleep(0.05)
    assert sock.is_socket(), "zygote never bound"
    return sock

  yield start
  for z in started:
    z.kill()
    z.wait(timeout=30)


@pytest.fixture(scope="session")
def bundle(amk, tmp_path_factory):
  """A bundle built from tests/fixtures/bundle/ by the binary under test, as smoke builds it."""
  out = tmp_path_factory.mktemp("bundle") / "b.amk"
  r = sh(amk, ["--bundle", "main.mk", "lib/", "--out", str(out)], cwd=BUNDLE_SRC)
  assert r.returncode == 0, r.stderr
  assert out.exists(), "bundle wrote nothing"
  return out


@pytest.fixture
def installed(amk, tmp_path):
  """An install: the binary in a directory of its own, reached only through the path."""
  d = tmp_path / "bin"
  d.mkdir()
  binary = d / "amk"
  shutil.copy2(amk, binary)
  binary.chmod(0o755)
  return binary

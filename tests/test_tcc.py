"""The tcc engine: C compiled in memory by libtcc and run in make's own process.

An import keeps its unit mapped and calls every setup function it defines; the unit
reaches make through the amk calls the prelude declares, and make's events through
amk_on_event. The status bar demo is pinned on a pseudo-terminal, since it draws only
on one, and off one, where it must leave the output untouched.
"""

import fcntl
import os
import pty
import select
import signal
import struct
import subprocess
import termios
import time

import pytest

from conftest import AMK_DIR, sh

pytestmark = pytest.mark.engines("tcc")

DEMO = AMK_DIR / "demos" / "tcc-statusbar.amk"


def write(tmp_path, text):
  path = tmp_path / "Makefile"
  path.write_text(text)
  return path


def test_import_runs_setup_and_sets_a_variable(amk, tmp_path):
  write(tmp_path, """
@tcc.import
define answer.c
  int answer_gmk_setup (void)
  {
    char buf[16];
    snprintf (buf, sizeof buf, "%d", 41 + 1);
    amk_var_set ("answer", buf);
    return 1;
  }
endef

all:
\techo "answer=$(answer)"
""")
  r = sh(amk, ["--silent", "-C", str(tmp_path)])
  assert r.returncode == 0, r.stderr
  assert r.stdout.strip() == "answer=42"


def test_a_setup_that_answers_zero_fails_the_import(amk, tmp_path):
  write(tmp_path, """
@tcc.import
define refuse.c
  int refuse_gmk_setup (void) { return 0; }
endef

all:
\techo unreachable
""")
  r = sh(amk, ["--silent", "-C", str(tmp_path)])
  assert r.returncode != 0
  assert "refuse_gmk_setup failed" in r.stderr


def test_a_compile_error_names_the_symbol(amk, tmp_path):
  write(tmp_path, """
@tcc.import
define broken.c
  int broken_gmk_setup (void) { return nope; }
endef

all:
\techo unreachable
""")
  r = sh(amk, ["--silent", "-C", str(tmp_path)])
  assert r.returncode != 0
  assert "tcc:" in r.stderr and "nope" in r.stderr


def test_events_reach_a_callback_in_the_owner(amk, tmp_path):
  write(tmp_path, """
@tcc.import
define count.c
  static int ended;
  static void on_event (const char *event, const char *target, const char *status, int code, int sig, long pid)
  {
    char buf[16];
    if (strcmp (event, "recipe_end") != 0)
      return;
    snprintf (buf, sizeof buf, "%d", ++ended);
    amk_var_set ("ended", buf);
  }
  int count_gmk_setup (void) { amk_on_event (on_event); return 1; }
endef

all: one two
\techo "ended=$(ended)"
one two:
\ttrue
""")
  r = sh(amk, ["--silent", "-C", str(tmp_path)])
  assert r.returncode == 0, r.stderr
  assert r.stdout.strip() == "ended=2"


def run_on_pty(amk, args, rows=24, cols=100, timeout=60, interrupt=None):
  """The binary on a pseudo-terminal of the given size: everything it wrote, and its exit status; interrupt, when given, is the text after which its process group gets SIGINT."""
  leader, follower = pty.openpty()
  fcntl.ioctl(follower, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
  env = dict(os.environ)
  for name in ("MAKELEVEL", "MAKEFLAGS", "MFLAGS", "AMK_STATUSBAR_OWNER"):
    env.pop(name, None)
  proc = subprocess.Popen(["sh", "-c", 'exec "$0" "$@"', str(amk), *args],
                          stdin=follower, stdout=follower, stderr=follower, env=env,
                          start_new_session=True)
  os.close(follower)
  out = b""
  deadline = time.monotonic() + timeout
  while time.monotonic() < deadline:
    if interrupt is not None and interrupt.encode() in out:
      os.killpg(proc.pid, signal.SIGINT)
      interrupt = None
    ready, _, _ = select.select([leader], [], [], 0.5)
    if ready:
      try:
        chunk = os.read(leader, 65536)
      except OSError:
        break
      if not chunk:
        break
      out += chunk
    elif proc.poll() is not None:
      break
  os.close(leader)
  return out.decode(errors="replace"), proc.wait(timeout=10)


def test_statusbar_reserves_draws_and_restores_on_a_terminal(amk):
  out, status = run_on_pty(amk, ["--silent", "-f", str(DEMO)], rows=24, cols=100)
  assert status == 0, out
  assert "\x1b[1;23r" in out
  assert "| 8 done | 0 failed |" in out
  assert "\x1b[r\x1b[24;1H\x1b[2K" in out
  assert out.index("\x1b[1;23r") < out.index("| 8 done |") < out.rindex("\x1b[r")
  assert "tcc-statusbar: built 8 parts" in out


def test_statusbar_restores_the_terminal_on_sigint(amk):
  out, status = run_on_pty(amk, ["--silent", "-f", str(DEMO)], rows=24, cols=100,
                           interrupt="| 4 running |")
  assert status != 0, out
  assert "| 4 running |" in out
  assert "built 8 parts" not in out
  assert out.rindex("\x1b[r\x1b[24;1H\x1b[2K") > out.rindex("\x1b[7m")


def test_statusbar_draws_nothing_off_a_terminal(amk):
  r = sh(amk, ["--silent", "-f", str(DEMO)])
  assert r.returncode == 0, r.stderr
  assert "\x1b" not in r.stdout
  assert "tcc-statusbar: built 8 parts" in r.stdout

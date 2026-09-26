"""Pins the signal side of the spawn api.

A spawned job is a process group. Pinned: a fatal signal at the parent ends the job and
the shells under it, amk.kill takes a job's shell with it and wait reports the signal, a
normal exit sweeps a job still running, and under a terminal a background job that reads
it stops, which wait reports, until amk.foreground hands it the terminal.
"""

import fcntl
import os
import pty
import select
import signal
import subprocess
import termios
import time

import pytest

from conftest import popen, sh

# A sleep length nothing else on the machine uses, so the process table answers plainly.
NAP = "7.31"

sleeper = "\n".join([
  "seed := $(lua.persistent)",
  "sleeper:",
  "\t@sleep %s" % NAP,
  "linger:",
  "\t@echo spawned $(lua.persistent p = amk.spawn({'sleeper'}))",
  "\t@sleep 3",
  "leave:",
  "\t@echo spawned $(lua.persistent p = amk.spawn({'sleeper'}))",
  "killer:",
  "\t@echo r=$(lua.persistent p = amk.spawn({'sleeper'}) os.execute('sleep 0.3') amk.kill(p) local r = amk.wait(p) print(r.status .. r.signal))",
  "",
])

asker = "\n".join([
  "seed := $(lua.persistent)",
  "ask:",
  "\t@read x && echo got:$$x",
  "driver:",
  "\t@true $(lua.persistent p = amk.spawn({'ask'}) local r = amk.wait(p) io.stderr:write('first=' .. r.status .. '\\n') amk.foreground(p) r = amk.wait(p) io.stderr:write('then=' .. r.status .. '\\n'))",
  "",
])


def _napping():
  ps = subprocess.run(["ps", "-axo", "args="], capture_output=True, text=True).stdout
  return [ln for ln in ps.splitlines() if ln.strip() == "sleep " + NAP]


def _settle(deadline=3.0):
  end = time.time() + deadline
  while time.time() < end and _napping():
    time.sleep(0.05)
  return _napping()


@pytest.fixture
def no_nappers():
  assert not _napping(), "a stray sleeper predates this test"
  yield
  assert not _settle(), "a spawned job outlived the run"


@pytest.mark.engines("lua")
@pytest.mark.parametrize("sig", [signal.SIGTERM, signal.SIGINT])
def test_a_fatal_signal_at_the_parent_ends_the_job(amk, tmp_path, no_nappers, sig):
  mk = tmp_path / "sleeper.mk"
  mk.write_text(sleeper)
  p = popen(amk, ["-s", "-f", str(mk), "linger"], cwd=tmp_path,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
  deadline = time.time() + 5
  while time.time() < deadline and not _napping():
    time.sleep(0.05)
  assert _napping(), "the job never started"
  p.send_signal(sig)
  p.wait(timeout=10)
  assert p.returncode != 0


@pytest.mark.engines("lua")
def test_kill_takes_the_shell_and_wait_reports_the_signal(amk, tmp_path, no_nappers):
  mk = tmp_path / "sleeper.mk"
  mk.write_text(sleeper)
  r = sh(amk, ["-s", "-f", str(mk), "killer"], timeout=60)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "r=signal15" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("lua")
def test_a_normal_exit_sweeps_a_running_job(amk, tmp_path, no_nappers):
  mk = tmp_path / "sleeper.mk"
  mk.write_text(sleeper)
  r = sh(amk, ["-s", "-f", str(mk), "leave"], timeout=60)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "spawned" in r.stdout


def _read_until(fd, needle, deadline=10.0):
  out = b""
  end = time.time() + deadline
  while time.time() < end and needle not in out:
    ready, _, _ = select.select([fd], [], [], 0.2)
    if ready:
      try:
        chunk = os.read(fd, 4096)
      except OSError:
        break
      if not chunk:
        break
      out += chunk
  return out


@pytest.mark.engines("lua")
def test_a_background_reader_stops_until_foregrounded(amk, tmp_path):
  mk = tmp_path / "asker.mk"
  mk.write_text(asker)
  master, slave = pty.openpty()

  def own_the_terminal():
    os.setsid()
    fcntl.ioctl(slave, termios.TIOCSCTTY, 0)

  p = subprocess.Popen(["sh", "-c", '"$0" "$@"', str(amk), "-s", "-f", str(mk), "driver"],
                       cwd=tmp_path, stdin=slave, stdout=slave, stderr=slave,
                       preexec_fn=own_the_terminal)
  os.close(slave)
  try:
    out = _read_until(master, b"first=stopped")
    assert b"first=stopped" in out, out
    os.write(master, b"hi\n")
    out += _read_until(master, b"then=success")
    assert b"got:hi" in out and b"then=success" in out, out
    p.wait(timeout=10)
    assert p.returncode == 0
  finally:
    if p.poll() is None:
      p.kill()
    os.close(master)

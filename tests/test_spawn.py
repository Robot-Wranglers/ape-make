"""Pins the job functions, `$(amk.spawn goals)` and its siblings, from makefiles and guests.

Pinned: the text contract (a pid out of spawn, json out of wait, 1 or empty from job control,
a failure for a pid that is not a number), two spawns reporting their own statuses, a failing
goal's make code, a child make's reaping reaching wait, and a served request spawning.
"""

import fcntl
import os
import pty
import re
import select
import subprocess
import termios
import time

import pytest

from conftest import sh

paired = "\n".join([
  "seed := $(lua.exec)",
  "all:",
  "\t@echo result=[$(lua.exec local json = require('dkjson') a = amk.spawn('one') b = amk.spawn('two') local rb = json.decode(amk.wait(b)) print(json.decode(amk.wait(a)).status .. ' ' .. rb.status .. ' ' .. rb.code))]",
  "one:",
  "\t@echo one",
  "two:",
  "\t@exit 3",
  "",
])

parked = "\n".join([
  "seed := $(lua.exec)",
  "all: slow fast last",
  "slow:",
  "\t@sleep 0.4",
  "fast:",
  "\t@echo fast $(lua.exec p = amk.spawn('one'))",
  "last: fast slow",
  "\t@echo r=$(lua.exec print(require('dkjson').decode(amk.wait(p)).status))",
  "one:",
  "\t@sleep 0.1",
  "",
])

served = "\n".join([
  "seed := $(lua.exec)",
  "show:",
  "\t@echo r=$(lua.exec print(require('dkjson').decode(amk.wait(amk.spawn('one'))).status))",
  "one:",
  "\t@echo one",
  "",
])


@pytest.mark.engines("lua")
def test_each_spawn_reports_its_own_status(amk, tmp_path):
  mk = tmp_path / "paired.mk"
  mk.write_text(paired)
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "one" in r.stdout, r.stdout
  assert "result=[success failed 2]" in r.stdout, r.stdout + r.stderr


scripted = "\n".join([
  "seed := $(js.exec)",
  "all:",
  "\t@echo result=[$(js.exec const a = amk.spawn('talker'), b = amk.spawn('two'); const rb = JSON.parse(amk.wait(b)), ra = JSON.parse(amk.wait(a)); print([ra.status, ra.mail, rb.status, rb.code].join(' ')))]",
  "killed:",
  "\t@echo killed=[$(js.exec const p = amk.spawn('nap'); const early = amk.wait(p, '0'); amk.kill(p); print((early === '' ? 'empty' : early) + ' ' + JSON.parse(amk.wait(p)).status))]",
  "talker:",
  "\t@true $(js.exec amk.send('hi'))",
  "two:",
  "\t@exit 3",
  "nap:",
  "\t@sleep 5",
  "",
])


schemed = "\n".join([
  "$(amk.require s7)",
  "all:",
  "\t@true $(info result=[$(s7.exec (load \"json.scm\") (let* ((a (amk-spawn \"one\")) (b (amk-spawn \"two\")) (early (amk-wait b \"0\")) (rb (json-read (amk-wait b))) (ra (json-read (amk-wait a)))) (display (list (ra (quote status)) (rb (quote status)) (rb (quote code)) (if (string=? early \"\") \"none\" early)))))])",
  "one:",
  "\t@echo one",
  "two:",
  "\t@sleep 0.2 ; exit 3",
  "",
])


@pytest.mark.engines("s7")
def test_s7_spawn_and_wait_report_status_and_a_nonblocking_wait_answers_empty(amk, tmp_path):
  mk = tmp_path / "schemed.mk"
  mk.write_text(schemed)
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "one" in r.stdout, r.stdout
  assert '("success" "failed" 2 "none")]' in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("js")
def test_js_spawn_reports_status_code_and_mail(amk, tmp_path):
  mk = tmp_path / "scripted.mk"
  mk.write_text(scripted)
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "result=[success hi failed 2]" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("js")
def test_js_kill_ends_a_job_a_nonblocking_wait_left_running(amk, tmp_path):
  mk = tmp_path / "scripted.mk"
  mk.write_text(scripted)
  r = sh(amk, ["-s", "-f", str(mk), "killed"], timeout=60)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "killed=[empty signal]" in r.stdout, r.stdout + r.stderr


awaited = "\n".join([
  "$(amk.require sqlite, js)",
  "load tspace",
  "seed := $(js.exec)",
  "ticking:",
  "\t@echo r=[$(js.exec let ticks = 0, done = false; const tick = () => { if (!done) { ticks++; os.setTimeout(tick, 50); } }; tick(); const r = await amk.exited(Number(amk.spawn('nap'))); done = true; print(r.status + ' ' + (ticks >= 4)))]",
  "reversed:",
  "\t@echo r=[$(js.exec const order = [], a = Number(amk.spawn('nap')), b = Number(amk.spawn('blink')); await Promise.all([amk.exited(a).then((r) => order.push('a' + (r.pid === a))), amk.exited(b).then((r) => order.push('b' + (r.pid === b)))]); print(order.join(' ')))]",
  "answered:",
  "\t@echo r=[$(js.exec await amk.exited(Number(amk.spawn('asker'))); print(JSON.parse(amk.call('tspace', 'inp', 'asked', '?str')).t[1]))]",
  "stranger:",
  "\t@echo r=[$(js.exec await amk.exited(1).then(() => print('settled'), () => print('refused')))]",
  "nap:",
  "\t@sleep 0.5",
  "blink:",
  "\t@sleep 0.1",
  "asker:",
  "\t@: $(js.exec amk.call('tspace', 'out', 'asked', 'answered'))",
  "",
])


@pytest.mark.engines("js")
@pytest.mark.parametrize("goal, want", [
  ("ticking", "r=[success true]"),
  ("reversed", "r=[btrue atrue]"),
  ("answered", "r=[answered]"),
  ("stranger", "r=[refused]"),
], ids=["timer-keeps-firing", "reverse-order", "store-call-answered", "unknown-pid"])
def test_exited_settles_from_the_reactor(amk, tmp_path, goal, want):
  """amk.exited resolves on the child's exit with no polling, and the reactor answers the child's store calls meanwhile."""
  mk = tmp_path / "awaited.mk"
  mk.write_text(awaited)
  r = sh(amk, ["-s", "-f", str(mk), goal], timeout=30)
  assert r.returncode == 0, r.stdout + r.stderr
  assert want in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("lua")
def test_a_child_make_reaped_first_still_reaches_wait(amk, tmp_path):
  mk = tmp_path / "parked.mk"
  mk.write_text(parked)
  r = sh(amk, ["-s", "-j2", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "r=success" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("lua")
def test_a_served_request_can_spawn(amk, tmp_path, zygote):
  mk = tmp_path / "served.mk"
  mk.write_text(served)
  sock = zygote(["-f", str(mk)], cwd=tmp_path)
  r = sh(amk, ["--client", str(sock), "show"], cwd=tmp_path, timeout=60)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "one" in r.stdout and "r=success" in r.stdout, r.stdout + r.stderr


goals = "\n".join([
  "seed := $(lua.exec)",
  "all:",
  "\t@: $(lua.exec amk.wait(amk.spawn('one two')))",
  "one:",
  "\t@echo one sees [$(MAKECMDGOALS)]",
  "two:",
  "\t@echo two sees [$(MAKECMDGOALS)]",
  "",
])


rearmed = "\n".join([
  "seed := $(lua.exec)",
  "me := $(shell echo $$PPID)",
  "all:",
  "\t@echo parent=$(me)",
  "\t@: $(lua.exec amk.wait(amk.spawn('one')) amk.wait(amk.spawn('one')))",
  "one:",
  "\t@echo child=$(me)",
  "",
])


@pytest.mark.engines("lua")
def test_a_spawned_job_rearms_its_pid(amk, tmp_path):
  """A name in AMK_REARM_PID is the job's own pid, as it is a served child's, not the parent's."""
  mk = tmp_path / "rearmed.mk"
  mk.write_text(rearmed)
  r = sh(amk, ["-s", "-f", str(mk)], env={"AMK_REARM_PID": "me"}, timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  pids = re.findall(r"^(?:parent|child)=(\d+)$", r.stdout, re.M)
  assert len(pids) == 3, r.stdout + r.stderr
  assert len(set(pids)) == 3, f"a job kept another's pid: {pids}\n{r.stdout}"


@pytest.mark.engines("lua")
def test_a_spawned_job_sees_its_own_goals(amk, tmp_path):
  """The spawn runs while a recipe expands; its goals must reach every target, not the expanding one's set."""
  mk = tmp_path / "goals.mk"
  mk.write_text(goals)
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "one sees [ one two]" in r.stdout, r.stdout + r.stderr
  assert "two sees [ one two]" in r.stdout, r.stdout + r.stderr


parity = "\n".join([
  "seed := $(lua.exec)",
  "spawner:",
  "\t@: $(lua.exec amk.wait(amk.spawn('show')))",
  "failer:",
  "\t@echo spawned=$(lua.exec local r = require('dkjson').decode(amk.wait(amk.spawn('fail'))) print(r.status .. ' ' .. r.code))",
  "show:",
  "\t@printf 'goals=[%s]\\n' '$(MAKECMDGOALS)'",
  "\t@printf 'flags=[%s]\\n' '$(MAKEFLAGS)'",
  "\t@printf 'level=[%s]\\n' '$(MAKELEVEL)'",
  "fail:",
  "\t@exit 3",
  "",
])


def _shown(r):
  return [ln for ln in r.stdout.splitlines() if re.match(r"^(goals|flags|level)=\[", ln)]


@pytest.mark.engines("lua")
def test_a_spawned_job_and_a_served_child_see_the_same_make(amk, tmp_path, zygote):
  """Both are children of the parsed image, so one goal reports the same goals, flags and level from either."""
  (tmp_path / "parity.mk").write_text(parity)
  sock = zygote(["-s", "-f", "parity.mk", "show"], tmp_path)
  served = sh(amk, ["--client", str(sock), "show"], cwd=tmp_path, timeout=120)
  spawned = sh(amk, ["-s", "-f", "parity.mk", "spawner"], cwd=tmp_path, timeout=120)
  assert served.returncode == 0 and spawned.returncode == 0, served.stderr + spawned.stderr
  assert len(_shown(served)) == 3, served.stdout + served.stderr
  assert _shown(served) == _shown(spawned)


@pytest.mark.engines("lua")
def test_a_spawned_job_and_a_served_child_fail_with_the_same_code(amk, tmp_path, zygote):
  """A failed goal is make's exit 2 from a served child and status failed with code 2 from a spawned job."""
  (tmp_path / "parity.mk").write_text(parity)
  sock = zygote(["-s", "-f", "parity.mk", "show"], tmp_path)
  served = sh(amk, ["--client", str(sock), "fail"], cwd=tmp_path, timeout=120)
  spawned = sh(amk, ["-s", "-f", "parity.mk", "failer"], cwd=tmp_path, timeout=120)
  assert served.returncode == 2, served.stdout + served.stderr
  assert "spawned=failed 2" in spawned.stdout, spawned.stdout + spawned.stderr


paused = {
  "lua": "\n".join([
    "all:",
    "\t@echo r=[$(lua.exec local json = require('dkjson') p = amk.spawn('nap') local s = amk.stop(p) local a = json.decode(amk.wait(p)).status local c = amk.resume(p) print(s .. ' ' .. a .. ' ' .. c .. ' ' .. json.decode(amk.wait(p)).status))]",
    "foreign:",
    "\t@echo r=[$(lua.exec print('stop=' .. amk.stop($(other)) .. ' resume=' .. amk.resume($(other)) .. ' kill=' .. amk.kill($(other))))]",
    "nap:",
    "\t@sleep 0.5",
    "",
  ]),
  "js": "\n".join([
    "all:",
    "\t@echo r=[$(js.exec const p = amk.spawn('nap'); const s = amk.stop(p), a = JSON.parse(amk.wait(p)).status, c = amk.resume(p); print([s, a, c, JSON.parse(amk.wait(p)).status].join(' ')))]",
    "foreign:",
    "\t@echo r=[$(js.exec print(`stop=${amk.stop($(other))} resume=${amk.resume($(other))} kill=${amk.kill($(other))}`))]",
    "nap:",
    "\t@sleep 0.5",
    "",
  ]),
}


@pytest.mark.parametrize("engine", [
  pytest.param("lua", marks=pytest.mark.engines("lua")),
  pytest.param("js", marks=pytest.mark.engines("js")),
])
def test_a_stopped_job_reports_stopped_then_finishes_once_resumed(amk, tmp_path, engine):
  mk = tmp_path / "paused.mk"
  mk.write_text(paused[engine])
  r = sh(amk, ["-s", "-f", str(mk), "other=0"], timeout=60)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "r=[1 stopped 1 success]" in r.stdout, r.stdout + r.stderr


@pytest.mark.parametrize("engine", [
  pytest.param("lua", marks=pytest.mark.engines("lua")),
  pytest.param("js", marks=pytest.mark.engines("js")),
])
def test_job_control_refuses_a_pid_that_is_not_a_spawned_job(amk, tmp_path, engine):
  """The pid is a process of the test's own, and stop, resume and kill must all leave it running."""
  mk = tmp_path / "paused.mk"
  mk.write_text(paused[engine])
  other = subprocess.Popen(["sleep", "30"], start_new_session=True)
  try:
    r = sh(amk, ["-s", "-f", str(mk), "foreign", f"other={other.pid}"], timeout=60)
    state = subprocess.run(["ps", "-o", "stat=", "-p", str(other.pid)], capture_output=True, text=True).stdout
    alive = other.poll() is None
  finally:
    other.kill()
    other.wait()
  assert r.returncode == 0, r.stdout + r.stderr
  assert "r=[stop= resume= kill=]" in r.stdout, r.stdout + r.stderr
  assert "T" not in state, state
  assert alive


from_make = "\n".join([
  "all:",
  "\t@echo pid=[$(eval p := $(amk.spawn talker))$(p)]",
  "\t@echo 'rec=$(amk.wait $(p))'",
  "killed:",
  "\t@echo early=[$(eval p := $(amk.spawn nap))$(amk.wait $(p),0)] sent=[$(amk.kill $(p))] status=[$(findstring \"signal\",$(amk.wait $(p)))]",
  "stranger:",
  "\t@echo kill=[$(amk.kill 1)] stop=[$(amk.stop 1)]",
  "bad:",
  "\t@echo $(amk.kill twelve)",
  "badset:",
  "\t@echo $(amk.wait 12 x)",
  "nogoals:",
  "\t@echo $(amk.spawn )",
  "talker:",
  "\t@printf 'a \"q\" \\\\ b\\n' >&$$AMK_MAIL",
  "nap:",
  "\t@sleep 5",
  "",
])


@pytest.mark.parametrize("goal, want", [
  ("all", 'rec={"pid": '),
  ("killed", "early=[] sent=[1] status=[signal]"),
  ("stranger", "kill=[] stop=[]"),
], ids=["spawn-and-wait", "nonblocking-then-kill", "foreign-pid-refused"])
def test_the_job_functions_answer_text_from_a_makefile(amk, tmp_path, goal, want):
  """No guest: spawn answers a pid, wait a json record, a nonblocking wait empty, kill 1 or empty."""
  mk = tmp_path / "from_make.mk"
  mk.write_text(from_make)
  r = sh(amk, ["-s", "-f", str(mk), goal], timeout=60)
  assert r.returncode == 0, r.stdout + r.stderr
  assert want in r.stdout, r.stdout + r.stderr


def test_wait_escapes_mail_as_json(amk, tmp_path):
  """Mail with a quote, a backslash and a newline survives the record as one json string."""
  import json
  mk = tmp_path / "from_make.mk"
  mk.write_text(from_make)
  r = sh(amk, ["-s", "-f", str(mk)], timeout=60)
  assert r.returncode == 0, r.stdout + r.stderr
  pid = re.search(r"^pid=\[(\d+)\]$", r.stdout, re.M)
  assert pid, r.stdout
  rec = json.loads(r.stdout.split("rec=", 1)[1].strip())
  assert rec["pid"] == int(pid.group(1)), rec
  assert rec["status"] == "success" and rec["mail"] == 'a "q" \\ b\n', rec


held = "\n".join([
  "fast:", "\t@true",
  "slow:", "\t@sleep 1",
  "talk:", "\t@printf 'hi' >&$$AMK_MAIL",
  "all:", "\t@true",
  "o := $(amk.spawn fast)",
  "s := $(amk.spawn slow)",
  "$(info set=$(amk.wait $(s)))",
  "$(info other=$(amk.wait $(o)))",
  "t := $(amk.spawn talk)",
  "$(info early=[$(amk.wait $(t),peek)])",
  "x := $(shell sleep 1)",
  "$(info peek=$(amk.wait $(t),peek))",
  "$(info take=$(amk.wait $(t)))",
  "$(info gone=[$(amk.wait $(t),0)])",
  "$(info none=[$(amk.wait )])",
  "$(info stale=[$(amk.wait $(t))])",
  "a := $(amk.spawn slow)",
  "b := $(amk.spawn fast)",
  "$(info a=$(a) b=$(b))",
  "$(info first=$(amk.wait $(a) $(b)))",
  "$(info second=$(amk.wait $(a) $(b)))",
  "",
])


def test_wait_on_a_set_reaps_no_job_outside_it_and_a_peek_holds_the_record(amk, tmp_path):
  """A wait on pids reaps only them; peek answers without taking; a blocking wait with nothing to wait for answers empty."""
  import json
  mk = tmp_path / "held.mk"
  mk.write_text(held)
  r = sh(amk, ["-s", "-f", str(mk)], timeout=60)
  assert r.returncode == 0, r.stdout + r.stderr
  out = dict(line.split("=", 1) for line in r.stdout.splitlines() if "=" in line and not line.startswith("a="))
  ab = re.search(r"^a=(\d+) b=(\d+)$", r.stdout, re.M)
  assert json.loads(out["set"])["status"] == json.loads(out["other"])["status"] == "success"
  assert out["early"] == "[]"
  assert out["peek"] == out["take"] and json.loads(out["take"])["mail"] == "hi"
  assert out["gone"] == out["none"] == out["stale"] == "[]"
  assert json.loads(out["first"])["pid"] == int(ab.group(2))
  assert json.loads(out["second"])["pid"] == int(ab.group(1))


@pytest.mark.parametrize("goal, why", [
  ("badset", "$(amk.wait ...): pid 'x' is not a number"),
  ("bad", "$(amk.kill ...): pid 'twelve' is not a number"),
  ("nogoals", "$(amk.spawn ...): between 1 and 63 goals"),
], ids=["set-pid-not-a-number", "pid-not-a-number", "no-goals"])
def test_malformed_job_arguments_fail_naming_the_function(amk, tmp_path, goal, why):
  mk = tmp_path / "from_make.mk"
  mk.write_text(from_make)
  r = sh(amk, ["-s", "-f", str(mk), goal], timeout=60)
  assert r.returncode != 0, r.stdout + r.stderr
  assert why in r.stderr, r.stdout + r.stderr


argv_make = "\n".join([
  "argv:",
  "\t@echo 'rec=$(amk.wait $(amk.spawn.argv echoer 'msg=a b' \"tag=c d\"))'",
  "plain:",
  "\t@echo 'rec=$(amk.wait $(amk.spawn echoer msg=a b))'",
  "noargv:",
  "\t@echo $(amk.spawn.argv )",
  "echoer:",
  "\t@printf '%s|%s' \"$(msg)\" \"$(tag)\" >&$$AMK_MAIL",
  "b:",
  "\t@true",
  "",
])


@pytest.mark.parametrize("goal, mail", [
  ("argv", "a b|c d"),
  ("plain", "a|"),
], ids=["quoted-words-kept", "plain-splits-on-space"])
def test_spawn_argv_splits_as_a_shell_would(amk, tmp_path, goal, mail):
  """spawn.argv keeps a quoted NAME=value whole, as eng.argv does; plain spawn still splits on whitespace."""
  import json
  mk = tmp_path / "argv.mk"
  mk.write_text(argv_make)
  r = sh(amk, ["-s", "-f", str(mk), goal], timeout=60)
  assert r.returncode == 0, r.stdout + r.stderr
  rec = json.loads(r.stdout.strip().removeprefix("rec="))
  assert rec["status"] == "success" and rec["mail"] == mail, rec


def test_spawn_argv_of_nothing_fails_naming_itself(amk, tmp_path):
  mk = tmp_path / "argv.mk"
  mk.write_text(argv_make)
  r = sh(amk, ["-s", "-f", str(mk), "noargv"], timeout=60)
  assert r.returncode != 0, r.stdout + r.stderr
  assert "$(amk.spawn.argv ...): between 1 and 63 goals" in r.stderr, r.stdout + r.stderr


reader = "\n".join([
  "ask:",
  "\t@read x && echo got:$$x",
  "driver:",
  "\t@true $(lua.exec local json = require('dkjson') p = amk.spawn('ask') local w = function(t) io.stderr:write(t .. '=' .. json.decode(amk.wait(p)).status .. '\\n') end w('first') amk.resume(p) w('resumed') amk.foreground(p) w('then'))",
  "",
])


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
def test_resume_leaves_the_terminal_and_foreground_still_continues(amk, tmp_path):
  """A background reader stops on the terminal; resumed it reads again and stops again, and only foreground lets it read."""
  mk = tmp_path / "reader.mk"
  mk.write_text(reader)
  master, slave = pty.openpty()

  def own_the_terminal():
    os.setsid()
    fcntl.ioctl(slave, termios.TIOCSCTTY, 0)

  p = subprocess.Popen(["sh", "-c", 'exec "$0" "$@"', str(amk), "-s", "-f", str(mk), "driver"],
                       cwd=tmp_path, stdin=slave, stdout=slave, stderr=slave,
                       preexec_fn=own_the_terminal)
  os.close(slave)
  try:
    out = _read_until(master, b"resumed=stopped")
    assert b"first=stopped" in out and b"resumed=stopped" in out, out
    os.write(master, b"hi\n")
    out += _read_until(master, b"then=success")
    assert b"got:hi" in out and b"then=success" in out, out
    p.wait(timeout=10)
    assert p.returncode == 0
  finally:
    if p.poll() is None:
      p.kill()
    os.close(master)

"""Pins the resident role and the roles beside it.

`--resident <args>` forks a zygote on the caller's argv, routes the command and its
recursion through it, and reaps on the way out. Pinned: one parse however deep the
recursion, recursion by make's own variable is routed, nothing survives the run, a
signalled client dies as a cold make does, the older roles still behave, which requests
are refused, what a served child sees and may define, and what a rearm recomputes.
"""

import signal
import subprocess
import time

import pytest

from conftest import popen, sh, _run_dirs

# Each parse announces itself, so parses are counted wherever recursion goes.
program = "\n".join([
  "n ?= 0",
  "$(info parsed)",
  "top:",
  "\t@if [ $(n) -lt $(depth) ]; then $(MAKE) -f Makefile n=$$(( $(n) + 1 )) top; \\",
  "\t else printf 'bottom n=%s MAKE=%s\\n' '$(n)' '$(MAKE)'; fi",
  "",
])
leaf_program = "leaf:\n\t@printf 'leaf ran\\n'\n"
# A parse that names its file, so a test can tell which makefiles a run read.
loud_leaf = "$(info parsed Makefile)\n" + leaf_program
loud_extra = "$(info parsed Extra.mk)\nextra:\n\t@printf 'extra ran\\n'\n"


@pytest.fixture
def prog(tmp_path):
  (tmp_path / "Makefile").write_text(program)
  return tmp_path


def _make(amk, prog, *args, depth=8):
  return sh(amk, [*args, "-f", "Makefile", "--no-print-directory", f"depth={depth}", "top"],
            cwd=prog, env={"NO_COLOR": "1", "TERM": "dumb"})


def _parses(r):
  return (r.stdout + r.stderr).count("parsed")


def _bottom(r):
  for line in (r.stdout + r.stderr).splitlines():
    if line.startswith("bottom "):
      return line
  raise AssertionError(f"program never reached bottom\n{r.stdout}\n{r.stderr}")


def test_cold_parses_once_per_level(amk, prog):
  """The baseline: without a zygote every level of recursion is a fresh parse."""
  r = _make(amk, prog, depth=8)
  assert r.returncode == 0, r.stderr[-2000:]
  assert _parses(r) == 9


def test_resident_parses_once_however_deep(amk, prog, no_leftovers):
  """The whole point: one parse serves every level."""
  shallow = _make(amk, prog, "--resident", depth=4)
  deep = _make(amk, prog, "--resident", depth=32)
  assert shallow.returncode == 0, shallow.stderr[-2000:]
  assert deep.returncode == 0, deep.stderr[-2000:]
  # The zygote's own parse is not on the caller's streams, so none is visible.
  assert _parses(shallow) == 0
  assert _parses(deep) == 0
  assert _bottom(shallow).startswith("bottom n=4 ")
  assert _bottom(deep).startswith("bottom n=32 ")


def test_resident_routes_recursion_by_path(amk, prog, no_leftovers):
  """A makefile recursing through make's own variable never consults the path."""
  r = _make(amk, prog, "--resident", depth=2)
  assert r.returncode == 0, r.stderr[-2000:]
  bottom = _bottom(r)
  assert "--client" in bottom, bottom
  assert "zygote.sock" in bottom, bottom


def test_cold_leaves_make_alone(amk, prog):
  """Without the role, the variable is whatever make itself decided."""
  r = _make(amk, prog, depth=2)
  assert "--client" not in _bottom(r)


def test_resident_reaps_after_an_interrupt(amk, prog, no_leftovers):
  """An interrupted run must not strand a zygote or its run directory."""
  before = set(_run_dirs())
  p = popen(amk, ["--resident", "-f", "Makefile", "--no-print-directory", "depth=400", "top"],
            cwd=prog, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
  deadline = time.time() + 60
  while time.time() < deadline and not set(_run_dirs()) - before:
    time.sleep(0.05)
  assert set(_run_dirs()) - before, "resident run never created its run directory"
  p.send_signal(signal.SIGINT)
  p.wait(timeout=60)
  # The fixture asserts the cleanup; give the reap a moment to land first.
  for _ in range(100):
    if not set(_run_dirs()) - before:
      break
    time.sleep(0.05)


def test_bare_invocation_is_still_stock_make(amk, prog):
  """The bare role carries the most weight: it is make."""
  v = sh(amk, ["--version"], timeout=60)
  assert v.stdout.startswith("GNU Make")
  r = _make(amk, prog, depth=0)
  assert r.returncode == 0
  assert _parses(r) == 1


def _napping():
  ps = subprocess.run(["pgrep", "-f", "sleep 20"], capture_output=True, text=True)
  return [p for p in ps.stdout.split() if p]


def _signalled(amk, args, cwd, sig):
  p = popen(amk, args, cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
  deadline = time.time() + 60
  while time.time() < deadline and not _napping():
    time.sleep(0.05)
  assert _napping(), "recipe never started"
  p.send_signal(sig)
  rc = p.wait(timeout=60)
  for _ in range(200):
    if not _napping():
      break
    time.sleep(0.05)
  return rc, _napping()


@pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM])
def test_a_signalled_client_dies_as_a_cold_make_does(sig, amk, tmp_path, zygote):
  """A supervisor signals its child, which under routing is the client."""
  (tmp_path / "Makefile").write_text("nap:\n\tsleep 20\n")
  cold_rc, cold_left = _signalled(amk, ["-f", "Makefile", "nap"], tmp_path, sig)
  assert not cold_left, "cold run stranded its recipe"
  sock = zygote(["-f", "Makefile", "nap"], tmp_path)
  hot_rc, hot_left = _signalled(
    amk, ["--client", str(sock), "--", str(amk), "-f", "Makefile", "nap"], tmp_path, sig)
  assert not hot_left, "routed run stranded its recipe"
  assert hot_rc == cold_rc, f"routed exit {hot_rc}, cold exit {cold_rc}"


def test_a_request_naming_no_goal_builds_the_default(amk, tmp_path, no_leftovers):
  """An entrypoint gets argv-free invocations, which must build what make would."""
  (tmp_path / "Makefile").write_text(leaf_program)
  for args in ([], ["--resident"]):
    r = sh(amk, args, cwd=tmp_path, env={"NO_COLOR": "1"})
    assert r.returncode == 0, f"{args}: {r.stderr[-2000:]}"
    assert "leaf ran" in r.stdout, f"{args} built nothing\n{r.stdout}"


def test_a_refused_request_falls_back_instead_of_answering_wrong(amk, tmp_path, zygote):
  """Negotiation refuses an option the zygote lacks; the caller's cold command runs."""
  (tmp_path / "Makefile").write_text(leaf_program)
  sock = zygote(["-f", "Makefile", "leaf"], tmp_path)
  r = sh(amk, ["--client", str(sock), "--", str(amk), "--dry-run", "-f", "Makefile", "leaf"],
         cwd=tmp_path, timeout=120)
  # The zygote holds no dry-run flag, so the caller's own command prints the recipe.
  assert r.returncode == 0, r.stderr[-2000:]
  assert "printf" in r.stdout, f"not a dry run's output\n{r.stdout}"


def _cold_after(amk, sock, *args):
  return ["--client", str(sock), "--", str(amk), *args]


def test_a_request_restating_the_zygotes_makefile_is_served(amk, tmp_path, zygote):
  """The zygote holds its own makefile option, so a request may repeat it."""
  (tmp_path / "Makefile").write_text(loud_leaf)
  sock = zygote(["-f", "Makefile", "leaf"], tmp_path)
  r = sh(amk, _cold_after(amk, sock, "-f", "Makefile", "leaf"), cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stderr[-2000:]
  assert "leaf ran" in r.stdout
  assert "parsed" not in r.stdout + r.stderr, "a served request read a makefile"


def test_a_request_naming_another_makefile_is_refused(amk, tmp_path, zygote):
  """A different makefile is a different make, so the caller's cold command runs."""
  (tmp_path / "Makefile").write_text(loud_leaf)
  (tmp_path / "Extra.mk").write_text(loud_extra)
  sock = zygote(["-f", "Makefile", "leaf"], tmp_path)
  r = sh(amk, _cold_after(amk, sock, "-f", "Extra.mk", "extra"), cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stderr[-2000:]
  assert "extra ran" in r.stdout
  assert "parsed Extra.mk" in r.stdout, "the cold command never parsed"
  assert "parsed Makefile" not in r.stdout


def test_a_request_adding_a_makefile_is_refused(amk, tmp_path, zygote):
  """A makefile beyond the zygote's own is refused too, and the cold command reads both."""
  (tmp_path / "Makefile").write_text(loud_leaf)
  (tmp_path / "Extra.mk").write_text(loud_extra)
  sock = zygote(["-f", "Makefile", "leaf"], tmp_path)
  r = sh(amk, _cold_after(amk, sock, "-f", "Makefile", "-f", "Extra.mk", "extra"),
         cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stderr[-2000:]
  assert "extra ran" in r.stdout
  assert "parsed Makefile" in r.stdout and "parsed Extra.mk" in r.stdout, r.stdout


def test_a_refusal_with_no_cold_command_fails(amk, tmp_path, zygote):
  """A refused request with nothing to fall back on is an error, never a wrong answer."""
  (tmp_path / "Makefile").write_text(loud_leaf)
  (tmp_path / "Extra.mk").write_text(loud_extra)
  sock = zygote(["-f", "Makefile", "leaf"], tmp_path)
  r = sh(amk, ["--client", str(sock), "-f", "Extra.mk", "extra"], cwd=tmp_path,
         env={"AMK_COLD": ""}, timeout=120)
  assert r.returncode == 2, r.stdout + r.stderr
  assert "no zygote answered" in r.stderr, r.stderr
  assert "extra ran" not in r.stdout


def test_a_served_child_cannot_define_a_rule(amk, tmp_path, zygote):
  """A rule defined from a recipe is refused by a served child as by a cold make."""
  (tmp_path / "Makefile").write_text("rule:\n\t$(eval late:;@echo late ran)\n\t@echo rule ran\n")
  sock = zygote(["-f", "Makefile", "rule"], tmp_path)
  cold = sh(amk, ["-f", "Makefile", "rule"], cwd=tmp_path, timeout=120)
  served = sh(amk, ["--client", str(sock), "rule"], cwd=tmp_path, timeout=120)
  for r in (cold, served):
    assert r.returncode == 2, r.stdout + r.stderr
    assert "prerequisites cannot be defined in recipes" in r.stderr, r.stderr
    assert "rule ran" not in r.stdout


def _named(r, key):
  for line in r.stdout.splitlines():
    if line.startswith(key + "=["):
      return line[len(key) + 2:-1]
  raise AssertionError(f"no {key} line\n{r.stdout}\n{r.stderr}")


def test_a_served_child_names_its_makefiles_and_goals_as_a_cold_make_does(amk, tmp_path, zygote):
  """The makefile list, the goals and the level are the request's, word for word."""
  (tmp_path / "Makefile").write_text("\n".join([
    "include Part.mk",
    "vars other:",
    "\t@printf 'list=[%s]\\n' '$(MAKEFILE_LIST)'",
    "\t@printf 'goals=[%s]\\n' '$(MAKECMDGOALS)'",
    "\t@printf 'level=[%s]\\n' '$(MAKELEVEL)'",
    "",
  ]))
  (tmp_path / "Part.mk").write_text("part := read\n")
  sock = zygote(["-f", "Makefile", "vars"], tmp_path)
  cold = sh(amk, ["-f", "Makefile", "vars"], cwd=tmp_path, timeout=120)
  served = sh(amk, ["--client", str(sock), "vars"], cwd=tmp_path, timeout=120)
  assert cold.returncode == 0 and served.returncode == 0, cold.stderr + served.stderr
  assert _named(cold, "list").split() == ["Makefile", "Part.mk"]
  for key in ("list", "goals", "level"):
    assert _named(served, key).split() == _named(cold, key).split(), key


@pytest.mark.xfail(strict=False, reason="a served child's goals carry a leading space")
def test_a_served_childs_goals_match_a_cold_makes_byte_for_byte(amk, tmp_path, zygote):
  """The goals variable holds the goals and nothing else."""
  (tmp_path / "Makefile").write_text("vars:\n\t@printf 'goals=[%s]\\n' '$(MAKECMDGOALS)'\n")
  sock = zygote(["-f", "Makefile", "vars"], tmp_path)
  cold = sh(amk, ["-f", "Makefile", "vars"], cwd=tmp_path, timeout=120)
  served = sh(amk, ["--client", str(sock), "vars"], cwd=tmp_path, timeout=120)
  assert _named(served, "goals") == _named(cold, "goals") == "vars"


rearm_program = "\n".join([
  "soft ?= parsed",
  "hard := parsed",
  "show:",
  "\t@printf 'soft=[%s]\\n' '$(soft)'",
  "\t@printf 'hard=[%s]\\n' '$(hard)'",
  "",
])


def test_a_parse_time_value_is_frozen_for_every_request(amk, tmp_path, zygote):
  """Without a rearm the zygote's parse answers, even where a cold make would take the caller's value."""
  (tmp_path / "Makefile").write_text(rearm_program)
  sock = zygote(["-f", "Makefile", "show"], tmp_path)
  caller = {"soft": "caller", "hard": "caller"}
  cold = sh(amk, ["-f", "Makefile", "show"], cwd=tmp_path, env=caller, timeout=120)
  served = sh(amk, ["--client", str(sock), "show"], cwd=tmp_path, env=caller, timeout=120)
  assert (_named(cold, "soft"), _named(cold, "hard")) == ("caller", "parsed")
  assert (_named(served, "soft"), _named(served, "hard")) == ("parsed", "parsed")


def test_a_rearmed_name_takes_the_callers_value(amk, tmp_path, zygote):
  """A name the caller lists is recomputed per request, and outranks the makefile's own assignment."""
  (tmp_path / "Makefile").write_text(rearm_program)
  sock = zygote(["-f", "Makefile", "show"], tmp_path)
  one = sh(amk, ["--client", str(sock), "show"], cwd=tmp_path, timeout=120,
           env={"AMK_REARM": "soft", "soft": "caller", "hard": "caller"})
  both = sh(amk, ["--client", str(sock), "show"], cwd=tmp_path, timeout=120,
            env={"AMK_REARM": "soft hard", "soft": "caller", "hard": "caller"})
  assert (_named(one, "soft"), _named(one, "hard")) == ("caller", "parsed")
  assert (_named(both, "soft"), _named(both, "hard")) == ("caller", "caller")


def test_a_rearm_does_not_outlive_its_request(amk, tmp_path, zygote):
  """The zygote stays pristine, so a later request without the rearm sees the parse again."""
  (tmp_path / "Makefile").write_text(rearm_program)
  sock = zygote(["-f", "Makefile", "show"], tmp_path)
  sh(amk, ["--client", str(sock), "show"], cwd=tmp_path, timeout=120,
     env={"AMK_REARM": "soft hard", "soft": "caller", "hard": "caller"})
  later = sh(amk, ["--client", str(sock), "show"], cwd=tmp_path, timeout=120)
  assert (_named(later, "soft"), _named(later, "hard")) == ("parsed", "parsed")


def test_a_served_request_keeps_the_clients_streams(amk, tmp_path, zygote):
  """Stdin and stdout belong to the client, so a routed recipe still pipes."""
  (tmp_path / "Makefile").write_text("filter:\n\t@tr a-z A-Z\n")
  sock = zygote(["-f", "Makefile", "filter"], tmp_path)
  r = sh(amk, ["--client", str(sock), "filter"], cwd=tmp_path, stdin="piped\n")
  assert r.returncode == 0, r.stderr
  assert r.stdout == "PIPED\n"


def test_a_client_waits_out_a_long_parse(amk, tmp_path, sock, monkeypatch):
  """A zygote still parsing is waited for as long as it lives, so no cold parse runs beside it."""
  (tmp_path / "Makefile").write_text("\n".join([
    "slow := $(shell sleep 25)",
    "show:",
    "\t@echo seen=$(lua.persistent print(seen))",
    "",
  ]))
  monkeypatch.setenv("AMK_LUA_INIT", "seen = 'zygote'")
  z = popen(amk, ["--serve", str(sock), "-f", "Makefile"], cwd=tmp_path, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
  monkeypatch.delenv("AMK_LUA_INIT")
  try:
    r = sh(amk, ["--client", str(sock), "show"], cwd=tmp_path, env={"AMK_ZYGOTE": str(z.pid)}, timeout=120)
  finally:
    z.kill()
    z.wait(timeout=30)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "seen=zygote" in r.stdout, r.stdout + r.stderr


def test_a_zygote_parks_after_remaking_an_included_file(amk, tmp_path, zygote):
  """A parse that remakes an included file restarts make; the re-exec keeps the serve words."""
  (tmp_path / "Makefile").write_text("\n".join([
    "-include generated.mk",
    "generated.mk:",
    "\t@printf 'gen := made\\n' > $@",
    "show:",
    "\t@printf 'gen=%s restarts=%s\\n' '$(gen)' '$(MAKE_RESTARTS)'",
    "",
  ]))
  sock = zygote(["-f", "Makefile", "show"], tmp_path)
  r = sh(amk, ["--client", str(sock), "show"], cwd=tmp_path, timeout=120)
  assert r.returncode == 0, r.stderr[-2000:]
  assert "gen=made restarts=1" in r.stdout, r.stdout

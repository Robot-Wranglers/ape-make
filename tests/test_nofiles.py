"""Pins that amk processes coordinate through descriptors, never through filesystem names.

A recipe's call channel is its own: concurrent callers under -j never read each other's
replies, a request left unread dies with its recipe, and a caller gone before its reply costs
make nothing. A forked guest's write lands when the call returns. The census runs the ape
under its own syscall trace with a private temp dir; every name made there is on the allowlist.
"""

import re
import time

import pytest

from conftest import sh

# Names the ape may make under the temp dir, as regular expressions on the path below it; an entry here is a design decision.
ALLOWED = [
  r"amk-resident\.\w+(/zygote\.sock)?",
  r"\.ape-[\w.]+",
]

names = "a b c d e f g h".split()

concurrent = "\n".join([
  "SHELL := bash",
  *[f"$(jq.ns K{n}, create)" for n in names],
  "seed := " + " ".join(f'$(K{n}.update "{n}")' for n in names),
  "all: " + " ".join(names),
  " ".join(names) + ":",
  "\t@source amk.sh; bad=0; for i in $$(seq 30); do v=$$(amk.call 'get K$@ .'); [ \"$$v\" = '\"$@\"' ] || bad=$$((bad + 1)); done; echo \"$@ bad=$$bad\"",
  "",
])

channel = "\n".join([
  "SHELL := bash",
  "three := [1,2,3]",
  "$(jq.ns S, create)",
  "seed := $(S.update $(three))",
  "unread:",
  "\t@printf 'get S length\\n' >&$$AMK_CALL",
  "after: unread",
  "\t@printf 'get S .[0]\\n' >&$$AMK_CALL; read -r st n <&$$AMK_REPLY; IFS= read -r v <&$$AMK_REPLY; echo \"v=$$v\"",
  "dead:",
  "\t@printf '@gone get S .\\n' >&$$AMK_CALL; read -r ack <&$$AMK_REPLY; echo dead-done",
  "",
])

ordering = "\n".join([
  "before := $(lua amk.var.X = \"set\"; print(amk.var.X))",
  "after := $(lua print(amk.var.X))",
  "all:",
  "\t@echo \"before=[$(before)] after=[$(after)]\"",
  "",
])

volume = "\n".join([
  ", := ,",
  "writes := $(lua for i = 1$(,) 3000 do amk.var['V' .. i] = string.rep('x'$(,) 40) end)",
  "all:",
  "\t@echo \"first=[$(V1)] last=[$(V3000)] count=$(words $(filter V1% V2% V3% V4% V5% V6% V7% V8% V9%,$(.VARIABLES)))\"",
  "",
])

census = "\n".join([
  "SHELL := bash",
  "$(jq.ns S, create)",
  "seed := $(S.update [1])",
  "@lua.import.target",
  "define hello",
  "print('hi')",
  "endef",
  "all: one two three",
  "one:",
  "\t@source amk.sh; amk.call 'get S .'",
  "two:",
  "\t@echo $(lua amk.var.X = \"x\")",
  "three:",
  "\t@echo $(goal hello)",
  "",
])

SYSCALL = re.compile(r'\b(mkdirat|mknodat|openat|bind|mkfifo|mknod)\((?:AT_FDCWD, )?"([^"]*)"([^)]*)\)')


def creations(trace, root):
  """Paths under root the trace shows being created: directories, nodes, sockets, and files opened to create."""
  out = set()
  for call, path, rest in SYSCALL.findall(trace):
    if not path.startswith(root + "/"):
      continue
    if call == "openat" and "O_CREAT" not in rest:
      continue
    out.add(path[len(root) + 1:])
  return out


def leftovers(tmp):
  return sorted(p.name for p in tmp.iterdir() if not p.name.startswith(".ape"))


@pytest.mark.engines("jq")
def test_concurrent_callers_never_read_each_others_replies(amk, tmp_path):
  mk = tmp_path / "concurrent.mk"
  mk.write_text(concurrent)
  r = sh(amk, ["-s", "-j4", "-f", str(mk), "all"], timeout=300)
  assert r.returncode == 0, r.stdout + r.stderr
  assert sorted(r.stdout.split("\n")[:-1]) == [f"{n} bad=0" for n in names], r.stdout + r.stderr


@pytest.mark.engines("jq")
def test_a_request_left_unread_dies_with_its_recipe(amk, tmp_path):
  mk = tmp_path / "channel.mk"
  mk.write_text(channel)
  r = sh(amk, ["-s", "-f", str(mk), "after"], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout == "v=1\n", r.stdout + r.stderr


@pytest.mark.engines("jq")
def test_a_caller_that_dies_before_its_reply_costs_nothing(amk, tmp_path):
  mk = tmp_path / "channel.mk"
  mk.write_text(channel)
  tmp = tmp_path / "t"
  tmp.mkdir()
  started = time.monotonic()
  r = sh(amk, ["-s", "-f", str(mk), "dead"], env={"TMPDIR": str(tmp)}, timeout=120)
  elapsed = time.monotonic() - started
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout == "dead-done\n", r.stdout + r.stderr
  assert elapsed < 2, f"make waited {elapsed:.1f}s on a caller that was gone"
  assert leftovers(tmp) == [], leftovers(tmp)


@pytest.mark.engines("lua")
def test_a_forked_guests_write_lands_when_the_call_returns(amk, tmp_path):
  mk = tmp_path / "ordering.mk"
  mk.write_text(ordering)
  r = sh(amk, ["-s", "-f", str(mk), "all"], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout == "before=[nil] after=[set]\n", r.stdout + r.stderr


@pytest.mark.engines("lua")
def test_a_forked_guests_writes_outgrow_a_pipe_buffer(amk, tmp_path):
  mk = tmp_path / "volume.mk"
  mk.write_text(volume)
  r = sh(amk, ["-s", "-f", str(mk), "all"], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout == f"first=[{'x' * 40}] last=[{'x' * 40}] count=3000\n", r.stdout + r.stderr


@pytest.mark.engines("jq", "lua")
def test_a_run_makes_no_name_under_the_temp_dir_but_the_allowed(amk, tmp_path):
  mk = tmp_path / "census.mk"
  mk.write_text(census)
  tmp = tmp_path / "t"
  tmp.mkdir()
  r = sh(amk, ["--strace", "-s", "-j2", "-f", str(mk), "all"], env={"TMPDIR": str(tmp)}, timeout=300)
  assert r.returncode == 0, r.stdout + r.stderr[-2000:]
  made = creations(r.stderr, str(tmp))
  assert made or "SYS" in r.stderr, "the trace shows no syscalls; the flag did not take"
  unexpected = sorted(p for p in made if not any(re.fullmatch(a, p) for a in ALLOWED))
  assert unexpected == [], f"names made under the temp dir: {unexpected}"
  assert leftovers(tmp) == [], leftovers(tmp)

"""Pins how the argv builtins split their option list.

`$(jq.argv opts,program)` and `$(awk.argv opts,program)` build the guest's argv from
one string. The split follows a shell command line, so an option list that works after
`jq` in a recipe means the same thing here: quotes group, a backslash escapes, nothing
expands.
"""

import pytest

from conftest import sh

makefile = "opts = {opts}\nprog = {prog}\n$(info [$(strip $({fn} $(opts),$(prog)))])\nall:\n\ttrue\n"

cases = {
  "unquoted words still split": ("jq.argv", "-n -r --arg a x", "$$a", "x"),
  "single quotes keep a space": ("jq.argv", "-n -r --arg a 'k/a k/b'", "$$a", "k/a k/b"),
  "double quotes keep a space": ("jq.argv", '-n -r --arg a "k/a k/b"', "$$a", "k/a k/b"),
  "an empty quoted value": ("jq.argv", '-n -r --arg a "" --arg b y', '"<" + $$a + ">" + $$b', "<>y"),
  "an escaped quote inside quotes": ("jq.argv", r'-n -r --arg a "say \"hi\""', "$$a", 'say "hi"'),
  "a backslash outside quotes": ("jq.argv", r"-n -r --arg a x\ y", "$$a", "x y"),
  "a backslash kept inside quotes": ("jq.argv", r'-n -r --arg a "a\tb"', "$$a", r"a\tb"),
  "single quotes keep a backslash": ("jq.argv", r"-n -r --arg a 'a\ b'", "$$a", r"a\ b"),
  "quotes joined to a bare word": ("jq.argv", "-n -r --arg a pre'fix ed'", "$$a", "prefix ed"),
  "awk takes a spaced assignment": ("awk.argv", "-v 'msg=hello world'", "BEGIN { print msg }", "hello world"),
}


@pytest.mark.engines("awk", "jq")
@pytest.mark.parametrize("fn,opts,prog,want", cases.values(), ids=cases.keys())
def test_option_list_splits_as_a_shell_would(amk, tmp_path, fn, opts, prog, want):
  mk = tmp_path / "argv.mk"
  mk.write_text(makefile.format(fn=fn, opts=opts, prog=prog))
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert f"[{want}]" in r.stdout, r.stdout + r.stderr

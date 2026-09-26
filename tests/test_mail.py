"""Pins a spawned job's mail.

Every spawned job has a pipe to its parent. A recipe writes it through the descriptor
`AMK_MAIL` names, the job's own Lua through `amk.send`, and the parent reads the whole of
it as `mail` on the wait result. Pinned: both writers reach the parent, the Lua send
first since a recipe expands before its lines run, a silent job mails nothing, and a
job's writers do not see another job's mail.
"""

import pytest

from conftest import sh

program = "\n".join([
  "seed := $(lua.exec)",
  "all:",
  "\t@echo mail=[$(lua.exec local p = amk.spawn({'talker'}) local r = amk.wait(p) print(r.mail))]",
  "talker:",
  "\t@printf 'one ' >&$$AMK_MAIL",
  "\t@true $(lua.exec amk.send('two '))",
  "\t@printf 'three ' >&$$AMK_MAIL",
  "quiet:",
  "\t@echo quiet=[$(lua.exec local p = amk.spawn({'hush'}) print(amk.wait(p).mail))]",
  "hush:",
  "\t@true",
  "pair:",
  "\t@echo pair=[$(lua.exec local a = amk.spawn({'sayer/a'}) local b = amk.spawn({'sayer/b'}) local ra = amk.wait(a) local rb = amk.wait(b) print(ra.mail .. rb.mail))]",
  "sayer/%:",
  "\t@printf '%s' $* >&$$AMK_MAIL",
  "",
])


@pytest.mark.engines("lua")
def test_a_recipe_and_the_job_itself_both_reach_the_parent(amk, tmp_path):
  mk = tmp_path / "mail.mk"
  mk.write_text(program)
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "mail=[two one three ]" in r.stdout, r.stdout + r.stderr


@pytest.mark.engines("lua")
def test_a_silent_job_mails_nothing_and_jobs_do_not_mix(amk, tmp_path):
  mk = tmp_path / "mail.mk"
  mk.write_text(program)
  r = sh(amk, ["-s", "-f", str(mk), "quiet", "pair"], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  assert "quiet=[]" in r.stdout, r.stdout + r.stderr
  assert "pair=[ab]" in r.stdout, r.stdout + r.stderr

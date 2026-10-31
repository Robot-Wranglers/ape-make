"""Pins the payload's flux library under amk alone, with no compose.mk.

Every combinator recurses through flux.reentrant, which is the program's own amk: and and
wrap run in order and stop at a failure, or stops at the first success, negate flips a status,
indent and obliviate rework a target's output, a partial forwards its bound argument, and
retry.sh gives up after its cap. Including the library leaves the includer's default goal alone.
"""

import pytest

from conftest import sh


def run(amk, tmp_path, recipe, goal="all"):
  mk = tmp_path / "flux.mk"
  mk.write_text(
    "$(amk.include flux)\n"
    "$(call __flux.partial__, say, flux.echo, hi)\n"
    f"all:\n\t{recipe}\n"
    "t.fail:\n\tfalse\n"
  )
  return sh(amk, ["-s", "-f", str(mk), *([goal] if goal else [])], timeout=120)


@pytest.mark.parametrize("recipe,out", [
  pytest.param("${flux.reentrant} flux.and/flux.echo/a,flux.echo/b", "a\nb\n", id="and"),
  pytest.param("${flux.reentrant} flux.all/flux.echo/a,flux.echo/b", "a\nb\n", id="all"),
  pytest.param("${flux.reentrant} flux.wrap/flux.echo/a:flux.echo/b", "a\nb\n", id="wrap"),
  pytest.param("${flux.reentrant} flux.or/t.fail,flux.echo/ok,flux.echo/no", "ok\n", id="or"),
  pytest.param("${flux.reentrant} flux.any/t.fail,flux.echo/ok", "ok\n", id="any"),
  pytest.param("${flux.reentrant} flux.indent/flux.echo/x", "  x\n", id="indent"),
  pytest.param("${flux.reentrant} flux.stream.obliviate/flux.echo/x", "", id="obliviate"),
  pytest.param("${flux.reentrant} say/there", "hi,there\n", id="partial"),
  pytest.param("$(call flux.and,flux.echo/m1,flux.echo/m2)", "m1\nm2\n", id="and-macro"),
])
def test_combinator_output(amk, tmp_path, recipe, out):
  r = run(amk, tmp_path, recipe)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout == out, r.stdout


@pytest.mark.parametrize("recipe", [
  pytest.param("${flux.reentrant} flux.and/t.fail,flux.echo/never", id="and"),
  pytest.param("${flux.reentrant} flux.or/t.fail,t.fail", id="or"),
  pytest.param("${flux.reentrant} flux.negate/flux.noop", id="negate"),
  pytest.param("$(call flux.retry.sh,false,2)", id="retry-cap"),
])
def test_combinator_fails(amk, tmp_path, recipe):
  r = run(amk, tmp_path, recipe)
  assert r.returncode != 0, r.stdout
  assert "never" not in r.stdout, r.stdout


def test_negate_of_a_failure_succeeds(amk, tmp_path):
  r = run(amk, tmp_path, "${flux.reentrant} flux.negate/t.fail")
  assert r.returncode == 0, r.stdout + r.stderr


def test_reentrant_is_the_programs_own_amk(amk, tmp_path):
  r = run(amk, tmp_path, "@echo '$(flux.reentrant)'")
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout.strip().endswith(f"-f {tmp_path / 'flux.mk'}"), r.stdout


def goal(amk, tmp_path, target):
  mk = tmp_path / "goal.mk"
  mk.write_text("$(amk.include flux)\nflux.ok:\n\t@true\nflux.fail:\n\t@false\n")
  return sh(amk, ["-s", "-f", str(mk), target], timeout=120)


@pytest.mark.parametrize("target,expected", [
  ("flux.echo/hello", "hello\n"),
  ("flux.echo/a,b,c", "a,b,c\n"),
])
def test_flux_stdout(amk, tmp_path, target, expected):
  r = goal(amk, tmp_path, target)
  assert r.returncode == 0, r.stderr
  assert r.stdout == expected


@pytest.mark.parametrize("target", [
  "flux.noop",
  "flux.negate/flux.fail",
  "flux.and/flux.ok,flux.ok",
  "flux.or/flux.fail,flux.ok",
  "flux.wrap/flux.ok:flux.ok",
  "flux.all/flux.ok,flux.ok",
  "flux.any/flux.fail,flux.ok",
  "flux.stream.obliviate/flux.ok",
  "flux.indent/flux.ok",
])
def test_flux_succeeds(amk, tmp_path, target):
  r = goal(amk, tmp_path, target)
  assert r.returncode == 0, r.stderr


@pytest.mark.parametrize("target", [
  "flux.negate/flux.ok",
  "flux.and/flux.ok,flux.fail",
  "flux.or/flux.fail,flux.fail",
  "flux.wrap/flux.ok:flux.fail",
  "flux.all/flux.ok,flux.fail",
])
def test_flux_fails(amk, tmp_path, target):
  r = goal(amk, tmp_path, target)
  assert r.returncode != 0


def test_flux_retry_sh_gives_up_after_cap(amk, tmp_path):
  # The second argument caps the attempts, and the last failure is the exit status.
  mk = tmp_path / "giveup.mk"
  mk.write_text(
    "$(amk.include flux)\n"
    "probe:\n"
    "\t@$(call flux.retry.sh, echo x >> count ; false, 3) && echo GAVEUP=no || echo GAVEUP=yes; \\\n"
    "\techo TRIES=`wc -l < count`\n"
  )
  r = sh(amk, ["-s", "-C", str(tmp_path), "-f", str(mk), "probe", "interval=0"], timeout=60)
  out = r.stdout + r.stderr
  assert r.returncode == 0, out
  assert "GAVEUP=yes" in out
  assert "TRIES=3" in out.replace(" ", "")


def test_include_keeps_the_default_goal(amk, tmp_path):
  r = run(amk, tmp_path, "@echo main", goal=None)
  assert r.returncode == 0, r.stdout + r.stderr
  assert r.stdout == "main\n", r.stdout

"""Pins `lib/s7/amb.scm`, amb over delimited control for stock s7, loaded by name from the engine's load path.

Pinned are reset answering its body, shift's captured rest of the body as a procedure
called twice, amb visiting every option in search order with fail pruning a branch, the
exhausted thunk running once the options are spent, and nested amb enumerating a product.
"""

import pytest

from conftest import sh

LOAD = '(load "amb.scm" (rootlet))'


def run(amk, tmp_path, form):
  mk = tmp_path / "f.mk"
  mk.write_text(f"x := $(s7.exec {LOAD} (display {form}))\nall:\n\t@echo '$(x)'\n")
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  return r.stdout.strip()


@pytest.mark.engines("s7")
def test_reset_answers_its_body_and_shift_captures_the_rest(amk, tmp_path):
  assert run(amk, tmp_path, "(reset (lambda () (+ 1 2)))") == "3"
  # the rest of the body, 1 + _, applied twice to 1
  assert run(amk, tmp_path, "(reset (lambda () (+ 1 (shift (lambda (k) (k (k 1)))))))") == "3"
  # f's value is the reset's, with the rest of the body never run
  assert run(amk, tmp_path, "(reset (lambda () (+ 1 (shift (lambda (k) 10)))))") == "10"


@pytest.mark.engines("s7")
def test_amb_visits_every_option_and_fail_prunes(amk, tmp_path):
  form = "(amb-collect (lambda () (let ((x (amb '(1 2 3 4)))) (if (even? x) (fail)) (* x 10))))"
  assert run(amk, tmp_path, form) == "(10 30)"


@pytest.mark.engines("s7")
def test_nested_amb_enumerates_in_search_order(amk, tmp_path):
  form = "(amb-collect (lambda () (let* ((x (amb '(1 2))) (y (amb '(a b)))) (list x y))))"
  assert run(amk, tmp_path, form) == "((1 a) (1 b) (2 a) (2 b))"


@pytest.mark.engines("s7")
def test_the_exhausted_thunk_runs_once_the_options_are_spent(amk, tmp_path):
  form = ("(let ((log ())) (amb-collect (lambda () (let ((x (amb '(1 2) (lambda () (set! log (cons 'spent log))))))"
          " (if (= x 2) (set! log (cons 'two log))) x))) (reverse log))")
  assert run(amk, tmp_path, form) == "(two spent)"

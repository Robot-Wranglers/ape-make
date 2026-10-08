"""Pins `lib/plex/init.scm`, the cooperative plex for stock s7, loaded by path.

Pinned are fork queueing tasks in order, yield handing the turn to the next ready task,
run answering done once every task has ended, finish ending the run early with its value,
pending counting the ready list, two plexes keeping separate ready lists, and an
unknown verb raising an error.
"""

import pytest

from conftest import sh

LOAD = '(load "/zip/lib/plex/init.scm" (rootlet))'


def run(amk, tmp_path, form):
  mk = tmp_path / "f.mk"
  mk.write_text(f"x := $(s7.exec {LOAD} (display {form}))\nall:\n\t@echo '$(x)'\n")
  r = sh(amk, ["-s", "-f", str(mk)], timeout=120)
  assert r.returncode == 0, r.stdout + r.stderr
  return r.stdout.strip()


def logged(body):
  """A form whose value is the run's answer and the log its tasks wrote, oldest first."""
  return f"(let* ((r (make-plex)) (log ()) (note (lambda (x) (set! log (cons x log))))) (let ((a {body})) (list a (reverse log))))"


@pytest.mark.engines("s7")
def test_forked_tasks_run_in_order_and_run_answers_done(amk, tmp_path):
  body = "(r 'run (lambda () (r 'fork (lambda () (note 1))) (r 'fork (lambda () (note 2))) (note 0)))"
  assert run(amk, tmp_path, logged(body)) == "(done (0 1 2))"


@pytest.mark.engines("s7")
def test_yield_hands_the_turn_to_the_next_ready_task(amk, tmp_path):
  task = "(lambda () (note '{0}1) (r 'yield) (note '{0}2) (r 'yield) (note '{0}3))"
  body = f"(r 'run (lambda () (r 'fork {task.format('a')}) (r 'fork {task.format('b')})))"
  assert run(amk, tmp_path, logged(body)) == "(done (a1 b1 a2 b2 a3 b3))"


@pytest.mark.engines("s7")
def test_finish_ends_the_run_with_its_value_and_drops_the_rest(amk, tmp_path):
  body = ("(r 'run (lambda () (r 'fork (lambda () (note 1) (r 'finish 'early) (note 2)))"
          " (r 'fork (lambda () (note 3)))))")
  assert run(amk, tmp_path, logged(body)) == "(early (1))"


@pytest.mark.engines("s7")
def test_pending_counts_the_ready_list(amk, tmp_path):
  body = "(r 'run (lambda () (r 'fork (lambda () (note (r 'pending)))) (r 'fork (lambda () #f)) (note (r 'pending))))"
  assert run(amk, tmp_path, logged(body)) == "(done (2 1))"


@pytest.mark.engines("s7")
def test_two_plexes_keep_separate_ready_lists(amk, tmp_path):
  body = ("(let ((q (make-plex))) (r 'run (lambda ()"
          " (r 'fork (lambda () (note 'outer)))"
          " (note (q 'run (lambda () (q 'fork (lambda () (note 'inner))) (q 'yield) (note (r 'pending))))))))")
  assert run(amk, tmp_path, logged(body)) == "(done (inner 1 done outer))"


@pytest.mark.engines("s7")
def test_an_unknown_verb_is_an_error(amk, tmp_path):
  form = "(catch #t (lambda () ((make-plex) 'bogus)) (lambda (type info) type))"
  assert run(amk, tmp_path, form) == "wrong-type-arg"


@pytest.mark.engines("s7")
def test_a_lifo_plex_runs_a_forked_group_first_and_in_its_own_order(amk, tmp_path):
  body = ("(let ((q (make-plex 'lifo))) (q 'run (lambda ()"
          " (q 'fork (lambda () (note 'late)))"
          " (q 'fork-all (list (lambda () (note 1)) (lambda () (note 2))))"
          " (note (q 'order)))))")
  assert run(amk, tmp_path, logged(body)) == "(done (lifo 1 2 late))"


# A search logged to a global: a let-bound log does not keep what a re-entered continuation set.
SEARCH = ('(load "amb.scm" (rootlet)) (define log ()) (define (note x) (set! log (cons x log)))'
          " (define (pairs choose) (let* ((x (choose (quote (1 2))))) (note x)"
          " (let ((y (choose (quote (a b))))) (note (list x y)))))")


def searched(order):
  return (f"(begin {SEARCH} (let ((p (make-plex {order})))"
          " (p 'run (lambda () (reset (lambda () (pairs (lambda (o) (amb-fork p o)))))))) (reverse log))")


@pytest.mark.engines("s7")
def test_amb_fork_on_a_lifo_plex_is_amb_depth_first(amk, tmp_path):
  """The same search through amb and through amb-fork on a stack visits the leaves in one order."""
  want = "(1 (1 a) (1 b) 2 (2 a) (2 b))"
  assert run(amk, tmp_path, f"(begin {SEARCH} (reset (lambda () (pairs amb))) (reverse log))") == want
  assert run(amk, tmp_path, searched("'lifo")) == want


@pytest.mark.engines("s7")
def test_amb_fork_on_a_fifo_plex_is_breadth_first(amk, tmp_path):
  assert run(amk, tmp_path, searched("")) == "(1 2 (1 a) (1 b) (2 a) (2 b))"

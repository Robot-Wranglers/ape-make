;; reactor/init.scm: a cooperative reactor for stock s7: a ready list of continuations, fork queueing a task, yield handing control to the next, and a task's end running what is left. Many reactors may exist; each is a procedure of a verb. No amk in it.

;; One reactor: run seeds it with a thunk and answers once every task has ended, or what finish was handed.
(define (make-reactor)
  (let ((ready ()) (finish #f))
    (define (next!)
      (let ((task (car ready)))
        (set! ready (cdr ready))
        (task #f)))
    (define (done)
      (if (null? ready) (finish 'done) (next!)))
    (define (fork thunk)
      (set! ready (append ready (list (lambda (x) (thunk) (done))))))
    (define (yield)
      (call/cc
        (lambda (k)
          (set! ready (append ready (list k)))
          (done))))
    (define (run thunk)
      (call/cc
        (lambda (stop)
          (set! finish stop)
          (thunk)
          (done))))
    (lambda (verb . args)
      (case verb
        ((fork) (fork (car args)))
        ((yield) (yield))
        ((done) (done))
        ((run) (run (car args)))
        ((finish) (finish (if (pair? args) (car args) 'done)))
        ((pending) (length ready))
        (else (error 'wrong-type-arg "reactor: no verb ~S" verb))))))

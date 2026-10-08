;; s7/amb.scm: amb for stock s7, over delimited control after Filinski: reset and shift from call/cc and one metacontinuation, then amb, fail and amb-collect as depth-first choice. No amk in it; load it anywhere s7 runs.

(define amb-meta (lambda (v) (error 'amb "shift outside reset")))

;; The thunk's value, or what a shift inside it hands the metacontinuation; the outer metacontinuation is back once the thunk is done.
(define (reset thunk)
  (let ((outer amb-meta))
    (call/cc
      (lambda (k)
        (set! amb-meta (lambda (v) (set! amb-meta outer) (k v)))
        (let ((v (thunk)))
          (amb-meta v))))))

;; f over the rest of the body up to the nearest reset, as a procedure that may be called any number of times; f's value is the reset's.
(define (shift f)
  (call/cc
    (lambda (k)
      (let ((v (f (lambda (v) (reset (lambda () (k v)))))))
        (amb-meta v)))))

;; Each option in turn through the rest of the body; when every option is spent, the exhausted thunk if given, then the enclosing reset ends.
(define (amb options . exhausted)
  (shift (lambda (k)
           (for-each k options)
           (if (pair? exhausted) ((car exhausted)) #f))))

;; The current option abandoned: the rest of the body is never run.
(define (fail)
  (shift (lambda (k) #f)))

;; Every value the body reaches, one per branch that neither fails nor runs out, in search order.
(define (amb-collect thunk)
  (let ((found ()))
    (reset (lambda () (set! found (cons (thunk) found))))
    (reverse found)))

;; Each option as a task on a plex: the rest of the body up to the nearest reset, once per option, in the plex's order; the reset answers #f at once and the plex's run drives the branches. On a lifo plex this is amb's own depth-first search; on a fifo plex the branches interleave.
(define (amb-fork plex options)
  (shift (lambda (k)
           (plex 'fork-all (map (lambda (o) (lambda () (k o))) options))
           #f)))

;; jobman/init.scm: amk-jobman for s7, the job functions with s7's own values and no pool, and a pool of jobs over them as a procedure of a verb, a host plex: spawn takes a token of the pool before the fork, wait gives it back on reap and waits only on the pool's own members, kill, stop, resume and foreground signal a job, map runs goal lists under the bound, in order, stopping at the first failure when fail_fast is set, race answers the first of its lists to finish and ends the rest, and close ends every member.

(unless (defined? 'json-read) (load "json.scm" (rootlet)))

(define (amk-jobman--decode t) (and (not (string=? t "")) (json-read t)))
(define (amk-jobman--words xs)
  (let words ((gs xs) (acc ""))
    (if (null? gs) acc
        (let ((w (if (number? (car gs)) (number->string (car gs)) (car gs))))
          (words (cdr gs) (if (string=? acc "") w (string-append acc " " w)))))))

;; A spawn of a kind, through amk.job.spawn kind=what, which knows the kinds and refuses the rest: what as a list or a string, a call's arguments as strings, and :foreground and :stdout as options; answers the pid.
(define (amk-jobman-spawn-kind kind what . opts)
  (let loop ((p opts) (args ()))
    (cond ((null? p)
           (string->number
             (apply amk-call "amk.job.spawn"
                    (string-append (if (symbol? kind) (symbol->string kind) kind) "="
                                   (if (pair? what) (amk-jobman--words what) what))
                    (reverse args))))
          ((string? (car p)) (loop (cdr p) (cons (car p) args)))
          ((not (pair? (cdr p))) (error 'wrong-type-arg "amk-jobman: option ~S has no value" (car p)))
          (else
           (loop (cddr p)
                 (case (car p)
                   ((:foreground) (if (cadr p) (cons "foreground=1" args) args))
                   ((:stdout) (cons (string-append "stdout=" (cadr p)) args))
                   (else (error 'wrong-type-arg "amk-jobman: no option ~S; options are :foreground and :stdout" (car p)))))))))

;; A spawn of a goal list.
(define (amk-jobman-spawn goals . opts) (apply amk-jobman-spawn-kind 'goals goals opts))

;; A wait answering the job's record as a hash table keyed by symbol, or #f when block is #f and none has finished.
(define (amk-jobman-wait . args)
  (amk-jobman--decode
    (cond ((null? args) (amk-call "amk.job.wait"))
          ((and (pair? (cdr args)) (not (cadr args))) (amk-call "amk.job.wait" (or (car args) "") "0"))
          (else (amk-call "amk.job.wait" (car args))))))

;; A job's record without consuming it, or #f while it runs.
(define (amk-jobman-peek pid) (amk-jobman--decode (amk-call "amk.job.peek" pid)))

;; Job control over a job of this process, #t when the signal went.
(define (amk-jobman-kill pid . sig) (string=? (apply amk-call "amk.kill" pid sig) "1"))
(define (amk-jobman-stop pid) (string=? (amk-call "amk.stop" pid) "1"))
(define (amk-jobman-resume pid) (string=? (amk-call "amk.resume" pid) "1"))
(define (amk-jobman-foreground pid) (string=? (amk-call "amk.foreground" pid) "1"))

;; A handle over the named pool; a verb it lacks is an error naming it.
(define (amk-jobman-on pool)
  (let ((held (make-hash-table)))
    ;; A record leaving the pool gives its token back; a stopped job keeps it.
    (define (settle r)
      (when (and r (not (string=? (r 'status) "stopped")) (held (r 'pid)))
        (set! (held (r 'pid)) #f)
        (amk-call "amk.pool.release" pool))
      r)
    (define (among pids . block)
      (and (pair? pids)
           (settle (amk-jobman--decode
                     (amk-call "amk.job.any" (amk-jobman--words pids)
                               (if (and (pair? block) (not (car block))) "0" ""))))))
    (define (pending) (sort! (map car held) <))
    (define (spawn-kind kind what . opts)
      (amk-call "amk.pool.acquire" pool)
      (let ((pid (apply amk-jobman-spawn-kind kind what opts)))
        (set! (held pid) #t)
        pid))
    ;; A verb spawn.<kind> names what is spawned.
    (define (spawn-verb? verb)
      (let ((s (symbol->string verb)))
        (and (> (string-length s) 6) (string=? (substring s 0 6) "spawn."))))
    (define (wait . args)
      (if (or (null? args) (not (car args)))
          (apply among (pending) (if (pair? args) (cdr args) ()))
          (settle (apply amk-jobman-wait args))))
    (define (end pid)
      (amk-jobman-kill pid)
      (amk-jobman-resume pid)
      (settle (amk-jobman-wait pid)))
    (define (map-goals lists . fail-fast)
      (let ((fail-fast (if (pair? fail-fast) (car fail-fast)
                           (equal? (amk-var (string-append "jobman." pool ".fail_fast")) "true")))
            (results (make-vector (length lists) #f))
            (slot (make-hash-table))
            (halted #f))
        (define (collect r)
          (let ((i (and r (slot (r 'pid)))))
            (when i
              (set! (slot (r 'pid)) #f)
              (set! (results i) r)
              (when (and fail-fast (not (string=? (r 'status) "success"))) (set! halted #t)))))
        (define (running) (map car slot))
        (let loop ((ls lists) (i 0))
          (when (and (pair? ls) (not halted))
            (do () ((or halted (not (string=? (amk-call "amk.pool.acquire" pool "0") "")))) (collect (among (running))))
            (unless halted
              (let ((pid (amk-jobman-spawn (car ls))))
                (set! (held pid) #t)
                (set! (slot pid) i))
              (loop (cdr ls) (+ i 1)))))
        (do () ((= (hash-table-entries slot) 0)) (collect (among (running))))
        results))
    ;; The first of the lists to finish; the others are ended and reaped.
    (define (race lists)
      (define (finish mine)
        (let ((winner (among mine)))
          (for-each (lambda (pid) (when (held pid) (end pid))) mine)
          winner))
      (let loop ((ls lists) (mine ()))
        (if (null? ls) (finish mine)
            (let ((got (not (string=? (amk-call "amk.pool.acquire" pool "0") ""))))
              (if (and (not got) (pair? mine)) (finish mine)
                  (begin
                    (unless got (amk-call "amk.pool.acquire" pool))
                    (let ((pid (amk-jobman-spawn (car ls))))
                      (set! (held pid) #t)
                      (loop (cdr ls) (cons pid mine)))))))))
    ;; Every member ended and reaped, its tokens given back; the records in pid order.
    (define (close) (map end (pending)))
    (lambda (verb . args)
      (case verb
        ((name) pool)
        ((pending) (pending))
        ((spawn) (apply spawn-kind 'goals args))
        ((wait) (apply wait args))
        ((peek) (apply amk-jobman-peek args))
        ((kill) (apply amk-jobman-kill args))
        ((stop) (apply amk-jobman-stop args))
        ((resume) (apply amk-jobman-resume args))
        ((foreground) (apply amk-jobman-foreground args))
        ((map) (apply map-goals args))
        ((race) (apply race args))
        ((close) (close))
        (else (if (spawn-verb? verb)
                  (apply spawn-kind (substring (symbol->string verb) 6) args)
                  (error 'wrong-type-arg "amk-jobman: no verb ~S" verb)))))))

(define amk-jobman-__jobs__ (amk-jobman-on "__jobs__"))

;; actor/init.scm: amk-actor for s7, the s7 backend of a group: every member a task on one cooperative plex, a scoped body yielding at its waits, a call or block one ffi call per start, Erlang's restart kinds over a restart budget, and giving up as the group's own exit. No timers; deterministic but for goals, processes whose exits come in the kernel's order.

(unless (defined? 'make-plex)
  (load "/zip/lib/plex/init.scm" (rootlet)))

;; A declared group's data is a jq workspace; a field is read as text, never copied.
(define (amk-actor-field group path)
  (amk-call (string-append group ".get") (string-append "-r " path)))

(define (amk-actor-lines group path)
  (let ((text (amk-actor-field group path)))
    (let loop ((start 0) (acc ()))
      (let ((end (or (char-position #\newline text start) (length text))))
        (if (>= start (length text))
            (reverse acc)
            (loop (+ end 1) (if (= end start) acc (cons (substring text start end) acc))))))))

(define (amk-actor-update group prog)
  (amk-call (string-append group ".update") prog))

;; Bodies bound by at line as scoped members, each a procedure of the group's handle, kept from parse for the run.
(define *amk-actor-scoped* (make-hash-table))

;; One member's view of its group, a procedure of a verb: its id, a field of the data by jq path, its siblings' ids, the mailbox verbs as itself, and yield.
(define (amk-actor-on group id plex)
  (lambda (verb . args)
    (case verb
      ((id) id)
      ((group) group)
      ((field) (amk-actor-field group (car args)))
      ((siblings) (let loop ((ids (amk-actor-lines group ".children | keys[]")) (acc ()))
                    (cond ((null? ids) (reverse acc))
                          ((string=? (car ids) id) (loop (cdr ids) acc))
                          (else (loop (cdr ids) (cons (car ids) acc))))))
      ((cast) (amk-call (string-append group ".cast") (car args) (cadr args)))
      ((recv) (amk-call (string-append group ".recv") id))
      ((ask) (amk-call (string-append group ".ask") id (car args) (cadr args)))
      ((reply) (amk-call (string-append group ".reply") (car args) (cadr args)))
      ((yield) (if plex
                   (plex 'yield)
                   (error 'wrong-type-arg (format #f "actor: ~A is a call member and cannot yield; give it kind=scoped" id))))
      (else (error 'wrong-type-arg "actor: no verb ~S" verb)))))

;; A group's reaper: a job's exit polled without blocking, yielding between polls, and one blocking wait on the group's own jobs once every ready task is a waiter, its record kept for that job's waiter; sweep kills every job still awaited.
(define (amk-actor-reaper plex)
  (let ((exits (make-hash-table)) (live (make-hash-table)) (waiting 0))
    (lambda (pid)
      (if (eq? pid 'sweep)
          (for-each (lambda (kv) (amk-call "amk.kill" (car kv))) live)
          (begin
            (set! waiting (+ waiting 1))
            (set! (live pid) #t)
            (let loop ()
              (let ((r (or (exits pid) (amk-jobman-wait pid #f))))
                (cond ((and r (not (string=? (r 'status) "stopped")))
                       (set! (exits pid) #f)
                       (set! (live pid) #f)
                       (set! waiting (- waiting 1))
                       r)
                      ((= (plex 'pending) (- waiting 1))
                       (let ((any (amk-jobman--decode
                                    (amk-call "amk.job.any" (amk-jobman--words (map car live))))))
                         (when (and any (not (string=? (any 'status) "stopped"))) (set! (exits (any 'pid)) any))
                         (loop)))
                      (else (plex 'yield) (loop))))))))))

;; A member's one start, answered as (code . reason): a goal is a target in its own process, its exit reaped on the plex; a call or block answers through make, a raise or an empty answer being a crash; a scoped body runs on the plex, an error being a crash.
(define (amk-actor-start group id kind engine handle reap)
  (cond ((string=? kind "goal")
         (let* ((r (reap (string->number (amk-call "amk.goal.spawn" id))))
                (code (r 'code)) (sig (r 'signal)))
           (cond ((> sig 0) (cons 1 (format #f "signal ~A" sig)))
                 ((= code 0) (cons 0 ""))
                 (else (cons code (format #f "exit ~A" code))))))
        ((string=? kind "scoped")
         (let ((body (*amk-actor-scoped* (string->symbol id))))
           (if (not body)
               (cons 1 "no scoped body bound")
               (catch #t
                 (lambda () (body handle handle) (cons 0 ""))
                 (lambda (type info)
                   (let ((msg (if (and (pair? info) (string? (car info))) (apply format #f info) (format #f "~A" (cons type info)))))
                     (format #t "~A: ~A~%" id msg)
                     (cons 1 msg)))))))
        ((string=? kind "group")
         (let ((r (amk-actor-run id)))
           (cons (car r) (cdr r))))
        (else
         (let ((answer (catch #t
                         (lambda ()
                           (if (string=? kind "block")
                               (amk-call (string-append engine "*") id)
                               (amk-call id (number->string (string->number (amk-actor-field group (string-append ".children." id ".start_count")))))))
                         (lambda (type info)
                           (cons 'raised (if (and (pair? info) (string? (car info))) (car info) (format #f "~A" (cons type info))))))))
           (cond ((pair? answer)
                  (format #t "~A: ~A~%" id (cdr answer))
                  (cons 1 (cdr answer)))
                 ((string=? answer "")
                  (cons 1 "empty answer"))
                 (else
                  (format #t "~A: ~A~%" id answer)
                  (cons 0 "")))))))

;; A leaf member holds one token of the group's pool while it runs; its start yields to the plex until one is free.
(define (amk-actor-take pool plex)
  (let loop ()
    (when (string=? (amk-call "amk.pool.acquire" pool "0") "")
      (plex 'yield)
      (loop))))

;; One member for its lifetime under its restart kind; past its intensity it gives the group up.
(define (amk-actor-member group id plex events gave-up reap)
  (let* ((entry (string-append ".children." id))
         (kind (amk-actor-field group (string-append entry ".kind")))
         (engine (amk-actor-field group (string-append entry ".engine // \"micropy\"")))
         (restart (amk-actor-field group (string-append entry ".restart // \"always\"")))
         (intensity (string->number (amk-actor-field group (string-append entry ".intensity // .intensity // 3"))))
         (pool (amk-actor-field group ".pool // \"actors\""))
         (pooled (not (string=? kind "group")))
         (handle (amk-actor-on group id plex)))
    (let loop ((start 1) (crashes 0))
      (when pooled (amk-actor-take pool plex))
      (amk-actor-update group (string-append entry ".start_count = " (number->string start)))
      (events "started" id 0 "")
      (let* ((r (amk-actor-start group id kind engine handle reap))
             (code (car r)) (reason (cdr r)) (clean (= code 0)))
        (when pooled (amk-call "amk.pool.release" pool))
        (events "exited" id code reason)
        (cond ((string=? restart "never") #t)
              ((and (string=? restart "on-failure") clean) #t)
              ((> (+ crashes 1) intensity)
               (gave-up (string-append id ": too many restarts")))
              (else
               (events "restarting" id code reason)
               (loop (+ start 1) (+ crashes 1))))))))

;; The events every backend prints: started, exited with its code, restarting, and gave_up with its reason.
(define (amk-actor-events group)
  (lambda (type id code reason)
    (format #t "~A: ~A ~A~A~%" group type id
            (cond ((string=? type "exited") (string-append " " (number->string code)))
                  ((string=? type "gave_up") (string-append ", " reason))
                  (else "")))))

;; A declared group run to its end on a plex of its own: every member a task; answers (code . reason), 0 when every member ended.
(define (amk-actor-run group)
  (let* ((plex (make-plex))
         (events (amk-actor-events group))
         (reap (amk-actor-reaper plex))
         (reason #f)
         (gave-up (lambda (why) (set! reason why) (plex 'finish 'gave-up))))
    (plex 'run
      (lambda ()
        (for-each (lambda (id) (plex 'fork (lambda () (amk-actor-member group id plex events gave-up reap))))
                  (amk-actor-lines group ".children | keys[]"))))
    (if reason
        (begin (reap 'sweep) (events "gave_up" group 1 reason) (cons 1 reason))
        (cons 0 ""))))

;; The define name bound as a member: a scoped body kept for the run, or a call member as a make function over the handle, answering its value or done.
(define (amk-actor-bind group name kind)
  (let ((body (eval-string (string-append "(lambda (" group " __group__) " ((amk-var 'raw) name) "\n)"))))
    (if (string=? kind "scoped")
        (set! (*amk-actor-scoped* (string->symbol name)) body)
        (amk-func (string->symbol name)
                  (lambda args
                    (let* ((h (amk-actor-on group name #f)) (v (body h h)))
                      (if (or (not v) (eq? v #<unspecified>)) "done" (format #f "~A" v))))))
    #t))

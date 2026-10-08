<!-- header # amb "`mod :: lisp :: amb`" |Concepts #concepts | Syntax #syntax | API #api | Search #example-search | Errors #errors | Demos #demos | Refs #references -->
<h1><a id="amb"></a><a href="../README.md#module-index"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-amb.amb.up.dark.svg"><img src="img/hdr/docs-amb.amb.up.svg" alt="up to the module index"></picture></a><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-amb.amb.title.dark.svg"><img src="img/hdr/docs-amb.amb.title.svg" alt="mod :: lisp :: amb"></picture><a href="#references"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-amb.amb.6.dark.svg"><img align=right src="img/hdr/docs-amb.amb.6.svg" alt="Refs"></picture></a><a href="#demos"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-amb.amb.5.dark.svg"><img align=right src="img/hdr/docs-amb.amb.5.svg" alt="Demos"></picture></a><a href="#errors"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-amb.amb.4.dark.svg"><img align=right src="img/hdr/docs-amb.amb.4.svg" alt="Errors"></picture></a><a href="#example-search"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-amb.amb.3.dark.svg"><img align=right src="img/hdr/docs-amb.amb.3.svg" alt="Search"></picture></a><a href="#api"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-amb.amb.2.dark.svg"><img align=right src="img/hdr/docs-amb.amb.2.svg" alt="API"></picture></a><a href="#syntax"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-amb.amb.1.dark.svg"><img align=right src="img/hdr/docs-amb.amb.1.svg" alt="Syntax"></picture></a><a href="#concepts"><picture><source media="(prefers-color-scheme: dark)" srcset="img/hdr/docs-amb.amb.0.dark.svg"><img align=right src="img/hdr/docs-amb.amb.0.svg" alt="Concepts"></picture></a><br clear="all"></h1>
<!-- /header -->

<a id="overview"></a>
McCarthy's `amb` for stock s7, built on delimited control after Filinski[^filinski]: `reset` and
`shift` from `call/cc` and one metacontinuation, then `amb`, `fail` and `amb-collect` over
them. One file, `amb.scm`, with nothing of amk in it.

```Makefile
load amb
```

<a id="loading"></a>

In any s7, by its path:

```scheme
(load "lib/s7/amb.scm")
```

Inside amk, by name, since this folder is on the load path:

```Makefile
seed := $(s7.exec (load "amb.scm"))
```

The folder is [the s7 library](../payload/lib/s7/README.md), and the plex it can fork
choices onto is [the plex module](plex.md#choice).

<a id="concepts"></a>

## Concepts

| Term | Meaning |
| --- | --- |
| Metacontinuation | the one mutable cell `reset` and `shift` are built from, holding where the nearest `reset` returns |
| The Rest of the Body | what `shift` captures: the computation up to the nearest `reset`, as a procedure |
| Option | one value an `amb` tries; the rest of the body runs once per option |
| Branch | the body between its first `amb` and its end |

<a id="syntax"></a>

## Syntax

amb adds no decorator, callform or at line; s7 code calls it as a library.

<a id="api"></a>

## API

amb is s7 only, so its one table set is s7's.

<a id="api-s7"></a>
<a id="delimited-control"></a>

### Delimited control

| Form | Answers |
| --- | --- |
| `(reset thunk)` | the thunk's value, or what a `shift` inside it hands back |
| `(shift f)` | `f` applied to the rest of the body up to the nearest `reset`, as a procedure; `f`'s value becomes the `reset`'s |

The captured rest may be called any number of times, or not at all:

```scheme
(reset (lambda () (+ 1 (shift (lambda (k) (k (k 1)))))))   ; 3
(reset (lambda () (+ 1 (shift (lambda (k) 10)))))          ; 10, the body's + never runs
```

The three forms as a demo, a `reset` alone, the rest called twice, and the rest dropped:

```Makefile
__main__: control

@s7.target
define control
  (load "amb.scm" (rootlet))
  (format #t "reset alone: ~A~%"
    (reset (lambda () (+ 1 2))))
  (format #t "rest called twice: ~A~%"
    (reset (lambda () (+ 1 (shift (lambda (k) (k (k 1))))))))
  (format #t "rest dropped: ~A~%"
    (reset (lambda () (+ 1 (shift (lambda (k) 10))))))
endef
```

<a id="choice"></a>

### Choice

| Form | Does |
| --- | --- |
| `(amb options)` | runs the rest of the body once per option, in order, and answers that option each time |
| `(amb options exhausted)` | the same, then calls `exhausted` once every option is spent |
| `(fail)` | abandons the current option; the rest of the body does not run |
| `(amb-collect thunk)` | every value the thunk reaches, one per branch that neither fails nor runs out, in search order |

```scheme
(amb-collect
  (lambda ()
    (let ((x (amb '(1 2 3 4))))
      (if (even? x) (fail))
      (* x 10))))                       ; (10 30)

(amb-collect
  (lambda ()
    (let* ((x (amb '(1 2))) (y (amb '(a b))))
      (list x y))))                     ; ((1 a) (1 b) (2 a) (2 b))
```

`amb` nests: each inner choice runs its options for every outer one, so the order is
depth first. A branch is the body between its first `amb` and its end, and a value is
collected only when the body returns.

Both choices above as a demo, `fail` pruning the even options, and two nested `amb`s in
search order:

```Makefile
__main__: choice

@s7.target
define choice
  (load "amb.scm" (rootlet))
  (format #t "odd tens: ~A~%"
    (amb-collect
      (lambda ()
        (let ((x (amb '(1 2 3 4))))
          (if (even? x) (fail))
          (* x 10)))))
  (format #t "pairs: ~A~%"
    (amb-collect
      (lambda ()
        (let* ((x (amb '(1 2))) (y (amb '(a b))))
          (list x y)))))
endef
```

<a id="example-search"></a>
<a id="writing-a-search"></a>

## Example (Search)

A search is a body under `amb-collect` that chooses, checks, and returns:

```scheme
(define (pythagorean n)
  (amb-collect
    (lambda ()
      (let* ((range (let loop ((i n) (acc ())) (if (< i 1) acc (loop (- i 1) (cons i acc)))))
             (a (amb range))
             (b (amb range))
             (c (amb range)))
        (if (or (> a b) (not (= (+ (* a a) (* b b)) (* c c)))) (fail))
        (list a b c)))))

(pythagorean 10)                        ; ((3 4 5) (6 8 10))
```

The `exhausted` thunk is where a search undoes what a choice point set up, since it runs
after the last option's branch and before the enclosing choice moves on.

The same search as a demo, every right triangle with sides up to 20, from three choices and
one check:

```Makefile
__main__: search

@s7.target
define search
  (load "amb.scm" (rootlet))
  (define (upto n)
    (let loop ((i n) (acc ()))
      (if (< i 1) acc (loop (- i 1) (cons i acc)))))
  (define (triples n)
    (amb-collect
      (lambda ()
        (let* ((a (amb (upto n))) (b (amb (upto n))) (c (amb (upto n))))
          (if (or (> a b) (not (= (+ (* a a) (* b b)) (* c c)))) (fail))
          (list a b c)))))
  (format #t "triples: ~A~%" (triples 20))
endef
```

<a id="errors"></a>

## Errors

| Condition | Message |
| --- | --- |
| A`shift` with no enclosing `reset` | `shift outside reset` |

<a id="demos"></a>

## Demos

Each runs from the repository with `amk -f`, or any one target by name.

| Demo | Targets | Shows |
| --- | --- | --- |
| [`stdlib-amb-control.amk`](../demos/stdlib-amb-control.amk), embedded under [delimited control](#delimited-control) | `control` | the three `reset` and `shift` forms above |
| [`stdlib-amb-choice.amk`](../demos/stdlib-amb-choice.amk), embedded under [choice](#choice) | `choice` | `amb` with `fail`, and nested `amb` in search order |
| [`stdlib-amb-search.amk`](../demos/stdlib-amb-search.amk), embedded under [the search](#example-search) | `search` | every right triangle with sides up to 20 |
| [`stdlib-amb-yinyang.amk`](../demos/stdlib-amb-yinyang.amk), embedded below | `yinyang` | the yin-yang puzzle, `@*@**@***` and on, stopped by a counter after 20 characters |
| [`stdlib-amb-2.amk`](../demos/stdlib-amb-2.amk) | `tasks` | cooperative multitasking: a ready list of continuations, `fork`, `yield`, three counters interleaving |
| | `branches` | the same scheduler with `shift` as the forker, the rest of the body queued once per option |

```
$ amk -f demos/stdlib-amb-yinyang.amk
yin-yang: @*@**@***@****@*****
$ amk -f demos/stdlib-amb-2.amk branches
one starts
two starts
three starts
one ends
two ends
three ends
```

The yin-yang puzzle and the scheduler are adapted from the examples in
Call-with-current-continuation[^callcc] on Wikipedia. Two things differ from the page. The page's overridden `exit` is a
`finish` continuation, so the s7 process stays the engine's. And a task's end stays
non-returning, as the page's `exit` is: a scheduler whose tasks return into its loop
replays that loop's frame through every continuation it captured.

The yin-yang puzzle, in which `yin` and `yang` each hold their own binding's continuation
and a counter escapes after 20 characters, adapted from the
[call/cc examples](https://en.wikipedia.org/wiki/Call-with-current-continuation#Examples) on Wikipedia:

```Makefile
__main__: yinyang

@s7.target
define yinyang
  (define out (open-output-string))
  (define budget 20)
  (define escape #f)
  (define (mark c)
    (write-char c out)
    (set! budget (- budget 1))
    (if (= budget 0) (escape (get-output-string out))))
  (format #t "yin-yang: ~A~%"
    (call/cc
      (lambda (stop)
        (set! escape stop)
        (let* ((yin ((lambda (cc) (mark #\@) cc) (call/cc (lambda (c) c))))
               (yang ((lambda (cc) (mark #\*) cc) (call/cc (lambda (c) c)))))
          (yin yang)))))
endef
```

<a id="references"></a>

## References

- [Plex](plex.md#choice), where `amb-fork` runs choice as tasks on a plex.
- [The runtime](runtime.md#control-multiplexer), the control layers `amb` sits on.
- [Nondeterministic programming](https://en.wikipedia.org/wiki/Nondeterministic_programming) and [delimited continuations](https://en.wikipedia.org/wiki/Delimited_continuation), on Wikipedia.
- Olivier Danvy and Andrzej Filinski, "Abstracting Control", LISP and Functional Programming, 1990: the paper that introduced `shift` and `reset`.
- Racket reference, [10.4.1 Additional Control Operators](https://docs.racket-lang.org/reference/cont.html#%28part._.Additional_.Control_.Operators%29): `shift` and `reset` as a library on Racket's prompts, with the same meaning as here; the parent section covers composable continuations and prompts.
- Oleg Kiselyov, [Continuations and Delimited Control](https://okmij.org/ftp/continuations/): tutorials and papers, beginning with [an introduction to programming with shift and reset](https://okmij.org/ftp/continuations/#tutorial), and a section on [search with delimited control](https://okmij.org/ftp/continuations/#reify-search) that is the shape of `amb-collect`.

[^filinski]: Andrzej Filinski, "Representing Monads", POPL 1994: `shift` and `reset` from `call/cc` and one mutable cell, which is this file's construction.
[^callcc]: Wikipedia, [Call-with-current-continuation, Examples](https://en.wikipedia.org/wiki/Call-with-current-continuation#Examples).

# via/amk/demos/define-1.mk: one target per engine, each written in its own language with define.<engine>, and make as the coordinator.
SHELL := bash
.SHELLFLAGS ?= -euo pipefail -c
MAKEFLAGS = -s -S --warn-undefined-variables
.DEFAULT_GOAL := all
self := $(lastword $(MAKEFILE_LIST))

# Stock make's feature list carries no engine word, so this demo stops before it reaches one.
ifneq ($(filter-out $(.FEATURES),lua s7 micropy js),)
  $(error $(self) needs amk with lua s7 micropy js -- run it as ./amk -f $(self), not under stock make)
endif

# Each define is a target of the same name; the body is the program, and what it prints is what the target prints.
define.lua fact
local n = 1
for i = 2, 20 do n = n * i end
print(n)
endef

define.s7 fib
(define (fib n) (if (< n 2) n (+ (fib (- n 1)) (fib (- n 2)))))
(display (fib 25))
endef

define.micropy primes
print(*[n for n in range(2, 50) if all(n % d for d in range(2, n))])
endef

define.js squares
print([1, 2, 3, 4, 5].map(x => x * x).join(" "))
endef

all: fact fib primes squares check

# The define is still a variable, so the same body can be handed to the engine directly, and a target's output is a sub-make away.
check:
	test "$(lua ${fact})" = "2432902008176640000"
	test "$$($(MAKE) -f $(self) fib)" = "75025"
	test "$$($(MAKE) -f $(self) primes | wc -w | tr -d ' ')" = "15"
	echo "define-1: every engine answered"

#!/usr/bin/env -S amk -f

# via/amk/demos/define-1.mk: one target per engine, each written in its own language under an import-target at line, and make as the coordinator.

$(amk.require lua s7 micropy js)

# Each define is a target of the same name; the body is the program, and what it prints is what the target prints.
@lua.import.target
define fact
  local n = 1
  for i = 2, 20 do n = n * i end
  print(n)
endef

@s7.import.target
define fib
  (define (fib n) (if (< n 2) n (+ (fib (- n 1)) (fib (- n 2)))))
  (display (fib 25))
endef

@micropy.import.target
define primes
  print(*[n for n in range(2, 50) if all(n % d for d in range(2, n))])
endef

@js.import.target
define squares
  print([1, 2, 3, 4, 5].map(x => x * x).join(" "))
endef

__main__: fact fib primes squares check

# The define is still a variable, so the same body can be handed to the engine directly, and a target's output is a sub-make away.
check:
	test "$(lua* fact)" = "2432902008176640000"
	test "$$(${amk} fib)" = "75025"
	test "$$(${amk} primes | wc -w | tr -d ' ')" = "15"
	echo "define-1: every engine answered"

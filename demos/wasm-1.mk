#!/usr/bin/env -S amk -f

# via/amk/demos/wasm-1.mk: a zig function compiled to wasm in a container, held in a make variable, and called from wasm3 without touching disk.
$(if $(filter wasm,$(.ENGINES)),,$(error $(__file__) needs a build with wasm3: make build with=wasm3))

define Dockerfile
FROM alpine:3.21
RUN apk add -q zig
endef

define fib.zig
export fn fib(n: u32) u32 {
    var a: u32 = 0;
    var b: u32 = 1;
    var i: u32 = 0;
    while (i < n) : (i += 1) {
        const t = a + b;
        a = b;
        b = t;
    }
    return a;
}
endef

define zig.build
cat > fib.zig && zig build-exe fib.zig -target wasm32-freestanding -O ReleaseSmall -fno-entry --export=fib && cat fib.wasm
endef

# A define streams out of a sub-make untouched: no quoting, no dollar escapes.
def.%:
	$(info $(value $*))

# One wasm3 session: the module loads from the variable as hex, then the function runs once per line, and the blank line ends the last one.
define session
:load-hex $(words $(wasm.hex))
$(wasm.hex)
fib 10
fib 20
fib 30

endef

# The image is built from its define, the module compiled from its define, and the session run, each once, at parse time, unless this run only streams a define.
ifeq ($(filter def.%,$(MAKECMDGOALS)),)
image := $(shell ${amk} def.Dockerfile | docker build -q -)
$(if $(filter-out 0,$(.SHELLSTATUS)),$(error docker build failed))
wasm.hex := $(shell ${amk} def.fib.zig | docker run -i --rm -w /tmp $(image) sh -c '$(zig.build)' | od -An -v -tx1)
$(if $(filter-out 0,$(.SHELLSTATUS)),$(error zig build failed))
results := $(patsubst Result:%,%,$(subst Result: ,Result:,$(wasm.argv --repl,,$(session))))
endif

__main__:
	echo "module: $(words $(wasm.hex)) bytes of wasm from $(words $(fib.zig)) words of zig"
	echo "fib 10 20 30: $(results)"
	test "$(lastword $(results))" = 832040

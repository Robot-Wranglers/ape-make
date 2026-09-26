# The program smoke bundles: the entry comes from the payload, and so does its include.
include lib/greet.mk
include lib/sub/deep.mk

entry:
	test "$(__file__)" = /zip/__main__.mk
	test "$(greeting)" = hello
	test "$(depth)" = 2
	echo "bundle: $(greeting) from $(__file__)"

recurse:
	$(MAKE) entry

served:
	echo "served by pid $$$$, level $(MAKELEVEL)"

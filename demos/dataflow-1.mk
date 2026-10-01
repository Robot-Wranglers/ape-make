#!/usr/bin/env -S amk -f

#
# via/amk/demos/dataflow-1.mk: 
#  5 imported targets in 5 langs, using incremental computing, 
#  dataflow style.  pipeline is *implicit* here: change
#  an input and only what depends on it reruns.
#  
goal.dir := build/dataflow-1

# A target that fails leaves no value behind, so the next run builds it again.
.DELETE_ON_ERROR:

$(amk.require awk, lua, s7, micropy, js)

# The input is a file under the value directory, written by the run below; an empty rule names it as a target a reference can resolve.
$(goal.dir)/numbers.txt: ;

# Each imported target names the values it reads, and that is its dependency list: a diamond, so two of these run at once under -j.
@awk.import.target
define sorted
  BEGIN { n = split("@numbers.txt@", a, " "); asort(a); for (i = 1; i <= n; i++) printf "%s%s", a[i], (i < n ? " " : "\n") }
endef

@lua.import.target
define json
  print("[" .. ("@sorted@"):gsub(" ", ",") .. "]")
endef

@s7.import.target
define stats
  (let ((xs (list @sorted@))) (format #t "~A numbers, sum ~A" (length xs) (apply + xs)))
endef

@micropy.import.target
define median
  import json
  xs = json.loads('@json@')
  print(xs[len(xs) // 2])
endef

@js.import.target
define report
  print("@stats@" + ", median @median@");
endef

__main__:
	$(file >$(goal.dir)/numbers.txt,3 1 4 1 5 9 2 6)
	${amk} report
	${amk} check expect="8 numbers, sum 31, median 4"
	@# A new input: only the targets downstream of it rerun, and the report follows.
	sleep 1.1 && echo "10 20 30" > $(goal.dir)/numbers.txt
	${amk} report
	${amk} check expect="3 numbers, sum 60, median 20"
	echo "five languages, one dataflow, incremental"

# A recipe is expanded whole before it runs, so a value read after a change belongs in its own target.
expect ?=
check:
	test "$(goal report)" = "$(expect)"

#
# payload/lib/dsys/workflow.jq:
#  a task graph compiled to a net that dsys/petri runs, by the rules of
#  scratch/workflow-compile.md. Definitions only; compile is the entry.
#

def refuse($who; $why): error("\($who): \($why)");

# Generated names: a task name holds no dot, so none of these meets one.
def ready($t): "\($t).ready";
def edge($from; $to): "\($from).to.\($to)";
def sink($t): "\($t).end";
def items($t): "\($t).items";
def results($t): "\($t).results";

def whens: {
  success: ["all success", "not all success"],
  failed: ["any failed", "not any failed"],
  done: [null, null]
};

# A need naming no task, which the schema cannot see; the shape is the workflow schema's.
def problems($k; $v; $names):
  ($v.needs // [])[] | select(IN($names[]) | not) | "needs \(.), which is no task";

def validate:
  (.tasks | keys_unsorted) as $names
  | first((.tasks | to_entries[] | .key as $k
      | problems($k; .value; $names) | refuse($k; .)), .);

# The tasks in an order that puts every need first, stable by declaration.
def topo:
  .tasks as $t
  | {order: [], left: ($t | keys_unsorted)}
  | until(.left == [];
      .order as $o
      | [.left[] | select(. as $k | $t[$k].needs | all(IN($o[])))] as $ready
      | if $ready == [] then refuse(.left[0]; "is on a cycle in needs")
        else .order += $ready | .left -= $ready end)
  | .order;

def normalize:
  .tasks |= with_entries(.value = {needs: [], when: "success"} + .value)
  | .order = topo;

# A task's neighbours, and the places it reads and writes.
def dependents($k): [.order[] as $d | select(.tasks[$d].needs | any(. == $k)) | $d];
def inputs($k):
  .tasks[$k].needs as $n
  | if $n == [] then [ready($k)] else [$n[] | edge(.; $k)] end;
def outputs($k):
  dependents($k) as $d
  | if $d == [] then [sink($k)] else [$d[] | edge($k; .)] end;

# Arcs from many places into one transition, and from one transition out.
def arcs_in($from; $t): [$from[] | [., $t]];
def arcs_out($t; $to): [$to[] | [$t, .]];
def guarded($t; $g): if $g then {($t): $g} else {} end;

# A net is the sum of its fragments: objects merge, lists append.
def plus($f):
  .places += ($f.places // {})
  | .transitions += ($f.transitions // [])
  | .arcs += ($f.arcs // [])
  | .amk *= ($f.amk // {});
def merge: reduce .[] as $f ({places: {}, transitions: [], arcs: [], amk: {}}; plus($f));

# The fragments of one task: its run, its skip, its step and its pool.
def plain($k; $in; $out; $go): {
  transitions: [$k],
  arcs: (arcs_in($in; $k) + arcs_out($k; $out)),
  amk: {label: {($k): "outcome"}, guard: guarded($k; $go)}
};
def over($k; $v; $in; $out; $go):
  "\($k).split" as $split | "\($k).join" as $join | ($v.over | length) as $n
  | {
      places: {(items($k)): [], (results($k)): []},
      transitions: [$split, $k, $join],
      arcs: (arcs_in($in; $split)
        + [[$split, items($k), $n], [items($k), $k],
           [$k, results($k)], [results($k), $join, $n]]
        + arcs_out($join; $out)),
      amk: {
        label: {($split): {items: $v.over}, ($k): "outcome", ($join): "merge"},
        guard: guarded($split; $go)
      }
    };
def skip($k; $in; $out; $no):
  "\($k).skip" as $s
  | {
      transitions: [$s],
      arcs: (arcs_in($in; $s) + arcs_out($s; $out)),
      amk: {label: {($s): "skipped"}, guard: {($s): $no}}
    };
def step($k; $v):
  if $v.run then {amk: {steps: {($k): {run: $v.run, kind: "goal.maybe"}}}} else {} end;
def pooled($k; $v):
  if $v.pool then {
    arcs: [[$v.pool, $k], [$k, $v.pool]],
    amk: {pools: {($v.pool): $v.pool}}
  } else {} end;

def fragment($k):
  .tasks[$k] as $v | inputs($k) as $in | outputs($k) as $out
  | whens[$v.when] as [$go, $no]
  | [
      {places: ((if $v.needs == [] then {(ready($k)): ["success"]} else {} end)
        + ($out | map({(.): []}) | add))},
      (if $v | has("over") then over($k; $v; $in; $out; $go)
       else plain($k; $in; $out; $go) end),
      (if $no then skip($k; $in; $out; $no) else empty end),
      step($k; $v),
      pooled($k; $v)
    ]
  | merge;

# Every task that nothing needs ends holding one token; nothing else holds any.
def finish($wf):
  .amk.backend = "petri"
  | .amk.final = ([$wf.order[] as $k
      | select($wf | dependents($k) == []) | {(sink($k)): 1}] | add // {});

def compile:
  validate | normalize | . as $wf
  | [{places: {}, transitions: [], arcs: []}, (.order[] as $k | $wf | fragment($k))]
  | merge | finish($wf);

#
# payload/lib/dsys/kahn.jq:
#  a Kahn network compiled to an open net that dsys/petri runs: a channel a
#  place, a process a transition reading one token from each channel it
#  reads, its writes left to its step. Definitions only; kahn is the entry.
#

def refuse($who; $why): error("\($who): \($why)");

# What the schema cannot see; a channel end shared by two would lose determinism.
def problems:
  (.channels | keys_unsorted) as $ch
  | (.processes | to_entries[] | .key as $p | .value as $v
      | (($v.reads + ($v.writes // []))[] | select(IN($ch[]) | not)
         | [$p, "names \(.), which is no channel"])),
    ($ch[] as $c
      | ([.processes[] | select(.reads | index([$c]))] | length) as $r
      | ([.processes[] | select(.writes // [] | index([$c]))] | length) as $w
      | if $r > 1 then [$c, "has \($r) readers, not 1"]
        elif $w > 1 then [$c, "has \($w) writers, not 1"]
        else empty end);

# The net, a final marking only when declared, since a loop ends holding tokens.
def net: {
  places: .channels,
  transitions: (.processes | keys_unsorted),
  arcs: [.processes | to_entries[] | .key as $p | .value.reads[] | [., $p]],
  amk: ({
    backend: "petri",
    strategy: "open",
    steps: (.processes | map_values({run: .run}))
  } + (if has("final") then {final: .final} else {} end))
};

def kahn: .processes //= {} | first((problems | refuse(.[0]; .[1])), .) | net;

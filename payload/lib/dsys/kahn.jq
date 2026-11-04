#
# payload/lib/dsys/kahn.jq:
#  a Kahn network compiled to an open net that dsys/petri runs: a channel a
#  place, a process a transition reading one token from each channel it
#  reads, its writes left to its step. Processes run as jobs, concurrently,
#  each holding its <p>.idle token while in flight so it fires one at a
#  time and its channels stay in order. Definitions only; kahn is the entry.
#

def refuse($who; $why): error("\($who): \($why)");

# A process's control place, one token while it is not in flight.
def idle($p): "\($p).idle";

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
        else empty end),
    (.processes | keys_unsorted[] | idle(.) as $i | select($i | IN($ch[]))
      | [$i, "is a channel and the control place of process \(.)"]);

# The net, a final marking only when declared, since a loop ends holding tokens.
def net:
  (.processes | keys_unsorted) as $ps
  | ($ps | map({(idle(.)): 1}) | add // {}) as $idle
  | {
      places: (.channels + $idle),
      transitions: $ps,
      arcs: ([.processes | to_entries[] | .key as $p | .value.reads[] | [., $p]]
        + [$ps[] | [idle(.), .], [., idle(.)]]),
      amk: ({
        backend: "petri",
        strategy: "open",
        steps: (.processes | map_values({run: .run, kind: "agoal"}))
      } + (if has("final") then {final: (.final + $idle)} else {} end))
    };

def kahn: .processes //= {} | first((problems | refuse(.[0]; .[1])), .) | net;

#
# payload/lib/dsys/petri.jq:
#  a net's JSON read once: checked, planned, and written as make
#  assignments the runtime in petri.amk fires from. Definitions only;
#  load is the entry, pnml the export.
#

def refuse($net; $why): error("\($net): \($why)");

def backends: ["petri"];
def kinds: ["goal", "goal.maybe", "agoal", "agoal.maybe"];
def async: ["agoal", "agoal.maybe"];
def guards: ["all_success", "not_all_success", "any_failed", "not_any_failed"];
def label_rules: ["outcome", "skipped", "merge", "items", "output"];

# The net normalized: per transition its arcs as place:weight, step, guard and label rule.
def plan:
  (.amk // {}) as $a | .arcs as $arcs
  | [.places | to_entries[] | select(.value | type == "array") | .key] as $labeled
  | {
      places: (.places | keys_unsorted),
      labeled: $labeled,
      guarded: ([.transitions[] as $t | select(($a.guard[$t] // "") != "")
        | $arcs[] | select(.[1] == $t) | .[0] | select(IN($labeled[]))] | unique),
      init: (.places | map_values(if type == "array" then join(" ") else tostring end)),
      pools: [($a.pools // {}) | to_entries[] | "\(.key):\(.value)"],
      strategy: ($a.strategy // "default"),
      open: ($a.open // []),
      busy: [.transitions[] as $t | select(($a.steps[$t].kind // "goal") | IN(async[])) | "\($t).busy"],
      transitions: .transitions,
      t: ([.transitions[] as $t | {key: $t, value: {
        in: [$arcs[] | select(.[1] == $t) | "\(.[0]):\(.[2] // 1)"],
        out: [$arcs[] | select(.[0] == $t) | "\(.[1]):\(.[2] // 1)"],
        run: ($a.steps[$t].run // "" | if type == "array" then join(" ") else . end),
        bind: [($a.steps[$t].bind // {}) | to_entries[] | "\(.key)=\(.value)"],
        kind: ($a.steps[$t].kind // "goal"),
        guard: ($a.guard[$t] // ""
          | if type == "object" then "label:\(.label)" else gsub(" "; "_") end),
        label: ($a.label[$t] // "" | if type == "object" then "items" else . end),
        items: ($a.label[$t].items? // [])
      }}] | from_entries),
      invariants: [($a.invariants // [])[]
        | {terms: [to_entries[] | select(.key != "=") | "\(.key):\(.value)"], eq: .["="]}],
      final: (if $a | has("final")
        then [$a.final | if type == "array" then .[] else . end
              | [to_entries[] | "\(.key):\(.value)"] | join(",")]
        else "-" end)
    };

# What is wrong with the net, as messages in the order they are checked.
def problems:
  (.amk // {}) as $a | plan as $p
  | (($a.pools // {}) | keys) as $pools
  | ($p.places + $pools) as $ends
  | (($a.backend // "petri") | select(IN(backends[]) | not)
      | "backend \(.); petri runs \(backends | join(" "))"),
    ((($a.steps // {}) | keys) - $p.transitions | .[] | "step \(.) names no transition"),
    ($pools[] | select(IN($p.places[])) | "\(.) is both a place and an existing pool"),
    ($p.open[] | select(IN($p.places[]) | not) | "open place \(.) is not a place of the net"),
    ($p.busy[] | select(IN($p.places[])) | "\(.) is both a place and the in-flight count of a transition"),
    ($p.transitions[] | select(IN($ends[])) | "\(.) is both a place and a transition"),
    (.arcs[] | select(
        ((.[0] | IN($ends[])) and (.[1] | IN($p.transitions[])))
        or ((.[0] | IN($p.transitions[])) and (.[1] | IN($ends[]))) | not)
      | "arc \(.[0]) to \(.[1]) does not join a place and a transition"),
    ($p.transitions[] as $t | $p.t[$t]
      | (.label | select(. != "" and (IN(label_rules[]) | not))
          | "transition \($t) has label rule \(.); petri knows \(label_rules | join(" "))"),
        (.guard | select(. != "" and (IN(guards[]) | not) and (startswith("label:") | not))
          | "transition \($t) has guard \(.); petri knows \(guards | join(" ")) and a label"),
        (.kind | select(IN(kinds[]) | not)
          | "step \($t) is of kind \(.); petri runs \(kinds | join(" "))"),
        (select(.in == [])
          | "transition \($t) has no input place, so it would fire forever")),
    (($p.places + $p.transitions)[] | select(test("^[A-Za-z0-9_.-]+$") | not)
      | "name \(tojson) is not letters, digits and _ . -"),
    ($p.labeled[] as $l | $p.init[$l] | split(" ")[] | select(test("[$#\\\\]"))
      | "label \(.) holds $, # or a backslash, which petri cannot carry");

# The net as pnml, with what only amk reads left out.
def pnml($net):
  "<pnml><net id=\"\($net)\" type=\"http://www.pnml.org/version-2009/grammar/ptnet\">"
  + "<page id=\"\($net)\">"
  + (.places | to_entries | map("<place id=\"\(.key)\"><initialMarking><text>\(
      if (.value | type) == "array" then (.value | length) else .value end
    )</text></initialMarking></place>") | join(""))
  + (.transitions | map("<transition id=\"\(.)\"/>") | join(""))
  + (.arcs | to_entries | map("<arc id=\"a\(.key)\" source=\"\(.value[0])\""
      + " target=\"\(.value[1])\"><inscription><text>\(.value[2] // 1)"
      + "</text></inscription></arc>") | join(""))
  + "</page></net></pnml>";

# One make assignment, a list joined by spaces.
def assign($var; $value):
  "\($var) := \($value | if type == "array" then join(" ") else tostring end)";

# The plan as make assignments under the net's name, every transition pending.
def make($n):
  plan as $p
  | assign("\($n).places"; $p.places),
    assign("\($n).labeled"; $p.labeled),
    assign("\($n).guarded"; $p.guarded),
    assign("\($n).transitions"; $p.transitions),
    assign("\($n).pools"; $p.pools),
    assign("\($n).strategy"; $p.strategy),
    assign("\($n).open"; $p.open),
    assign("\($n).busy"; $p.busy),
    ($p.init | to_entries[] | assign("\($n).init.\(.key)"; .value)),
    ($p.t | to_entries[] | .key as $t
      | .value | to_entries[] | assign("\($n).\($t).\(.key)"; .value)),
    assign("\($n).invariants"; $p.invariants | length),
    ($p.invariants | to_entries[]
      | assign("\($n).inv.\(.key + 1)"; .value.terms),
        assign("\($n).inv.\(.key + 1).eq"; .value.eq)),
    assign("\($n).final"; $p.final),
    assign("\($n).trace"; ""),
    assign("\($n).inflight"; ""),
    ($p.transitions[] | assign("\($n).\(.).state"; "pending")),
    assign("\($n).pnml"; pnml($n));

def load($n): first((problems | refuse($n; .)), .) | make($n);

# The plan again for a definition that changed, the run's own variables left as they are.
def replan($n):
  make($n) | select(test("\\.(trace|inflight) := |\\.state := pending$") | not);
def grow($n): first((problems | refuse($n; .)), .) | replan($n);

# A guard over the labels its transition reads: a rule over outcomes, or the label itself.
def guard($rule; $labels):
  if $rule | startswith("label:") then ($rule[6:]) as $want | all($labels[]; . == $want)
  elif $rule == "all_success" then all($labels[]; . == "success")
  elif $rule == "not_all_success" then any($labels[]; . != "success")
  elif $rule == "any_failed" then any($labels[]; . == "failed")
  elif $rule == "not_any_failed" then all($labels[]; . != "failed")
  else true end;

# A transition's arcs read apart, and whether a marking holds every input arc's weight.
def arcs: map(split(":") | {place: .[0], weight: (.[1] | tonumber)});
def held($marking): all(.in | arcs[]; $marking[.place] >= .weight);

# The labels a guard reads: each labeled input place, one token each in the snapshot.
def reads($net; $t; $labeled; $marking; $labels):
  [.in | arcs[] | .place | select(IN($labeled[])) | . as $place
    | if $labels | has($place) then $labels[$place][]
      else refuse($net; "the guard of \($t) reads \($place), which holds \($marking[$place]) tokens, not 1") end];

# The first enabled transition under a marking, in transitions order, or none.
def first_enabled($net; $p; $marking; $labels):
  first($p.transitions[] as $t | $p.t[$t]
      | select(held($marking))
      | select(.guard == "" or guard(.guard; reads($net; $t; $p.labeled; $marking; $labels)))
      | $t) // empty;
def enabled($net; $marking; $labels): plan as $p | first_enabled($net; $p; $marking; $labels);

# The final markings as wants per place, one object each, or null when the net declares none.
def wants($p):
  if $p.final == "-" then null
  else [$p.final[] | [split(",")[] | split(":") | {key: .[0], value: (.[1] | tonumber)}] | from_entries] end;
def meets($p; $marking; $w): all($p.places[]; $marking[.] == ($w[.] // 0));
def met($p; $marking):
  wants($p) as $ws | $ws != null and any($ws[]; meets($p; $marking; .));

# The loop's one question: the transition to fire or -, and met or -, after the firing cap.
def next($net; $marking; $labels; $trace; $max):
  plan as $p
  | if ($trace | length) >= $max then refuse($net; "\($max) firings and still enabled") else . end
  | "\(first_enabled($net; $p; $marking; $labels) // "-") \(if met($p; $marking) then "met" else "-" end)";

# A firing's label by the transition's rule: the n-th of its items, or one for every token.
def token_label($net; $t; $d; $f; $n):
  if $d.label == "outcome" then (if $f.outcome == "" then "success" else $f.outcome end)
  elif $d.label == "skipped" then "skipped"
  elif $d.label == "merge" then
    (if "failed" | IN($f.taken[]) then "failed" elif "skipped" | IN($f.taken[]) then "skipped" else "success" end)
  elif $d.label == "items" then
    ($d.items[$n - 1] // refuse($net; "\($t) produces token \($n) but has \($d.items | length) items"))
  elif $d.label == "output" then
    (if $f.output == "" then refuse($net; "\($t) labels by its output, and its step printed none") else $f.output end)
  else $f.token end;

# A firing's second half as assignments: what each output arc gives, and the transition's state.
def fire($net; $f):
  plan as $p | $f.t as $t | $p.t[$t] as $d
  | assign("\($net).\($t).gives"; [$d.out | arcs[] | .place as $place | (range(.weight) + 1) as $n
      | if $place | IN($p.labeled[]) then
          (token_label($net; $t; $d; $f; $n)
            | if . == "" then refuse($net; "\($t) puts a token in labeled place \($place) but took no label")
              else "\($place):\(.)" end)
        else "\($place):1" end]),
    assign("\($net).\($t).state";
      if $d.label | IN("outcome", "skipped", "merge") then token_label($net; $t; $d; $f; 1)
      else "fired" end);

# Every invariant holds under the marking, or the run stops naming the first broken.
def invariants($net; $t; $marking):
  plan as $p
  | $p.invariants | to_entries[] | .key + 1 as $i | .value
  | ([.terms[] | split(":") | $marking[.[0]] * (.[1] | tonumber)] | add // 0) as $total
  | select($total != .eq)
  | refuse($net; "invariant \($i) broken after \($t): \($total), not \(.eq)");

# The run's end: a place off every final marking stops it, a net declaring none never does.
def stuck($net; $marking):
  plan as $p | wants($p) as $ws
  | select($ws != null and (met($p; $marking) | not))
  | if ($ws | length) == 1 then
      first($p.places[] | select($marking[.] != ($ws[0][.] // 0))
        | refuse($net; "stuck with \(.) at \($marking[.]), the final marking wants \($ws[0][.] // 0)"))
    else refuse($net; "stuck at \([$p.places[] | "\(.)=\($marking[.])"] | join(" ")), none of \($ws | length) final markings met")
    end;

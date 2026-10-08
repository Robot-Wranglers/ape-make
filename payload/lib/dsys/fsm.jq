#
# payload/lib/dsys/fsm.jq:
#  a state machine in the shape of an xstate machine config, normalized to
#  the definition xstate serializes, and compiled to a net that dsys/petri
#  runs: a place per state holding the machine's one token, an open place
#  per event the environment feeds, a transition per entry under on.
#  Definitions only; normalize and compile are the entries.
#

def refuse($who; $why): error("\($who): \($why)");

# Names of what the subset leaves out, refused at normalize.
def refused: ["context", "after", "history", "meta"];

# Actions as the definition writes them, one object per name.
def actions:
  if . == null then []
  elif type == "string" then [{type: .}]
  elif type == "array" then map(if type == "string" then {type: .} else . end)
  else [.] end;

# A target as an absolute id: a sibling by bare name, a child by a leading dot, an id by #.
def target($parent; $self):
  if . == null then []
  elif type == "array" then map(target($parent; $self)[])
  elif startswith("#") then [.]
  elif startswith(".") then ["#\($self)\(.)"]
  else ["#\($parent).\(.)"] end;

# One transition object of the definition from one entry under on; a guard is a name, or @ and a state.
def transition($parent; $self; $event; $entry):
  ($entry | if type == "string" then {target: .} else . end) as $o
  | { eventType: $event, source: "#\($self)",
      target: ($o.target | target($parent; $self)), actions: ($o.actions | actions) }
  + (if $o.guard then
       (select($o.guard | test("^(@|[A-Za-z0-9_.-]+$)") | not)
          | refuse($self; "guard \($o.guard) is an expression, not a name")),
       {cond: {type: $o.guard}}
     else {} end);

# The transitions under on, each event's entry or list of entries.
def transitions($parent; $self; $on):
  ($on // {}) | with_entries(.value |= (if type == "array" then . else [.] end))
  | with_entries(.key as $event | .value |= map(transition($parent; $self; $event; .)));

# A node's path under the machine, the machine's own id dropped.
def under: split(".")[1:] | join(".");

# A state's handlers: on, always as the empty event, onDone as the done event of the state itself.
def handlers($parent; $self; $s):
  transitions($parent; $self; ($s.on // {})
    + (if $s.always != null then {"": $s.always} else {} end)
    + (if $s.onDone != null then {("done.state.\($self | under)"): $s.onDone} else {} end));

# An invoke as the definition writes it, its done and error events as transitions.
def invoked($parent; $self; $inv):
  ($inv.id // $inv.src) as $iid
  | { invoke: [{type: "xstate.invoke", id: $iid, src: $inv.src}],
      on: ({} + (if $inv.onDone then {("done.invoke.\($iid)"): $inv.onDone} else {} end)
             + (if $inv.onError then {("error.platform.\($iid)"): $inv.onError} else {} end)
           | transitions($parent; $self; .)) };

# A state's kind: as written, else compound when it has children, else atomic.
def kind: .type // (if has("states") then "compound" else "atomic" end);

# Whether an initial is written as a name or a list of names; where they lead is checked at compile.
def named: type == "string" or (type == "array" and length > 0 and all(.[]; type == "string"));

# One state node of the definition, its children under it.
def node($parent; $key; $i; $s):
  "\($parent).\($key)" as $self
  | (refused[] as $r | select($s | has($r)) | refuse($self; "\($r) is outside the subset")),
    (select($s.type == "history") | refuse($self; "history is outside the subset")),
    (select(($s | kind) == "parallel" and (($s.states | type) != "object"))
      | refuse($self; "a parallel state needs regions under states")),
    (select(($s | kind) == "compound" and ($s.initial | named | not))
      | refuse($self; "initial names no state")),
    ({ id: $self, key: $key, order: $i, type: ($s | kind) }
     + (if ($s | kind) == "final" then {}
        else { on: handlers($parent; $self; $s), entry: ($s.entry | actions), exit: ($s.exit | actions) }
          + (if $s.invoke then (invoked($parent; $self; $s.invoke) as $v
               | {invoke: $v.invoke, on: (handlers($parent; $self; $s) + $v.on)}) else {} end)
        end)
     + (if ($s | kind) == "compound" then
          { initial: { actions: [], source: "#\($self)", target: ($s.initial | target($self; $self)) } }
        else {} end)
     + (if ($s | kind) == "compound" or ($s | kind) == "parallel" then
          { states: ([$s.states | to_entries | to_entries[]
              | {key: .value.key, value: node($self; .value.key; .key; .value.value)}] | from_entries) }
        else {} end));
def children($self; $states):
  [$states | to_entries | to_entries[]
    | {key: .value.key, value: node($self; .value.key; .key; .value.value)}] | from_entries;

# The config as the definition: ids under the machine, every node typed and ordered.
def normalize:
  . as $m | ($m.id // "machine") as $id
  | ((refused + ["always"])[] as $r | select($m | has($r)) | refuse($id; "\($r) is outside the subset")),
    (select(($m.states | type) != "object") | refuse($id; "states is not an object")),
    (select($m.initial | named | not) | refuse($id; "initial names no state")),
    { id: $id, key: $id, type: "compound", version: "1",
      initial: { actions: [], source: "#\($id)", target: ($m.initial | target($id; $id)) },
      states: children($id; $m.states) };

# A place's name is the node's id under the machine, dots and all.
def key($id): sub("^#?\($id)\\."; "");

# Every node of the definition as a record: id, parent, kind, transitions, actions, invoke, initial, children.
def flat($def):
  def rec($n; $parent):
    { id: $n.id, parent: $parent, type: $n.type, on: ($n.on // {}),
      entry: [($n.entry // [])[] | .type], exit: [($n.exit // [])[] | .type],
      invoke: (($n.invoke // [])[0] // null),
      initial: [($n.initial.target // [])[] | ltrimstr("#")],
      children: [($n.states // {})[] | .id] },
    (($n.states // {})[] | rec(.; $n.id));
  [$def.states[] | rec(.; $def.id)];

# A node's ancestry: itself and its ancestors up to, not including, the root.
def chain($by; $root; $id):
  if $id == $root then [] else [$id] + chain($by; $root; $by[$id].parent) end;
def depth($by; $root; $id): chain($by; $root; $id) | length;

# The nearest parallel state strictly above a node, and the region of it the node is in.
def par($by; $root; $id): [chain($by; $root; $id)[1:][] | select($by[.].type == "parallel")] | .[0];
def region($by; $root; $id):
  par($by; $root; $id) as $p
  | if $p == null then null else (chain($by; $root; $id) as $c | $c[($c | index($p)) - 1]) end;

# Whether a node is a state or lies under it.
def within($s): . == $s or startswith($s + ".");

# The leaves entered under a node by targets below it: each target settled through its initials, and every region of a parallel on the way that no target names entered by default.
def enter($by; $top; $ids):
  [ $ids[] as $t
    | ($by[$t] as $n
       | if $n.type == "compound" then enter($by; $t; $n.initial)[]
         elif $n.type == "parallel" then enter($by; $t; $n.children)[]
         else $t end),
      (chain($by; $top; $t)[1:][] | select($by[.].type == "parallel") | $by[.].children[]
       | select(. as $r | any($ids[]; within($r)) | not) | enter($by; .; [.])[]) ]
  | unique;

# Whether a descriptor takes an event: its own name, any name under a partial wildcard, anything for the star.
def matches($desc; $event):
  $desc == $event
  or ($event != "" and ($desc == "*" or (($desc | endswith(".*")) and ($event | startswith($desc[:-1])))));

# A descriptor's specificity: an exact name, then the longer partial wildcard, then the star.
def rank($desc): if $desc == "*" then 0 elif ($desc | endswith(".*")) then ($desc | length) else 1000 end;

# The event standing for every name a wildcard takes that no descriptor names.
def sentinel: if . == "*" then "_" else .[:-1] + "_" end;

# An invoke's own events, taken from its outcome rather than a place.
def internal: startswith("done.invoke.") or startswith("error.platform.");

# Every event the net needs a place for, always first, then done events, then the rest with each wildcard's sentinel.
def universe($by):
  [$by[] | .on | keys[] | select(internal | not) | if contains("*") then sentinel else . end] | unique
  | sort_by(if . == "" then 0 elif startswith("done.state.") then 1 else 2 end);

# The place an event lands in: its own, else the closest wildcard's sentinel, else none.
def route($u; $e):
  if any($u[]; . == $e) then $e
  else ([$u[] | select(. != "_" and endswith("._")) | .[:-1] | select(. as $p | $e | startswith($p))] | max_by(length)) as $p
    | if $p then $p + "_" elif any($u[]; . == "_") then "_" else null end end;

# The done events a configuration raises on entry: each nested final's parent, and a parallel whose regions all ended.
def dones($by; $root; $to):
  [$to[] | $by[.] | select(.type == "final" and .parent != $root) | .parent] as $parents
  | ($parents + [$parents[] | $by[.].parent | select(. != $root and $by[.].type == "parallel") | . as $P
       | select(all($by[$P].children[]; . as $r | any($to[]; $by[.].parent == $r and $by[.].type == "final")))])
  | unique | map("done.state.\(. | under)");

# The nearest node of a chain that handles an event, by its most specific descriptor, or null.
def handler($by; $chain; $event):
  first($chain[] as $n | [$by[$n].on | keys[] | select(matches(.; $event))] | select(length > 0)
        | max_by(rank(.)) as $d | {node: $n, entries: $by[$n].on[$d]}) // null;

# The targets of an entry, checked: none for a transition that stays, one, or one per region of a parallel state.
def targets($by; $root; $who; $tr):
  ($tr.target | map(ltrimstr("#"))) as $to
  | ($to[] | . as $t | select($by | has($t) | not) | refuse($who; "target \($t) is no state")),
    (select(($to | length) > 1)
     | ([$to[] | par($by; $root; .)] | unique) as $ps | ([$to[] | region($by; $root; .)] | unique) as $rs
     | select(($ps | length) != 1 or $ps[0] == null or ($rs | length) != ($to | length))
     | refuse($who; "targets \([$to[] | key($root)] | join(" ")) are not one per region of a parallel state")),
    $to;

# The event's part of a net transition's name; the empty event is always.
def ename($e): if $e == "" then "always" else $e end;

# The actions of a move: exits of what it leaves, deepest first, then entries of what it enters, from the top.
def acts($by; $root; $from; $to; $self):
  ([$from[] | chain($by; $root; .)[]] | unique) as $was
  | ([$to[] | chain($by; $root; .)[]] | unique) as $now
  | (if $self then $from else $was - $now end) as $left
  | (if $self then $to else $now - $was end) as $came
  | ([$left[] | [depth($by; $root; .), .]] | sort | reverse | map(.[1]) | [.[] | $by[.].exit[]])
    + ([$came[] | [depth($by; $root; .), .]] | sort | map(.[1]) | [.[] | $by[.].entry[]]);

# One net transition between leaves, its step the move's actions with the event bound.
def move($id; $by; $root; $name; $from; $event; $tos; $self):
  acts($by; $root; $from; $tos; $self) as $run
  | { name: $name, from: [$from[] | key($id)], event: $event, arc: true, tos: $tos, to: [$tos[] | key($id)] }
  + (if ($run | length) > 0 then {run: $run, bind: {("\($id).event"): $event}} else {} end);

# Whether a handler needs a choice at firing time: several entries, or one with a guard.
def guarded($h): ($h.entries | length) > 1 or ($h.entries[0].cond != null);

# A handler's choices: each alternative by its index, and 0 for none when every one is guarded.
def choices($h):
  if guarded($h) | not then [1]
  else [range(1; ($h.entries | length) + 1)] + (if all($h.entries[]; .cond != null) then [0] else [] end) end;

# The configuration a picker's guards read: the active leaves and their ancestors, as @state names them.
def config($by; $root; $leaves): [$leaves[] | chain($by; $root; .)[]] | unique | map(key($root)) | join(",");

# A picker: a step into a labeled place printing, per guarded handler, which alternative held.
def pick($id; $base; $from; $event; $arc; $guard; $hs; $config):
  { name: $base, from: $from, event: $event, arc: $arc, tos: [], to: ["\($base).choice"],
    run: ["\($id).\($base).pick"], kind: "goal", label: "output", place: "\($base).choice",
    pick: [$hs[] | select(guarded(.)) | [.entries[] | .cond.type // "-"]], bind: {("\($id).config"): $config} }
  + (if $guard then {guard: $guard} else {} end);

# The transitions one handler lowers to, from a source place: one move, or a picker and a move per choice.
def takes($id; $by; $root; $leaf; $event; $src; $guard; $h; $arc):
  "\($id).\($leaf | key($id))" as $who
  | "\($leaf | key($id)).\(ename($event))" as $base
  | def settle($to): if $to == [] then [$leaf] else enter($by; $root; $to) end;
    if guarded($h) | not then
      targets($by; $root; $who; $h.entries[0]) as $to
      | move($id; $by; $root; $base; [$leaf]; $event; settle($to); $to == [$leaf])
      | .from = [$src] | .arc = $arc | (if $guard then .guard = $guard else . end)
    else
      (select($event == "" and (choices($h) | index(0)) != null)
        | refuse($who; "an eventless transition with guards needs an unguarded alternative")),
      pick($id; $base; [$src]; $event; $arc; $guard; [$h]; config($by; $root; [$leaf])),
      (choices($h)[] as $c
       | (if $c == 0 then [] else targets($by; $root; $who; $h.entries[$c - 1]) end) as $to
       | move($id; $by; $root; "\($base).\($c)"; [$leaf]; $event; settle($to); $to == [$leaf])
       | .from = ["\($base).choice"] | .arc = false | .guard = {label: "\($c)"})
    end;

# An invoke's step: the service into a labeled place holding its outcome, fatal unless an error handler takes it.
def invoker($id; $by; $root; $leaf; $inv):
  ($leaf | key($id)) as $k
  | handler($by; chain($by; $root; $leaf); "error.platform.\($inv.id)") as $err
  | { name: "\($k).invoke", from: [$k], event: "", arc: false, tos: [], to: ["\($k).invoked"],
      run: [$inv.src], kind: (if $err then "goal.maybe" else "goal" end), label: "outcome", place: "\($k).invoked" };

# An invoke on a leaf outside any parallel state: its step, and its done and error handlers from the outcome.
def invokes($id; $by; $root; $leaf; $inv):
  "\($leaf | key($id)).invoked" as $place
  | chain($by; $root; $leaf) as $chain
  | handler($by; $chain; "done.invoke.\($inv.id)") as $done
  | handler($by; $chain; "error.platform.\($inv.id)") as $err
  | invoker($id; $by; $root; $leaf; $inv),
    (select($done != null) | takes($id; $by; $root; $leaf; "done.invoke.\($inv.id)"; $place; {label: "success"}; $done; false)),
    (select($err != null) | takes($id; $by; $root; $leaf; "error.platform.\($inv.id)"; $place; {label: "failed"}; $err; false));

# Net transitions for the leaves outside any parallel state: eventless first, then an invoke, then events.
def outside($id; $by; $root; $leaves):
  [$leaves[] as $leaf | select(par($by; $root; $leaf) == null)
    | chain($by; $root; $leaf) as $chain | ($leaf | key($id)) as $k
    | (handler($by; $chain; "") as $h | select($h != null) | takes($id; $by; $root; $leaf; ""; $k; null; $h; true)),
      ($by[$leaf].invoke as $inv | select($inv != null) | invokes($id; $by; $root; $leaf; $inv)),
      (universe($by)[] | select(. != "") as $event
       | handler($by; $chain; $event) as $h | select($h != null)
       | takes($id; $by; $root; $leaf; $event; $k; null; $h; true))];

# The cartesian product of lists.
def product: reduce .[] as $xs ([[]]; [.[] as $acc | $xs[] | $acc + [.]]);

# Where a region's token may sit: its leaf's place, and the invoked place of a leaf with a service.
def positions($by; $id; $leaf):
  ($leaf | key($id)) as $k | ($k | split(".") | last) as $tag
  | {leaf: $leaf, place: $k, tag: $tag, invoked: false, inv: null},
    ($by[$leaf].invoke | select(. != null) | {leaf: $leaf, place: "\($k).invoked", tag: "\($tag).invoked", invoked: true, inv: .});

# Net transitions for one parallel state: per configuration of its regions and event, what scxml selects.
def parallel($id; $by; $root; $P; $leaves):
  $by[$P].children as $regions
  | "\($id).\($P | key($id))" as $who
  | ([$regions[] as $r | [$leaves[] | select(region($by; $root; .) == $r and par($by; $root; .) == $P) | positions($by; $id; .)]] | product)[] as $combo
  | ($combo | map(.leaf)) as $cl
  | ($combo | map(.place)) as $places
  | (universe($by) + [$combo[] | select(.invoked) | .inv.id | "done.invoke.\(.)", "error.platform.\(.)"])[] as $event
  | ([$combo[] | select(.invoked) | .inv.id as $iid | select($event | endswith(".\($iid)"))] | .[0]) as $ipos
  | (if $ipos then {label: (if ($event | startswith("done.")) then "success" else "failed" end)} else null end) as $guard
  | ([range($regions | length) as $i | $combo[$i] as $pos
     | select(($event | internal) == $pos.invoked)
     | handler($by; chain($by; $P; $pos.leaf); $event) | select(. != null) | . + {i: $i}]
     | if length > 0 then . else [handler($by; chain($by; $root; $P); $event) | select(. != null) | . + {i: null}] end) as $hs
  | select(($hs | length) > 0)
  | ($event | internal | not) as $arc
  | "\($P | key($id)).\($combo | map(.tag) | join("-")).\(ename($event))" as $name
  | def settle($chosen):
      ([$chosen[] | .i as $i | .to as $to
        | . + {exit: (if $i == null then ($to | length) > 0 else any($to[]; within($regions[$i]) | not) end)}]
       | reduce .[] as $h ([]; if length == 0 then [$h] elif any(.[]; .exit) or $h.exit then . else . + [$h] end)) as $taken
      | if ($taken | length) > 0 and $taken[0].exit then [enter($by; $root; $taken[0].to)[] | {leaf: ., place: key($id)}]
        else [range($regions | length) as $i | ([$taken[] | select(.i == $i and (.to | length) > 0)] | .[0]) as $t
              | if $t then (enter($by; $regions[$i]; $t.to)[] | {leaf: ., place: key($id)}) else $combo[$i] end]
        end;
    if any($hs[]; guarded(.)) then
      ([$hs[] | choices(.)] | product) as $all
      | (select($event == "" and any($all[]; all(.[]; . == 0)))
          | refuse($who; "an eventless transition with guards needs an unguarded alternative")),
        pick($id; $name; $places; $event; $arc; $guard; $hs; config($by; $root; $cl)),
        ($all[] as $cs
         | ([range($hs | length) as $k | select(guarded($hs[$k])) | $cs[$k] | tostring] | join("-")) as $label
         | ([range($hs | length) as $k | select($cs[$k] > 0) | {i: $hs[$k].i, to: targets($by; $root; $who; $hs[$k].entries[$cs[$k] - 1])}] | settle(.)) as $tos
         | move($id; $by; $root; "\($name).\($label)"; $cl; $event; ($tos | map(.leaf)); false)
         | .from = ["\($name).choice"] | .to = ($tos | map(.place)) | .arc = false | .guard = {label: $label})
    else
      ([$hs[] | {i: .i, to: targets($by; $root; $who; .entries[0])}] | settle(.)) as $tos
      | move($id; $by; $root; $name; $cl; $event; ($tos | map(.leaf)); false)
      | .from = $places | .to = ($tos | map(.place)) | .arc = $arc | (if $guard then .guard = $guard else . end)
    end;

# The places the done events of an entered configuration land in, those its leaves' chains handle.
def raised($by; $root; $u; $tos):
  [dones($by; $root; $tos)[] as $e
   | select(any($tos[]; handler($by; chain($by; $root; .); $e) != null))
   | route($u; $e) | select(. != null)] | unique;

# The definition as the net dsys/petri runs: a place per leaf, an open place per event, a step per move with actions; a top-level final drops every event.
def compile($def):
  $def.id as $id
  | (flat($def) | map({key: .id, value: .}) | from_entries) as $by
  | ($by | to_entries | map(select(.value.type != "compound" and .value.type != "parallel") | .key)) as $leaves
  | ($by | to_entries | map(select(.value.type == "parallel") | .key)) as $parallels
  | ($by | to_entries | map(select(.value.type == "final" and .value.parent == $id))) as $finals
  | ($def.initial.target | map(ltrimstr("#"))) as $init
  | ($parallels[] | select(par($by; $id; .) != null) | refuse(.; "a parallel state inside a parallel state is not lowered yet")),
    ($init[] | . as $t | select(($by | has($t) | not) or ($t | within($id) | not)) | refuse($id; "initial \($t | key($id)) is no state")),
    ($by[] | select(.initial != []) | .id as $n | .initial[] | . as $t
      | select(($by | has($t) | not) or ($t | within($n) | not) or $t == $n) | refuse($n; "initial \($t | key($id)) is no state")),
    (universe($by) as $u
  | enter($by; $id; $init) as $starts
  | [$starts[] | key($id)] as $start
  | (outside($id; $by; $id; $leaves)
     + [$leaves[] | select(par($by; $id; .) != null and $by[.].invoke != null) | invoker($id; $by; $id; .; $by[.].invoke)]
     + [$parallels[] as $P | parallel($id; $by; $id; $P; $leaves)]
     | map(. + {done: raised($by; $id; $u; .tos)})) as $arcs
  | ([$arcs[] | select(.arc) | .event | select(. != "")] | unique) as $events
  | ($arcs + [$finals[] | .key as $f | $events[] | select(startswith("done.state.") | not)
       | { name: "\($f | key($id)).\(.)", from: [$f | key($id)], event: ., arc: true, tos: [$f], to: [$f | key($id)], done: [] }]) as $arcs
  | raised($by; $id; $u; $starts) as $lit
  | { places: (([$leaves[] | key($id) | {(.): (if IN($start[]) then 1 else 0 end)}]
               + [$events[] | {("ev.\(.)"): (if IN($lit[]) then 1 else 0 end)}]
               + [$arcs[] | .place | select(. != null) | {(.): []}]) | add),
      transitions: [$arcs[] | .name],
      arcs: [$arcs[] | .name as $n | .event as $e | .arc as $a
             | (.from[] | [., $n]), (select($a and $e != "") | ["ev.\($e)", $n]), (.to[] | [$n, .]), (.done[] | [$n, "ev.\(.)"])],
      amk: ({ backend: "petri", open: [$events[] | select(startswith("done.state.") | not) | "ev.\(.)"] }
        + ([$finals[] | {(.key | key($id)): 1}]
           | if length == 0 then {} elif length == 1 then {final: .[0]} else {final: .} end)
        + ([$arcs[] | select(.run) | {(.name): ({run: .run} + (if .bind then {bind: .bind} else {} end) + (if .kind then {kind: .kind} else {} end))}]
           | if length == 0 then {} else {steps: add} end)
        + ([$arcs[] | select(.guard) | {(.name): .guard}] | if length == 0 then {} else {guard: add} end)
        + ([$arcs[] | select(.label) | {(.name): .label}] | if length == 0 then {} else {label: add} end)),
      fsm: { enter: acts($by; $id; []; $starts; false),
             pickers: ([$arcs[] | select(.pick) | {("\($id).\(.name).pick"): .pick}] | add // {}),
             invokers: [$leaves[] | select($by[.].invoke != null) | key($id)] } });

def compile: normalize as $def | compile($def);

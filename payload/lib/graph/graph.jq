# The graph document: sugar normalized, names checked, compiled to SQL calling the cypher function, and assembled back from query rows.

def ident: type == "string" and test("^[A-Za-z_][A-Za-z0-9_]*$");
def sq: gsub("'"; "''");
def labels: if .label == null then [] elif (.label | type) == "array" then .label else [.label] end;

# A node key whose value is a list of node ids is an edge type with no properties.
def edge_sugar($g): (.value | type) == "array" and (.value | length) > 0
  and all(.value[]; type == "string" and (. as $t | $g.nodes | has($t)));

def normalize:
  (if type == "object" and has("nodes") then . else {nodes: ., edges: []} end)
  | .nodes = (.nodes // {}) | .edges = (.edges // [])
  | .nodes |= with_entries(.value |= (. // {}))
  | . as $g
  | .edges += [$g.nodes | to_entries[] | .key as $s | .value | to_entries[]
      | select(.key != "label" and edge_sugar($g))
      | .key as $t | .value[] | {source: $s, target: ., type: $t}]
  | .nodes |= with_entries(.value |= with_entries(select(.key == "label" or (edge_sugar($g) | not))))
  | .nodes |= with_entries(.value |= (if (.label | type) == "array" and (.label | length) == 1 then .label = .label[0] else . end));

# Every label, type and property key is an identifier.
def check_names:
  . as $g
  | ([$g.nodes | to_entries[] | .value | (labels[], (keys[] | select(. != "label")))]
     + [$g.edges[] | (.type, (keys[] | select(. != "source" and . != "target" and . != "type")))]
     | map(select(ident | not))) as $bad
  | if ($bad | length) > 0 then error("graph: not an identifier: \($bad[0] | tojson)") else . end;

# Every edge end is a node of this document; a document merged into a graph may name nodes the graph already has, so compile leaves this to the at line.
def check_ends:
  . as $g
  | ([$g.edges[] | .source, .target | . as $t | select(($g.nodes | has($t)) | not)]) as $missing
  | if ($missing | length) > 0 then error("graph: an edge end is not a node: \($missing[0] | tojson)") else . end;

def check: check_names | check_ends;

def statement($q; $rows): "SELECT cypher('\($q | sq)', '\({rows: $rows} | tojson | sq)');";

# One statement per set of labels and per edge type, every value a parameter.
def compile:
  normalize | check_names | . as $g
  | ([$g.nodes | to_entries | group_by(.value | labels)[]
      | (.[0].value | labels | map(":" + .) | join("")) as $l
      | statement("UNWIND $rows AS r MERGE (n\($l) {id: r.id}) SET n += r.props";
                  map({id: .key, props: (.value | del(.label))}))]
     + [$g.edges | group_by(.type)[] | .[0].type as $t
      | statement("UNWIND $rows AS r MATCH (a {id: r.source}), (b {id: r.target}) MERGE (a)-[e:\($t)]->(b) SET e += r.props";
                  map({source, target, props: del(.source, .target, .type)}))])
  | join("\n");

# The at line's document stands alone, so its edges end at its own nodes.
def compile_whole: normalize | check_ends | compile;

# The rows of the two dump queries back into the document.
def dump_nodes:
  map({key: .id, value: ((if (.labels | length) == 0 then {} elif (.labels | length) == 1 then {label: .labels[0]} else {label: .labels} end)
                         + (.props | del(.id)))})
  | from_entries;
def dump_edges: map({source, target, type} + .props);

# schema.jq, a JSON Schema draft 2020-12 validator by yne, github.com/yne/schema.jq, two-clause Berkeley license; as a module, with an unresolved ref an error and unevaluatedProperties for properties.

def getType:
  if . == null then "null"
  elif type == "boolean" then "boolean"
  elif type == "number" then
    if . == floor then "integer" else "number" end
  elif type == "string" then "string"
  elif type == "array" then "array"
  else "object" end;

def unescape_token: gsub("~1"; "/") | gsub("~0"; "~");

def decode_uri_fragment:
  gsub("%25"; "%") | gsub("%7E"; "~") | gsub("%7e"; "~") |
  gsub("%2F"; "/") | gsub("%2f"; "/");

def resolve_pointer($doc):
  . as $ptr |
  if $ptr == "" then $doc
  elif ($ptr | startswith("/") | not) then null
  else
    ($ptr | ltrimstr("/") | split("/") | map(unescape_token)) as $parts |
    reduce $parts[] as $part (
      $doc;
      if . == null then null
      elif type == "object" then .[$part]
      elif type == "array" then (if $part | test("^[0-9]+$") then .[$part | tonumber] else null end)
      else null end
    )
  end;

def collect_ids($base_id):
  . as $node |
  if ($node | type) != "object" then []
  else
    (if ($node | has("$id")) then
      ($node["$id"]) as $id |
      (if ($id | test("^https?://|^urn:")) then $id
       elif ($id | startswith("#")) then "\($base_id)\($id)"
       elif $base_id != "" then
         ($base_id | gsub("#.*$"; "") | gsub("/[^/]*$"; "")) + "/" + ($id | ltrimstr("/"))
       else $id end) as $resolved_id |
      [{"id": $resolved_id, "schema": $node}] +
      (if $resolved_id != $id then [{"id": $id, "schema": $node}] else [] end)
    else [] end) +
    (if ($node | has("$anchor")) then
      (if $base_id != "" then [
        {"id": "\($base_id | gsub("#.*$"; ""))#\($node["$anchor"])", "schema": $node},
        {"id": "#\($node["$anchor"])", "schema": $node}
      ] else [{"id": "#\($node["$anchor"])", "schema": $node}] end)
    else [] end) +
    ($node | to_entries | map(
      .value as $v |
      .key as $k |
      $v | if type == "object" then
        (if has("$id") then
          ($v["$id"]) as $new_id_raw |
          (if ($new_id_raw | test("^https?://|^urn:")) then $new_id_raw
           elif $base_id != "" then
             ($base_id | gsub("#.*$"; "") | gsub("/[^/]*$"; "")) + "/" + ($new_id_raw | ltrimstr("/"))
           else $new_id_raw end) as $new_base |
          collect_ids($new_base)
        else collect_ids($base_id) end)
      elif type == "array" then collect_ids($base_id)
      else [] end
    ) | add // [])
  end;

def build_registry($schemas_list):
  if ($schemas_list | length) == 0 then {}
  else
    [$schemas_list[] |
      select(type == "object") |
      . as $root |
      ($root["$id"] // "") as $base |
      collect_ids($base)] |
    add // [] |
    map({(.id): .schema}) |
    add // {}
  end;

def resolve_uri($base):
  . as $ref |
  if ($ref | startswith("http://") or startswith("https://") or startswith("urn:")) then $ref
  elif ($ref | startswith("/")) then
    ($base | capture("^(?<scheme>https?://[^/]+)") | .scheme // "") + $ref
  elif $base != "" then
    ($base | gsub("#.*$"; "") | gsub("/[^/]*$"; "")) + "/" + $ref
  else $ref end;

def resolve_ref($ref; $root; $registry):
  (if ($root | type) == "object" then ($root["$id"] // "") else "" end) as $base |
  if $ref == "#" then $root
  elif $ref | startswith("#/") then ($ref | decode_uri_fragment | .[1:] | resolve_pointer($root))
  elif $ref | startswith("#") then
    ($ref | decode_uri_fragment) as $decoded |
    ($registry[$decoded] // $registry[$ref] // null)
  elif $ref | test("#") then
    ($ref | split("#")[0]) as $base_part |
    ("#" + ($ref | split("#")[1])) as $frag |
    ($base_part | resolve_uri($base)) as $resolved_base |
    ($registry[$resolved_base] // $registry[$base_part]) as $base_schema |
    if $base_schema == null then null
    elif $frag == "#" then $base_schema
    elif $frag | startswith("#/") then ($frag | decode_uri_fragment | .[1:] | resolve_pointer($base_schema))
    else
      ($frag | decode_uri_fragment) as $decoded_frag |
      ($registry["\($resolved_base)\($decoded_frag)"] //
       $registry["\($base_part)\($decoded_frag)"] //
       $registry[$decoded_frag] //
       $registry[$frag])
    end
  elif $registry | has($ref) then $registry[$ref]
  else
    ($ref | resolve_uri($base)) as $resolved |
    ($registry[$resolved] // $registry[$ref] // null)
  end;

def validate($data; $schema; $root; $registry):
  # The keys of an object that a schema and the subschemas it applies in place evaluate, for unevaluatedProperties.
  def evaluated($d; $s; $r):
    if ($s | type) != "object" or ($d | type) != "object" then []
    else
      (if $s | has("$id") then $s else $r end) as $er |
      [ ($s.properties // {} | keys[] | select(. as $k | $d | has($k))),
        ($s.patternProperties // {} | keys[] as $p | $d | keys[] | select(test($p))),
        (if ($s | has("additionalProperties")) or ($s | has("unevaluatedProperties")) then $d | keys[] else empty end),
        (if $s | has("$ref") then
           resolve_ref($s["$ref"]; $er; $registry) as $t
           | if $t != null then evaluated($d; $t; $er)[] else empty end
         else empty end),
        ($s.allOf // [] | .[] | evaluated($d; .; $er)[]),
        (($s.anyOf // []) + ($s.oneOf // []) | .[]
           | select(validate($d; .; $er; $registry) == []) | evaluated($d; .; $er)[]),
        (if $s | has("if") then
           if validate($d; $s.if; $er; $registry) == []
           then evaluated($d; $s.if; $er)[], evaluated($d; $s.then // {}; $er)[]
           else evaluated($d; $s.else // {}; $er)[] end
         else empty end),
        ($s.dependentSchemas // {} | to_entries[] | select(.key as $k | $d | has($k))
           | evaluated($d; .value; $er)[])
      ] | unique
    end;
  if $schema == false then ["Schema is false"]
  elif $schema == true then []
  elif ($schema | type) != "object" then []
  else
    $data as $d | $schema as $s |
    (if $s | has("$id") then $s else $root end) as $effective_root |
    [
      (if $s | has("$ref") then
        resolve_ref($s["$ref"]; $effective_root; $registry) as $resolved |
        if $resolved != null then
          validate($d; $resolved; $effective_root; $registry)
        else ["Unresolved $ref \($s["$ref"])"] end
      else [] end),

      (if $s | has("type") then
        if ($s.type | type) == "string" then
          if $s.type == "integer" then
            if ($d | getType) == "integer" then [] else ["Type mismatch: expected integer, got \($d | getType)"] end
          elif $s.type == "number" then
            if ($d | type) == "number" then [] else ["Type mismatch: expected number, got \($d | getType)"] end
          elif ($d | getType) != $s.type then
            ["Type mismatch: expected \($s.type), got \($d | getType)"]
          else [] end
        elif ($s.type | type) == "array" then
          if ($s.type | any(. as $t |
            if $t == "integer" then ($d | getType) == "integer"
            elif $t == "number" then ($d | type) == "number"
            else ($d | getType) == $t end
          )) | not then
            ["Type mismatch: expected one of [\($s.type | join(", "))], got \($d | getType)"]
          else [] end
        else [] end
      else [] end),

      (if $s | has("enum") then
        if ($s.enum | any(. == $d)) | not
        then ["Value \($d | tojson) not in enum; one of \($s.enum | map(tojson) | join(" "))"]
        else [] end
      else [] end),

      (if $s | has("const") then
        if $d != $s.const then ["Value must equal const"] else [] end
      else [] end),

      (if ($d | type) == "number" then
        [
          (if $s | has("multipleOf") then
            if (($d / $s.multipleOf) | . != (. | floor)) then ["Not a multiple of \($s.multipleOf)"] else [] end
          else [] end),
          (if $s | has("maximum") then if $d > $s.maximum then ["Exceeds maximum \($s.maximum)"] else [] end else [] end),
          (if $s | has("exclusiveMaximum") then if $d >= $s.exclusiveMaximum then ["Exceeds exclusive maximum \($s.exclusiveMaximum)"] else [] end else [] end),
          (if $s | has("minimum") then if $d < $s.minimum then ["Less than minimum \($s.minimum)"] else [] end else [] end),
          (if $s | has("exclusiveMinimum") then if $d <= $s.exclusiveMinimum then ["At or below exclusive minimum \($s.exclusiveMinimum)"] else [] end else [] end)
        ] | add // []
      else [] end),

      (if ($d | type) == "string" then
        [
          (if $s | has("maxLength") then if ($d | explode | length) > $s.maxLength then ["Exceeds maxLength \($s.maxLength)"] else [] end else [] end),
          (if $s | has("minLength") then if ($d | explode | length) < $s.minLength then ["Less than minLength \($s.minLength)"] else [] end else [] end),
          (if $s | has("pattern") then if ($d | test($s.pattern)) | not then ["Does not match pattern \($s.pattern)"] else [] end else [] end)
        ] | add // []
      else [] end),

      (if ($d | type) == "array" then
        [
          (if $s | has("maxItems") then if ($d | length) > $s.maxItems then ["Exceeds maxItems \($s.maxItems)"] else [] end else [] end),
          (if $s | has("minItems") then if ($d | length) < $s.minItems then ["Less than minItems \($s.minItems)"] else [] end else [] end),
          (if ($s | has("uniqueItems")) and $s.uniqueItems then
            if ($d | unique | length) != ($d | length) then ["Has duplicate items"] else [] end
          else [] end),
          (if $s | has("contains") then
            ($d | map(validate(.; $s.contains; $effective_root; $registry) | length == 0) | map(if . then 1 else 0 end) | add // 0) as $cnt |
            ($s.minContains // 1) as $minC |
            ($s.maxContains // infinite) as $maxC |
            if $cnt < $minC then ["Array does not contain enough matching items (contains)"]
            elif $cnt > $maxC then ["Array contains too many matching items (maxContains)"]
            else [] end
          else
            []
          end),
          (if $s | has("prefixItems") then
            [$d | to_entries[] |
              (.key) as $idx | .value as $val |
              if $idx < ($s.prefixItems | length) then
                validate($val; $s.prefixItems[$idx]; $effective_root; $registry)
              else [] end
            ] | add // []
          else [] end),
          (if ($s | has("items")) and ($s.items != null) then
            if ($s | has("prefixItems") | not) then
              [$d[] | validate(.; $s.items; $effective_root; $registry)] | add // []
            else
              [$d | to_entries[] |
                (.key) as $idx | .value as $val |
                if $idx >= ($s.prefixItems | length) then
                  validate($val; $s.items; $effective_root; $registry)
                else [] end
              ] | add // []
            end
          else [] end)
        ] | add // []
      else [] end),

      (if ($d | type) == "object" then
        [
          (if $s | has("maxProperties") then if ($d | length) > $s.maxProperties then ["Exceeds maxProperties \($s.maxProperties)"] else [] end else [] end),
          (if $s | has("minProperties") then if ($d | length) < $s.minProperties then ["Less than minProperties \($s.minProperties)"] else [] end else [] end),
          (if $s | has("required") then
            ($s.required | map(. as $k | select(($d | has($k)) | not))) as $missing |
            if ($missing | length) > 0 then ["Missing required: \($missing | join(", "))"] else [] end
          else [] end),
          (if $s | has("properties") then
            [$s.properties | to_entries[] |
              .key as $key | .value as $propSchema |
              if $d | has($key) then
                validate($d[$key]; $propSchema; $effective_root; $registry) | map("Property \($key): " + .)
              else [] end
            ] | add // []
          else [] end),
          (if $s | has("patternProperties") then
            [$d | to_entries[] |
              .key as $key | .value as $val |
              [$s.patternProperties | to_entries[] |
                select(.key as $pat | $key | test($pat)) |
                validate($val; .value; $effective_root; $registry)
              ] | add // []
            ] | add // []
          else [] end),
          (if $s | has("additionalProperties") then
            [$d | to_entries[] |
              .key as $key | .value as $val |
              if (($s | has("properties")) and ($s.properties | has($key))) then []
              elif (($s | has("patternProperties")) and
                   ($s.patternProperties | keys | any(. as $pat | $key | test($pat)))) then []
              elif $s.additionalProperties == false then
                ["Additional property '\($key)' not allowed"]
              elif $s.additionalProperties == true then []
              else
                validate($val; $s.additionalProperties; $effective_root; $registry) |
                map("Additional property \($key): " + .)
              end
            ] | add // []
          else [] end),
          (if $s | has("propertyNames") then
            [$d | keys[] as $key |
              validate($key; $s.propertyNames; $effective_root; $registry) |
              map("Property name '\($key)': " + .)
            ] | add // []
          else [] end),
          (if $s | has("dependentRequired") then
            [$s.dependentRequired | to_entries[] |
              .key as $dep | .value as $required |
              if $d | has($dep) then
                ($required | map(. as $k | select(($d | has($k)) | not))) as $missing |
                if ($missing | length) > 0 then
                  ["dependentRequired '\($dep)' missing: \($missing | join(", "))"]
                else [] end
              else [] end
            ] | add // []
          else [] end),
          (if $s | has("dependentSchemas") then
            [$s.dependentSchemas | to_entries[] |
              .key as $dep | .value as $depSchema |
              if $d | has($dep) then validate($d; $depSchema; $effective_root; $registry) else [] end
            ] | add // []
          else [] end),
          (if $s | has("unevaluatedProperties") then
            evaluated($d; $s | del(.unevaluatedProperties); $effective_root) as $ev |
            [$d | keys[] as $k | select($ev | any(. == $k) | not) |
              if $s.unevaluatedProperties == false then ["Additional property '\($k)' not allowed"]
              elif $s.unevaluatedProperties == true then []
              else
                validate($d[$k]; $s.unevaluatedProperties; $effective_root; $registry) |
                map("Additional property \($k): " + .)
              end
            ] | add // []
          else [] end)
        ] | add // []
      else [] end),

      (if $s | has("allOf") then
        [$s.allOf[] | validate($d; .; $effective_root; $registry)] | add // []
      else [] end),

      (if $s | has("anyOf") then
        if ($s.anyOf | any(validate($d; .; $effective_root; $registry) | length == 0)) | not then
          ["No subschema in anyOf matches"]
        else [] end
      else [] end),

      (if $s | has("oneOf") then
        ($s.oneOf | map(validate($d; .; $effective_root; $registry) | length == 0) |
          map(if . then 1 else 0 end) | add) as $cnt |
        ([$s.oneOf[] | if has("enum") then .enum[] | tojson elif has("const") then .const | tojson
          elif has("type") then (.type | tostring) as $t | (if $t | test("^[aeiou]") then "an " else "a " end) + $t
          else empty end] | join(" ")) as $alts |
        if $cnt == 0 then ["Value \($d | tojson) matches no branch of oneOf; one of \($alts)"]
        elif $cnt != 1 then ["Exactly one of oneOf must match (matched \($cnt))"] else [] end
      else [] end),

      (if $s | has("not") then
        if (validate($d; $s.not; $effective_root; $registry) | length) == 0 then
          ["Data matches not schema"]
        else [] end
      else [] end),

      (if $s | has("if") then
        if (validate($d; $s.if; $effective_root; $registry) | length) == 0 then
          if $s | has("then") then validate($d; $s.then; $effective_root; $registry) else [] end
        else
          if $s | has("else") then validate($d; $s.else; $effective_root; $registry) else [] end
        end
      else [] end)

    ] | add // []
  end;

# The input's errors against a schema, with more schemas its refs may name; an empty array is valid.
def schema_errors($schema; $schemas):
  build_registry($schemas + [$schema]) as $registry |
  validate(.; $schema; $schema; $registry);
def schema_errors($schema): schema_errors($schema; []);

#
# payload/lib/dsys/pnml.awk:
#  a place/transition net in pnml as the JSON petri.amk loads: places with
#  their initial markings, transitions, and arcs with their inscriptions, in
#  document order. Names, graphics and tool-specific parts are passed over.
#
BEGIN { RS = "<" }

# An attribute's value on a tag, or nothing.
function attr(s, name) {
  if (match(s, name "=\"[^\"]*\""))
    return substr(s, RSTART + length(name) + 2, RLENGTH - length(name) - 3)
  return ""
}

{
  tag = $0; sub(/[ \t\r\n>].*/, "", tag); sub(/\/$/, "", tag)
  head = $0; sub(/>.*/, "", head)
  body = $0; sub(/^[^>]*>/, "", body)
  if (tag == "place") {
    cur = attr(head, "id"); place[++np] = cur; marking[cur] = 0; mode = ""
  } else if (tag == "transition") {
    trans[++nt] = attr(head, "id"); mode = ""
  } else if (tag == "arc") {
    na++; src[na] = attr(head, "source"); dst[na] = attr(head, "target")
    weight[na] = 1; mode = ""
  } else if (tag == "initialMarking" || tag == "inscription") {
    mode = tag
  } else if (tag == "/initialMarking" || tag == "/inscription") {
    mode = ""
  } else if (tag == "text" && mode == "initialMarking") {
    marking[cur] = body + 0
  } else if (tag == "text" && mode == "inscription") {
    weight[na] = body + 0
  }
}

END {
  printf "{\"places\":{"
  for (i = 1; i <= np; i++)
    printf "%s\"%s\":%d", (i > 1 ? "," : ""), place[i], marking[place[i]]
  printf "},\"transitions\":["
  for (i = 1; i <= nt; i++)
    printf "%s\"%s\"", (i > 1 ? "," : ""), trans[i]
  printf "],\"arcs\":["
  for (i = 1; i <= na; i++)
    printf "%s[\"%s\",\"%s\",%d]", (i > 1 ? "," : ""), src[i], dst[i], weight[i]
  print "]}"
}

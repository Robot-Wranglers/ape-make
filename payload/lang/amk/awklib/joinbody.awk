# A define body as the recipe lines of one target, for the preprocessor to
# print: the block indent removed, blank lines and comments dropped, a leading
# at-hash block kept as the docstring, and every other line chained by
# joinlines from functions.awk so the body shares one shell and fails fast.

# The recipe opens with the target's preamble variable, when one is defined, so
# a library may put text ahead of the body; the first body line's at sign moves
# up to it.
function preamble(name, op,   v) {
  v = "$(" name ".preamble)"
  return "$(if $(filter-out undefined,$(origin " name ".preamble))," \
    v (op == "" ? "" : " " op) ")"
}

function joinbody(body, n, join, name,
    i, m, base, c, op, doc, buf, quiet) {
  op = "&&"
  if (join == ";") op = ";"; else if (join == "none") op = ""
  base = ""
  for (i = 1; i <= n; i++) if (body[i] !~ /^[ \t]*$/) {
    match(body[i], /^[ \t]*/); base = substr(body[i], 1, RLENGTH); break }
  m = 0; doc = 1; quiet = ""
  for (i = 1; i <= n; i++) {
    c = body[i]
    if (base != "" && index(c, base) == 1) c = substr(c, length(base) + 1)
    if (doc && c ~ /^[ \t]*@#/) {
      sub(/^[ \t]*/, "", c); print "\t" c; continue }
    doc = 0; c = strip_comment(c)
    if (c ~ /^[ \t]*$/) continue
    if (m == 0 && c ~ /^[ \t]*@/) quiet = "@"
    sub(/^[ \t]*@/, "", c)
    buf[++m] = c
  }
  if (m > 0) print "\t" quiet preamble(name, op) (op == "" ? "" : " \\")
  joinlines(buf, m, join)
}

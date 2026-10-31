# The m5 wrap as a rewrite: a bare bracket read such as m5[1] becomes the value
# expansion $(m5[1]), taking a trailing accessor named in M5ACC and a trailing ?
# inside. A read already wrapped or glued to a preceding name passes through, as
# do define bodies, triple-quote literals and recipe doc lines. Runs behind
# globals.awk and functions.awk, with defskip and a parse_literal from the
# caller.
BEGIN {
  _na = split(M5ACC, _aa, " ")
  for (_ai = 1; _ai <= _na; _ai++) _acc[_aa[_ai]] = 1 }
function wrap(s,   out,i,L,c3,pc,prev2,start,j,grp,k,nm) {
  out = ""; i = 1; L = length(s)
  while (i <= L) {
    c3 = substr(s, i, 3)
    if (is_triple_quote(c3)) {
      parse_literal(substr(s, i), "m5wrap")
      out = out LIT_
      s = REM_
      i = 1
      L = length(s)
      continue }
    if (c3 == "m5[") {
      prev2 = (i >= 3) ? substr(s, i-2, 2) : ""
      pc = (i >= 2) ? substr(s, i-1, 1) : ""
      if (prev2 == "$(" || prev2 == "${" || pc ~ /[A-Za-z0-9._]/) {
        out = out "m5["
        i += 3
        continue }
      start = i; i += 2; grp = 0
      while (substr(s, i, 1) == "[") {
        j = i+1
        while (j <= L && substr(s, j, 1) != "]") j++
        if (j > L) break
        i = j+1
        grp = 1 }
      if (!grp) { out = out substr(s, start, 2); continue }
      if (substr(s, i, 1) == ".") {
        k = i+1
        while (k <= L && substr(s, k, 1) ~ /[A-Za-z0-9_]/) k++
        nm = substr(s, i+1, k-i-1)
        if (nm in _acc) i = k }
      if (substr(s, i, 1) == "?") i++
      out = out "$(" substr(s, start, i - start) ")"; continue }
    out = out substr(s, i, 1); i++
  }
  return out }
defskip($0) { print; next }
/^\t@#/ { print; next }
{ print wrap($0) }

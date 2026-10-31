# The functions every amk awk program shares; a program runs behind globals.awk
# and this file.
function trim(s) { sub(/^[ \t]+/, "", s); sub(/[ \t]+$/, "", s); return s }
function lead_ws(s) { match(s, /^[ \t]*/); return substr(s, 1, RLENGTH) }
function strip_prefix(s, p) {
  return (substr(s, 1, length(p)) == p) ? substr(s, length(p) + 1) : s }
# Character classes over the grammar symbols: an identifier character, and one
# allowed in a callform name, which adds the predicate and bang suffixes.
function is_name_char(c) { return (c ~ SYM_NAME) }
function is_call_name_char(c) { return (c ~ SYM_NAME_CALL) }
# One of the three triple-quote openers a literal starts with.
function is_triple_quote(s) {
  return (s == "'''" || s == "\"\"\"" || s == "```") }
# Shell quoting: single quotes make s one literal word; double quotes escape
# only backslash and double quote, so dollar and backtick still expand.
function shell_single_quote(s,   n, p, i, r) {
    n = split(s, p, "'"); r = p[1]
    for (i = 2; i <= n; i++) r = r "'\\''" p[i]
    return "'" r "'" }
function shell_double_quote(s,   n, p, i, r) {
    n = split(s, p, /\\/); r = p[1]
    for (i = 2; i <= n; i++) r = r "\\\\" p[i]
    s = r; n = split(s, p, /"/); r = p[1]
    for (i = 2; i <= n; i++) r = r "\\\"" p[i]
    return "\"" r "\"" }
# Define blocks: an opener, indented or with the override, export, or private
# prefix; an opener at column 0 with no prefix; a closer; and the name an
# opener defines.
function is_define(s) {
  return s ~ /^[ \t]*((override|export|private)[ \t]+)*define([ \t]|$)/ }
function is_define_col0(s) { return s ~ (SYM_DEFINE " ") }
function is_endef(s) { return s ~ /^[ \t]*endef([ \t]|$|#)/ }
function defname(s,   t) {
  t = s; sub(/^[ \t]*((override|export|private)[ \t]+)*define[ \t]*/, "", t)
  sub(/[ \t].*$/, "", t); sub(/=.*$/, "", t); sub(/[:+?!]$/, "", t); return t }
# The offset of a trailing shell comment, outside quotes and make references,
# or zero.
function comment_pos(s,   i, c, q, depth, prev) {
  q = ""; depth = 0
  for (i = 1; i <= length(s); i++) {
    c = substr(s, i, 1)
    if (q != "") {
      if (q == "\"" && c == "\\") i++; else if (c == q) q = ""
      continue }
    if (c == "'" || c == "\"" || c == "`") { q = c; continue }
    if (c == "$" && substr(s, i + 1, 1) ~ /[({]/) { depth++; i++; continue }
    if (depth > 0 && c ~ /[)}]/) { depth--; continue }
    if (depth == 0 && c == "#") {
      prev = i == 1 ? "" : substr(s, i - 1, 1)
      if (prev == "" || prev ~ /[ \t]/) return i }
  }
  return 0
}
function strip_comment(s,   p) {
  p = comment_pos(s)
  if (p > 0) { s = substr(s, 1, p - 1); sub(/[ \t]+$/, "", s) }
  return s }
# Makefile line classifiers: a rule header and the target it names, an
# assignment and the variable it names.
function is_target(s) { return (s ~ /^[^\t#][^=]*:([^=]|$)/) }
function target_name(s,   name) {
    name = s; sub(/:.*/, "", name); sub(/^[ \t]+/, "", name)
    sub(/[ \t].*/, "", name)
    return name
}
function is_assign(s) {
    return (s ~ ("^[ \t]*" SYM_NAME "+[ \t]*(:=|\\+=|\\?=|=|<-)")) }
function assign_name(s,   name) {
    name = s; sub(/[ \t]*(:=|\+=|\?=|=|<-).*/, "", name)
    sub(/^[ \t]+/, "", name)
    return name
}
# The index in s of the closer that balances a group already open before
# index from, honouring nesting; 0 when it never closes.
function group_close(s, from, oc, cc,   depth, n, c) {
  depth = 1; n = length(s)
  for (; from <= n; from++) {
    c = substr(s, from, 1)
    if (c == oc) depth++; else if (c == cc && --depth == 0) return from }
  return 0 }
# The first top-level shell statement separator in s, a semicolon or a logical
# and or or, as its position and text in sepout, or position 0; one inside
# quotes or a paren or brace group is skipped.
function next_sep(s, sepout,   i, c, n, q, d, two, bs) {
  n = length(s); q = ""; d = 0; bs = 0
  for (i = 1; i <= n; i++) {
    c = substr(s, i, 1)
    if (q == "'") { if (c == "'") q = ""; continue }
    if (bs) { bs = 0; continue }
    if (c == "\\") { bs = 1; continue }
    if (q == "\"") { if (c == "\"") q = ""; continue }
    if (c == "'" || c == "\"") { q = c; continue }
    if (c == "(" || c == "{") { d++; continue }
    if (c == ")" || c == "}") { if (d > 0) d--; continue }
    if (d > 0) continue
    if (c == ";") { sepout[1] = i; sepout[2] = ";"; return }
    two = substr(s, i, 2)
    if (two == "&&") { sepout[1] = i; sepout[2] = "&&"; return }
    if (two == "||") { sepout[1] = i; sepout[2] = "||"; return }
  }
  sepout[1] = 0; sepout[2] = "" }
# Recipe lines as one shell, chained by the join connector: and, semicolon, or none.
function joinlines(buf, m, join,   i, conn, tail) {
  conn = " && \\"
  if (join == ";") conn = " ; \\"; else if (join == "none") conn = ""
  for (i = 1; i <= m; i++) {
    if (i == m) tail = ""
    else if (buf[i] ~ /\\$/) tail = ""
    else if (buf[i] ~ /(;|&&|\|\||\||&)[ \t]*$/) tail = conn == "" ? "" : " \\"
    else tail = conn
    print "\t" buf[i] tail
  }
}
# The one exit for a refusal: the stage, the message, and the line number and
# source text it cites when given; exit status 76.
function amk_die(stage, msg, lineno, src) {
  printf "amk (%s) error: %s:%s: %s%s\n", stage, file, lineno,
    (src == "" ? "" : src ": "), msg > "/dev/stderr"
  failed = 1; exit 76 }

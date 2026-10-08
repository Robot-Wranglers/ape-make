# The define decorator as a rewrite: a column-0 decorator above a define is
# dropped, and one line after the endef calls the macro name_star with the
# define's name and the arguments, or errors naming the macro; a decorator that
# no define follows passes through. A define closed on its own line, define name
# body endef, becomes the three-line block first. A refusal is one line in amk's
# voice through amk_die, with the file, the line, and the at line it names, and
# exit status 76. Runs behind globals.awk and functions.awk.

# A one-line define ends in the word endef; the text between the name with any
# assignment token and that word is the body.
function oneliner(s,   t) {
  if (!is_define(s) || s !~ /[ \t]endef[ \t]*$/) return 0
  t = s; sub(/[ \t]+endef[ \t]*$/, "", t); ohead = t
  sub(/^[ \t]*((override|export|private)[ \t]+)*define[ \t]*/, "", t)
  sub(/^[^ \t]+/, "", t)
  t = trim(t)
  sub(/^(::=|:=|\+=|\?=|!=|=)[ \t]*/, "", t)
  obody = t
  ohead = substr(ohead, 1, length(ohead) - length(obody))
  sub(/[ \t]+$/, "", ohead)
  return 1
}

# The grammar: a name, then positional arguments, each a word or a quoted
# literal, with parens as an optional group that also takes commas; options as
# key=value inside braces; an unquoted colon starts the prerequisites and a
# triple colon the mark. The raw text a macro gets is the arguments as written,
# a lone group unwrapped.
function arg_end(i,   t, eq) {
  if (!intok) return
  t = tok; eq = tokeq; intok = 0; tok = ""; tokeq = 0
  if (inopt) {
    if (eq < 2) amk_die("preprocess",
      "an option in braces is key=value, not " t, NR, "@" pname)
    pkwn[i]++
    pkwk[i, pkwn[i]] = substr(t, 1, eq - 1)
    pkwv[i, pkwn[i]] = substr(t, eq + 1)
    return
  }
  pn++; pel[i, pn] = t; pkey[i, pn] = ""
  if (eq > 1) {
    pkey[i, pn] = substr(t, 1, eq - 1)
    pel[i, pn] = substr(t, eq + 1) }
}
function at_parse(s, idx,   rest, i, L, c, q, d, before, hadd, hadb, eng) {
  if (match(s, "^@" SYM_NAME "+") == 0) return 0
  pname = substr(s, 2, RLENGTH - 1)
  rest = substr(s, RLENGTH + 1)
  pkind = ""; pargs = ""; pdeps = ""; eng = ""
  if (match(rest, "^/" SYM_NAME "+")) {
    eng = substr(rest, 2, RLENGTH - 1)
    rest = substr(rest, RLENGTH + 1) }
  if (rest !~ /^([ \t]|$|:|\(|\{)/) return 0
  rest = trim(rest)
  if (rest ~ /^(=|:=|::=|\+=|\?=|!=)/) return 0
  pn = 0; pkwn[idx] = 0; tok = ""; tokeq = 0; intok = 0; inopt = 0
  if (eng != "") { pn = 1; pel[idx, 1] = eng; pkey[idx, 1] = "" }
  q = ""; d = 0; hadd = 0; hadb = 0; L = length(rest); before = rest
  for (i = 1; i <= L; i++) {
    c = substr(rest, i, 1)
    if (q != "") { if (c == q) q = ""; else tok = tok c; continue }
    if (c == "'" || c == "\"") { q = c; intok = 1; continue }
    if (c == "(" || c == "{") {
      if (d) amk_die("preprocess", "a group does not nest", NR, "@" pname)
      if (c == "(" ? hadd++ : hadb++)
        amk_die("preprocess", "one group of each kind", NR, "@" pname)
      arg_end(idx); d = c; inopt = (c == "{"); continue
    }
    if ((c == ")" && d == "(") || (c == "}" && d == "{")) {
      arg_end(idx)
      d = 0
      inopt = 0
      continue }
    if (c == ")" || c == "}") amk_die("preprocess", "a stray " c, NR, "@" pname)
    if (!d && substr(rest, i, 3) == ":::") {
      arg_end(idx)
      pkind = trim(substr(rest, i + 3))
      before = trim(substr(rest, 1, i - 1))
      break }
    if (!d && c == ":") {
      arg_end(idx)
      pdeps = trim(substr(rest, i + 1))
      before = trim(substr(rest, 1, i - 1))
      break }
    if (c == " " || c == "\t" || (c == "," && d)) { arg_end(idx); continue }
    if (c == "=" && intok && tokeq == 0) tokeq = length(tok) + 1
    tok = tok c; intok = 1
  }
  if (q != "") amk_die("preprocess", "an unterminated quote", NR, "@" pname)
  if (d) amk_die("preprocess", "an unterminated group", NR, "@" pname)
  arg_end(idx)
  if (pdeps != "" && (i = index(pdeps, ":::")) > 0) {
    pkind = trim(substr(pdeps, i + 3))
    pdeps = trim(substr(pdeps, 1, i - 1)) }
  if (before ~ /^\(.*\)$/) before = trim(substr(before, 2, length(before) - 2))
  if (eng != "") before = eng (before == "" ? "" : " " before)
  pargs = before (pdeps == "" ? "" : (before == "" ? "" : " ") ": " pdeps)
  pcnt[idx] = pn; pdep[idx] = pdeps
  return 1
}

# The call leaves the decorator's text and its parsed pieces where its macro can
# read them, as amk.decorator and the variables under it.
function emit(i,   a, k, kws) {
  a = (args[i] == "") ? "" : "," args[i]
  printf "$(eval amk.decorator = %s:%d: @%s%s)", file, line[i], name[i],
    (args[i] == "") ? "" : " " args[i]
  printf "$(eval amk.decorator.deps = %s)$(eval amk.decorator.argc := %d)",
    pdep[i], pcnt[i]
  for (k = 1; k <= pcnt[i]; k++)
    printf "$(eval amk.decorator.%d = %s)$(eval amk.decorator.%d.key = %s)",
      k, pel[i, k], k, pkey[i, k]
  kws = ""
  for (k = 1; k <= pkwn[i]; k++) {
    kws = kws (k > 1 ? " " : "") pkwk[i, k]
    printf "$(eval amk.decorator.kw.%s = %s)", pkwk[i, k], pkwv[i, k] }
  printf "$(eval amk.decorator.kws = %s)", kws
  printf "$(if $(filter-out undefined,$(origin %s.__schema__)),$(amk.val.schema %s, $(%s.__schema__)))",
    name[i], subject, name[i]
  printf "$(if $(filter-out undefined,$(origin %s_star)),$(if $(call %s_star,%s%s),),$(error %s:%d: @%s: no macro %s_star))\n",
    name[i], name[i], subject, a, file, line[i], name[i], name[i]
}
# The amk.target decorator, its amklang names, and any dot amk name, is a rewrite in
# place: the define stays, and after it the phony rule, its prerequisites the
# text after the colon and its recipe the joined body, with the default goal put
# back; a dot amk name also calls its macro, which may set the target's
# preamble.
function is_amk_target(nm) {
  return nm == "amk.target" || nm == "amklang.target" || nm == "amklang.import.target" }
function is_rule(i) { return is_amk_target(name[i]) || name[i] ~ /\.amk$/ }
function rule(i,   k, join) {
  join = "&&"
  for (k = 1; k <= pkwn[i]; k++) if (pkwk[i, k] == "join") join = pkwv[i, k]
  if (!is_amk_target(name[i])) emit(i)
  print "amk.goal := $(.DEFAULT_GOAL)"
  print ".PHONY: " subject
  print subject ":" (pdep[i] == "" ? "" : " " pdep[i])
  joinbody(body, nb, join, subject)
  print ".DEFAULT_GOAL := $(amk.goal)"
}
function flush(all,   i) {
  for (i = 1; i <= nh; i++) if (all || !isat[i]) print held[i]
  nh = 0 }
function clear() { n = 0; nh = 0; nb = 0 }
function check(   i) {
  for (i = 1; i <= n; i++) if (kind[i] != "" && kind[i] != "postfix")
    amk_die("preprocess", "a define decorator takes only postfix", line[i],
      "@" name[i] " ::: " kind[i])
}

# One input line, after a one-line define has been split into its three.
function step(s,   i) {
  if (depth > 0) {
    print s
    if (is_define(s)) depth++
    else if (is_endef(s)) {
      depth--
      if (depth == 0 && subject != "") {
        for (i = n; i >= 1; i--) if (is_rule(i)) rule(i); else emit(i)
        clear()
        subject = "" } }
    else if (subject != "") body[++nb] = s
    return }
  if (s ~ /^@/ && at_parse(s, n + 1)) {
    n++
    name[n] = pname
    args[n] = pargs
    kind[n] = pkind
    line[n] = NR
    held[++nh] = s
    isat[nh] = 1
    return }
  if (n > 0 && is_define(s)) {
    check()
    subject = defname(s)
    flush(0)
    depth = 1
    print s
    return }
  if (n > 0 && s ~ /^[ \t]*(#|$)/) { held[++nh] = s; isat[nh] = 0; return }
  if (n > 0) { flush(1); clear() }
  if (is_define(s)) depth = 1
  print s
}

BEGIN {
  n = 0; nh = 0; nb = 0; depth = 0; subject = ""; failed = 0
  if (file == "") file = "-" }
{
  if (oneliner($0)) {
    step(ohead)
    if (obody != "") step(obody)
    step("endef") }
  else step($0) }
END { if (!failed) flush(1) }

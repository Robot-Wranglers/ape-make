# The target decorator as a rewrite, the sibling of the define decorator in
# definedecorators.awk, and it decorates only targets and assignments: column-0
# decorator lines above a target, a column-0 at sign and a macro name, are
# relocated as make calls: each is read as a callform behind the prefix
# TARGET_DECORATOR_PREFIX and lowered by callforms.awk. A trailing triple-colon
# mark names the kind, else a companion advice assignment, else before. Weave
# kinds compose the recipe: before joins ahead of the body, and after_return,
# after, and after_throw chain behind it by a connector and a line continuation,
# so make joins them into one shell command. Block kinds compose the file:
# prefix prints the call above the target or assignment, postfix once it ends.
# Around moves the body aside and calls through the aspect; mark prints the call
# above a target with its name as first argument. Stray decorator lines print
# back as written; a refusal goes through amk_die. Runs behind the awklib.

# An explicit trailing mark wins, then the advice registry, then before.
function classify(line,   adv, cleaned, name) {
  cleaned = line
  if (match(line, /[ \t]*:::[ \t]*[A-Za-z_]+[ \t]*$/)) {
    adv = substr(line, RSTART, RLENGTH); cleaned = substr(line, 1, RSTART-1)
    sub(/^[ \t]*:::[ \t]*/, "", adv); sub(/[ \t]*$/, "", adv)
  } else {
    name = strip_prefix(line, TARGET_DECORATOR_PREFIX)
    sub(/\(.*/, "", name)
    sub(/[ \t]+$/, "", name)
    adv = (name in pdefault) ? pdefault[name] : "before"
  }
  if (cleaned !~ /\(/) cleaned = cleaned "()"
  # around and mark keep the callform until the target name is threaded in.
  if (adv != "around" && adv != "mark") cleaned = lower_callforms__macro(cleaned)
  if (adv == "before") { pren++; pre[pren] = cleaned; return }
  if (adv == "prefix") { blockn++; block[blockn] = cleaned; return }
  if (adv == "postfix") { bpostn++; bpost[bpostn] = cleaned; return }
  if (adv == "around") { aroundn++; around[aroundn] = cleaned; return }
  if (adv == "mark") { markn++; mark[markn] = cleaned; return }
  if (!(adv in advconn)) amk_die("targetdecorators",
    "advice must be one of: before after_return after after_throw prefix postfix around mark (got: " adv ")",
    NR)
  postn++; post[postn] = cleaned; postc[postn] = advconn[adv]
}
# Decorator lines nothing can take print back as written, like any line no
# stage claims.
function release_stray(   k) {
  for (k = 1; k <= rawn; k++) print rawl[k]
  rawn = 0; pren = 0; postn = 0; blockn = 0; bpostn = 0; aroundn = 0; markn = 0
}
function emit_block(   k) {
  for (k = 1; k <= blockn; k++) print block[k]
  blockn = 0
}
# The marks above a target, each called with the target's name.
function emit_marks(name,   k) {
  for (k = 1; k <= markn; k++)
    print lower_callforms__macro(with_handle(mark[k], name))
  markn = 0
}
# The deferred postfix calls, once the decorated target or assignment has ended.
function emit_bpost(   k) {
  for (k = 1; k <= bpostn; k++) print bpost[k]
  bpostn = 0; bpend = ""
}
# An around macro freezes in place, then rebinds to the aspect holding that
# slot.
function emit_around_macro(s,   name, i, slot) {
  name = assign_name(s)
  print s
  for (i = 1; i <= aroundn; i++) {
    slot = name ".__prev__." i
    print "$(call m5.def!," slot ",$(value " name "))"
    print name "=" lower_callforms__macro(with_handle(around[aroundn - i + 1],
      slot ",$(1)"))
  }
  aroundn = 0
}
# The proceed handle rides as the aspect's first positional, so nesting stays
# re-entrant.
function with_handle(call, slot,   p, head, rest) {
  p = index(call, "("); head = substr(call, 1, p); rest = substr(call, p + 1)
  if (rest ~ /^\)/) return head slot rest
  return head slot "," rest
}
# A leading docstring documents the public name, so it stays behind when the
# body moves.
function docstring_span(   n, line) {
  if (arn < 1 || arbody[1] !~ /^[ \t]*'''/) return 0
  line = arbody[1]
  if (gsub(/'''/, "&", line) >= 2) return 1
  for (n = 2; n <= arn; n++) if (arbody[n] ~ /'''/) return n
  return 0
}
# The moved body lands in a block opened and closed by the block markers, a
# define unless the caller lowers it later.
function emit_around(   k, i, ds) {
  ds = docstring_span()
  print TARGET_DECORATOR_BLOCK_OPEN arname ".__prev__.1"
  for (k = ds + 1; k <= arn; k++) print arbody[k]
  print TARGET_DECORATOR_BLOCK_CLOSE
  for (i = 1; i < aroundn; i++) {
    print TARGET_DECORATOR_BLOCK_OPEN arname ".__prev__." (i + 1)
    print "\t" lower_callforms__macro(with_handle(around[aroundn - i + 1],
      arname ".__prev__." i))
    print TARGET_DECORATOR_BLOCK_CLOSE
  }
  print arname ":"
  for (k = 1; k <= ds; k++) print arbody[k]
  print "\t" lower_callforms__macro(with_handle(around[1],
    arname ".__prev__." aroundn))
  aroundn = 0; arn = 0; arpend = 0; arname = ""
}
# The first line, inline recipe or last body line, then the after calls, each
# connector and a line continuation appended to the line before it.
function emit_chain(first, firsttab,   k, n, txt) {
  n = 1; cseq[1] = first; ctab[1] = firsttab; cconn[1] = ""
  for (k = 1; k <= postn; k++) {
    n++
    cseq[n] = post[k]
    ctab[n] = "\t"
    cconn[n] = postc[k] }
  for (k = 1; k <= n; k++) {
    txt = ctab[k] cseq[k]
    if (k < n) txt = txt " " cconn[k+1] " \\"
    print txt }
}
# A deferred after target: the body with its last line joined to the chain; a
# target with no body gets plain lines.
function emit_post(   k) {
  if (bn >= 1) {
    for (k = 1; k < bn; k++) print body[k]
    emit_chain(body[bn], "") }
  else { for (k = 1; k <= postn; k++) print "\t" post[k] }
  bn = 0; postn = 0; inpost = 0
}
BEGIN { failed = 0; if (file == "") file = "-"
  CALLFORM_MACRO_TRIGGER = "prefix"
  CALLFORM_MACRO_PREFIX = TARGET_DECORATOR_PREFIX
  if (TARGET_DECORATOR_BLOCK_OPEN == "") TARGET_DECORATOR_BLOCK_OPEN = "define "
  if (TARGET_DECORATOR_BLOCK_CLOSE == "") TARGET_DECORATOR_BLOCK_CLOSE = "endef"
  in_def = 0; rawn = 0; pren = 0; postn = 0; bn = 0; inpost = 0; blockn = 0
  bpostn = 0; bpend = ""; aroundn = 0; arn = 0; arpend = 0; arname = ""; markn = 0
  advconn["after_return"] = "&&"
  advconn["after"] = ";"
  advconn["after_throw"] = "||"
  if (TARGET_DECORATOR_MARKS == "") TARGET_DECORATOR_MARKS = "amk.file amk.nocache"
  nmarks = split(TARGET_DECORATOR_MARKS, markdefault, " ")
  for (k = 1; k <= nmarks; k++) pdefault[markdefault[k]] = "mark" }
{
  if (inpost) {
    if ($0 ~ /^[ \t]*$/) {
      emit_post()
      if (bpend == "recipe") emit_bpost()
      print
      next }
    if ($0 ~ /^[ \t]/) { body[++bn] = $0; next }
    emit_post()
  }
  if (arpend) {
    if ($0 ~ /^[ \t]/ && $0 !~ /^[ \t]*$/) { arbody[++arn] = $0; next }
    emit_around()
  }
  if (bpend == "recipe") {
    if ($0 ~ /^[ \t]/ && $0 !~ /^[ \t]*$/) { print; next }
    emit_bpost()
  }
  if ($0 ~ /^[A-Za-z._][A-Za-z0-9._]*\.advice[ \t]*:?=/ && !in_def) {
    dname = $0; sub(/\.advice[ \t]*:?=.*/, "", dname)
    dmode = $0
    sub(/.*\.advice[ \t]*:?=[ \t]*/, "", dmode)
    sub(/[ \t]*$/, "", dmode)
    pdefault[dname] = dmode; print; next
  }
  # an equals sign before any paren makes the line an assignment to a variable
  # whose name starts with an at sign.
  if ($0 ~ /^@[A-Za-z._]/ && !in_def && $0 !~ /^@[^(=]*=/) {
    rawl[++rawn] = $0
    sub(/^@/, TARGET_DECORATOR_PREFIX)
    classify($0)
    next }
  if (aroundn > 0) {
    if (is_target($0)) {
      rawn = 0
      arname = target_name($0)
      arpend = 1
      arn = 0
      next }
    if (is_assign($0)) { rawn = 0; emit_around_macro($0); next }
    release_stray()
  }
  # a weave kind or a mark needs a target; a block kind also rides above an assignment.
  weave = (pren > 0 || postn > 0 || markn > 0)
  if ((weave || blockn > 0 || bpostn > 0) && !is_target($0) &&
    !(!weave && is_assign($0))) release_stray()
  if (pren > 0 || postn > 0 || blockn > 0 || bpostn > 0 || markn > 0) {
    rawn = 0
    if (blockn > 0) emit_block()
    if (markn > 0) emit_marks(target_name($0))
    if (bpostn > 0) bpend = is_target($0) ? "recipe" : "line"
    if (!is_target($0)) {
      print $0
      if (bpend == "line") emit_bpost()
      next }
    r = index($0, ";"); c = index($0, ":")
    if (r > c) {
      hdr = substr($0, 1, r-1); rec = substr($0, r+1); sub(/^[ \t]+/, "", rec)
      print hdr; for (i = 1; i <= pren; i++) print "\t" pre[i]
      emit_chain(rec, "\t"); pren = 0; postn = 0; next }
    else {
      print $0; for (i = 1; i <= pren; i++) print "\t" pre[i]; pren = 0
      if (postn > 0) { inpost = 1; bn = 0 }
      next }
  }
  if (is_define_col0($0)) { in_def = 1; print; next }
  if ($0 ~ /^endef[ \t]*$/) { in_def = 0; print; next }
  if (in_def) { print; next }
  print $0
}
END { if (failed) exit 76
  if (inpost) emit_post()
  if (arpend) emit_around()
  if (bpend != "") emit_bpost()
  release_stray() }

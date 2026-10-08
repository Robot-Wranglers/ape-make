# Callform lowering, the macro mode only: lower_callforms__macro rewrites each
# trigger, a name and a parenthesized argument list, as a make call with the
# arguments lowered in turn; the target, smart, stream, and env modes live in
# the compose.mk callform stage. CALLFORM_MACRO_TRIGGER picks the trigger:
# prefix, a CALLFORM_MACRO_PREFIX string before the name, or names, any key of
# CALLFORM_MACRO_NAMES. CALLFORM_MACRO_SELF_TOKEN, when set, is a token a
# prefixed name may start with. An unbalanced paren is re-emitted as written.
# Runs behind globals.awk.

function lower_callforms__macro(text,
    result, pos, hit, name, lit, astart, args, paren, c, p,
    kp, klen, blen, bname, bpos) {
  result = ""; pos = 1
  while (pos <= length(text)) {
    if (CALLFORM_MACRO_TRIGGER == "prefix") {
      hit = index(substr(text, pos), CALLFORM_MACRO_PREFIX)
      if (hit == 0) { result = result substr(text, pos); break }
      result = result substr(text, pos, hit - 1)
      pos = pos + hit - 1 + length(CALLFORM_MACRO_PREFIX)
      lit = CALLFORM_MACRO_PREFIX; name = ""
      klen = length(CALLFORM_MACRO_SELF_TOKEN)
      if (klen > 0 && substr(text, pos, klen) == CALLFORM_MACRO_SELF_TOKEN) {
        name = CALLFORM_MACRO_SELF_TOKEN; pos += klen }
      while (pos <= length(text) && substr(text, pos, 1) ~ SYM_NAME_CALL) {
        name = name substr(text, pos, 1); pos++ }
      if (substr(text, pos, 1) != "(") { result = result lit name; continue } }
    else {
      bpos = 0
      for (p = pos; p <= length(text) && bpos == 0; p++) {
        blen = 0
        for (kp in CALLFORM_MACRO_NAMES) {
          klen = length(kp)
          if (substr(text, p, klen) == kp && substr(text, p+klen, 1) == "(" &&
              klen > blen) {
            blen = klen; bname = kp } }
        if (blen > 0) { bpos = p } }
      if (bpos == 0) { result = result substr(text, pos); break }
      result = result substr(text, pos, bpos - pos)
      pos = bpos + length(bname); lit = ""; name = bname }
    if (pos > length(text)) { result = result lit name; break }
    pos++
    astart = pos; paren = 1
    while (pos <= length(text) && paren > 0) {
      c = substr(text, pos, 1)
      if (c == "(") paren++; else if (c == ")") paren--
      pos++ }
    if (paren > 0) { result = result lit name "(" substr(text, astart); break }
    args = substr(text, astart, pos - astart - 1)
    result = result "$(call " name "," lower_callforms__macro(args) ")" }
  return result }

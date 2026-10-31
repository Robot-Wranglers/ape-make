# The grammar symbols every amk awk program shares, read as string patterns:
# the identifier class, the callform class with its predicate and bang
# suffixes, the path class, and the define opener; set in a BEGIN block that loads first.
BEGIN {
  SYM_NAME      = "[A-Za-z0-9._!-]"
  SYM_NAME_CALL = "[A-Za-z0-9._?!-]"
  SYM_PATH      = "[A-Za-z0-9._/-]"
  SYM_DEFINE    = "^define"
}

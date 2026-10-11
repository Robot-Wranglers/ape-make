# The call channel from a recipe; on PATH under amk, so a recipe sources it by name.

# One request to the running make, input lines after it; the reply lines on stdout, the status returned.
amk.call() {
  local st n line
  printf '%s\n' "$1" >&"$AMK_CALL" || return 2
  if [ $# -gt 1 ]; then
    printf '%s\n' "${@:2}" >&"$AMK_CALL" || return 2
  fi
  read -r st n <&"$AMK_REPLY" || return 2
  while [ "$n" -gt 0 ]; do
    IFS= read -r line <&"$AMK_REPLY"
    printf '%s\n' "$line"
    n=$((n - 1))
  done
  return "$st"
}

# The arguments as words on a request line, each double-quoted with backslash, quote and newline escaped, so any value survives the split and the line framing.
amk.words() {
  local a
  for a ; do a=${a//\\/\\\\} ; a=${a//\"/\\\"} ; a=${a//$'\n'/\\n} ; printf '"%s" ' "$a" ; done
}

# One operation on a workspace: the operation, the namespace, the engine's options, then the program after a double dash; a bound value is quoted for the line, and the program rides raw with its newlines made spaces.
amk.ns() {
  local line="$1 $2"
  shift 2
  while [ $# -gt 0 ] && [ "$1" != -- ]; do
    case "$1" in
      --arg|--argjson|--rawfile|--slurpfile) line="$line $1 $2 $(amk.words "$3")" ; shift 3 ;;
      *) line="$line $1" ; shift ;;
    esac
  done
  [ $# -eq 0 ] || shift
  line="$line $*"
  amk.call "${line//$'\n'/ }"
}

# A pipeline stage: the engine, its options, then the program, over stdin in the make process; the program rides raw as the rest of the line.
amk.filter() {
  local engine=$1 ; shift
  local -a lines
  mapfile -t lines
  amk.call "filter $engine ${#lines[@]} $(amk.words "${@:1:$#-1}")${@: -1}" "${lines[@]}"
}

# The same stage through jq.
jq.pipe() {
  amk.filter jq "$@"
}

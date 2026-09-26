# The call channel from a recipe; on PATH under amk, so a recipe sources it by name.

# One tagged request to the running make, input lines after it; the reply lines on stdout, the status returned.
amk.call() {
  local tag=$BASHPID st n line
  printf '@%s %s\n' "$tag" "$1" >&"$AMK_CALL" || return 2
  if [ $# -gt 1 ]; then
    printf '%s\n' "${@:2}" >&"$AMK_CALL" || return 2
  fi
  read -r line <&"$AMK_REPLY" || return 2
  {
    read -r st n || return 2
    while [ "$n" -gt 0 ]; do
      IFS= read -r line
      printf '%s\n' "$line"
      n=$((n - 1))
    done
  } < "$AMK_REPLY_DIR/$tag"
  return "$st"
}

# A pipeline stage: the jq program, with the tool's options, over stdin in the make process.
jq.pipe() {
  local -a lines
  mapfile -t lines
  amk.call "filter ${#lines[@]} $*" "${lines[@]}"
}

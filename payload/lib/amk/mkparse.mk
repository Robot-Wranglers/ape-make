#
# payload/lib/amk/mkparse.mk:
#  mkparse, the Makefile-to-JSON engine behind mk.parse.  Defines only: the
#  awk programs that scan `make -pRrq` output and doc blocks into JSONL, the
#  jq programs that reshape, filter, and render it, and the POSIX sh
#  dispatcher that ties them to a container-style CLI.  It reads only make
#  builtins and itself; the caller supplies the runner, which bakes these
#  programs into the dispatcher's environment.
#
##░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
## BEGIN: native mk.parse :: The awk+jq Makefile-to-JSON engine (the `mkparse` seam)
##
## awk extracts scalar-only JSONL (docs joined by a 0x1f sentinel); jq reshapes,
## derives booleans, filters, and renders.  The shallow path reuses
## `.awk.completion.scan -v emit=jsonl` (one scanner for help + completion).
##░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
define _mkp.awk.jesc
  function jrep(s, fs, rep,   n, p, i, r) {
    n = split(s, p, fs); r = p[1]
    for (i = 2; i <= n; i++) r = r rep p[i]
    return r }
  function jesc(s) {
    s = jrep(s, "\\\\", "\\\\"); s = jrep(s, "\"", "\\\"")
    s = jrep(s, "\t", "\\t"); s = jrep(s, "\r", "\\r")
    s = jrep(s, SEP, "\\u001f")
    return "\"" s "\"" }
  BEGIN{ SEP=sprintf("%c",31) }
endef

# full parse of `make -pRrq` output.  Paragraph mode (RS="", FS="\n") so $1 is the
# stanza header; both rule sections are scanned (`# Implicit Rules` = pattern
# targets, `# Files` = explicit).
define _mkp.awk.full
  BEGIN{ RS=""; FS="\n"; Q=sprintf("%c",39) }
  /(^|\n)# Implicit Rules(\n|$)/          { infiles=1; next }
  /(^|\n)# Files(\n|$)/                   { infiles=1; next }
  /(^|\n)# Finished Make data base/       { infiles=0; next }
  !infiles { next }
  {
    line1=$1
    ci=index(line1,":"); if(ci==0) next
    head=substr(line1,1,ci-1)
    if(substr(line1,ci+1,1)=="=" || substr(line1,ci+1,1)==":") next
    if(head !~ /^[A-Za-z0-9._%\/!][A-Za-z0-9._%\/! -]*$/) next
    prereqs=substr(line1,ci+1); gsub(/^[ \t]+/,"",prereqs); gsub(/[ \t]+$/,"",prereqs)
    file=""; lineno=0; typ="file"; docs=""; hasrecipe=0
    for(i=2;i<=NF;i++){ l=$i
      if(l ~ /^#  recipe to execute \(from /){
        hasrecipe=1
        if(match(l,/line [0-9]+/)){ ln=substr(l,RSTART); sub(/line /,"",ln); lineno=ln+0 }
        q1=index(l,Q); if(q1>0){ r=substr(l,q1+1); q2=index(r,Q); if(q2>0) file=substr(r,1,q2-1) }
        continue }
      if(l ~ /^#  Phony target/){ typ="phony"; continue }
      if(substr(l,1,3)=="\t@#"){ d=substr(l,4); sub(/^ /,"",d); docs=(docs==""?d:docs SEP d) }
    }
    if(!hasrecipe && prereqs=="" && typ!="phony") next
    n=split(head,toks,/[ \t]+/)
    for(i=1;i<=n;i++){ t=toks[i]; if(t=="") continue
      printf "{\"name\":%s,\"file\":%s,\"lineno\":%d,\"header\":%s,\"prereqs\":%s,\"docs\":%s,\"type\":%s}\n", jesc(t), jesc(file), lineno, jesc(line1), jesc(prereqs), jesc(docs), jesc(typ) }
  }
endef

define _mkp.awk.cblocks
  /^## BEGIN:/ {
    s=$0; sub(/^## BEGIN:[ \t]*/,"",s)
    ci=index(s,":")
    if(ci>0){ label=substr(s,1,ci-1); tail=substr(s,ci+1) } else { label=s; tail="" }
    gsub(/^[ \t]+|[ \t]+$/,"",label); gsub(/^[ \t]+|[ \t]+$/,"",tail)
    inblk=1
    if(tail!="") printf "{\"label\":%s,\"text\":%s}\n", jesc(label), jesc(tail)
    next }
  /^## END:/ { inblk=0; next }
  inblk && /^##/ {
    t=$0; sub(/^##[ ]?/,"",t)
    printf "{\"label\":%s,\"text\":%s}\n", jesc(label), jesc(t); next }
endef

# JSONL array -> object|names|markdown.  Flag args are "" when unset.  `private`
# is a leading `.` only (matches the container, keeps `_`).  alias/primary group
# a multi-target line (same file,lineno); primary = shortest name.
define _mkp.jq.targets
  def bn: (. // "") | split("/") | last;
  def arr($s): if ($s // "")=="" then [] else ($s|split("\u001f")) end;
  map( . + {
    docs:    arr(.docs),
    prereqs: (if (.prereqs // "")=="" then [] else (.prereqs|split(" ")|map(select(length>0))) end),
    private: (.name|test("^[.]")),
    parametric: (.name|test("%")),
    local:   (((.file // "")|bn)==$localfile or ((.file // "")|test($hosted)))
  })
  | ( group_by([.file, .lineno])
      | map( if ((length > 1) and (.[0].file != "") and ((.[0].lineno // 0) != 0))
             then ( (sort_by([(.name|length), .name]) | .[0].name) as $prim
                    | map(.primary = $prim | .alias = (.name != $prim)) )
             else map(.primary = .name | .alias = false) end )
      | add )
  | map(select( ($public=="")      or (.private|not) ))
  | map(select( ($private=="")     or (.private) ))
  | map(select( ($local=="")       or (.local) ))
  | map(select( ($parametrics=="") or (.parametric) ))
  | map(select( ($prefix=="")      or (.name|startswith($prefix)) ))
  | map(select( ($target=="")      or (.name==$target) ))
  | if   $output=="names"    then .[].name
    elif $output=="markdown" then
      ( reduce .[] as $t ({seen:{},out:""};
          ($t.name|gsub("%";"")) as $k
          | if .seen[$k] then . else
              .seen[$k]=true
              | .out += "\n[**`\($k)`**](#\($k))\n\n"
                  + (($t.docs // [])|map(gsub("^\\s+|\\s+$";""))|join("\n"))
                  + "\n\n---------\n"
            end) | .out )
    else ( map({(.name): .}) | add // {} )
    end
endef

define _mkp.jq.cblocks
  ( group_by(.label) | map({key:.[0].label, value:[.[].text]}) | from_entries )
  | if $pattern=="" then . else with_entries(select(.key|test($pattern))) end
endef

define _mkp.jq.graph.edges
  [ to_entries[] as $t | $t.value.prereqs[]? | {from:$t.key, to:.} ]
endef

define _mkp.jq.graph.dot
  "digraph make {",
  ( to_entries[] as $t | $t.value.prereqs[]? | "  \"\($t.key)\" -> \"\(.)\";" ),
  "}"
endef

# `_mkp.dispatch` -- the container-compatible CLI front-end (POSIX sh).  Reads the
# awk/jq programs from MKP_* env (materialized by `_mkp.native`), so the engine
# lives once in the defines above.  Presents `targets`/`cblocks`/`graph` + the
# container flags; bare `--shallow` emits a JSON ARRAY of names (__targets__
# pipes `jq -r '.[]'`).  jq programs go via argv so a dockerized ${jq} still works.
define _mkp.dispatch
  set -eu
  sub=targets
  case "${1:-}" in targets|cblocks|graph) sub=$1; shift ;; esac
  PUBLIC= PRIVATE= LOCAL= SHALLOW= NAMES= PARAMETRICS= MARKDOWN= PREVIEW= DOT= PREFIX= PATTERN= TARGET= file=
  while [ $# -gt 0 ]; do case "$1" in
    --public) PUBLIC=1;; --private) PRIVATE=1;; --local) LOCAL=1;; --shallow) SHALLOW=1;;
    --names-only) NAMES=1;; --parametrics) PARAMETRICS=1;; --markdown) MARKDOWN=1;;
    --preview) PREVIEW=1; MARKDOWN=1;; --dot) DOT=1;;
    --prefix) shift; PREFIX="${1:-}";; --prefix=*) PREFIX="${1#--prefix=}";;
    --pattern) shift; PATTERN="${1:-}";; --pattern=*) PATTERN="${1#--pattern=}";;
    --target) shift; TARGET="${1:-}";; --target=*) TARGET="${1#--target=}";;
    --*) : ;;
    *) file="$1";;
  esac; shift; done
  file="${file:-${MAKEFILE:-Makefile}}"
  [ -f "$file" ] || { printf 'mk.parse: no such file: %s\n' "$file" >&2; exit 2; }
  base=$(basename "$file"); HOSTED='\.tmp\.hosted\.'
  jsonl(){ if [ -n "$SHALLOW" ]; then awk -v emit=jsonl "$MKP_SCAN" "$file"
    else { env -u MAKEFILE -u __file__ -u MAKEFILE_LIST MAKEFLAGS= LC_ALL=C make -pRrq -f "$file" : 2>/dev/null || true; } | awk "$MKP_JESC
  $MKP_FULL"; fi; }
  tjq(){ $MKP_JQ -rs --arg prefix "$PREFIX" --arg localfile "$base" --arg hosted "$HOSTED" \
    --arg target "$TARGET" --arg output "$1" --arg public "$PUBLIC" --arg private "$PRIVATE" \
    --arg local "$LOCAL" --arg parametrics "$PARAMETRICS" "$MKP_JQ_TARGETS"; }
  preview(){ if [ -n "$PREVIEW" ] && command -v glow >/dev/null 2>&1; then glow -; else cat; fi; }
  case "$sub" in
  targets)
    if   [ -n "$NAMES" ];    then jsonl | tjq names
    elif [ -n "$MARKDOWN" ]; then jsonl | tjq markdown | preview
    elif [ -n "$SHALLOW" ];  then PUBLIC=1; jsonl | tjq names | $MKP_JQ -Rs 'split("\n")|map(select(length>0))'
    else jsonl | tjq json; fi ;;
  cblocks) awk "$MKP_JESC
  $MKP_CBLOCKS" "$file" | $MKP_JQ -s --arg pattern "$PATTERN" "$MKP_JQ_CBLOCKS" ;;
  graph) obj=$(jsonl | tjq json)
    if [ -n "$DOT" ]; then printf '%s' "$obj" | $MKP_JQ -r "$MKP_JQ_GDOT"
    else printf '%s' "$obj" | $MKP_JQ "$MKP_JQ_GEDGES"; fi ;;
  *) printf 'mk.parse: unknown subcommand: %s\n' "$sub" >&2; exit 1 ;;
  esac
endef

/* The trilog guest: a Prolog context with amk's handle registered as foreign '$amk_' builtins under the prelude's amk_ predicates, as a one-shot chunk and as a kept state. */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "trilog.h"
#include "amk_guest.h"

#define TRILOG_BOOT "/zip/lib/trilog/boot/core.pl"
#define TRILOG_LIBS "ensure_loaded(library(apply)), ensure_loaded(library(between)), ensure_loaded(library(dcgs)), ensure_loaded(library(charsio))"

/* The name the Prolog side opens to read the chunk being run, which no file on disk answers. */
#define TRILOG_CHUNK "amk-chunk:"

#define TRILOG_NO_DB "no make database, running outside a makefile"

/* The handle's Prolog side: the amk_ builtins over the foreign ones, json_write/1, the chunk runner that answers each ?- query as JSON lines, the workspace get, load and dump over a sealed base of predicates, and the export and lifted-function queries. */
static const char *trilog_amk_prelude =
  "'$amk_text'(T, _, Who) :- var(T), !, throw(error(instantiation_error, Who)).\n"
  "'$amk_text'(T, T, _) :- atom(T), !.\n"
  "'$amk_text'(T, A, _) :- number(T), !, number_codes(T, Cs), atom_codes(A, Cs).\n"
  "'$amk_text'(T, A, _) :- '$amk_chars'(T), !, atom_chars(A, T).\n"
  "'$amk_text'(T, A, _) :- '$amk_codes'(T), !, atom_codes(A, T).\n"
  "'$amk_text'(T, _, Who) :- throw(error(type_error(atomic, T), Who)).\n"
  "'$amk_chars'([C|Cs]) :- atom(C), atom_length(C, 1), ( Cs == [] -> true ; '$amk_chars'(Cs) ).\n"
  "'$amk_codes'([C|Cs]) :- integer(C), C >= 0, ( Cs == [] -> true ; '$amk_codes'(Cs) ).\n"
  "'$amk_as'(Goal, Who) :- catch(Goal, error(F, _), throw(error(F, Who))).\n"
  "amk_expand(T, V) :- '$amk_text'(T, A, amk_expand/2), '$amk_as'('$amk_expand'(A, V), amk_expand/2).\n"
  "amk_eval(T) :- '$amk_text'(T, A, amk_eval/1), '$amk_as'('$amk_eval'(A), amk_eval/1).\n"
  "amk_var(N, V) :- '$amk_text'(N, A, amk_var/2), '$amk_as'('$amk_var'(A, V), amk_var/2).\n"
  "amk_var_set(N, V) :- '$amk_text'(N, A, amk_var_set/2), '$amk_text'(V, B, amk_var_set/2),\n"
  "  '$amk_as'('$amk_var_set'(A, B), amk_var_set/2).\n"
  "amk_goal(G, O) :- '$amk_text'(G, A, amk_goal/2), '$amk_as'('$amk_goal'(A, O), amk_goal/2).\n"
  "amk_goal_spawn(G, P) :- '$amk_text'(G, A, amk_goal_spawn/2), '$amk_as'('$amk_goal_spawn'(A, P), amk_goal_spawn/2).\n"
  "amk_job_wait(P, O) :- '$amk_text'(P, A, amk_job_wait/2), '$amk_as'('$amk_job_wait'(A, O, _), amk_job_wait/2).\n"
  "amk_job_wait(P, O, M) :- '$amk_text'(P, A, amk_job_wait/3), '$amk_as'('$amk_job_wait'(A, O, M), amk_job_wait/3).\n"
  "amk_job_stop(P) :- '$amk_text'(P, A, amk_job_stop/1), '$amk_as'('$amk_job_stop'(A), amk_job_stop/1).\n"
  "amk_send(T) :- '$amk_text'(T, A, amk_send/1), '$amk_as'('$amk_send'(A), amk_send/1).\n"
  "amk_call(N, Args, V) :- '$amk_text'(N, A, amk_call/3), '$amk_texts'(Args, Ts, amk_call/3),\n"
  "  length(Ts, Count), '$amk_join'(Ts, 31, Joined), '$amk_as'('$amk_call'(A, Count, Joined, V), amk_call/3).\n"
  "amk_job_any(Ps, P, O) :- '$amk_pids'(Ps, J, amk_job_any/3), '$amk_as'('$amk_job_any'(J, P, O), amk_job_any/3).\n"
  "amk_job_all(Ps, Os) :- '$amk_pids'(Ps, J, amk_job_all/2), '$amk_as'('$amk_job_all'(J, A), amk_job_all/2),\n"
  "  atom_codes(A, Cs), '$amk_words'(Cs, Os).\n"
  "'$amk_texts'(L, _, Who) :- var(L), !, throw(error(instantiation_error, Who)).\n"
  "'$amk_texts'([], [], _) :- !.\n"
  "'$amk_texts'([X|Xs], [T|Ts], Who) :- !, '$amk_text'(X, T, Who), '$amk_texts'(Xs, Ts, Who).\n"
  "'$amk_texts'(L, _, Who) :- throw(error(type_error(list, L), Who)).\n"
  "'$amk_pids'(L, _, Who) :- var(L), !, throw(error(instantiation_error, Who)).\n"
  "'$amk_pids'([], '', _) :- !.\n"
  "'$amk_pids'([P|Ps], J, Who) :- !, ( integer(P) -> true ; throw(error(type_error(integer, P), Who)) ),\n"
  "  '$amk_pids'(Ps, Rest, Who), number_codes(P, Cs), atom_codes(A, Cs),\n"
  "  ( Rest == '' -> J = A ; '$amk_join'([A, Rest], 32, J) ).\n"
  "'$amk_pids'(L, _, Who) :- throw(error(type_error(list, L), Who)).\n"
  "'$amk_join'([], _, '').\n"
  "'$amk_join'([A|As], Sep, J) :- atom_codes(A, Cs), '$amk_join_rest'(As, Sep, Rest), append(Cs, Rest, All), atom_codes(J, All).\n"
  "'$amk_join_rest'([], _, []).\n"
  "'$amk_join_rest'([A|As], Sep, [Sep|All]) :- atom_codes(A, Cs), '$amk_join_rest'(As, Sep, Rest), append(Cs, Rest, All).\n"
  "'$amk_words'([], []) :- !.\n"
  "'$amk_words'([32|Cs], Ws) :- !, '$amk_words'(Cs, Ws).\n"
  "'$amk_words'(Cs, [W|Ws]) :- '$amk_word'(Cs, Wc, Rest), atom_codes(W, Wc), '$amk_words'(Rest, Ws).\n"
  "'$amk_word'([], [], []).\n"
  "'$amk_word'([32|Cs], [], [32|Cs]) :- !.\n"
  "'$amk_word'([C|Cs], [C|Wc], Rest) :- '$amk_word'(Cs, Wc, Rest).\n"
  "json_write(T) :- '$amk_json'(T).\n"
  "'$amk_json'(T) :- var(T), !, write(null).\n"
  "'$amk_json'([]) :- !, write('[]').\n"
  "'$amk_json'(T) :- number(T), !, write(T).\n"
  "'$amk_json'(T) :- atom(T), !, '$amk_json_str'(T).\n"
  "'$amk_json'(T) :- is_list(T), !, write('['), '$amk_json_items'(T), write(']').\n"
  "'$amk_json'(T) :- T =.. [F|As], write('{\"functor\":'), '$amk_json_str'(F),\n"
  "  write(',\"args\":['), '$amk_json_items'(As), write(']}').\n"
  "'$amk_json_items'([]).\n"
  "'$amk_json_items'([X|Xs]) :- '$amk_json'(X), '$amk_json_more'(Xs).\n"
  "'$amk_json_more'([]).\n"
  "'$amk_json_more'([X|Xs]) :- write(','), '$amk_json'(X), '$amk_json_more'(Xs).\n"
  "'$amk_json_str'(A) :- atom_codes(A, Cs), put_code(34), '$amk_json_codes'(Cs), put_code(34).\n"
  "'$amk_json_codes'([]).\n"
  "'$amk_json_codes'([C|Cs]) :- '$amk_json_code'(C), '$amk_json_codes'(Cs).\n"
  "'$amk_json_code'(C) :- '$amk_json_esc'(C, E), !, put_code(92), put_code(E).\n"
  "'$amk_json_code'(C) :- C < 32, !, put_code(92), put_code(0'u), put_code(0'0), put_code(0'0),\n"
  "  H is C >> 4, L is C /\\ 15, '$amk_hex'(H), '$amk_hex'(L).\n"
  "'$amk_json_code'(C) :- put_code(C).\n"
  "'$amk_json_esc'(34, 34). '$amk_json_esc'(92, 92). '$amk_json_esc'(10, 0'n). '$amk_json_esc'(9, 0't).\n"
  "'$amk_json_esc'(13, 0'r). '$amk_json_esc'(8, 0'b). '$amk_json_esc'(12, 0'f).\n"
  "'$amk_hex'(D) :- D < 10, !, C is 0'0 + D, put_code(C).\n"
  "'$amk_hex'(D) :- C is 0'a + D - 10, put_code(C).\n"
  "'$amk_report'(E) :- write(user_error, 'trilog: uncaught exception: '), writeq(user_error, E), nl(user_error).\n"
  "'$amk_chunk'(Path, Directives) :- open(Path, read, S),\n"
  "  catch('$amk_terms'(S, Directives, Ok), E, ('$amk_report'(E), Ok = false)), close(S), Ok == true.\n"
  "'$amk_terms'(S, Directives, Ok) :- read_term(S, T, [variable_names(Vs)]),\n"
  "  ( T == end_of_file -> Ok = true ; '$amk_term'(T, Vs, Directives) -> '$amk_terms'(S, Directives, Ok) ; Ok = false ).\n"
  "'$amk_term'((:- G), _, Directives) :- !, '$amk_directives'(Directives, (:- G)),\n"
  "  catch((once(G) -> true ; true), E, ('$amk_report'(E), fail)).\n"
  "'$amk_term'((?- G), Vs, Directives) :- !, '$amk_directives'(Directives, (?- G)),\n"
  "  catch(('$amk_answers'(G, Vs) -> true ; true), E, ('$amk_report'(E), fail)).\n"
  "'$amk_term'(C, _, _) :- assertz(C).\n"
  "'$amk_directives'(true, _) :- !.\n"
  "'$amk_directives'(_, T) :- write(user_error, 'trilog: load takes clauses, not directives: '),\n"
  "  writeq(user_error, T), nl(user_error), fail.\n"
  "'$amk_answers'(G, Vs) :- call(G), '$amk_answer'(Vs), fail.\n"
  "'$amk_answer'(Vs) :- write('{'), '$amk_bindings'(Vs, 0), write('}'), nl.\n"
  "'$amk_bindings'([], _).\n"
  "'$amk_bindings'([N=V|Vs], K) :-\n"
  "  ( atom_codes(N, [0'_|_]) -> K1 = K\n"
  "  ; ( K > 0 -> write(',') ; true ), '$amk_json_str'(N), write(':'), '$amk_json'(V), K1 is K + 1 ),\n"
  "  '$amk_bindings'(Vs, K1).\n"
  "'$amk_seal' :- findall(P, current_predicate(P), Ps), '$amk_seal'(Ps), assertz('$amk_base'('$amk_base'/1)).\n"
  "'$amk_seal'([]).\n"
  "'$amk_seal'([P|Ps]) :- assertz('$amk_base'(P)), '$amk_seal'(Ps).\n"
  "'$amk_user'(N/A) :- current_predicate(N/A), \\+ '$amk_base'(N/A).\n"
  "'$amk_snapshot'(Snap) :- findall(C, ('$amk_user'(N/A), functor(H, N, A), clause(H, B), C = (H :- B)), Snap).\n"
  "'$amk_wipe' :- findall(H, ('$amk_user'(N/A), functor(H, N, A)), Hs), '$amk_retract_all'(Hs).\n"
  "'$amk_retract_all'([]).\n"
  "'$amk_retract_all'([H|Hs]) :- retractall(H), '$amk_retract_all'(Hs).\n"
  "'$amk_restore'(Snap) :- '$amk_wipe', '$amk_assert_all'(Snap).\n"
  "'$amk_assert_all'([]).\n"
  "'$amk_assert_all'([C|Cs]) :- assertz(C), '$amk_assert_all'(Cs).\n"
  "'$amk_get'(Path) :- '$amk_snapshot'(Snap), ( '$amk_chunk'(Path, true) -> Ok = true ; Ok = false ),\n"
  "  '$amk_restore'(Snap), Ok == true.\n"
  "'$amk_load'(Path) :- open(Path, read, S), catch('$amk_clauses'(S, Cs), E, ('$amk_report'(E), Cs = error)),\n"
  "  close(S), Cs \\== error, '$amk_wipe', '$amk_assert_all'(Cs).\n"
  "'$amk_clauses'(S, Cs) :- read_term(S, T, []),\n"
  "  ( T == end_of_file -> Cs = [] ; ( T = (:- _) ; T = (?- _) ) -> '$amk_directives'(false, T)\n"
  "  ; Cs = [T|Rest], '$amk_clauses'(S, Rest) ).\n"
  "'$amk_dump' :- '$amk_snapshot'(Snap), '$amk_dump'(Snap).\n"
  "'$amk_dump'([]).\n"
  "'$amk_dump'([C|Cs]) :- \\+ \\+ ( numbervars(C, 0, _), '$amk_clause'(C) ), '$amk_dump'(Cs).\n"
  "'$amk_clause'((H :- true)) :- !, '$amk_q'(H), write('.'), nl.\n"
  "'$amk_clause'((H :- B)) :- '$amk_q'(H), write(' :- '), '$amk_body'(B), write('.'), nl.\n"
  "'$amk_body'((A, B)) :- !, '$amk_q'(A), write(', '), '$amk_body'(B).\n"
  "'$amk_body'(G) :- '$amk_q'(G).\n"
  "'$amk_q'(T) :- write_term(T, [quoted(true), numbervars(true)]).\n"
  "'$amk_export'(N, V) :- current_predicate(amk_export/2), catch(amk_export(N0, V0), _, fail),\n"
  "  catch(('$amk_text'(N0, N, amk_export/2), '$amk_text'(V0, V, amk_export/2)), _, fail).\n"
  "'$amk_function'(F) :- current_predicate(amk_function/1), catch(amk_function(F0), _, fail),\n"
  "  catch('$amk_text'(F0, F, amk_function/1), _, fail).\n"
  "'$amk_fn'(Name, Args, R) :- append(Args, [R0], All), G =.. [Name|All],\n"
  "  ( once(G), catch('$amk_text'(R0, R1, Name), _, fail) -> R = R1 ; R = '' ).\n";

/* A stream: a stdio file, or the text of the chunk being run. */
struct trilog_stream
{
  FILE *file;
  const char *text;
  size_t pos, len;
};

static struct trilog_stream trilog_in, trilog_out, trilog_err;
static const char *trilog_chunk_text;

static void *
trilog_io_open (void *ud, const char *path, const char *mode)
{
  struct trilog_stream *s;
  FILE *f = NULL;
  (void) ud;
  if (strcmp (path, TRILOG_CHUNK) != 0 && (f = fopen (path, mode)) == NULL)
    return NULL;
  if (f == NULL && trilog_chunk_text == NULL)
    return NULL;
  s = calloc (1, sizeof *s);
  if (s == NULL)
    {
      if (f)
        fclose (f);
      return NULL;
    }
  s->file = f;
  if (f == NULL)
    {
      s->text = trilog_chunk_text;
      s->len = strlen (trilog_chunk_text);
    }
  return s;
}

static long
trilog_io_read (void *ud, void *handle, char *buf, size_t n)
{
  struct trilog_stream *s = handle;
  (void) ud;
  if (s->file)
    return (long) fread (buf, 1, n, s->file);
  if (n > s->len - s->pos)
    n = s->len - s->pos;
  memcpy (buf, s->text + s->pos, n);
  s->pos += n;
  return (long) n;
}

static long
trilog_io_write (void *ud, void *handle, const char *buf, size_t n)
{
  struct trilog_stream *s = handle;
  (void) ud;
  return s->file ? (long) fwrite (buf, 1, n, s->file) : -1;
}

static void
trilog_io_close (void *ud, void *handle)
{
  struct trilog_stream *s = handle;
  (void) ud;
  if (s == &trilog_in || s == &trilog_out || s == &trilog_err)
    return;
  if (s->file)
    fclose (s->file);
  free (s);
}

static void
trilog_io_flush (void *ud, void *handle)
{
  struct trilog_stream *s = handle;
  (void) ud;
  if (s->file)
    fflush (s->file);
}

/* The text an output slot answers: kept here until the next call, since the engine copies it only after the call returns. */
static const char *
trilog_hold (int slot, const char *text)
{
  static char *held[2];
  free (held[slot]);
  held[slot] = strdup (text ? text : "");
  return held[slot];
}

/* An amk_error(Why) raised from the foreign call, Why a quoted atom. */
static bool
trilog_raise (trilog_t *t, const char *why)
{
  char buf[1024];
  size_t n = 0;
  const char *p;
  for (p = why ? why : "failed"; *p && n + 3 < sizeof buf; p++)
    {
      if (*p == '\'' || *p == '\\')
        buf[n++] = '\\';
      buf[n++] = *p == '\n' ? ' ' : *p;
    }
  buf[n] = '\0';
  return trilog_error (t, "amk_error('%s')", buf);
}

/* A make call's answer as the output atom, or the call's error raised; the text is make's, freed here. */
static bool
trilog_answer (trilog_t *t, trilog_value_t *out, char *text, const char *why)
{
  if (text == NULL)
    return trilog_raise (t, why);
  out[0].a = trilog_hold (0, text);
  gmk_free (text);
  return true;
}

/* A make function called with one argument, answering its text, the caller's to free with gmk_free. */
static char *
trilog_call1 (const char *fn, const char *arg, const char **why)
{
  if (!amk_has_db ())
    {
      *why = TRILOG_NO_DB;
      return NULL;
    }
  return amk_call (fn, arg ? 1 : 0, &arg, why);
}

/* A field of a job record: the text after "key": up to the closing quote, escapes undone, or for a bare value the next comma. */
static const char *
trilog_field (const char *record, const char *key, char *buf, size_t size)
{
  char pat[32];
  const char *p;
  size_t n = 0;
  int quoted;
  snprintf (pat, sizeof pat, "\"%s\": ", key);
  p = record ? strstr (record, pat) : NULL;
  if (p == NULL)
    return NULL;
  p += strlen (pat);
  quoted = *p == '"';
  p += quoted;
  while (*p && (quoted ? *p != '"' : *p != ',' && *p != '}') && n + 1 < size)
    {
      if (quoted && *p == '\\' && p[1])
        {
          p++;
          buf[n++] = *p == 'n' ? '\n' : *p == 't' ? '\t' : *p;
          p++;
          continue;
        }
      buf[n++] = *p++;
    }
  buf[n] = '\0';
  return buf;
}

/* '$amk_expand'(+Text, -Value) */
static bool
trilog_amk_expand (trilog_t *t, void *ud, const trilog_value_t *in, trilog_value_t *out)
{
  (void) ud;
  if (!amk_has_db ())
    return trilog_raise (t, TRILOG_NO_DB);
  return trilog_answer (t, out, gmk_expand (in[0].a), "expand failed");
}

/* '$amk_eval'(+Text) */
static bool
trilog_amk_eval (trilog_t *t, void *ud, const trilog_value_t *in, trilog_value_t *out)
{
  (void) ud;
  (void) out;
  if (!amk_has_db ())
    return trilog_raise (t, TRILOG_NO_DB);
  amk_eval (in[0].a);
  return true;
}

/* '$amk_call'(+Name, +Count, +Joined, -Value): Joined is Count arguments separated by the unit separator. */
static bool
trilog_amk_call (trilog_t *t, void *ud, const trilog_value_t *in, trilog_value_t *out)
{
  const char *why = NULL;
  char *copy, *p, *s, **vals;
  unsigned int n = (unsigned int) in[1].i, i = 0;
  (void) ud;
  if (!amk_has_db ())
    return trilog_raise (t, TRILOG_NO_DB);
  copy = strdup (in[2].a);
  vals = calloc (n ? n : 1, sizeof *vals);
  for (p = copy; n && i < n; i++)
    {
      vals[i] = p;
      p = strchr (p, '\x1f');
      if (p == NULL)
        break;
      *p++ = '\0';
    }
  s = amk_call_kind (AMK_AS_ANY, in[0].a, n, (const char **) vals, &why);
  free (vals);
  free (copy);
  return trilog_answer (t, out, s, why);
}

/* '$amk_var'(+Name, -Value): fails when make has never seen the name. */
static bool
trilog_amk_var (trilog_t *t, void *ud, const trilog_value_t *in, trilog_value_t *out)
{
  char *s;
  (void) ud;
  if (!amk_has_db ())
    return trilog_raise (t, TRILOG_NO_DB);
  s = amk_var_get (in[0].a);
  return s != NULL && trilog_answer (t, out, s, NULL);
}

/* '$amk_var_set'(+Name, +Value) */
static bool
trilog_amk_var_set (trilog_t *t, void *ud, const trilog_value_t *in, trilog_value_t *out)
{
  (void) ud;
  (void) out;
  if (!amk_has_db ())
    return trilog_raise (t, TRILOG_NO_DB);
  amk_var_set (in[0].a, in[1].a);
  return true;
}

/* '$amk_goal'(+Goal, -Outcome): the goal run to its end, once. */
static bool
trilog_amk_goal (trilog_t *t, void *ud, const trilog_value_t *in, trilog_value_t *out)
{
  const char *why = NULL;
  char *value = trilog_call1 ("amk.goal.maybe", in[0].a, &why);
  (void) ud;
  if (value == NULL)
    return trilog_raise (t, why);
  gmk_free (value);
  return trilog_answer (t, out, amk_var_get ("amk.goal.maybe.status"), NULL);
}

/* '$amk_goal_spawn'(+Goal, -Pid) */
static bool
trilog_amk_goal_spawn (trilog_t *t, void *ud, const trilog_value_t *in, trilog_value_t *out)
{
  const char *why = NULL;
  char *pid = trilog_call1 ("amk.goal.spawn", in[0].a, &why);
  (void) ud;
  if (pid == NULL || *pid == '\0')
    {
      if (pid)
        gmk_free (pid);
      return trilog_raise (t, why ? why : "amk.goal.spawn answered no pid; load dsys/job");
    }
  out[0].i = atoll (pid);
  gmk_free (pid);
  return true;
}

/* '$amk_job_wait'(+Pid, -Outcome, -Mail): Mail is what the job sent, empty when it sent nothing. */
static bool
trilog_amk_job_wait (trilog_t *t, void *ud, const trilog_value_t *in, trilog_value_t *out)
{
  static char mail[16384];
  char status[32];
  const char *why = NULL;
  char *record = trilog_call1 ("amk.job.wait", in[0].a, &why);
  bool ok;
  (void) ud;
  if (record == NULL)
    return trilog_raise (t, why);
  ok = trilog_field (record, "status", status, sizeof status) != NULL;
  if (trilog_field (record, "mail", mail, sizeof mail) == NULL)
    mail[0] = '\0';
  gmk_free (record);
  if (!ok)
    return trilog_raise (t, "no record for the pid");
  out[0].a = trilog_hold (0, status);
  out[1].a = trilog_hold (1, mail);
  return true;
}

/* '$amk_job_any'(+Pids, -Pid, -Outcome): the first of the space-joined set to finish. */
static bool
trilog_amk_job_any (trilog_t *t, void *ud, const trilog_value_t *in, trilog_value_t *out)
{
  char pid[32], status[32];
  const char *why = NULL;
  char *record = trilog_call1 ("amk.job.any", in[0].a, &why);
  bool ok;
  (void) ud;
  if (record == NULL)
    return trilog_raise (t, why);
  ok = trilog_field (record, "pid", pid, sizeof pid) != NULL
       && trilog_field (record, "status", status, sizeof status) != NULL;
  gmk_free (record);
  if (!ok)
    return false;
  out[0].i = atoll (pid);
  out[1].a = trilog_hold (0, status);
  return true;
}

/* '$amk_job_all'(+Pids, -Outcomes): every job of the space-joined set waited for, the outcomes space-joined in its order. */
static bool
trilog_amk_job_all (trilog_t *t, void *ud, const trilog_value_t *in, trilog_value_t *out)
{
  char status[32], *joined;
  const char *why = NULL, *p;
  char *records = trilog_call1 ("amk.job.all", in[0].a, &why);
  size_t len = 0;
  (void) ud;
  if (records == NULL)
    return trilog_raise (t, why);
  joined = malloc (strlen (records) + 1);
  joined[0] = '\0';
  for (p = strchr (records, '{'); p != NULL; p = strchr (p + 1, '{'))
    if (trilog_field (p, "status", status, sizeof status) != NULL)
      len += (size_t) sprintf (joined + len, "%s%s", len ? " " : "", status);
  gmk_free (records);
  out[0].a = trilog_hold (0, joined);
  free (joined);
  return true;
}

/* '$amk_job_stop'(+Pid): fails for a pid that is not a live job. */
static bool
trilog_amk_job_stop (trilog_t *t, void *ud, const trilog_value_t *in, trilog_value_t *out)
{
  const char *why = NULL;
  char *r = trilog_call1 ("amk.job.stop", in[0].a, &why);
  bool live;
  (void) ud;
  (void) out;
  if (r == NULL)
    return trilog_raise (t, why);
  live = *r != '\0';
  gmk_free (r);
  return live;
}

/* '$amk_send'(+Text): the text written to the parent's mail, from inside a job; fails outside one. */
static bool
trilog_amk_send (trilog_t *t, void *ud, const trilog_value_t *in, trilog_value_t *out)
{
  (void) t;
  (void) ud;
  (void) out;
  return amk_mail_send (in[0].a, strlen (in[0].a)) == 0;
}

/* The context a query is running in, and the process running it: a job forked from inside that query inherits a copy the engine refuses to start another query in. */
static trilog_t *trilog_busy;
static pid_t trilog_busy_pid;

static trilog_t *trilog_state_open (void);

/* The context to query: the one given, or in a child forked while it was busy, a fresh one of that child's own. */
static trilog_t *
trilog_usable (trilog_t *t)
{
  static trilog_t *fresh;
  static pid_t fresh_pid;
  if (t != trilog_busy || trilog_busy_pid == getpid ())
    return t;
  if (fresh_pid != getpid ())
    {
      trilog_busy = NULL;
      fresh = trilog_state_open ();
      fresh_pid = getpid ();
    }
  return fresh ? fresh : t;
}

/* A query with its context marked busy while it runs. */
static trilog_status_t
trilog_ask (trilog_t *t, const char *goal, trilog_solution_fn fn, void *ud)
{
  trilog_t *prev = trilog_busy;
  pid_t prev_pid = trilog_busy_pid;
  trilog_status_t st;
  trilog_busy = t;
  trilog_busy_pid = getpid ();
  st = trilog_query (t, goal, fn, ud);
  trilog_busy = prev;
  trilog_busy_pid = prev_pid;
  return st;
}

/* Stops a query after its first solution. */
static bool
trilog_once (trilog_t *t, void *ud, bool has_more)
{
  (void) t;
  (void) ud;
  (void) has_more;
  return false;
}

/* A goal run to its first solution: 0 when it succeeded, 1 when it failed or raised, the raise reported on stderr. */
static int
trilog_run (trilog_t *t, const char *goal)
{
  trilog_status_t st;
  t = trilog_usable (t);
  st = trilog_ask (t, goal, trilog_once, NULL);
  if (st == TRILOG_ERROR)
    {
      char buf[1024];
      trilog_term_t e = trilog_error_term (t);
      if (trilog_term_type (t, e) != TRILOG_INVALID)
        trilog_format (t, e, TRILOG_FORMAT_QUOTED, buf, sizeof buf);
      else
        strcpy (buf, "an error");
      fprintf (stderr, "trilog: uncaught exception: %s\n", buf);
    }
  fflush (stdout);
  fflush (stderr);
  return st == TRILOG_TRUE ? 0 : 1;
}

/* The goal over the chunk's text, which the Prolog side reads as a stream. */
static int
trilog_run_text (trilog_t *t, const char *goal, const char *text)
{
  int rc;
  trilog_chunk_text = text;
  rc = trilog_run (t, goal);
  trilog_chunk_text = NULL;
  return rc;
}

/* A context with the core, the libraries and the Prolog side loaded, the foreign builtins registered and the base sealed, or null. */
static trilog_t *
trilog_state_open (void)
{
  static trilog_io_t io;
  trilog_t *t;
  trilog_in.file = stdin;
  trilog_out.file = stdout;
  trilog_err.file = stderr;
  io = (trilog_io_t) { .open = trilog_io_open, .read = trilog_io_read, .write = trilog_io_write,
                       .close = trilog_io_close, .flush = trilog_io_flush,
                       .in = &trilog_in, .out = &trilog_out, .err = &trilog_err };
  t = trilog_new (&(trilog_config_t) { .boot_path = TRILOG_BOOT, .io = &io });
  if (t == NULL)
    {
      fprintf (stderr, "trilog: cannot boot from %s\n", TRILOG_BOOT);
      return NULL;
    }
  trilog_register (t, "$amk_expand", "a>a", trilog_amk_expand, NULL);
  trilog_register (t, "$amk_eval", "a", trilog_amk_eval, NULL);
  trilog_register (t, "$amk_call", "aia>a", trilog_amk_call, NULL);
  trilog_register (t, "$amk_var", "a>a", trilog_amk_var, NULL);
  trilog_register (t, "$amk_var_set", "aa", trilog_amk_var_set, NULL);
  trilog_register (t, "$amk_goal", "a>a", trilog_amk_goal, NULL);
  trilog_register (t, "$amk_goal_spawn", "a>i", trilog_amk_goal_spawn, NULL);
  trilog_register (t, "$amk_job_wait", "a>aa", trilog_amk_job_wait, NULL);
  trilog_register (t, "$amk_job_any", "a>ia", trilog_amk_job_any, NULL);
  trilog_register (t, "$amk_job_all", "a>a", trilog_amk_job_all, NULL);
  trilog_register (t, "$amk_job_stop", "a", trilog_amk_job_stop, NULL);
  trilog_register (t, "$amk_send", "a", trilog_amk_send, NULL);
  if (trilog_run (t, TRILOG_LIBS) != 0 || trilog_load_string (t, trilog_amk_prelude) != TRILOG_TRUE
      || trilog_run (t, "'$amk_seal'") != 0)
    {
      fprintf (stderr, "trilog: cannot load the amk prelude\n");
      trilog_free (t);
      return NULL;
    }
  return t;
}

/* argv[1] is Prolog source text rather than a command line; whatever its directives print is the result. */
__attribute__ ((visibility ("default"))) int
trilog_run_main (int argc, char **argv)
{
  trilog_t *t;
  int rc;
  if (argc < 2 || argv[1] == NULL)
    {
      fprintf (stderr, "trilog: no chunk\n");
      return 2;
    }
  t = trilog_state_open ();
  if (t == NULL)
    return 1;
  rc = trilog_run_text (t, "'$amk_chunk'('" TRILOG_CHUNK "', true)", argv[1]);
  trilog_free (t);
  return rc;
}

/* The create member: a kept context, which make holds for the life of the process. */
__attribute__ ((visibility ("default"))) void *
trilog_create (void)
{
  return trilog_state_open ();
}

/* The value of the named binding as an atom's text, or null. */
static const char *
trilog_binding_text (trilog_t *t, const char *name)
{
  int i;
  for (i = 0; i < trilog_binding_count (t); i++)
    if (strcmp (trilog_binding_name (t, i), name) == 0)
      return trilog_get_atom (t, trilog_binding_value (t, i));
  return NULL;
}

/* The names an import set in make, space-joined for the sink. */
struct trilog_export
{
  char *names;
  size_t n;
};

/* One amk_export(Name, Value) set in make, its name added to the sink's list. */
static bool
trilog_export_one (trilog_t *t, void *ud, bool has_more)
{
  struct trilog_export *ex = ud;
  const char *name = trilog_binding_text (t, "N"), *value = trilog_binding_text (t, "V");
  size_t len;
  (void) has_more;
  if (name == NULL || value == NULL || !amk_name_ok (name))
    return true;
  len = strlen (name);
  amk_var_set (name, value);
  ex->names = realloc (ex->names, ex->n + len + 2);
  if (ex->n > 0)
    ex->names[ex->n++] = ' ';
  memcpy (ex->names + ex->n, name, len);
  ex->n += len;
  ex->names[ex->n] = '\0';
  return true;
}

/* The text of R from a lifted function's one solution. */
static bool
trilog_fn_take (trilog_t *t, void *ud, bool has_more)
{
  char **text = ud;
  const char *r = trilog_binding_text (t, "R");
  (void) has_more;
  *text = strdup (r ? r : "");
  return false;
}

/* The text as a quoted atom, appended at p, answering the end. */
static char *
trilog_quote (char *p, const char *s)
{
  *p++ = '\'';
  for (; *s; s++)
    {
      if (*s == '\'' || *s == '\\')
        *p++ = '\\';
      *p++ = *s;
    }
  *p++ = '\'';
  *p = '\0';
  return p;
}

/* make's call into a lifted function: Name(Arg1, ..., Result) with each argument a quoted atom, answering the text of Result from the first solution; no solution answers empty. */
static char *
trilog_fn_call (void *state, const char *nm, unsigned int argc, char **argv)
{
  trilog_t *t = trilog_usable (state);
  size_t len = 2 * strlen (nm) + 32, i;
  char *goal, *p, *out, *text = NULL;
  for (i = 0; i < argc; i++)
    len += 2 * strlen (argv[i]) + 4;
  goal = malloc (len);
  p = trilog_quote (goal + sprintf (goal, "'$amk_fn'("), nm);
  p += sprintf (p, ", [");
  for (i = 0; i < argc; i++)
    {
      if (i)
        *p++ = ',';
      p = trilog_quote (p, argv[i]);
    }
  strcpy (p, "], R)");
  if (trilog_ask (t, goal, trilog_fn_take, &text) == TRILOG_ERROR)
    {
      free (goal);
      free (text);
      amk_func_raise ("trilog", nm, "the goal raised");
      return NULL;
    }
  free (goal);
  out = gmk_alloc ((unsigned int) (text ? strlen (text) : 0) + 1);
  strcpy (out, text ? text : "");
  free (text);
  return out;
}

/* One amk_function(Name) the context answers, made make's function of that name. */
static bool
trilog_lift_one (trilog_t *t, void *ud, bool has_more)
{
  const char *name = trilog_binding_text (t, "F");
  (void) ud;
  (void) has_more;
  if (name != NULL && amk_name_ok (name) && amk_func_add (name, t, trilog_fn_call) < 0)
    fprintf (stderr, "trilog: %s is a make function already\n", name);
  return true;
}

/* exec runs the chunk with what it prints to the sink; import runs it with output on stderr, then sets in make every amk_export(Name, Value) the context answers and hands the sink their names. */
static int
trilog_run_op (void *state, struct amk_sink *out, const char *op, const char *prog)
{
  trilog_t *t = state;
  struct amk_capture capture;
  struct trilog_export ex = { NULL, 0 };
  int rc;
  if (prog == NULL)
    {
      fprintf (stderr, "trilog.%s: no chunk\n", op);
      return 2;
    }
  if (strcmp (op, "import") != 0)
    {
      amk_capture_begin_to (&capture, out);
      rc = trilog_run_text (t, "'$amk_chunk'('" TRILOG_CHUNK "', true)", prog);
      amk_capture_end (&capture, out);
      return rc;
    }
  amk_capture_begin (&capture);
  rc = trilog_run_text (t, "'$amk_chunk'('" TRILOG_CHUNK "', true)", prog);
  amk_capture_end (&capture, &amk_sink_stderr);
  if (rc != 0)
    return rc;
  t = trilog_usable (t);
  trilog_ask (t, "'$amk_export'(N, V)", trilog_export_one, &ex);
  trilog_ask (t, "'$amk_function'(F)", trilog_lift_one, NULL);
  if (ex.n > 0)
    out->write (out, ex.names, ex.n);
  out->write (out, "\n", 1);
  free (ex.names);
  return 0;
}

__attribute__ ((visibility ("default"))) int
trilog_exec (void *state, struct amk_sink *out, const char *prog)
{
  return trilog_run_op (state, out, "exec", prog);
}

__attribute__ ((visibility ("default"))) int
trilog_import (void *state, struct amk_sink *out, const char *prog)
{
  return trilog_run_op (state, out, "import", prog);
}

/* A goal run as a query through the driver, its answers to the sink as JSON lines; a trailing full stop is optional. */
static int
trilog_goal (trilog_t *t, struct amk_sink *out, const char *driver, const char *prog)
{
  struct amk_capture capture;
  size_t n = strlen (prog);
  char *chunk;
  int rc;
  while (n > 0 && (prog[n - 1] == ' ' || prog[n - 1] == '\t' || prog[n - 1] == '\n'))
    n--;
  if (n > 0 && prog[n - 1] == '.')
    n--;
  chunk = malloc (n + 6);
  memcpy (chunk, "?- ", 3);
  memcpy (chunk + 3, prog, n);
  memcpy (chunk + 3 + n, ".\n", 3);
  amk_capture_begin_to (&capture, out);
  rc = trilog_run_text (t, driver, chunk);
  amk_capture_end (&capture, out);
  free (chunk);
  return rc;
}

/* The workspace get: the goal's answers, with the clause store put back as it was, so an assert or retract in it does not last. */
__attribute__ ((visibility ("default"))) int
trilog_get (void *state, struct amk_sink *out, const char *prog)
{
  return trilog_goal (state, out, "'$amk_get'('" TRILOG_CHUNK "')", prog);
}

/* The workspace update: the goal's answers, with whatever it asserts or retracts kept. */
__attribute__ ((visibility ("default"))) int
trilog_update (void *state, struct amk_sink *out, const char *prog)
{
  return trilog_goal (state, out, "'$amk_chunk'('" TRILOG_CHUNK "', true)", prog);
}

/* The workspace load: the text's clauses replace every user clause, all or nothing; a directive or a clause that does not parse leaves the store as it was. */
__attribute__ ((visibility ("default"))) int
trilog_load (void *state, const char *text)
{
  return trilog_run_text (state, "'$amk_load'('" TRILOG_CHUNK "')", text);
}

/* The workspace dump: every user clause, one to a line, in the text load takes back. */
__attribute__ ((visibility ("default"))) int
trilog_dump (void *state, struct amk_sink *out)
{
  struct amk_capture capture;
  int rc;
  amk_capture_begin_to (&capture, out);
  rc = trilog_run (state, "'$amk_dump'");
  amk_capture_end (&capture, out);
  return rc;
}

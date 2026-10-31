/* The s7 guest's entry point: amk links the interpreter, not the s7 repl, so it supplies this. */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#include "s7.h"
#include "amk_guest.h"

/* Whether the interpreter is a kept state, which make holds, as against a one-shot call's that ends with the call. */
static int
s7_is_kept (s7_scheme *sc)
{
  return s7_symbol_value (sc, s7_make_symbol (sc, "*amk-kept*")) == s7_t (sc);
}

/* Under the engine flag make has parsed nothing, so the handle raises rather than reads. */
static s7_pointer
s7_amk_need_make (s7_scheme *sc, const char *who)
{
  if (amk_has_db ())
    return NULL;
  return s7_error (sc, s7_make_symbol (sc, "amk-error"),
                   s7_list (sc, 1, s7_make_string (sc, "no make database, running outside a makefile")));
}

/* A variable name as a symbol or a string, or a wrong-type error. */
static const char *
s7_amk_name (s7_scheme *sc, s7_pointer args, const char *who)
{
  s7_pointer p = s7_car (args);
  if (s7_is_symbol (p))
    return s7_symbol_name (p);
  if (s7_is_string (p))
    return s7_string (p);
  s7_wrong_type_arg_error (sc, who, 1, p, "a symbol or a string");
  return NULL;
}

/* A value as the text make gets: a string as is, a symbol as its name, #f as nothing, and anything else as display would show it. The result is malloc'd. */
static char *
s7_amk_text (s7_scheme *sc, s7_pointer value)
{
  if (s7_is_string (value))
    return strdup (s7_string (value));
  if (s7_is_symbol (value))
    return strdup (s7_symbol_name (value));
  if (value == s7_f (sc) || s7_is_unspecified (sc, value))
    return strdup ("");
  return s7_object_to_c_string (sc, value);
}

/* (amk-expand text): the text expanded by make. */
static s7_pointer
s7_amk_expand (s7_scheme *sc, s7_pointer args)
{
  s7_pointer err = s7_amk_need_make (sc, "amk-expand");
  char *s;
  s7_pointer r;
  if (err != NULL)
    return err;
  if (!s7_is_string (s7_car (args)))
    return s7_wrong_type_arg_error (sc, "amk-expand", 1, s7_car (args), "a string");
  s = gmk_expand (s7_string (s7_car (args)));
  r = s7_make_string (sc, s ? s : "");
  gmk_free (s);
  return r;
}

/* (amk-call name value ...): the make function or macro of that name, each value one whole argument, never expanded. */
static s7_pointer
s7_amk_call_kind (s7_scheme *sc, s7_pointer args, int kind, const char *who)
{
  s7_pointer err = s7_amk_need_make (sc, who);
  const char *why = NULL, **vals;
  char *name, *s;
  s7_pointer p, r;
  unsigned int n = 0, i;
  if (err != NULL)
    return err;
  if (!s7_is_string (s7_car (args)) && !s7_is_symbol (s7_car (args)))
    return s7_wrong_type_arg_error (sc, who, 1, s7_car (args), "a string or a symbol");
  name = s7_amk_text (sc, s7_car (args));
  for (p = s7_cdr (args); s7_is_pair (p); p = s7_cdr (p))
    n++;
  vals = malloc ((n + 1) * sizeof *vals);
  for (i = 0, p = s7_cdr (args); i < n; i++, p = s7_cdr (p))
    vals[i] = s7_amk_text (sc, s7_car (p));
  s = amk_call_kind (kind, name, n, vals, &why);
  for (i = 0; i < n; i++)
    free ((char *) vals[i]);
  free (vals);
  free (name);
  if (s == NULL)
    return s7_error (sc, s7_make_symbol (sc, "amk-error"), s7_list (sc, 1, s7_make_string (sc, why)));
  r = s7_make_string (sc, s);
  gmk_free (s);
  return r;
}

/* (amk-call name value ...): the cascade, a make function, the name under amk., a macro; amk-fxn and amk-macro take one layer by its full name. */
static s7_pointer s7_amk_call (s7_scheme *sc, s7_pointer args) { return s7_amk_call_kind (sc, args, AMK_AS_ANY, "amk-call"); }
static s7_pointer s7_amk_fxn (s7_scheme *sc, s7_pointer args) { return s7_amk_call_kind (sc, args, AMK_AS_FXN, "amk-fxn"); }
static s7_pointer s7_amk_macro (s7_scheme *sc, s7_pointer args) { return s7_amk_call_kind (sc, args, AMK_AS_MACRO, "amk-macro"); }

/* (amk-call-begin name value ...): the call begun in a fork, as a list of its pid and the fd that reads as done when the result is in; amk-afxn and amk-amacro the same over one layer. */
static s7_pointer
s7_amk_call_begin_kind (s7_scheme *sc, s7_pointer args, int kind, const char *who)
{
  s7_pointer err = s7_amk_need_make (sc, who);
  const char **vals;
  char *name;
  s7_pointer p;
  unsigned int n = 0, i;
  int fd = -1;
  pid_t pid;
  if (err != NULL)
    return err;
  if (!s7_is_string (s7_car (args)) && !s7_is_symbol (s7_car (args)))
    return s7_wrong_type_arg_error (sc, who, 1, s7_car (args), "a string or a symbol");
  name = s7_amk_text (sc, s7_car (args));
  for (p = s7_cdr (args); s7_is_pair (p); p = s7_cdr (p))
    n++;
  vals = malloc ((n + 1) * sizeof *vals);
  for (i = 0, p = s7_cdr (args); i < n; i++, p = s7_cdr (p))
    vals[i] = s7_amk_text (sc, s7_car (p));
  pid = amk_call_begin (kind, name, n, vals, &fd);
  for (i = 0; i < n; i++)
    free ((char *) vals[i]);
  free (vals);
  free (name);
  if (pid < 0)
    return s7_error (sc, s7_make_symbol (sc, "amk-error"), s7_list (sc, 2, s7_make_string (sc, "~A: fork failed"), s7_make_string (sc, who)));
  return s7_list (sc, 2, s7_make_integer (sc, pid), s7_make_integer (sc, fd));
}
static s7_pointer s7_amk_call_begin (s7_scheme *sc, s7_pointer args) { return s7_amk_call_begin_kind (sc, args, AMK_AS_ANY, "amk-call-begin"); }
static s7_pointer s7_amk_afxn (s7_scheme *sc, s7_pointer args) { return s7_amk_call_begin_kind (sc, args, AMK_AS_FXN, "amk-afxn"); }
static s7_pointer s7_amk_amacro (s7_scheme *sc, s7_pointer args) { return s7_amk_call_begin_kind (sc, args, AMK_AS_MACRO, "amk-amacro"); }

/* (amk-agoal name): amk-call-begin of the goal function, the goal run in a fork as (pid fd). */
static s7_pointer
s7_amk_agoal (s7_scheme *sc, s7_pointer args)
{
  return s7_amk_call_begin (sc, s7_cons (sc, s7_make_string (sc, "amk.goal"), args));
}

/* (amk-call-end pid): the call collected, its text, or its error raised. */
static s7_pointer
s7_amk_call_end (s7_scheme *sc, s7_pointer args)
{
  s7_pointer err = s7_amk_need_make (sc, "amk-call-end");
  const char *why = NULL;
  char *s;
  s7_pointer r;
  if (err != NULL)
    return err;
  if (!s7_is_integer (s7_car (args)))
    return s7_wrong_type_arg_error (sc, "amk-call-end", 1, s7_car (args), "an integer");
  if (amk_call_end ((pid_t) s7_integer (s7_car (args)), &s, &why) < 0)
    return s7_error (sc, s7_make_symbol (sc, "amk-error"), s7_list (sc, 1, s7_make_string (sc, why)));
  r = s7_make_string (sc, s);
  free (s);
  return r;
}

/* (amk-ask-begin op namespace value ...): one request sent to the owner, as its id; the process goes on until amk-ask-end, and in the owner a request that would park is an error. */
static s7_pointer
s7_amk_ask_begin (s7_scheme *sc, s7_pointer args)
{
  s7_pointer err = s7_amk_need_make (sc, "amk-ask-begin");
  const char **vals;
  char *op, *ns, *line;
  s7_pointer p;
  unsigned int n = 0, i;
  long id;
  if (err != NULL)
    return err;
  if (!s7_is_string (s7_car (args)) && !s7_is_symbol (s7_car (args)))
    return s7_wrong_type_arg_error (sc, "amk-ask-begin", 1, s7_car (args), "a string or a symbol");
  if (!s7_is_pair (s7_cdr (args)) || (!s7_is_string (s7_cadr (args)) && !s7_is_symbol (s7_cadr (args))))
    return s7_wrong_type_arg_error (sc, "amk-ask-begin", 2, s7_is_pair (s7_cdr (args)) ? s7_cadr (args) : s7_nil (sc), "a string or a symbol");
  op = s7_amk_text (sc, s7_car (args));
  ns = s7_amk_text (sc, s7_cadr (args));
  for (p = s7_cddr (args); s7_is_pair (p); p = s7_cdr (p))
    n++;
  vals = malloc ((n + 1) * sizeof *vals);
  for (i = 0, p = s7_cddr (args); i < n; i++, p = s7_cdr (p))
    vals[i] = s7_amk_text (sc, s7_car (p));
  line = amk_ask_line (op, ns, n, vals);
  for (i = 0; i < n; i++)
    free ((char *) vals[i]);
  free (vals);
  free (op);
  free (ns);
  id = amk_ask_begin (line);
  free (line);
  if (id < 0)
    return s7_error (sc, s7_make_symbol (sc, "amk-error"), s7_list (sc, 1, s7_make_string (sc, "amk-ask-begin: " AMK_ASK_PARKED)));
  return s7_make_integer (sc, id);
}

/* (amk-ask-end id): the reply waited for, its text, or its error raised. */
static s7_pointer
s7_amk_ask_end (s7_scheme *sc, s7_pointer args)
{
  s7_pointer err = s7_amk_need_make (sc, "amk-ask-end");
  const char *why = NULL;
  char *s;
  s7_pointer r;
  if (err != NULL)
    return err;
  if (!s7_is_integer (s7_car (args)))
    return s7_wrong_type_arg_error (sc, "amk-ask-end", 1, s7_car (args), "an integer");
  if (amk_ask_result (amk_ask_collect ((unsigned long) s7_integer (s7_car (args))), &s, &why) < 0)
    return s7_error (sc, s7_make_symbol (sc, "amk-error"), s7_list (sc, 1, s7_make_string (sc, why)));
  r = s7_make_string (sc, s);
  free (s);
  return r;
}

/* (amk-eval text): the text read by make as makefile syntax. */
static s7_pointer
s7_amk_eval (s7_scheme *sc, s7_pointer args)
{
  s7_pointer err = s7_amk_need_make (sc, "amk-eval");
  if (err != NULL)
    return err;
  if (!s7_is_string (s7_car (args)))
    return s7_wrong_type_arg_error (sc, "amk-eval", 1, s7_car (args), "a string");
  amk_eval (s7_string (s7_car (args)));
  return s7_unspecified (sc);
}

/* (amk-var name): the variable expanded, or #f when make has never seen the name. */
static s7_pointer
s7_amk_var (s7_scheme *sc, s7_pointer args)
{
  s7_pointer err = s7_amk_need_make (sc, "amk-var");
  const char *name;
  char *s;
  s7_pointer r;
  if (err != NULL)
    return err;
  name = s7_amk_name (sc, args, "amk-var");
  if (strcmp (name, "raw") == 0)
    return s7_name_to_value (sc, "amk-var-raw");
  s = amk_var_get (name);
  if (s == NULL)
    return s7_f (sc);
  r = s7_make_string (sc, s);
  gmk_free (s);
  return r;
}

/* ((amk-var 'raw) name): the variable's text as stored, never expanded, or #f when make has never seen the name. */
static s7_pointer
s7_amk_var_raw (s7_scheme *sc, s7_pointer args)
{
  s7_pointer err = s7_amk_need_make (sc, "amk-var-raw");
  const char *name;
  char *s;
  s7_pointer r;
  if (err != NULL)
    return err;
  name = s7_amk_name (sc, args, "amk-var-raw");
  s = amk_var_raw_get (name);
  if (s == NULL)
    return s7_f (sc);
  r = s7_make_string (sc, s);
  gmk_free (s);
  return r;
}

/* (set! ((amk-var 'raw) name) value) defines a recursive variable with the value's text as written; #f is the empty string. */
static s7_pointer
s7_amk_var_raw_set (s7_scheme *sc, s7_pointer args)
{
  s7_pointer err = s7_amk_need_make (sc, "amk-var-raw");
  const char *name;
  s7_pointer value;
  char *text;
  if (err != NULL)
    return err;
  name = s7_amk_name (sc, args, "amk-var-raw");
  value = s7_cadr (args);
  text = s7_amk_text (sc, value);
  amk_var_raw_set (name, text ? text : "");
  free (text);
  return value;
}

/* (set! (amk-var name) value) defines a simple variable with the value's text; #f is the empty string. */
static s7_pointer
s7_amk_var_set (s7_scheme *sc, s7_pointer args)
{
  s7_pointer err = s7_amk_need_make (sc, "amk-var");
  const char *name;
  s7_pointer value;
  char *text;
  if (err != NULL)
    return err;
  name = s7_amk_name (sc, args, "amk-var");
  value = s7_cadr (args);
  text = s7_amk_text (sc, value);
  amk_var_set (name, text ? text : "");
  free (text);
  return value;
}

/* The persistent state's tables, held in the rootlet so the collector keeps them: the make functions it defined by name, the hook procedures by event, and the snapshot an export compares against. */
static s7_pointer
s7_amk_table (s7_scheme *sc, const char *name)
{
  return s7_symbol_value (sc, s7_make_symbol (sc, name));
}

/* A procedure applied under a catch: an error answers the guest error symbol, reported on stderr with the caller's name, or kept in *amk-guest-why* when raises is set so the caller can raise it. */
static s7_pointer
s7_amk_apply (s7_scheme *sc, const char *who, int raises, s7_pointer fn, s7_pointer args)
{
  s7_define_variable (sc, "*amk-call-who*", s7_make_string (sc, who));
  s7_define_variable (sc, "*amk-call-raises*", s7_make_boolean (sc, raises));
  s7_define_variable (sc, "*amk-call-fn*", fn);
  s7_define_variable (sc, "*amk-call-args*", args);
  return s7_call_with_catch (sc, s7_t (sc), s7_amk_table (sc, "amk-call-thunk"), s7_amk_table (sc, "amk-call-handler"));
}

/* s7 calls this at the start of every body of more than one form, and it raises on each call once the process's deadline has passed, so a catch inside the run cannot keep it going. */
static void
s7_deadline_hook (s7_scheme *sc, bool *val)
{
  char msg[64];
  (void) val;
  if (amk_deadline_expired ())
    {
      snprintf (msg, sizeof msg, "deadline: %ld ms", amk_deadline_budget ());
      s7_error (sc, s7_make_symbol (sc, "deadline"), s7_list (sc, 1, s7_make_string (sc, msg)));
    }
}

/* make's call into a defined function, in the state that defined it: the arguments as strings, the result as text, and an error raised to whoever made the call. */
static char *
s7_func_call (void *state, const char *nm, unsigned int argc, char **argv)
{
  s7_scheme *sc = state;
  s7_pointer fn, args = NULL, result;
  char who[300];
  char *text, *out;
  unsigned int i;

  fn = s7_hash_table_ref (sc, s7_amk_table (sc, "*amk-funcs*"), s7_make_symbol (sc, nm));
  if (!s7_is_procedure (fn))
    return NULL;
  args = s7_nil (sc);
  for (i = argc; i > 0; i--)
    args = s7_cons (sc, s7_make_string (sc, argv[i - 1]), args);
  snprintf (who, sizeof who, "$(%s ...)", nm);
  if (amk_deadline_active ())
    s7_set_begin_hook (sc, s7_deadline_hook);
  result = s7_amk_apply (sc, who, 1, fn, args);
  s7_set_begin_hook (sc, amk_deadline_active () ? s7_deadline_hook : NULL);
  if (s7_is_eq (result, s7_make_symbol (sc, "amk-guest-error")))
    {
      if (!amk_deadline_expired ())
        amk_func_raise ("s7", nm, s7_string (s7_name_to_value (sc, "*amk-guest-why*")));
      return NULL;
    }
  text = s7_amk_text (sc, result);
  out = gmk_alloc ((unsigned int) strlen (text) + 1);
  strcpy (out, text);
  free (text);
  return out;
}

/* The procedure becomes make's function of that name, or replaces the one this state defined before; a name make has from elsewhere is an error. */
static s7_pointer
s7_define_func (s7_scheme *sc, const char *name, s7_pointer fn)
{
  s7_pointer funcs = s7_amk_table (sc, "*amk-funcs*");
  s7_pointer sym = s7_make_symbol (sc, name);
  if (amk_func_add (name, sc, s7_func_call) < 0)
    return s7_error (sc, s7_make_symbol (sc, "amk-error"),
                     s7_list (sc, 2, s7_make_string (sc, "amk-func: ~A is a make function already"), sym));
  s7_hash_table_set (sc, funcs, sym, fn);
  return s7_unspecified (sc);
}

/* (amk-func name fn): make gains a function of that name whose arguments, expanded, reach fn as strings and whose result is what fn returns; only a kept state outlives the call to answer. */
static s7_pointer
s7_amk_func (s7_scheme *sc, s7_pointer args)
{
  s7_pointer err = s7_amk_need_make (sc, "amk-func");
  const char *name;
  if (err != NULL)
    return err;
  if (!s7_is_kept (sc))
    return s7_error (sc, s7_make_symbol (sc, "amk-error"),
                     s7_list (sc, 1, s7_make_string (sc, "amk-func: only from s7.exec, since a one-shot call's state ends with the call")));
  name = s7_amk_name (sc, args, "amk-func");
  if (!s7_is_procedure (s7_cadr (args)))
    return s7_wrong_type_arg_error (sc, "amk-func", 2, s7_cadr (args), "a procedure");
  return s7_define_func (sc, name, s7_cadr (args));
}

/* (amk-on event): the hook procedure for the event, or #f; (set! (amk-on event) fn) subscribes. */
static s7_pointer
s7_amk_on (s7_scheme *sc, s7_pointer args)
{
  const char *event = s7_amk_name (sc, args, "amk-on");
  return s7_hash_table_ref (sc, s7_amk_table (sc, "*amk-on*"), s7_make_symbol (sc, event));
}

static s7_pointer
s7_amk_on_set (s7_scheme *sc, s7_pointer args)
{
  const char *event = s7_amk_name (sc, args, "amk-on");
  s7_hash_table_set (sc, s7_amk_table (sc, "*amk-on*"), s7_make_symbol (sc, event), s7_cadr (args));
  return s7_cadr (args);
}

/* (amk-deadline-push ms): the tighter of ms and the process's deadline takes effect, and the one it replaced comes back for amk-deadline-pop. */
static s7_pointer
s7_amk_deadline_push (s7_scheme *sc, s7_pointer args)
{
  struct amk_deadline saved;
  s7_int ms;
  if (!s7_is_integer (s7_car (args)) || (ms = s7_integer (s7_car (args))) < 0)
    return s7_wrong_type_arg_error (sc, "amk-deadline", 1, s7_car (args), "a non-negative integer");
  amk_deadline_push ((long) ms, &saved);
  s7_set_begin_hook (sc, s7_deadline_hook);
  return s7_list (sc, 2, s7_make_real (sc, saved.at), s7_make_integer (sc, saved.ms));
}

/* (amk-deadline-pop saved): the deadline before the push back in force, answering the budget that had run out, or #f. */
static s7_pointer
s7_amk_deadline_pop (s7_scheme *sc, s7_pointer args)
{
  s7_pointer list = s7_car (args);
  struct amk_deadline saved = { s7_real (s7_car (list)), (long) s7_integer (s7_cadr (list)) };
  long hit = amk_deadline_pop (&saved);
  s7_set_begin_hook (sc, amk_deadline_active () ? s7_deadline_hook : NULL);
  return hit >= 0 ? s7_make_integer (sc, hit) : s7_f (sc);
}

/* The handle: expand, eval, func, and the two dilambdas, so generalized set! reaches their setters; the call, chunk, and hook plumbing lives beside them in the rootlet, and a chunk is read in the rootlet so its defines persist; an unbound amk-name-... loads the payload module name/init.scm once. */
static const char *s7_amk_prelude =
  "(begin"
  " (define *amk-funcs* (make-hash-table))"
  " (define *amk-on* (make-hash-table))"
  " (define *amk-kept* #f)"
  " (define *amk-call-who* \"\")"
  " (define *amk-call-fn* #f)"
  " (define *amk-call-args* ())"
  " (define *amk-chunk* \"\")"
  " (define (amk-chunk-thunk) (eval-string (string-append \"(begin \" *amk-chunk* \"\\n)\") (rootlet)))"
  " (define (amk-call-thunk)"
  "   (let ((who *amk-call-who*) (raises *amk-call-raises*) (fn *amk-call-fn*) (args *amk-call-args*))"
  "     (catch #t (lambda () (apply fn args)) (lambda (type info) (amk-call-report who raises type info)))))"
  " (define (amk-deadline ms fn . args)"
  "   (let ((saved (amk-deadline-push ms)))"
  "     (catch #t"
  "       (lambda () (let ((r (apply fn args))) (amk-deadline-pop saved) r))"
  "       (lambda (type info)"
  "         (let ((hit (amk-deadline-pop saved)))"
  "           (if hit (error 'deadline (format #f \"deadline: ~A ms\" hit)) (apply error type info)))))))"
  " (define *amk-guest-why* \"\")"
  " (define *amk-call-raises* #f)"
  " (define (amk-call-report who raises type info)"
  "   (cond (raises (set! *amk-guest-why* (format #f \"~A\" (cons type info))))"
  "         ((string=? who \"\") (format *stderr* \"s7: ~A~%\" (cons type info)))"
  "         (else (format *stderr* \"s7 ~A: ~A~%\" who (cons type info))))"
  "   'amk-guest-error)"
  " (define (amk-call-handler type info) (amk-call-report *amk-call-who* *amk-call-raises* type info))"
  " (define *amk-modules* (make-hash-table))"
  " (define (amk-module-path name)"
  "   (let* ((s (symbol->string name)) (end (and (> (length s) 4) (string=? (substring s 0 4) \"amk-\") (char-position #\\- s 4))))"
  "     (and end (let ((path (string-append \"/zip/lib/\" (substring s 4 end) \"/init.scm\")))"
  "                (and (not (*amk-modules* path))"
  "                     (catch #t (lambda () (close-input-port (open-input-file path)) path) (lambda args #f)))))))"
  " (define (amk-dotted name)"
  "   (let ((s (copy (symbol->string name))))"
  "     (and (> (length s) 4) (string=? (substring s 0 4) \"amk-\")"
  "          (do ((i 4 (+ i 1))) ((= i (length s)) (substring s 4))"
  "            (when (char=? (string-ref s i) #\\-) (string-set! s i #\\.))))))"
  " (set! (hook-functions *unbound-variable-hook*)"
  "   (cons (lambda (h)"
  "           (let ((path (amk-module-path (h 'variable))))"
  "             (if path"
  "                 (begin"
  "                   (set! (*amk-modules* path) #t)"
  "                   (load path (rootlet))"
  "                   (set! (h 'result) (symbol->value (h 'variable) (rootlet))))"
  "                 (let ((dotted (amk-dotted (h 'variable))))"
  "                   (when (and dotted (amk-call? dotted))"
  "                     (set! (h 'result) (lambda args (apply amk-call dotted args))))))))"
  "         (hook-functions *unbound-variable-hook*))))";

/* (amk-call? name): whether the cascade answers for the name, so an unbound amk-a-b may stand for a.b. */
static s7_pointer
s7_amk_call_p (s7_scheme *sc, s7_pointer args)
{
  char full[512];
  const char *err;
  return s7_make_boolean (sc, s7_is_string (s7_car (args)) && amk_resolve (s7_string (s7_car (args)), full, sizeof full, &err) >= 0);
}

static void
s7_bind_amk (s7_scheme *sc)
{
  s7_define_function (sc, "amk-expand", s7_amk_expand, 1, 0, false, "(amk-expand text) the text expanded by make");
  s7_define_function (sc, "amk-eval", s7_amk_eval, 1, 0, false, "(amk-eval text) the text read by make as makefile syntax");
  s7_define_function (sc, "amk-call", s7_amk_call, 1, 0, true, "(amk-call name value ...) the make function or macro, each value one whole argument");
  s7_define_function (sc, "amk-fxn", s7_amk_fxn, 1, 0, true, "(amk-fxn name value ...) the make function of that name, each value one whole argument");
  s7_define_function (sc, "amk-macro", s7_amk_macro, 1, 0, true, "(amk-macro name value ...) the macro of that name, each value one whole argument");
  s7_define_function (sc, "amk-call?", s7_amk_call_p, 1, 0, false, "(amk-call? name) whether the cascade answers for the name");
  s7_define_function (sc, "amk-call-begin", s7_amk_call_begin, 1, 0, true, "(amk-call-begin name value ...) the call begun in a fork, as (pid fd)");
  s7_define_function (sc, "amk-afxn", s7_amk_afxn, 1, 0, true, "(amk-afxn name value ...) the make function begun in a fork, as (pid fd)");
  s7_define_function (sc, "amk-amacro", s7_amk_amacro, 1, 0, true, "(amk-amacro name value ...) the macro begun in a fork, as (pid fd)");
  s7_define_function (sc, "amk-call-end", s7_amk_call_end, 1, 0, false, "(amk-call-end pid) the call collected");
  s7_define_function (sc, "amk-agoal", s7_amk_agoal, 1, 0, false, "(amk-agoal name) the goal begun in a fork, as (pid fd)");
  s7_define_function (sc, "amk-ask-begin", s7_amk_ask_begin, 2, 0, true, "(amk-ask-begin op namespace value ...) one request to the owner, as its id");
  s7_define_function (sc, "amk-ask-end", s7_amk_ask_end, 1, 0, false, "(amk-ask-end id) the reply waited for");
  s7_define_function (sc, "amk-func", s7_amk_func, 2, 0, false, "(amk-func name fn) defines a make function");
  s7_define_function (sc, "amk-deadline-push", s7_amk_deadline_push, 1, 0, false, "(amk-deadline-push ms) puts a deadline in force");
  s7_define_function (sc, "amk-deadline-pop", s7_amk_deadline_pop, 1, 0, false, "(amk-deadline-pop saved) restores the deadline before it");
  s7_dilambda (sc, "amk-var", s7_amk_var, 1, 0, s7_amk_var_set, 2, 0,
               "(amk-var name) a make variable expanded, or #f; (set! (amk-var name) value) defines it");
  s7_dilambda (sc, "amk-var-raw", s7_amk_var_raw, 1, 0, s7_amk_var_raw_set, 2, 0,
               "((amk-var 'raw) name) a make variable as stored, or #f; (set! ((amk-var 'raw) name) value) defines it recursive");
  s7_dilambda (sc, "amk-on", s7_amk_on, 1, 0, s7_amk_on_set, 2, 0,
               "(amk-on event) the hook for the event, or #f; (set! (amk-on event) fn) subscribes");
  s7_eval_c_string (sc, s7_amk_prelude);
}

/* A chunk read in the rootlet under a catch, so an uncaught error reports itself and answers with a sentinel: 0 when it ran through, 1 when it raised. */
static int
s7_run_chunk (s7_scheme *sc, const char *src)
{
  s7_pointer result;
  s7_define_variable (sc, "*amk-call-who*", s7_make_string (sc, ""));
  s7_define_variable (sc, "*amk-call-raises*", s7_f (sc));
  s7_define_variable (sc, "*amk-chunk*", s7_make_string (sc, src));
  result = s7_call_with_catch (sc, s7_t (sc), s7_amk_table (sc, "amk-chunk-thunk"), s7_amk_table (sc, "amk-call-handler"));
  return s7_is_eq (result, s7_make_symbol (sc, "amk-guest-error")) ? 1 : 0;
}

/* s7 reads its own stdin through a fixed 1024-byte fgets that keeps the newline and answers
   an empty string at end of file, so a guest given input reads a string port instead: the
   whole of a file or a pipe, up to end of file; a terminal is left to s7.  */
static char *
s7_guest_slurp_stdin (void)
{
  char *buf;
  size_t len = 0, cap = 4096;

  if (isatty (STDIN_FILENO))
    return NULL;
  buf = malloc (cap + 1);
  if (buf == NULL)
    return NULL;
  for (;;)
    {
      size_t r = fread (buf + len, 1, cap - len, stdin);
      len += r;
      if (len < cap)
        break;
      cap *= 2;
      buf = realloc (buf, cap + 1);
      if (buf == NULL)
        return NULL;
    }
  buf[len] = '\0';
  return buf;
}

/* An interpreter with the handle bound and the payload's s7 packages on its load path, or null. */
static s7_scheme *
s7_state_open (void)
{
  s7_scheme *sc = s7_init ();
  if (sc == NULL)
    {
      fprintf (stderr, "s7: cannot create interpreter\n");
      return NULL;
    }
  s7_add_to_load_path (sc, "/zip/lib/s7");
  s7_bind_amk (sc);
  return sc;
}

/* argv[1] is Scheme source text rather than a command line; whatever it prints is the result. */
__attribute__ ((visibility ("default"))) int
s7_run_main (int argc, char **argv)
{
  s7_scheme *sc;
  char *input;
  int rc;

  if (argc < 2 || argv[1] == NULL)
    {
      fprintf (stderr, "s7: no chunk\n");
      return 2;
    }
  sc = s7_state_open ();
  if (sc == NULL)
    return 1;

  input = s7_guest_slurp_stdin ();
  if (input != NULL)
    s7_set_current_input_port (sc, s7_open_input_string (sc, input));

  rc = s7_run_chunk (sc, argv[1]);
  free (input);
  s7_free (sc);
  fflush (stdout);
  return rc;
}

struct s7_names
{
  char *s;
  size_t n, cap;
};

static void
s7_names_add (struct s7_names *names, const char *name)
{
  size_t len = strlen (name);
  if (names->n + len + 2 > names->cap)
    names->s = realloc (names->s, names->cap = (names->n + len + 2) * 2);
  if (names->n > 0)
    names->s[names->n++] = ' ';
  memcpy (names->s + names->n, name, len);
  names->n += len;
  names->s[names->n] = '\0';
}

/* A binding to export, gathered so the walk can sort by name. */
struct s7_binding
{
  const char *name;
  s7_pointer value;
};

static int
s7_binding_cmp (const void *a, const void *b)
{
  return strcmp (((const struct s7_binding *) a)->name, ((const struct s7_binding *) b)->name);
}

/* The name of a key, a symbol or a string, or null for one make cannot spell. */
static const char *
s7_key_name (s7_pointer key)
{
  if (s7_is_symbol (key))
    return s7_symbol_name (key);
  if (s7_is_string (key))
    return s7_string (key);
  return NULL;
}

static s7_pointer s7_export_value (s7_scheme *sc, const char *name, s7_pointer value, struct s7_names *names);

/* An alist of key and value pairs as fields: one variable per key as name.key, in key order, recursing. */
static s7_pointer
s7_export_fields (s7_scheme *sc, const char *name, s7_pointer alist, struct s7_names *names)
{
  struct s7_binding *fields = NULL;
  size_t n = 0, cap = 0, i;
  s7_pointer p, r = s7_unspecified (sc);

  for (p = alist; s7_is_pair (p); p = s7_cdr (p))
    {
      s7_pointer entry = s7_car (p);
      const char *key = s7_is_pair (entry) ? s7_key_name (s7_car (entry)) : NULL;
      if (key == NULL || !amk_name_ok (key))
        {
          free (fields);
          return s7_error (sc, s7_make_symbol (sc, "amk-error"),
                           s7_list (sc, 3, s7_make_string (sc, "amk import: ~A has a key make cannot spell: ~S"),
                                    s7_make_string (sc, name), s7_is_pair (entry) ? s7_car (entry) : entry));
        }
      if (n == cap)
        fields = realloc (fields, (cap += 16) * sizeof *fields);
      fields[n].name = key;
      fields[n].value = s7_cdr (entry);
      n++;
    }
  qsort (fields, n, sizeof *fields, s7_binding_cmp);
  for (i = 0; i < n && !s7_is_eq (r, s7_make_symbol (sc, "amk-guest-error")); i++)
    {
      char *child = malloc (strlen (name) + strlen (fields[i].name) + 2);
      sprintf (child, "%s.%s", name, fields[i].name);
      r = s7_export_value (sc, child, fields[i].value, names);
      free (child);
    }
  free (fields);
  return r;
}

/* A hash table as an alist of its entries. */
static s7_pointer
s7_hash_table_alist (s7_scheme *sc, s7_pointer table)
{
  s7_pointer iter = s7_make_iterator (sc, table);
  s7_pointer alist = s7_nil (sc);
  while (1)
    {
      s7_pointer entry = s7_iterate (sc, iter);
      if (s7_iterator_is_at_end (sc, iter))
        break;
      alist = s7_cons (sc, entry, alist);
    }
  return alist;
}

/* One binding into make: a procedure as a make function, a list or vector as words, a hash table or let as fields, #t as true and #f as nothing, and a string, symbol, or number as its text; unspecified and anything else are skipped. */
static s7_pointer
s7_export_value (s7_scheme *sc, const char *name, s7_pointer value, struct s7_names *names)
{
  if (s7_is_unspecified (sc, value) || s7_is_c_object (value) || s7_is_iterator (value) || s7_is_macro (sc, value))
    return s7_unspecified (sc);
  if (s7_is_hash_table (value))
    return s7_export_fields (sc, name, s7_hash_table_alist (sc, value), names);
  if (s7_is_let (value))
    return s7_export_fields (sc, name, s7_let_to_list (sc, value), names);
  if (s7_is_procedure (value))
    {
      s7_pointer r = s7_define_func (sc, name, value);
      if (!s7_is_unspecified (sc, r))
        return r;
    }
  else if (s7_is_boolean (value))
    amk_var_set (name, value == s7_t (sc) ? "true" : "");
  else if (s7_is_pair (value) || s7_is_null (sc, value) || s7_is_vector (value))
    {
      struct s7_names words = { NULL, 0, 0 };
      if (s7_is_vector (value))
        {
          s7_int i, n = s7_vector_length (value);
          for (i = 0; i < n; i++)
            {
              char *text = s7_amk_text (sc, s7_vector_ref (sc, value, i));
              s7_names_add (&words, text);
              free (text);
            }
        }
      else
        {
          s7_pointer p;
          for (p = value; s7_is_pair (p); p = s7_cdr (p))
            {
              char *text = s7_amk_text (sc, s7_car (p));
              s7_names_add (&words, text);
              free (text);
            }
        }
      amk_var_set (name, words.s ? words.s : "");
      free (words.s);
    }
  else
    {
      char *text = s7_amk_text (sc, value);
      amk_var_set (name, text);
      free (text);
    }
  s7_names_add (names, name);
  return s7_unspecified (sc);
}

/* The rootlet as it was before an export chunk, each value boxed in a list so a missing binding and a #f one differ. */
static void
s7_snapshot_globals (s7_scheme *sc)
{
  s7_pointer before = s7_make_hash_table (sc, 256);
  s7_pointer p;
  for (p = s7_let_to_list (sc, s7_rootlet (sc)); s7_is_pair (p); p = s7_cdr (p))
    {
      s7_pointer entry = s7_car (p);
      if (s7_is_pair (entry) && s7_is_symbol (s7_car (entry)))
        s7_hash_table_set (sc, before, s7_car (entry), s7_list (sc, 1, s7_cdr (entry)));
    }
  s7_define_variable (sc, "*amk-before*", before);
}

/* Every rootlet binding that is new or rebound since the snapshot, exported in name order, and the names to the sink. */
static int
s7_export_globals (s7_scheme *sc, struct amk_sink *out)
{
  s7_pointer before = s7_amk_table (sc, "*amk-before*");
  struct s7_binding *bindings = NULL;
  size_t n = 0, cap = 0, i;
  struct s7_names names = { NULL, 0, 0 };
  s7_pointer p;
  int rc = 0;

  for (p = s7_let_to_list (sc, s7_rootlet (sc)); s7_is_pair (p); p = s7_cdr (p))
    {
      s7_pointer entry = s7_car (p), was;
      const char *name;
      if (!s7_is_pair (entry) || !s7_is_symbol (s7_car (entry)))
        continue;
      name = s7_symbol_name (s7_car (entry));
      if (!amk_name_ok (name))
        continue;
      was = s7_hash_table_ref (sc, before, s7_car (entry));
      if (s7_is_pair (was) && s7_is_eq (s7_car (was), s7_cdr (entry)))
        continue;
      if (n == cap)
        bindings = realloc (bindings, (cap += 32) * sizeof *bindings);
      bindings[n].name = name;
      bindings[n].value = s7_cdr (entry);
      n++;
    }
  qsort (bindings, n, sizeof *bindings, s7_binding_cmp);
  for (i = 0; i < n && rc == 0; i++)
    {
      s7_pointer r = s7_amk_apply (sc, "import", 0, s7_amk_table (sc, "amk-export-one"),
                                   s7_list (sc, 2, s7_make_string (sc, bindings[i].name), bindings[i].value));
      (void) r;
      if (s7_is_eq (r, s7_make_symbol (sc, "amk-guest-error")))
        rc = 1;
      else
        {
          s7_pointer got = s7_amk_table (sc, "*amk-export-names*");
          if (s7_is_string (got) && *s7_string (got))
            s7_names_add (&names, s7_string (got));
        }
    }
  free (bindings);
  if (names.n > 0)
    out->write (out, names.s, names.n);
  out->write (out, "\n", 1);
  free (names.s);
  return rc;
}

/* (amk-export-one name value), the export of one binding run under the catch, leaving the names it produced in the rootlet. */
static s7_pointer
s7_amk_export_one (s7_scheme *sc, s7_pointer args)
{
  struct s7_names names = { NULL, 0, 0 };
  s7_pointer r = s7_export_value (sc, s7_string (s7_car (args)), s7_cadr (args), &names);
  s7_define_variable (sc, "*amk-export-names*", s7_make_string (sc, names.s ? names.s : ""));
  free (names.s);
  return r;
}

/* The create member: a kept interpreter, which make holds for the life of the process, with the handle bound and the export helper defined. */
__attribute__ ((visibility ("default"))) void *
s7_create (void)
{
  s7_scheme *sc = s7_state_open ();
  if (sc == NULL)
    return NULL;
  s7_define_function (sc, "amk-export-one", s7_amk_export_one, 2, 0, false, "one binding into make");
  s7_define_variable (sc, "*amk-kept*", s7_t (sc));
  return sc;
}

/* exec runs the chunk in the interpreter with what it prints to the sink; import runs it with output on stderr, then hands make what it left in the rootlet and the sink their names. */
static int
s7_run_op (void *state, struct amk_sink *out, const char *op, const char *prog)
{
  s7_scheme *sc = state;
  struct amk_capture capture;
  int export = strcmp (op, "import") == 0;
  int rc;

  if (prog == NULL)
    {
      fprintf (stderr, "s7.%s: no chunk\n", op);
      return 2;
    }

  if (!export)
    {
      amk_capture_begin_to (&capture, out);
      rc = s7_run_chunk (sc, prog);
      amk_capture_end (&capture, out);
      return rc;
    }

  s7_snapshot_globals (sc);
  amk_capture_begin (&capture);
  rc = s7_run_chunk (sc, prog);
  amk_capture_end (&capture, &amk_sink_stderr);
  if (rc == 0)
    rc = s7_export_globals (sc, out);
  return rc;
}

__attribute__ ((visibility ("default"))) int
s7_exec (void *state, struct amk_sink *out, const char *prog)
{
  return s7_run_op (state, out, "exec", prog);
}

__attribute__ ((visibility ("default"))) int
s7_import (void *state, struct amk_sink *out, const char *prog)
{
  return s7_run_op (state, out, "import", prog);
}

/* The hook primitive: (amk-on event), when the interpreter holds a procedure there, is called with the event as a let. Its output goes to stderr, and an error reports there and is otherwise ignored. */
__attribute__ ((visibility ("default"))) void
s7_hook (void *state, const char *event, const char *target, const char *status, int exit_code, int exit_sig, long pid)
{
  s7_scheme *sc = state;
  struct amk_capture capture;
  s7_pointer fn, e;
  char who[64];

  fn = s7_hash_table_ref (sc, s7_amk_table (sc, "*amk-on*"), s7_make_symbol (sc, event));
  if (!s7_is_procedure (fn))
    return;
  e = s7_inlet (sc, s7_list (sc, 12,
                             s7_make_symbol (sc, "event"), s7_make_string (sc, event),
                             s7_make_symbol (sc, "target"), s7_make_string (sc, target),
                             s7_make_symbol (sc, "status"), s7_make_string (sc, status),
                             s7_make_symbol (sc, "code"), s7_make_integer (sc, exit_code),
                             s7_make_symbol (sc, "signal"), s7_make_integer (sc, exit_sig),
                             s7_make_symbol (sc, "pid"), s7_make_integer (sc, pid)));
  snprintf (who, sizeof who, "hook %s", event);
  amk_capture_begin (&capture);
  s7_amk_apply (sc, who, 0, fn, s7_list (sc, 1, e));
  amk_capture_end (&capture, &amk_sink_stderr);
}

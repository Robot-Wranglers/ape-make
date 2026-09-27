/* The s7 guest's entry point: amk links the interpreter, not the s7 repl, so it supplies this. */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#include "s7.h"
#include "amk_guest.h"

/* The one interpreter the persistent entry and the hook share, kept for the life of the process. */
static s7_scheme *persistent;

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
  s = amk_var_get (name);
  if (s == NULL)
    return s7_f (sc);
  r = s7_make_string (sc, s);
  gmk_free (s);
  return r;
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

/* A procedure applied under a catch: an error reports on stderr with the caller's name and answers the guest error symbol. */
static s7_pointer
s7_amk_apply (s7_scheme *sc, const char *who, s7_pointer fn, s7_pointer args)
{
  s7_define_variable (sc, "*amk-call-who*", s7_make_string (sc, who));
  s7_define_variable (sc, "*amk-call-fn*", fn);
  s7_define_variable (sc, "*amk-call-args*", args);
  return s7_call_with_catch (sc, s7_t (sc), s7_amk_table (sc, "amk-call-thunk"), s7_amk_table (sc, "amk-call-handler"));
}

/* make's call into a defined function: the arguments as strings, the result as text, and an error reported on stderr and answered empty. */
static char *
s7_func_call (const char *nm, unsigned int argc, char **argv)
{
  s7_scheme *sc = persistent;
  s7_pointer fn, args = NULL, result;
  char who[300];
  char *text, *out;
  unsigned int i;

  if (sc == NULL)
    return NULL;
  fn = s7_hash_table_ref (sc, s7_amk_table (sc, "*amk-funcs*"), s7_make_symbol (sc, nm));
  if (!s7_is_procedure (fn))
    return NULL;
  args = s7_nil (sc);
  for (i = argc; i > 0; i--)
    args = s7_cons (sc, s7_make_string (sc, argv[i - 1]), args);
  snprintf (who, sizeof who, "$(%s ...)", nm);
  result = s7_amk_apply (sc, who, fn, args);
  if (s7_is_eq (result, s7_make_symbol (sc, "amk-guest-error")))
    return NULL;
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
  if (s7_hash_table_ref (sc, funcs, sym) == s7_f (sc))
    {
      if (amk_function_exists (name))
        return s7_error (sc, s7_make_symbol (sc, "amk-error"),
                         s7_list (sc, 2, s7_make_string (sc, "amk-func: ~A is a make function already"), sym));
      gmk_add_function (name, s7_func_call, 0, 0, 0);
    }
  s7_hash_table_set (sc, funcs, sym, fn);
  return s7_unspecified (sc);
}

/* (amk-func name fn): make gains a function of that name whose arguments, expanded, reach fn as strings and whose result is what fn returns; only the persistent state outlives the call to answer. */
static s7_pointer
s7_amk_func (s7_scheme *sc, s7_pointer args)
{
  s7_pointer err = s7_amk_need_make (sc, "amk-func");
  const char *name;
  if (err != NULL)
    return err;
  if (sc != persistent)
    return s7_error (sc, s7_make_symbol (sc, "amk-error"),
                     s7_list (sc, 1, s7_make_string (sc, "amk-func: only from s7.persistent, since a one-shot call's state ends with the call")));
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

/* The handle: expand, eval, func, and the two dilambdas, so generalized set! reaches their setters; the call, chunk, and hook plumbing lives beside them in the rootlet, and a chunk is read in the rootlet so its defines persist. */
static const char *s7_amk_prelude =
  "(begin"
  " (define *amk-funcs* (make-hash-table))"
  " (define *amk-on* (make-hash-table))"
  " (define amk-input \"\")"
  " (define *amk-call-who* \"\")"
  " (define *amk-call-fn* #f)"
  " (define *amk-call-args* ())"
  " (define *amk-chunk* \"\")"
  " (define (amk-chunk-thunk) (eval-string (string-append \"(begin \" *amk-chunk* \"\\n)\") (rootlet)))"
  " (define (amk-call-thunk) (apply *amk-call-fn* *amk-call-args*))"
  " (define (amk-call-handler type info)"
  "   (if (string=? *amk-call-who* \"\")"
  "       (format *stderr* \"s7: ~A~%\" (cons type info))"
  "       (format *stderr* \"s7 ~A: ~A~%\" *amk-call-who* (cons type info)))"
  "   'amk-guest-error))";

static void
s7_bind_amk (s7_scheme *sc)
{
  s7_define_function (sc, "amk-expand", s7_amk_expand, 1, 0, false, "(amk-expand text) the text expanded by make");
  s7_define_function (sc, "amk-eval", s7_amk_eval, 1, 0, false, "(amk-eval text) the text read by make as makefile syntax");
  s7_define_function (sc, "amk-func", s7_amk_func, 2, 0, false, "(amk-func name fn) defines a make function");
  s7_dilambda (sc, "amk-var", s7_amk_var, 1, 0, s7_amk_var_set, 2, 0,
               "(amk-var name) a make variable expanded, or #f; (set! (amk-var name) value) defines it");
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
  s7_define_variable (sc, "*amk-chunk*", s7_make_string (sc, src));
  result = s7_call_with_catch (sc, s7_t (sc), s7_amk_table (sc, "amk-chunk-thunk"), s7_amk_table (sc, "amk-call-handler"));
  return s7_is_eq (result, s7_make_symbol (sc, "amk-guest-error")) ? 1 : 0;
}

/* s7 reads its own stdin through a fixed 1024-byte fgets that keeps the newline and answers
   an empty string at end of file, so a guest given input reads a string port instead: make
   already staged that input as a regular file, which is the only case worth slurping.  */
static char *
s7_guest_slurp_stdin (void)
{
  struct stat st;
  char *buf;
  size_t len = 0;

  if (fstat (STDIN_FILENO, &st) != 0 || !S_ISREG (st.st_mode))
    return NULL;

  buf = malloc ((size_t) st.st_size + 1);
  if (buf == NULL)
    return NULL;
  while (len < (size_t) st.st_size)
    {
      size_t r = fread (buf + len, 1, (size_t) st.st_size - len, stdin);
      if (r == 0)
        break;
      len += r;
    }
  buf[len] = '\0';
  return buf;
}

/* An interpreter with the handle bound, or null. */
static s7_scheme *
s7_state_open (void)
{
  s7_scheme *sc = s7_init ();
  if (sc == NULL)
    {
      fprintf (stderr, "s7: cannot create interpreter\n");
      return NULL;
    }
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
  persistent = NULL;
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
                           s7_list (sc, 3, s7_make_string (sc, "amk export: ~A has a key make cannot spell: ~S"),
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
      s7_pointer r = s7_amk_apply (sc, "export", s7_amk_table (sc, "amk-export-one"),
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

/* The persistent entry: one interpreter for the life of the process, so a definition one chunk makes is there for the next. What the chunk prints goes to the sink, and argv[2], if any, is amk-input; the export form instead exports what the chunk left in the rootlet. */
__attribute__ ((visibility ("default"))) int
s7_persist_main (struct amk_sink *out, int argc, char **argv)
{
  struct amk_capture capture;
  const char *input = argc > 2 && argv[2] != NULL ? argv[2] : "";
  int export = amk_entry_is (argv[0], "export");
  s7_scheme *sc;
  int rc;

  if (argc < 2 || argv[1] == NULL)
    {
      fprintf (stderr, "s7.persistent: no chunk\n");
      return 2;
    }
  if (persistent == NULL)
    {
      persistent = s7_state_open ();
      if (persistent == NULL)
        return 1;
      s7_define_function (persistent, "amk-export-one", s7_amk_export_one, 2, 0, false, "one binding into make");
    }
  sc = persistent;
  s7_define_variable (sc, "amk-input", s7_make_string (sc, input));

  if (!export)
    {
      amk_capture_begin (&capture);
      rc = s7_run_chunk (sc, argv[1]);
      amk_capture_end (&capture, out);
      return rc;
    }

  s7_snapshot_globals (sc);
  amk_capture_begin (&capture);
  rc = s7_run_chunk (sc, argv[1]);
  amk_capture_end (&capture, &amk_sink_stderr);
  if (rc == 0)
    rc = s7_export_globals (sc, out);
  return rc;
}

/* The hook entry: (amk-on event), when the persistent state holds a procedure there, is called with the event as a let. Its output goes to stderr, and an error reports there and is otherwise ignored. */
__attribute__ ((visibility ("default"))) void
s7_hook_main (const char *event, const char *target, const char *status, int exit_code, int exit_sig, long pid)
{
  s7_scheme *sc = persistent;
  struct amk_capture capture;
  s7_pointer fn, e;
  char who[64];

  if (sc == NULL)
    return;
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
  s7_amk_apply (sc, who, fn, s7_list (sc, 1, e));
  amk_capture_end (&capture, &amk_sink_stderr);
}

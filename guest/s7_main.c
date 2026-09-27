/* The s7 guest's entry point: amk links the interpreter, not the s7 repl, so it supplies this. */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#include "s7.h"
#include "amk_guest.h"

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

/* (set! (amk-var name) value) defines a simple variable with the value's display text; #f is the empty string. */
static s7_pointer
s7_amk_var_set (s7_scheme *sc, s7_pointer args)
{
  s7_pointer err = s7_amk_need_make (sc, "amk-var");
  const char *name;
  s7_pointer value;
  if (err != NULL)
    return err;
  name = s7_amk_name (sc, args, "amk-var");
  value = s7_cadr (args);
  if (value == s7_f (sc))
    amk_var_set (name, "");
  else if (s7_is_string (value))
    amk_var_set (name, s7_string (value));
  else
    {
      char *text = s7_object_to_c_string (sc, value);
      amk_var_set (name, text ? text : "");
      free (text);
    }
  return value;
}

/* amk-var is a dilambda, so generalized set! reaches the setter. */
static void
s7_bind_amk (s7_scheme *sc)
{
  s7_define_function (sc, "amk-expand", s7_amk_expand, 1, 0, false, "(amk-expand text) the text expanded by make");
  s7_define_function (sc, "amk-eval", s7_amk_eval, 1, 0, false, "(amk-eval text) the text read by make as makefile syntax");
  s7_dilambda (sc, "amk-var", s7_amk_var, 1, 0, s7_amk_var_set, 2, 0,
               "(amk-var name) a make variable expanded, or #f; (set! (amk-var name) value) defines it");
}

/* An uncaught error reports itself and answers with a sentinel, so the chunk never unwinds past s7. */
static const char *s7_guest_wrapper =
  "(catch #t (lambda () %s) (lambda args (format *stderr* \"s7: ~A~%%\" args) 'amk-guest-error))";

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

/* argv[1] is Scheme source text rather than a command line; whatever it prints is the result. */
__attribute__ ((visibility ("default"))) int
s7_run_main (int argc, char **argv)
{
  s7_scheme *s7;
  s7_pointer result;
  char *chunk, *input;
  size_t len;
  int rc;

  if (argc < 2 || argv[1] == NULL)
    {
      fprintf (stderr, "s7: no chunk\n");
      return 2;
    }

  s7 = s7_init ();
  if (s7 == NULL)
    {
      fprintf (stderr, "s7: cannot create interpreter\n");
      return 1;
    }
  s7_bind_amk (s7);

  len = strlen (s7_guest_wrapper) + strlen (argv[1]) + 1;
  chunk = malloc (len);
  if (chunk == NULL)
    {
      fprintf (stderr, "s7: out of memory\n");
      s7_free (s7);
      return 1;
    }
  snprintf (chunk, len, s7_guest_wrapper, argv[1]);

  input = s7_guest_slurp_stdin ();
  if (input != NULL)
    s7_set_current_input_port (s7, s7_open_input_string (s7, input));

  result = s7_eval_c_string (s7, chunk);
  rc = s7_is_eq (result, s7_make_symbol (s7, "amk-guest-error")) ? 1 : 0;

  free (chunk);
  free (input);
  s7_free (s7);
  fflush (stdout);
  return rc;
}

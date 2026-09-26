/* The s7 guest's entry point: amk links the interpreter, not the s7 repl, so it supplies this. */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#include "s7.h"

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

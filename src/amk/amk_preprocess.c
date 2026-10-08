/* The define decorator as a rewrite, the awk rule in the payload run through the engine, so one rule serves amk and anything that calls amk for it.  This side is the fast path, the run, and the three places text comes from: a makefile before its parse, evaluated text, and the command that does only the rewrite.  */

#include "makeint.h"
#include "variable.h"
#include "amk.h"

#define AMK_GLOBALS_AWK "/zip/lang/amk/awklib/globals.awk"
#define AMK_FUNCTIONS_AWK "/zip/lang/amk/awklib/functions.awk"
#define AMK_PREPROCESS_AWK "/zip/lang/amk/comp/definedecorators.awk"
#define AMK_JOINBODY_AWK "/zip/lang/amk/awklib/joinbody.awk"
#define AMK_CALLFORMS_AWK "/zip/lang/amk/awklib/callforms.awk"
#define AMK_TARGETDECORATORS_AWK "/zip/lang/amk/comp/targetdecorators.awk"

/* Whether the rewrite is on: the environment turns it off with any value but empty or zero.  */
static int
preprocess_on (void)
{
  static int on = -1;
  if (on < 0)
    {
      const char *v = getenv ("AMK_DISABLE_PREPROCESS");
      on = v == NULL || *v == '\0' || strcmp (v, "0") == 0;
    }
  return on;
}

/* The word at p followed by a blank, or null.  */
static const char *
after_word (const char *p, const char *word)
{
  size_t n = strlen (word);
  if (strncmp (p, word, n) != 0 || (p[n] != ' ' && p[n] != '\t'))
    return NULL;
  p += n;
  while (*p == ' ' || *p == '\t')
    p++;
  return p;
}

/* Whether any line is a define that ends in the word endef: a one-line define.  */
static int
has_oneliner (const char *text)
{
  const char *p = text, *l, *w, *end;
  while (p != NULL && *p != '\0')
    {
      l = p;
      end = strchr (p, '\n');
      if (end == NULL)
        end = p + strlen (p);
      while (*l == ' ' || *l == '\t')
        l++;
      while ((w = after_word (l, "override")) != NULL || (w = after_word (l, "export")) != NULL || (w = after_word (l, "private")) != NULL)
        l = w;
      if ((l = after_word (l, "define")) != NULL)
        {
          while (end > l && (end[-1] == ' ' || end[-1] == '\t' || end[-1] == '\r'))
            end--;
          if (end - l > 6 && strncmp (end - 5, "endef", 5) == 0 && (end[-6] == ' ' || end[-6] == '\t'))
            return 1;
        }
      p = strchr (p, '\n');
      if (p != NULL)
        p++;
    }
  return 0;
}

/* The text with its at lines and one-line defines rewritten, or null when it has neither; the rule's own message has gone to stderr when the status says it failed.  The define decorators run first, then the target decorators over what they leave, each at line nothing takes printing back as written.  */
char *
amk_preprocess (const char *text, const char *filenm, int *status)
{
  const struct amk_engine *e;
  char *av[12], *tv[14], *file, *out, *next;
  *status = 0;
  if (text[0] != '@' && strstr (text, "\n@") == NULL && !has_oneliner (text))
    return NULL;
  e = amk_engine_by_name ("awk");
  if (e == NULL)
    O (fatal, NILF, _("a define decorator needs the awk engine, which this build leaves out"));
  file = xmalloc (strlen (filenm) + 6);
  sprintf (file, "file=%s", filenm);
  av[0] = (char *) "awk";
  av[1] = (char *) "-v";
  av[2] = file;
  av[3] = (char *) "-f";
  av[4] = (char *) AMK_GLOBALS_AWK;
  av[5] = (char *) "-f";
  av[6] = (char *) AMK_FUNCTIONS_AWK;
  av[7] = (char *) "-f";
  av[8] = (char *) AMK_PREPROCESS_AWK;
  av[9] = (char *) "-f";
  av[10] = (char *) AMK_JOINBODY_AWK;
  av[11] = NULL;
  out = amk_engine_filter (e, 11, av, text, status);
  if (*status == 0)
    {
      tv[0] = (char *) "awk";
      tv[1] = (char *) "-v";
      tv[2] = file;
      tv[3] = (char *) "-v";
      tv[4] = (char *) "TARGET_DECORATOR_PREFIX=@";
      tv[5] = (char *) "-f";
      tv[6] = (char *) AMK_GLOBALS_AWK;
      tv[7] = (char *) "-f";
      tv[8] = (char *) AMK_FUNCTIONS_AWK;
      tv[9] = (char *) "-f";
      tv[10] = (char *) AMK_CALLFORMS_AWK;
      tv[11] = (char *) "-f";
      tv[12] = (char *) AMK_TARGETDECORATORS_AWK;
      tv[13] = NULL;
      next = amk_engine_filter (e, 13, tv, out, status);
      free (out);
      out = next;
    }
  free (file);
  return out;
}

/* A file's bytes as text.  */
static char *
read_text (const char *path)
{
  size_t len;
  unsigned char *buf = amk_slurp (path, &len);
  if (buf == NULL)
    return NULL;
  buf = xrealloc (buf, len + 1);
  buf[len] = '\0';
  return (char *) buf;
}

/* A makefile's text with its at lines rewritten, for the reader to parse in place of the stream, or null when it has none.  */
char *
amk_preprocess_file (FILE *fp, const char *filenm)
{
  char *text, *out;
  int status;
  (void) fp;
  if (!preprocess_on ())
    return NULL;
  text = read_text (filenm);
  if (text == NULL)
    pfatal_with_name (filenm);
  out = amk_preprocess (text, filenm, &status);
  free (text);
  if (status != 0)
    die (MAKE_FAILURE);
  return out;
}

/* Evaluated text with its at lines rewritten, or null when it has none.  */
char *
amk_preprocess_text (const char *text, const floc *flocp)
{
  char *out;
  int status;
  if (!preprocess_on ())
    return NULL;
  out = amk_preprocess (text, flocp->filenm != NULL ? flocp->filenm : "-", &status);
  if (status != 0)
    die (MAKE_FAILURE);
  return out;
}

/* The preprocessor as a command: one makefile, or standard input, rewritten onto standard output and nothing read or run.  */
int
amk_preprocess_main (int argc, char **argv)
{
  const char *path = argc > 0 ? argv[0] : "-";
  char *text = read_text (strcmp (path, "-") == 0 ? "/dev/stdin" : path);
  char *out;
  int status;
  if (text == NULL)
    {
      fprintf (stderr, "amk: %s: %s\n", path, strerror (errno));
      return 2;
    }
  out = amk_preprocess (text, path, &status);
  if (status == 0)
    fputs (out != NULL ? out : text, stdout);
  free (out);
  free (text);
  return status;
}

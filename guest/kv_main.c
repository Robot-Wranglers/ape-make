/* The kv guest's kept-state primitives: a state is a text of key=value lines make holds, shaped like a table rather than a language, and it meets the workspace row's contract with no library behind it. */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* make's sink, where a run's result goes: one write function, and make decides where the bytes land. */
struct amk_sink
{
  void (*write) (struct amk_sink *, const char *, size_t);
};

#define KV_STATUS_USAGE 2

/* The line for a key in the text, or null; the match is the whole key before the equals sign. */
static const char *
kv_find (const char *text, const char *key)
{
  size_t n = strlen (key);
  const char *p = text;
  while (*p != '\0')
    {
      if (strncmp (p, key, n) == 0 && p[n] == '=')
        return p;
      p = strchr (p, '\n');
      if (p == NULL)
        break;
      ++p;
    }
  return NULL;
}

/* The text with the key set to the value, the old line dropped and the new one appended. */
static char *
kv_set (const char *text, const char *key, const char *value)
{
  const char *old = kv_find (text, key);
  size_t before = old != NULL ? (size_t) (old - text) : strlen (text);
  const char *after = "";
  char *next;
  if (old != NULL)
    {
      const char *nl = strchr (old, '\n');
      after = nl != NULL ? nl + 1 : old + strlen (old);
    }
  next = malloc (before + strlen (after) + strlen (key) + strlen (value) + 3);
  if (next == NULL)
    return NULL;
  memcpy (next, text, before);
  strcpy (next + before, after);
  sprintf (next + strlen (next), "%s=%s\n", key, value);
  return next;
}

static char *
kv_dup (const char *s)
{
  char *d = malloc (strlen (s) + 1);
  if (d != NULL)
    strcpy (d, s);
  return d;
}

/* get: the whole text under the whole program, else the one key's value on a line of its own. */
static int
kv_get (const char *text, struct amk_sink *out, const char *key)
{
  const char *line;
  if (strcmp (key, "*") == 0)
    {
      out->write (out, text, strlen (text));
      return 0;
    }
  line = kv_find (text, key);
  if (line == NULL)
    return 1;
  line += strlen (key) + 1;
  out->write (out, line, strcspn (line, "\n"));
  out->write (out, "\n", 1);
  return 0;
}

/* The open primitive: a fresh state holding no lines. */
__attribute__ ((visibility ("default"))) void *
kv_open (void)
{
  char **state = malloc (sizeof *state);
  if (state == NULL)
    return NULL;
  *state = kv_dup ("");
  return state;
}

/* The run primitive: get key, update key value, or load text on the state, with the output to the sink. */
__attribute__ ((visibility ("default"))) int
kv_run (void *state, struct amk_sink *out, const char *op, const char *prog)
{
  char **text = state;
  char *next;
  if (prog == NULL)
    prog = "";
  if (strcmp (op, "get") == 0)
    {
      if (*prog == '\0')
        {
          fprintf (stderr, "kv.get: no key\n");
          return KV_STATUS_USAGE;
        }
      return kv_get (*text, out, prog);
    }
  if (strcmp (op, "update") == 0)
    {
      size_t n = strcspn (prog, " \t");
      const char *value = prog + n;
      char *key;
      if (n == 0)
        {
          fprintf (stderr, "kv.update: no key\n");
          return KV_STATUS_USAGE;
        }
      while (*value == ' ' || *value == '\t')
        ++value;
      key = malloc (n + 1);
      if (key == NULL)
        return KV_STATUS_USAGE;
      memcpy (key, prog, n);
      key[n] = '\0';
      next = kv_set (*text, key, value);
      free (key);
      if (next == NULL)
        return KV_STATUS_USAGE;
      free (*text);
      *text = next;
      return 0;
    }
  if (strcmp (op, "load") == 0)
    {
      size_t n = strlen (prog);
      next = malloc (n + 2);
      if (next == NULL)
        return KV_STATUS_USAGE;
      strcpy (next, prog);
      if (n > 0 && next[n - 1] != '\n')
        strcat (next, "\n");
      free (*text);
      *text = next;
      return 0;
    }
  fprintf (stderr, "kv: unknown operation %s; one of get, update, load\n", op);
  return KV_STATUS_USAGE;
}

static void
kv_stdout_write (struct amk_sink *s, const char *p, size_t n)
{
  (void) s;
  fwrite (p, 1, n, stdout);
}

/* The command line: a get of one key, or an update of a key to a value, over the key=value lines on stdin, the result on stdout. */
__attribute__ ((visibility ("default"))) int
kv_main (int argc, char **argv)
{
  struct amk_sink out = { kv_stdout_write };
  char *text = kv_dup ("");
  char buf[4096];
  size_t len = 0, cap = 0;
  int rc;
  if (argc < 3 || (strcmp (argv[1], "get") != 0 && strcmp (argv[1], "update") != 0))
    {
      fprintf (stderr, "usage: kv get key | kv update key value; the key=value lines on stdin\n");
      return KV_STATUS_USAGE;
    }
  while ((len = fread (buf, 1, sizeof buf, stdin)) > 0)
    {
      text = realloc (text, cap + len + 1);
      memcpy (text + cap, buf, len);
      cap += len;
      text[cap] = '\0';
    }
  if (strcmp (argv[1], "get") == 0)
    return kv_get (text, &out, argv[2]);
  {
    char *next = kv_set (text, argv[2], argc > 3 ? argv[3] : "");
    rc = next == NULL ? KV_STATUS_USAGE : 0;
    if (next != NULL)
      fputs (next, stdout);
  }
  return rc;
}

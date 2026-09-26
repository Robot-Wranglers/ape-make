/* The jq guest's kept-state primitives: a state is one JSON value make holds, and jq programs run over it through libjq with no fork; the filter runs a program over an input text with no state. */

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "jq.h"
#include "jv.h"

/* make's sink, where a run's result goes: one write function, and make decides where the bytes land. */
struct amk_sink
{
  void (*write) (struct amk_sink *, const char *, size_t);
};

/* Compiled programs, keyed by the bound names and the program text. */
struct jq_prog
{
  char *key;
  jq_state *jq;
};
static struct jq_prog *progs;
static int nprogs;

#define JQ_MAXARGS 32
#define JQ_STATUS_USAGE 2
#define JQ_STATUS_COMPILE 3
#define JQ_STATUS_RUN 5

static void
jq_emit (struct amk_sink *out, const char *s, size_t n)
{
  out->write (out, s, n);
}

/* One word off the line as a shell would read it, quotes honored; the word is written into buf and p moves past it. */
static int
jq_word (const char **p, char *buf, size_t size)
{
  const char *s = *p;
  size_t n = 0;
  char quote = 0;
  while (*s == ' ' || *s == '\t')
    ++s;
  if (*s == '\0')
    {
      *p = s;
      return 0;
    }
  while (*s && (quote || (*s != ' ' && *s != '\t')))
    {
      if (!quote && (*s == '\'' || *s == '"'))
        quote = *s++;
      else if (*s == quote)
        {
          quote = 0;
          ++s;
        }
      else if (quote == '"' && *s == '\\' && s[1] == 'n')
        {
          if (n + 1 < size)
            buf[n++] = '\n';
          s += 2;
        }
      else
        {
          if (*s == '\\' && s[1] && (!quote || (quote == '"' && (s[1] == '"' || s[1] == '\\'))))
            ++s;
          if (n + 1 < size)
            buf[n++] = *s;
          ++s;
        }
    }
  buf[n] = '\0';
  *p = s;
  return 1;
}

/* The program compiled once per distinct text and set of bound names: the bindings ride in on the input beside the value, so a new value for a name is never a recompile. */
static jq_state *
jq_compiled (const char *prog, char **names, int nnames)
{
  size_t klen = strlen (prog) + 2, tlen = strlen (prog) + 64;
  char *key, *text, *w;
  jq_state *jq;
  int i;

  for (i = 0; i < nnames; i++)
    {
      klen += strlen (names[i]) + 1;
      tlen += strlen (names[i]) * 2 + 16;
    }
  key = malloc (klen);
  w = key;
  for (i = 0; i < nnames; i++)
    w += sprintf (w, "%s ", names[i]);
  sprintf (w, "\n%s", prog);
  for (i = 0; i < nprogs; i++)
    if (strcmp (progs[i].key, key) == 0)
      {
        free (key);
        return progs[i].jq;
      }

  text = malloc (tlen);
  w = text;
  for (i = 0; i < nnames; i++)
    w += sprintf (w, ".args.%s as $%s | ", names[i], names[i]);
  sprintf (w, ".value | (\n%s\n)", prog);
  jq = jq_init ();
  if (jq == NULL || !jq_compile (jq, text))
    {
      if (jq != NULL)
        jq_teardown (&jq);
      free (text);
      free (key);
      return NULL;
    }
  free (text);
  progs = realloc (progs, (nprogs + 1) * sizeof *progs);
  progs[nprogs].key = key;
  progs[nprogs].jq = jq;
  nprogs++;
  return jq;
}

/* One output as the jq tool prints it: JSON, compact or indented by two as the tool's default, or the bare text of a string under raw. */
static void
jq_emit_value (struct amk_sink *out, jv v, int raw, int compact)
{
  if (raw && jv_get_kind (v) == JV_KIND_STRING)
    {
      jq_emit (out, jv_string_value (v), (size_t) jv_string_length_bytes (jv_copy (v)));
      jv_free (v);
    }
  else
    {
      jv s = jv_dump_string (v, compact ? 0 : JV_PRINT_PRETTY | JV_PRINT_INDENT_FLAGS (2));
      jq_emit (out, jv_string_value (s), strlen (jv_string_value (s)));
      jv_free (s);
    }
  jq_emit (out, "\n", 1);
}

/* After the last output: a halt's code and message, or an uncaught error's message, on stderr; the status the tool would exit with. */
static int
jq_finish (jq_state *jq, jv last)
{
  int rc = 0;
  if (jq_halted (jq))
    {
      jv code = jq_get_exit_code (jq);
      jv msg = jq_get_error_message (jq);
      if (jv_get_kind (code) == JV_KIND_NUMBER)
        rc = (int) jv_number_value (code);
      else if (jv_is_valid (code))
        rc = JQ_STATUS_RUN;
      jv_free (code);
      if (jv_get_kind (msg) == JV_KIND_STRING)
        fputs (jv_string_value (msg), stderr);
      else if (jv_is_valid (msg) && jv_get_kind (msg) != JV_KIND_NULL)
        {
          msg = jv_dump_string (msg, 0);
          fprintf (stderr, "%s\n", jv_string_value (msg));
        }
      fflush (stderr);
      jv_free (msg);
    }
  else if (jv_invalid_has_msg (jv_copy (last)))
    {
      jv msg = jv_invalid_get_msg (jv_copy (last));
      if (jv_get_kind (msg) != JV_KIND_STRING)
        msg = jv_dump_string (msg, 0);
      fprintf (stderr, "jq: error: %s\n", jv_string_value (msg));
      fflush (stderr);
      jv_free (msg);
      rc = JQ_STATUS_RUN;
    }
  jv_free (last);
  return rc;
}

/* The values a filter runs over: every JSON text in the input, or all of them as one array under slurp, or null under null-input. */
static jv
jq_filter_inputs (const char *text, int slurp, int null_input)
{
  jv all = jv_array ();
  struct jv_parser *parser;
  jv v;

  if (null_input)
    return jv_array_append (all, jv_null ());
  parser = jv_parser_new (0);
  jv_parser_set_buf (parser, text, (int) strlen (text), 0);
  while (jv_is_valid (v = jv_parser_next (parser)))
    all = jv_array_append (all, v);
  if (jv_invalid_has_msg (jv_copy (v)))
    {
      jv msg = jv_invalid_get_msg (v);
      fprintf (stderr, "jq: filter: %s\n", jv_string_value (msg));
      jv_free (msg);
      jv_free (all);
      jv_parser_free (parser);
      return jv_invalid ();
    }
  jv_free (v);
  jv_parser_free (parser);
  if (slurp)
    return jv_array_append (jv_array (), all);
  return all;
}

/* Run the program, its leading options read first: get emits every output, update keeps the first in the state and emits the rest, and filter, with no state, runs over the input text. The state changes only when the run ends clean. */
static int
jq_run_op (jv *state, struct amk_sink *out, const char *op, const char *rest, const char *text)
{
  char *names[JQ_MAXARGS];
  jv values[JQ_MAXARGS];
  int nargs = 0, raw = 0, compact = state != NULL, slurp = 0, null_input = 0, exit_status = 0, i, rc, n = 0, ninputs;
  char word[4096], key[256];
  const char *p = rest, *prog;
  jq_state *jq;
  jv inputs = jv_invalid (), result = jv_invalid (), kept = jv_invalid (), emitted = jv_invalid ();

  for (;;)
    {
      prog = p;
      if (!jq_word (&p, word, sizeof word))
        break;
      if (strcmp (word, "-r") == 0)
        raw = 1;
      else if (strcmp (word, "-c") == 0)
        compact = 1;
      else if (strcmp (word, "-e") == 0)
        exit_status = 1;
      else if (strcmp (word, "-n") == 0)
        null_input = 1;
      else if (strcmp (word, "-s") == 0)
        slurp = 1;
      else if (word[0] == '-' && word[1] != '\0' && strcmp (word, "--arg") != 0 && strcmp (word, "--argjson") != 0
               && strcmp (word, "--slurpfile") != 0 && strcmp (word, "--rawfile") != 0)
        {
          fprintf (stderr, "jq.%s: unsupported option %s; one of -r -c -e -n -s --arg --argjson --slurpfile --rawfile\n", op, word);
          rc = JQ_STATUS_USAGE;
          goto done;
        }
      else if (strcmp (word, "--arg") == 0 || strcmp (word, "--argjson") == 0
               || strcmp (word, "--slurpfile") == 0 || strcmp (word, "--rawfile") == 0)
        {
          char *opt = strdup (word);
          int json = strcmp (opt, "--argjson") == 0, slurpfile = strcmp (opt, "--slurpfile") == 0, rawfile = strcmp (opt, "--rawfile") == 0;
          if (nargs == JQ_MAXARGS || !jq_word (&p, key, sizeof key) || !jq_word (&p, word, sizeof word))
            {
              fprintf (stderr, "jq.%s: %s takes a name and a value\n", op, opt);
              free (opt);
              rc = JQ_STATUS_USAGE;
              goto done;
            }
          free (opt);
          values[nargs] = json ? jv_parse (word) : slurpfile ? jv_load_file (word, 0) : rawfile ? jv_load_file (word, 1) : jv_string (word);
          if (!jv_is_valid (values[nargs]))
            {
              jv msg = jv_invalid_get_msg (values[nargs]);
              fprintf (stderr, "jq.%s: --argjson %s: %s\n", op, key, jv_is_valid (msg) ? jv_string_value (msg) : "invalid JSON");
              jv_free (msg);
              rc = JQ_STATUS_USAGE;
              goto done;
            }
          names[nargs++] = strdup (key);
        }
      else
        break;
    }
  while (*prog == ' ' || *prog == '\t')
    ++prog;
  if (*prog == '\0')
    {
      fprintf (stderr, "jq.%s: no program\n", op);
      rc = JQ_STATUS_USAGE;
      goto done;
    }

  jq = jq_compiled (prog, names, nargs);
  if (jq == NULL)
    {
      rc = JQ_STATUS_COMPILE;
      goto done;
    }

  if (state != NULL)
    inputs = jv_array_append (jv_array (), jv_copy (*state));
  else
    inputs = jq_filter_inputs (text != NULL ? text : "", slurp, null_input);
  if (!jv_is_valid (inputs))
    {
      rc = JQ_STATUS_USAGE;
      goto done;
    }

  emitted = jv_array ();
  ninputs = jv_array_length (jv_copy (inputs));
  for (i = 0; i < ninputs; i++)
    {
      jv input = jv_object (), args = jv_object ();
      int k;
      input = jv_object_set (input, jv_string ("value"), jv_array_get (jv_copy (inputs), i));
      for (k = 0; k < nargs; k++)
        args = jv_object_set (args, jv_string (names[k]), jv_copy (values[k]));
      input = jv_object_set (input, jv_string ("args"), args);
      jq_start (jq, input, 0);
      while (jv_is_valid (result = jq_next (jq)))
        {
          if (n++ == 0 && state != NULL && strcmp (op, "update") == 0)
            kept = result;
          else
            emitted = jv_array_append (emitted, result);
        }
      rc = jq_finish (jq, result);
      if (rc != 0)
        goto done;
    }
  /* The tool's exit status option: 1 when the last output is false or null, 4 when there was none.  */
  if (exit_status)
    {
      int m = jv_array_length (jv_copy (emitted));
      if (m == 0)
        rc = 4;
      else
        {
          jv last = jv_array_get (jv_copy (emitted), m - 1);
          jv_kind kind = jv_get_kind (last);
          rc = kind == JV_KIND_NULL || kind == JV_KIND_FALSE ? 1 : 0;
          jv_free (last);
        }
    }

  if (jv_is_valid (kept))
    {
      jv_free (*state);
      *state = kept;
      kept = jv_invalid ();
    }
  n = jv_array_length (jv_copy (emitted));
  for (i = 0; i < n; i++)
    jq_emit_value (out, jv_array_get (jv_copy (emitted), i), raw, compact);

done:
  jv_free (inputs);
  jv_free (kept);
  jv_free (emitted);
  for (i = 0; i < nargs; i++)
    {
      free (names[i]);
      jv_free (values[i]);
    }
  return rc;
}

/* load: the one JSON text that is the program becomes the value. */
static int
jq_load (jv *state, const char *text)
{
  jv v = jv_parse (text);
  if (!jv_is_valid (v))
    {
      jv msg = jv_invalid_get_msg (v);
      fprintf (stderr, "jq.load: %s\n", jv_is_valid (msg) ? jv_string_value (msg) : "invalid JSON");
      jv_free (msg);
      return JQ_STATUS_USAGE;
    }
  jv_free (*state);
  *state = v;
  return 0;
}

/* The open primitive: a fresh state holding null. */
__attribute__ ((visibility ("default"))) void *
jq_open (void)
{
  jv *state = malloc (sizeof *state);
  if (state == NULL)
    return NULL;
  *state = jv_null ();
  return state;
}

/* The run primitive: get, update or load on the state, with the output to the sink. */
__attribute__ ((visibility ("default"))) int
jq_run (void *state, struct amk_sink *out, const char *op, const char *prog)
{
  if (strcmp (op, "get") == 0 || strcmp (op, "update") == 0)
    return jq_run_op (state, out, op, prog != NULL ? prog : "", NULL);
  if (strcmp (op, "load") == 0)
    return jq_load (state, prog != NULL ? prog : "");
  fprintf (stderr, "jq: unknown operation %s; one of get, update, load\n", op);
  return JQ_STATUS_USAGE;
}

/* The filter primitive: the program over every JSON text in the input, with no state. */
__attribute__ ((visibility ("default"))) int
jq_filter (struct amk_sink *out, const char *prog, const char *input)
{
  return jq_run_op (NULL, out, "filter", prog != NULL ? prog : "", input);
}

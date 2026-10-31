/* The wasm guest's kept state: a wasm3 runtime holding loaded modules, whose exports become make functions, and the handle a module imports from "amk". The cli stays wasm3's own main. */

#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "wasm3.h"
#include "m3_env.h"
#include "m3_api_libc.h"
#include "m3_api_wasi.h"

#include "amk_guest.h"

/* The stack a runtime gets, wasm3's own default for its cli. */
#define WASM_STACK (64 * 1024)

/* A module's bytes must outlive the module, so each load keeps its copy on the state. */
struct wasm_bytes
{
  uint8_t *data;
  struct wasm_bytes *next;
};

struct wasm_state
{
  IM3Environment env;
  IM3Runtime runtime;
  struct wasm_bytes *bytes;
};

/* Where the state's output goes: make's sink during a call, stderr between calls. */
static struct amk_sink *wasm_sink = &amk_sink_stderr;

static void
wasm_emit (const char *s, size_t n)
{
  wasm_sink->write (wasm_sink, s, n);
}

/* The trap the interpreter answers once the deadline in force has passed. */
static const char wasm_deadline_trap[] = "deadline";

/* wasm3 asks before every call; the clock is read once in a while, and a run past the deadline traps at the next ask. */
M3Result
m3_Yield (void)
{
  static unsigned count;
  if (amk_deadline_active () && (++count & 255) == 0 && amk_deadline_expired ())
    return wasm_deadline_trap;
  return m3Err_none;
}

static void
wasm_need_make (void)
{
  if (!amk_has_db ())
    fprintf (stderr, "wasm: no make database, running outside a makefile\n");
}

/* A guest string into a fresh C string, or null for a span outside the module's memory. */
static char *
wasm_take (IM3Runtime runtime, void *mem, const char *p, uint32_t n)
{
  char *s;
  if ((const void *) p < mem || (uint64_t) (uintptr_t) p + n > (uint64_t) (uintptr_t) mem + m3_GetMemorySize (runtime))
    return NULL;
  s = malloc (n + 1);
  memcpy (s, p, n);
  s[n] = '\0';
  return s;
}

/* A C string into the guest's buffer, as much as fits, answering the whole length; -1 is make's "never seen". */
static int32_t
wasm_give (IM3Runtime runtime, void *mem, char *buf, uint32_t cap, const char *s)
{
  size_t n;
  if (s == NULL)
    return -1;
  n = strlen (s);
  if ((void *) buf >= mem && (uint64_t) (uintptr_t) buf + cap <= (uint64_t) (uintptr_t) mem + m3_GetMemorySize (runtime))
    memcpy (buf, s, n < cap ? n : cap);
  return (int32_t) n;
}

/* amk.print(ptr, len): the bytes to the sink. */
m3ApiRawFunction (wasm_amk_print)
{
  m3ApiGetArgMem (const char *, p)
  m3ApiGetArg (uint32_t, n)
  m3ApiCheckMem (p, n);
  wasm_emit (p, n);
  m3ApiSuccess ();
}

/* amk.var_get(name, name_len, buf, cap) -> len: a variable's expanded value into buf, its whole length back, -1 when make never saw the name. */
m3ApiRawFunction (wasm_amk_var_get)
{
  m3ApiReturnType (int32_t)
  m3ApiGetArgMem (const char *, name)
  m3ApiGetArg (uint32_t, name_len)
  m3ApiGetArgMem (char *, buf)
  m3ApiGetArg (uint32_t, cap)
  char *key, *value;
  int32_t len;
  m3ApiCheckMem (name, name_len);
  wasm_need_make ();
  key = wasm_take (runtime, _mem, name, name_len);
  value = amk_var_get (key);
  len = wasm_give (runtime, _mem, buf, cap, value);
  gmk_free (value);
  free (key);
  m3ApiReturn (len);
}

/* amk.var_set(name, name_len, value, value_len): a simple variable with the literal text. */
m3ApiRawFunction (wasm_amk_var_set)
{
  m3ApiGetArgMem (const char *, name)
  m3ApiGetArg (uint32_t, name_len)
  m3ApiGetArgMem (const char *, value)
  m3ApiGetArg (uint32_t, value_len)
  char *key, *text;
  m3ApiCheckMem (name, name_len);
  m3ApiCheckMem (value, value_len);
  wasm_need_make ();
  key = wasm_take (runtime, _mem, name, name_len);
  text = wasm_take (runtime, _mem, value, value_len);
  amk_var_set (key, text);
  free (text);
  free (key);
  m3ApiSuccess ();
}

/* amk.expand(text, len, buf, cap) -> len: the text expanded by make, into buf. */
m3ApiRawFunction (wasm_amk_expand)
{
  m3ApiReturnType (int32_t)
  m3ApiGetArgMem (const char *, text)
  m3ApiGetArg (uint32_t, text_len)
  m3ApiGetArgMem (char *, buf)
  m3ApiGetArg (uint32_t, cap)
  char *src, *value;
  int32_t len;
  m3ApiCheckMem (text, text_len);
  wasm_need_make ();
  src = wasm_take (runtime, _mem, text, text_len);
  value = gmk_expand (src);
  len = wasm_give (runtime, _mem, buf, cap, value != NULL ? value : "");
  gmk_free (value);
  free (src);
  m3ApiReturn (len);
}

/* amk.eval(text, len): the text read by make as makefile syntax. */
m3ApiRawFunction (wasm_amk_eval)
{
  m3ApiGetArgMem (const char *, text)
  m3ApiGetArg (uint32_t, text_len)
  char *src;
  m3ApiCheckMem (text, text_len);
  wasm_need_make ();
  src = wasm_take (runtime, _mem, text, text_len);
  amk_eval (src);
  free (src);
  m3ApiSuccess ();
}

/* The handle, under the import module "amk", on whatever the module asks for; libc and wasi beside it. */
static M3Result
wasm_link (IM3Module module)
{
  static const struct { const char *name, *sig; M3RawCall fn; } handle[] = {
    { "print", "v(ii)", wasm_amk_print },
    { "var_get", "i(iiii)", wasm_amk_var_get },
    { "var_set", "v(iiii)", wasm_amk_var_set },
    { "expand", "i(iiii)", wasm_amk_expand },
    { "eval", "v(ii)", wasm_amk_eval },
  };
  M3Result res;
  size_t i;
  for (i = 0; i < sizeof handle / sizeof *handle; i++)
    {
      res = m3_LinkRawFunction (module, "amk", handle[i].name, handle[i].sig, handle[i].fn);
      if (res != m3Err_none && res != m3Err_functionLookupFailed)
        return res;
    }
  res = m3_LinkLibC (module);
  if (res != m3Err_none && res != m3Err_functionLookupFailed)
    return res;
  res = m3_LinkWASI (module);
  return res == m3Err_functionLookupFailed ? m3Err_none : res;
}

/* The create member: an environment and a runtime that make holds for the life of the process. */
__attribute__ ((visibility ("default"))) void *
wasm_create (void)
{
  struct wasm_state *w = calloc (1, sizeof *w);
  w->env = m3_NewEnvironment ();
  w->runtime = w->env != NULL ? m3_NewRuntime (w->env, WASM_STACK, w) : NULL;
  if (w->runtime == NULL)
    {
      fprintf (stderr, "wasm: cannot create a runtime\n");
      free (w);
      return NULL;
    }
  return w;
}

/* One result of a finished call as text. */
static void
wasm_emit_result (IM3Function f, unsigned i, const void *p)
{
  char buf[64];
  int n;
  switch (m3_GetRetType (f, i))
    {
    case c_m3Type_i32: n = snprintf (buf, sizeof buf, "%" PRIi32, *(const int32_t *) p); break;
    case c_m3Type_i64: n = snprintf (buf, sizeof buf, "%" PRIi64, *(const int64_t *) p); break;
    case c_m3Type_f32: n = snprintf (buf, sizeof buf, "%g", (double) *(const float *) p); break;
    case c_m3Type_f64: n = snprintf (buf, sizeof buf, "%g", *(const double *) p); break;
    default: n = snprintf (buf, sizeof buf, "?"); break;
    }
  wasm_emit (buf, (size_t) n);
}

/* An export called with string arguments, the results to the sink separated by spaces; a trap or a mismatch reports on stderr unless the deadline ended it, and answers 1. */
static int
wasm_call (struct wasm_state *w, const char *name, unsigned argc, const char **argv)
{
  IM3Function f;
  M3Result res = m3_FindFunction (&f, w->runtime, name);
  uint64_t slots[16];
  const void *ptrs[16];
  unsigned i, nret;

  if (res != m3Err_none)
    {
      fprintf (stderr, "wasm: %s: %s\n", name, res);
      return 1;
    }
  m3_wasi_context_t *ctx = m3_GetWasiContext ();
  if (ctx != NULL)
    ctx->exit_code = 0;
  if (strcmp (name, "_start") == 0)
    {
      if (ctx != NULL)
        {
          ctx->argc = argc;
          ctx->argv = argv;
        }
      argc = 0;
    }
  res = m3_CallArgv (f, argc, argv);
  /* A wasi exit is the program's answer: zero succeeds with what it printed, anything else reports the code. */
  if (res == m3Err_trapExit && ctx != NULL)
    {
      if (ctx->exit_code == 0)
        return 0;
      fprintf (stderr, "wasm: %s: exit %u\n", name, ctx->exit_code);
      return 1;
    }
  if (res != m3Err_none)
    {
      if (res != wasm_deadline_trap && !amk_deadline_expired ())
        fprintf (stderr, "wasm: %s: %s\n", name, res);
      return 1;
    }
  nret = m3_GetRetCount (f);
  if (nret > 16)
    nret = 16;
  for (i = 0; i < nret; i++)
    ptrs[i] = &slots[i];
  res = m3_GetResults (f, nret, ptrs);
  if (res != m3Err_none)
    {
      fprintf (stderr, "wasm: %s: %s\n", name, res);
      return 1;
    }
  for (i = 0; i < nret; i++)
    {
      if (i > 0)
        wasm_emit (" ", 1);
      wasm_emit_result (f, i, ptrs[i]);
    }
  return 0;
}

/* A sink that keeps what it is given, for a call whose results come back as make's value. */
struct wasm_text_sink
{
  struct amk_sink base;
  char *s;
  size_t n;
};

static void
wasm_text_write (struct amk_sink *s, const char *p, size_t n)
{
  struct wasm_text_sink *t = (struct wasm_text_sink *) s;
  t->s = realloc (t->s, t->n + n + 1);
  memcpy (t->s + t->n, p, n);
  t->n += n;
}

/* A sink that passes what it is given along and remembers the last byte, so a line end is added only where one is missing. */
struct wasm_line_sink
{
  struct amk_sink base;
  struct amk_sink *to;
  char last;
};

static void
wasm_line_write (struct amk_sink *s, const char *p, size_t n)
{
  struct wasm_line_sink *l = (struct wasm_line_sink *) s;
  if (n > 0)
    l->last = p[n - 1];
  l->to->write (l->to, p, n);
}

static unsigned wasm_words (char *text, const char **words, unsigned max);

/* make's call into a lifted export, in the runtime that holds it: the arguments, split on commas or on spaces alike since every one is a number, and the results as text. */
static char *
wasm_func_call (void *state, const char *name, unsigned argc, char **argv)
{
  struct wasm_state *w = state;
  struct amk_sink *saved = wasm_sink;
  struct wasm_text_sink out = { { wasm_text_write }, NULL, 0 };
  const char *words[64];
  char *text = NULL;
  size_t n = 0;
  unsigned i, count;
  char *result;

  for (i = 0; i < argc; i++)
    {
      text = realloc (text, n + strlen (argv[i]) + 2);
      sprintf (text + n, "%s ", argv[i]);
      n += strlen (argv[i]) + 1;
    }
  count = text != NULL ? wasm_words (text, words, 64) : 0;
  wasm_sink = &out.base;
  if (wasm_call (w, name, count, words) != 0)
    {
      wasm_sink = saved;
      free (out.s);
      free (text);
      return NULL;
    }
  wasm_sink = saved;
  free (text);
  result = gmk_alloc ((unsigned) out.n + 1);
  memcpy (result, out.s != NULL ? out.s : "", out.n);
  result[out.n] = '\0';
  free (out.s);
  return result;
}

/* The program split into words on whitespace, in place; the count comes back and the words point into the copy. */
static unsigned
wasm_words (char *text, const char **words, unsigned max)
{
  unsigned n = 0;
  char *p = text;
  while (n < max)
    {
      while (*p == ' ' || *p == '\t' || *p == '\n' || *p == '\r')
        ++p;
      if (*p == '\0')
        break;
      words[n++] = p;
      while (*p != '\0' && *p != ' ' && *p != '\t' && *p != '\n' && *p != '\r')
        ++p;
      if (*p != '\0')
        *p++ = '\0';
    }
  return n;
}

static int wasm_is_hex (const char *text);
__attribute__ ((visibility ("default"))) int wasm_import (void *state, struct amk_sink *out, const char *prog);

/* Whether a program is a module rather than a call: hex bytes, or one word ending in .wasm. */
static int
wasm_is_module (const char *prog)
{
  const char *words[2];
  char *text = strdup (prog);
  int one = wasm_words (text, words, 2) == 1;
  size_t n = one ? strlen (words[0]) : 0;
  int module = one && n > 5 && strcmp (words[0] + n - 5, ".wasm") == 0;
  free (text);
  return module || wasm_is_hex (prog);
}

/* The exec member: [deadline ms] name [args...], the export called in the state with the results on one line; a wasi module's _start takes the args as its argv and its stdout lands in the sink too. A module in place of a call is imported, so an init chunk can name one. */
__attribute__ ((visibility ("default"))) int
wasm_exec (void *state, struct amk_sink *out, const char *prog)
{
  struct wasm_state *w = state;
  const char *words[64];
  char *text;
  unsigned n, first = 0;
  long ms = -1;
  struct amk_deadline saved;
  struct amk_capture capture;
  struct wasm_line_sink line = { { wasm_line_write }, out, 0 };
  int rc;

  if (prog == NULL)
    {
      fprintf (stderr, "wasm.exec: no call\n");
      return 2;
    }
  if (wasm_is_module (prog))
    return wasm_import (state, out, prog);
  text = strdup (prog);
  n = wasm_words (text, words, 64);
  if (n >= 2 && strcmp (words[0], "deadline") == 0)
    {
      ms = atol (words[1]);
      first = 2;
    }
  if (n <= first)
    {
      fprintf (stderr, "wasm.exec: no function named\n");
      free (text);
      return 2;
    }
  wasm_sink = &line.base;
  if (ms >= 0)
    amk_deadline_push (ms, &saved);
  amk_capture_begin (&capture);
  rc = wasm_call (w, words[first], n - first - 1, words + first + 1);
  amk_capture_end (&capture, &line.base);
  if (ms >= 0 && amk_deadline_pop (&saved) >= 0)
    {
      fprintf (stderr, "wasm: deadline: %ld ms\n", ms);
      rc = 1;
      amk_ns_answered ();
    }
  else if (rc == 0 && line.last != '\n')
    wasm_emit ("\n", 1);
  wasm_sink = &amk_sink_stderr;
  free (text);
  return rc;
}

/* Whether the text is hex bytes rather than a path: more than one word, every one two hex digits. */
static int
wasm_is_hex (const char *text)
{
  int words = 0, digits = 0;
  for (; *text; ++text)
    {
      if (*text == ' ' || *text == '\t' || *text == '\n' || *text == '\r')
        {
          if (digits != 0 && digits != 2)
            return 0;
          words += digits == 2;
          digits = 0;
        }
      else if ((*text >= '0' && *text <= '9') || (*text >= 'a' && *text <= 'f') || (*text >= 'A' && *text <= 'F'))
        ++digits;
      else
        return 0;
    }
  return (digits == 0 || digits == 2) && words + (digits == 2) > 1;
}

/* The module's bytes from a path or from hex, kept on the state; null with the error reported. */
static uint8_t *
wasm_read (struct wasm_state *w, const char *prog, uint32_t *size)
{
  struct wasm_bytes *b;
  uint8_t *data = NULL;
  size_t n = 0, cap = 0;

  if (wasm_is_hex (prog))
    {
      const char *p = prog;
      cap = strlen (prog) / 2 + 1;
      data = malloc (cap);
      while (*p)
        {
          unsigned v;
          while (*p == ' ' || *p == '\t' || *p == '\n' || *p == '\r')
            ++p;
          if (*p == '\0')
            break;
          sscanf (p, "%2x", &v);
          data[n++] = (uint8_t) v;
          p += 2;
        }
    }
  else
    {
      char path[1024];
      const char *words[2];
      char *text = strdup (prog);
      FILE *f;
      if (wasm_words (text, words, 2) != 1)
        {
          fprintf (stderr, "wasm.import: a module is one path, or its bytes in hex\n");
          free (text);
          return NULL;
        }
      snprintf (path, sizeof path, "%s", words[0]);
      free (text);
      f = fopen (path, "rb");
      if (f == NULL)
        {
          fprintf (stderr, "wasm.import: cannot read %s\n", path);
          return NULL;
        }
      while (1)
        {
          if (n == cap)
            data = realloc (data, cap = cap ? cap * 2 : 65536);
          n += fread (data + n, 1, cap - n, f);
          if (n < cap)
            break;
        }
      fclose (f);
    }
  b = malloc (sizeof *b);
  b->data = data;
  b->next = w->bytes;
  w->bytes = b;
  *size = (uint32_t) n;
  return data;
}

/* The import member: the module at a path, or given as hex bytes, loaded into the state with its start run, and every exported function make can spell lifted as a make function; the names go to the sink. */
__attribute__ ((visibility ("default"))) int
wasm_import (void *state, struct amk_sink *out, const char *prog)
{
  struct wasm_state *w = state;
  IM3Module module = NULL;
  M3Result res;
  uint8_t *data;
  uint32_t size;
  unsigned i;
  int first = 1;

  if (prog == NULL)
    {
      fprintf (stderr, "wasm.import: no module\n");
      return 2;
    }
  wasm_need_make ();
  data = wasm_read (w, prog, &size);
  if (data == NULL)
    return 1;
  res = m3_ParseModule (w->env, &module, data, size);
  if (res == m3Err_none)
    res = m3_LoadModule (w->runtime, module);
  if (res != m3Err_none)
    {
      fprintf (stderr, "wasm.import: %s\n", res);
      m3_FreeModule (module);
      return 1;
    }
  wasm_sink = &amk_sink_stderr;
  res = wasm_link (module);
  if (res == m3Err_none)
    res = m3_RunStart (module);
  if (res != m3Err_none)
    {
      fprintf (stderr, "wasm.import: start: %s\n", res);
      return 1;
    }
  for (i = 0; i < module->numFunctions; i++)
    {
      const char *name = module->functions[i].export_name;
      if (name == NULL || !amk_name_ok (name))
        continue;
      if (amk_func_add (name, w, wasm_func_call) < 0)
        {
          fprintf (stderr, "wasm.import: %s is a make function already\n", name);
          return 1;
        }
      if (!first)
        out->write (out, " ", 1);
      out->write (out, name, strlen (name));
      first = 0;
    }
  out->write (out, "\n", 1);
  return 0;
}

/* The tcc guest: C compiled in memory by libtcc and run in make's own process. An import keeps its unit alive and calls every setup function it defines; the unit reaches make and libc only through the symbols added here, declared to it by the prelude. */

#include <signal.h>
#include <sys/ioctl.h>
#include <time.h>
#include "libtcc.h"
#include "amk_guest.h"

typedef void (*tcc_event_fn) (const char *event, const char *target, const char *status, int code, int sig, long pid);
typedef void (*tcc_void_fn) (void);

#define TCC_MAX_CALLBACKS 16

/* A namespace's units, every one still mapped, since a callback may point into any of them. */
struct tcc_state
{
  TCCState **units;
  size_t n;
};

/* The callbacks run only in the process that registered them, so a fork of the image hears nothing, and no event reaches them once the exits have run. */
static pid_t tcc_owner;
static tcc_event_fn tcc_events[TCC_MAX_CALLBACKS];
static tcc_void_fn tcc_exits[TCC_MAX_CALLBACKS];
static tcc_void_fn tcc_winches[TCC_MAX_CALLBACKS];
static int tcc_nevents, tcc_nexits, tcc_nwinches, tcc_exited;

static const char tcc_prelude[] =
  "typedef __SIZE_TYPE__ size_t;\n"
  "typedef long ssize_t;\n"
  "#define NULL ((void *) 0)\n"
  "ssize_t write (int, const void *, size_t);\n"
  "int snprintf (char *, size_t, const char *, ...);\n"
  "int printf (const char *, ...);\n"
  "int puts (const char *);\n"
  "size_t strlen (const char *);\n"
  "int strcmp (const char *, const char *);\n"
  "int strncmp (const char *, const char *, size_t);\n"
  "char *strcpy (char *, const char *);\n"
  "char *strncpy (char *, const char *, size_t);\n"
  "char *strcat (char *, const char *);\n"
  "char *strchr (const char *, int);\n"
  "void *memcpy (void *, const void *, size_t);\n"
  "void *memmove (void *, const void *, size_t);\n"
  "void *memset (void *, int, size_t);\n"
  "void *malloc (size_t);\n"
  "void *calloc (size_t, size_t);\n"
  "void *realloc (void *, size_t);\n"
  "void free (void *);\n"
  "char *getenv (const char *);\n"
  "int setenv (const char *, const char *, int);\n"
  "int isatty (int);\n"
  "int getpid (void);\n"
  "char *amk_var_get (const char *);\n"
  "void amk_var_set (const char *, const char *);\n"
  "char *gmk_expand (const char *);\n"
  "void gmk_free (char *);\n"
  "void amk_eval (const char *);\n"
  "void amk_on_event (void (*) (const char *, const char *, const char *, int, int, long));\n"
  "void amk_on_exit (void (*) (void));\n"
  "void amk_on_winch (void (*) (void));\n"
  "int amk_term_size (int, int *, int *);\n"
  "long amk_now_ms (void);\n"
  "#line 1\n";

static void
tcc_on_error (void *opaque, const char *msg)
{
  fprintf (stderr, "tcc: %s\n", msg);
}

static void
tcc_run_exits (void)
{
  int i;
  if (tcc_exited || getpid () != tcc_owner)
    return;
  tcc_exited = 1;
  for (i = tcc_nexits - 1; i >= 0; --i)
    tcc_exits[i] ();
}

/* The signals that end make: the exits run, then the handler make had takes the signal as before. */
static const int tcc_fatal[] = { SIGINT, SIGTERM, SIGHUP, SIGQUIT };
static struct sigaction tcc_prior[sizeof tcc_fatal / sizeof tcc_fatal[0]];

static void
tcc_on_fatal (int sig)
{
  size_t i;
  tcc_run_exits ();
  for (i = 0; i < sizeof tcc_fatal / sizeof tcc_fatal[0]; ++i)
    if (tcc_fatal[i] == sig)
      {
        sigaction (sig, &tcc_prior[i], NULL);
        raise (sig);
      }
}

static void
tcc_on_winch_signal (int sig)
{
  int i;
  if (getpid () != tcc_owner)
    return;
  for (i = 0; i < tcc_nwinches; ++i)
    tcc_winches[i] ();
}

static void
tcc_claim (void)
{
  tcc_owner = getpid ();
}

static void
amk_on_event (tcc_event_fn fn)
{
  tcc_claim ();
  if (tcc_nevents < TCC_MAX_CALLBACKS)
    tcc_events[tcc_nevents++] = fn;
}

static void
amk_on_exit (tcc_void_fn fn)
{
  size_t i;
  tcc_claim ();
  if (tcc_nexits == 0)
    {
      struct sigaction sa;
      atexit (tcc_run_exits);
      memset (&sa, 0, sizeof sa);
      sa.sa_handler = tcc_on_fatal;
      sigemptyset (&sa.sa_mask);
      for (i = 0; i < sizeof tcc_fatal / sizeof tcc_fatal[0]; ++i)
        sigaction (tcc_fatal[i], &sa, &tcc_prior[i]);
    }
  if (tcc_nexits < TCC_MAX_CALLBACKS)
    tcc_exits[tcc_nexits++] = fn;
}

static void
amk_on_winch (tcc_void_fn fn)
{
  tcc_claim ();
  if (tcc_nwinches == 0)
    {
      struct sigaction sa;
      memset (&sa, 0, sizeof sa);
      sa.sa_handler = tcc_on_winch_signal;
      sa.sa_flags = SA_RESTART;
      sigemptyset (&sa.sa_mask);
      sigaction (SIGWINCH, &sa, NULL);
    }
  if (tcc_nwinches < TCC_MAX_CALLBACKS)
    tcc_winches[tcc_nwinches++] = fn;
}

static int
amk_term_size (int fd, int *rows, int *cols)
{
  struct winsize ws;
  if (ioctl (fd, TIOCGWINSZ, &ws) != 0 || ws.ws_row == 0)
    return -1;
  *rows = ws.ws_row;
  *cols = ws.ws_col;
  return 0;
}

static long
amk_now_ms (void)
{
  struct timespec ts;
  clock_gettime (CLOCK_MONOTONIC, &ts);
  return (long) ts.tv_sec * 1000 + ts.tv_nsec / 1000000;
}

static void
tcc_add_symbols (TCCState *s)
{
  static const struct { const char *name; const void *val; } table[] = {
    { "write", (const void *) write }, { "snprintf", (const void *) snprintf },
    { "printf", (const void *) printf }, { "puts", (const void *) puts },
    { "strlen", (const void *) strlen }, { "strcmp", (const void *) strcmp },
    { "strncmp", (const void *) strncmp }, { "strcpy", (const void *) strcpy },
    { "strncpy", (const void *) strncpy }, { "strcat", (const void *) strcat },
    { "strchr", (const void *) strchr }, { "memcpy", (const void *) memcpy },
    { "memmove", (const void *) memmove }, { "memset", (const void *) memset },
    { "malloc", (const void *) malloc }, { "calloc", (const void *) calloc },
    { "realloc", (const void *) realloc }, { "free", (const void *) free },
    { "getenv", (const void *) getenv }, { "setenv", (const void *) setenv },
    { "isatty", (const void *) isatty }, { "getpid", (const void *) getpid },
    { "amk_var_get", (const void *) amk_var_get }, { "amk_var_set", (const void *) amk_var_set },
    { "gmk_expand", (const void *) gmk_expand }, { "gmk_free", (const void *) gmk_free },
    { "amk_eval", (const void *) amk_eval },
    { "amk_on_event", (const void *) amk_on_event }, { "amk_on_exit", (const void *) amk_on_exit },
    { "amk_on_winch", (const void *) amk_on_winch }, { "amk_term_size", (const void *) amk_term_size },
    { "amk_now_ms", (const void *) amk_now_ms },
  };
  size_t i;
  for (i = 0; i < sizeof table / sizeof table[0]; ++i)
    tcc_add_symbol (s, table[i].name, table[i].val);
}

/* One unit compiled from the text and relocated, or null with the reason already on stderr. */
static TCCState *
tcc_unit (const char *prog)
{
  TCCState *s = tcc_new ();
  size_t n = strlen (tcc_prelude) + strlen (prog) + 1;
  char *text = malloc (n);
  if (s == NULL || text == NULL)
    {
      free (text);
      if (s)
        tcc_delete (s);
      return NULL;
    }
  strcpy (text, tcc_prelude);
  strcat (text, prog);
  tcc_set_error_func (s, NULL, tcc_on_error);
  tcc_set_options (s, "-nostdlib");
  tcc_set_output_type (s, TCC_OUTPUT_MEMORY);
  if (tcc_compile_string (s, text) < 0)
    {
      free (text);
      tcc_delete (s);
      return NULL;
    }
  free (text);
  tcc_add_symbols (s);
  if (tcc_relocate (s) < 0)
    {
      tcc_delete (s);
      return NULL;
    }
  return s;
}

struct tcc_setups
{
  const char *names[TCC_MAX_CALLBACKS];
  const void *vals[TCC_MAX_CALLBACKS];
  int n;
};

static void
tcc_find_setup (void *ctx, const char *name, const void *val)
{
  struct tcc_setups *found = ctx;
  size_t len = strlen (name), tail = sizeof "_gmk_setup" - 1;
  if (len > tail && strcmp (name + len - tail, "_gmk_setup") == 0 && found->n < TCC_MAX_CALLBACKS)
    {
      found->names[found->n] = name;
      found->vals[found->n++] = val;
    }
}

__attribute__ ((visibility ("default"))) void *
tcc_create (void)
{
  return calloc (1, sizeof (struct tcc_state));
}

/* An import: the unit stays mapped in the namespace, and each setup function it defines runs once; a setup that answers zero fails the import, as a failed load does. */
__attribute__ ((visibility ("default"))) int
tcc_import (void *state, struct amk_sink *out, const char *prog)
{
  struct tcc_state *t = state;
  struct tcc_setups found;
  TCCState **grown;
  TCCState *s = tcc_unit (prog);
  int i, status = 0;
  if (s == NULL)
    return 1;
  grown = realloc (t->units, (t->n + 1) * sizeof *grown);
  if (grown == NULL)
    {
      tcc_delete (s);
      return 1;
    }
  t->units = grown;
  t->units[t->n++] = s;
  found.n = 0;
  tcc_list_symbols (s, &found, tcc_find_setup);
  for (i = 0; i < found.n; ++i)
    if (((int (*) (void)) found.vals[i]) () == 0)
      {
        fprintf (stderr, "tcc: %s failed\n", found.names[i]);
        status = 1;
      }
  return status;
}

/* An exec: the unit runs its main once, its stdout to the sink, and is gone after. */
__attribute__ ((visibility ("default"))) int
tcc_exec (void *state, struct amk_sink *out, const char *prog)
{
  struct amk_capture cap;
  TCCState *s = tcc_unit (prog);
  int (*entry) (void);
  int rc;
  if (s == NULL)
    return 1;
  entry = (int (*) (void)) tcc_get_symbol (s, "main");
  if (entry == NULL)
    {
      fprintf (stderr, "tcc: the program defines no main\n");
      tcc_delete (s);
      return 1;
    }
  amk_capture_begin_to (&cap, out);
  rc = entry ();
  amk_capture_end (&cap, out);
  tcc_delete (s);
  return rc;
}

__attribute__ ((visibility ("default"))) void
tcc_hook (void *state, const char *event, const char *target, const char *status, int exit_code, int exit_sig, long pid)
{
  int i;
  if (getpid () != tcc_owner || tcc_exited)
    return;
  for (i = 0; i < tcc_nevents; ++i)
    tcc_events[i] (event, target ? target : "", status ? status : "", exit_code, exit_sig, pid);
}

/* The command line: the first word is a file to read when it names one, else the program itself, as the builtin and a target pass it; the unit is compiled and its main called with the words after. */
__attribute__ ((visibility ("default"))) int
tcc_run_main (int argc, char **argv)
{
  size_t len = 0, cap = 4096, r;
  char *text = NULL;
  FILE *f;
  TCCState *s;
  int (*entry) (int, char **);
  if (argc < 2)
    {
      fprintf (stderr, "usage: tcc file.c|program [args...]\n");
      return 2;
    }
  f = fopen (argv[1], "r");
  if (f != NULL)
    {
      text = malloc (cap);
      while (text != NULL && (r = fread (text + len, 1, cap - len - 1, f)) > 0)
        if ((len += r) + 1 == cap)
          text = realloc (text, cap *= 2);
      fclose (f);
      if (text == NULL)
        {
          fprintf (stderr, "tcc: cannot read %s\n", argv[1]);
          return 2;
        }
      text[len] = '\0';
    }
  s = tcc_unit (text != NULL ? text : argv[1]);
  free (text);
  if (s == NULL)
    return 1;
  entry = (int (*) (int, char **)) tcc_get_symbol (s, "main");
  if (entry == NULL)
    {
      fprintf (stderr, "tcc: the program defines no main\n");
      return 1;
    }
  fflush (stdout);
  r = (size_t) entry (argc - 1, argv + 1);
  fflush (stdout);
  return (int) r;
}

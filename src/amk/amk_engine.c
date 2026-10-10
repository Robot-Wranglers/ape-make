/* The engine table and what runs a guest: the rows, the hooks and init chunks, the one-shot guest in a fork, the engine builtins, the sinks, and the ledger of what each engine gave make.  */

#include "makeint.h"
#include "filedef.h"
#include "variable.h"
#include "dep.h"
#include "job.h"
#include "os.h"
#include "commands.h"
#include "debug.h"
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <sys/wait.h>
#include "amk.h"

/* Each row: the builtin name, the multi-call names, the entry point, and the argv shape.  */
const struct amk_engine amk_engines[] =
  {
#ifdef AMK_ENGINE_GAWK
    { "awk", "awk gawk", gawk_main, 1, 0, 1 },
#endif
#ifdef AMK_ENGINE_JQ
    { "jq", "jq", jq_main, 0, 0, 1, jq_open, jq_run, 0, jq_filter, "get update load", "." },
#endif
#ifdef AMK_ENGINE_LUA
    { "lua", 0, lua_run_main, 0, 0, 0, lua_open, lua_run, lua_hook, 0, "exec import" },
#endif
#ifdef AMK_ENGINE_S7
    { "s7", 0, s7_run_main, 0, 0, 0, s7_open, s7_run, s7_hook, 0, "exec import" },
#endif
#ifdef AMK_ENGINE_MICROPY
    { "micropy", 0, micropy_run_main, 0, 0, 0, micropy_open, micropy_run, micropy_hook, 0, "exec import" },
#endif
#ifdef AMK_ENGINE_WASM3
    { "wasm", "wasm3", wasm3_main, 0, 1, 1 },
#endif
#ifdef AMK_ENGINE_QUICKJS
    { "js", 0, js_run_main, 0, 0, 0, js_open, js_run, js_hook, 0, "exec import" },
#endif
#ifdef AMK_ENGINE_SQLITE
    { "sqlite", "sqlite3", sqlite_main, 1, 0, 1, sqlite_open, sqlite_run, 0, 0, "get update load", ".dump" },
#endif
    { 0, 0, 0, 0, 0, 0 }
  };

/* The row for a builtin name, with or without its .argv suffix.  */
const struct amk_engine *
amk_engine_by_name (const char *name)
{
  const struct amk_engine *e;
  size_t n = strcspn (name, ".");
  for (e = amk_engines; e->name; ++e)
    if (strlen (e->name) == n && memcmp (e->name, name, n) == 0)
      return e;
  return NULL;
}

/* One name per event, in enum order, so a guest can key its subscribers by it.  */
const char *const amk_event_names[] = { "goals", "recipe_start", "recipe_end" };

/* Every row with a hook entry hears the event in its main state, in table order; an engine whose main never opened hears nothing.  */
void
amk_hook_fire (enum amk_event event, const struct amk_event_info *info)
{
  const struct amk_engine *e;
  for (e = amk_engines; e->name; ++e)
    if (e->hook)
      {
        void *state = amk_ns_state (e, "main", 0);
        if (state != NULL)
          e->hook (state, amk_event_names[event], info->target, info->status, info->exit_code, info->exit_sig, (long) info->pid);
      }
}

/* The init chunk for a row: the environment's, as text or as the file an @ names, else the payload's; null when there is none.  */
static char *
amk_init_chunk (const struct amk_engine *e)
{
  char var[64], path[64];
  const char *env, *file = NULL;
  char *chunk = NULL, *p;
  FILE *f;
  size_t len = 0, cap = 4096;

  sprintf (var, "AMK_%s_INIT", e->name);
  for (p = var + 4; *p != '_'; ++p)
    if (*p >= 'a' && *p <= 'z')
      *p -= 'a' - 'A';
  env = getenv (var);
  if (env != NULL && *env == '@')
    file = env + 1;
  else if (env != NULL && *env != '\0')
    return xstrdup (env);
  else
    {
      sprintf (path, "/zip/__init__.%s", e->name);
      file = path;
    }
  f = fopen (file, "r");
  if (f == NULL)
    {
      if (file != path)
        OSS (error, NILF, _("%s: cannot read %s"), var, file);
      return NULL;
    }
  chunk = xmalloc (cap + 1);
  while (1)
    {
      len += fread (chunk + len, 1, cap - len, f);
      if (len < cap)
        break;
      cap *= 2;
      chunk = xrealloc (chunk, cap + 1);
    }
  chunk[len] = '\0';
  fclose (f);
  return chunk;
}

/* Every row with a run entry runs its init chunk, once, in main, with print on stderr.  */
void
amk_engine_init (void)
{
  const struct amk_engine *e;
  for (e = amk_engines; e->name; ++e)
    if (e->run)
      {
        char *chunk = amk_init_chunk (e);
        void *state;
        if (chunk == NULL)
          continue;
        state = amk_ns_state (e, "main", 1);
        if (state != NULL)
          e->run (state, &amk_sink_stderr, "exec", chunk);
        free (chunk);
      }
}

/* The goal make chose for itself from the first rule, so a later value can be told from a makefile's own.  */
char *amk_goal_autofill = NULL;

/* A target named __main__ becomes the default goal when a makefile named none itself, ahead of make's own first-rule pick.  */
void
amk_default_goal_settle (void)
{
  struct file *f = lookup_file ("__main__");
  const char *v = default_goal_var->value;

  if (f == NULL || !f->is_target)
    return;
  if (v[0] == '\0' || (amk_goal_autofill != NULL && streq (v, amk_goal_autofill)))
    define_variable_global (".DEFAULT_GOAL", 13, "__main__", o_file, 0, NILF);
}

/* Whether word is one of the row's multi-call names.  */
int
amk_engine_called (const struct amk_engine *e, const char *word)
{
  const char *p = e->aliases;
  size_t n = strlen (word);
  while (p && *p)
    {
      size_t len = strcspn (p, " ");
      if (len == n && memcmp (p, word, n) == 0)
        return 1;
      p += len;
      while (*p == ' ')
        ++p;
    }
  return 0;
}

/* A guest's exit inside the forked child: flush its own output and leave without libc's stream cleanup, which would seek the parent's open makefile. */
void
amk_exit (int status)
{
  fflush (stdout);
  fflush (stderr);
  _exit (status);
}

/* Run a linked-in guest's main over the argv in a forked child, no exec: input, if any, becomes its stdin through a pipe the parent feeds between reads of the child's stdout, which is appended to o with its lines intact, less one trailing newline. */
static char *
func_guest (char *o, const char *funcname, int (*guest_main) (int, char **),
            int ac, char **av, const char *input)
{
  int out[2], in[2] = { -1, -1 }, q[2] = { -1, -1 };
  const char *s = input;
  size_t n = input != NULL ? strlen (input) : 0;
  void (*pipe_handler) (int) = SIG_DFL;
  pid_t pid;
  char *buffer;
  size_t i = 0;
  int st = 0;

  if (pipe (out) < 0 || pipe (q) < 0 || (n > 0 && pipe (in) < 0))
    OSS (fatal, NILF, _("$(%s ...): pipe: %s"), funcname, strerror (errno));

  fflush (stdout);
  fflush (stderr);
  pid = fork ();
  if (pid < 0)
    OSS (fatal, NILF, _("$(%s ...): fork: %s"), funcname, strerror (errno));
  if (pid == 0)
    {
      if (in[0] >= 0)
        {
          dup2 (in[0], 0);
          close (in[0]);
          close (in[1]);
        }
      else
        {
          int nul = open ("/dev/null", O_RDONLY);
          if (nul >= 0)
            dup2 (nul, 0);
        }
      dup2 (out[1], 1);
      close (out[0]);
      close (out[1]);
      close (q[0]);
      amk_queue_fd = q[1];
      optind = 0;
      amk_exit (guest_main (ac, av));
    }

  close (out[1]);
  close (q[1]);
  if (in[0] >= 0)
    close (in[0]);
  /* A guest that stops reading early answers the next write with EPIPE, which must not end make; the feed just ends.  */
  if (in[1] >= 0)
    {
      fcntl (in[1], F_SETFL, fcntl (in[1], F_GETFL) | O_NONBLOCK);
      pipe_handler = signal (SIGPIPE, SIG_IGN);
    }

  buffer = amk_collect (&out[0], &i, &q[0], &in[1], s, n);
  if (input != NULL && strlen (input) > 0)
    signal (SIGPIPE, pipe_handler);
  waitpid (pid, &st, 0);
  shell_completed (WIFEXITED (st) ? WEXITSTATUS (st) : 127, WIFSIGNALED (st) ? WTERMSIG (st) : 0);

  /* One trailing newline goes, as $(file <) drops it; any before it stay.  */
  if (i > 0 && buffer[i - 1] == '\n')
    {
      --i;
      if (i > 0 && buffer[i - 1] == '\r')
        --i;
    }
  if (i > 0)
    o = variable_buffer_output (o, buffer, i);
  free (buffer);
  return o;
}

/* Split a list in place into av as a shell would, honoring quotes and backslashes and expanding nothing; returns the count, and the buffer stays the caller's. */
static int
amk_split_argv (char *args, char **av, int max)
{
  int ac = 0;
  char *p = args;
  char *w = args;
  while (ac < max)
    {
      char quote = 0;
      while (*p == ' ' || *p == '\t')
        ++p;
      if (!*p)
        break;
      av[ac++] = w;
      while (*p && (quote || (*p != ' ' && *p != '\t')))
        {
          if (!quote && (*p == '\'' || *p == '"'))
            quote = *p++;
          else if (*p == quote)
            {
              quote = 0;
              ++p;
            }
          else
            {
              if (*p == '\\' && p[1] && (!quote || (quote == '"' && (p[1] == '"' || p[1] == '\\'))))
                ++p;
              *w++ = *p++;
            }
        }
      if (*p)
        ++p;
      *w++ = '\0';
    }
  return ac;
}

static char *amk_filter_expand (char *o, const struct amk_engine *e, const char *prog, const char *input);

/* Every engine builtin: $(name program[,input]) and $(name.argv options,program[,input]), the argv built the way the row says; a row with a filter runs the plain form in this process. */
char *
func_engine (char *o, char **argv, const char *funcname)
{
  const struct amk_engine *e = amk_engine_by_name (funcname);
  char *av[64];
  char *opts = NULL;
  char *args = NULL;
  int ac = 1;
  if (e->filter && strchr (funcname, '.') == NULL)
    return amk_filter_expand (o, e, argv[0], argv[1]);
  av[0] = (char *) e->name;
  if (strchr (funcname, '.'))
    {
      opts = xstrdup (*argv++);
      ac += amk_split_argv (opts, av + ac, 30);
    }
  if (e->dashdash)
    av[ac++] = (char *) "--";
  if (e->cmdline)
    {
      args = xstrdup (argv[0]);
      ac += amk_split_argv (args, av + ac, 62 - ac);
    }
  else
    av[ac++] = argv[0];
  av[ac] = NULL;
  o = func_guest (o, funcname, e->main, ac, av, argv[1]);
  free (opts);
  free (args);
  return o;
}

/* An imported target's job, inside its fork: the engine's main over the target's flags and then the program as the builtin would pass it; handle writes have no queue, so they end with the job.  */
void
amk_engine_program (const struct amk_engine *e, const char *flags, const char *program)
{
  char *av[64];
  char *args = NULL;
  int ac = 1;
  av[0] = (char *) e->name;
  if (flags != NULL)
    ac += amk_split_argv (xstrdup (flags), av + ac, 30);
  if (e->dashdash)
    av[ac++] = (char *) "--";
  if (e->cmdline)
    {
      args = xstrdup (program);
      ac += amk_split_argv (args, av + ac, 62 - ac);
    }
  else
    av[ac++] = (char *) program;
  av[ac] = NULL;
  amk_queue_fd = -1;
  optind = 0;
  amk_exit (e->main (ac, av));
}

/* The expansion being built, as a sink: what an engine writes lands in make's own buffer at the call's place, with no copy between.  */
extern char *variable_buffer;

void
amk_expand_write (struct amk_sink *s, const char *p, size_t n)
{
  struct amk_expand_sink *e = (struct amk_expand_sink *) s;
  e->o = variable_buffer_output (e->o, p, n);
}

static void
amk_stderr_write (struct amk_sink *s, const char *p, size_t n)
{
  (void) s;
  fwrite (p, 1, n, stderr);
}

struct amk_sink amk_sink_stderr = { amk_stderr_write };

/* The stateless filter of a row that has one, run in this process over the input text, its output at the call's place less one trailing newline.  */
static char *
amk_filter_expand (char *o, const struct amk_engine *e, const char *prog, const char *input)
{
  struct amk_expand_sink sink;
  size_t start = o - variable_buffer;
  int rc;

  sink.base.write = amk_expand_write;
  sink.o = o;
  rc = e->filter (&sink.base, prog, input != NULL ? input : "");
  shell_completed (rc, 0);
  o = sink.o;
  if ((size_t) (o - variable_buffer) > start && o[-1] == '\n')
    {
      --o;
      if ((size_t) (o - variable_buffer) > start && o[-1] == '\r')
        --o;
    }
  return o;
}

/* The engine whose kept-state call is running, so a function registered during it is credited to that engine.  */
const char *amk_binding_engine;

/* A name appended once to an engine's ledger of what it gave make, its fxns or its vars.  */
void
amk_binding_add (const char *engine, const char *kind, const char *name, size_t len)
{
  char var[96];
  struct variable *v;
  const char *old, *p, *w;
  size_t wlen;
  char *val;

  snprintf (var, sizeof var, "%s.__%s__", engine, kind);
  v = lookup_variable (var, strlen (var));
  old = v != NULL ? v->value : "";
  p = old;
  while ((w = find_next_token (&p, &wlen)) != NULL)
    if (wlen == len && memcmp (w, name, len) == 0)
      return;
  val = xmalloc (strlen (old) + len + 2);
  sprintf (val, "%s%s%.*s", old, *old ? " " : "", (int) len, name);
  define_variable_global (var, strlen (var), val, o_file, 0, NILF);
  free (val);
}

/* $(amk.fxns? engines...) and $(amk.vars? engines...): what each named engine gave make, its functions or its variables, in order; commas and spaces both separate names.  */
char *
func_bindings (char *o, char **argv, const char *funcname)
{
  const char *kind = strstr (funcname, "fxns") != NULL ? "fxns" : "vars";
  const char *p, *w;
  size_t wlen;
  int first = 1;

  for (; *argv != NULL; ++argv)
    for (p = *argv; (w = find_next_token (&p, &wlen)) != NULL;)
      {
        char var[96];
        struct variable *v;

        snprintf (var, sizeof var, "%.*s.__%s__", (int) wlen, w, kind);
        v = lookup_variable (var, strlen (var));
        if (v != NULL && *v->value != '\0')
          {
            if (!first)
              o = variable_buffer_output (o, " ", 1);
            o = variable_buffer_output (o, v->value, strlen (v->value));
            first = 0;
          }
      }
  return o;
}

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

/* Each engine's interfaces, then its row: the builtin name, the multi-call names, and the interfaces it has.  */
#ifdef AMK_ENGINE_GAWK
static const struct amk_cli_ops awk_cli = { .main = gawk_main, .dashdash = 1, .argv = 1 };
#endif
#ifdef AMK_ENGINE_JQ
static const struct amk_cli_ops jq_cli = { .main = jq_main, .argv = 1 };
static const struct amk_workspace_ops jq_workspace = {
  .kept = { .create = jq_create },
  .get = jq_get, .update = jq_update, .load = jq_load, .dump = jq_dump, .filter = jq_filter,
};
#endif
#ifdef AMK_ENGINE_LUA
static const struct amk_cli_ops lua_cli = { .main = lua_run_main };
static const struct amk_state_ops lua_state = {
  .kept = { .create = lua_create }, .exec = lua_exec, .import = lua_import, .hook = lua_hook,
};
#endif
#ifdef AMK_ENGINE_S7
static const struct amk_cli_ops s7_cli = { .main = s7_run_main };
static const struct amk_state_ops s7_state = {
  .kept = { .create = s7_create }, .exec = s7_exec, .import = s7_import, .hook = s7_hook,
};
#endif
#ifdef AMK_ENGINE_MICROPY
static const struct amk_cli_ops micropy_cli = { .main = micropy_run_main };
static const struct amk_state_ops micropy_state = {
  .kept = { .create = micropy_create }, .exec = micropy_exec, .import = micropy_import, .hook = micropy_hook,
};
#endif
#ifdef AMK_ENGINE_WASM3
static const struct amk_cli_ops wasm_cli = { .main = wasm3_main, .cmdline = 1, .argv = 1 };
#endif
#ifdef AMK_ENGINE_QUICKJS
static const struct amk_cli_ops js_cli = { .main = js_run_main };
static const struct amk_state_ops js_state = {
  .kept = { .create = js_create }, .exec = js_exec, .import = js_import, .hook = js_hook,
};
#endif
#ifdef AMK_ENGINE_SQLITE
static const struct amk_cli_ops sqlite_cli = { .main = sqlite_main, .dashdash = 1, .argv = 1 };
static const struct amk_workspace_ops sqlite_workspace = {
  .kept = { .create = sqlite_create },
  .get = sqlite_get, .update = sqlite_update, .load = sqlite_load, .dump = sqlite_dump,
};
#endif

const struct amk_engine amk_engines[] =
  {
#ifdef AMK_ENGINE_GAWK
    { .name = "awk", .aliases = "awk gawk", .cli = &awk_cli },
#endif
#ifdef AMK_ENGINE_JQ
    { .name = "jq", .aliases = "jq", .cli = &jq_cli, .workspace = &jq_workspace },
#endif
#ifdef AMK_ENGINE_LUA
    { .name = "lua", .cli = &lua_cli, .state = &lua_state },
#endif
#ifdef AMK_ENGINE_S7
    { .name = "s7", .cli = &s7_cli, .state = &s7_state },
#endif
#ifdef AMK_ENGINE_MICROPY
    { .name = "micropy", .cli = &micropy_cli, .state = &micropy_state },
#endif
#ifdef AMK_ENGINE_WASM3
    { .name = "wasm", .aliases = "wasm3", .cli = &wasm_cli },
#endif
#ifdef AMK_ENGINE_QUICKJS
    { .name = "js", .cli = &js_cli, .state = &js_state },
#endif
#ifdef AMK_ENGINE_SQLITE
    { .name = "sqlite", .aliases = "sqlite3", .cli = &sqlite_cli, .workspace = &sqlite_workspace },
#endif
    { .name = NULL }
  };

/* A row is refused unless it has a command line, at most one kept-state interface, and every member of that interface but the optional hook and filter.  */
void
amk_engines_check (void)
{
  const struct amk_engine *e;
  for (e = amk_engines; e->name; ++e)
    {
      const char *missing = NULL;
      if (e->cli == NULL || e->cli->main == NULL)
        missing = "a command line";
      else if (e->state != NULL && e->workspace != NULL)
        missing = "only one of the state and workspace interfaces";
      else if (e->state != NULL && (e->state->kept.create == NULL || e->state->exec == NULL || e->state->import == NULL))
        missing = "every member of its state interface";
      else if (e->workspace != NULL
               && (e->workspace->kept.create == NULL || e->workspace->get == NULL || e->workspace->update == NULL
                   || e->workspace->load == NULL || e->workspace->dump == NULL))
        missing = "every member of its workspace interface";
      if (missing != NULL)
        OSS (fatal, NILF, _("engine %s: needs %s"), e->name, missing);
    }
}

const struct amk_kept_ops *
amk_engine_kept (const struct amk_engine *e)
{
  if (e == NULL)
    return NULL;
  return e->state != NULL ? &e->state->kept : e->workspace != NULL ? &e->workspace->kept : NULL;
}

const char *
amk_engine_ops (const struct amk_engine *e)
{
  if (e == NULL)
    return NULL;
  return e->state != NULL ? "exec import" : e->workspace != NULL ? "get update load" : NULL;
}

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
    if (e->state != NULL && e->state->hook != NULL)
      {
        void *state = amk_ns_state (e, "main", 0);
        if (state != NULL)
          e->state->hook (state, amk_event_names[event], info->target, info->status, info->exit_code, info->exit_sig, (long) info->pid);
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

/* Every row with a state interface runs its init chunk, once, in main, with print on stderr.  */
void
amk_engine_init (void)
{
  const struct amk_engine *e;
  for (e = amk_engines; e->name; ++e)
    if (e->state != NULL)
      {
        char *chunk = amk_init_chunk (e);
        void *state;
        if (chunk == NULL)
          continue;
        state = amk_ns_state (e, "main", 1);
        if (state != NULL)
          e->state->exec (state, &amk_sink_stderr, chunk);
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
  if (e->workspace != NULL && e->workspace->filter != NULL && strchr (funcname, '.') == NULL)
    return amk_filter_expand (o, e, argv[0], argv[1]);
  av[0] = (char *) e->name;
  if (strchr (funcname, '.'))
    {
      opts = xstrdup (*argv++);
      ac += amk_split_argv (opts, av + ac, 30);
    }
  if (e->cli->dashdash)
    av[ac++] = (char *) "--";
  if (e->cli->cmdline)
    {
      args = xstrdup (argv[0]);
      ac += amk_split_argv (args, av + ac, 62 - ac);
    }
  else
    av[ac++] = argv[0];
  av[ac] = NULL;
  o = func_guest (o, funcname, e->cli->main, ac, av, argv[1]);
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
  if (e->cli->dashdash)
    av[ac++] = (char *) "--";
  if (e->cli->cmdline)
    {
      args = xstrdup (program);
      ac += amk_split_argv (args, av + ac, 62 - ac);
    }
  else
    av[ac++] = (char *) program;
  av[ac] = NULL;
  amk_queue_fd = -1;
  optind = 0;
  amk_exit (e->cli->main (ac, av));
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
  rc = e->workspace->filter (&sink.base, prog, input != NULL ? input : "");
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

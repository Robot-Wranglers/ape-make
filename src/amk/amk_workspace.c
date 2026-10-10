/* Namespaces and workspaces: each engine's kept states by name, their operations, backings, handles, imports, and the functions guests define.  */

#include "makeint.h"
#include "filedef.h"
#include "variable.h"
#include "dep.h"
#include "job.h"
#include "os.h"
#include "commands.h"
#include "debug.h"
#include "amk.h"

extern char *variable_buffer;

/* The namespaces so far, each held by one engine with the state its operations run in: main exists for every engine and joins on first use, every other name is one engine's, and handles says whether create has made its ns.op functions.  */
struct amk_ns
  {
    char *name;
    const struct amk_engine *engine;
    void *state;
    unsigned int handles:1;
    unsigned int mode:2;
    unsigned int loaded:1;
    char *path;
    time_t mtime;
    off_t size;
  };
static struct amk_ns *amk_nss;
static unsigned int amk_nss_len;

/* The row for a name, under one engine or, with none given, any.  */
static struct amk_ns *
amk_ns_find (const struct amk_engine *e, const char *name)
{
  unsigned int i;
  for (i = 0; i < amk_nss_len; ++i)
    if ((e == NULL || amk_nss[i].engine == e) && streq (amk_nss[i].name, name))
      return &amk_nss[i];
  return NULL;
}

/* The engine a name other than main belongs to, or null.  */
static const struct amk_engine *
amk_ns_owner (const char *name)
{
  struct amk_ns *ns = streq (name, "main") ? NULL : amk_ns_find (NULL, name);
  return ns != NULL ? ns->engine : NULL;
}

static struct amk_ns *
amk_ns_add (const struct amk_engine *e, const char *name)
{
  amk_nss = xrealloc (amk_nss, (amk_nss_len + 1) * sizeof *amk_nss);
  amk_nss[amk_nss_len].name = xstrdup (name);
  amk_nss[amk_nss_len].engine = e;
  amk_nss[amk_nss_len].state = NULL;
  amk_nss[amk_nss_len].handles = 0;
  amk_nss[amk_nss_len].mode = 0;
  amk_nss[amk_nss_len].loaded = 0;
  amk_nss[amk_nss_len].path = NULL;
  amk_nss[amk_nss_len].mtime = 0;
  amk_nss[amk_nss_len].size = 0;
  return &amk_nss[amk_nss_len++];
}

/* The state a namespace runs in, opened on first use when open says so; null when it was never opened and open is off, or when the engine cannot open it.  */
void *
amk_ns_state (const struct amk_engine *e, const char *name, int open)
{
  struct amk_ns *ns = amk_ns_find (e, name);
  if (ns == NULL)
    {
      if (!open || !streq (name, "main"))
        return NULL;
      ns = amk_ns_add (e, name);
    }
  if (ns->state == NULL && open && amk_engine_kept (e) != NULL)
    ns->state = amk_engine_kept (e)->create ();
  return ns->state;
}

/* The member an operation names, on the interface the row has.  */
static int
amk_state_member (const struct amk_engine *e, void *state, struct amk_sink *out, const char *op, const char *prog)
{
  const struct amk_state_ops *s = e->state;
  const struct amk_workspace_ops *w = e->workspace;
  if (s != NULL && streq (op, "exec"))
    return s->exec (state, out, prog);
  if (s != NULL && streq (op, "import"))
    return s->import (state, out, prog);
  if (w != NULL && streq (op, "get"))
    return w->get (state, out, prog);
  if (w != NULL && streq (op, "update"))
    return w->update (state, out, prog);
  if (w != NULL && streq (op, "load"))
    return w->load (state, prog);
  if (w != NULL && streq (op, "dump"))
    return w->dump (state, out);
  fprintf (stderr, "amk: %s has no %s; one of %s\n", e->name, op, amk_engine_ops (e) != NULL ? amk_engine_ops (e) : "none");
  return 2;
}

/* One operation in a state, credited to its engine while it runs.  */
static int
amk_state_run (const struct amk_engine *e, void *state, struct amk_sink *out, const char *op, const char *prog)
{
  const char *outer = amk_binding_engine;
  int rc;
  amk_binding_engine = e->name;
  rc = amk_state_member (e, state, out, op, prog);
  amk_binding_engine = outer;
  return rc;
}

/* A namespace is one word that the channel's request line carries unquoted.  */
static int
amk_ns_valid (const char *name)
{
  size_t n = strlen (name);
  return n > 0 && n < 200 && strpbrk (name, " \t\n'\"\\") == NULL;
}

int
amk_engine_has_op (const struct amk_engine *e, const char *word, size_t len)
{
  const char *p = amk_engine_ops (e), *w;
  size_t wlen;
  if (p == NULL)
    return 0;
  while ((w = find_next_token (&p, &wlen)) != NULL)
    if (wlen == len && memcmp (w, word, wlen) == 0)
      return 1;
  return 0;
}

char *
func_refuse (char *o, char **argv, const char *funcname)
{
  const struct amk_engine *e = amk_engine_by_name (funcname);
  (void) argv;
  if (amk_engine_ops (e) == NULL)
    OSS (fatal, reading_file, _("%s: %s has no state or workspace interface"), funcname, e->name);
  OSSS (fatal, reading_file, _("%s: %s has no such operation; one of %s"), funcname, e->name, amk_engine_ops (e));
  return o;
}

int
amk_engine_is_workspace (const struct amk_engine *e)
{
  return e != NULL && e->workspace != NULL;
}

const struct amk_engine *
amk_workspace_engine (const char *ns)
{
  const struct amk_engine *e = ns != NULL ? amk_ns_owner (ns) : NULL;
  if (e != NULL)
    return e;
  for (e = amk_engines; e->name != NULL; ++e)
    if (amk_engine_is_workspace (e))
      return e;
  return NULL;
}

/* An argument with the blanks around it cut off in place.  */
char *
amk_trim (char *s)
{
  char *end;
  while (ISSPACE (*s))
    s++;
  end = s + strlen (s);
  while (end > s && ISSPACE (end[-1]))
    *--end = '\0';
  return s;
}

static int amk_ns_sync_in (const struct amk_engine *e, struct amk_ns *row);
static int amk_ns_sync_out (const struct amk_engine *e, struct amk_ns *row);

/* One operation on a namespace's state, with its backing file read before and, for a write, written after.  */
static int
amk_ns_apply (const struct amk_engine *e, struct amk_ns *row, struct amk_sink *out, const char *op, const char *prog)
{
  int rc = amk_ns_sync_in (e, row);
  if (rc == 0)
    rc = amk_state_run (e, row->state, out, op, prog);
  if (rc == 0 && (streq (op, "update") || streq (op, "load")))
    rc = amk_ns_sync_out (e, row);
  return rc;
}

/* One operation in one namespace, in this process with no fork, so what one call leaves in the namespace the next call finds.  */
static char *
amk_ns_run (char *o, const struct amk_engine *e, const char *ns, const char *op, const char *prog, const char *funcname)
{
  struct amk_expand_sink sink;
  size_t start = o - variable_buffer;
  int rc;

  sink.base.write = amk_expand_write;
  sink.o = o;
  /* A forwarder has no workspace of its own: a workspace row's call goes up the channel as a request line, which a load's text cannot ride.  */
  if (amk_engine_is_workspace (e) && amk_call_forwarding ())
    {
      char *line;
      if (streq (op, "load"))
        OS (error, NILF, _("$(%s ...): a load's text does not travel the call channel"), funcname);
      line = xmalloc (strlen (op) + strlen (ns) + strlen (prog) + 3);
      sprintf (line, "%s %s %s", op, ns, prog);
      rc = amk_call_forward (line, &sink.base);
      free (line);
    }
  else
    {
      void *state = amk_ns_state (e, ns, 1);
      struct amk_ns *row = amk_ns_find (e, ns);
      if (state == NULL)
        OSS (fatal, reading_file, _("%s: cannot open a %s state"), funcname, e->name);
      rc = amk_ns_apply (e, row, &sink.base, op, prog);
    }
  shell_completed (rc, 0);
  o = sink.o;

  /* One trailing newline goes, as for every builtin; the buffer may have moved, so the start is an offset.  */
  if ((size_t) (o - variable_buffer) > start && o[-1] == '\n')
    {
      --o;
      if ((size_t) (o - variable_buffer) > start && o[-1] == '\r')
        --o;
    }

  /* An import's names that are not functions are the variables it gave make.  */
  if (streq (op, "import"))
    {
      char *names = xstrndup (variable_buffer + start, o - variable_buffer - start);
      const char *p = names, *w;
      size_t wlen;

      while ((w = find_next_token (&p, &wlen)) != NULL)
        {
          char *name = xstrndup (w, wlen);
          if (!amk_function_exists (name))
            amk_binding_add (e->name, "vars", w, wlen);
          free (name);
        }
      free (names);
    }
  return o;
}

/* $(eng.op program): the operation in main.  */
char *
func_op (char *o, char **argv, const char *funcname)
{
  const struct amk_engine *e = amk_engine_by_name (funcname);
  return amk_ns_run (o, e, "main", strchr (funcname, '.') + 1, argv[0], funcname);
}

/* A handle, ns.op: the operation in the namespace it was made for.  */
char *
func_handle (char *o, char **argv, const char *funcname)
{
  const char *dot = strrchr (funcname, '.');
  char *ns = xstrndup (funcname, dot - funcname);
  const struct amk_engine *e = amk_ns_owner (ns);
  if (!amk_engine_has_op (e, dot + 1, strlen (dot + 1)))
    OSSS (fatal, reading_file, _("%s: %s has no such operation; one of %s"), funcname, e->name, amk_engine_ops (e));
  o = amk_ns_run (o, e, ns, dot + 1, argv[0], funcname);
  free (ns);
  return o;
}

/* A backing is a mode and, past run, a path: run keeps the value in the workspace alone, owned loads the file once at first use and writes every update through, shared also reloads when the file changed since the last load.  */
#define AMK_BACK_NONE 0
#define AMK_BACK_RUN 1
#define AMK_BACK_OWNED 2
#define AMK_BACK_SHARED 3
static const char *const amk_back_names[] = { "none", "run", "owned", "shared" };

#include <sys/stat.h>

struct amk_text_sink { struct amk_sink base; char *buf; size_t len; };

static void
amk_text_write (struct amk_sink *s, const char *p, size_t n)
{
  struct amk_text_sink *t = (struct amk_text_sink *) s;
  t->buf = xrealloc (t->buf, t->len + n + 1);
  memcpy (t->buf + t->len, p, n);
  t->len += n;
  t->buf[t->len] = '\0';
}

/* The whole of a backing file as text, or null when it cannot be read.  */
static char *
amk_ns_slurp (const char *path)
{
  FILE *f = fopen (path, "r");
  char *text;
  size_t len = 0, cap = 4096;
  if (f == NULL)
    return NULL;
  text = xmalloc (cap + 1);
  for (;;)
    {
      len += fread (text + len, 1, cap - len, f);
      if (len < cap)
        break;
      cap *= 2;
      text = xrealloc (text, cap + 1);
    }
  text[len] = '\0';
  fclose (f);
  return text;
}

/* The file into the state when the mode says so: owned at first use, shared whenever the file's time or size moved since the last load; a missing or empty file loads nothing.  */
static int
amk_ns_sync_in (const struct amk_engine *e, struct amk_ns *row)
{
  struct amk_text_sink sink = { { amk_text_write }, NULL, 0 };
  struct stat st;
  char *text;
  int rc, moved;

  if (row->mode < AMK_BACK_OWNED)
    return 0;
  if (stat (row->path, &st) < 0 || st.st_size == 0)
    {
      row->loaded = 1;
      return 0;
    }
  moved = st.st_mtime != row->mtime || st.st_size != row->size;
  if (row->loaded && (row->mode == AMK_BACK_OWNED || !moved))
    return 0;
  text = amk_ns_slurp (row->path);
  if (text == NULL)
    {
      fprintf (stderr, "amk: workspace: %s: cannot read %s\n", row->name, row->path);
      return 2;
    }
  if (getenv ("AMK_DEBUG") != 0)
    fprintf (stderr, "amk: workspace: %s loaded from %s\n", row->name, row->path);
  rc = amk_state_run (e, row->state, &sink.base, "load", text);
  free (text);
  free (sink.buf);
  if (rc != 0)
    return 2;
  row->loaded = 1;
  row->mtime = st.st_mtime;
  row->size = st.st_size;
  return 0;
}

/* The state into the file after a write, through a temp file beside it and a rename, with the file's new time and size kept so the next call does not read its own write back.  */
static int
amk_ns_sync_out (const struct amk_engine *e, struct amk_ns *row)
{
  struct amk_text_sink sink = { { amk_text_write }, NULL, 0 };
  struct stat st;
  char *tmp;
  FILE *f;
  int rc;

  if (row->mode < AMK_BACK_OWNED)
    return 0;
  rc = amk_state_run (e, row->state, &sink.base, "dump", "");
  if (rc != 0)
    {
      free (sink.buf);
      return 2;
    }
  tmp = xmalloc (strlen (row->path) + 32);
  sprintf (tmp, "%s.tmp.%ld", row->path, (long) getpid ());
  f = fopen (tmp, "w");
  if (f == NULL || (sink.len > 0 && fwrite (sink.buf, 1, sink.len, f) != sink.len) || fclose (f) != 0
      || rename (tmp, row->path) < 0)
    {
      fprintf (stderr, "amk: workspace: %s: cannot write %s\n", row->name, row->path);
      unlink (tmp);
      free (tmp);
      free (sink.buf);
      return 2;
    }
  free (tmp);
  free (sink.buf);
  if (stat (row->path, &st) == 0)
    {
      row->mtime = st.st_mtime;
      row->size = st.st_size;
    }
  row->loaded = 1;
  return 0;
}

/* A workspace's backing declaration, a mode word then a path, on a row made on first use; a second declaration must repeat the first.  */
int
amk_workspace_backing (const char *ns, const char *spec)
{
  const struct amk_engine *e = amk_workspace_engine (ns);
  const struct amk_engine *owner;
  struct amk_ns *row;
  char *copy, *word, *path;
  int mode;

  if (!amk_engine_is_workspace (e))
    {
      fprintf (stderr, "amk: workspace: this build has no workspaces\n");
      return 2;
    }
  if (!amk_ns_valid (ns))
    {
      fprintf (stderr, "amk: workspace: namespace \"%s\" is not a name\n", ns);
      return 2;
    }
  owner = amk_ns_owner (ns);
  if (owner != NULL && owner != e)
    {
      fprintf (stderr, "amk: workspace: namespace %s belongs to %s\n", ns, owner->name);
      return 2;
    }
  copy = xstrdup (spec);
  word = strtok (copy, " \t");
  path = word != NULL ? strtok (NULL, " \t") : NULL;
  for (mode = AMK_BACK_RUN; mode <= AMK_BACK_SHARED; ++mode)
    if (word != NULL && streq (word, amk_back_names[mode]))
      break;
  if (word == NULL || mode > AMK_BACK_SHARED || (mode >= AMK_BACK_OWNED && path == NULL)
      || (path != NULL && strtok (NULL, " \t") != NULL))
    {
      fprintf (stderr, "amk: workspace: %s: expected a backing, one of run, owned PATH, shared PATH; got: %s\n", ns, spec);
      free (copy);
      return 2;
    }
  row = amk_ns_find (e, ns);
  if (row == NULL)
    row = amk_ns_add (e, ns);
  if (row->mode != AMK_BACK_NONE)
    {
      int same = row->mode == mode && ((row->path == NULL && path == NULL)
                                       || (row->path != NULL && path != NULL && streq (row->path, path)));
      free (copy);
      if (same)
        return 0;
      fprintf (stderr, "amk: workspace: %s is backed as %s%s%s already\n", ns, amk_back_names[row->mode],
               row->path != NULL ? " " : "", row->path != NULL ? row->path : "");
      return 2;
    }
  row->mode = mode;
  row->path = path != NULL ? xstrdup (path) : NULL;
  free (copy);
  return 0;
}

/* create: the namespace held by the engine with a state of its own, and a handle with its star twin for each of the engine's operations; a second create by the same engine changes nothing. Main opens first, so an engine with one state keeps it there and refuses the second.  */
static void
amk_ns_create (const struct amk_engine *e, const char *ns, const char *funcname)
{
  const struct amk_engine *owner = amk_ns_owner (ns);
  struct amk_ns *row = owner == e ? amk_ns_find (e, ns) : NULL;
  const char *p, *w;
  size_t wlen;

  if (streq (ns, "main") || (row != NULL && row->handles))
    return;
  if (owner != NULL && owner != e)
    OSSS (fatal, reading_file, _("%s: namespace %s belongs to %s"), funcname, ns, owner->name);
  if (row == NULL)
    {
      if (amk_ns_state (e, "main", 1) == NULL)
        OSS (fatal, reading_file, _("%s: cannot open a %s state"), funcname, e->name);
      row = amk_ns_add (e, ns);
      row->state = amk_engine_kept (e)->create ();
      if (row->state == NULL)
        OSS (fatal, reading_file, _("%s: create is not supported for %s"), funcname, e->name);
    }
  for (p = AMK_OPS_ALL; (w = find_next_token (&p, &wlen)) != NULL;)
    {
      char *name = xmalloc (strlen (ns) + wlen + 3);
      sprintf (name, "%s.%.*s", ns, (int) wlen, w);
      if (amk_function_exists (name))
        OSS (fatal, reading_file, _("%s: %s is a make function already"), funcname, name);
      strcat (name, "*");
      if (amk_function_exists (name))
        OSS (fatal, reading_file, _("%s: %s is a make function already"), funcname, name);
      free (name);
    }
  row->handles = 1;
  for (p = AMK_OPS_ALL; (w = find_next_token (&p, &wlen)) != NULL;)
    {
      amk_handle_add (ns, w, wlen, 0);
      amk_handle_add (ns, w, wlen, 1);
    }
}

/* The call channel's operation on a workspace namespace, made with a state on first use and no handles; a name another engine holds, or an operation the row lacks, answers the usage status.  */
int
amk_workspace_call (struct amk_sink *out, const char *op, const char *ns, const char *prog)
{
  const struct amk_engine *e = amk_workspace_engine (ns);
  const struct amk_engine *owner;
  struct amk_ns *row;
  int rc;

  if (!amk_engine_is_workspace (e))
    {
      fprintf (stderr, "amk: call: this build has no workspaces\n");
      return 2;
    }
  if (!amk_engine_has_op (e, op, strlen (op)) && !streq (op, "dump"))
    {
      fprintf (stderr, "amk: call: unknown operation %s; one of %s, dump, filter, create\n", op, amk_engine_ops (e));
      return 2;
    }
  if (!amk_ns_valid (ns))
    {
      fprintf (stderr, "amk: call: %s: namespace \"%s\" is not a name\n", op, ns);
      return 2;
    }
  owner = amk_ns_owner (ns);
  if (owner != NULL && owner != e)
    {
      fprintf (stderr, "amk: call: namespace %s belongs to %s\n", ns, owner->name);
      return 2;
    }
  row = amk_ns_find (e, ns);
  if (row == NULL)
    row = amk_ns_add (e, ns);
  if (row->state == NULL)
    row->state = e->workspace->kept.create ();
  if (row->state == NULL)
    {
      fprintf (stderr, "amk: call: cannot open a %s state\n", e->name);
      return 2;
    }
  return amk_ns_apply (e, row, out, op, prog);
}

/* The call channel's filter: the named engine's stateless run over the input text; an engine without one is refused by name.  */
int
amk_workspace_filter (struct amk_sink *out, const char *engine, const char *prog, const char *input)
{
  const struct amk_engine *e = amk_engine_by_name (engine);
  if (e == NULL)
    {
      fprintf (stderr, "amk: call: filter: no engine named %s\n", engine);
      return 2;
    }
  if (e->workspace == NULL || e->workspace->filter == NULL)
    {
      fprintf (stderr, "amk: call: filter: %s has no filter\n", e->name);
      return 2;
    }
  return e->workspace->filter (out, prog, input != NULL ? input : "");
}

/* The functions guests defined, each with the state that answers it, so make's call lands in the namespace that made it.  */
struct amk_func
  {
    char *name;
    void *state;
    char *(*fn) (void *state, const char *name, unsigned int argc, char **argv);
  };
static struct amk_func *amk_funcs;
static unsigned int amk_funcs_len;

static struct amk_func *
amk_func_find (const char *name)
{
  unsigned int i;
  for (i = 0; i < amk_funcs_len; ++i)
    if (streq (amk_funcs[i].name, name))
      return &amk_funcs[i];
  return NULL;
}

/* Every guest function enters make as this one, which hands the call to the state that defined the name.  */
static char *
amk_func_dispatch (const char *name, unsigned int argc, char **argv)
{
  struct amk_func *f = amk_func_find (name);
  return f != NULL ? f->fn (f->state, name, argc, argv) : NULL;
}

int
amk_func_add (const char *name, void *state, char *(*fn) (void *state, const char *name, unsigned int argc, char **argv))
{
  struct amk_func *f = amk_func_find (name);
  if (f != NULL)
    {
      if (f->state != state)
        return -1;
      f->fn = fn;
      return 1;
    }
  if (amk_function_exists (name))
    return -1;
  amk_funcs = xrealloc (amk_funcs, (amk_funcs_len + 1) * sizeof *amk_funcs);
  amk_funcs[amk_funcs_len].name = xstrdup (name);
  amk_funcs[amk_funcs_len].state = state;
  amk_funcs[amk_funcs_len].fn = fn;
  amk_funcs_len++;
  define_new_function (NILF, name, 0, 0, 0, amk_func_dispatch);
  return 0;
}

/* $(eng.ns name, op[, program]): the operation in a created namespace or main, or create, which makes the namespace and its handles.  */
char *
func_ns (char *o, char **argv, const char *funcname)
{
  const struct amk_engine *e = amk_engine_by_name (funcname);
  const struct amk_engine *owner;
  char *ns = amk_trim (argv[0]);
  char *op = amk_trim (argv[1]);

  if (!amk_ns_valid (ns))
    OSS (fatal, reading_file, _("%s: namespace \"%s\" is not a name"), funcname, ns);
  if (streq (op, "create"))
    {
      if (argv[2] != NULL && !amk_engine_is_workspace (e))
        OS (fatal, reading_file, _("%s: create takes no program"), funcname);
      amk_ns_create (e, ns, funcname);
      /* A workspace's create may name a backing, which a forwarder declares to the owner up the channel.  */
      if (argv[2] != NULL)
        {
          char *spec = amk_trim (argv[2]);
          if (amk_call_forwarding ())
            {
              struct amk_expand_sink sink;
              char *line = xmalloc (strlen (ns) + strlen (spec) + 9);
              sink.base.write = amk_expand_write;
              sink.o = o;
              sprintf (line, "create %s %s", ns, spec);
              if (amk_call_forward (line, &sink.base) != 0)
                OSS (fatal, reading_file, _("%s: namespace %s: the owner refused the backing"), funcname, ns);
              free (line);
            }
          else if (amk_workspace_backing (ns, spec) != 0)
            OSS (fatal, reading_file, _("%s: namespace %s: the backing was refused"), funcname, ns);
        }
      return o;
    }
  if (!amk_engine_has_op (e, op, strlen (op)))
    OSSS (fatal, reading_file, _("%s: expected an op, got \"%s\"; one of %s create"), funcname, op, amk_engine_ops (e));
  if (argv[2] == NULL)
    OSS (fatal, reading_file, _("%s %s: no program"), funcname, op);
  if (!streq (ns, "main"))
    {
      owner = amk_ns_owner (ns);
      if (owner == NULL)
        OSS (fatal, reading_file, _("%s: namespace %s was never created"), funcname, ns);
      if (owner != e)
        OSSS (fatal, reading_file, _("%s: namespace %s belongs to %s"), funcname, ns, owner->name);
    }
  return amk_ns_run (o, e, ns, op, argv[2], funcname);
}

/* $(name.import.target target,program[,flags]): the program stored as the variable target, and the rules that run it, with the engine's flags ahead of the program, into a cached value and print it under the target's name.  */
char *
func_import_target (char *o, char **argv, const char *funcname)
{
  const struct amk_engine *e = amk_engine_by_name (funcname);
  char *name = amk_trim (argv[0]);
  const char *body = argv[1] != NULL ? argv[1] : "";
  const char *flags = argv[1] != NULL && argv[2] != NULL ? amk_trim (argv[2]) : NULL;

  if (*name == '\0')
    OS (fatal, reading_file, _("%s: no target named"), funcname);
  define_variable_global (name, strlen (name), body, o_file, 1, reading_file);
  amk_import_target (name, e->name, body, flags, reading_file);
  return o;
}

/* Whether a builtin's name is a workspace row's import.  */
int
amk_is_workspace_import (const char *name)
{
  const struct amk_engine *e = amk_engine_by_name (name);
  return amk_engine_is_workspace (e) && streq (name + strcspn (name, "."), ".import");
}

/* $(jq.import name,text): the namespace made as create makes it, handles included, with the one text loaded as its whole value; importing the name again replaces the value.  */
char *
func_workspace_import (char *o, char **argv, const char *funcname)
{
  const struct amk_engine *e = amk_engine_by_name (funcname);
  struct amk_text_sink sink = { { amk_text_write }, NULL, 0 };
  char *ns = amk_trim (argv[0]);
  struct amk_ns *row;
  int rc;

  if (argv[1] == NULL)
    OS (fatal, reading_file, _("%s: no text; give a namespace and its JSON, or put the at line above a define"), funcname);
  if (!amk_ns_valid (ns))
    OSS (fatal, reading_file, _("%s: namespace \"%s\" is not a name"), funcname, ns);
  if (amk_call_forwarding ())
    OS (fatal, reading_file, _("%s: an import's text does not travel the call channel"), funcname);
  amk_ns_create (e, ns, funcname);
  row = amk_ns_find (e, ns);
  rc = amk_ns_apply (e, row, &sink.base, "load", argv[1]);
  free (sink.buf);
  if (rc != 0)
    OSS (fatal, reading_file, _("%s: %s: the text did not load as one value"), funcname, ns);
  return o;
}

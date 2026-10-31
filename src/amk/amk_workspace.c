/* Workspaces: the datastructure interface on a namespace, with its backings, the ask channel's entry points, and imports.  */

#include "makeint.h"
#include "filedef.h"
#include "variable.h"
#include "dep.h"
#include "job.h"
#include "os.h"
#include "commands.h"
#include "debug.h"
#include "amk.h"
#include <sys/stat.h>

/* A backing is a mode and, past run, a path: run keeps the value in the workspace alone, owned loads the file once at first use and writes every update through, shared also reloads when the file changed since the last load; an engine with open uses the file as its store instead, held alone when owned.  */
#define AMK_BACK_RUN 1
#define AMK_BACK_OWNED 2
#define AMK_BACK_SHARED 3
static const char *const amk_back_names[] = { "none", "run", "owned", "shared" };

/* The backings declared so far, one per workspace namespace that has one, with the file's time and size at the last load or write.  */
struct amk_backing
  {
    char *name;
    const struct amk_engine *engine;
    unsigned int mode:2;
    unsigned int loaded:1;
    char *path;
    time_t mtime;
    off_t size;
  };
static struct amk_backing *amk_backings;
static unsigned int amk_backings_len;

static struct amk_backing *
amk_backing_find (const struct amk_engine *e, const char *name)
{
  unsigned int i;
  for (i = 0; i < amk_backings_len; ++i)
    if (amk_backings[i].engine == e && streq (amk_backings[i].name, name))
      return &amk_backings[i];
  return NULL;
}

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
amk_backing_slurp (const char *path)
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

/* The file into the state when the mode says so: an engine whose file is its store opens it once at first use; any other loads it, owned at first use, shared whenever the file's time or size moved since the last load, a missing or empty file loading nothing.  */
int
amk_backing_sync_in (const struct amk_engine *e, const char *ns, void **statep)
{
  struct amk_backing *b = amk_backing_find (e, ns);
  struct amk_text_sink sink = { { amk_text_write }, NULL, 0 };
  void *state = *statep;
  struct stat st;
  char *text;
  int rc, moved;

  if (b == NULL || b->mode < AMK_BACK_OWNED)
    return 0;
  if (e->workspace != NULL && e->workspace->open != NULL)
    {
      if (b->loaded)
        return 0;
      state = e->workspace->open (state, b->path, b->mode == AMK_BACK_SHARED);
      if (state == NULL)
        {
          fprintf (stderr, "amk: workspace: %s: cannot open %s\n", b->name, b->path);
          return 2;
        }
      *statep = state;
      b->loaded = 1;
      return 0;
    }
  if (stat (b->path, &st) < 0 || st.st_size == 0)
    {
      b->loaded = 1;
      return 0;
    }
  moved = st.st_mtime != b->mtime || st.st_size != b->size;
  if (b->loaded && (b->mode == AMK_BACK_OWNED || !moved))
    return 0;
  text = amk_backing_slurp (b->path);
  if (text == NULL)
    {
      fprintf (stderr, "amk: workspace: %s: cannot read %s\n", b->name, b->path);
      return 2;
    }
  if (getenv ("AMK_DEBUG") != 0)
    fprintf (stderr, "amk: workspace: %s loaded from %s\n", b->name, b->path);
  rc = amk_state_run (e, state, &sink.base, "load", text);
  free (text);
  free (sink.buf);
  if (rc != 0)
    return 2;
  b->loaded = 1;
  b->mtime = st.st_mtime;
  b->size = st.st_size;
  return 0;
}

/* The state into the file after a write, through a temp file beside it and a rename, with the file's new time and size kept so the next call does not read its own write back.  */
int
amk_backing_sync_out (const struct amk_engine *e, const char *ns, void *state, const char *op)
{
  struct amk_backing *b;
  struct amk_text_sink sink = { { amk_text_write }, NULL, 0 };
  struct stat st;
  char *tmp;
  FILE *f;
  int rc;

  if (!streq (op, "update") && !streq (op, "load"))
    return 0;
  b = amk_backing_find (e, ns);
  if (b == NULL || b->mode < AMK_BACK_OWNED || (e->workspace != NULL && e->workspace->open != NULL))
    return 0;
  rc = amk_state_run (e, state, &sink.base, "dump", "");
  if (rc != 0)
    {
      free (sink.buf);
      return 2;
    }
  tmp = xmalloc (strlen (b->path) + 32);
  sprintf (tmp, "%s.tmp.%ld", b->path, (long) getpid ());
  f = fopen (tmp, "w");
  if (f == NULL || (sink.len > 0 && fwrite (sink.buf, 1, sink.len, f) != sink.len) || fclose (f) != 0
      || rename (tmp, b->path) < 0)
    {
      fprintf (stderr, "amk: workspace: %s: cannot write %s\n", b->name, b->path);
      unlink (tmp);
      free (tmp);
      free (sink.buf);
      return 2;
    }
  free (tmp);
  free (sink.buf);
  if (stat (b->path, &st) == 0)
    {
      b->mtime = st.st_mtime;
      b->size = st.st_size;
    }
  b->loaded = 1;
  return 0;
}

/* A workspace's backing declaration, a mode word then a path, which claims the name for the workspace on first use; a second declaration must repeat the first.  */
int
amk_workspace_backing (const char *ns, const char *spec)
{
  const struct amk_engine *e = amk_workspace_engine (ns);
  const struct amk_engine *owner;
  struct amk_backing *b;
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
  /* A forwarder's create names its engine first; the namespace is claimed for it, and with no backing after it that is the whole request.  */
  if (word != NULL && amk_engine_by_name (word) != NULL && amk_engine_is_workspace (amk_engine_by_name (word)))
    {
      const struct amk_engine *named = amk_engine_by_name (word);
      if (owner != NULL && owner != named)
        {
          fprintf (stderr, "amk: workspace: namespace %s belongs to %s\n", ns, owner->name);
          free (copy);
          return 2;
        }
      e = named;
      word = strtok (NULL, " \t");
      if (word == NULL)
        {
          amk_ns_open (e, ns, 0);
          free (copy);
          return 0;
        }
    }
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
  amk_ns_open (e, ns, 0);
  b = amk_backing_find (e, ns);
  if (b != NULL)
    {
      int same = b->mode == mode && ((b->path == NULL && path == NULL)
                                     || (b->path != NULL && path != NULL && streq (b->path, path)));
      free (copy);
      if (same)
        return 0;
      fprintf (stderr, "amk: workspace: %s is backed as %s%s%s already\n", ns, amk_back_names[b->mode],
               b->path != NULL ? " " : "", b->path != NULL ? b->path : "");
      return 2;
    }
  amk_backings = xrealloc (amk_backings, (amk_backings_len + 1) * sizeof *amk_backings);
  b = &amk_backings[amk_backings_len++];
  b->name = xstrdup (ns);
  b->engine = e;
  b->mode = mode;
  b->loaded = 0;
  b->path = path != NULL ? xstrdup (path) : NULL;
  b->mtime = 0;
  b->size = 0;
  free (copy);
  return 0;
}

/* A create's backing, run or a mode and its path joined by an equals sign, or none; a forwarder declares every create to the owner up the channel in the wire form, its engine first, so the owner claims the namespace for that engine, and a refusal is fatal.  */
void
amk_workspace_declare (char *o, const struct amk_engine *e, const char *ns, const char *make_spec, const char *funcname)
{
  char *copy = make_spec != NULL ? xstrdup (make_spec) : NULL;
  char *path = NULL;
  char *mode = copy != NULL ? amk_kwarg (copy, &path) : NULL;
  char *spec;

  if (mode != NULL && path == NULL && !streq (mode, "run"))
    OSSS (fatal, reading_file, _("%s: namespace %s: expected a backing, one of run, owned=PATH, shared=PATH; got: %s"),
          funcname, ns, make_spec);
  spec = xmalloc ((mode != NULL ? strlen (mode) : 0) + (path != NULL ? strlen (path) : 0) + 2);
  sprintf (spec, path != NULL ? "%s %s" : "%s", mode != NULL ? mode : "", path);
  free (copy);
  if (amk_ask_forwarding ())
    {
      struct amk_expand_sink sink;
      char *line = xmalloc (strlen (ns) + strlen (e->name) + strlen (spec) + 10);
      sink.base.write = amk_expand_write;
      sink.o = o;
      sprintf (line, "create %s %s %s", ns, e->name, spec);
      if (amk_ask_forward (line, &sink.base) != 0)
        OSS (fatal, reading_file, _("%s: namespace %s: the owner refused the backing"), funcname, ns);
      free (line);
    }
  else if (mode != NULL && amk_workspace_backing (ns, spec) != 0)
    OSS (fatal, reading_file, _("%s: namespace %s: the backing was refused"), funcname, ns);
  free (spec);
}

/* A forwarder has no workspace of its own: its call goes up the channel as a request line, which a load's text cannot ride.  */
int
amk_workspace_forward (struct amk_sink *out, const char *op, const char *ns, const char *prog, const char *funcname)
{
  char *line;
  int rc;
  if (streq (op, "load"))
    OS (error, NILF, _("$(%s ...): a load's text does not travel the ask channel"), funcname);
  line = xmalloc (strlen (op) + strlen (ns) + strlen (prog) + 3);
  sprintf (line, "%s %s %s", op, ns, prog);
  rc = amk_ask_forward (line, out);
  free (line);
  return rc;
}

/* The workspace row a namespace name reaches: its owner, else the first workspace row in the build.  */
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

/* The ask channel's filter: the named engine's stateless run over the input text; an engine without one is refused by name.  */
int
amk_workspace_filter (struct amk_sink *out, const char *engine, const char *prog, const char *input)
{
  const struct amk_engine *e = amk_engine_by_name (engine);
  if (e == NULL)
    {
      fprintf (stderr, "amk: ask: filter: no engine named %s\n", engine);
      return 2;
    }
  if (e->workspace == NULL || e->workspace->filter == NULL)
    {
      fprintf (stderr, "amk: ask: filter: %s has no filter\n", e->name);
      return 2;
    }
  return e->workspace->filter (out, prog, input != NULL ? input : "");
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
  int rc;

  if (argv[1] == NULL)
    OS (fatal, reading_file, _("%s: no text; give a namespace and its JSON, or put the at line above a define"), funcname);
  if (!amk_ns_valid (ns))
    OSS (fatal, reading_file, _("%s: namespace \"%s\" is not a name"), funcname, ns);
  if (amk_ask_forwarding ())
    OS (fatal, reading_file, _("%s: an import's text does not travel the ask channel"), funcname);
  amk_ns_create (e, ns, funcname);
  rc = amk_ns_apply (e, ns, &sink.base, "load", argv[1]);
  free (sink.buf);
  if (rc != 0)
    OSS (fatal, reading_file, _("%s: %s: the text did not load as one value"), funcname, ns);
  return o;
}

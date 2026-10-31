/* Namespaces: each engine's kept states by name, the operations that run in them, create and its handles, and the builtins that reach them.  */

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

const struct amk_engine *
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

void *
amk_ns_open (const struct amk_engine *e, const char *name, int open)
{
  struct amk_ns *ns = amk_ns_find (e, name);
  if (ns == NULL)
    ns = amk_ns_add (e, name);
  if (ns->state == NULL && open)
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

int
amk_state_run (const struct amk_engine *e, void *state, struct amk_sink *out, const char *op, const char *prog)
{
  const char *outer = amk_binding_engine;
  int rc;
  amk_binding_engine = e->name;
  rc = amk_state_member (e, state, out, op, prog);
  amk_binding_engine = outer;
  return rc;
}

int
amk_ns_valid (const char *name)
{
  size_t n = strlen (name);
  return n > 0 && n < 200 && strpbrk (name, " \t\n'\"\\") == NULL;
}

/* An engine reports that the operation running now changed its state; a load always does.  */
static int amk_changed;

void
amk_ns_changed (void)
{
  amk_changed = 1;
}

/* An engine reports that the nonzero status of the operation running now is its answer, not a failure.  */
static int amk_answered;

void
amk_ns_answered (void)
{
  amk_answered = 1;
}

/* Whether the engine answered with its status since the last take, clearing the mark, for a call outside a namespace.  */
int
amk_ns_answered_take (void)
{
  int answered = amk_answered;
  amk_answered = 0;
  return answered;
}

int
amk_ns_apply (const struct amk_engine *e, const char *ns, struct amk_sink *out, const char *op, const char *prog)
{
  struct amk_ns *row = amk_ns_find (e, ns);
  int rc = amk_backing_sync_in (e, ns, &row->state);
  void *state = row->state;
  amk_changed = streq (op, "load");
  if (rc == 0)
    rc = amk_state_run (e, state, out, op, prog);
  if (rc == 0)
    rc = amk_backing_sync_out (e, ns, state, op);
  /* An operation that parks left the state as it was, whatever the engine reported, so it wakes nothing; the channel holds it.  */
  if (rc == AMK_PARK)
    {
      amk_ask_hold = 1;
      return 0;
    }
  if (amk_changed)
    amk_ns_version_bump (ns);
  return rc;
}

/* An ask's output, passed on to the asker and kept, so an import can credit the names it printed.  */
struct amk_tee_sink { struct amk_sink base; struct amk_sink *out; char *buf; size_t len; };

static void
amk_tee_write (struct amk_sink *s, const char *p, size_t n)
{
  struct amk_tee_sink *t = (struct amk_tee_sink *) s;
  t->out->write (t->out, p, n);
  t->buf = xrealloc (t->buf, t->len + n + 1);
  memcpy (t->buf + t->len, p, n);
  t->len += n;
}

/* An op asked over the channel, on the namespace's owner or, for a name none holds, the first workspace row, which makes it on first use; an op the owner lacks answers the usage status.  */
int
amk_ns_ask (struct amk_sink *out, const char *op, const char *ns, const char *prog)
{
  const struct amk_engine *e;
  struct amk_tee_sink tee = { { amk_tee_write }, out, NULL, 0 };
  int rc;

  if (!amk_ns_valid (ns))
    {
      fprintf (stderr, "amk: ask: %s: namespace \"%s\" is not a name\n", op, ns);
      return 2;
    }
  e = amk_ns_owner (ns);
  if (e == NULL)
    e = amk_workspace_engine (NULL);
  if (e == NULL)
    {
      fprintf (stderr, "amk: ask: namespace \"%s\" was never created\n", ns);
      return 2;
    }
  if (!amk_engine_has_op (e, op, strlen (op)) && !(amk_engine_is_workspace (e) && streq (op, "dump")))
    {
      fprintf (stderr, "amk: ask: unknown operation \"%s\" on namespace \"%s\" (%s); one of: %s%s\n", op, ns, e->name,
               amk_engine_ops (e), amk_engine_is_workspace (e) ? " dump" : "");
      return 2;
    }
  if (amk_ns_open (e, ns, 1) == NULL)
    {
      fprintf (stderr, "amk: ask: cannot open a %s state\n", e->name);
      return 2;
    }
  if (!streq (op, "import"))
    return amk_ns_apply (e, ns, out, op, prog);
  rc = amk_ns_apply (e, ns, &tee.base, op, prog);
  if (rc == 0)
    amk_binding_vars (e->name, tee.buf != NULL ? tee.buf : "", tee.len);
  free (tee.buf);
  return rc;
}

/* An import's output kept and nothing shown, so a load line can credit the names without a value to put them in.  */
struct amk_buf_sink { struct amk_sink base; char *buf; size_t len; };

static void
amk_buf_write (struct amk_sink *s, const char *p, size_t n)
{
  struct amk_buf_sink *b = (struct amk_buf_sink *) s;
  b->buf = xrealloc (b->buf, b->len + n + 1);
  memcpy (b->buf + b->len, p, n);
  b->len += n;
}

static int amk_load_qualified (const char *path);
static char *amk_load_find (const floc *flocp, const char *lib, const char *path);

/* The library roots a payload name is looked up in, in order: each colon-separated entry of the path variable, spelled as python spells its own or as AMK_PATH, then the payload's own lib, so an entry shadows the payload as python's path shadows its stdlib.  */
static const char **
amk_load_roots (size_t *n)
{
  static const char **roots;
  static size_t count;
  if (roots == NULL)
    {
      const char *env = getenv ("AMKPATH");
      char *copy, *p;
      if (env == NULL)
        env = getenv ("AMK_PATH");
      copy = p = xstrdup (env != NULL ? env : "");
      while (*p)
        {
          size_t len = strcspn (p, ":");
          if (len > 0)
            {
              roots = xrealloc (roots, (count + 1) * sizeof *roots);
              roots[count++] = xstrndup (p, len);
            }
          p += len;
          if (*p == ':')
            ++p;
        }
      free (copy);
      roots = xrealloc (roots, (count + 1) * sizeof *roots);
      roots[count++] = "/zip/lib";
    }
  *n = count;
  return roots;
}

/* A payload name under one root's library for the engine, named by the row or by a user-defined engine.  */
static char *
amk_load_qualify (const char *root, const char *lib, const char *path)
{
  char *full = xmalloc (strlen (root) + strlen (lib) + strlen (path) + 3);
  if (*lib == '\0')
    sprintf (full, "%s/%s", root, path);
  else
    sprintf (full, "%s/%s/%s", root, lib, path);
  return full;
}

/* The user-defined engine that claims an extension or a library directory, as amk.engine recorded it; null for none.  */
static const char *
amk_user_engine (const char *ext)
{
  char var[128];
  struct variable *v;
  if (strlen (ext) > 100)
    return NULL;
  sprintf (var, "amk.engine.ext.%s", ext);
  v = lookup_variable (var, strlen (var));
  return v != NULL && *v->value != '\0' ? v->value : NULL;
}

/* The rest of a path tried at every depth under the root, the root itself included, in sorted order: the one match, with the count of them.  */
static char *
amk_load_walk (const char *root, const char *rest, size_t *count)
{
  char **names = NULL, *found = NULL;
  size_t n = 0, cap = 0, i, rlen = strlen (rest);
  amk_walk (root, &names, &n, &cap);
  qsort (names, n, sizeof *names, amk_walk_cmp);
  *count = 0;
  for (i = 0; i < n; ++i)
    {
      size_t len = strlen (names[i]);
      int hit = len > rlen && names[i][len - rlen - 1] == '/' && streq (names[i] + len - rlen, rest);
      if (hit)
        ++*count;
      if (hit && found == NULL)
        found = names[i];
      else
        free (names[i]);
    }
  free (names);
  if (*count > 1)
    {
      free (found);
      found = NULL;
    }
  return found;
}

/* One candidate path: with a ... component, the one file the walk below the directory before it finds; without, the file itself when it is there. The path, freed and null with errno otherwise.  */
static char *
amk_load_resolve_in (const floc *flocp, const char *name, char *full)
{
  char *p, *dots = NULL, *found;
  size_t count;

  for (p = full; dots == NULL && (p = strstr (p, "...")) != NULL; p += 3)
    if ((p == full || p[-1] == '/') && (p[3] == '/' || p[3] == '\0'))
      dots = p;
  if (dots == NULL)
    {
      if (access (full, R_OK) == 0)
        return full;
      free (full);
      errno = ENOENT;
      return NULL;
    }
  dots[-1] = '\0';
  found = amk_load_walk (full, dots + 4, &count);
  if (count > 1)
    OSN (fatal, flocp, _("load: %s: ... matches %d files"), name, (int) count);
  if (found == NULL)
    errno = ENOENT;
  free (full);
  return found;
}

/* A load line's file: the init stem refused since a module's init has other semantics, at most one whole ... component, then a qualified path as written or a payload name under each root in turn. The resolved path, or null with errno for a file that is not there; the errors of the line itself are fatal under -load too.  */
static char *
amk_load_resolve (const floc *flocp, const char *lib, const char *path)
{
  const char *base = strrchr (path, '/');
  const char *dot, *p, *dots = NULL;

  base = base != NULL ? base + 1 : path;
  dot = strrchr (base, '.');
  if (dot != NULL && dot - base == 4 && strncmp (base, "init", 4) == 0)
    OS (fatal, flocp, _("load: %s: init is a module's own file and has other semantics"), path);
  for (p = path; (p = strstr (p, "...")) != NULL; p += 3)
    if ((p == path || p[-1] == '/') && (p[3] == '/' || p[3] == '\0'))
      {
        if (dots != NULL)
          OS (fatal, flocp, _("load: %s: more than one ... component"), path);
        dots = p;
      }
  if (dots != NULL && dots[3] == '\0')
    OS (fatal, flocp, _("load: %s: a ... component needs a name after it"), path);
  return amk_load_find (flocp, lib, path);
}

/* A path as written when it names its place, else the first root holding it under the library, in the roots' order. The resolved path, or null with errno.  */
static char *
amk_load_find (const floc *flocp, const char *lib, const char *path)
{
  const char **roots;
  size_t n, i;
  char *found;

  if (amk_load_qualified (path))
    return amk_load_resolve_in (flocp, path, xstrdup (path));
  roots = amk_load_roots (&n);
  for (i = 0; i < n; ++i)
    {
      found = amk_load_resolve_in (flocp, path, amk_load_qualify (roots[i], lib, path));
      if (found != NULL)
        return found;
    }
  errno = ENOENT;
  return NULL;
}

/* $(amk.lib.find path): the file a payload path names under the library roots in load's order, a ... component walked and a path that names its place taken as written; nothing when no root holds it.  */
char *
amk_func_lib_find (char *o, char **argv, const char *funcname UNUSED)
{
  char *found = amk_load_find (reading_file, "", amk_trim (argv[0]));
  if (found != NULL)
    {
      o = variable_buffer_output (o, found, strlen (found));
      free (found);
    }
  return o;
}

/* $(amk.lib.roots ): the library roots in load's order, space separated; the argument is ignored, since make reads a bare reference as a variable.  */
char *
amk_func_lib_roots (char *o, char **argv UNUSED, const char *funcname UNUSED)
{
  const char **roots;
  size_t n, i;

  roots = amk_load_roots (&n);
  for (i = 0; i < n; ++i)
    {
      if (i > 0)
        o = variable_buffer_output (o, " ", 1);
      o = variable_buffer_output (o, roots[i], strlen (roots[i]));
    }
  return o;
}

/* Whether a path names its place: ./ and ../ for the working directory, / for the root; any other is a payload name.  */
static int
amk_load_qualified (const char *path)
{
  return path[0] == '/' || strncmp (path, "./", 2) == 0 || strncmp (path, "../", 3) == 0;
}

/* The files directly under an engine's library in one root, <root>/<eng>/<name>.<ext>, over the libraries sorted: the exact name when an extension was given, else any extension; the engine is the directory's. One match is the answer with its engine; every match is listed in all, space separated, and the count says whether the name is ambiguous.  */
static char *
amk_load_hammer_lib (const char *root, const char *name, int exact, const struct amk_engine **ep, const char **userp, char **all, size_t *count)
{
  char **names = NULL, *found = NULL;
  size_t n = 0, cap = 0, i, nlen = strlen (name), rlen = strlen (root);
  *all = NULL;
  *count = 0;
  amk_walk (root, &names, &n, &cap);
  qsort (names, n, sizeof *names, amk_walk_cmp);
  for (i = 0; i < n; ++i)
    {
      const char *dir = names[i] + rlen + 1, *slash = strchr (dir, '/'), *file = slash != NULL ? slash + 1 : NULL;
      const struct amk_engine *e = NULL;
      const char *user = NULL;
      if (file != NULL && strchr (file, '/') == NULL && strncmp (file, name, nlen) == 0
          && (exact ? file[nlen] == '\0' : file[nlen] == '.'))
        {
          char *eng = xstrndup (dir, slash - dir);
          e = amk_engine_by_extension (eng);
          if (e == NULL)
            user = amk_user_engine (eng);
          free (eng);
        }
      if (e == NULL && user == NULL)
        {
          free (names[i]);
          continue;
        }
      *all = xrealloc (*all, (*all != NULL ? strlen (*all) + 1 : 0) + strlen (names[i]) + 1);
      if (*count == 0)
        {
          strcpy (*all, names[i]);
          found = names[i];
          *ep = e;
          *userp = user;
        }
      else
        {
          strcat (*all, " ");
          strcat (*all, names[i]);
          free (names[i]);
        }
      ++*count;
    }
  free (names);
  if (*count > 1)
    {
      free (found);
      found = NULL;
    }
  return found;
}

/* Whether a word is in a list variable's value, so a load line is idempotent over the loaded paths and the included names alike.  */
static int
amk_var_has (const char *var, const char *path)
{
  struct variable *v = lookup_variable (var, strlen (var));
  const char *p = v != NULL ? v->value : "";
  size_t len = strlen (path);
  while (*p)
    {
      size_t n = strcspn (p, " ");
      if (n == len && memcmp (p, path, len) == 0)
        return 1;
      p += n;
      while (*p == ' ')
        ++p;
    }
  return 0;
}

/* The last fallback for a payload name no engine claims: the first lib/<eng>/<name>.<ext>, else the library amk.include would read, in its order and through it, so its guard holds. A warning names an engine file taken; an include is as quiet as include. The path and engine of the first form; null when a makefile was included, or, after the policy and a NoSuchModule fatal, when nothing was found; -load is silent instead.  */
static char *
amk_load_hammer (const floc *flocp, const char *name, int noerror, const struct amk_engine **ep, const char **userp)
{
  const char *ext = strrchr (name, '.');
  const char **roots;
  char *all, *text, *path, *found = NULL;
  size_t count = 0, nroots, i;

  roots = amk_load_roots (&nroots);
  for (i = 0; i < nroots && count == 0; ++i)
    {
      found = amk_load_hammer_lib (roots[i], name, ext != NULL, ep, userp, &all, &count);
      if (count > 1)
        {
          char why[1024];
          snprintf (why, sizeof why, "load: %s: ambiguous, %d engine libraries hold it: %s", name, (int) count, all);
          free (all);
          OS (fatal, flocp, "%s", why);
        }
      free (all);
    }
  if (found != NULL)
    {
      if (!amk_var_has (".LOADED", found))
        {
          char why[1024];
          snprintf (why, sizeof why, "load: %s: found as %s, loaded in %s", name, found, *ep != NULL ? (*ep)->name : *userp);
          amk_warning (flocp, why);
        }
      return found;
    }
  if (amk_var_has ("amk.included", name))
    return NULL;
  text = xmalloc (strlen (name) + 24);
  sprintf (text, "$(call amk.lib.path,%s)", name);
  path = allocated_variable_expand (text);
  free (text);
  if (*path != '\0')
    {
      if (!amk_var_has (".LOADED", path))
        {
          text = xmalloc (strlen (name) + 16);
          sprintf (text, "$(amk.include %s)\n", name);
          eval_buffer (text, flocp);
          free (text);
          do_variable_definition (flocp, ".LOADED", path, o_file, f_append_value, 0);
        }
      free (path);
      return NULL;
    }
  free (path);
  if (noerror)
    return NULL;
  {
    char why[1024];
    snprintf (why, sizeof why, "load: %s: no engine claims the name; each AMKPATH root and the payload's lib were searched as <root>/*/%s%s, then <root>/amk/%s.amk or .mk, then <root>/%s/init.amk%s%s%s",
              name, name, ext != NULL ? "" : ".*", name, name,
              strchr (name, '/') != NULL ? ", then <root>/" : "", strchr (name, '/') != NULL ? name : "", strchr (name, '/') != NULL ? ".amk, a part of its topic" : "");
    amk_warning (flocp, why);
  }
  OS (fatal, flocp, _("load: %s: NoSuchModule: ENOENT"), name);
}

/* A file into a user-defined engine: its text becomes the variable named by the file's basename, and the engine's import decorator runs on that name, the same point the at line reaches. Status 0 when the import ran, else nonzero with the engine's message above.  */
static int
amk_load_user (const floc *flocp, const char *user, const char *path)
{
  const char *base = strrchr (path, '/');
  unsigned char *text;
  char *macro, *call;
  size_t len;

  base = base != NULL ? base + 1 : path;
  macro = xmalloc (strlen (user) + 13);
  sprintf (macro, "%s.import_star", user);
  if (lookup_variable (macro, strlen (macro)) == NULL)
    OSS (fatal, flocp, _("load: %s: engine %s does not define its import decorator"), path, user);
  free (macro);
  text = amk_slurp (path, &len);
  if (text == NULL)
    return 1;
  text = xrealloc (text, len + 1);
  text[len] = '\0';
  do_variable_definition (flocp, base, (char *) text, o_file, f_simple, 0);
  free (text);
  call = xmalloc (strlen (user) + strlen (base) + 32);
  sprintf (call, "$(if $(call %s.import_star,%s),)\n", user, base);
  eval_buffer (call, flocp);
  free (call);
  return 0;
}

/* A load line: the file goes to the engine that claims its extension, a row or a user-defined one, in main, as an import of its text, of its path for a module engine, or as a workspace load. The answer is never-rebuild, since the file is read at the parse; under -load a file that does not load is silent.  */
int
amk_load_file (const floc *flocp, const char *name, int noerror)
{
  const char *base = strrchr (name, '/');
  const char *ext = strrchr (base != NULL ? base : name, '.');
  const struct amk_engine *e = ext != NULL ? amk_engine_by_extension (ext + 1) : NULL;
  const char *user = e == NULL && ext != NULL ? amk_user_engine (ext + 1) : NULL;
  struct amk_buf_sink sink = { { amk_buf_write }, NULL, 0 };
  unsigned char *text = NULL;
  const char *op, *prog;
  char *path;
  size_t len = 0;
  int rc;

  do_variable_definition (flocp, "amk.loaded", name, o_file, f_append_value, 0);
  if (ext != NULL && strncmp (ext, ".so", 3) == 0 && (ext[3] == '\0' || ext[3] == '('))
    OS (fatal, flocp, _("load: %s: PlatformError: ENOSYS: amk is portable via cosmocc, no support for .so"), name);
  if (e == NULL && user == NULL && amk_load_qualified (name))
    {
      if (noerror)
        return -1;
      OSS (fatal, flocp, _("load: %s: no engine claims the extension; one of %s"), name, amk_engine_extensions ());
    }
  if (e != NULL || user != NULL)
    path = amk_load_resolve (flocp, e != NULL ? e->name : user, name);
  else
    path = amk_load_hammer (flocp, name, noerror, &e, &user);
  if (path == NULL)
    {
      if (noerror || (e == NULL && user == NULL))
        return -1;
      OSS (fatal, flocp, _("load: %s: %s"), name, strerror (errno));
    }
  if (amk_var_has (".LOADED", path))
    {
      free (path);
      return -1;
    }
  if (user != NULL)
    {
      rc = amk_load_user (flocp, user, path);
      if (rc != 0 && !noerror)
        OSS (fatal, flocp, _("load: %s: %s"), name, strerror (errno));
      if (rc == 0)
        do_variable_definition (flocp, ".LOADED", path, o_file, f_append_value, 0);
      free (path);
      return -1;
    }
  prog = path;
  op = e->state != NULL ? "import" : "load";
  if (e->state == NULL || !e->state->module)
    {
      text = amk_slurp (path, &len);
      if (text != NULL)
        {
          text = xrealloc (text, len + 1);
          text[len] = '\0';
          prog = (const char *) text;
        }
    }
  else if (access (path, R_OK) != 0)
    text = NULL;
  else
    text = (unsigned char *) xstrdup (path);
  if (text == NULL)
    {
      free (path);
      if (noerror)
        return -1;
      OSS (fatal, flocp, _("load: %s: %s"), name, strerror (errno));
    }
  if (amk_ns_state (e, "main", 1) == NULL)
    OS (fatal, flocp, _("load: cannot open a %s state"), e->name);
  if (amk_engine_is_workspace (e) && amk_ask_forwarding ())
    rc = amk_workspace_forward (&sink.base, op, "main", prog, "load");
  else
    rc = amk_ns_apply (e, "main", &sink.base, op, prog);
  if (rc == 0 && e->state != NULL)
    amk_binding_vars (e->name, sink.buf != NULL ? sink.buf : "", sink.len);
  free (sink.buf);
  free (text);
  if (rc != 0 && !noerror)
    {
      char why[512];
      snprintf (why, sizeof why, "load: %s: %s %s exited with status %d", path, e->name, op, rc);
      OS (fatal, flocp, "%s", why);
    }
  if (rc == 0)
    do_variable_definition (flocp, ".LOADED", path, o_file, f_append_value, 0);
  free (path);
  return -1;
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
  amk_answered = 0;
  if (amk_engine_is_workspace (e) && amk_ask_forwarding ())
    rc = amk_workspace_forward (&sink.base, op, ns, prog, funcname);
  else if (streq (op, "version"))
    {
      amk_ns_version_write (&sink.base, ns);
      rc = 0;
    }
  else if (streq (op, "wait"))
    OS (fatal, reading_file, _("%s: the owner would wait on itself; call it from a recipe, a target or a spawned job"), funcname);
  else
    {
      if (amk_ns_state (e, ns, 1) == NULL)
        OSS (fatal, reading_file, _("%s: cannot open a %s state"), funcname, e->name);
      rc = amk_ns_apply (e, ns, &sink.base, op, prog);
      if (amk_ask_hold)
        {
          amk_ask_hold = 0;
          OS (fatal, reading_file, _("%s: the operation parked, and the owner would wait on itself; call it from a recipe, a target or a spawned job"), funcname);
        }
    }
  shell_completed (rc, 0);
  o = sink.o;

  /* An operation that failed fails the call that made it, unless the engine answered with that status.  */
  if (rc != 0 && !amk_answered)
    {
      char why[256];
      snprintf (why, sizeof why, "%s: %s %s exited with status %d", funcname, e->name, op, rc);
      amk_fail (why);
    }

  /* One trailing newline goes, as for every builtin; the buffer may have moved, so the start is an offset.  */
  if ((size_t) (o - variable_buffer) > start && o[-1] == '\n')
    {
      --o;
      if ((size_t) (o - variable_buffer) > start && o[-1] == '\r')
        --o;
    }

  if (streq (op, "import"))
    amk_binding_vars (e->name, variable_buffer + start, o - variable_buffer - start);
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

void
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
  /* Handles only for the ops the row has, so a name outside its interface stays free for a library to define.  */
  for (p = amk_engine_ops (e); (w = find_next_token (&p, &wlen)) != NULL;)
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
  for (p = amk_engine_ops (e); (w = find_next_token (&p, &wlen)) != NULL;)
    {
      amk_handle_add (ns, w, wlen, 0);
      amk_handle_add (ns, w, wlen, 1);
    }
  /* The makefile side sees the namespaces that exist, so a library building on one knows its handles are there.  */
  do_variable_definition (reading_file, "amk.namespaces", ns, o_file, f_append_value, 0);
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
      if (amk_engine_is_workspace (e) && (argv[2] != NULL || amk_ask_forwarding ()))
        amk_workspace_declare (o, e, ns, argv[2] != NULL ? amk_trim (argv[2]) : NULL, funcname);
      return o;
    }
  if (!amk_engine_has_op (e, op, strlen (op)) && !(amk_engine_is_workspace (e) && amk_ns_channel_op (op)))
    OSSS (fatal, reading_file, _("%s: expected an op, got \"%s\"; one of %s create, and version wait on a workspace"), funcname, op, amk_engine_ops (e));
  if (argv[2] == NULL && !streq (op, "version"))
    OSS (fatal, reading_file, _("%s %s: no program"), funcname, op);
  if (!streq (ns, "main"))
    {
      owner = amk_ns_owner (ns);
      if (owner == NULL)
        OSS (fatal, reading_file, _("%s: namespace %s was never created"), funcname, ns);
      if (owner != e)
        OSSS (fatal, reading_file, _("%s: namespace %s belongs to %s"), funcname, ns, owner->name);
    }
  return amk_ns_run (o, e, ns, op, argv[2] != NULL ? argv[2] : "", funcname);
}

/* $(eng.ns.create name[, backing]): $(eng.ns name, create[, backing]) under its own name.  */
char *
func_ns_create (char *o, char **argv, const char *funcname)
{
  char create[] = "create";
  char *args[4] = { argv[0], create, argv[1], NULL };
  return func_ns (o, args, funcname);
}

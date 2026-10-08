/* Goal references: the >>name<< references in an imported body, their resolution to targets and value files after the parse, and the values spliced into the body inside the job's fork. The value policy lives here too: which targets have their standard output as their value, and the capture of a recipe target's output into its value file.  */

#include "makeint.h"
#include "filedef.h"
#include "dep.h"
#include "commands.h"
#include "variable.h"
#include "hash.h"
#include "amk.h"
#include <fcntl.h>
#include <sys/stat.h>

/* Whether a special target such as .PHONY lists a name among its prerequisites, read before snap_deps marks the files.  */
static int
amk_listed (const char *special, const char *name)
{
  const struct file *f;
  const struct dep *d;

  for (f = lookup_file (special); f != NULL; f = f->prev)
    for (d = f->deps; d != NULL; d = d->next)
      if (streq (dep_name (d), name))
        return 1;
  return 0;
}

/* Whether a target has no recipe to run: none at all, or an empty rule.  */
static int
amk_recipe_empty (const struct file *f)
{
  const char *p = f->cmds != NULL ? f->cmds->commands : NULL;

  if (p == NULL)
    return 1;
  while (ISSPACE (*p))
    ++p;
  return *p == '\0';
}

/* The value policy, in one place. A target's value is its standard output unless it is marked as a file or has no recipe, and that output is kept for one run only when the target is phony or marked no-cache. An imported target's name is phony by construction and its output is always its value.  */
enum amk_value_kind
amk_value_kind (const struct file *f)
{
  if (f->amk_engine != NULL)
    return AMK_VALUE_STDOUT;
  if (amk_recipe_empty (f) || amk_listed (".AMK_FILE", f->name))
    return AMK_VALUE_FILE;
  if (amk_listed (".AMK_NOCACHE", f->name) || amk_listed (".PHONY", f->name))
    return AMK_VALUE_STDOUT_NOCACHE;
  return AMK_VALUE_STDOUT;
}

/* Whether a file is a kept value: a value file under the value directory, whichever target's output fills it.  */
int
amk_value_kept (const struct file *f)
{
  return f != NULL && f->amk_value != NULL && streq (f->amk_value, f->name);
}

/* Whether a target's job prints its kept value rather than running anything: a name whose value file is kept elsewhere.  */
int
amk_value_prints (const struct file *f)
{
  return f != NULL && f->amk_value != NULL && !streq (f->amk_value, f->name);
}

/* The width of the digraph on either side of a goal name.  */
#define AMK_GOAL_MARK 2

/* The next goal reference at or after p: a name of letters, digits, underscore, dot, dash and slash between an opening >> and a closing <<; answers the opening mark and the name's length.  */
static const char *
amk_goal_ref_next (const char *p, size_t *len)
{
  for (; (p = strstr (p, ">>")) != NULL; ++p)
    {
      const char *name = p + AMK_GOAL_MARK;
      size_t n = 0;
      while (isalnum ((unsigned char) name[n]) || (name[n] != '\0' && strchr ("_.-/", name[n]) != NULL))
        ++n;
      if (n > 0 && name[n] == '<' && name[n + 1] == '<')
        {
          *len = n;
          return p;
        }
    }
  return NULL;
}

/* Every goal an imported body references, each spelling once, not yet resolved.  */
struct amk_goal_ref *
amk_goal_refs (const char *body)
{
  struct amk_goal_ref *refs = NULL, *r;
  const char *p = body;
  size_t len;

  while ((p = amk_goal_ref_next (p, &len)) != NULL)
    {
      const char *word = strcache_add_len (p + AMK_GOAL_MARK, len);
      for (r = refs; r != NULL && r->word != word; r = r->next)
        ;
      if (r == NULL)
        {
          r = xcalloc (sizeof *r);
          r->word = word;
          r->next = refs;
          refs = r;
        }
      p += len + 2 * AMK_GOAL_MARK;
    }
  return refs;
}

/* One more spelling a reference could mean; a second distinct one is kept to be reported.  */
static void
amk_goal_candidate (const char *name, const char **first, const char **second)
{
  if (*first == NULL)
    *first = name;
  else if (*first != name && *second == NULL)
    *second = name;
}

/* The target a reference names, in any case: a target a makefile names, bare or under the value directory, and never a file that is only on disk.  */
static const char *
amk_goal_named (const char *dir, const char *word, const char **second)
{
  size_t dlen = strlen (dir);
  const char *first = NULL;
  struct file **slot = (struct file **) files.ht_vec;
  struct file **end = slot + files.ht_size;

  for (; slot < end; ++slot)
    if (! HASH_VACANT (*slot) && (*slot)->is_target)
      {
        const char *n = (*slot)->name;
        if (strncmp (n, dir, dlen) == 0 && n[dlen] == '/')
          n += dlen + 1;
        if (strcasecmp (n, word) == 0)
          amk_goal_candidate (strcache_add (n), &first, second);
      }
  return first;
}

/* The value directory, allocated: the active mode's, or the default when the mode keeps none of its own.  */
char *
amk_goal_dir (void)
{
  const struct amk_mode *mode = amk_mode_active ();
  return mode->value_dir != NULL ? mode->value_dir () : xstrdup (".amk/goals");
}

/* After the makefiles are read, when some body holds a reference or the mode keeps every value: the value directory, and every reference resolved to one target, a plain file where it is. A target a body references whose value is its output gets a value file, which its name waits on, and under a mode with a value directory every imported target does; what a body reads is a prerequisite of its value file, or of its name when it keeps none.  */
void
amk_goal_refs_settle (void)
{
  struct file **slot = (struct file **) files.ht_vec;
  struct file **end = slot + files.ht_size;
  struct file **imported = xmalloc ((files.ht_fill + 1) * sizeof *imported);
  struct file **valued = xmalloc ((files.ht_fill + 1) * sizeof *valued);
  size_t count = 0, reading = 0, nvalued = 0, dlen, i;
  int keep_all = amk_mode_active ()->value_dir != NULL;
  char *dir, *text;

  for (; slot < end; ++slot)
    if (! HASH_VACANT (*slot) && (*slot)->amk_engine != NULL)
      {
        imported[count++] = *slot;
        reading += (*slot)->amk_refs != NULL;
      }
  if (count == 0 || (reading == 0 && !keep_all))
    {
      free (imported);
      free (valued);
      return;
    }

  dir = amk_goal_dir ();
  dlen = strlen (dir);
  text = xmalloc (dlen + 24);
  sprintf (text, "$(shell mkdir -p %s)\n", dir);
  eval_buffer (text, &imported[0]->cmds->fileinfo);
  free (text);

  for (i = 0; i < count; ++i)
    {
      struct file *f = imported[i];
      const floc *flocp = &f->cmds->fileinfo;
      struct amk_goal_ref *r;

      for (r = f->amk_refs; r != NULL; r = r->next)
        {
          const char *second = NULL;
          const char *name = amk_goal_named (dir, r->word, &second);
          struct file *read;
          char *path;

          if (name == NULL)
            OSS (fatal, flocp, _(">>%s<< in imported target '%s' names no target, and a file needs a rule to be one; an operator between two names needs spaces around it"), r->word, f->amk_program);
          if (second != NULL)
            fatal (flocp, strlen (r->word) + strlen (f->amk_program) + strlen (name) + strlen (second),
                   _(">>%s<< in imported target '%s' names both '%s' and '%s'"), r->word, f->amk_program, name, second);
          path = xmalloc (dlen + strlen (name) + 2);
          sprintf (path, "%s/%s", dir, name);
          read = lookup_file (name);
          if (read != NULL && read->is_target && amk_value_kind (read) != AMK_VALUE_FILE)
            {
              r->path = strcache_add (path);
              if (read->amk_value == NULL)
                {
                  read->amk_value = r->path;
                  if (read->amk_engine == NULL)
                    valued[nvalued++] = read;
                }
            }
          else
            r->path = lookup_file (path) != NULL ? strcache_add (path) : name;
          free (path);
        }
    }

  /* Under a mode with a value directory, an imported target nobody reads keeps its value too.  */
  if (keep_all)
    for (i = 0; i < count; ++i)
      if (imported[i]->amk_value == NULL)
        {
          char *path = xmalloc (dlen + strlen (imported[i]->name) + 2);
          sprintf (path, "%s/%s", dir, imported[i]->name);
          imported[i]->amk_value = strcache_add (path);
          free (path);
        }

  for (i = 0; i < count; ++i)
    {
      struct file *f = imported[i];
      const char *reader = f->amk_value != NULL ? f->amk_value : f->name;
      const struct amk_goal_ref *r;
      const struct dep *d;
      size_t len = 3 * strlen (reader) + 2 * strlen (f->name) + 24;

      for (r = f->amk_refs; r != NULL; r = r->next)
        len += strlen (r->path) + 1;
      for (d = f->deps; d != NULL; d = d->next)
        len += strlen (dep_name (d)) + 1;
      text = xmalloc (len);
      text[0] = '\0';
      if (f->amk_value != NULL)
        sprintf (text, "%s:; @: %s\n%s: %s\n", reader, f->name, f->name, reader);
      sprintf (text + strlen (text), "%s:", reader);
      for (r = f->amk_refs; r != NULL; r = r->next)
        sprintf (text + strlen (text), " %s", r->path);
      /* The prerequisites a makefile wrote on the name are the value's inputs too, so a kept value reruns when one changes.  */
      if (f->amk_value != NULL)
        for (d = f->deps; d != NULL; d = d->next)
          sprintf (text + strlen (text), " %s", dep_name (d));
      strcat (text, "\n");
      eval_buffer (text, &f->cmds->fileinfo);
      free (text);
      if (f->amk_value != NULL)
        {
          struct file *kept = lookup_file (reader);
          kept->amk_engine = f->amk_engine;
          kept->amk_program = f->amk_program;
          kept->amk_flags = f->amk_flags;
          kept->amk_refs = f->amk_refs;
          kept->amk_value = kept->name;
        }
    }

  /* A recipe target some body reads: its recipe moves to its value file, where its output lands, with the name's prerequisites as the value's inputs; the name waits on the value and its own job prints it. A no-cache value is phony, so it is computed once per run and never reused.  */
  for (i = 0; i < nvalued; ++i)
    {
      struct file *f = valued[i];
      const char *reader = f->amk_value;
      struct file *kept;
      struct commands *print;
      const struct dep *d;
      size_t len = 3 * strlen (reader) + strlen (f->name) + 32;

      for (d = f->deps; d != NULL; d = d->next)
        len += strlen (dep_name (d)) + 1;
      text = xmalloc (len);
      sprintf (text, "%s: %s\n%s:", f->name, reader, reader);
      for (d = f->deps; d != NULL; d = d->next)
        sprintf (text + strlen (text), " %s", dep_name (d));
      strcat (text, "\n");
      if (amk_value_kind (f) == AMK_VALUE_STDOUT_NOCACHE)
        sprintf (text + strlen (text), ".PHONY: %s\n", reader);
      eval_buffer (text, &f->cmds->fileinfo);
      free (text);
      kept = lookup_file (reader);
      kept->cmds = f->cmds;
      kept->amk_name = f->name;
      kept->amk_value = kept->name;
      print = xcalloc (sizeof *print);
      print->fileinfo = f->cmds->fileinfo;
      print->commands = xstrdup ("@: value\n");
      f->cmds = print;
    }
  free (valued);
  free (imported);
  free (dir);
}

/* The value file the recipe line about to run prints into, or -1 when the line is no kept recipe value's.  */
static int amk_value_out = -1;

/* Before a recipe child starts: a kept recipe value's file opens for its line to append onto.  */
void
amk_value_capture (const struct file *f)
{
  amk_value_release ();
  if (!amk_value_kept (f) || f->amk_name == NULL)
    return;
  amk_value_out = open (f->name, O_WRONLY | O_CREAT | O_APPEND, 0666);
  if (amk_value_out < 0)
    OSS (fatal, NILF, _("amk: %s: cannot write its value: %s"), f->name, strerror (errno));
}

int
amk_value_fd (void)
{
  return amk_value_out;
}

/* Once the child is started: this side's descriptor goes.  */
void
amk_value_release (void)
{
  if (amk_value_out >= 0)
    close (amk_value_out);
  amk_value_out = -1;
}

/* Before a kept recipe value's recipe: its file starts empty, so the lines append this run's output alone.  */
void
amk_value_recipe_start (const struct file *f)
{
  int fd;

  if (!amk_value_kept (f) || f->amk_name == NULL)
    return;
  fd = open (f->name, O_WRONLY | O_CREAT | O_TRUNC, 0666);
  if (fd < 0)
    OSS (fatal, NILF, _("amk: %s: cannot write its value: %s"), f->name, strerror (errno));
  close (fd);
}

/* After a kept recipe value's recipe succeeds: a value left empty by a recipe that wrote the file of its name instead is a failure, reported, since that target wants the file mark.  */
int
amk_value_recipe_end (const struct file *f)
{
  struct stat value, named;

  if (!amk_value_kept (f) || f->amk_name == NULL)
    return 1;
  if (stat (f->name, &value) != 0 || value.st_size > 0)
    return 1;
  if (stat (f->amk_name, &named) != 0 || !S_ISREG (named.st_mode))
    return 1;
  if (FILE_TIMESTAMP_STAT_MODTIME (f->amk_name, named) < FILE_TIMESTAMP_STAT_MODTIME (f->name, value))
    return 1;
  OS (error, NILF, _("%s wrote its file but printed nothing; mark it @amk.file"), f->amk_name);
  return 0;
}

/* A goal's value: the text of its file less one trailing newline, allocated, or null when the file cannot be read.  */
char *
amk_goal_value (const char *path)
{
  FILE *fp = fopen (path, "r");
  char *value = NULL;
  size_t len = 0, n;

  if (fp == NULL)
    return NULL;
  do
    {
      value = xrealloc (value, len + 4097);
      n = fread (value + len, 1, 4096, fp);
      len += n;
    }
  while (n > 0);
  fclose (fp);
  if (len > 0 && value[len - 1] == '\n' && --len > 0 && value[len - 1] == '\r')
    --len;
  value[len] = '\0';
  return value;
}

/* An imported body for its engine, inside the job's fork: each reference replaced by its value, raw, less one trailing newline, and nothing else touched.  */
char *
amk_goal_splice (const struct file *file, const char *body)
{
  size_t size = strlen (body) + 1, used = 0, len;
  char *out = xmalloc (size);
  const char *p = body, *at;

  while ((at = amk_goal_ref_next (p, &len)) != NULL)
    {
      const struct amk_goal_ref *r;
      char *value = NULL;
      size_t vlen = 0;

      for (r = file->amk_refs; r != NULL; r = r->next)
        if (strlen (r->word) == len && strncasecmp (r->word, at + AMK_GOAL_MARK, len) == 0 && r->path != NULL)
          break;
      if (r != NULL)
        {
          value = amk_goal_value (r->path);
          if (value == NULL)
            {
              fprintf (stderr, "amk: %s: >>%s<< has no value at %s: %s\n", file->name, r->word, r->path, strerror (errno));
              _exit (127);
            }
          vlen = strlen (value);
          at += len + 2 * AMK_GOAL_MARK;
        }
      else
        ++at;

      size += vlen + (size_t) (at - p);
      out = xrealloc (out, size);
      if (r != NULL)
        {
          memcpy (out + used, p, (size_t) (at - p) - len - 2 * AMK_GOAL_MARK);
          used += (size_t) (at - p) - len - 2 * AMK_GOAL_MARK;
          memcpy (out + used, value, vlen);
          used += vlen;
        }
      else
        {
          memcpy (out + used, p, (size_t) (at - p));
          used += (size_t) (at - p);
        }
      free (value);
      p = at;
    }
  strcpy (out + used, p);
  return out;
}

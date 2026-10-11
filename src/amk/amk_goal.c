/* Goal references: the @name@ references in an imported body, their resolution to targets and value files after the parse, and the values spliced into the body inside the job's fork.  */

#include "makeint.h"
#include "filedef.h"
#include "dep.h"
#include "commands.h"
#include "variable.h"
#include "hash.h"
#include "amk.h"

/* The next goal reference at or after p: a name of letters, digits, underscore, dot, dash and slash between two at signs; answers the opening sign and the name's length.  */
static const char *
amk_goal_ref_next (const char *p, size_t *len)
{
  for (; (p = strchr (p, '@')) != NULL; ++p)
    {
      size_t n = 0;
      while (isalnum ((unsigned char) p[1 + n]) || (p[1 + n] != '\0' && strchr ("_.-/", p[1 + n]) != NULL))
        ++n;
      if (n > 0 && p[1 + n] == '@')
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
      const char *word = strcache_add_len (p + 1, len);
      for (r = refs; r != NULL && r->word != word; r = r->next)
        ;
      if (r == NULL)
        {
          r = xcalloc (sizeof *r);
          r->word = word;
          r->next = refs;
          refs = r;
        }
      p += len + 2;
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

/* The value directory, allocated: what a makefile or the command line assigned to goal.dir, or the default.  */
char *
amk_goal_dir (void)
{
  const struct variable *v = lookup_variable ("goal.dir", 8);
  return v != NULL && v->value[0] != '\0' ? allocated_variable_expand ("$(goal.dir)") : xstrdup (".amk/goals");
}

/* After the makefiles are read, and only when some body holds a reference: the value directory, and every reference resolved to one target, a plain file where it is. A target a body references gets a value file, which its name waits on; what a body reads is a prerequisite of its value file, or of its name when it keeps none.  */
void
amk_goal_refs_settle (void)
{
  struct file **slot = (struct file **) files.ht_vec;
  struct file **end = slot + files.ht_size;
  struct file **imported = xmalloc ((files.ht_fill + 1) * sizeof *imported);
  size_t count = 0, reading = 0, dlen, i;
  char *dir, *text;

  for (; slot < end; ++slot)
    if (! HASH_VACANT (*slot) && (*slot)->amk_engine != NULL)
      {
        imported[count++] = *slot;
        reading += (*slot)->amk_refs != NULL;
      }
  if (reading == 0)
    {
      free (imported);
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
            OSS (fatal, flocp, _("@%s@ in imported target '%s' names no target, and a file needs a rule to be one; an operator between two names needs spaces around it"), r->word, f->amk_program);
          if (second != NULL)
            fatal (flocp, strlen (r->word) + strlen (f->amk_program) + strlen (name) + strlen (second),
                   _("@%s@ in imported target '%s' names both '%s' and '%s'"), r->word, f->amk_program, name, second);
          path = xmalloc (dlen + strlen (name) + 2);
          sprintf (path, "%s/%s", dir, name);
          read = lookup_file (name);
          if (read != NULL && read->amk_engine != NULL)
            read->amk_value = r->path = strcache_add (path);
          else
            r->path = lookup_file (path) != NULL ? strcache_add (path) : name;
          free (path);
        }
    }

  for (i = 0; i < count; ++i)
    {
      struct file *f = imported[i];
      const char *reader = f->amk_value != NULL ? f->amk_value : f->name;
      const struct amk_goal_ref *r;
      size_t len = 3 * strlen (reader) + 2 * strlen (f->name) + 24;

      for (r = f->amk_refs; r != NULL; r = r->next)
        len += strlen (r->path) + 1;
      text = xmalloc (len);
      text[0] = '\0';
      if (f->amk_value != NULL)
        sprintf (text, "%s:; @: %s\n%s: %s\n", reader, f->name, f->name, reader);
      sprintf (text + strlen (text), "%s:", reader);
      for (r = f->amk_refs; r != NULL; r = r->next)
        sprintf (text + strlen (text), " %s", r->path);
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
  free (imported);
  free (dir);
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
        if (strlen (r->word) == len && strncasecmp (r->word, at + 1, len) == 0 && r->path != NULL)
          break;
      if (r != NULL)
        {
          value = amk_goal_value (r->path);
          if (value == NULL)
            {
              fprintf (stderr, "amk: %s: @%s@ has no value at %s: %s\n", file->name, r->word, r->path, strerror (errno));
              _exit (127);
            }
          vlen = strlen (value);
          at += len + 2;
        }
      else
        ++at;

      size += vlen + (size_t) (at - p);
      out = xrealloc (out, size);
      if (r != NULL)
        {
          memcpy (out + used, p, (size_t) (at - p) - len - 2);
          used += (size_t) (at - p) - len - 2;
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

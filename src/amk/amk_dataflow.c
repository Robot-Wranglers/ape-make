/* The dataflow mode: a record beside every kept value, imported or a recipe target's, a failed value moved aside with its engine's stderr, a file that existed before a failed recipe kept, early cutoff when a value's content does not change, and a rerun when its body does.  */

#include "makeint.h"
#include "filedef.h"
#include "dep.h"
#include "commands.h"
#include "variable.h"
#include "hash.h"
#include "amk.h"
#include <fcntl.h>
#include <sys/stat.h>

/* The value directory, allocated: amk.dataflow_dir, else the environment's, else one per run under the top-level make's pid; exported, so every sub-make of the run shares it.  */
static char *
amk_dataflow_dir (void)
{
  char dflt[64];
  char *dir;

  sprintf (dflt, ".amk/dataflow-%ld", (long) getpid ());
  dir = amk_setting ("amk.dataflow_dir", "AMK_DATAFLOW_DIR", dflt);
  setenv ("AMK_DATAFLOW_DIR", dir, 1);
  return dir;
}

/* A file beside a target, allocated: its name and a suffix.  */
static char *
amk_beside (const char *name, const char *suffix)
{
  char *path = xmalloc (strlen (name) + strlen (suffix) + 1);
  sprintf (path, "%s%s", name, suffix);
  return path;
}

/* Whether a path is a regular file.  */
static int
amk_regular (const char *path)
{
  struct stat st;
  return stat (path, &st) == 0 && S_ISREG (st.st_mode);
}

/* A copy of a file, mode and all, in place of whatever the destination held; false when either side fails.  */
static int
amk_copy_file (const char *from, const char *to)
{
  struct stat st;
  char buf[65536];
  ssize_t n;
  int in, out, ok = 1;

  if ((in = open (from, O_RDONLY)) < 0)
    return 0;
  if (fstat (in, &st) != 0 || (out = open (to, O_WRONLY | O_CREAT | O_TRUNC, st.st_mode & 07777)) < 0)
    {
      close (in);
      return 0;
    }
  while ((n = read (in, buf, sizeof buf)) > 0)
    if (!amk_write_all (out, buf, (size_t) n))
      {
        ok = 0;
        break;
      }
  ok = ok && n == 0;
  close (in);
  close (out);
  return ok;
}

/* The checksum of a value's body as make holds it, as the cksum builtin prints it: an imported target's program, or a recipe target's recipe text, unexpanded either way.  */
static void
amk_body_cksum (const struct file *f, char *buf)
{
  const struct variable *v = f->amk_program != NULL ? lookup_variable (f->amk_program, strlen (f->amk_program)) : NULL;
  const char *body = v != NULL ? v->value : f->cmds != NULL && f->cmds->commands != NULL ? f->cmds->commands : "";
  sprintf (buf, "%lu-%lu", amk_cksum ((const unsigned char *) body, strlen (body)), (unsigned long) strlen (body));
}

/* The body field of a value's record, allocated, or null when there is no record.  */
static char *
amk_record_body (const char *name)
{
  char *path = amk_beside (name, ".json");
  char *text = amk_goal_value (path);
  char *body = NULL, *p, *end;

  free (path);
  if (text != NULL && (p = strstr (text, "\"body\":\"")) != NULL && (end = strchr (p += 8, '"')) != NULL)
    body = xstrndup (p, (size_t) (end - p));
  free (text);
  return body;
}

/* One json string, escaped, onto a stream.  */
static void
amk_json_string (FILE *fp, const char *s)
{
  putc ('"', fp);
  for (; *s != '\0'; ++s)
    if (*s == '"' || *s == '\\')
      fprintf (fp, "\\%c", *s);
    else if ((unsigned char) *s < 0x20)
      fprintf (fp, "\\u%04x", (unsigned char) *s);
    else
      putc (*s, fp);
  putc ('"', fp);
}

/* The record beside a kept value, one json object: its engine, the job's exit status, its body's checksum, and the checksum of each declared input, null for one that cannot be read.  */
static void
amk_record_write (const struct file *f, int status)
{
  char *path = amk_beside (f->name, ".json");
  FILE *fp = fopen (path, "w");
  const struct dep *d;
  char body[64];
  int first = 1;

  free (path);
  if (fp == NULL)
    return;
  amk_body_cksum (f, body);
  fprintf (fp, "{\"engine\":\"%s\",\"status\":%d,\"body\":\"%s\",\"inputs\":{", f->amk_engine != NULL ? f->amk_engine->name : "recipe", status, body);
  for (d = f->deps; d != NULL; d = d->next)
    {
      const char *input = dep_name (d);
      int ok;
      unsigned long crc = amk_cksum_file (input, &ok);
      if (!first)
        putc (',', fp);
      first = 0;
      amk_json_string (fp, input);
      if (ok)
        fprintf (fp, ":\"%lu\"", crc);
      else
        fputs (":null", fp);
    }
  fputs ("}}\n", fp);
  fclose (fp);
}

/* After the parse: a kept value whose body differs from its record moves aside, so make rebuilds it whatever the mtimes say, and the rebuild compares against it.  */
static void
amk_dataflow_settled (void)
{
  struct file **slot = (struct file **) files.ht_vec;
  struct file **end = slot + files.ht_size;

  for (; slot < end; ++slot)
    if (! HASH_VACANT (*slot) && amk_value_kept (*slot))
      {
        const struct file *f = *slot;
        char *was = amk_record_body (f->name);
        char body[64];
        amk_body_cksum (f, body);
        if (was == NULL || !streq (was, body))
          {
            char *prev = amk_beside (f->name, ".prev");
            rename (f->name, prev);
            free (prev);
          }
        free (was);
      }
}

/* Inside the job's fork: an engine's stderr goes to the log beside its value.  */
static void
amk_dataflow_job_start (struct file *f)
{
  if (amk_value_kept (f) && f->amk_engine != NULL)
    {
      char *err = amk_beside (f->name, ".err");
      if (freopen (err, "w", stderr) == NULL)
        fprintf (stderr, "amk: %s: cannot log stderr to %s: %s\n", f->name, err, strerror (errno));
      free (err);
    }
}

/* Before a recipe: a kept value moves aside for the comparison after, and a file that existed before is copied aside so a failure can put it back.  */
static void
amk_dataflow_recipe_start (struct file *f)
{
  char *prev;

  if (f == NULL || f->phony || f->precious)
    return;
  prev = amk_beside (f->name, ".prev");
  if (amk_value_kept (f))
    rename (f->name, prev);
  else if (f->amk_engine == NULL && amk_regular (f->name) && !amk_copy_file (f->name, prev))
    OSS (error, NILF, _("amk: %s: cannot keep a copy at %s"), f->name, prev);
  free (prev);
}

/* On failure, before make's own deletion: a kept value moves to its failed name and its stderr log prints beside make's error; a file that existed before comes back and is marked precious; a file this run made goes.  */
static void
amk_dataflow_target_failed (struct file *f, int status)
{
  char *prev;

  if (f == NULL || f->phony || f->precious)
    return;
  prev = amk_beside (f->name, ".prev");
  if (amk_value_kept (f))
    {
      char *failed = amk_beside (f->name, ".failed");
      char *err = amk_beside (f->name, ".err");
      char *text = amk_goal_value (err);
      rename (f->name, failed);
      if (text != NULL && *text != '\0')
        fprintf (stderr, "amk: %s: stderr, kept at %s:\n%s\n", f->name, err, text);
      amk_record_write (f, status);
      free (text);
      free (err);
      free (failed);
    }
  else if (f->amk_engine == NULL)
    {
      if (amk_regular (prev))
        {
          if (rename (prev, f->name) == 0)
            f->precious = 1;
        }
      else if (amk_regular (f->name))
        {
          OS (error, NILF, _("*** Deleting file '%s'"), f->name);
          unlink (f->name);
        }
    }
  free (prev);
}

/* After a recipe succeeds: a kept value whose content matches the one moved aside takes that one back, mtime and all, so nothing downstream reruns; its record is written either way, and a copy kept for a file goes.  */
static void
amk_dataflow_recipe_end (struct file *f, int status)
{
  char *prev;

  if (f == NULL || f->phony || f->precious)
    return;
  prev = amk_beside (f->name, ".prev");
  if (amk_value_kept (f))
    {
      int ok_new, ok_old;
      unsigned long now = amk_cksum_file (f->name, &ok_new);
      unsigned long was = amk_cksum_file (prev, &ok_old);
      char *failed = amk_beside (f->name, ".failed");
      if (ok_new && ok_old && now == was)
        rename (prev, f->name);
      else
        unlink (prev);
      unlink (failed);
      amk_record_write (f, status);
      free (failed);
    }
  else
    unlink (prev);
  free (prev);
}

/* The mode's ear on the event bus.  */
static void
amk_dataflow_hook (enum amk_event event, const struct amk_event_info *info)
{
  struct file *f = info->target != NULL ? lookup_file (info->target) : NULL;

  switch (event)
    {
    case AMK_EVENT_SETTLED:
      amk_dataflow_settled ();
      break;
    case AMK_EVENT_JOB_START:
      amk_dataflow_job_start (f);
      break;
    case AMK_EVENT_RECIPE_START:
      amk_dataflow_recipe_start (f);
      break;
    case AMK_EVENT_TARGET_FAILED:
      amk_dataflow_target_failed (f, info->exit_sig != 0 ? 128 + info->exit_sig : info->exit_code);
      break;
    case AMK_EVENT_RECIPE_END:
      if (info->status != NULL && streq (info->status, "success"))
        amk_dataflow_recipe_end (f, info->exit_code);
      break;
    default:
      break;
    }
}

const struct amk_mode amk_dataflow_mode = { "dataflow", amk_dataflow_hook, amk_dataflow_dir };

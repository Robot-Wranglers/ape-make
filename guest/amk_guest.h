/* The make side of every guest, declared once: resolved at link, so no guest keeps a header of make's. */

#ifndef AMK_GUEST_H
#define AMK_GUEST_H

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <unistd.h>

/* Where a persistent entry's result goes: write appends bytes, and make decides where they land. */
struct amk_sink
{
  void (*write) (struct amk_sink *, const char *, size_t);
};
extern struct amk_sink amk_sink_stderr;

/* The spawn api: a goal list run in a fork of this parsed image, the wait that collects it, the verbs over it, and the mail between them. */
extern pid_t amk_spawn_goals (int n, char **words, int foreground, const char *stdout_path);
extern int amk_wait_child (pid_t want, int block, pid_t *got, int *code, int *sig, int *stopped);
extern int amk_kill_child (pid_t pid, int sig);
extern int amk_foreground (pid_t pid);
extern int amk_mail_take (pid_t pid, char **buf, size_t *len);
extern int amk_mail_send (const char *s, size_t n);

/* The handle: expand and the variable reads, the writes that queue from a forked guest, and the function registration a persistent state may use. */
extern char *gmk_expand (const char *str);
extern void gmk_free (char *str);
extern char *gmk_alloc (unsigned int len);
extern void gmk_add_function (const char *name, char *(*func) (const char *, unsigned int, char **),
                              unsigned int min, unsigned int max, unsigned int flags);
extern int amk_has_db (void);
extern int amk_function_exists (const char *name);
extern char *amk_var_get (const char *name);
extern void amk_var_set (const char *name, const char *value);
extern void amk_eval (const char *text);

/* Whether the builtin that called a persistent entry, its first argument, carries the given suffix, as name.export does. */
static inline int
amk_entry_is (const char *argv0, const char *suffix)
{
  const char *dot = argv0 ? strrchr (argv0, '.') : NULL;
  return dot != NULL && strcmp (dot + 1, suffix) == 0;
}

/* Whether a name is one make can spell for a variable or a function. */
static inline int
amk_name_ok (const char *name)
{
  const char *p = name;
  if (*p == '\0' || *p == '_')
    return 0;
  for (; *p; p++)
    if (!((*p >= 'a' && *p <= 'z') || (*p >= 'A' && *p <= 'Z') || (*p >= '0' && *p <= '9')
          || *p == '_' || *p == '-' || *p == '.'))
      return 0;
  return 1;
}

/* A capture of standard output for a persistent entry whose engine writes the descriptor rather than a function the guest can rebind: what the chunk wrote goes to the sink when the capture ends. */
struct amk_capture
{
  FILE *file;
  int saved;
};

static inline void
amk_capture_begin (struct amk_capture *c)
{
  fflush (stdout);
  c->file = tmpfile ();
  c->saved = c->file ? dup (STDOUT_FILENO) : -1;
  if (c->saved >= 0)
    dup2 (fileno (c->file), STDOUT_FILENO);
}

static inline void
amk_capture_end (struct amk_capture *c, struct amk_sink *out)
{
  char buf[4096];

  fflush (stdout);
  if (c->saved >= 0)
    {
      dup2 (c->saved, STDOUT_FILENO);
      close (c->saved);
    }
  if (c->file == NULL)
    return;
  lseek (fileno (c->file), 0, SEEK_SET);
  while (1)
    {
      ssize_t r = read (fileno (c->file), buf, sizeof buf);
      if (r < 0 && errno == EINTR)
        continue;
      if (r <= 0)
        break;
      out->write (out, buf, (size_t) r);
    }
  fclose (c->file);
}

#endif

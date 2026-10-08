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
extern struct amk_sink amk_sink_stdout;

/* The spawn api: a goal list run in a fork of this parsed image, the wait that collects it, the verbs over it, and the mail between them. */
extern pid_t amk_spawn_goals (int n, char **words, int foreground, const char *stdout_path);
extern int amk_wait_child (pid_t want, int block, pid_t *got, int *code, int *sig, int *stopped);
extern int amk_kill_child (pid_t pid, int sig);
extern int amk_stop_child (pid_t pid);
extern int amk_spawn_live (pid_t pid);
extern int amk_ask_fds (int *fds, int max);
extern void amk_ask_wait (int ms);
/* A guest's own request line to the owner: begin answers a number, or -1 when it parked in the owner; poll answers the raw reply once it is here and collect waits for it; result turns a reply into the text, the caller's to free, or -1 with the reason in err. */
extern long amk_ask_begin (const char *line);
extern char *amk_ask_poll (unsigned long id);
extern char *amk_ask_collect (unsigned long id);
extern int amk_ask_result (char *reply, char **text, const char **err);
#define AMK_ASK_PARKED "the operation parked, and the owner would wait on itself; call it from a recipe, a target or a spawned job"

/* One request line from an op, a namespace and the values after them, space-joined; the caller frees it. */
static inline char *
amk_ask_line (const char *op, const char *ns, unsigned int n, const char **vals)
{
  size_t len = strlen (op) + strlen (ns) + 2, i;
  char *line;
  for (i = 0; i < n; i++)
    len += strlen (vals[i]) + 1;
  line = malloc (len + 1);
  strcpy (line, op);
  strcat (line, " ");
  strcat (line, ns);
  for (i = 0; i < n; i++)
    {
      strcat (line, " ");
      strcat (line, vals[i]);
    }
  return line;
}
extern void amk_ns_changed (void);
/* An engine reports that the nonzero status the operation running now answers is its answer, not a failure: jq's exit-status option, or a deadline, which answers empty. */
extern void amk_ns_answered (void);
/* The status an operation answers to be held and run again after the next change to its namespace; amk.h carries the same number. */
#define AMK_PARK 4
extern int amk_resume_child (pid_t pid);
extern int amk_foreground (pid_t pid);
extern void amk_exit_with (int status);
extern int amk_mail_take (pid_t pid, char **buf, size_t *len);
extern int amk_mail_send (const char *s, size_t n);

/* The handle: expand and the variable reads, the writes that queue from a forked guest, and the function registration a kept state may use: fn answers make's call in the state that defined the name, a name make has already is refused with -1. */
extern char *gmk_expand (const char *str);
extern void gmk_free (char *str);
extern char *gmk_alloc (unsigned int len);
extern int amk_func_add (const char *name, void *state, char *(*fn) (void *state, const char *name, unsigned int argc, char **argv));
extern int amk_has_db (void);
extern int amk_function_exists (const char *name);
extern char *amk_var_get (const char *name);
extern void amk_var_set (const char *name, const char *value);
extern char *amk_var_raw_get (const char *name);
extern void amk_var_raw_set (const char *name, const char *value);
extern void amk_eval (const char *text);
extern char *amk_call (const char *name, unsigned int argc, const char **args, const char **err);
/* A call by kind: the cascade for any, else that one layer by its full name; amk_resolve answers which layer the cascade would take, or -1 with the reason. */
enum amk_as { AMK_AS_ANY, AMK_AS_FXN, AMK_AS_MACRO };
extern char *amk_call_kind (int kind, const char *name, unsigned int argc, const char **args, const char **err);
extern int amk_resolve (const char *name, char *full, size_t len, const char **err);

/* A defined function that raised: its wrapper records the message here, and the call that made it fails with it. */
extern void amk_func_raise (const char *engine, const char *name, const char *msg);

/* The one deadline every guest's hook reads: push puts the tighter of ms and the one in force into effect, pop restores the one before and answers the budget that had run out, or -1. */
struct amk_deadline { double at; long ms; };
extern void amk_deadline_push (long ms, struct amk_deadline *saved);
extern long amk_deadline_pop (const struct amk_deadline *saved);
extern int amk_deadline_active (void);
extern int amk_deadline_expired (void);
extern long amk_deadline_budget (void);

/* The deferred call: begin forks the image to run the call and names the descriptor its result arrives on, end collects the text or the error once that descriptor reads as done. */
extern pid_t amk_call_begin (int kind, const char *name, unsigned int argc, const char **args, int *fd);
extern int amk_call_end (pid_t pid, char **text, const char **err);

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

/* The capture a chunk's sink calls for: none when the sink is stdout itself, so what the chunk writes streams out as it is written. */
static inline void
amk_capture_begin_to (struct amk_capture *c, struct amk_sink *out)
{
  if (out == &amk_sink_stdout)
    {
      c->file = NULL;
      c->saved = -1;
      return;
    }
  amk_capture_begin (c);
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

/* One word off a request line as a shell would read it, quotes honored and the escapes amk.words writes undone; the word is written into buf and p moves past it. */
static inline int
amk_word (const char **p, char *buf, size_t size)
{
  const char *s = *p;
  size_t n = 0;
  char quote = 0;
  while (*s == ' ' || *s == '\t')
    ++s;
  if (*s == '\0')
    {
      *p = s;
      return 0;
    }
  while (*s && (quote || (*s != ' ' && *s != '\t')))
    {
      if (!quote && (*s == '\'' || *s == '"'))
        quote = *s++;
      else if (*s == quote)
        {
          quote = 0;
          ++s;
        }
      else if (quote == '"' && *s == '\\' && s[1] == 'n')
        {
          if (n + 1 < size)
            buf[n++] = '\n';
          s += 2;
        }
      else
        {
          if (*s == '\\' && s[1] && (!quote || (quote == '"' && (s[1] == '"' || s[1] == '\\'))))
            ++s;
          if (n + 1 < size)
            buf[n++] = *s;
          ++s;
        }
    }
  buf[n] = '\0';
  *p = s;
  return 1;
}

#endif

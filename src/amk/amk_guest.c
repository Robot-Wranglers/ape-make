/* The guest handle's make side: variable reads and writes, eval, the queue a forked guest's writes ride up, the collector, $(goal), $(amk.stdin), and $(amk.bash).  */

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
#include <sys/wait.h>
#include "amk.h"

/* Inside a forked guest, the pipe every write goes up as a record; anywhere else, none, and a write applies at once.  */
int amk_queue_fd = -1;

/* Whether make has built its variable tables: not yet under an engine flag, where the guest runs before any makefile.  */
int
amk_has_db (void)
{
  return current_variable_set_list != NULL && current_variable_set_list->set->table.ht_vec != NULL;
}

/* The value a guest reads through its variable proxy: expanded the way a reference would be, and null rather than empty for a name make has never seen.  */
char *
amk_var_get (const char *name)
{
  struct variable *v;
  if (!amk_has_db ())
    return NULL;
  v = lookup_variable (name, strlen (name));
  if (v == NULL)
    return NULL;
  return recursively_expand (v);
}

/* The value a guest reads through its raw variable proxy: the text as stored, never expanded, and null for a name make has never seen.  */
char *
amk_var_raw_get (const char *name)
{
  struct variable *v;
  if (!amk_has_db ())
    return NULL;
  v = lookup_variable (name, strlen (name));
  if (v == NULL)
    return NULL;
  return xstrdup (v->value);
}

static void
amk_queue_write (int fd, const char *s, size_t n)
{
  while (n > 0)
    {
      ssize_t w = write (fd, s, n);
      if (w < 0 && errno == EINTR)
        continue;
      if (w <= 0)
        return;
      s += w;
      n -= w;
    }
}

/* One record: the kind, the two lengths, then the two bodies back to back.  */
static void
amk_queue_record (char kind, const char *a, const char *b)
{
  char head[64];
  size_t la = strlen (a);
  size_t lb = b ? strlen (b) : 0;
  int n = snprintf (head, sizeof head, "%c %lu %lu\n", kind, (unsigned long) la, (unsigned long) lb);
  amk_queue_write (amk_queue_fd, head, (size_t) n);
  amk_queue_write (amk_queue_fd, a, la);
  if (lb > 0)
    amk_queue_write (amk_queue_fd, b, lb);
}

/* A simple variable with the literal value, at file origin so an override still wins; queued from a forked guest.  */
void
amk_var_set (const char *name, const char *value)
{
  if (amk_queue_fd >= 0)
    {
      amk_queue_record ('V', name, value);
      return;
    }
  if (!amk_has_db ())
    return;
  define_variable_global (name, strlen (name), value, o_file, 0, NILF);
}

/* A recursive variable with the text as written, as a define makes one, at file origin; queued from a forked guest.  */
void
amk_var_raw_set (const char *name, const char *value)
{
  if (amk_queue_fd >= 0)
    {
      amk_queue_record ('D', name, value);
      return;
    }
  if (!amk_has_db ())
    return;
  define_variable_global (name, strlen (name), value, o_file, 1, NILF);
}

/* Text read as makefile syntax; queued from a forked guest.  */
void
amk_eval (const char *text)
{
  if (amk_queue_fd >= 0)
    {
      amk_queue_record ('E', text, NULL);
      return;
    }
  if (!amk_has_db ())
    return;
  gmk_eval (text, NULL);
}

/* The parent's side of the queue: every whole record in the buffer applied in order, a partial one left for the next read; the bytes consumed are returned.  */
static size_t
amk_queue_apply (const char *buf, size_t len)
{
  size_t pos = 0;
  while (pos < len)
    {
      char kind;
      unsigned long la, lb;
      int used = 0;
      char *a, *b;
      if (memchr (buf + pos, '\n', len - pos) == NULL
          || sscanf (buf + pos, "%c %lu %lu\n%n", &kind, &la, &lb, &used) < 3 || used == 0)
        break;
      if (pos + (size_t) used + la + lb > len)
        break;
      pos += (size_t) used;
      a = xstrndup (buf + pos, la);
      b = xstrndup (buf + pos + la, lb);
      pos += la + lb;
      if (kind == 'V')
        amk_var_set (a, b);
      else if (kind == 'D')
        amk_var_raw_set (a, b);
      else if (kind == 'E')
        amk_eval (a);
      free (a);
      free (b);
    }
  return pos;
}

/* The pipe read once it is ready: whole records applied, a partial one kept in the buffer, and the descriptor closed and set to -1 at its end.  */
static void
amk_queue_drain (int *fd, char **buf, size_t *len, size_t *cap)
{
  ssize_t r;
  if (*len == *cap)
    {
      *cap += 4096;
      *buf = xrealloc (*buf, *cap + 1);
    }
  r = read (*fd, *buf + *len, *cap - *len);
  if (r > 0)
    {
      size_t used;
      *len += r;
      (*buf)[*len] = '\0';
      used = amk_queue_apply (*buf, *len);
      memmove (*buf, *buf + used, *len - used);
      *len -= used;
    }
  else if (r == 0 || errno != EINTR)
    {
      close (*fd);
      *fd = -1;
    }
}

/* A child's output and its writes read until both end: the output into a buffer the caller frees, the writes applied by whole records as they come, and a feed, when one is given, written as the child takes it.  Every descriptor is closed and set to -1.  */
char *
amk_collect (int *out, size_t *outlen, int *q, int *in, const char *feed, size_t feedlen)
{
  char *buf = xmalloc (4097), *qbuf = NULL;
  size_t len = 0, cap = 4096, qlen = 0, qcap = 0;

  while (*out >= 0 || *q >= 0)
    {
      struct pollfd fds[3];
      int nfds = 0, iout = -1, iin = -1, iq = -1;
      ssize_t r;

      if (*out >= 0)
        {
          iout = nfds++;
          fds[iout].fd = *out;
          fds[iout].events = POLLIN;
          fds[iout].revents = 0;
        }
      if (in != NULL && *in >= 0)
        {
          iin = nfds++;
          fds[iin].fd = *in;
          fds[iin].events = POLLOUT;
          fds[iin].revents = 0;
        }
      if (*q >= 0)
        {
          iq = nfds++;
          fds[iq].fd = *q;
          fds[iq].events = POLLIN;
          fds[iq].revents = 0;
        }
      if (poll (fds, nfds, -1) < 0)
        {
          if (errno == EINTR)
            continue;
          break;
        }
      if (iin >= 0 && fds[iin].revents != 0)
        {
          ssize_t w = write (*in, feed, feedlen);
          if (w > 0)
            {
              feed += w;
              feedlen -= w;
            }
          else if (w < 0 && errno != EAGAIN && errno != EINTR)
            feedlen = 0;
          if (feedlen == 0)
            {
              close (*in);
              *in = -1;
            }
        }
      if (iq >= 0 && fds[iq].revents != 0)
        amk_queue_drain (q, &qbuf, &qlen, &qcap);
      if (iout < 0 || fds[iout].revents == 0)
        continue;
      if (len == cap)
        {
          cap += 4096;
          buf = xrealloc (buf, cap + 1);
        }
      r = read (*out, buf + len, cap - len);
      if (r < 0 && errno == EINTR)
        continue;
      if (r <= 0)
        {
          close (*out);
          *out = -1;
          continue;
        }
      len += r;
    }
  free (qbuf);
  if (*q >= 0)
    {
      close (*q);
      *q = -1;
    }
  if (*out >= 0)
    {
      close (*out);
      *out = -1;
    }
  if (in != NULL && *in >= 0)
    {
      close (*in);
      *in = -1;
    }
  buf[len] = '\0';
  *outlen = len;
  return buf;
}

/* $(goal name): the goal brought up to date by a fork of this image, then its value read: a kept value from its file, a plain file target in place, and an imported target that keeps none from what its run printed.  */
char *
amk_func_goal (char *o, char **argv, const char *funcname)
{
  char *name = argv[0];
  char *end, *path = NULL, *value, *words[1];
  struct file *f, ran;
  pid_t pid, got = 0;
  int code = 0, sig = 0, stopped = 0, printed;

  while (ISSPACE (*name))
    name++;
  end = name + strlen (name);
  while (end > name && ISSPACE (end[-1]))
    *--end = '\0';
  if (*name == '\0')
    OS (fatal, NILF, _("$(%s ...): no goal named"), funcname);
  f = lookup_file (name);
  printed = f != NULL && f->amk_engine != NULL && f->amk_value == NULL;
  if (printed)
    {
      /* The fork runs the target again even when this make already has, so its record of that is set aside for the fork.  */
      ran = *f;
      f->updated = 0;
      f->command_state = cs_not_started;
      amk_spawn_stdout_to_mail ();
    }
  else if (f != NULL && f->is_target && f->amk_engine == NULL)
    path = xstrdup (name);
  else
    {
      char *dir = amk_goal_dir ();
      path = xmalloc (strlen (dir) + strlen (name) + 2);
      sprintf (path, "%s/%s", dir, name);
      free (dir);
    }

  words[0] = printed ? name : path;
  pid = amk_spawn_goals (1, words, 0, printed ? NULL : "/dev/null");
  if (printed)
    {
      f->updated = ran.updated;
      f->command_state = ran.command_state;
    }
  if (pid < 0)
    OSS (fatal, NILF, _("$(%s %s): cannot fork"), funcname, name);
  do
    amk_wait_child (pid, 1, &got, &code, &sig, &stopped);
  while (stopped);
  if (code != 0 || sig != 0)
    OSS (fatal, NILF, _("$(%s %s): the goal failed"), funcname, name);

  if (printed)
    {
      /* What the job printed came up its mail, less one trailing newline as a value file would lose.  */
      size_t mlen = 0;
      if (!amk_mail_take (pid, &value, &mlen))
        value = NULL;
      else if (value == NULL)
        value = xstrdup ("");
      else
        {
          if (mlen > 0 && value[mlen - 1] == '\n' && --mlen > 0 && value[mlen - 1] == '\r')
            --mlen;
          value[mlen] = '\0';
        }
    }
  else
    value = amk_goal_value (path);
  if (value == NULL)
    OSS (fatal, NILF, _("$(%s %s): the goal left no value"), funcname, name);
  o = variable_buffer_output (o, value, strlen (value));
  free (value);
  free (path);
  return o;
}

/* The pipes waiting for their recipe lines, each keyed by the target's variable set and the line's index; one is pending for the child about to start.  */
struct amk_stdin
{
  const struct variable_set_list *set;
  unsigned long line;
  int fd;
};
static struct amk_stdin amk_stdins[64];
static const void *amk_stdin_child;
static int amk_stdin_ready = -1;

/* $(amk.stdin text): a pipe that carries the text, filled by a helper detached twice so no one waits on it, and kept for the recipe line being expanded.  */
char *
amk_func_stdin (char *o, char **argv, const char *funcname)
{
  int p[2];
  pid_t pid;
  unsigned int i;

  if (reading_file == NULL)
    OS (fatal, NILF, _("$(%s ...): only in a recipe"), funcname);
  for (i = 0; i < 64 && amk_stdins[i].fd > 0; ++i)
    ;
  if (i == 64 || pipe (p) < 0)
    OS (fatal, NILF, _("$(%s ...): cannot open a pipe"), funcname);
  fflush (NULL);
  pid = fork ();
  if (pid < 0)
    OS (fatal, NILF, _("$(%s ...): cannot fork"), funcname);
  if (pid == 0)
    {
      const char *s = argv[0];
      size_t n = strlen (s);
      if (fork () != 0)
        _exit (0);
      close (p[0]);
      signal (SIGPIPE, SIG_DFL);
      while (n > 0)
        {
          ssize_t w = write (p[1], s, n);
          if (w < 0 && errno == EINTR)
            continue;
          if (w <= 0)
            break;
          s += w;
          n -= w;
        }
      _exit (0);
    }
  waitpid (pid, NULL, 0);
  close (p[1]);
  amk_stdins[i].set = current_variable_set_list;
  amk_stdins[i].line = reading_file->offset;
  amk_stdins[i].fd = p[0];
  return o;
}

/* The child about to run a line: its pipe for that line, if one waits, becomes the ready descriptor.  */
void
amk_stdin_pending (struct child *child)
{
  unsigned int i;
  amk_stdin_child = child;
  amk_stdin_ready = -1;
  for (i = 0; i < 64; ++i)
    if (amk_stdins[i].fd > 0 && amk_stdins[i].set == child->file->variables
        && amk_stdins[i].line == child->command_line - 1)
      {
        amk_stdin_ready = amk_stdins[i].fd;
        amk_stdins[i].fd = 0;
        return;
      }
}

/* The ready pipe when this is the child it waits for, else -1 and make chooses as usual.  */
int
amk_stdin_fd (const void *child)
{
  if (child == amk_stdin_child && amk_stdin_ready >= 0)
    return amk_stdin_ready;
  return -1;
}

/* A finished child: the parent's end of the pipe its line read, and any pipe its lines never ran, go.  */
void
amk_stdin_drop (struct child *child)
{
  unsigned int i;
  if (child == amk_stdin_child)
    {
      if (amk_stdin_ready >= 0)
        close (amk_stdin_ready);
      amk_stdin_ready = -1;
      amk_stdin_child = NULL;
    }
  for (i = 0; i < 64; ++i)
    if (amk_stdins[i].fd > 0 && amk_stdins[i].set == child->file->variables)
      {
        close (amk_stdins[i].fd);
        amk_stdins[i].fd = 0;
      }
}

/* An engine flag followed by a lone dash: the program is standard input, read whole.  */
void
amk_program_from_stdin (const struct amk_engine *e, int argc, char **argv)
{
  char *buf;
  size_t len = 0, cap = 4096;
  if (e->cli->argv || argc < 2 || strcmp (argv[1], "-") != 0)
    return;
  buf = xmalloc (cap + 1);
  while (1)
    {
      ssize_t r;
      if (len == cap)
        buf = xrealloc (buf, (cap *= 2) + 1);
      r = read (STDIN_FILENO, buf + len, cap - len);
      if (r < 0 && errno == EINTR)
        continue;
      if (r <= 0)
        break;
      len += r;
    }
  buf[len] = '\0';
  argv[1] = buf;
}

/* $(amk.bash cmd): the command run by bash under -euo pipefail in one fork, never the makefile's SHELL, stdin closed, and its output kept with its lines intact, less one trailing newline; a nonzero status is fatal, 127 when bash is not found.  */
char *
amk_func_bash (char *o, char **argv, const char *funcname)
{
  char *av[] = { (char *) "bash", (char *) "-euo", (char *) "pipefail", (char *) "-c", argv[0], NULL };
  int out[2], q = -1, st = 0, status;
  size_t len = 0;
  char *buf, code[16];
  pid_t pid;

  if (pipe (out) < 0)
    OSS (fatal, NILF, _("$(%s ...): pipe: %s"), funcname, strerror (errno));
  fflush (stdout);
  fflush (stderr);
  pid = fork ();
  if (pid < 0)
    OSS (fatal, NILF, _("$(%s ...): fork: %s"), funcname, strerror (errno));
  if (pid == 0)
    {
      int nul = open ("/dev/null", O_RDONLY);
      if (nul >= 0)
        dup2 (nul, 0);
      dup2 (out[1], 1);
      close (out[0]);
      close (out[1]);
      signal (SIGPIPE, SIG_DFL);
      execvp ("bash", av);
      fprintf (stderr, "%s: bash: %s\n", funcname, strerror (errno));
      _exit (127);
    }

  close (out[1]);
  buf = amk_collect (&out[0], &len, &q, NULL, NULL, 0);
  while (waitpid (pid, &st, 0) < 0 && errno == EINTR)
    ;
  status = WIFEXITED (st) ? WEXITSTATUS (st) : 128 + WTERMSIG (st);
  if (status != 0)
    {
      sprintf (code, "%d", status);
      OSS (fatal, reading_file, _("$(%s ...): bash exited with status %s"), funcname, code);
    }
  if (len > 0 && buf[len - 1] == '\n')
    --len;
  if (len > 0)
    o = variable_buffer_output (o, buf, len);
  free (buf);
  return o;
}

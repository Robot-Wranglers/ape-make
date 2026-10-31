/* Spawned goal lists: the pids still out, and the ones make's own reaping collected before they were asked for.  */

#include "makeint.h"
#include "os.h"
#include "filedef.h"
#include "variable.h"
#include "job.h"
#include "commands.h"
#include <fcntl.h>
#include <poll.h>
#include <sys/wait.h>
#include "amk.h"

static pid_t amk_live[AMK_SPAWNED];
static struct { pid_t pid; int code; int sig; int stopped; } amk_parked[AMK_SPAWNED];
/* What each job runs, goals, goal or call, named in its record.  */
static struct { pid_t pid; const char *kind; } amk_kinds[AMK_SPAWNED];
/* Each job's mail: the read end of a pipe the job and its shells write, drained as it comes and handed over once the job is collected; inside a job, the write end.  */
static int amk_mail[AMK_SPAWNED];
static char *amk_mailbuf[AMK_SPAWNED];
static size_t amk_maillen[AMK_SPAWNED];
static struct { pid_t pid; char *buf; size_t len; } amk_mails[AMK_SPAWNED];
int amk_mail_fd = -1;
static int amk_spawn_mail_stdout;

static void
amk_drain (unsigned int i) {
  char tmp[4096];
  ssize_t r;
  int fd = amk_mail[i];
  if (fd <= 0)
    return;
  for (;;) {
    r = read (fd, tmp, sizeof tmp);
    if (r > 0) {
      amk_mailbuf[i] = xrealloc (amk_mailbuf[i], amk_maillen[i] + r + 1);
      memcpy (amk_mailbuf[i] + amk_maillen[i], tmp, r);
      amk_maillen[i] += r;
      amk_mailbuf[i][amk_maillen[i]] = '\0';
    } else if (r == 0) {
      close (fd);
      amk_mail[i] = 0;
      return;
    } else if (errno == EINTR) {
      continue;
    } else {
      return;
    }
  }
}

/* A collected job's mail, read to its end and set aside under the pid for amk_mail_take.  */
static void
amk_mail_finish (unsigned int i, pid_t pid) {
  unsigned int m;
  amk_drain (i);
  if (amk_mail[i] > 0) {
    close (amk_mail[i]);
    amk_mail[i] = 0;
  }
  amk_chan_close (&amk_chan[i]);
  for (m = 0; m < AMK_SPAWNED && amk_mails[m].pid != 0; ++m)
    ;
  if (m < AMK_SPAWNED) {
    amk_mails[m].pid = pid;
    amk_mails[m].buf = amk_mailbuf[i] != NULL ? amk_mailbuf[i] : xstrdup ("");
    amk_mails[m].len = amk_maillen[i];
  } else
    free (amk_mailbuf[i]);
  amk_mailbuf[i] = NULL;
  amk_maillen[i] = 0;
}

/* What a collected job wrote, once; the caller owns the buffer.  */
int
amk_mail_take (pid_t pid, char **buf, size_t *len) {
  unsigned int i;
  for (i = 0; i < AMK_SPAWNED; ++i)
    if (amk_mails[i].pid == pid) {
      *buf = amk_mails[i].buf;
      *len = amk_mails[i].len;
      amk_mails[i].pid = 0;
      amk_mails[i].buf = NULL;
      return 1;
    }
  return 0;
}

/* What a collected job wrote, left in place for the wait that takes it.  */
static int
amk_mail_peek (pid_t pid, const char **buf, size_t *len) {
  unsigned int i;
  for (i = 0; i < AMK_SPAWNED; ++i)
    if (amk_mails[i].pid == pid) {
      *buf = amk_mails[i].buf;
      *len = amk_mails[i].len;
      return 1;
    }
  return 0;
}

/* A job writes its mail; outside a job there is none to write.  */
int
amk_mail_send (const char *s, size_t n) {
  while (amk_mail_fd >= 0 && n > 0) {
    ssize_t w = write (amk_mail_fd, s, n);
    if (w < 0 && errno == EINTR)
      continue;
    if (w <= 0)
      return -1;
    s += w;
    n -= w;
  }
  return amk_mail_fd >= 0 ? 0 : -1;
}

static int
amk_live_drop (pid_t pid) {
  unsigned int i;
  for (i = 0; i < AMK_SPAWNED; ++i)
    if (amk_live[i] == pid) { amk_live[i] = 0; return 1; }
  return 0;
}

/* A record set aside for the wait that names its pid, or any wait.  */
static void
amk_park (pid_t pid, int code, int sig, int stopped) {
  unsigned int i;
  for (i = 0; i < AMK_SPAWNED; ++i)
    if (amk_parked[i].pid == 0) {
      amk_parked[i].pid = pid;
      amk_parked[i].code = code;
      amk_parked[i].sig = sig;
      amk_parked[i].stopped = stopped;
      return;
    }
}

void
amk_reap_foreign (pid_t pid, int code, int sig) {
  unsigned int i;
  for (i = 0; i < AMK_SPAWNED && amk_live[i] != pid; ++i)
    ;
  if (i == AMK_SPAWNED)
    return;
  amk_mail_finish (i, pid);
  amk_live_drop (pid);
  amk_park (pid, code, sig, 0);
}

/* Every spawned job is a process group, and one of them may hold the terminal.  */
static pid_t amk_tty_owner;

static int
amk_tty (void) {
  return isatty (STDIN_FILENO) ? STDIN_FILENO : -1;
}

/* The terminal to a group, with the stop the kernel sends a background caller set aside.  */
static void
amk_tty_give (pid_t pgrp) {
  int tty = amk_tty ();
  void (*old) (int);
  if (tty < 0)
    return;
  old = signal (SIGTTOU, SIG_IGN);
  if (tcsetpgrp (tty, pgrp) == 0)
    amk_tty_owner = pgrp;
  signal (SIGTTOU, old);
}

static void
amk_tty_take (void) {
  if (amk_tty_owner != 0 && amk_tty_owner != getpgrp ())
    amk_tty_give (getpgrp ());
  amk_tty_owner = 0;
}

/* A fork of this parsed image in a slot, with the mail pipe, the call pair, the group, and the signals set up on both sides; the parent gets the pid, the child 0 with what it runs left to the caller, and -1 is no slot or no fork.  */
static pid_t
amk_fork_slot (unsigned int *slot, int foreground, const char *stdout_path) {
  unsigned int i;
  pid_t pid;
  int p[2], req[2], rep[2];
  for (i = 0; i < AMK_SPAWNED && amk_live[i] != 0; ++i)
    ;
  if (i == AMK_SPAWNED)
    return -1;
  *slot = i;
  if (pipe (p) < 0)
    return -1;
  if (pipe (req) < 0 || pipe (rep) < 0) {
    close (p[0]);
    close (p[1]);
    return -1;
  }
  fflush (NULL);
  pid = fork ();
  if (pid < 0) {
    close (p[0]);
    close (p[1]);
    close (req[0]);
    close (req[1]);
    close (rep[0]);
    close (rep[1]);
    return -1;
  }
  if (pid > 0) {
    setpgid (pid, pid);
    amk_live[i] = pid;
    close (p[1]);
    fcntl (p[0], F_SETFL, fcntl (p[0], F_GETFL) | O_NONBLOCK);
    amk_mail[i] = p[0];
    free (amk_mailbuf[i]);
    amk_mailbuf[i] = NULL;
    amk_maillen[i] = 0;
    /* The job's call pair: its ends go with it, this side answers while waiting.  */
    close (req[1]);
    close (rep[0]);
    fcntl (req[0], F_SETFD, FD_CLOEXEC);
    fcntl (rep[1], F_SETFD, FD_CLOEXEC);
    amk_chan_close (&amk_chan[i]);
    amk_chan[i].req = req[0];
    amk_chan[i].rep = rep[1];
    if (foreground)
      amk_tty_give (pid);
    return pid;
  }
  setpgid (0, 0);
  close (p[0]);
  amk_mail_fd = p[1];
  {
    char fd[16];
    sprintf (fd, "%d", p[1]);
    define_variable_global ("AMK_MAIL", 8, fd, o_env, 0, NILF)->export = v_export;
  }
  /* A job holds no workspace: its parent's pairs go, and its own requests travel the new pair up.  */
  close (req[0]);
  close (rep[1]);
  for (i = 0; i <= AMK_SPAWNED; ++i)
    amk_chan_close (&amk_chan[i]);
  amk_ask_children_drop ();
  amk_up_req = req[1];
  amk_up_rep = rep[0];
  amk_ask_fd[0] = req[1];
  amk_ask_fd[1] = rep[0];
  amk_ask_export (req[1], rep[0]);
  if (foreground)
    amk_tty_give (getpid ());
  if (stdout_path != NULL && freopen (stdout_path, "w", stdout) == NULL)
    fprintf (stderr, "amk: spawn: cannot write %s: %s\n", stdout_path, strerror (errno));
  if (amk_spawn_mail_stdout)
    dup2 (amk_mail_fd, 1);
  signal (SIGINT, fatal_error_signal);
  signal (SIGTERM, fatal_error_signal);
  signal (SIGHUP, fatal_error_signal);
  signal (SIGQUIT, fatal_error_signal);
  amk_fork_settle ();
  return 0;
}

/* A job's kind, set as it is spawned and read by the record.  */
static void
amk_kind_set (pid_t pid, const char *kind) {
  unsigned int i;
  for (i = 0; i < AMK_SPAWNED; ++i)
    if (amk_kinds[i].pid == 0 || amk_kinds[i].pid == pid) {
      amk_kinds[i].pid = pid;
      amk_kinds[i].kind = kind;
      return;
    }
}

static const char *
amk_kind_of (pid_t pid, int forget) {
  unsigned int i;
  for (i = 0; i < AMK_SPAWNED; ++i)
    if (amk_kinds[i].pid == pid) {
      const char *k = amk_kinds[i].kind;
      if (forget)
        amk_kinds[i].pid = 0;
      return k;
    }
  return "goals";
}

pid_t
amk_spawn_goals (int n, char **words, int foreground, const char *stdout_path) {
  unsigned int i;
  pid_t pid = amk_fork_slot (&i, foreground, stdout_path);
  amk_spawn_mail_stdout = 0;
  if (pid != 0)
    return pid;
  die (amk_run_goals (n, words));
}

/* A fork of this image that evaluates text, when there is any, then runs the goals, when there are any, printing into its mail; the job is waited for here, and what it printed, less one trailing newline, is the value.  Answers 0 with the value, 1 when the job failed, -1 when there was no slot or no fork.  */
int
amk_spawn_capture (const char *text, int n, char **words, char **value) {
  unsigned int i;
  pid_t pid, got = 0;
  int code = 0, sig = 0, stopped = 0;
  size_t len = 0;
  *value = NULL;
  amk_spawn_mail_stdout = 1;
  pid = amk_fork_slot (&i, 0, NULL);
  amk_spawn_mail_stdout = 0;
  if (pid < 0)
    return -1;
  if (pid == 0) {
    if (text != NULL)
      gmk_eval (text, NULL);
    die (n > 0 ? amk_run_goals (n, words) : 0);
  }
  do
    amk_wait_child (pid, 1, &got, &code, &sig, &stopped);
  while (stopped);
  if (!amk_mail_take (pid, value, &len) || *value == NULL) {
    *value = xstrdup ("");
    len = 0;
  }
  if (code != 0 || sig != 0) {
    free (*value);
    *value = NULL;
    return 1;
  }
  if (len > 0 && (*value)[len - 1] == '\n' && --len > 0 && (*value)[len - 1] == '\r')
    --len;
  (*value)[len] = '\0';
  return 0;
}

/* The deferred calls in flight: the pid, the pipe its value arrives on and what has arrived, and the pipe its writes come back through with any record not yet whole.  */
static struct {
  pid_t pid;
  int fd, qfd;
  char *buf, *qbuf;
  size_t len, cap, qlen, qcap;
} amk_calls[AMK_SPAWNED];

static int
amk_call_slot (pid_t pid) {
  int k;
  for (k = 0; k < AMK_SPAWNED; ++k)
    if (pid > 0 && amk_calls[k].pid == pid)
      return k;
  return -1;
}

/* A call's value and writes read as far as they have come, or to their end when block is set, so a call is never stopped by a full pipe while it is waited on.  */
static void
amk_call_pump (int k, int block) {
  while (amk_calls[k].fd >= 0 || amk_calls[k].qfd >= 0) {
    struct pollfd fds[2];
    int nfds = 0, iout = -1, iq = -1;
    ssize_t r;
    if (amk_calls[k].fd >= 0) {
      iout = nfds++;
      fds[iout].fd = amk_calls[k].fd;
      fds[iout].events = POLLIN;
      fds[iout].revents = 0;
    }
    if (amk_calls[k].qfd >= 0) {
      iq = nfds++;
      fds[iq].fd = amk_calls[k].qfd;
      fds[iq].events = POLLIN;
      fds[iq].revents = 0;
    }
    r = poll (fds, nfds, block ? -1 : 0);
    if (r < 0 && errno == EINTR)
      continue;
    if (r <= 0)
      return;
    if (iq >= 0 && fds[iq].revents != 0)
      amk_queue_drain (&amk_calls[k].qfd, &amk_calls[k].qbuf, &amk_calls[k].qlen, &amk_calls[k].qcap);
    if (iout >= 0 && fds[iout].revents != 0) {
      if (amk_calls[k].len == amk_calls[k].cap) {
        amk_calls[k].cap += 4096;
        amk_calls[k].buf = xrealloc (amk_calls[k].buf, amk_calls[k].cap + 1);
      }
      r = read (amk_calls[k].fd, amk_calls[k].buf + amk_calls[k].len, amk_calls[k].cap - amk_calls[k].len);
      if (r < 0 && errno == EINTR)
        continue;
      if (r <= 0) {
        close (amk_calls[k].fd);
        amk_calls[k].fd = -1;
      } else
        amk_calls[k].len += r;
    }
  }
}

/* A call's whole value, read to its end and handed to the caller, its slot freed.  */
static char *
amk_call_take (int k, size_t *len) {
  char *buf;
  amk_call_pump (k, 1);
  buf = amk_calls[k].buf != NULL ? amk_calls[k].buf : xstrdup ("");
  buf[amk_calls[k].len] = '\0';
  *len = amk_calls[k].len;
  free (amk_calls[k].qbuf);
  memset (&amk_calls[k], 0, sizeof amk_calls[k]);
  amk_calls[k].fd = amk_calls[k].qfd = -1;
  return buf;
}

/* A forked call holds no socket, so a server's connection closes with its reply rather than when the call ends.  */
static void
amk_close_sockets (void) {
  int fd, top = (int) sysconf (_SC_OPEN_MAX);
  struct stat st;
  if (top < 0 || top > 4096) top = 4096;
  for (fd = 3; fd < top; ++fd)
    if (fstat (fd, &st) == 0 && S_ISSOCK (st.st_mode))
      close (fd);
}

/* The deferred call: amk_call run in a fork of this parsed image, its text or its error written to a pipe whose read end the caller gets to wait on; the child is a spawned job to the reaper, so make's own waiting cannot lose it.  */
pid_t
amk_call_begin (int kind, const char *name, unsigned int argc, const char **args, int *fd) {
  unsigned int i, k;
  int out[2], q[2];
  pid_t pid;
  const char *err = NULL, *text;
  char *s;
  for (k = 0; k < AMK_SPAWNED && amk_calls[k].pid != 0; ++k)
    ;
  if (k == AMK_SPAWNED || pipe (out) < 0)
    return -1;
  if (pipe (q) < 0) {
    close (out[0]);
    close (out[1]);
    return -1;
  }
  pid = amk_fork_slot (&i, 0, NULL);
  if (pid < 0) {
    close (out[0]);
    close (out[1]);
    close (q[0]);
    close (q[1]);
    return -1;
  }
  if (pid > 0) {
    close (out[1]);
    close (q[1]);
    memset (&amk_calls[k], 0, sizeof amk_calls[k]);
    amk_calls[k].pid = pid;
    amk_calls[k].fd = out[0];
    amk_calls[k].qfd = q[0];
    amk_kind_set (pid, "call");
    *fd = out[0];
    return pid;
  }
  close (out[0]);
  close (q[0]);
  amk_close_sockets ();
  amk_queue_fd = q[1];
  s = amk_call_kind (kind, name, argc, args, &err);
  text = s != NULL ? s : err != NULL ? err : "";
  amk_write_all (out[1], text, strlen (text));
  close (out[1]);
  die (s != NULL ? 0 : 1);
}

/* The call collected: its pipe read to the end, the child waited for, its writes applied; the text is the caller's to free, and a call that raised, died, or was never begun answers -1 with the reason in err.  */
int
amk_call_end (pid_t pid, char **text, const char **err) {
  static char why[256];
  int k = amk_call_slot (pid);
  char *buf;
  size_t len = 0;
  pid_t got = 0;
  int code = 0, sig = 0, stopped = 0;
  char *mail = NULL;
  size_t maillen = 0;
  if (k < 0) {
    *err = "no such call";
    return -1;
  }
  buf = amk_call_take (k, &len);
  do
    amk_wait_child (pid, 1, &got, &code, &sig, &stopped);
  while (stopped);
  if (amk_mail_take (pid, &mail, &maillen))
    free (mail);
  amk_kind_of (pid, 1);
  if (sig != 0 || code > 1) {
    snprintf (why, sizeof why, sig != 0 ? "the call died of signal %d" : "the call exited with status %d", sig != 0 ? sig : code);
    *err = why;
    free (buf);
    return -1;
  }
  if (code == 1) {
    snprintf (why, sizeof why, "%s", buf);
    *err = why;
    free (buf);
    return -1;
  }
  *text = buf;
  return 0;
}

/* What a fork of the parsed image drops before it runs anything: the served request's connection, which the request answers when its own goals end, the jobserver, leaving one slot, and every child and mailbox that belongs to the parent.  */
void
amk_fork_settle (void) {
  unsigned int i;
  if (amk_conn >= 0) {
    close (amk_conn);
    amk_conn = -1;
  }
  amk_child = 1;
  {
    struct variable *aspid = lookup_variable (STRING_SIZE_TUPLE ("AMK_REARM_PID"));
    if (aspid != 0 && aspid->value[0] != '\0')
      amk_rearm_pid (aspid->value);
  }
  job_slots = 1;
  jobserver_auth = NULL;
  jobserver_clear ();
  amk_pool_forget_held ();
  amk_forget_children ();
  memset (amk_live, 0, sizeof amk_live);
  memset (amk_parked, 0, sizeof amk_parked);
  memset (amk_kinds, 0, sizeof amk_kinds);
  for (i = 0; i < AMK_SPAWNED; ++i)
    amk_calls[i].pid = 0;
  for (i = 0; i < AMK_SPAWNED; ++i) {
    if (amk_mail[i] > 0)
      close (amk_mail[i]);
    amk_mail[i] = 0;
  }
}

/* A pid among the wanted ones; none wanted means any will do.  */
static int
amk_wanted (pid_t pid, const pid_t *wants, int n) {
  int k;
  if (n == 0)
    return 1;
  for (k = 0; k < n; ++k)
    if (wants[k] == pid)
      return 1;
  return 0;
}

/* A parked record first, then waitpid on each wanted live job in turn, so a job outside the set is never reaped; a stopped job is reported and stays live, and a finished terminal holder gives the terminal back.  */
static int
amk_wait_set (const pid_t *wants, int n, int block, pid_t *got, int *code, int *sig, int *stopped) {
  unsigned int i;
  for (;;) {
    for (i = 0; i < AMK_SPAWNED; ++i)
      if (amk_parked[i].pid != 0 && amk_wanted (amk_parked[i].pid, wants, n)) {
        *got = amk_parked[i].pid;
        *code = amk_parked[i].code;
        *sig = amk_parked[i].sig;
        *stopped = amk_parked[i].stopped;
        amk_parked[i].pid = 0;
        return 1;
      }
    for (i = 0; i < AMK_SPAWNED; ++i) {
      int status;
      pid_t pid;
      if (amk_live[i] == 0 || !amk_wanted (amk_live[i], wants, n))
        continue;
      amk_drain (i);
      if (amk_call_slot (amk_live[i]) >= 0)
        amk_call_pump (amk_call_slot (amk_live[i]), 0);
      pid = waitpid (amk_live[i], &status, WUNTRACED | WNOHANG);
      if (pid < 0 && errno == EINTR)
        continue;
      if (pid <= 0)
        continue;
      *got = pid;
      if (WIFSTOPPED (status)) {
        *stopped = 1;
        *code = 0;
        *sig = WSTOPSIG (status);
      } else {
        amk_mail_finish (i, pid);
        amk_live_drop (pid);
        *stopped = 0;
        *code = WIFEXITED (status) ? WEXITSTATUS (status) : 0;
        *sig = WIFSIGNALED (status) ? WTERMSIG (status) : 0;
      }
      if (pid == amk_tty_owner)
        amk_tty_take ();
      return 1;
    }
    if (!block)
      return 0;
    for (i = 0; i < AMK_SPAWNED && !(amk_live[i] != 0 && amk_wanted (amk_live[i], wants, n)); ++i)
      ;
    if (i == AMK_SPAWNED)
      return 0;
    amk_ask_wait (5);
  }
}

/* One wanted pid, or any job when want is 0.  */
int
amk_wait_child (pid_t want, int block, pid_t *got, int *code, int *sig, int *stopped) {
  return want > 0 ? amk_wait_set (&want, 1, block, got, code, sig, stopped)
                  : amk_wait_set (NULL, 0, block, got, code, sig, stopped);
}

int
amk_kill_child (pid_t pid, int sig) {
  return killpg (pid, sig);
}

/* A guest names the status this process leaves with; a loop run as a recipe
   carries its own code past make's exit 2 for a failed goal.  */
void
amk_exit_with (int status) {
  amk_exit_status = status;
}

static int
amk_live_has (pid_t pid) {
  unsigned int i;
  for (i = 0; i < AMK_SPAWNED; ++i)
    if (pid > 0 && amk_live[i] == pid)
      return 1;
  return 0;
}

int
amk_spawn_live (pid_t pid) {
  return amk_live_has (pid);
}

/* Stop and resume name their signals here, where the host's numbers are known, and refuse a pid that is not a live job of this process.  */
int
amk_stop_child (pid_t pid) {
  if (!amk_live_has (pid)) { errno = ESRCH; return -1; }
  return killpg (pid, SIGSTOP);
}

int
amk_resume_child (pid_t pid) {
  if (!amk_live_has (pid)) { errno = ESRCH; return -1; }
  return killpg (pid, SIGCONT);
}

/* The terminal to a job, and the job continued: what a shell's fg does.  */
int
amk_foreground (pid_t pid) {
  amk_tty_give (pid);
  return amk_live_has (pid) ? amk_resume_child (pid) : killpg (pid, SIGCONT);
}

/* Every live group hears the signal the parent is dying of.  */
void
amk_signal_spawned (int sig) {
  unsigned int i;
  for (i = 0; i < AMK_SPAWNED; ++i)
    if (amk_live[i] != 0)
      killpg (amk_live[i], sig);
}

/* Nothing outlives the run: every held request is answered never, every live group is terminated, then killed if it lingers, and the terminal comes back.  */
void
amk_sweep_spawned (void) {
  unsigned int i, tries;
  int any = 0;
  amk_held_end ();
  amk_pool_release_all ();
  for (i = 0; i < AMK_SPAWNED; ++i)
    if (amk_live[i] != 0) { killpg (amk_live[i], SIGTERM); any = 1; }
  if (!any)
    return;
  for (tries = 0; tries < 100; ++tries) {
    any = 0;
    for (i = 0; i < AMK_SPAWNED; ++i)
      if (amk_live[i] != 0 && waitpid (amk_live[i], NULL, WNOHANG) == amk_live[i])
        amk_live[i] = 0;
      else if (amk_live[i] != 0)
        any = 1;
    if (!any)
      break;
    usleep (10000);
  }
  for (i = 0; i < AMK_SPAWNED; ++i)
    if (amk_live[i] != 0) { killpg (amk_live[i], SIGKILL); waitpid (amk_live[i], NULL, 0); amk_live[i] = 0; }
  amk_tty_take ();
}

/* An argument read as a whole number, or a failure naming the function and the text; a guest catches it through amk.call.  */
static long
amk_job_number (const char *fn, const char *what, char *arg) {
  char *s = amk_trim (arg), *end;
  long n;
  char why[256];
  errno = 0;
  n = strtol (s, &end, 10);
  if (*s != '\0' && *end == '\0' && errno == 0)
    return n;
  snprintf (why, sizeof why, "$(%s ...): %s '%s' is not a number", fn, what, s);
  amk_fail (why);
  return -1;
}

static char *
amk_job_flag (int ok) {
  return xstrdup (ok ? "1" : "");
}

/* $(amk.spawn goals[, foreground=1][, stdout=path]): this parsed image forked to run the goal list as its own process group, answering the pid.
   $(amk.spawn.argv argv[, ...]): the same, with the list split as a shell would, like eng.argv, so a quoted NAME=value word keeps its spaces.  */
static char *
amk_func_spawn (void *state, const char *fn, unsigned int argc, char **argv) {
  char *words[64], *copy, *tok, *stdout_path = NULL, buf[32];
  const char *kind = "goals";
  int n = 0, foreground = 0;
  unsigned int i;
  pid_t pid;
  (void) state;
  copy = xstrdup (argc > 0 ? argv[0] : "");
  if (strcmp (fn, "amk.spawn.argv") == 0)
    n = amk_split_argv (copy, words, 64);
  else
    for (tok = strtok (copy, " \t\n"); tok != NULL; tok = strtok (NULL, " \t\n"))
      if (n < 64)
        words[n++] = tok;
      else
        ++n;
  if (n < 1 || n > 63) {
    char why[128];
    free (copy);
    snprintf (why, sizeof why, "$(%s ...): between 1 and 63 goals", fn);
    amk_fail (why);
    return xstrdup ("");
  }
  words[n] = NULL;
  for (i = 1; i < argc; ++i) {
    char *opt = amk_trim (argv[i]);
    if (*opt == '\0')
      continue;
    if (strncmp (opt, "foreground=", 11) == 0)
      foreground = opt[11] != '\0' && strcmp (opt + 11, "0") != 0;
    else if (strncmp (opt, "stdout=", 7) == 0)
      stdout_path = opt + 7;
    else if (strcmp (opt, "kind=goal") == 0 && n == 1)
      kind = "goal";
    else if (strcmp (opt, "kind=goals") == 0)
      kind = "goals";
    else {
      char why[256];
      free (copy);
      snprintf (why, sizeof why, "$(%s ...): no option '%s'; options are foreground=, stdout= and kind=goal for one goal", fn, opt);
      amk_fail (why);
      return xstrdup ("");
    }
  }
  pid = amk_spawn_goals (n, words, foreground, stdout_path);
  free (copy);
  if (pid < 0) {
    char why[128];
    snprintf (why, sizeof why, "$(%s ...): fork failed", fn);
    amk_fail (why);
    return xstrdup ("");
  }
  amk_kind_set (pid, kind);
  sprintf (buf, "%ld", (long) pid);
  return xstrdup (buf);
}

static void
amk_job_put (char **out, size_t *len, size_t *cap, const char *s, size_t n) {
  if (*len + n + 2 > *cap) {
    *cap = (*len + n + 2) * 2;
    *out = xrealloc (*out, *cap);
  }
  memcpy (*out + *len, s, n);
  *len += n;
  (*out)[*len] = '\0';
}

/* One json string onto a growing buffer, n bytes of s escaped as amk_json_string does.  */
static void
amk_job_json (char **out, size_t *len, size_t *cap, const char *s, size_t n) {
  size_t i;
  amk_job_put (out, len, cap, "\"", 1);
  for (i = 0; i < n; ++i) {
    char esc[8];
    if (s[i] == '"' || s[i] == '\\') {
      esc[0] = '\\';
      esc[1] = s[i];
      amk_job_put (out, len, cap, esc, 2);
    } else if ((unsigned char) s[i] < 0x20) {
      sprintf (esc, "\\u%04x", (unsigned char) s[i]);
      amk_job_put (out, len, cap, esc, 6);
    } else
      amk_job_put (out, len, cap, s + i, 1);
  }
  amk_job_put (out, len, cap, "\"", 1);
}

/* $(amk.wait [pids[, block]]): the next finished or stopped job of this process, or the first of the pids named, as a json object of pid, code, signal, status and mail; a job outside the named pids is never reaped. Empty when block is empty, 0 or false and none has finished; with block peek, the same without blocking, the record left for the next wait.  */
static char *
amk_func_wait (void *state, const char *fn, unsigned int argc, char **argv) {
  pid_t wants[AMK_SPAWNED], got = 0;
  int n = 0, block = 1, peek = 0, code = 0, sig = 0, stopped = 0;
  char *out, *mail = NULL, *copy, *tok, head[160];
  size_t len, cap, mlen = 0;
  (void) state;
  copy = xstrdup (argc > 0 ? argv[0] : "");
  for (tok = strtok (copy, " \t\n"); tok != NULL; tok = strtok (NULL, " \t\n")) {
    if (n == AMK_SPAWNED) {
      free (copy);
      amk_fail ("$(amk.wait ...): more pids than this process has jobs");
      return xstrdup ("");
    }
    wants[n++] = (pid_t) amk_job_number (fn, "pid", tok);
  }
  free (copy);
  if (argc > 1) {
    const char *b = amk_trim (argv[1]);
    peek = strcmp (b, "peek") == 0;
    block = !(peek || *b == '\0' || strcmp (b, "0") == 0 || strcmp (b, "false") == 0);
  }
  if (amk_wait_set (wants, n, block, &got, &code, &sig, &stopped) <= 0)
    return xstrdup ("");
  if (peek)
    amk_park (got, code, sig, stopped);
  snprintf (head, sizeof head, "{\"pid\": %ld, \"code\": %d, \"signal\": %d, \"status\": \"%s\", \"mail\": ",
            (long) got, code, sig,
            stopped ? "stopped" : sig ? "signal" : code == 0 ? "success" : code == 1 ? "question" : "failed");
  len = strlen (head);
  cap = len + 64;
  out = xmalloc (cap);
  memcpy (out, head, len + 1);
  if (peek) {
    const char *kept = NULL;
    if (!stopped && amk_mail_peek (got, &kept, &mlen) && kept != NULL)
      amk_job_json (&out, &len, &cap, kept, mlen);
    else
      amk_job_json (&out, &len, &cap, "", 0);
  } else if (!stopped && amk_mail_take (got, &mail, &mlen) && mail != NULL) {
    amk_job_json (&out, &len, &cap, mail, mlen);
    free (mail);
  } else
    amk_job_json (&out, &len, &cap, "", 0);
  amk_job_put (&out, &len, &cap, ", \"kind\": ", 10);
  {
    const char *kind = amk_kind_of (got, !peek && !stopped);
    amk_job_json (&out, &len, &cap, kind, strlen (kind));
  }
  if (amk_call_slot (got) >= 0)
    amk_job_put (&out, &len, &cap, ", \"value\": true", 15);
  amk_job_put (&out, &len, &cap, "}", 1);
  return out;
}

/* $(amk.job.value pid): a call's value, read to its end and taken once; empty for a pid with no value left.  The job itself is left for its wait.  */
static char *
amk_func_value (void *state, const char *fn, unsigned int argc, char **argv) {
  int k;
  size_t len;
  (void) state;
  if (argc < 1 || *amk_trim (argv[0]) == '\0') {
    amk_fail ("$(amk.job.value ...): no pid");
    return xstrdup ("");
  }
  k = amk_call_slot ((pid_t) amk_job_number (fn, "pid", argv[0]));
  return k < 0 ? xstrdup ("") : amk_call_take (k, &len);
}

/* $(amk.call.spawn name, args...): a call to the function, macro or engine name with its arguments, run in a job; answers the pid, the value read with amk.job.value.  */
static char *
amk_func_call_spawn (void *state, const char *fn, unsigned int argc, char **argv) {
  const char *args[64];
  unsigned int i;
  int fd;
  pid_t pid;
  char buf[32];
  (void) state;
  (void) fn;
  if (argc < 1 || *amk_trim (argv[0]) == '\0') {
    amk_fail ("$(amk.call.spawn ...): no name to call");
    return xstrdup ("");
  }
  for (i = 1; i < argc && i <= 64; ++i)
    args[i - 1] = argv[i];
  pid = amk_call_begin (AMK_AS_ANY, amk_trim (argv[0]), argc - 1, args, &fd);
  if (pid < 0) {
    amk_fail ("$(amk.call.spawn ...): no slot or no fork");
    return xstrdup ("");
  }
  sprintf (buf, "%ld", (long) pid);
  return xstrdup (buf);
}

/* $(amklang prog), $(amklang.exec prog) and $(amklang.argv argv, prog): make itself as a language engine, the program evaluated in a fork of the default workspace, then argv run as its command line, split as amk.spawn.argv splits it; the value is what the fork printed, and its writes never reach this make.  */
static char *
amk_func_amklang (void *state, const char *fn, unsigned int argc, char **argv) {
  char *words[64], *copy = NULL, *value;
  const char *prog = argc > 0 ? argv[0] : "";
  int n = 0, r;
  (void) state;
  if (strcmp (fn, "amklang.argv") == 0) {
    copy = xstrdup (argc > 0 ? argv[0] : "");
    prog = argc > 1 ? argv[1] : "";
    n = amk_split_argv (copy, words, 64);
    if (n > 63) {
      free (copy);
      amk_fail ("$(amklang.argv ...): between 0 and 63 words");
      return xstrdup ("");
    }
    words[n] = NULL;
  }
  r = amk_spawn_capture (prog, n, words, &value);
  free (copy);
  if (r != 0) {
    char why[128];
    snprintf (why, sizeof why, r < 0 ? "$(%s ...): no slot or no fork" : "$(%s ...): the program failed", fn);
    amk_fail (why);
    return xstrdup ("");
  }
  return value;
}

/* $(amk.kill pid[, sig]), $(amk.stop pid), $(amk.resume pid) and $(amk.foreground pid): the verb on a live job of this process, answering 1 when it went and empty for a pid that is not one.  */
static char *
amk_func_jobctl (void *state, const char *fn, unsigned int argc, char **argv) {
  const char *verb = fn + strlen ("amk.");
  pid_t pid;
  (void) state;
  if (argc < 1 || *amk_trim (argv[0]) == '\0') {
    char why[128];
    snprintf (why, sizeof why, "$(%s ...): no pid", fn);
    amk_fail (why);
    return xstrdup ("");
  }
  pid = (pid_t) amk_job_number (fn, "pid", argv[0]);
  if (!amk_live_has (pid))
    return xstrdup ("");
  if (strcmp (verb, "kill") == 0) {
    int sig = argc > 1 && *amk_trim (argv[1]) != '\0' ? (int) amk_job_number (fn, "signal", argv[1]) : SIGTERM;
    return amk_job_flag (amk_kill_child (pid, sig) == 0);
  }
  if (strcmp (verb, "stop") == 0)
    return amk_job_flag (amk_stop_child (pid) == 0);
  if (strcmp (verb, "resume") == 0)
    return amk_job_flag (amk_resume_child (pid) == 0);
  return amk_job_flag (amk_foreground (pid) == 0);
}

/* The job verbs as make functions, once, for makefiles and every guest alike.  */
void
amk_spawn_init (void) {
  amk_func_add ("amk.spawn", NULL, amk_func_spawn);
  amk_func_add ("amk.spawn.argv", NULL, amk_func_spawn);
  amk_func_add ("amk.wait", NULL, amk_func_wait);
  amk_func_add ("amk.job.value", NULL, amk_func_value);
  amk_func_add ("amk.call.spawn", NULL, amk_func_call_spawn);
  amk_func_add ("amklang", NULL, amk_func_amklang);
  amk_func_add ("amklang.exec", NULL, amk_func_amklang);
  amk_func_add ("amklang.argv", NULL, amk_func_amklang);
  amk_func_add ("amk.kill", NULL, amk_func_jobctl);
  amk_func_add ("amk.stop", NULL, amk_func_jobctl);
  amk_func_add ("amk.resume", NULL, amk_func_jobctl);
  amk_func_add ("amk.foreground", NULL, amk_func_jobctl);
}

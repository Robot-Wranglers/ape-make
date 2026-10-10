/* Spawned goal lists: the pids still out, and the ones make's own reaping collected before they were asked for.  */

#include "makeint.h"
#include "os.h"
#include "filedef.h"
#include "variable.h"
#include "job.h"
#include "commands.h"
#include <fcntl.h>
#include <sys/wait.h>
#include "amk.h"

static pid_t amk_live[AMK_SPAWNED];
static struct { pid_t pid; int code; int sig; } amk_parked[AMK_SPAWNED];
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

void
amk_reap_foreign (pid_t pid, int code, int sig) {
  unsigned int i;
  for (i = 0; i < AMK_SPAWNED && amk_live[i] != pid; ++i)
    ;
  if (i == AMK_SPAWNED)
    return;
  amk_mail_finish (i, pid);
  amk_live_drop (pid);
  for (i = 0; i < AMK_SPAWNED; ++i)
    if (amk_parked[i].pid == 0) {
      amk_parked[i].pid = pid;
      amk_parked[i].code = code;
      amk_parked[i].sig = sig;
      return;
    }
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
  amk_call_children_drop ();
  amk_up_req = req[1];
  amk_up_rep = rep[0];
  amk_call_fd[0] = req[1];
  amk_call_fd[1] = rep[0];
  amk_call_export (req[1], rep[0]);
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

pid_t
amk_spawn_goals (int n, char **words, int foreground, const char *stdout_path) {
  unsigned int i;
  pid_t pid = amk_fork_slot (&i, foreground, stdout_path);
  amk_spawn_mail_stdout = 0;
  if (pid != 0)
    return pid;
  die (amk_run_goals (n, words));
}

/* The next spawned job prints into its mail, so what it printed is taken with amk_mail_take once it is collected.  */
void
amk_spawn_stdout_to_mail (void) {
  amk_spawn_mail_stdout = 1;
}

/* The deferred calls in flight: the pid, the pipe its result arrives on, and the pipe its writes come back through.  */
static struct { pid_t pid; int fd; int qfd; } amk_calls[AMK_SPAWNED];

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
amk_call_begin (const char *name, unsigned int argc, const char **args, int *fd) {
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
    amk_calls[k].pid = pid;
    amk_calls[k].fd = out[0];
    amk_calls[k].qfd = q[0];
    *fd = out[0];
    return pid;
  }
  close (out[0]);
  close (q[0]);
  amk_close_sockets ();
  amk_queue_fd = q[1];
  s = amk_call (name, argc, args, &err);
  text = s != NULL ? s : err != NULL ? err : "";
  amk_write_all (out[1], text, strlen (text));
  close (out[1]);
  die (s != NULL ? 0 : 1);
}

/* The call collected: its pipe read to the end, the child waited for, its writes applied; the text is the caller's to free, and a call that raised, died, or was never begun answers -1 with the reason in err.  */
int
amk_call_end (pid_t pid, char **text, const char **err) {
  static char why[256];
  unsigned int k;
  char *buf;
  size_t len = 0;
  pid_t got = 0;
  int code = 0, sig = 0, stopped = 0;
  char *mail = NULL;
  size_t maillen = 0;
  for (k = 0; k < AMK_SPAWNED && amk_calls[k].pid != pid; ++k)
    ;
  if (k == AMK_SPAWNED) {
    *err = "no such call";
    return -1;
  }
  buf = amk_collect (&amk_calls[k].fd, &len, &amk_calls[k].qfd, NULL, NULL, 0);
  do
    amk_wait_child (pid, 1, &got, &code, &sig, &stopped);
  while (stopped);
  if (amk_mail_take (pid, &mail, &maillen))
    free (mail);
  amk_calls[k].pid = 0;
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
  amk_forget_children ();
  memset (amk_live, 0, sizeof amk_live);
  memset (amk_parked, 0, sizeof amk_parked);
  for (i = 0; i < AMK_SPAWNED; ++i) {
    if (amk_mail[i] > 0)
      close (amk_mail[i]);
    amk_mail[i] = 0;
  }
}

/* A parked child first, then waitpid on the wanted pid, or on each live one in turn when any will do; a stopped job is reported and stays live, and a finished terminal holder gives the terminal back.  */
int
amk_wait_child (pid_t want, int block, pid_t *got, int *code, int *sig, int *stopped) {
  unsigned int i;
  for (;;) {
    for (i = 0; i < AMK_SPAWNED; ++i)
      if (amk_parked[i].pid != 0 && (want <= 0 || amk_parked[i].pid == want)) {
        *got = amk_parked[i].pid;
        *code = amk_parked[i].code;
        *sig = amk_parked[i].sig;
        amk_parked[i].pid = 0;
        *stopped = 0;
        return 1;
      }
    for (i = 0; i < AMK_SPAWNED; ++i) {
      int status;
      pid_t pid;
      if (amk_live[i] == 0 || (want > 0 && amk_live[i] != want))
        continue;
      amk_drain (i);
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
    amk_call_wait (5);
  }
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

/* The terminal to a job, and the job continued: what a shell's fg does.  */
int
amk_foreground (pid_t pid) {
  amk_tty_give (pid);
  return killpg (pid, SIGCONT);
}

/* Every live group hears the signal the parent is dying of.  */
void
amk_signal_spawned (int sig) {
  unsigned int i;
  for (i = 0; i < AMK_SPAWNED; ++i)
    if (amk_live[i] != 0)
      killpg (amk_live[i], sig);
}

/* Nothing outlives the run: every live group is terminated, then killed if it lingers, and the terminal comes back.  */
void
amk_sweep_spawned (void) {
  unsigned int i, tries;
  int any = 0;
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

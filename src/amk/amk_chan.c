/* The call channel: a request pipe and a reply pipe, named to recipes as AMK_CALL and AMK_REPLY, one pair per recipe child and per spawned job, answered from a workspace while the process waits; a process that inherits a live pair holds no workspace and sends every request up it.  */

#include "makeint.h"
#include "filedef.h"
#include "variable.h"
#include "job.h"
#include <fcntl.h>
#include <sys/wait.h>
#include "amk.h"

#define AMK_OWN AMK_SPAWNED
struct amk_chan amk_chan[AMK_SPAWNED + 1];
int amk_up_req = -1, amk_up_rep = -1;
static int amk_chld[2] = { -1, -1 };
/* The descriptor numbers recipes read the pair at, and the pair waiting for the child about to spawn.  */
int amk_call_fd[2] = { -1, -1 };
static int amk_pend_req[2] = { -1, -1 }, amk_pend_rep[2] = { -1, -1 };

static void
amk_chld_handler (int sig) {
  child_handler (sig);
  if (amk_chld[1] >= 0 && write (amk_chld[1], "", 1) < 0)
    ;
}

static void
amk_chld_open (void) {
  int i;
  if (pipe (amk_chld) < 0) {
    amk_chld[0] = amk_chld[1] = -1;
    return;
  }
  for (i = 0; i < 2; ++i) {
    fcntl (amk_chld[i], F_SETFL, fcntl (amk_chld[i], F_GETFL) | O_NONBLOCK);
    fcntl (amk_chld[i], F_SETFD, FD_CLOEXEC);
  }
}

static void
amk_chld_drain (void) {
  char tmp[64];
  while (amk_chld[0] >= 0 && read (amk_chld[0], tmp, sizeof tmp) > 0)
    ;
}

void
amk_chan_close (struct amk_chan *c) {
  if (c->req > 0)
    close (c->req);
  if (c->rep > 0)
    close (c->rep);
  free (c->buf);
  memset (c, 0, sizeof *c);
}

void
amk_call_export (int req, int rep) {
  char fd[16];
  sprintf (fd, "%d", req);
  define_variable_global ("AMK_CALL", 8, fd, o_env, 0, NILF)->export = v_export;
  sprintf (fd, "%d", rep);
  define_variable_global ("AMK_REPLY", 9, fd, o_env, 0, NILF)->export = v_export;
}

static void
amk_pend_close (void) {
  int i;
  for (i = 0; i < 2; ++i) {
    if (amk_pend_req[i] >= 0)
      close (amk_pend_req[i]);
    if (amk_pend_rep[i] >= 0)
      close (amk_pend_rep[i]);
    amk_pend_req[i] = amk_pend_rep[i] = -1;
  }
}

/* The pair for the recipe child about to spawn, every end closed on exec since the child reads its two at the named numbers.  */
void
amk_call_child_pending (void) {
  int i;
  amk_pend_close ();
  if (amk_call_fd[0] < 0)
    return;
  if (pipe (amk_pend_req) < 0 || pipe (amk_pend_rep) < 0) {
    amk_pend_close ();
    return;
  }
  for (i = 0; i < 2; ++i) {
    fcntl (amk_pend_req[i], F_SETFD, FD_CLOEXEC);
    fcntl (amk_pend_rep[i], F_SETFD, FD_CLOEXEC);
  }
}

int
amk_call_child_fds (int *req, int *rep, int *req_at, int *rep_at) {
  if (amk_pend_req[1] < 0)
    return 0;
  *req = amk_pend_req[1];
  *rep = amk_pend_rep[0];
  *req_at = amk_call_fd[0];
  *rep_at = amk_call_fd[1];
  return 1;
}

/* After the spawn: the child's ends go, and this side rides on the child until it is freed.  */
void
amk_call_child_spawned (struct child *child) {
  if (amk_pend_req[0] < 0)
    return;
  if (child->pid > 0) {
    child->amk_chan = xcalloc (sizeof *child->amk_chan);
    child->amk_chan->req = amk_pend_req[0];
    child->amk_chan->rep = amk_pend_rep[1];
    amk_pend_req[0] = amk_pend_rep[1] = -1;
  }
  amk_pend_close ();
}

void
amk_call_child_drop (struct child *child) {
  if (child->amk_chan != NULL) {
    amk_chan_close (child->amk_chan);
    free (child->amk_chan);
    child->amk_chan = NULL;
  }
}

/* A fork that holds no workspace drops the pairs of the children it inherited on the chain.  */
void
amk_call_children_drop (void) {
  struct child *ch;
  for (ch = children; ch != NULL; ch = ch->next)
    amk_call_child_drop (ch);
}

/* A pair for this process's own recipes: the recipe ends inheritable and named, this side closed on exec.  */
static void
amk_call_own (void) {
  int req[2], rep[2];
  amk_chan_close (&amk_chan[AMK_OWN]);
  if (pipe (req) < 0)
    return;
  if (pipe (rep) < 0) {
    close (req[0]);
    close (req[1]);
    return;
  }
  fcntl (req[0], F_SETFD, FD_CLOEXEC);
  fcntl (rep[1], F_SETFD, FD_CLOEXEC);
  amk_chan[AMK_OWN].req = req[0];
  amk_chan[AMK_OWN].rep = rep[1];
  amk_call_fd[0] = req[1];
  amk_call_fd[1] = rep[0];
  amk_call_export (req[1], rep[0]);
}

/* The descriptor a name in the environment gives, when it is open and a pipe; else -1.  */
int
amk_fd_is_pipe (const char *spec) {
  struct stat st;
  char *end;
  long fd;
  if (spec == NULL || *spec == '\0')
    return -1;
  fd = strtol (spec, &end, 10);
  if (*end != '\0' || fd < 3 || fstat ((int) fd, &st) < 0 || !S_ISFIFO (st.st_mode))
    return -1;
  return (int) fd;
}

void
amk_call_init (void) {
  int up_req = amk_fd_is_pipe (getenv ("AMK_CALL"));
  int up_rep = amk_fd_is_pipe (getenv ("AMK_REPLY"));
  amk_chld_open ();
  bsd_signal (SIGCHLD, amk_chld_handler);
  if (up_req >= 0 && up_rep >= 0) {
    amk_up_req = up_req;
    amk_up_rep = up_rep;
    amk_call_fd[0] = up_req;
    amk_call_fd[1] = up_rep;
  } else
    amk_call_own ();
}

/* A served request forwards up the pair its request carried, named to its recipes at the numbers it arrived on; a request without one starts as an owner, since the zygote closed every inherited descriptor.  */
void
amk_call_dispatch (int req, int rep) {
  unsigned int i;
  amk_up_req = amk_up_rep = -1;
  for (i = 0; i <= AMK_SPAWNED; ++i) {
    free (amk_chan[i].buf);
    memset (&amk_chan[i], 0, sizeof amk_chan[i]);
  }
  amk_call_children_drop ();
  amk_chld[0] = amk_chld[1] = -1;
  amk_chld_open ();
  bsd_signal (SIGCHLD, amk_chld_handler);
  if (req >= 0 && rep >= 0) {
    amk_up_req = req;
    amk_up_rep = rep;
    amk_call_fd[0] = req;
    amk_call_fd[1] = rep;
    amk_call_export (req, rep);
  } else
    amk_call_own ();
}

int
amk_call_forwarding (void) {
  return amk_up_req >= 0;
}

struct amk_buf_sink { struct amk_sink base; char *buf; size_t len; };

static void
amk_buf_write (struct amk_sink *s, const char *p, size_t n) {
  struct amk_buf_sink *b = (struct amk_buf_sink *) s;
  b->buf = xrealloc (b->buf, b->len + n + 1);
  memcpy (b->buf + b->len, p, n);
  b->len += n;
  b->buf[b->len] = '\0';
}

/* One line off a descriptor other readers share, a byte at a time so nothing past the newline is taken; the newline stays on.  */
static char *
amk_read_line_shared (int fd) {
  size_t len = 0, cap = 256;
  char *line = xmalloc (cap);
  for (;;) {
    ssize_t r = read (fd, line + len, 1);
    if (r < 0 && errno == EINTR)
      continue;
    if (r <= 0) {
      free (line);
      return NULL;
    }
    if (line[len++] == '\n')
      break;
    if (len + 1 == cap)
      line = xrealloc (line, cap *= 2);
  }
  line[len] = '\0';
  return line;
}

/* A filter request's header names its engine, then how many input lines follow it; the old form without the engine is counted too, so the stream stays in step until it is refused. -1 for any other request.  */
static int
amk_call_input_lines (const char *line) {
  const char *p;
  char *end;
  long n;
  if (strncmp (line, "filter ", 7) != 0)
    return -1;
  p = line + 7;
  n = strtol (p, &end, 10);
  if (end == p || (*end != ' ' && *end != '\0')) {
    p += strcspn (p, " ");
    while (*p == ' ')
      ++p;
    n = strtol (p, &end, 10);
  }
  if (end == p || (*end != ' ' && *end != '\0') || n < 0)
    return -1;
  return (int) n;
}

/* The head of a reply: its status and line count; the body starts after the newline.  */
static int
amk_reply_head (const char *reply, int *n, const char **body) {
  char *end;
  int rc = (int) strtol (reply, &end, 10);
  *n = (int) strtol (end, &end, 10);
  *body = strchr (reply, '\n');
  *body = *body != NULL ? *body + 1 : reply + strlen (reply);
  return rc;
}

/* The next word of a request line into word, p moved past it; 0 at the end.  */
static int
amk_call_word (const char **p, char *word, size_t size) {
  const char *s = *p;
  size_t n = 0;
  while (*s == ' ' || *s == '\t')
    ++s;
  if (*s == '\0') {
    *p = s;
    return 0;
  }
  while (*s != '\0' && *s != ' ' && *s != '\t') {
    if (n + 1 < size)
      word[n++] = *s;
    ++s;
  }
  word[n] = '\0';
  *p = s;
  return 1;
}

/* The whole of a file as text, or null with the reason on stderr.  */
static char *
amk_call_slurp (const char *op, const char *name, const char *path) {
  FILE *f = fopen (path, "r");
  char *text;
  size_t len = 0, cap = 4096;
  if (f == NULL) {
    fprintf (stderr, "amk: call: %s %s: cannot read %s\n", op, name, path);
    return NULL;
  }
  text = xmalloc (cap + 1);
  for (;;) {
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

/* One request line to a workspace: the operation, the name, and the rest as the program. A dump prints the whole state, a load names a file read here, and a filter names its engine and the input lines the transport counted.  */
static int
amk_call_serve (struct amk_sink *out, const char *line, const char *input) {
  char op[32], name[1024], count[32];
  const char *p = line;
  char *text;
  int rc;

  if (!amk_call_word (&p, op, sizeof op)) {
    fprintf (stderr, "amk: call: expected an operation, got: %s\n", line);
    return 2;
  }
  if (strcmp (op, "filter") == 0) {
    if (!amk_call_word (&p, name, sizeof name) || strspn (name, "0123456789") == strlen (name)
        || !amk_call_word (&p, count, sizeof count)) {
      fprintf (stderr, "amk: call: filter names its engine first: filter ENGINE LINES PROGRAM\n");
      return 2;
    }
    while (*p == ' ' || *p == '\t')
      ++p;
    return amk_workspace_filter (out, name, p, input);
  }
  if (!amk_call_word (&p, name, sizeof name)) {
    fprintf (stderr, "amk: call: %s: expected a name, got: %s\n", op, line);
    return 2;
  }
  while (*p == ' ' || *p == '\t')
    ++p;
  if (strcmp (op, "create") == 0)
    return amk_workspace_backing (name, p);
  if (strcmp (op, "dump") == 0)
    return amk_workspace_call (out, "dump", name, "");
  if (strcmp (op, "load") == 0) {
    char path[4096];
    if (!amk_call_word (&p, path, sizeof path)) {
      fprintf (stderr, "amk: call: load %s: no path\n", name);
      return 2;
    }
    text = amk_call_slurp (op, name, path);
    if (text == NULL)
      return 2;
    rc = amk_workspace_call (out, "load", name, text);
    free (text);
    return rc;
  }
  return amk_workspace_call (out, op, name, p);
}

/* The reply to one request: the workspace's status and how many lines follow, then each output on a line of its own, verbatim.  A build without a workspace row answers 2.  */
static char *
amk_call_answer (const char *line, const char *input) {
  struct amk_buf_sink sink = { { amk_buf_write }, NULL, 0 };
  char *reply;
  const char *p;
  int rc, n = 0;

  rc = amk_call_serve (&sink.base, line, input);

  for (p = sink.buf; p != NULL && *p != '\0'; ++n) {
    const char *nl = strchr (p, '\n');
    p = nl != NULL ? nl + 1 : p + strlen (p);
  }
  reply = xmalloc (sink.len + 32);
  sprintf (reply, "%d %d\n", rc, n);
  if (sink.buf != NULL) {
    strcat (reply, sink.buf);
    if (sink.len > 0 && sink.buf[sink.len - 1] != '\n')
      strcat (reply, "\n");
  }
  free (sink.buf);
  return reply;
}

/* A request sent up the inherited pair, input lines after it, and the whole reply that comes back; nothing when the owner is gone.  */
static char *
amk_call_up (const char *line, const char *input) {
  size_t n = strlen (line), m = input != NULL ? strlen (input) : 0;
  char *req = xmalloc (n + m + 2), *reply, *more;
  const char *body;
  int lines;
  memcpy (req, line, n);
  req[n] = '\n';
  if (m > 0)
    memcpy (req + n + 1, input, m);
  {
    /* An owner that went away is an error line and a status, not a signal.  */
    void (*prev) (int) = signal (SIGPIPE, SIG_IGN);
    int wrote = amk_write_all (amk_up_req, req, n + 1 + m);
    signal (SIGPIPE, prev);
    free (req);
    if (wrote < 0)
      return NULL;
  }
  reply = amk_read_line_shared (amk_up_rep);
  if (reply == NULL)
    return NULL;
  amk_reply_head (reply, &lines, &body);
  while (lines-- > 0) {
    more = amk_read_line_shared (amk_up_rep);
    if (more == NULL) {
      free (reply);
      return NULL;
    }
    reply = xrealloc (reply, strlen (reply) + strlen (more) + 1);
    strcat (reply, more);
    free (more);
  }
  return reply;
}

static char *
amk_call_handle (const char *line, const char *input) {
  char *reply;
  /* Halt names this process, not the workspace's owner, so it is answered before any forwarding.  */
  if (strcmp (line, "halt") == 0) {
    amk_halt = 1;
    return xstrdup ("0 0\n");
  }
  reply = amk_up_req >= 0 ? amk_call_up (line, input) : amk_call_answer (line, input);
  if (reply == NULL) {
    fprintf (stderr, "amk: call: no reply from the workspaces' owner\n");
    reply = xstrdup ("2 0\n");
  }
  return reply;
}

/* A forwarder's own persistent call: the reply's lines into the sink as they are; the status is the workspace's.  */
int
amk_call_forward (const char *line, struct amk_sink *out) {
  char *reply = amk_call_handle (line, NULL);
  const char *body;
  int n, rc = amk_reply_head (reply, &n, &body);
  out->write (out, body, strlen (body));
  free (reply);
  return rc;
}

/* Whatever a channel holds: each complete request, its input lines included, is answered on its reply end or into its tag's FIFO; a partial request waits for the rest.  */
static void
amk_chan_serve (struct amk_chan *c) {
  char tmp[4096];
  ssize_t r;
  do r = read (c->req, tmp, sizeof tmp); while (r < 0 && errno == EINTR);
  if (r <= 0) {
    if (r == 0) {
      close (c->req);
      c->req = 0;
    }
    return;
  }
  c->buf = xrealloc (c->buf, c->len + r + 1);
  memcpy (c->buf + c->len, tmp, r);
  c->len += r;
  c->buf[c->len] = '\0';
  for (;;) {
    char *nl = memchr (c->buf, '\n', c->len), *line, *input = NULL, *reply, *end;
    size_t used;
    int lines;
    if (nl == NULL)
      return;
    /* Nothing in the buffer changes until the whole request is here, since a partial one is read again.  */
    line = c->buf;
    *nl = '\0';
    lines = amk_call_input_lines (line);
    *nl = '\n';
    end = nl + 1;
    if (lines > 0) {
      int k;
      for (k = 0; k < lines; ++k) {
        char *next = memchr (end, '\n', c->len - (end - c->buf));
        if (next == NULL)
          return;
        end = next + 1;
      }
      input = xmalloc (end - (nl + 1) + 1);
      memcpy (input, nl + 1, end - (nl + 1));
      input[end - (nl + 1)] = '\0';
    } else if (lines == 0)
      input = xstrdup ("");
    *nl = '\0';
    reply = amk_call_handle (line, input);
    {
      void (*prev) (int) = signal (SIGPIPE, SIG_IGN);
      amk_write_all (c->rep, reply, strlen (reply));
      signal (SIGPIPE, prev);
    }
    free (reply);
    free (input);
    used = end - c->buf;
    memmove (c->buf, end, c->len - used);
    c->len -= used;
    c->buf[c->len] = '\0';
  }
}

/* Wait for a dead child or a request, whichever comes first, at most ms milliseconds when ms is not negative, and answer every request that is ready.  */
int
amk_call_fdset (fd_set *rd) {
  unsigned int i;
  struct child *ch;
  int top = -1;
  if (amk_chld[0] >= 0 && amk_chld[0] < FD_SETSIZE) {
    FD_SET (amk_chld[0], rd);
    top = amk_chld[0];
  }
  for (i = 0; i <= AMK_SPAWNED; ++i)
    if (amk_chan[i].req > 0 && amk_chan[i].req < FD_SETSIZE) {
      FD_SET (amk_chan[i].req, rd);
      if (amk_chan[i].req > top)
        top = amk_chan[i].req;
    }
  for (ch = children; ch != NULL; ch = ch->next)
    if (ch->amk_chan != NULL && ch->amk_chan->req > 0 && ch->amk_chan->req < FD_SETSIZE) {
      FD_SET (ch->amk_chan->req, rd);
      if (ch->amk_chan->req > top)
        top = ch->amk_chan->req;
    }
  return top;
}

void
amk_call_ready (fd_set *rd) {
  unsigned int i;
  struct child *ch;
  if (amk_chld[0] >= 0 && FD_ISSET (amk_chld[0], rd))
    amk_chld_drain ();
  for (i = 0; i <= AMK_SPAWNED; ++i)
    if (amk_chan[i].req > 0 && FD_ISSET (amk_chan[i].req, rd))
      amk_chan_serve (&amk_chan[i]);
  for (ch = children; ch != NULL; ch = ch->next)
    if (ch->amk_chan != NULL && ch->amk_chan->req > 0 && FD_ISSET (ch->amk_chan->req, rd))
      amk_chan_serve (ch->amk_chan);
}

void
amk_call_wait (int ms) {
  fd_set rd;
  struct timespec ts, *tsp = NULL;
  sigset_t empty;
  int top;

  FD_ZERO (&rd);
  top = amk_call_fdset (&rd);
  if (ms >= 0) {
    ts.tv_sec = ms / 1000;
    ts.tv_nsec = (ms % 1000) * 1000000L;
    tsp = &ts;
  }
  if (top < 0) {
    if (tsp != NULL)
      nanosleep (tsp, NULL);
    return;
  }
  sigemptyset (&empty);
  if (pselect (top + 1, &rd, NULL, NULL, tsp, &empty) <= 0)
    return;
  amk_call_ready (&rd);
}

/* The blocking wait for any child, answering requests as they come.  The child pipe is drained before the check, so a death between the check and the wait leaves a byte that ends the wait at once.  */
pid_t
amk_wait_any (int *status) {
  for (;;) {
    pid_t pid;
    amk_chld_drain ();
    pid = waitpid (-1, status, WNOHANG);
    if (pid > 0 || (pid < 0 && errno != EINTR))
      return pid;
    amk_call_wait (amk_chld[0] >= 0 ? -1 : 50);
  }
}

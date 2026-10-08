/* The ask channel: a request pipe and a reply pipe, named to recipes as AMK_ASK and AMK_REPLY, one pair per recipe child and per spawned job, answered from a workspace while the process waits; a process that inherits a live pair holds no workspace and sends every request up it.  */

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
int amk_ask_fd[2] = { -1, -1 };
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

/* The version of each namespace asked about so far, and the wait requests held until theirs moves, each with the channel its reply goes to.  */
struct amk_version { char *ns; unsigned long v; };
static struct amk_version *amk_versions;
static unsigned int amk_versions_len;
struct amk_held { struct amk_chan *c; char *line; char *tag; };
static struct amk_held *amk_held;
static unsigned int amk_held_len;
int amk_ask_hold;

/* A forwarder's requests sent up and not yet answered: each child request goes up under a number of this process's own and is answered to its channel when the reply with that number comes back, so a held reply blocks no one else; a child's own number, when it is a forwarder too, rides along and goes back on its reply.  A guest's own ask has no channel: its reply is kept on the row until the guest polls for it.  */
struct amk_up_sent { unsigned long id; struct amk_chan *c; char *tag; char *reply; };
static struct amk_up_sent *amk_up_sent;
static unsigned int amk_up_sent_len;
static unsigned long amk_up_next = 1;

/* A request line's leading tag, a number after a hash, split off; the rest of the line is answered.  */
static const char *
amk_ask_untag (const char *line, char **tag) {
  const char *p = line;
  *tag = NULL;
  if (*p != '#')
    return line;
  while (*p != ' ' && *p != '\0')
    ++p;
  *tag = xstrndup (line, p - line);
  while (*p == ' ')
    ++p;
  return p;
}

/* The head of a reply with the tag it carries, if any; the body starts after the newline.  */
static int
amk_reply_parse (const char *reply, int *n, char **tag, const char **body) {
  char *end;
  int rc = (int) strtol (reply, &end, 10);
  *n = (int) strtol (end, &end, 10);
  while (*end == ' ')
    ++end;
  *tag = *end == '#' ? xstrndup (end, strcspn (end, " \n")) : NULL;
  *body = strchr (reply, '\n');
  *body = *body != NULL ? *body + 1 : reply + strlen (reply);
  return rc;
}

/* The same reply under another tag, or under none.  */
static char *
amk_reply_retag (const char *reply, const char *tag) {
  const char *body;
  char *old, *out;
  int n, rc = amk_reply_parse (reply, &n, &old, &body);
  free (old);
  out = xmalloc (strlen (body) + (tag != NULL ? strlen (tag) : 0) + 32);
  sprintf (out, "%d %d%s%s\n%s", rc, n, tag != NULL ? " " : "", tag != NULL ? tag : "", body);
  return out;
}

static struct amk_version *
amk_version_row (const char *ns) {
  unsigned int i;
  for (i = 0; i < amk_versions_len; ++i)
    if (strcmp (amk_versions[i].ns, ns) == 0)
      return &amk_versions[i];
  amk_versions = xrealloc (amk_versions, (amk_versions_len + 1) * sizeof *amk_versions);
  amk_versions[amk_versions_len].ns = xstrdup (ns);
  amk_versions[amk_versions_len].v = 0;
  return &amk_versions[amk_versions_len++];
}

unsigned long
amk_ns_version (const char *ns) {
  return amk_version_row (ns)->v;
}

void
amk_ns_version_write (struct amk_sink *out, const char *ns) {
  char text[32];
  sprintf (text, "%lu\n", amk_ns_version (ns));
  out->write (out, text, strlen (text));
}

/* The ops the channel answers itself on any workspace namespace, beside the engine's own.  */
int
amk_ns_channel_op (const char *op) {
  return strcmp (op, "version") == 0 || strcmp (op, "wait") == 0;
}

static void
amk_chan_reply (struct amk_chan *c, const char *reply) {
  amk_write_quiet (c->rep, reply, strlen (reply));
}

static void
amk_held_add (struct amk_chan *c, const char *line, char *tag) {
  amk_held = xrealloc (amk_held, (amk_held_len + 1) * sizeof *amk_held);
  amk_held[amk_held_len].c = c;
  amk_held[amk_held_len].line = xstrdup (line);
  amk_held[amk_held_len].tag = tag;
  ++amk_held_len;
}

static void
amk_held_take (unsigned int i) {
  free (amk_held[i].line);
  free (amk_held[i].tag);
  memmove (amk_held + i, amk_held + i + 1, (amk_held_len - i - 1) * sizeof *amk_held);
  --amk_held_len;
}

static void
amk_up_sent_take (unsigned int i) {
  free (amk_up_sent[i].tag);
  free (amk_up_sent[i].reply);
  memmove (amk_up_sent + i, amk_up_sent + i + 1, (amk_up_sent_len - i - 1) * sizeof *amk_up_sent);
  --amk_up_sent_len;
}

/* A channel that closed takes its held requests and the ones it sent up with it; a reply that comes back for one later has no one to go to.  */
static void
amk_held_drop (struct amk_chan *c) {
  unsigned int i = 0;
  while (i < amk_held_len)
    if (amk_held[i].c == c)
      amk_held_take (i);
    else
      ++i;
  i = 0;
  while (i < amk_up_sent_len)
    if (amk_up_sent[i].c == c)
      amk_up_sent_take (i);
    else
      ++i;
}

static char *amk_ask_handle (const char *line, const char *input);
static char *amk_read_line_shared (int fd);
static int amk_reply_head (const char *reply, int *n, const char **body);

/* A held request's reply, tagged as its request was.  */
static void
amk_held_reply (unsigned int i, const char *reply) {
  char *tagged = amk_reply_retag (reply, amk_held[i].tag);
  amk_chan_reply (amk_held[i].c, tagged);
  free (tagged);
}

/* Each held request asked again in arrival order, and answered where it no longer parks; the hold flag of the request being served around this is kept.  */
static void
amk_held_retry (void) {
  int outer = amk_ask_hold;
  unsigned int i = 0;
  while (i < amk_held_len) {
    char *reply;
    amk_ask_hold = 0;
    reply = amk_ask_handle (amk_held[i].line, NULL);
    if (amk_ask_hold) {
      ++i;
      continue;
    }
    amk_held_reply (i, reply);
    free (reply);
    amk_held_take (i);
  }
  amk_ask_hold = outer;
}

/* A namespace changed: its version moves, and whatever is held gets its retry.  */
void
amk_ns_version_bump (const char *ns) {
  amk_version_row (ns)->v++;
  amk_held_retry ();
}

/* At exit, every held request is answered never.  */
void
amk_held_end (void) {
  char reply[16];
  sprintf (reply, "%d 0\n", AMK_NEVER);
  while (amk_held_len > 0) {
    amk_held_reply (0, reply);
    amk_held_take (0);
  }
}

/* One whole reply off the up pipe, head and lines; null when the owner is gone.  */
static char *
amk_up_read (void) {
  char *reply = amk_read_line_shared (amk_up_rep), *more, *tag;
  const char *body;
  int lines;
  if (reply == NULL)
    return NULL;
  amk_reply_parse (reply, &lines, &tag, &body);
  free (tag);
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

/* A reply from up routed to the child whose request it answers, under that child's own tag; one that is nobody's, or is this process's own, is handed back.  */
static char *
amk_up_route (char *reply, unsigned long mine) {
  const char *body;
  char *tag, *end;
  unsigned long id;
  unsigned int i;
  int n;
  amk_reply_parse (reply, &n, &tag, &body);
  if (tag == NULL)
    return reply;
  id = strtoul (tag + 1, &end, 10);
  free (tag);
  if (id == mine)
    return reply;
  for (i = 0; i < amk_up_sent_len; ++i)
    if (amk_up_sent[i].id == id) {
      char *down = amk_reply_retag (reply, amk_up_sent[i].tag);
      if (amk_up_sent[i].c == NULL) {
        free (amk_up_sent[i].reply);
        amk_up_sent[i].reply = down;
      } else {
        amk_chan_reply (amk_up_sent[i].c, down);
        free (down);
        amk_up_sent_take (i);
      }
      break;
    }
  free (reply);
  return NULL;
}

/* A reply the owner sent on its own time, for a request this forwarder relayed; an owner that is gone answers every ask still waiting with a status.  */
static void
amk_up_ready (void) {
  char *reply = amk_up_read ();
  unsigned int i;
  if (reply != NULL) {
    if (amk_up_route (reply, 0) != NULL)
      free (reply);
    return;
  }
  for (i = 0; i < amk_up_sent_len; ++i)
    if (amk_up_sent[i].c == NULL && amk_up_sent[i].reply == NULL)
      amk_up_sent[i].reply = xstrdup ("2 0\n");
}

/* A guest's own request under a fresh number: sent up when this process forwards, with the reply kept on its row once it comes, so the guest goes on meanwhile; answered in place in the owner, where a request that parks has no one to wait for it.  Answers the number, or -1 when it parked in the owner.  */
long
amk_ask_begin (const char *line) {
  unsigned long id = amk_up_next++;
  char *reply = NULL, *req;
  if (amk_up_req < 0 || strcmp (line, "halt") == 0) {
    amk_ask_hold = 0;
    reply = amk_ask_handle (line, NULL);
    if (amk_ask_hold) {
      amk_ask_hold = 0;
      return -1;
    }
  } else {
    req = xmalloc (strlen (line) + 32);
    sprintf (req, "#%lu %s\n", id, line);
    if (amk_write_quiet (amk_up_req, req, strlen (req)) < 0) {
      fprintf (stderr, "amk: ask: no reply from the workspaces' owner\n");
      reply = xstrdup ("2 0\n");
    }
    free (req);
  }
  amk_up_sent = xrealloc (amk_up_sent, (amk_up_sent_len + 1) * sizeof *amk_up_sent);
  amk_up_sent[amk_up_sent_len].id = id;
  amk_up_sent[amk_up_sent_len].c = NULL;
  amk_up_sent[amk_up_sent_len].tag = NULL;
  amk_up_sent[amk_up_sent_len].reply = reply;
  ++amk_up_sent_len;
  return (long) id;
}

/* The reply to a begun ask, waited for; replies to others are routed meanwhile.  */
char *
amk_ask_collect (unsigned long id) {
  for (;;) {
    char *reply = amk_ask_poll (id);
    if (reply != NULL)
      return reply;
    amk_ask_wait (-1);
  }
}

/* A reply's body as the ask's text, one trailing newline dropped as a call's text has it, the caller's to free; or -1 with the reason in err: an owner that exited, or the status with whatever it printed.  The reply is consumed.  */
int
amk_ask_result (char *reply, char **text, const char **err) {
  static char why[4096];
  const char *body;
  int n, rc = amk_reply_head (reply, &n, &body);
  if (rc == 0) {
    size_t len = strlen (body);
    if (len > 0 && body[len - 1] == '\n')
      --len;
    *text = xstrndup (body, len);
    free (reply);
    return 0;
  }
  if (rc == AMK_NEVER)
    strcpy (why, "the owner exited");
  else {
    size_t len = strcspn (body, "\n");
    if (len > 0)
      snprintf (why, sizeof why, "%.*s", (int) len, body);
    else
      snprintf (why, sizeof why, "status %d", rc);
  }
  free (reply);
  *err = why;
  return -1;
}

/* The reply to a begun ask once it is here, the caller's to free; null while it is still out.  */
char *
amk_ask_poll (unsigned long id) {
  unsigned int i;
  for (i = 0; i < amk_up_sent_len; ++i)
    if (amk_up_sent[i].c == NULL && amk_up_sent[i].id == id && amk_up_sent[i].reply != NULL) {
      char *reply = amk_up_sent[i].reply;
      amk_up_sent[i].reply = NULL;
      amk_up_sent_take (i);
      return reply;
    }
  return NULL;
}

/* A child's request sent up under a fresh number and remembered; the child blocks on its reply, this process does not.  */
static void
amk_up_relay (struct amk_chan *c, const char *line, const char *input) {
  char *tag, *req;
  const char *rest = amk_ask_untag (line, &tag);
  size_t n, m = input != NULL ? strlen (input) : 0;
  unsigned long id = amk_up_next++;
  int wrote;
  req = xmalloc (strlen (rest) + m + 32);
  sprintf (req, "#%lu %s\n", id, rest);
  n = strlen (req);
  if (m > 0)
    memcpy (req + n, input, m);
  wrote = amk_write_quiet (amk_up_req, req, n + m);
  free (req);
  if (wrote < 0) {
    char *down = amk_reply_retag ("2 0\n", tag);
    fprintf (stderr, "amk: ask: no reply from the workspaces' owner\n");
    amk_chan_reply (c, down);
    free (down);
    free (tag);
    return;
  }
  amk_up_sent = xrealloc (amk_up_sent, (amk_up_sent_len + 1) * sizeof *amk_up_sent);
  amk_up_sent[amk_up_sent_len].id = id;
  amk_up_sent[amk_up_sent_len].c = c;
  amk_up_sent[amk_up_sent_len].tag = tag;
  amk_up_sent[amk_up_sent_len].reply = NULL;
  ++amk_up_sent_len;
}

void
amk_chan_close (struct amk_chan *c) {
  amk_held_drop (c);
  if (c->req > 0)
    close (c->req);
  if (c->rep > 0)
    close (c->rep);
  free (c->buf);
  memset (c, 0, sizeof *c);
}

void
amk_ask_export (int req, int rep) {
  char fd[16];
  sprintf (fd, "%d", req);
  define_variable_global ("AMK_ASK", 7, fd, o_env, 0, NILF)->export = v_export;
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
amk_ask_child_pending (void) {
  int i;
  amk_pend_close ();
  if (amk_ask_fd[0] < 0)
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
amk_ask_child_fds (int *req, int *rep, int *req_at, int *rep_at) {
  if (amk_pend_req[1] < 0)
    return 0;
  *req = amk_pend_req[1];
  *rep = amk_pend_rep[0];
  *req_at = amk_ask_fd[0];
  *rep_at = amk_ask_fd[1];
  return 1;
}

/* After the spawn: the child's ends go, and this side rides on the child until it is freed.  */
void
amk_ask_child_spawned (struct child *child) {
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
amk_ask_child_drop (struct child *child) {
  if (child->amk_chan != NULL) {
    amk_chan_close (child->amk_chan);
    free (child->amk_chan);
    child->amk_chan = NULL;
  }
}

/* A fork that holds no workspace drops the pairs of the children it inherited on the chain.  */
void
amk_ask_children_drop (void) {
  struct child *ch;
  for (ch = children; ch != NULL; ch = ch->next)
    amk_ask_child_drop (ch);
}

/* A pair for this process's own recipes: the recipe ends inheritable and named, this side closed on exec.  */
static void
amk_ask_own (void) {
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
  amk_ask_fd[0] = req[1];
  amk_ask_fd[1] = rep[0];
  amk_ask_export (req[1], rep[0]);
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
amk_ask_init (void) {
  int up_req = amk_fd_is_pipe (getenv ("AMK_ASK"));
  int up_rep = amk_fd_is_pipe (getenv ("AMK_REPLY"));
  amk_chld_open ();
  bsd_signal (SIGCHLD, amk_chld_handler);
  if (up_req >= 0 && up_rep >= 0) {
    amk_up_req = up_req;
    amk_up_rep = up_rep;
    amk_ask_fd[0] = up_req;
    amk_ask_fd[1] = up_rep;
  } else
    amk_ask_own ();
}

/* A served request forwards up the pair its request carried, named to its recipes at the numbers it arrived on; a request without one starts as an owner, since the zygote closed every inherited descriptor.  */
void
amk_ask_dispatch (int req, int rep) {
  unsigned int i;
  amk_up_req = amk_up_rep = -1;
  for (i = 0; i <= AMK_SPAWNED; ++i) {
    free (amk_chan[i].buf);
    memset (&amk_chan[i], 0, sizeof amk_chan[i]);
  }
  amk_ask_children_drop ();
  amk_chld[0] = amk_chld[1] = -1;
  amk_chld_open ();
  bsd_signal (SIGCHLD, amk_chld_handler);
  if (req >= 0 && rep >= 0) {
    amk_up_req = req;
    amk_up_rep = rep;
    amk_ask_fd[0] = req;
    amk_ask_fd[1] = rep;
    amk_ask_export (req, rep);
  } else
    amk_ask_own ();
}

int
amk_ask_forwarding (void) {
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
amk_ask_input_lines (const char *line) {
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

/* The head of a reply: its status and line count, any tag dropped; the body starts after the newline.  */
static int
amk_reply_head (const char *reply, int *n, const char **body) {
  char *tag;
  int rc = amk_reply_parse (reply, n, &tag, body);
  free (tag);
  return rc;
}

/* The next word of a request line into word, p moved past it; 0 at the end.  */
static int
amk_ask_word (const char **p, char *word, size_t size) {
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
amk_ask_slurp (const char *op, const char *name, const char *path) {
  FILE *f = fopen (path, "r");
  char *text;
  size_t len = 0, cap = 4096;
  if (f == NULL) {
    fprintf (stderr, "amk: ask: %s %s: cannot read %s\n", op, name, path);
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

/* One request line to the owner: the operation, the namespace, and the rest as the program. A dump prints the whole state, a load names a file read here, and a filter names its engine and the input lines the transport counted.  */
static int
amk_ask_serve (struct amk_sink *out, const char *line, const char *input) {
  char op[32], name[1024], count[32];
  const char *p = line;
  char *text;
  int rc;

  if (!amk_ask_word (&p, op, sizeof op)) {
    fprintf (stderr, "amk: ask: expected an operation, got: %s\n", line);
    return 2;
  }
  if (strcmp (op, "filter") == 0) {
    if (!amk_ask_word (&p, name, sizeof name) || strspn (name, "0123456789") == strlen (name)
        || !amk_ask_word (&p, count, sizeof count)) {
      fprintf (stderr, "amk: ask: filter names its engine first: filter ENGINE LINES PROGRAM\n");
      return 2;
    }
    while (*p == ' ' || *p == '\t')
      ++p;
    return amk_workspace_filter (out, name, p, input);
  }
  if (!amk_ask_word (&p, name, sizeof name)) {
    fprintf (stderr, "amk: ask: %s: expected a name, got: %s\n", op, line);
    return 2;
  }
  while (*p == ' ' || *p == '\t')
    ++p;
  if (strcmp (op, "create") == 0)
    return amk_workspace_backing (name, p);
  if (strcmp (op, "dump") == 0)
    return amk_ns_ask (out, "dump", name, "");
  if (amk_ns_channel_op (op)) {
    char *end;
    unsigned long v = strtoul (p, &end, 10);
    if (strcmp (op, "wait") == 0 && (end == p || !amk_ns_valid (name))) {
      fprintf (stderr, "amk: ask: wait names a namespace and the version seen: wait NAME VERSION\n");
      return 2;
    }
    if (strcmp (op, "wait") == 0 && amk_ns_version (name) <= v) {
      amk_ask_hold = 1;
      return 0;
    }
    amk_ns_version_write (out, name);
    return 0;
  }
  if (strcmp (op, "load") == 0) {
    char path[4096];
    if (!amk_ask_word (&p, path, sizeof path)) {
      fprintf (stderr, "amk: ask: load %s: no path\n", name);
      return 2;
    }
    text = amk_ask_slurp (op, name, path);
    if (text == NULL)
      return 2;
    rc = amk_ns_ask (out, "load", name, text);
    free (text);
    return rc;
  }
  return amk_ns_ask (out, op, name, p);
}

/* The reply to one request: the workspace's status and how many lines follow, then each output on a line of its own, verbatim.  A build without a workspace row answers 2.  */
static char *
amk_ask_answer (const char *line, const char *input) {
  struct amk_buf_sink sink = { { amk_buf_write }, NULL, 0 };
  char *reply;
  const char *p;
  int rc, n = 0;

  rc = amk_ask_serve (&sink.base, line, input);
  if (amk_ask_hold) {
    free (sink.buf);
    return NULL;
  }

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

/* This process's own request sent up the inherited pair under a number, input lines after it, and its reply when that number comes back, children's replies routed on the way; nothing when the owner is gone.  */
static char *
amk_ask_up (const char *line, const char *input) {
  size_t n, m = input != NULL ? strlen (input) : 0;
  unsigned long id = amk_up_next++;
  char *req = xmalloc (strlen (line) + m + 32), *reply;
  sprintf (req, "#%lu %s\n", id, line);
  n = strlen (req);
  if (m > 0)
    memcpy (req + n, input, m);
  {
    /* An owner that went away is an error line and a status, not a signal.  */
    int wrote = amk_write_quiet (amk_up_req, req, n + m);
    free (req);
    if (wrote < 0)
      return NULL;
  }
  for (;;) {
    reply = amk_up_read ();
    if (reply == NULL)
      return NULL;
    reply = amk_up_route (reply, id);
    if (reply != NULL)
      return amk_reply_retag (reply, NULL);
  }
}

static char *
amk_ask_handle (const char *line, const char *input) {
  char *reply;
  /* Halt names this process, not the workspace's owner, so it is answered before any forwarding.  */
  if (strcmp (line, "halt") == 0) {
    amk_halt = 1;
    return xstrdup ("0 0\n");
  }
  reply = amk_up_req >= 0 ? amk_ask_up (line, input) : amk_ask_answer (line, input);
  if (reply == NULL && !amk_ask_hold) {
    fprintf (stderr, "amk: ask: no reply from the workspaces' owner\n");
    reply = xstrdup ("2 0\n");
  }
  return reply;
}

/* A forwarder's own persistent call: the reply's lines into the sink as they are; the status is the workspace's.  */
int
amk_ask_forward (const char *line, struct amk_sink *out) {
  char *reply = amk_ask_handle (line, NULL);
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
      amk_held_drop (c);
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
    lines = amk_ask_input_lines (line);
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
    if (amk_up_req >= 0 && strcmp (line, "halt") != 0)
      amk_up_relay (c, line, input);
    else {
      char *tag;
      const char *rest = amk_ask_untag (line, &tag);
      amk_ask_hold = 0;
      reply = amk_ask_handle (rest, input);
      /* A held request keeps its line and answers from a later change; the caller blocks on its reply as for any request.  */
      if (amk_ask_hold) {
        amk_held_add (c, rest, tag);
        amk_ask_hold = 0;
      } else {
        char *tagged = amk_reply_retag (reply, tag);
        amk_chan_reply (c, tagged);
        free (tagged);
        free (reply);
        free (tag);
      }
    }
    free (input);
    used = end - c->buf;
    memmove (c->buf, end, c->len - used);
    c->len -= used;
    c->buf[c->len] = '\0';
  }
}

/* Wait for a dead child or a request, whichever comes first, at most ms milliseconds when ms is not negative, and answer every request that is ready.  */
int
amk_ask_fdset (fd_set *rd) {
  unsigned int i;
  struct child *ch;
  int top = -1;
  if (amk_chld[0] >= 0 && amk_chld[0] < FD_SETSIZE) {
    FD_SET (amk_chld[0], rd);
    top = amk_chld[0];
  }
  if (amk_up_sent_len > 0 && amk_up_rep >= 0 && amk_up_rep < FD_SETSIZE) {
    FD_SET (amk_up_rep, rd);
    if (amk_up_rep > top)
      top = amk_up_rep;
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
amk_ask_ready (fd_set *rd) {
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
  if (amk_up_sent_len > 0 && amk_up_rep >= 0 && FD_ISSET (amk_up_rep, rd))
    amk_up_ready ();
}

/* The descriptors make's own wait watches, up to max of them into fds, for a guest reactor that answers through amk_ask_wait with no wait.  */
int
amk_ask_fds (int *fds, int max) {
  fd_set rd;
  int fd, top, n = 0;
  FD_ZERO (&rd);
  top = amk_ask_fdset (&rd);
  for (fd = 0; fd <= top && n < max; ++fd)
    if (FD_ISSET (fd, &rd))
      fds[n++] = fd;
  return n;
}

void
amk_ask_wait (int ms) {
  fd_set rd;
  struct timespec ts, *tsp = NULL;
  sigset_t empty;
  int top;

  FD_ZERO (&rd);
  top = amk_ask_fdset (&rd);
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
  amk_ask_ready (&rd);
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
    amk_ask_wait (amk_chld[0] >= 0 ? -1 : 50);
  }
}

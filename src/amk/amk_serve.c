/* Resident dispatch: a zygote parses the makefiles, parks on a unix socket, and forks a
   child per request carrying the client's cwd, argv, environment and descriptors.  Roles
   come from argv only: amk --serve <socket> -f <program> [goal], and amk --client <socket>
   [-- <cold command>] <args>.  A reply is the child's pid, then its status; 75 means the
   zygote declined and the client runs cold.  A missing socket runs cold at once, unless
   AMK_ZYGOTE names a live pid that has yet to bind it.  */

#include "makeint.h"
#include "filedef.h"
#include "dep.h"
#include "variable.h"
#include <fcntl.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <sys/stat.h>
#include <poll.h>
#include "amk.h"

extern char **environ;

#define AMK_MAXREQ    (4 * 1024 * 1024)
#define AMK_MAXCONN   1024

/* Client mode runs before make is initialized, so its failures cannot go
   through the usual reporting.  */

static void amk_die (const char *what, const char *why) NORETURN;

static void
amk_die (const char *what, const char *why) {
  fprintf (stderr, "amk: %s: %s\n", what, why);
  exit (MAKE_FAILURE);
}

int
amk_write_all (int fd, const void *buf, size_t len) {
  const char *p = buf;
  while (len > 0) {
    ssize_t w = write (fd, p, len);
    if (w < 0) { if (errno == EINTR) continue; return -1; }
    p += w;
    len -= (size_t) w;
  }
  return 0;
}

static int
amk_read_all (int fd, void *buf, size_t len) {
  char *p = buf;
  while (len > 0) {
    ssize_t r = read (fd, p, len);
    if (r < 0) { if (errno == EINTR) continue; return -1; }
    if (r == 0) return -1;
    p += r;
    len -= (size_t) r;
  }
  return 0;
}

static int
amk_read_line (int fd, char *buf, size_t size) {
  size_t len = 0;
  for (;;) {
    char c;
    ssize_t r = read (fd, &c, 1);
    if (r < 0) { if (errno == EINTR) continue; return 0; }
    if (r == 0) return 0;
    if (c == '\n') break;
    if (len < size - 1) buf[len++] = c;
  }
  buf[len] = '\0';
  return 1;
}

/* Make installs a fatal handler for the broken-pipe signal, so a departed
   client must not take a finished child down before it exits on its own.  */

int
amk_write_quiet (int fd, const void *buf, size_t len) {
  void (*prev) (int) = signal (SIGPIPE, SIG_IGN);
  int rc = amk_write_all (fd, buf, len);
  signal (SIGPIPE, prev);
  return rc;
}

void
amk_write_status (int fd, int status) {
  char buf[32];
  int len = sprintf (buf, "%d\n", status);
  amk_write_quiet (fd, buf, (size_t) len);
}

static void
amk_put_u32 (char **p, size_t v) {
  unsigned char *q = (unsigned char *) *p;
  q[0] = (unsigned char) (v & 0xff);
  q[1] = (unsigned char) ((v >> 8) & 0xff);
  q[2] = (unsigned char) ((v >> 16) & 0xff);
  q[3] = (unsigned char) ((v >> 24) & 0xff);
  *p += 4;
}

size_t
amk_get_u32 (const char **p) {
  const unsigned char *q = (const unsigned char *) *p;
  *p += 4;
  return (size_t) q[0] | ((size_t) q[1] << 8) | ((size_t) q[2] << 16)
         | ((size_t) q[3] << 24);
}

/* Pack cwd, argv and the environment into one length-prefixed buffer.  */

static char *
amk_build_request (int argc, char **argv, size_t *lenp) {
  PATH_VAR (cwd);
  size_t need = 4 + 4 + 4;
  int i, envc;
  char *buf, *p;

  if (getcwd (cwd, GET_PATH_MAX) == 0)
    amk_die ("getcwd", strerror (errno));

  need += strlen (cwd) + 1;
  for (i = 0; i < argc; ++i) need += strlen (argv[i]) + 1;
  for (envc = 0; environ[envc] != 0; ++envc) need += strlen (environ[envc]) + 1;

  buf = xmalloc (need);
  p = buf;
  amk_put_u32 (&p, need - 4);
  strcpy (p, cwd);
  p += strlen (cwd) + 1;

  amk_put_u32 (&p, (size_t) argc);
  for (i = 0; i < argc; ++i) { strcpy (p, argv[i]); p += strlen (argv[i]) + 1; }

  amk_put_u32 (&p, (size_t) envc);
  for (i = 0; i < envc; ++i) { strcpy (p, environ[i]); p += strlen (environ[i]) + 1; }

  *lenp = need;
  return buf;
}

/* Cosmopolitan carries the Linux cmsghdr on every host, and the Darwin and
   Berkeley kernels read their own 12-byte header instead, so on those hosts
   the block is laid out by hand.  Every other build compiles the standard
   path alone.  */

#ifdef __COSMOPOLITAN__
#define _COSMO_SOURCE 1
#include "libc/dce.h"
#define AMK_BSD_CMSG_LEN (12 + AMK_NFD * (int) sizeof (int))

static int
amk_bsd_cmsg (void) {
  return IsBsd ();
}

static void
amk_bsd_cmsg_pack (char *b, const int fds[AMK_NFD]) {
  uint32_t clen = AMK_BSD_CMSG_LEN;
  int32_t level = SOL_SOCKET, type = SCM_RIGHTS;
  memcpy (b, &clen, 4);
  memcpy (b + 4, &level, 4);
  memcpy (b + 8, &type, 4);
  memcpy (b + 12, fds, AMK_NFD * sizeof (int));
}

static int
amk_bsd_cmsg_unpack (const char *b, size_t n, int fds[AMK_NFD]) {
  uint32_t clen;
  int32_t level, type;
  if (n < AMK_BSD_CMSG_LEN) return 0;
  memcpy (&clen, b, 4);
  memcpy (&level, b + 4, 4);
  memcpy (&type, b + 8, 4);
  if (clen != AMK_BSD_CMSG_LEN || level != SOL_SOCKET || type != SCM_RIGHTS)
    return 0;
  memcpy (fds, b + 12, AMK_NFD * sizeof (int));
  return 1;
}
#else
#define AMK_BSD_CMSG_LEN 0
static int amk_bsd_cmsg (void) { return 0; }
static void amk_bsd_cmsg_pack (char *b, const int fds[AMK_NFD]) { (void) b; (void) fds; }
static int amk_bsd_cmsg_unpack (const char *b, size_t n, int fds[AMK_NFD]) { (void) b; (void) n; (void) fds; return 0; }
#endif

/* Hand the request over with the standard descriptors, the mail pipe and the
   call pair attached; a caller without one sends its stderr in that slot and
   no name for it in the environment.  A zygote that answered and closed before
   the send gives 0, not a signal.  */

static int
amk_send_request (int fd, const char *buf, size_t len) {
  union { struct cmsghdr align; char b[CMSG_SPACE (AMK_NFD * sizeof (int))]; } cbuf;
  int fds[AMK_NFD];
  struct msghdr msg;
  struct iovec iov;
  struct cmsghdr *cm;
  ssize_t sent;

  fds[0] = STDIN_FILENO;
  fds[1] = STDOUT_FILENO;
  fds[2] = STDERR_FILENO;
  fds[AMK_MAILFD] = amk_fd_is_pipe (getenv ("AMK_MAIL"));
  if (fds[AMK_MAILFD] < 0)
    fds[AMK_MAILFD] = STDERR_FILENO;
  fds[AMK_ASKFD] = amk_fd_is_pipe (getenv ("AMK_ASK"));
  fds[AMK_REPLYFD] = amk_fd_is_pipe (getenv ("AMK_REPLY"));
  if (fds[AMK_ASKFD] < 0 || fds[AMK_REPLYFD] < 0)
    fds[AMK_ASKFD] = fds[AMK_REPLYFD] = STDERR_FILENO;

  memset (&msg, '\0', sizeof msg);
  memset (&cbuf, '\0', sizeof cbuf);
  iov.iov_base = (void *) buf;
  iov.iov_len = len;
  msg.msg_iov = &iov;
  msg.msg_iovlen = 1;
  msg.msg_control = cbuf.b;
  if (amk_bsd_cmsg ()) {
    msg.msg_controllen = AMK_BSD_CMSG_LEN;
    amk_bsd_cmsg_pack (cbuf.b, fds);
  } else {
    msg.msg_controllen = CMSG_SPACE (AMK_NFD * sizeof (int));
    cm = CMSG_FIRSTHDR (&msg);
    cm->cmsg_level = SOL_SOCKET;
    cm->cmsg_type = SCM_RIGHTS;
    cm->cmsg_len = CMSG_LEN (AMK_NFD * sizeof (int));
    memcpy (CMSG_DATA (cm), fds, sizeof fds);
  }

  for (;;) {
    sent = sendmsg (fd, &msg, 0);
    if (sent >= 0) break;
    if (errno != EINTR) return 0;
  }

  /* Ancillary data rides the first sendmsg; any tail is plain stream.  */
  if ((size_t) sent < len
      && amk_write_all (fd, buf + sent, len - (size_t) sent) < 0)
    return 0;
  return 1;
}

/* Collect one request and its descriptors.  Returns 0 on a malformed one.  */

int
amk_recv_request (int fd, char **bufp, int fds[AMK_NFD]) {
  union { struct cmsghdr align; char b[CMSG_SPACE (AMK_NFD * sizeof (int))]; } cbuf;
  char head[4];
  const char *hp = head;
  struct msghdr msg;
  struct iovec iov;
  struct cmsghdr *cm;
  ssize_t r;
  size_t len;
  char *buf;

  memset (&msg, '\0', sizeof msg);
  memset (&cbuf, '\0', sizeof cbuf);
  iov.iov_base = head;
  iov.iov_len = sizeof head;
  msg.msg_iov = &iov;
  msg.msg_iovlen = 1;
  msg.msg_control = cbuf.b;
  msg.msg_controllen = sizeof cbuf.b;

  do r = recvmsg (fd, &msg, 0); while (r < 0 && errno == EINTR);
  if (r < 1) return 0;

  if (amk_bsd_cmsg ()) {
    if (!amk_bsd_cmsg_unpack (cbuf.b, msg.msg_controllen, fds))
      return 0;
  } else {
    cm = CMSG_FIRSTHDR (&msg);
    if (cm == 0 || cm->cmsg_level != SOL_SOCKET || cm->cmsg_type != SCM_RIGHTS
        || cm->cmsg_len != CMSG_LEN (AMK_NFD * sizeof (int)))
      return 0;
    memcpy (fds, CMSG_DATA (cm), AMK_NFD * sizeof (int));
  }

  if ((size_t) r < sizeof head
      && amk_read_all (fd, head + r, sizeof head - (size_t) r) < 0)
    return 0;

  len = amk_get_u32 (&hp);
  if (len == 0 || len > AMK_MAXREQ) return 0;

  buf = xmalloc (len);
  if (amk_read_all (fd, buf, len) < 0) { free (buf); return 0; }

  *bufp = buf;
  return 1;
}

/* Names make maintains across recursion, which keep the zygote's values.  */

static const char *const amk_env_managed[] =
  {
    "MAKEFLAGS", "MFLAGS", "MAKEOVERRIDES", "MAKE_TERMOUT", "MAKE_TERMERR",
    "MAKE_RESTARTS", "CURDIR"
  };

static int
amk_env_is_managed (const char *name, size_t len)
{
  unsigned int i;

  for (i = 0; i < sizeof amk_env_managed / sizeof *amk_env_managed; ++i)
    if (strlen (amk_env_managed[i]) == len
        && memcmp (name, amk_env_managed[i], len) == 0)
      return 1;
  return 0;
}

/* Drop what the zygote took from its own environment, so that a request's
   environment matches a cold run instead of adding to the zygote's.  */

void
amk_clear_zygote_env (void)
{
  unsigned int i;

  for (i = 0; environ[i] != 0; ++i) {
    size_t len = strcspn (environ[i], "=");
    if (environ[i][len] == '=' && !amk_env_is_managed (environ[i], len))
      undefine_variable_global (environ[i], len, o_env);
  }
}

/* Names the caller lists in AMK_REARM: per-execution values a makefile
   computes once at parse time, which a shared parse would otherwise freeze.  */

static int
amk_rearm_has (const char *set, const char *name, size_t len) {
  const char *p = set;

  if (set == 0)
    return 0;
  while (*p != '\0') {
    size_t n;
    p += strspn (p, " \t");
    n = strcspn (p, " \t");
    if (n == len && strncmp (p, name, len) == 0)
      return 1;
    p += n;
  }
  return 0;
}

char *
amk_env_value (const char *p, size_t envc, const char *key) {
  size_t klen = strlen (key);
  size_t i;

  for (i = 0; i < envc; ++i) {
    if (strncmp (p, key, klen) == 0 && p[klen] == '=')
      return xstrdup (p + klen + 1);
    p += strlen (p) + 1;
  }
  return 0;
}

/* Import the request environment the way make imports its own at startup, so
   that a makefile assignment still outranks it unless -e was given.  A rearmed
   name is the exception: the caller's value must beat the zygote's parse.  */

void
amk_import_env (const char *p, size_t envc, const char *rearm) {
  size_t i;

  for (i = 0; i < envc; ++i) {
    size_t len = strcspn (p, "=");
    const char *val = p + len;
    struct variable *v;

    if (*val != '=' || amk_env_is_managed (p, len)) {
      p += strlen (p) + 1;
      continue;
    }
    ++val;

    v = define_variable (p, len, val,
                         amk_rearm_has (rearm, p, len) ? o_override : o_env, 1);
    v->export = v_export;

    /* A makefile SHELL must not reach subprocesses, per posix.  */
    if (streq (v->name, "SHELL")) {
      v->export = v_noexport;
      shell_var.name = xstrdup ("SHELL");
      shell_var.length = 5;
      shell_var.value = xstrdup (val);
    }
    else if (streq (v->name, MAKELEVEL_NAME))
      makelevel = make_toui (val, NULL);

    p += strlen (p) + 1;
  }
}

/* The zygote's own options, normalized so that a separated argument is joined
   to its flag.  A request repeating one of these is asking for what the zygote
   already is, so the token is dropped; anything else it cannot serve.  */

#define AMK_ARGOPTS "fCoWImj"

static char **amk_zopts;
static int amk_nzopts;
static char amk_zshort[64];

int
amk_opt_takes_arg (const char *tok) {
  return tok[2] == '\0' && strchr (AMK_ARGOPTS, tok[1]) != 0;
}

static void
amk_zshort_add (const char *chars) {
  size_t n = strlen (amk_zshort);
  for (; *chars != '\0'; ++chars)
    if (strchr (amk_zshort, *chars) == 0 && n + 1 < sizeof amk_zshort) {
      amk_zshort[n++] = *chars;
      amk_zshort[n] = '\0';
    }
}

/* A run of short flags none of which takes an argument, so the letters can be
   compared one at a time rather than as a whole token.  */

static int
amk_opt_is_cluster (const char *tok) {
  const char *p;
  for (p = tok + 1; *p != '\0'; ++p)
    if (!isalpha ((unsigned char) *p) || strchr (AMK_ARGOPTS, *p) != 0)
      return 0;
  return tok[1] != '\0';
}

static void
amk_zopts_note (const char *tok) {
  if (tok[1] != '-' && amk_opt_is_cluster (tok))
    amk_zshort_add (tok + 1);
  else
    amk_zopts[amk_nzopts++] = xstrdup (tok);
}

/* The zygote's effective options: its own argv, which carries the makefile, plus
   MAKEFLAGS, which the makefiles themselves may set and which is therefore what
   a recursive call site expands to.  */

static void
amk_zopts_init (void) {
  struct variable *v;
  int i;

  amk_zopts = xmalloc (((size_t) amk_serve_argc + 64) * sizeof *amk_zopts);

  for (i = 1; i < amk_serve_argc; ++i) {
    const char *tok = amk_serve_argv[i];

    if (tok[0] != '-' || tok[1] == '\0') continue;
    if (amk_opt_takes_arg (tok) && i + 1 < amk_serve_argc) {
      char *joined = xmalloc (strlen (tok) + strlen (amk_serve_argv[i + 1]) + 1);
      sprintf (joined, "%s%s", tok, amk_serve_argv[++i]);
      amk_zopts[amk_nzopts++] = joined;
    }
    else
      amk_zopts_note (tok);
  }

  v = lookup_variable (STRING_SIZE_TUPLE ("MAKEFLAGS"));
  if (v != 0 && v->value != 0) {
    char *copy = xstrdup (v->value);
    char *tok;

    for (tok = strtok (copy, " \t"); tok != 0; tok = strtok (0, " \t")) {
      /* Everything past the separator is a variable override, not a flag.  */
      if (streq (tok, "--")) break;
      if (tok[0] == '-') amk_zopts_note (tok);
      else if (strchr (tok, '=') == 0) amk_zshort_add (tok);
    }
    free (copy);
  }
}

static int
amk_zopts_has (const char *tok) {
  int i;

  /* A cluster is satisfied letter by letter, so a request asking for less than
     the zygote carries still matches.  */
  if (tok[1] != '-' && amk_opt_is_cluster (tok)) {
    const char *p;
    for (p = tok + 1; *p != '\0'; ++p)
      if (strchr (amk_zshort, *p) == 0) return 0;
    return 1;
  }

  for (i = 0; i < amk_nzopts; ++i)
    if (streq (amk_zopts[i], tok)) return 1;
  return 0;
}

/* Walk a request's argv, joining a separated option argument.  Returns 0 when
   the request carries an option the zygote does not already have.  */

static void
amk_refused (const char *tok) {
  if (getenv ("AMK_DEBUG") != 0)
    fprintf (stderr, "amk: refused, zygote has no %s (it holds -%s %s)\n",
             tok, amk_zshort, amk_nzopts > 0 ? amk_zopts[0] : "");
}

int
amk_negotiate (const char *p, size_t argc) {
  size_t i;

  for (i = 0; i < argc; ++i) {
    const char *tok = p;

    p += strlen (p) + 1;
    if (tok[0] != '-' || tok[1] == '\0') continue;

    if (amk_opt_takes_arg (tok) && i + 1 < argc) {
      char *joined = xmalloc (strlen (tok) + strlen (p) + 1);
      int known;

      sprintf (joined, "%s%s", tok, p);
      p += strlen (p) + 1;
      ++i;
      known = amk_zopts_has (joined);
      if (!known) amk_refused (joined);
      free (joined);
      if (!known) return 0;
    }
    else if (!amk_zopts_has (tok)) {
      amk_refused (tok);
      return 0;
    }
  }
  return 1;
}

/* Opt-in staleness, for a makefile nothing else version-stamps.  A generator
   that names its artifacts by content needs none of this, since a changed
   program is a different path and its zygote cannot go stale.  AMK_WATCH arms
   it for hand-written makefiles, which are edited in place.  */

struct amk_watch { const char *name; time_t mtime; };

static struct amk_watch *amk_watched;
static unsigned int amk_nwatched;

static void
amk_watch_init (struct goaldep *deps) {
  const char *arm = getenv ("AMK_WATCH");
  struct goaldep *d;
  unsigned int n = 0;

  if (arm == 0 || *arm == '\0' || streq (arm, "0")) return;

  for (d = deps; d != 0; d = d->next) ++n;
  if (n == 0) return;

  amk_watched = xmalloc (n * sizeof *amk_watched);
  for (d = deps; d != 0; d = d->next) {
    const char *name = dep_name (d);
    struct stat st;

    amk_watched[amk_nwatched].name = name;
    amk_watched[amk_nwatched].mtime
      = stat (name, &st) == 0 ? st.st_mtime : (time_t) 0;
    ++amk_nwatched;
  }
}

static int
amk_watch_stale (void) {
  unsigned int i;

  for (i = 0; i < amk_nwatched; ++i) {
    struct stat st;
    time_t now = stat (amk_watched[i].name, &st) == 0 ? st.st_mtime : (time_t) 0;
    if (now != amk_watched[i].mtime) return 1;
  }
  return 0;
}

/* Serve requests on a unix socket, forking a child for each.  Never returns.  */

void
amk_serve (const char *sockpath, struct goaldep *deps) {
  struct { pid_t pid; int fd; } live[AMK_MAXCONN];
  unsigned int nlive = 0;
  struct sockaddr_un addr;
  struct pollfd pfd;
  int lfd;

  amk_watch_init (deps);
  amk_zopts_init ();

  if (strlen (sockpath) >= sizeof addr.sun_path)
    OS (fatal, NILF, _("socket path too long: %s"), sockpath);

  lfd = socket (AF_UNIX, SOCK_STREAM, 0);
  if (lfd < 0)
    pfatal_with_name ("socket");

  memset (&addr, '\0', sizeof addr);
  addr.sun_family = AF_UNIX;
  strcpy (addr.sun_path, sockpath);
  unlink (sockpath);

  if (bind (lfd, (struct sockaddr *) &addr, sizeof addr) < 0)
    pfatal_with_name (sockpath);
  if (listen (lfd, 64) < 0)
    pfatal_with_name ("listen");

  /* A zygote outlives whatever started it, so an inherited descriptor would be
     held open for good and a caller waiting for end of stream on one would wait
     forever.  The client supplies the standard three; the listener is ours.  */
  {
    int fd, top = (int) sysconf (_SC_OPEN_MAX);

    if (top < 0 || top > 4096) top = 4096;
    for (fd = 3; fd < top; ++fd)
      if (fd != lfd) close (fd);
  }

  for (;;) {
    unsigned int i;
    pid_t done;
    int conn;

    pfd.fd = lfd;
    pfd.events = POLLIN;
    if (poll (&pfd, 1, 1000) < 0 && errno != EINTR)
      pfatal_with_name ("poll");

    /* Reap children and release the connections they answered on.  */
    while ((done = waitpid (-1, NULL, WNOHANG)) > 0)
      for (i = 0; i < nlive; ++i)
        if (live[i].pid == done) {
          close (live[i].fd);
          live[i] = live[--nlive];
          break;
        }

    /* A client that has gone takes its child with it.  The peek consumes
       nothing and reports a live peer whether or not the child has read.  */
    for (i = 0; i < nlive; ++i) {
      char c;
      if (recv (live[i].fd, &c, 1, MSG_PEEK | MSG_DONTWAIT) == 0)
        kill (live[i].pid, SIGTERM);
    }

    if (!(pfd.revents & POLLIN)) continue;

    conn = accept (lfd, NULL, NULL);
    if (conn < 0) {
      if (errno == EINTR || errno == ECONNABORTED) continue;
      pfatal_with_name ("accept");
    }

    if (amk_watch_stale () || nlive == AMK_MAXCONN) {
      amk_write_status (conn, 0);
      amk_write_status (conn, nlive == AMK_MAXCONN ? MAKE_FAILURE : AMK_STALE);
      close (conn);
      continue;
    }

    /* Fork before reading, so a client that stalls blocks only its own
       child rather than every request behind it.  */
    fflush (NULL);
    live[nlive].pid = fork ();
    if (live[nlive].pid < 0)
      pfatal_with_name ("fork");

    if (live[nlive].pid == 0) { close (lfd); amk_dispatch (conn); }

    live[nlive++].fd = conn;
  }
}

/* The command to run when no zygote can serve the request.  After `--` the
   caller supplied it outright; otherwise AMK_COLD names the make to prepend.  */

static char **amk_cold_argv;

static void amk_cold (int argc, char **argv) NORETURN;

static void
amk_cold (int argc, char **argv) {
  const char *cold;
  char **nargv;
  char *spec, *tok;
  int n = 0, i;

  /* The client ignores a broken pipe; a cold make must not inherit that.  */
  signal (SIGPIPE, SIG_DFL);

  if (amk_cold_argv != 0) {
    execvp (amk_cold_argv[0], amk_cold_argv);
    amk_die (amk_cold_argv[0], strerror (errno));
  }

  cold = getenv ("AMK_COLD");
  if (cold == 0 || *cold == '\0')
    amk_die ("no zygote answered", "no command after -- and AMK_COLD unset");

  spec = xstrdup (cold);
  nargv = xmalloc ((strlen (spec) / 2 + (size_t) argc + 2) * sizeof *nargv);
  for (tok = strtok (spec, " \t"); tok != 0; tok = strtok (0, " \t")) nargv[n++] = tok;
  for (i = 0; i < argc; ++i) nargv[n++] = argv[i];
  nargv[n] = 0;

  execvp (nargv[0], nargv);
  amk_die (nargv[0], strerror (errno));
}

/* The child this client is waiting on, and the signal it last passed along.  */

static volatile sig_atomic_t amk_peer_pid;
static volatile sig_atomic_t amk_peer_sig;

static void
amk_forward_signal (int sig) {
  amk_peer_sig = sig;
  if (amk_peer_pid > 0) kill ((pid_t) amk_peer_pid, sig);
  else _exit (128 + sig);
}

/* An already-ignored signal stays ignored, as make does for its own.  */

static void
amk_catch (int sig) {
  if (signal (sig, amk_forward_signal) == SIG_IGN)
    signal (sig, SIG_IGN);
}

/* One run, resident: fork a zygote on this command's own argv, route the command
   through it, and take the zygote down when the command ends; every nested client
   descends from the request, so none outlives it.  Returns nonzero in the child,
   which parses and parks; the parent never returns.  */

static char amk_run_dir[] = "/tmp/amk-resident.XXXXXX";
static char amk_run_sock[sizeof amk_run_dir + 16];
static pid_t amk_run_zygote;

/* Idempotent, since a resident run may reach it by exit, by signal, or by the
   client dying alongside its child.  */

static void
amk_resident_reap (void) {
  if (amk_run_sock[0] == '\0')
    return;
  if (amk_run_zygote > 0) {
    kill (amk_run_zygote, SIGTERM);
    waitpid (amk_run_zygote, NULL, 0);
    amk_run_zygote = 0;
  }
  unlink (amk_run_sock);
  rmdir (amk_run_dir);
  amk_run_sock[0] = '\0';
}

static void
amk_resident_signal (int sig) {
  amk_resident_reap ();
  signal (sig, SIG_DFL);
  raise (sig);
}

int
amk_resident (int argc, char **argv) {
  const char *tmp = getenv ("TMPDIR");
  unsigned int waited;
  pid_t pid;

  if (tmp != 0 && *tmp != '\0'
      && strlen (tmp) + sizeof "/amk-resident.XXXXXX" <= sizeof amk_run_dir)
    sprintf (amk_run_dir, "%s/amk-resident.XXXXXX", tmp);

  /* Nowhere to put a socket is a reason to be an ordinary make, not to fail.  */
  if (mkdtemp (amk_run_dir) == 0)
    return 0;
  sprintf (amk_run_sock, "%s/zygote.sock", amk_run_dir);

  pid = fork ();
  if (pid < 0) {
    rmdir (amk_run_dir);
    return 0;
  }

  if (pid == 0) {
    /* The zygote answers on the socket and owns none of the caller's streams.  */
    int null = open ("/dev/null", O_RDWR);
    if (null >= 0) {
      dup2 (null, STDIN_FILENO);
      dup2 (null, STDOUT_FILENO);
      dup2 (null, STDERR_FILENO);
      if (null > STDERR_FILENO) close (null);
    }
    amk_serve_path = amk_run_sock;
    return 1;
  }

  amk_run_zygote = pid;
  atexit (amk_resident_reap);
  signal (SIGINT, amk_resident_signal);
  signal (SIGTERM, amk_resident_signal);
  signal (SIGHUP, amk_resident_signal);

  for (waited = 0; waited < 3000; ++waited) {
    struct stat st;
    int gone;

    if (stat (amk_run_sock, &st) == 0)
      break;
    gone = waitpid (pid, NULL, WNOHANG) == pid;
    if (gone) {
      amk_run_zygote = 0;
      rmdir (amk_run_dir);
      return 0;
    }
    usleep (10000);
  }

  /* A zygote that never bound costs nothing but the saving.  */
  {
    struct stat st;
    if (stat (amk_run_sock, &st) != 0) {
      amk_resident_reap ();
      return 0;
    }
  }

  /* Recursion by path reaches the zygote through MAKE; a caller that recurses
     by name instead reads AMK_CLIENT and prefixes its own command.  */
  {
    char *spec = xmalloc (strlen (argv[0]) * 2 + strlen (amk_run_sock) + 32);
    sprintf (spec, "%s --client %s -- %s", argv[0], amk_run_sock, argv[0]);
    setenv ("MAKE", spec, 1);
    sprintf (spec, "%s --client %s -- ", argv[0], amk_run_sock);
    setenv ("AMK_CLIENT", spec, 1);
    free (spec);
  }

  /* A refusal re-runs the caller's own command as an ordinary make.  */
  amk_cold_argv = argv;
  amk_client (amk_run_sock, argc - 1, argv + 1);
  return 0;
}

/* Connect to a zygote's socket, or return -1.  A socket that is not there yet
   is retried in process for as long as the pid in AMK_ZYGOTE is alive; any
   other failure, and a dead or absent zygote, answers at once.  */

static int
amk_connect (const char *sockpath) {
  struct sockaddr_un addr;
  const char *spec = getenv ("AMK_ZYGOTE");
  pid_t zygote = spec != 0 ? (pid_t) atoi (spec) : 0;

  if (strlen (sockpath) >= sizeof addr.sun_path)
    amk_die (sockpath, "socket path too long");

  memset (&addr, '\0', sizeof addr);
  addr.sun_family = AF_UNIX;
  strcpy (addr.sun_path, sockpath);

  for (;;) {
    int fd = socket (AF_UNIX, SOCK_STREAM, 0);
    int err;

    if (fd < 0)
      amk_die ("socket", strerror (errno));
    if (connect (fd, (struct sockaddr *) &addr, sizeof addr) == 0)
      return fd;
    err = errno;
    close (fd);
    /* A parse that stages a cold cache runs as long as it runs; the wait ends with the zygote, not with a count.  */
    if (err != ENOENT || zygote <= 0)
      return -1;
    if (kill (zygote, 0) < 0 && errno == ESRCH)
      return -1;
    usleep (10000);
  }
}

/* Hand this command to a zygote and exit on its status.  Never returns.  */

void
amk_client (const char *sockpath, int argc, char **argv) {
  char line[64];
  size_t len;
  char *buf;
  int fd;

  /* A cold command after the separator is the caller's own fallback; the
     request then repeats it without the program name the zygote already is.  */
  if (argc >= 2 && strcmp (argv[0], "--") == 0) {
    amk_cold_argv = argv + 1;
    argv += 2;
    argc -= 2;
  }

  /* A missing or dead socket is the same answer as a stale one.  */
  fd = amk_connect (sockpath);
  if (fd < 0)
    amk_cold (argc, argv);

  signal (SIGPIPE, SIG_IGN);
  amk_catch (SIGINT);
  amk_catch (SIGTERM);
  amk_catch (SIGHUP);
  amk_catch (SIGQUIT);

  /* A mail or call name with no pipe behind it would name a closed descriptor in the request.  */
  if (amk_fd_is_pipe (getenv ("AMK_MAIL")) < 0)
    unsetenv ("AMK_MAIL");
  if (amk_fd_is_pipe (getenv ("AMK_ASK")) < 0 || amk_fd_is_pipe (getenv ("AMK_REPLY")) < 0) {
    unsetenv ("AMK_ASK");
    unsetenv ("AMK_REPLY");
  }

  buf = amk_build_request (argc, argv, &len);
  if (!amk_send_request (fd, buf, len))
    amk_cold (argc, argv);
  free (buf);

  /* The pid line, then the status.  Waiting for end of stream instead would
     cost a poll interval, since the parent holds its copy until it reaps.  */
  if (!amk_read_line (fd, line, sizeof line))
    amk_cold (argc, argv);
  amk_peer_pid = (sig_atomic_t) atoi (line);

  if (!amk_read_line (fd, line, sizeof line)) {
    /* No status after a signal means the child died on it, so die alike.
       Dying by signal skips the exit handlers, so a resident run reaps here.  */
    if (amk_peer_sig) {
      amk_resident_reap ();
      signal ((int) amk_peer_sig, SIG_DFL);
      raise ((int) amk_peer_sig);
    }
    exit (MAKE_FAILURE);
  }

  if (atoi (line) == AMK_STALE)
    amk_cold (argc, argv);

  exit (atoi (line));
}

/* Pools: named semaphores generalizing the jobserver into colored tokens for control structures and bounded concurrency, each a ledger of a size, goals being make's own; a labeled pool's token is its label; the amk.pool builtins, and what this process holds given back at exit and forgotten in a fork, each a hook of the pool's own.  */

#include "makeint.h"
#include "os.h"
#include "filedef.h"
#include "variable.h"
#include "amk.h"
#include <sys/ioctl.h>

#define AMK_POOLS 64
#define AMK_POOL_WIDTH 32
#define AMK_POOL_PIPE 16384

/* A pool: its ledger, its size, what this process holds, the bytes in one token, 1 unlabeled, the labels held, the process that opened it, whether produce or consume ran here, whether its strategy is open, and its give-back at exit and forgetting at fork.  */
struct amk_pool {
  const char *name;
  unsigned int size;
  unsigned int held;
  struct jobserver *js;
  unsigned int width;
  char *held_labels;
  unsigned int held_cap;
  pid_t opener;
  int resized;
  int open;
  void (*give_back) (struct amk_pool *p);
  void (*forget) (struct amk_pool *p);
};
static struct amk_pool amk_pools[AMK_POOLS] = { { "goals", 0, 0, NULL, 1, NULL, 0, 0, 0, 0, NULL, NULL } };
static unsigned int amk_pools_len = 1;

static int
amk_pool_find (const char *name) {
  unsigned int i;
  for (i = 0; i < amk_pools_len; ++i)
    if (strcmp (amk_pools[i].name, name) == 0)
      return (int) i;
  return -1;
}

static unsigned int
amk_pool_named (const char *fn, const char *name) {
  int c = amk_pool_find (name);
  if (c < 0)
    OSS (fatal, reading_file, "%s: no pool named %s", fn, name);
  return (unsigned int) c;
}

static const char *const amk_pool_verbs[] = { "size", "held", "auth", "acquire", "release", "produce", "consume", NULL };
static char *amk_func_pool_bound (void *state, const char *fn, unsigned int argc, char **argv);

/* The pool's verbs as make functions of its own name, amk.pool.name.verb, so a guest reaches them as fields of its handle.  */
static void
amk_pool_bind (unsigned int c) {
  const char *const *v;
  char fn[320];
  for (v = amk_pool_verbs; *v != NULL; ++v) {
    snprintf (fn, sizeof fn, "amk.pool.%s.%s", amk_pools[c].name, *v);
    amk_func_add (fn, &amk_pools[c], amk_func_pool_bound);
  }
}

/* A label fits a token when it is one to width-1 bytes with no whitespace.  */
static void
amk_pool_label_check (const char *name, const char *label) {
  const char *s;
  if (*label == '\0' || strlen (label) >= AMK_POOL_WIDTH)
    OSS (fatal, reading_file, "amk.pool: %s: label '%s' is not 1 to 31 bytes", name, label);
  for (s = label; *s != '\0'; ++s)
    if (ISSPACE (*s))
      OSS (fatal, reading_file, "amk.pool: %s: label '%s' has whitespace", name, label);
}

/* One label written as one whole token, padded with zero bytes.  */
static void
amk_pool_write_label (struct amk_pool *p, int is_fatal, const char *label) {
  char token[JOBSERVER_WIDTH_MAX];
  memset (token, 0, sizeof token);
  memcpy (token, label, strlen (label));
  jobserver_release_token_on (p->js, is_fatal, token);
}

/* The labels this process holds, one token's width each.  */
static void
amk_pool_hold_label (struct amk_pool *p, const char *token) {
  if (p->held >= p->held_cap) {
    p->held_cap = p->held_cap ? p->held_cap * 2 : 4;
    p->held_labels = xrealloc (p->held_labels, p->held_cap * p->width);
  }
  memcpy (p->held_labels + p->held * p->width, token, p->width);
  p->held++;
}

static int
amk_pool_held_index (struct amk_pool *p, const char *label) {
  unsigned int k;
  for (k = 0; k < p->held; ++k)
    if (strncmp (p->held_labels + k * p->width, label, p->width) == 0)
      return (int) k;
  return -1;
}

/* The give-back every pool has today: what it holds goes back, labels as they were taken.  */
static void
amk_pool_give_back_held (struct amk_pool *p) {
  if (p->width > 1)
    for (; p->held > 0; p->held--)
      amk_pool_write_label (p, 0, p->held_labels + (p->held - 1) * p->width);
  else
    for (; p->held > 0; p->held--)
      jobserver_release_on (p->js, 0);
}

/* The forgetting every pool has today: a fork's child holds none.  */
static void
amk_pool_forget_all (struct amk_pool *p) {
  p->held = 0;
}

/* A new pool: a pipe-style ledger of size + tokens by the jobserver's own setup, or, given labels, one whole token per label, and empty at size 0; its tokens must fit the pipe, and a name that is a verb would shadow the verbs.  */
static void
amk_pool_open (const char *name, unsigned int size, char **labels, int open) {
  unsigned int i = amk_pools_len;
  unsigned int width = labels != NULL ? AMK_POOL_WIDTH : 1;
  const char *const *v;
  struct amk_pool *p;
  if (amk_pool_find (name) >= 0)
    OS (fatal, reading_file, "amk.pool: %s is already open", name);
  for (v = amk_pool_verbs; *v != NULL; ++v)
    if (strcmp (*v, name) == 0)
      OS (fatal, reading_file, "amk.pool: %s is a verb, not a name a pool may take", name);
  if (size > AMK_POOL_PIPE / width)
    ONS (fatal, reading_file, "amk.pool: %u tokens fill the pipe, and %s has more", AMK_POOL_PIPE / width, name);
  if (i >= AMK_POOLS)
    ONS (fatal, reading_file, "amk.pool: %u pools are open, no room for %s", AMK_POOLS, name);
  p = &amk_pools[i];
  memset (p, 0, sizeof *p);
  p->js = jobserver_new ();
  p->name = xstrdup (name);
  p->size = size;
  p->width = width;
  p->opener = getpid ();
  p->open = open;
  p->give_back = amk_pool_give_back_held;
  p->forget = amk_pool_forget_all;
  if (labels != NULL) {
    unsigned int k;
    jobserver_setup_on (p->js, 0, "pipe");
    jobserver_width_on (p->js, width);
    for (k = 0; k < size; ++k)
      amk_pool_write_label (p, 1, labels[k]);
  } else
    jobserver_setup_on (p->js, (int) size, "pipe");
  amk_pools_len = i + 1;
  amk_pool_bind (i);
}

/* The goals pool's size: make's slot count while it holds one, else the -j in MAKEFLAGS once the jobserver owns the count.  */
static unsigned int
amk_pool_goals_size (void) {
  const struct variable *v;
  const char *p;
  if (job_slots > 0)
    return job_slots;
  v = lookup_variable (STRING_SIZE_TUPLE ("MAKEFLAGS"));
  for (p = v != NULL ? v->value : ""; *p != '\0'; ++p)
    if (*p == 'j' && ISDIGIT (p[1]) && (p == v->value || !ISDIGIT (p[-1])))
      return (unsigned int) atoi (p + 1);
  return 1;
}

/* The tokens waiting in the pipe now, by the kernel's count, exact in every process.  */
static unsigned int
amk_pool_count (struct amk_pool *p) {
  char *auth = jobserver_get_auth_on (p->js);
  int n = 0, fd = atoi (auth);
  free (auth);
  if (ioctl (fd, FIONREAD, &n) < 0)
    OS (fatal, reading_file, "amk.pool: %s: cannot count the pipe", p->name);
  return (unsigned int) n / p->width;
}

/* A size: an open pool's is the kernel's count; a strict one's is exact in the opener, the one process that resizes, and refused in a fork once produce or consume ran before it, since its copy is stale.  */
static unsigned int
amk_pool_size (unsigned int c) {
  if (c == 0)
    return amk_pool_goals_size ();
  if (amk_pools[c].open)
    return amk_pool_count (&amk_pools[c]);
  if (amk_pools[c].resized && getpid () != amk_pools[c].opener)
    OS (fatal, reading_file, "amk.pool: %s: the size is kept only by the process that opened it once produce or consume ran", amk_pools[c].name);
  return amk_pools[c].size;
}

static char *
amk_pool_number (unsigned int n) {
  char buf[32];
  sprintf (buf, "%u", n);
  return xstrdup (buf);
}

/* At exit every pool but goals runs its give-back; after a fork every pool runs its forgetting.  */
void
amk_pool_release_all (void) {
  unsigned int i;
  for (i = 1; i < amk_pools_len; ++i)
    if (amk_pools[i].give_back != NULL)
      amk_pools[i].give_back (&amk_pools[i]);
}

void
amk_pool_forget_held (void) {
  unsigned int i;
  for (i = 0; i < amk_pools_len; ++i)
    if (amk_pools[i].forget != NULL)
      amk_pools[i].forget (&amk_pools[i]);
}

/* The opening arguments: a bare size, or size=, labels=, labeled=true for a labeled pool that starts empty, strategy= of default, strict or fifo, all one, or open, and the reserved label_gen= as key=value, an empty value being no value; labels set the size, and a size that disagrees is refused.  */
static void
amk_pool_open_args (const char *name, unsigned int argc, char **argv) {
  const char *size = NULL;
  char **labels = NULL;
  int labeled = 0, open = 0;
  unsigned int i, n = 0, cap = 0;
  for (i = 1; i < argc; ++i) {
    char *copy = xstrdup (argv[i]);
    char *value;
    char *key = amk_kwarg (copy, &value);
    if (value == NULL && i == 1 && *key != '\0')
      size = xstrdup (key);
    else if (value == NULL)
      OSS (fatal, reading_file, "amk.pool: %s: no key %s", name, key);
    else if (*value == '\0')
      ;
    else if (strcmp (key, "size") == 0)
      size = xstrdup (value);
    else if (strcmp (key, "labels") == 0) {
      const char *p = value;
      char *w;
      size_t len;
      while ((w = find_next_token (&p, &len)) != NULL) {
        if (n >= cap) {
          cap = cap ? cap * 2 : 8;
          labels = xrealloc (labels, cap * sizeof (char *));
        }
        labels[n] = xstrndup (w, len);
        amk_pool_label_check (name, labels[n++]);
      }
    }
    else if (strcmp (key, "labeled") == 0) {
      if (strcmp (value, "true") != 0 && strcmp (value, "false") != 0)
        OSS (fatal, reading_file, "amk.pool: %s: labeled is true or false, not %s", name, value);
      labeled = strcmp (value, "true") == 0;
    }
    else if (strcmp (key, "label_gen") == 0)
      OS (fatal, reading_file, "amk.pool: %s: label_gen is reserved, not yet supported", name);
    else if (strcmp (key, "strategy") == 0) {
      open = strcmp (value, "open") == 0;
      if (!open && strcmp (value, "default") != 0 && strcmp (value, "strict") != 0 && strcmp (value, "fifo") != 0)
        OSS (fatal, reading_file, "amk.pool: %s: strategy %s; one of default strict open", name, value);
    }
    else
      OSS (fatal, reading_file, "amk.pool: %s: no key %s", name, key);
    free (copy);
  }
  if (size != NULL && (*size == '\0' || size[strspn (size, "0123456789")] != '\0'))
    OSS (fatal, reading_file, "amk.pool: %s: size %s is not a number", name, size);
  if (labeled && labels == NULL) {
    if (size != NULL && atoi (size) != 0)
      OSS (fatal, reading_file, "amk.pool: %s: a labeled pool takes its tokens from labels, not size %s", name, size);
    labels = xmalloc (sizeof (char *));
    size = NULL;
  }
  if (labels == NULL && size == NULL)
    OS (fatal, reading_file, "amk.pool: %s needs a size or labels", name);
  if (labels != NULL && size != NULL && (unsigned int) atoi (size) != n)
    OSS (fatal, reading_file, "amk.pool: %s: size %s disagrees with the labels", name, size);
  amk_pool_open (name, labels != NULL ? n : (size != NULL ? (unsigned int) atoi (size) : 0), labels, open);
}

/* $(amk.pool name) answers a size, empty for none, and an empty name lists the open pools, since make reads a bare $(amk.pool) as a variable; $(amk.pool name, size) or $(amk.pool name, labels=a b) opens one.  */
static char *
amk_func_pool (void *state, const char *fn, unsigned int argc, char **argv) {
  const char *name;
  int c;
  name = argc > 0 ? amk_trim (argv[0]) : "";
  if (*name == '\0') {
    unsigned int i;
    size_t len = 1;
    char *out;
    for (i = 0; i < amk_pools_len; ++i)
      len += strlen (amk_pools[i].name) + 1;
    out = xmalloc (len);
    out[0] = '\0';
    for (i = 0; i < amk_pools_len; ++i) {
      if (i > 0)
        strcat (out, " ");
      strcat (out, amk_pools[i].name);
    }
    return out;
  }
  if (argc == 1) {
    c = amk_pool_find (name);
    if (c < 0)
      return xstrdup ("");
    return amk_pool_number (amk_pool_size ((unsigned int) c));
  }
  if (strcmp (name, "goals") == 0)
    O (fatal, reading_file, "amk.pool: goals is the jobserver, sized by -j");
  amk_pool_open_args (name, argc, argv);
  return xstrdup ("");
}

/* The token the last acquire took: a labeled pool's label, refused when it is no whole label.  */
static const char *
amk_pool_taken (struct amk_pool *p) {
  const char *token = jobserver_token_on ();
  if (token[0] == '\0' || token[p->width - 1] != '\0')
    OS (fatal, reading_file, "amk.pool: %s: a token that is no label", p->name);
  return token;
}

/* A labeled pool's release: the label named, else the one held, and only a label this process holds.  */
static char *
amk_pool_release_label (struct amk_pool *p, const char *label) {
  int k;
  if (*label == '\0' && p->held != 1)
    OS (fatal, reading_file, "amk.pool: %s: release names a label unless exactly one is held", p->name);
  k = *label == '\0' ? 0 : amk_pool_held_index (p, label);
  if (k < 0)
    OSS (fatal, reading_file, "amk.pool: %s: %s is not held here", p->name, label);
  amk_pool_write_label (p, 1, p->held_labels + k * p->width);
  p->held--;
  memmove (p->held_labels + k * p->width, p->held_labels + (k + 1) * p->width, (p->held - k) * p->width);
  return xstrdup ("");
}

/* produce and consume change the size, so only the process that opened a strict pool runs them, any process an open one's, and never on goals.  */
static void
amk_pool_resizer (unsigned int c, const char *verb) {
  if (c == 0)
    O (fatal, reading_file, "amk.pool: goals is the jobserver, sized by -j");
  if (!amk_pools[c].open && getpid () != amk_pools[c].opener)
    OSS (fatal, reading_file, "amk.pool: %s: only the process that opened it may %s", amk_pools[c].name, verb);
}

/* produce: one token more, with no token held; a labeled pool's label may be new.  */
static char *
amk_pool_produce (unsigned int c, const char *label) {
  struct amk_pool *p = &amk_pools[c];
  amk_pool_resizer (c, "produce");
  if ((p->open ? amk_pool_count (p) : p->size) + 1 > AMK_POOL_PIPE / p->width)
    ONS (fatal, reading_file, "amk.pool: %u tokens fill the pipe, and %s has them", AMK_POOL_PIPE / p->width, p->name);
  if (p->width > 1) {
    amk_pool_label_check (p->name, label);
    amk_pool_write_label (p, 1, label);
  } else if (*label != '\0')
    OS (fatal, reading_file, "amk.pool: %s: produce takes a label only on a labeled pool", p->name);
  else
    jobserver_release_on (p->js, 1);
  p->size++;
  p->resized = 1;
  return xstrdup ("");
}

/* consume: a fresh token taken for good, waiting with no ms; refused while this process holds one, since a held token goes back by release.  */
static char *
amk_pool_consume (unsigned int c, unsigned int argc, char **argv) {
  struct amk_pool *p = &amk_pools[c];
  amk_pool_resizer (c, "consume");
  if (p->held > 0)
    OS (fatal, reading_file, "amk.pool: %s: consume takes a fresh token, and this process holds one", p->name);
  if (!jobserver_acquire_on (p->js, argc > 0 ? atoi (amk_trim (argv[0])) : -1))
    return xstrdup ("");
  p->size--;
  p->resized = 1;
  return xstrdup (p->width > 1 ? amk_pool_taken (p) : "1");
}

/* One verb on one pool: size, held, auth as the value --jobserver-auth takes and empty for goals without a jobserver, acquire answering 1 with a token held, or a labeled pool's label, or empty when none came within ms, waiting with no ms, release giving one back, and produce and consume.  */
static char *
amk_pool_verb (unsigned int c, const char *verb, unsigned int argc, char **argv) {
  struct amk_pool *p = &amk_pools[c];
  const char *arg = argc > 0 ? amk_trim (argv[0]) : "";
  if (strcmp (verb, "size") == 0)
    return amk_pool_number (amk_pool_size (c));
  if (strcmp (verb, "held") == 0)
    return amk_pool_number (p->held);
  if (strcmp (verb, "auth") == 0) {
    if (p->width > 1)
      OS (fatal, reading_file, "amk.pool: %s: a labeled pool gives no auth", p->name);
    if (!jobserver_enabled_on (p->js))
      return xstrdup ("");
    return jobserver_get_auth_on (p->js);
  }
  if (strcmp (verb, "produce") == 0)
    return amk_pool_produce (c, arg);
  if (strcmp (verb, "consume") == 0)
    return amk_pool_consume (c, argc, argv);
  if (strcmp (verb, "release") == 0) {
    if (p->held == 0)
      OS (fatal, reading_file, "amk.pool: %s: nothing held to release", p->name);
    if (p->width > 1)
      return amk_pool_release_label (p, arg);
    if (*arg != '\0')
      OS (fatal, reading_file, "amk.pool: %s: release takes a label only on a labeled pool", p->name);
    jobserver_release_on (p->js, 1);
    p->held--;
    return xstrdup ("");
  }
  if (!jobserver_acquire_on (p->js, *arg != '\0' ? atoi (arg) : -1))
    return xstrdup ("");
  if (p->width > 1) {
    const char *token = amk_pool_taken (p);
    amk_pool_hold_label (p, token);
    return xstrdup (token);
  }
  p->held++;
  return xstrdup ("1");
}

/* $(amk.pool.<verb> name, ...): the verb on the pool the first argument names.  */
static char *
amk_func_pool_member (void *state, const char *fn, unsigned int argc, char **argv) {
  unsigned int c = amk_pool_named (fn, amk_trim (argv[0]));
  return amk_pool_verb (c, fn + strlen ("amk.pool."), argc - 1, argv + 1);
}

/* $(amk.pool.<name>.<verb> ...): the verb on the pool the function was bound to.  */
static char *
amk_func_pool_bound (void *state, const char *fn, unsigned int argc, char **argv) {
  unsigned int c = (unsigned int) ((char *) state - (char *) amk_pools) / sizeof amk_pools[0];
  return amk_pool_verb (c, strrchr (fn, '.') + 1, argc, argv);
}

void
amk_pool_init (void) {
  const char *const *v;
  char fn[64];
  amk_pools[0].js = jobserver_goals ();
  amk_pools[0].forget = amk_pool_forget_all;
  amk_func_add ("amk.pool", NULL, amk_func_pool);
  for (v = amk_pool_verbs; *v != NULL; ++v) {
    snprintf (fn, sizeof fn, "amk.pool.%s", *v);
    amk_func_add (fn, NULL, amk_func_pool_member);
  }
  amk_pool_bind (0);
}

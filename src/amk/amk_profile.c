/* The function profiler: when AMK_PROFILE names a file, or a dash for stderr, every builtin, every call of a macro and every recursive variable expansion is timed under its name, and the table of self and total time per name is appended when the process dies.  Unset, the one check per expansion is the whole cost.  */

#include "makeint.h"
#include "hash.h"
#include "amk.h"

int amk_profile_on = -1;

struct amk_prof_node { const char *key; unsigned long count; double total; double self; };
static struct hash_table amk_prof_table;
static struct amk_prof_frame *amk_prof_top = NULL;
static double amk_prof_start;

static unsigned long
amk_prof_hash_1 (const void *k)
{
  return_STRING_HASH_1 (((const struct amk_prof_node *) k)->key);
}

static unsigned long
amk_prof_hash_2 (const void *k)
{
  return_STRING_HASH_2 (((const struct amk_prof_node *) k)->key);
}

static int
amk_prof_cmp (const void *x, const void *y)
{
  return_STRING_COMPARE (((const struct amk_prof_node *) x)->key, ((const struct amk_prof_node *) y)->key);
}

static double
amk_prof_now (void)
{
  struct timespec ts;
  clock_gettime (CLOCK_MONOTONIC, &ts);
  return ts.tv_sec + ts.tv_nsec * 1e-9;
}

/* Opens a frame and answers whether it is timed; the first call reads the environment and sets up the table.  */
int
amk_profile_enter (struct amk_prof_frame *f)
{
  if (amk_profile_on < 0)
    {
      const char *path = getenv ("AMK_PROFILE");
      amk_profile_on = path != NULL && *path != '\0';
      if (amk_profile_on)
        {
          hash_init (&amk_prof_table, 1024, amk_prof_hash_1, amk_prof_hash_2, amk_prof_cmp);
          amk_prof_start = amk_prof_now ();
        }
    }
  if (!amk_profile_on)
    return 0;
  f->start = amk_prof_now ();
  f->child = 0;
  f->up = amk_prof_top;
  amk_prof_top = f;
  return 1;
}

/* Closes a frame under kind and name: its whole time goes to the parent's children and to this name's total, the rest to its self.  */
void
amk_profile_leave (struct amk_prof_frame *f, const char *kind, const char *name)
{
  double dur = amk_prof_now () - f->start;
  struct amk_prof_node key, *node;
  void **slot;
  char *k = xmalloc (strlen (kind) + strlen (name) + 2);

  amk_prof_top = f->up;
  if (amk_prof_top)
    amk_prof_top->child += dur;
  sprintf (k, "%s %s", kind, name);
  key.key = k;
  slot = hash_find_slot (&amk_prof_table, &key);
  node = *slot;
  if (HASH_VACANT (node))
    {
      node = xcalloc (sizeof *node);
      node->key = k;
      hash_insert_at (&amk_prof_table, node, slot);
    }
  else
    free (k);
  node->count++;
  node->total += dur;
  node->self += dur - f->child;
}

static int
amk_prof_order (const void *a, const void *b)
{
  const struct amk_prof_node *x = *(const struct amk_prof_node *const *) a;
  const struct amk_prof_node *y = *(const struct amk_prof_node *const *) b;
  return x->self < y->self ? 1 : x->self > y->self ? -1 : 0;
}

/* Writes the table, every name by self time descending, with the process wall and pid on its header line.  */
void
amk_profile_report (void)
{
  const char *path;
  FILE *out;
  void **v, **p;

  if (amk_profile_on <= 0)
    return;
  path = getenv ("AMK_PROFILE");
  out = strcmp (path, "-") == 0 ? stderr : fopen (path, "a");
  if (out == NULL)
    return;
  v = xmalloc (sizeof (void *) * (amk_prof_table.ht_fill + 1));
  hash_dump (&amk_prof_table, v, amk_prof_order);
  fprintf (out, "# amk profile pid=%ld wall=%.3fs names=%lu\n", (long) getpid (), amk_prof_now () - amk_prof_start, amk_prof_table.ht_fill);
  fprintf (out, "%10s %10s %8s  %s\n", "self_ms", "total_ms", "count", "name");
  for (p = v; *p != NULL; ++p)
    {
      const struct amk_prof_node *n = *p;
      fprintf (out, "%10.3f %10.3f %8lu  %s\n", n->self * 1e3, n->total * 1e3, n->count, n->key);
    }
  if (out != stderr)
    fclose (out);
  free (v);
}

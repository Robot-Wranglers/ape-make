/* The payload: booting into its entry script, unpacking and listing its members, putting its tools on PATH, and bundling a makefile program into a copy of the binary.  */

#include "makeint.h"
#include "filedef.h"
#include "variable.h"
#include <fcntl.h>
#include "amk.h"

/* Payload boot: a distribution appends its own entry program to the binary and
   this hands control to it, so the engine learns one member name and nothing
   about whatever framework rides on top.  */

#ifdef __COSMOPOLITAN__
#include <cosmo.h>

#define AMK_ENTRY "/zip/__main__."

/* The engine and path of the payload's entry: the first member named for an extension that a row claims and can run as a file; an empty member is a payload that does not want to boot.  */
static const struct amk_engine *
amk_payload_entry (char *path, size_t size)
{
  const struct amk_engine *e;
  struct stat st;
  for (e = amk_engines; e->name; ++e)
    {
      const char *p = e->name;
      if (e->cli->argv && !e->cli->file)
        continue;
      while (p != NULL && *p)
        {
          size_t n = strcspn (p, " ");
          snprintf (path, size, "%s%.*s", AMK_ENTRY, (int) n, p);
          if (stat (path, &st) == 0 && st.st_size > 0)
            return e;
          p = p == e->name ? e->aliases : p + n + (p[n] == ' ');
        }
    }
  return NULL;
}

void
amk_payload_boot (int argc, char **argv)
{
  static char path[64];
  const struct amk_engine *e;
  char **av;
  int i, j, rc;

  /* Recursion routes back into this binary, so a child must not boot again.  */
  if (getenv ("AMK_BOOTED"))
    return;
  e = amk_payload_entry (path, sizeof path);
  if (e == NULL)
    return;
  /* A row that runs a file by exec reads it through a payload tool, which a bare PATH does not have.  */
  if (e->cli->file && getenv ("AMK_NO_PATH"))
    amk_warn ("AMK_NO_PATH is set, and the entry needs the payload's %s to read %s",
              e->name, path);

  /* The entry is the program and the caller's arguments follow it; a row that takes its program as text gets the member's text.  */
  av = xmalloc ((argc + 2) * sizeof *av);
  i = 0;
  av[i++] = (char *) e->name;
  av[i++] = path;
  for (j = 1; j < argc; ++j)
    av[i++] = argv[j];
  av[i] = NULL;
  if (!e->cli->argv)
    amk_program_from_stdin (e, i, av);
  rc = e->cli->main (i, av);
  if (e->cli->file)
    amk_warn ("the entry %s did not run", path);
  exit (rc);
}
#else
void
amk_payload_boot (int argc UNUSED, char **argv UNUSED)
{
}
#endif

/* Payload unpack: copy one payload member out to the host, so a distribution
   can hand a file it carries to a tool that only reads the filesystem.  */

#ifdef __COSMOPOLITAN__
static int
amk_unpack_fail (const char *what, const char *path)
{
  fprintf (stderr, "amk: --ape-unpack: %s: %s: %s\n", what, path,
           strerror (errno));
  return MAKE_FAILURE;
}

int
amk_ape_unpack (const char *name, const char *dest, int force)
{
  char *src, *tmp, *p;
  const char *base;
  char buf[1 << 16];
  struct stat st, have, self;
  int in, out, r;

  /* A member is named relative to the payload root and never climbs out.  */
  if (!name || !*name || name[0] == '/' || strstr (name, ".."))
    {
      fprintf (stderr, "amk: --ape-unpack: '%s' is not a payload-relative name\n",
               name ? name : "");
      return MAKE_FAILURE;
    }
  if (!dest || !*dest)
    dest = name;

  src = xmalloc (strlen (name) + 6);
  sprintf (src, "/zip/%s", name);
  EINTRLOOP (in, open (src, O_RDONLY));
  if (in < 0)
    return amk_unpack_fail ("no payload member", name);
  if (fstat (in, &st) < 0 || !S_ISREG (st.st_mode))
    {
      errno = EISDIR;
      return amk_unpack_fail ("not a regular member", name);
    }

  /* A copy at least as new as this binary already holds this payload.  */
  if (!force && stat (dest, &have) == 0
      && stat (GetProgramExecutableName (), &self) == 0
      && have.st_mtime >= self.st_mtime)
    {
      close (in);
      return MAKE_SUCCESS;
    }

  /* The scratch copy sits beside the destination, so the rename stays on one
     filesystem and a reader never sees a partial file.  */
  tmp = xmalloc (strlen (dest) + 32);
  base = strrchr (dest, '/');
  base = base ? base + 1 : dest;
  sprintf (tmp, "%.*s.tmp.%ld.%s", (int) (base - dest), dest,
           (long) getpid (), base);
  for (p = tmp + 1; *p; ++p)
    if (*p == '/')
      {
        *p = '\0';
        if (mkdir (tmp, 0777) < 0 && errno != EEXIST)
          return amk_unpack_fail ("mkdir", tmp);
        *p = '/';
      }

  EINTRLOOP (out, open (tmp, O_WRONLY | O_CREAT | O_TRUNC, 0600));
  if (out < 0)
    return amk_unpack_fail ("open", tmp);
  while (1)
    {
      ssize_t n, w, off = 0;
      EINTRLOOP (n, read (in, buf, sizeof buf));
      if (n == 0)
        break;
      while (n > 0 && off < n)
        {
          EINTRLOOP (w, write (out, buf + off, n - off));
          if (w < 0)
            break;
          off += w;
        }
      if (n < 0 || off < n)
        {
          amk_unpack_fail ("copy", tmp);
          unlink (tmp);
          return MAKE_FAILURE;
        }
    }
  close (in);
  /* The member's own mode rides along, so a script stays executable.  */
  fchmod (out, (st.st_mode & 0777) ? (st.st_mode & 0777) : 0644);
  close (out);

  EINTRLOOP (r, rename (tmp, dest));
  if (r < 0)
    {
      amk_unpack_fail ("rename", dest);
      unlink (tmp);
      return MAKE_FAILURE;
    }
  return MAKE_SUCCESS;
}

#include <dirent.h>

int
amk_walk_cmp (const void *a, const void *b)
{
  return strcmp (*(const char *const *) a, *(const char *const *) b);
}

/* Every regular file under the directory, each named with the directory as its prefix, appended to the list; the payload's members when the directory is under /zip.  */
void
amk_walk (const char *dir, char ***names, size_t *n, size_t *cap)
{
  DIR *d = opendir (dir);
  struct dirent *e;
  struct stat st;
  char *path;

  if (!d)
    return;
  while ((e = readdir (d)) != NULL)
    {
      if (strcmp (e->d_name, ".") == 0 || strcmp (e->d_name, "..") == 0)
        continue;
      path = xmalloc (strlen (dir) + strlen (e->d_name) + 2);
      sprintf (path, "%s/%s", dir, e->d_name);
      if (stat (path, &st) < 0)
        {
          free (path);
          continue;
        }
      if (S_ISDIR (st.st_mode))
        {
          amk_walk (path, names, n, cap);
          free (path);
          continue;
        }
      if (*n == *cap)
        {
          *cap = *cap ? *cap * 2 : 64;
          *names = xrealloc (*names, *cap * sizeof **names);
        }
      (*names)[(*n)++] = path;
    }
  closedir (d);
}

/* The payload's members, one per line, sorted, each spelled from the given offset into its path under /zip.  */
static int
amk_payload_list (const char *verb, size_t skip)
{
  char **names = NULL;
  size_t i, n = 0, cap = 0;
  struct stat st;

  if (stat ("/zip", &st) < 0)
    {
      fprintf (stderr, "amk: %s: this build carries no payload\n", verb);
      return MAKE_FAILURE;
    }
  amk_walk ("/zip", &names, &n, &cap);
  qsort (names, n, sizeof *names, amk_walk_cmp);
  for (i = 0; i < n; ++i)
    {
      puts (names[i] + skip);
      free (names[i]);
    }
  free (names);
  return MAKE_SUCCESS;
}

/* The members as --ape-unpack names them, relative to the payload's root.  */
int
amk_ape_list (void)
{
  return amk_payload_list ("--ape-list", 5);
}
#else
int
amk_ape_unpack (const char *name UNUSED, const char *dest UNUSED,
                int force UNUSED)
{
  fprintf (stderr, "amk: --ape-unpack: this build carries no payload\n");
  return MAKE_FAILURE;
}

int
amk_ape_list (void)
{
  fprintf (stderr, "amk: --ape-list: this build carries no payload\n");
  return MAKE_FAILURE;
}
#endif

/* Payload tools: every member under the payload's bin directory is unpacked
   into a cache keyed by this binary, and that directory goes first on PATH,
   so a recipe finds the tools the build carries without being told.  */

#ifdef __COSMOPOLITAN__
#include <dirent.h>

#define AMK_TOOLS_DIR "/zip/bin"

/* One engine name in the tools directory, a link that runs this binary under that name; a payload tool of the same name stays, and a link to a binary since moved is replaced.  */
static void
amk_payload_link (const char *dir, const char *name, size_t nl)
{
  const char *self = GetProgramExecutableName ();
  char *dest = xmalloc (strlen (dir) + nl + 2), have[PATH_MAX];
  ssize_t r;

  sprintf (dest, "%s/%.*s", dir, (int) nl, name);
  r = readlink (dest, have, sizeof have - 1);
  if (r >= 0)
    {
      have[r] = '\0';
      if (strcmp (have, self) != 0)
        unlink (dest);
    }
  if ((r >= 0 || errno == ENOENT) && symlink (self, dest) < 0 && errno != EEXIST)
    amk_warn ("the engine name %s did not link into %s: %s", dest + strlen (dir) + 1,
              dir, strerror (errno));
  free (dest);
}

/* Every name and alias of an engine whose command line is the tool's own.  */
static void
amk_payload_links (const char *dir)
{
  const struct amk_engine *e;
  for (e = amk_engines; e->name; ++e)
    {
      const char *p = e->aliases;
      if (e->cli == NULL || !e->cli->tool)
        continue;
      amk_payload_link (dir, e->name, strlen (e->name));
      while (p != NULL && *p)
        {
          size_t n = strcspn (p, " ");
          amk_payload_link (dir, p, n);
          p += n;
          while (*p == ' ')
            ++p;
        }
    }
}

static void
amk_payload_tools (void)
{
  const char *base, *sub, *path;
  char *dir, *name, *dest, *next;
  struct stat self;
  struct dirent *e;
  DIR *d;
  size_t n;

  if (getenv ("AMK_NO_PATH"))
    return;
  if (stat (GetProgramExecutableName (), &self) < 0)
    return;
  base = getenv ("XDG_CACHE_HOME");
  sub = "";
  if (!base || !*base)
    {
      base = getenv ("HOME");
      sub = "/.cache";
    }
  if (!base || !*base)
    {
      if (stat (AMK_TOOLS_DIR, &self) == 0)
        amk_warn ("no HOME and no XDG_CACHE_HOME, so the payload's tools are not unpacked and the host's are used");
      return;
    }

  /* The key changes with the binary, so an upgrade never runs a stale tool.  */
  dir = xmalloc (strlen (base) + 64);
  sprintf (dir, "%s%s/amk/%lld-%lld/bin", base, sub,
           (long long) self.st_size, (long long) self.st_mtime);

  /* A recursive make inherits the directory from its parent and stops here.  */
  path = getenv ("PATH");
  n = strlen (dir);
  if (path && strncmp (path, dir, n) == 0 && (path[n] == ':' || path[n] == '\0'))
    {
      free (dir);
      return;
    }

  d = opendir (AMK_TOOLS_DIR);
  if (!d)
    {
      free (dir);
      return;
    }
  while ((e = readdir (d)) != NULL)
    {
      int r;
      if (e->d_name[0] == '.')
        continue;
      name = xmalloc (strlen (e->d_name) + 5);
      dest = xmalloc (n + strlen (e->d_name) + 2);
      sprintf (name, "bin/%s", e->d_name);
      sprintf (dest, "%s/%s", dir, e->d_name);
      r = amk_ape_unpack (name, dest, 0);
      free (name);
      free (dest);
      /* A tool that failed to land leaves PATH alone rather than half set.  */
      if (r != MAKE_SUCCESS)
        {
          amk_warn ("the payload's tools did not unpack into %s, so the host's are used",
                    dir);
          closedir (d);
          free (dir);
          return;
        }
    }
  closedir (d);
  amk_payload_links (dir);

  next = xmalloc (n + (path ? strlen (path) : 0) + 2);
  sprintf (next, "%s%s%s", dir, path && *path ? ":" : "", path ? path : "");
  setenv ("PATH", next, 1);
  free (next);
  free (dir);
}

/* A module path the caller set for micropython keeps the payload's modules after it, since that tool reads the variable in place of its default path.  */
static void
amk_payload_modules (void)
{
#ifdef AMK_ENGINE_MICROPY
  static const char lib[] = ":/zip/lib/micropy";
  const char *path = getenv ("MICROPYPATH");
  size_t n = path != NULL ? strlen (path) : 0;
  char *next;

  if (n == 0 || (n >= sizeof lib - 1 && strcmp (path + n - (sizeof lib - 1), lib) == 0))
    return;
  next = xmalloc (n + sizeof lib);
  memcpy (next, path, n);
  memcpy (next + n, lib, sizeof lib);
  setenv ("MICROPYPATH", next, 1);
  free (next);
#endif
}

/* A cosmo child maps the file this names as its own /zip, so a payload tool reads this payload in place; an inherited name goes before the first read of /zip, and the new one follows the change to PATH because it moves the environment main holds.  */
void
amk_payload_path (void)
{
  unsetenv ("COSMOPOLITAN_INIT_ZIPOS");
  amk_payload_tools ();
  amk_payload_modules ();
  setenv ("COSMOPOLITAN_INIT_ZIPOS", GetProgramExecutableName (), 1);
}
#else
void
amk_payload_path (void)
{
}
#endif

/* The name set at startup is new to the environment make already read, so it becomes an exported variable for recipes to inherit.  */
void
amk_payload_init (void)
{
  const char *zip = getenv ("COSMOPOLITAN_INIT_ZIPOS");
  if (zip && *zip)
    define_variable_global ("COSMOPOLITAN_INIT_ZIPOS", 23, zip, o_env, 0, NILF)->export = v_export;
}

/* Payload bundle: write a copy of this binary whose payload carries a makefile
   program, and run that program when the caller names no makefile.  */

#define AMK_MAIN_MK "/zip/__main__.mk"

#ifdef __COSMOPOLITAN__
#include <sys/file.h>
#include "third_party/zlib/zlib.h"

struct amk_member
{
  const char *name;
  unsigned char *data;
  size_t len;
  unsigned long crc, off;
  unsigned int mode, dostime, dosdate;
};

/* The flag a failure names, since bundle and unbundle share their zip code.  */
static const char *amk_bundle_verb = "--bundle";

static int
amk_bundle_fail (const char *what, const char *path)
{
  fprintf (stderr, "amk: %s: %s: %s: %s\n", amk_bundle_verb, what, path,
           strerror (errno));
  return MAKE_FAILURE;
}

static void
amk_put16 (unsigned char *p, unsigned int v)
{
  p[0] = v & 0xff;
  p[1] = (v >> 8) & 0xff;
}

static void
amk_put32 (unsigned char *p, unsigned long v)
{
  amk_put16 (p, v & 0xffff);
  amk_put16 (p + 2, (v >> 16) & 0xffff);
}

static unsigned int
amk_get16 (const unsigned char *p)
{
  return p[0] | (p[1] << 8);
}

static unsigned long
amk_get32 (const unsigned char *p)
{
  return amk_get16 (p) | ((unsigned long) amk_get16 (p + 2) << 16);
}

unsigned char *
amk_slurp (const char *path, size_t *len)
{
  unsigned char *buf;
  size_t cap = 1 << 16;
  int fd;

  EINTRLOOP (fd, open (path, O_RDONLY));
  if (fd < 0)
    return NULL;
  buf = xmalloc (cap);
  *len = 0;
  while (1)
    {
      ssize_t r;
      if (*len == cap)
        {
          cap *= 2;
          buf = xrealloc (buf, cap);
        }
      EINTRLOOP (r, read (fd, buf + *len, cap - *len));
      if (r < 0)
        {
          close (fd);
          free (buf);
          return NULL;
        }
      if (r == 0)
        break;
      *len += (size_t) r;
    }
  close (fd);
  return buf;
}

struct amk_members
{
  struct amk_member *m;
  int n, cap;
};

static int amk_bundle_walk (struct amk_members *s, const char *dir,
                            const char *name);

/* Add a file under its member name, or every file under a directory, and let a
   later name replace an earlier one rather than appear twice.  */
static int
amk_bundle_add (struct amk_members *s, const char *path, const char *name)
{
  struct amk_member *mb;
  struct stat st;
  struct tm *t;
  int i;

  while (name[0] == '.' && name[1] == '/')
    name += 2;
  if (name[0] == '/' || strstr (name, ".."))
    {
      fprintf (stderr, "amk: --bundle: '%s' is not a relative name\n", name);
      return MAKE_FAILURE;
    }
  if (stat (path, &st) < 0)
    return amk_bundle_fail ("stat", path);
  if (S_ISDIR (st.st_mode))
    {
      char *dir = xstrdup (name);
      size_t len = strlen (dir);
      while (len > 0 && dir[len - 1] == '/')
        dir[--len] = '\0';
      if (strcmp (dir, ".") == 0)
        dir[0] = '\0';
      return amk_bundle_walk (s, path, dir);
    }
  if (!S_ISREG (st.st_mode) || !*name)
    {
      errno = EINVAL;
      return amk_bundle_fail ("not a regular file", path);
    }

  for (i = 0; i < s->n; ++i)
    if (strcmp (s->m[i].name, name) == 0)
      break;
  if (i == s->n)
    {
      if (s->n == s->cap)
        {
          s->cap = s->cap ? s->cap * 2 : 16;
          s->m = xrealloc (s->m, s->cap * sizeof *s->m);
        }
      ++s->n;
    }
  mb = &s->m[i];
  memset (mb, 0, sizeof *mb);
  mb->name = name;
  mb->data = amk_slurp (path, &mb->len);
  if (!mb->data)
    return amk_bundle_fail ("read", path);
  mb->crc = crc32 (0L, mb->data, (uInt) mb->len);
  mb->mode = st.st_mode & 0777;
  t = localtime (&st.st_mtime);
  if (t && t->tm_year >= 80)
    {
      mb->dostime = (t->tm_hour << 11) | (t->tm_min << 5) | (t->tm_sec / 2);
      mb->dosdate = ((t->tm_year - 80) << 9) | ((t->tm_mon + 1) << 5)
                    | t->tm_mday;
    }
  else
    mb->dosdate = (1 << 5) | 1;
  return MAKE_SUCCESS;
}

/* Dot entries are skipped and a symlinked directory is not followed, so a link
   cycle cannot recurse.  */
static int
amk_bundle_walk (struct amk_members *s, const char *dir, const char *name)
{
  struct dirent *e;
  DIR *d;
  int r = MAKE_SUCCESS;

  d = opendir (dir);
  if (!d)
    return amk_bundle_fail ("opendir", dir);
  while (r == MAKE_SUCCESS && (e = readdir (d)) != NULL)
    {
      struct stat ls;
      char *path, *sub;
      if (e->d_name[0] == '.')
        continue;
      path = xmalloc (strlen (dir) + strlen (e->d_name) + 2);
      sub = xmalloc (strlen (name) + strlen (e->d_name) + 2);
      sprintf (path, "%s/%s", dir, e->d_name);
      sprintf (sub, "%s%s%s", name, *name ? "/" : "", e->d_name);
      if (lstat (path, &ls) == 0 && S_ISLNK (ls.st_mode)
          && stat (path, &ls) == 0 && S_ISDIR (ls.st_mode))
        {
          free (path);
          free (sub);
          continue;
        }
      r = amk_bundle_add (s, path, sub);
      free (path);
    }
  closedir (d);
  return r;
}

/* The end record's counts for this binary's zip, or a failure when it is not a plain one.  */
static int
amk_zip_end (unsigned char *self, size_t selflen, size_t *entries,
             size_t *cdsize, size_t *cdoff)
{
  unsigned char *eocd = NULL, *q;

  for (q = self + selflen - 22; selflen >= 22 && q >= self; --q)
    {
      if (amk_get32 (q) == 0x06054b50)
        {
          eocd = q;
          break;
        }
      if ((size_t) (self + selflen - q) > 22 + 0xffff)
        break;
    }
  if (!eocd)
    {
      errno = EINVAL;
      return amk_bundle_fail ("no zip end record", GetProgramExecutableName ());
    }
  *entries = amk_get16 (eocd + 10);
  *cdsize = amk_get32 (eocd + 12);
  *cdoff = amk_get32 (eocd + 16);
  /* Only a plain end record is rewritten; zip64 and split archives stop here.  */
  if (*entries == 0xffff || *cdoff == 0xffffffff
      || *cdoff + *cdsize > (size_t) (eocd - self))
    {
      errno = ENOTSUP;
      return amk_bundle_fail ("unsupported zip layout",
                              GetProgramExecutableName ());
    }
  return MAKE_SUCCESS;
}

/* The member name an entry file takes: the makefile entry for a makefile, else the entry of the engine that claims the file's extension and can run it as a file.  */
static const char *
amk_bundle_entry (const char *file)
{
  static char entry[80];
  const char *base = strrchr (file, '/');
  const char *ext = strrchr (base != NULL ? base : file, '.');
  const struct amk_engine *e = ext != NULL ? amk_engine_by_extension (ext + 1) : NULL;

  if (ext != NULL && (strcmp (ext, ".mk") == 0 || strcmp (ext, ".amk") == 0))
    return "__main__.mk";
  if (e == NULL || (e->cli->argv && !e->cli->file) || strlen (ext) + 9 > sizeof entry)
    {
      fprintf (stderr, "amk: --bundle-main: %s: no engine runs this extension as an entry; the extensions are %s\n",
               file, amk_engine_extensions ());
      return NULL;
    }
  sprintf (entry, "__main__%s", ext);
  return entry;
}

static int amk_payload_rewrite (struct amk_members *set, int n, char **names,
                                int all, const char *out);

static int
amk_bundle (int n, char **files, int by_engine, const char *out)
{
  struct amk_members set = { NULL, 0, 0 };
  const char *entry = "__main__.mk";
  int i;

  if (n < 1)
    {
      fprintf (stderr, "amk: %s: names no %s\n", amk_bundle_verb, by_engine ? "entry" : "makefile");
      return MAKE_FAILURE;
    }
  if (!out || !*out)
    {
      fprintf (stderr, "amk: %s: names no --out\n", amk_bundle_verb);
      return MAKE_FAILURE;
    }
  if (by_engine && (entry = amk_bundle_entry (files[0])) == NULL)
    return MAKE_FAILURE;

  /* The first file is the entry; the rest keep their names under the root.  */
  {
    struct stat st;
    if (stat (files[0], &st) == 0 && !S_ISREG (st.st_mode))
      {
        errno = EISDIR;
        return amk_bundle_fail ("the entry must be a file", files[0]);
      }
  }
  for (i = 0; i < n; ++i)
    if (amk_bundle_add (&set, files[i], i == 0 ? entry : files[i])
        != MAKE_SUCCESS)
      return MAKE_FAILURE;
  return amk_payload_rewrite (&set, 0, NULL, 0, out);
}

/* Payload rewrite: one writer behind every verb that changes the payload, so
   each of them replaces, removes and closes the space the same way.  */

struct amk_entry
{
  unsigned char *rec;
  size_t reclen, nl, off, end, newoff;
  int drop, own;
};

static int
amk_entry_cmp (const void *a, const void *b)
{
  const struct amk_entry *x = *(const struct amk_entry *const *) a;
  const struct amk_entry *y = *(const struct amk_entry *const *) b;
  return x->off < y->off ? -1 : x->off > y->off;
}

/* The linker's members sit inside the program image: a dot name, or the zone database.  */
static int
amk_entry_own (const unsigned char *name, size_t nl)
{
  return (nl > 0 && name[0] == '.') || (nl >= 4 && memcmp (name, "usr/", 4) == 0);
}

/* An entry besides the makefile's: a member named for some engine's extension.  */
static int
amk_entry_boots (const unsigned char *name, size_t nl)
{
  return nl > 9 && memcmp (name, "__main__.", 9) == 0 && !(nl == 11 && memcmp (name + 9, "mk", 2) == 0);
}

/* The named members and everything under them leave, or every member a strip takes; the set's members land, each replacing one of its name; what is left moves up over the space the departed held.  */
static int
amk_payload_rewrite (struct amk_members *set, int n, char **names, int all, const char *out)
{
  struct amk_entry *ent, **byoff;
  struct amk_member *add = set != NULL ? set->m : NULL;
  unsigned char *self, *q, hdr[46];
  size_t selflen, cdoff, cdsize, entries, pos, cdstart, kept = 0, fixed = 0, e;
  const char *base;
  char *tmp;
  int adds = set != NULL ? set->n : 0;
  int fd, r, i, reported = 0, turn = -1;
  struct stat held, named;

  /* A rewrite of this binary itself waits its turn before it reads: the lock is on the file, and the writer ahead put a new file under the name, so the name is checked against the file once the wait ends.  */
  while (stat (out, &named) == 0 && stat (GetProgramExecutableName (), &held) == 0
         && named.st_dev == held.st_dev && named.st_ino == held.st_ino)
    {
      EINTRLOOP (turn, open (out, O_RDONLY));
      if (turn < 0)
        return amk_bundle_fail ("open", out);
      EINTRLOOP (r, flock (turn, LOCK_EX));
      if (r < 0)
        return amk_bundle_fail ("lock", out);
      if (fstat (turn, &held) == 0 && stat (out, &named) == 0
          && named.st_dev == held.st_dev && named.st_ino == held.st_ino)
        break;
      close (turn);
      turn = -1;
    }

  /* A rename needs only the directory, so the binary's own protection is asked about here; a file of another user's comes back as the writer's own, which is said and not refused.  */
  if (turn >= 0)
    {
      if (access (out, W_OK) < 0)
        {
          fprintf (stderr, "amk: %s: cannot rewrite %s in place: %s\n", amk_bundle_verb, out, strerror (errno));
          return MAKE_FAILURE;
        }
      if (held.st_uid != geteuid ())
        amk_warn ("%s belongs to another user, and the rewritten file will belong to you", out);
    }

  self = amk_slurp (turn >= 0 ? out : GetProgramExecutableName (), &selflen);
  if (!self)
    return amk_bundle_fail ("read", GetProgramExecutableName ());
  if (amk_zip_end (self, selflen, &entries, &cdsize, &cdoff) != MAKE_SUCCESS)
    return MAKE_FAILURE;

  ent = xcalloc ((entries + 1) * sizeof *ent);
  byoff = xcalloc ((entries + 1) * sizeof *byoff);
  for (q = self + cdoff, e = 0; e < entries; ++e)
    {
      if (q + 46 > self + cdoff + cdsize || amk_get32 (q) != 0x02014b50)
        {
          errno = EINVAL;
          return amk_bundle_fail ("damaged central directory",
                                  GetProgramExecutableName ());
        }
      ent[e].rec = q;
      ent[e].nl = amk_get16 (q + 28);
      ent[e].reclen = 46 + ent[e].nl + amk_get16 (q + 30) + amk_get16 (q + 32);
      ent[e].off = amk_get32 (q + 42);
      ent[e].own = amk_entry_own (q + 46, ent[e].nl);
      /* A strip keeps the tools beside the program's own members.  */
      ent[e].drop = all && !ent[e].own
                    && !(ent[e].nl >= 4 && memcmp (q + 46, "bin/", 4) == 0);
      if (ent[e].off + 30 > cdoff || amk_get32 (self + ent[e].off) != 0x04034b50)
        {
          errno = EINVAL;
          return amk_bundle_fail ("damaged member record",
                                  GetProgramExecutableName ());
        }
      byoff[e] = &ent[e];
      q += ent[e].reclen;
    }

  /* Each name takes the member it spells and every member under it as a directory.  */
  for (i = 0; i < n; ++i)
    {
      const char *nm = names[i];
      size_t len, hits = 0;
      /* A member is named as the listing prints it, under /zip, or from the payload's root.  */
      if (strncmp (nm, "/zip/", 5) == 0)
        nm += 5;
      while (nm[0] == '.' && nm[1] == '/')
        nm += 2;
      len = strlen (nm);
      while (len > 0 && nm[len - 1] == '/')
        --len;
      if (len == 0 || nm[0] == '/' || strstr (nm, ".."))
        {
          fprintf (stderr, "amk: %s: '%s' is not a payload name\n", amk_bundle_verb,
                   names[i]);
          return MAKE_FAILURE;
        }
      for (e = 0; e < entries; ++e)
        {
          const unsigned char *have = ent[e].rec + 46;
          if (ent[e].nl < len || memcmp (have, nm, len) != 0
              || (ent[e].nl > len && have[len] != '/'))
            continue;
          if (ent[e].own)
            {
              fprintf (stderr, "amk: %s: '%s' belongs to the program itself\n",
                       amk_bundle_verb, names[i]);
              return MAKE_FAILURE;
            }
          ent[e].drop = 1;
          ++hits;
        }
      if (hits == 0)
        {
          errno = ENOENT;
          return amk_bundle_fail ("no payload member", names[i]);
        }
    }

  /* A member that lands replaces the one of its name, and a payload holds one entry besides the makefile's.  */
  for (i = 0; i < adds; ++i)
    {
      size_t nl = strlen (add[i].name);
      if (amk_entry_own ((const unsigned char *) add[i].name, nl))
        {
          fprintf (stderr, "amk: %s: '%s' belongs to the program itself\n",
                   amk_bundle_verb, add[i].name);
          return MAKE_FAILURE;
        }
      for (e = 0; e < entries; ++e)
        {
          const unsigned char *have = ent[e].rec + 46;
          if (ent[e].nl == nl && memcmp (have, add[i].name, nl) == 0)
            ent[e].drop = 1;
          else if (!ent[e].drop && amk_entry_boots ((const unsigned char *) add[i].name, nl)
                   && amk_entry_boots (have, ent[e].nl))
            {
              errno = EEXIST;
              return amk_bundle_fail ("the payload already has an entry, which --bundle-rm removes",
                                      xstrndup ((const char *) have, ent[e].nl));
            }
        }
    }

  /* A member's bytes run to the next member's record, and nothing at or below the linker's last member moves.  */
  qsort (byoff, entries, sizeof *byoff, amk_entry_cmp);
  for (e = 0; e < entries; ++e)
    {
      byoff[e]->end = e + 1 < entries ? byoff[e + 1]->off : cdoff;
      if (byoff[e]->own && byoff[e]->end > fixed)
        fixed = byoff[e]->end;
    }

  tmp = xmalloc (strlen (out) + 32);
  base = strrchr (out, '/');
  base = base ? base + 1 : out;
  sprintf (tmp, "%.*s.tmp.%ld.%s", (int) (base - out), out, (long) getpid (),
           base);
  EINTRLOOP (fd, open (tmp, O_WRONLY | O_CREAT | O_TRUNC, 0755));
  if (fd < 0)
    {
      /* The result is written beside the destination, so the failure is the directory's, and the message names what was asked for.  */
      fprintf (stderr, "amk: %s: cannot write %s: its directory takes no new file: %s\n",
               amk_bundle_verb, out, strerror (errno));
      return MAKE_FAILURE;
    }

  pos = entries ? byoff[0]->off : cdoff;
  if (amk_write_all (fd, self, pos) < 0)
    goto fail;
  for (e = 0; e < entries; ++e)
    {
      struct amk_entry *m = byoff[e];
      if (m->drop && m->off >= fixed)
        continue;
      if (amk_write_all (fd, self + m->off, m->end - m->off) < 0)
        goto fail;
      m->newoff = pos;
      pos += m->end - m->off;
    }
  for (i = 0; i < adds; ++i)
    {
      size_t nl = strlen (add[i].name);
      memset (hdr, 0, 30);
      amk_put32 (hdr, 0x04034b50);
      amk_put16 (hdr + 4, 20);
      amk_put16 (hdr + 10, add[i].dostime);
      amk_put16 (hdr + 12, add[i].dosdate);
      amk_put32 (hdr + 14, add[i].crc);
      amk_put32 (hdr + 18, add[i].len);
      amk_put32 (hdr + 22, add[i].len);
      amk_put16 (hdr + 26, nl);
      add[i].off = pos;
      if (amk_write_all (fd, hdr, 30) < 0
          || amk_write_all (fd, add[i].name, nl) < 0
          || amk_write_all (fd, add[i].data, add[i].len) < 0)
        goto fail;
      pos += 30 + nl + add[i].len;
    }

  cdstart = pos;
  for (e = 0; e < entries; ++e)
    {
      if (ent[e].drop)
        continue;
      amk_put32 (ent[e].rec + 42, ent[e].newoff);
      if (amk_write_all (fd, ent[e].rec, ent[e].reclen) < 0)
        goto fail;
      pos += ent[e].reclen;
      ++kept;
    }
  for (i = 0; i < adds; ++i)
    {
      size_t nl = strlen (add[i].name);
      memset (hdr, 0, 46);
      amk_put32 (hdr, 0x02014b50);
      amk_put16 (hdr + 4, (3 << 8) | 30);
      amk_put16 (hdr + 6, 20);
      amk_put16 (hdr + 12, add[i].dostime);
      amk_put16 (hdr + 14, add[i].dosdate);
      amk_put32 (hdr + 16, add[i].crc);
      amk_put32 (hdr + 20, add[i].len);
      amk_put32 (hdr + 24, add[i].len);
      amk_put16 (hdr + 28, nl);
      amk_put32 (hdr + 38, (unsigned long) (S_IFREG | add[i].mode) << 16);
      amk_put32 (hdr + 42, add[i].off);
      if (amk_write_all (fd, hdr, 46) < 0
          || amk_write_all (fd, add[i].name, nl) < 0)
        goto fail;
      pos += 46 + nl;
      ++kept;
    }
  if (pos > 0xffffffffUL || kept > 0xfffe)
    {
      errno = EFBIG;
      reported = amk_bundle_fail ("too large for a plain zip", out);
      goto fail;
    }
  memset (hdr, 0, 22);
  amk_put32 (hdr, 0x06054b50);
  amk_put16 (hdr + 8, kept);
  amk_put16 (hdr + 10, kept);
  amk_put32 (hdr + 12, pos - cdstart);
  amk_put32 (hdr + 16, cdstart);
  if (amk_write_all (fd, hdr, 22) < 0)
    goto fail;
  fchmod (fd, turn >= 0 ? held.st_mode & 0777 : 0755);
  /* The new file reaches the disk before it takes the name, so a crash leaves the old binary or the whole new one.  */
  EINTRLOOP (r, fsync (fd));
  if (r < 0)
    goto fail;
  close (fd);

  EINTRLOOP (r, rename (tmp, out));
  if (r < 0)
    {
      amk_bundle_fail ("rename", out);
      unlink (tmp);
      return MAKE_FAILURE;
    }
  /* The name's own change is in the directory, which is flushed where the system lets a directory be.  */
  sprintf (tmp, "%.*s", (int) (base - out), out);
  EINTRLOOP (fd, open (*tmp ? tmp : ".", O_RDONLY));
  if (fd >= 0)
    {
      fsync (fd);
      close (fd);
    }
  if (turn >= 0)
    close (turn);
  return MAKE_SUCCESS;

 fail:
  if (!reported)
    amk_bundle_fail ("write", tmp);
  close (fd);
  unlink (tmp);
  return MAKE_FAILURE;
}

/* Payload verbs: the payload as a small filesystem, listed, copied into and out of, and removed from, by the flags that begin with the bundle word.  */

/* The last word of a path, trailing slashes aside, as a new string.  */
static char *
amk_path_base (const char *path)
{
  size_t len = strlen (path);
  const char *p;
  while (len > 1 && path[len - 1] == '/')
    --len;
  for (p = path + len; p > path && p[-1] != '/'; --p)
    ;
  return xstrndup (p, len - (p - path));
}

/* Whether a word names the payload's side of a copy: /zip or a path under it.  */
static int
amk_path_zip (const char *path)
{
  return strncmp (path, "/zip", 4) == 0 && (path[4] == '/' || path[4] == '\0');
}

/* Where one source of a copy lands under a destination: at the destination itself when it is the only source, and under its own last word when there are several or when a lone file is copied into a name that ends in a slash.  */
static char *
amk_copy_name (const char *dest, const char *src, int several, int is_dir)
{
  size_t len = strlen (dest);
  int into = several || (!is_dir && (len == 0 || dest[len - 1] == '/'));
  char *base, *name;
  while (len > 0 && dest[len - 1] == '/')
    --len;
  if (!into)
    return xstrndup (dest, len);
  base = amk_path_base (src);
  name = xmalloc (len + strlen (base) + 2);
  sprintf (name, "%.*s%s%s", (int) len, dest, len ? "/" : "", base);
  free (base);
  return name;
}

/* Host files and directories into the payload, under the destination past its /zip.  */
static int
amk_copy_in (int n, char **srcs, const char *dest, const char *out)
{
  struct amk_members set = { NULL, 0, 0 };
  int i;
  dest += 4;
  while (*dest == '/')
    ++dest;
  for (i = 0; i < n; ++i)
    {
      struct stat st;
      if (amk_path_zip (srcs[i]))
        {
          fprintf (stderr, "amk: --bundle-cp: '%s' and the destination are both in the payload\n", srcs[i]);
          return MAKE_FAILURE;
        }
      if (stat (srcs[i], &st) < 0)
        return amk_bundle_fail ("stat", srcs[i]);
      if (amk_bundle_add (&set, srcs[i], amk_copy_name (dest, srcs[i], n > 1, S_ISDIR (st.st_mode)))
          != MAKE_SUCCESS)
        return MAKE_FAILURE;
    }
  return amk_payload_rewrite (&set, 0, NULL, 0, out);
}

/* Payload members and directories out to the host, each file by the unpack every member takes.  */
static int
amk_copy_out (int n, char **srcs, const char *dest)
{
  struct stat st;
  int i, dest_dir = stat (dest, &st) == 0 && S_ISDIR (st.st_mode);
  for (i = 0; i < n; ++i)
    {
      char **names = NULL, *to;
      size_t k, count = 0, cap = 0, root = strlen (srcs[i]);
      int is_dir;
      if (!amk_path_zip (srcs[i]) || amk_path_zip (dest))
        {
          fprintf (stderr, "amk: --bundle-cp: one side of the copy is under /zip and the other is not\n");
          return MAKE_FAILURE;
        }
      while (root > 4 && srcs[i][root - 1] == '/')
        --root;
      if (stat (srcs[i], &st) < 0)
        {
          errno = ENOENT;
          return amk_bundle_fail ("no payload member", srcs[i]);
        }
      is_dir = S_ISDIR (st.st_mode);
      to = amk_copy_name (dest, srcs[i], n > 1 || (!is_dir && dest_dir), is_dir);
      if (!is_dir)
        {
          if (amk_ape_unpack (srcs[i] + 5, to, 1) != MAKE_SUCCESS)
            return MAKE_FAILURE;
          continue;
        }
      amk_walk (xstrndup (srcs[i], root), &names, &count, &cap);
      for (k = 0; k < count; ++k)
        {
          char *file = xmalloc (strlen (to) + strlen (names[k]) + 2);
          sprintf (file, "%s%s", to, names[k] + root);
          if (amk_ape_unpack (names[k] + 5, file, 1) != MAKE_SUCCESS)
            return MAKE_FAILURE;
        }
    }
  return MAKE_SUCCESS;
}

/* A flag that begins with the bundle word is one of the payload's verbs: its status, or a negative number for any other word.  A verb that writes names its result, a new file or this binary in place, and prints that path.  */
int
amk_payload_verb (int argc, char **argv)
{
  static const char *const verbs[] = { "--bundle", "--bundle-main", "--bundle-ls", "--bundle-cp", "--bundle-rm", "--bundle-strip", NULL };
  const char *verb = argv[1], *out = NULL;
  char **words = xmalloc (argc * sizeof *words);
  int i, n = 0, in_place = 0, writes, r;

  for (i = 0; verbs[i] != NULL && strcmp (verbs[i], verb) != 0; ++i)
    ;
  if (verbs[i] == NULL)
    return -1;
  amk_bundle_verb = verb;
  for (i = 2; i < argc; ++i)
    if (strcmp (argv[i], "--out") == 0 && i + 1 < argc)
      out = argv[++i];
    else if (strncmp (argv[i], "--out=", 6) == 0)
      out = argv[i] + 6;
    else if (strcmp (argv[i], "--in-place") == 0)
      in_place = 1;
    else
      words[n++] = argv[i];

  if (strcmp (verb, "--bundle-ls") == 0)
    return amk_payload_list (verb, 0);
  writes = strcmp (verb, "--bundle-cp") != 0 || (n >= 2 && amk_path_zip (words[n - 1]));
  if (writes ? (out != NULL && *out) == in_place : (out != NULL || in_place))
    {
      fprintf (stderr, "amk: %s: %s\n", verb,
               writes ? "names one of --out DEST and --in-place" : "a copy out of the payload takes neither --out nor --in-place");
      return MAKE_FAILURE;
    }
  if (in_place)
    out = GetProgramExecutableName ();

  if (strcmp (verb, "--bundle-cp") == 0)
    {
      if (n < 2)
        {
          fprintf (stderr, "amk: %s: names a source and a destination, one of them under /zip\n", verb);
          return MAKE_FAILURE;
        }
      r = writes ? amk_copy_in (n - 1, words, words[n - 1], out) : amk_copy_out (n - 1, words, words[n - 1]);
    }
  else if (strcmp (verb, "--bundle-rm") == 0 || strcmp (verb, "--bundle-strip") == 0)
    {
      int all = verb[9] == 's';
      if (all ? n > 0 : n < 1)
        {
          fprintf (stderr, "amk: %s: %s\n", verb, all ? "takes no member names" : "names no member");
          return MAKE_FAILURE;
        }
      r = amk_payload_rewrite (NULL, n, words, all, out);
    }
  else
    r = amk_bundle (n, words, verb[8] != '\0', out);
  if (r == MAKE_SUCCESS && writes)
    puts (out);
  return r;
}

/* A bundle runs its program when the caller names no makefile of their own.  */
void
amk_payload_main (int *argcp, char ***argvp)
{
  int argc = *argcp, i, j;
  char **argv = *argvp, **av;
  struct stat st;

  if (stat (AMK_MAIN_MK, &st) < 0)
    return;
  for (i = 1; i < argc; ++i)
    {
      const char *tok = argv[i], *p;
      if (strcmp (tok, "--") == 0)
        break;
      if (tok[0] != '-' || tok[1] == '\0')
        continue;
      if (tok[1] == '-')
        {
          size_t len = strcspn (tok + 2, "=");
          if ((len >= 1 && strncmp (tok + 2, "file", len) == 0 && len <= 4)
              || (len >= 3 && strncmp (tok + 2, "makefile", len) == 0
                  && len <= 8))
            return;
          continue;
        }
      for (p = tok + 1; *p; ++p)
        {
          if (*p == 'f')
            return;
          if (strchr ("CEIWo", *p))
            {
              if (p[1] == '\0')
                ++i;
              break;
            }
        }
    }

  av = xmalloc ((argc + 5) * sizeof *av);
  av[0] = argv[0];
  av[1] = (char *) "-f";
  av[2] = (char *) AMK_MAIN_MK;
  av[3] = (char *) "-I";
  av[4] = (char *) "/zip";
  for (j = 1; j <= argc; ++j)
    av[j + 4] = argv[j];
  *argcp = argc + 4;
  *argvp = av;
}
#else
int
amk_payload_verb (int argc UNUSED, char **argv)
{
  if (strncmp (argv[1], "--bundle", 8) != 0)
    return -1;
  fprintf (stderr, "amk: %s: this build carries no payload\n", argv[1]);
  return MAKE_FAILURE;
}

void
amk_payload_main (int *argcp UNUSED, char ***argvp UNUSED)
{
}
#endif

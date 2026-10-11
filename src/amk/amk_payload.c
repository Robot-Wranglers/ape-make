/* The payload: booting into its entry script, unpacking and listing its members, putting its tools on PATH, and bundling a makefile program into a copy of the binary.  */

#include "makeint.h"
#include <fcntl.h>
#include "amk.h"

/* Payload boot: a distribution appends its own entry script to the binary and
   this hands control to it, so the engine learns one filename and nothing about
   whatever framework rides on top.  */

#ifdef __COSMOPOLITAN__
#include <cosmo.h>

#define AMK_BOOT_SCRIPT "/zip/__main__.sh"

void
amk_payload_boot (int argc, char **argv)
{
  char *script, **av;
  size_t len = 0, cap = 1 << 16;
  int fd, i, j;

  /* Recursion routes back into this binary, so a child must not boot again.  */
  if (getenv ("AMK_BOOTED"))
    return;
  EINTRLOOP (fd, open (AMK_BOOT_SCRIPT, O_RDONLY));
  if (fd < 0)
    return;
  script = xmalloc (cap + 1);
  while (1)
    {
      ssize_t r;
      if (len == cap)
        {
          cap *= 2;
          script = xrealloc (script, cap + 1);
        }
      EINTRLOOP (r, read (fd, script + len, cap - len));
      if (r < 0)
        {
          close (fd);
          free (script);
          return;
        }
      if (r == 0)
        break;
      len += (size_t) r;
    }
  close (fd);
  script[len] = '\0';
  /* An empty script is a payload that does not want to boot; do not spawn.  */
  if (len == 0)
    {
      free (script);
      return;
    }

  /* The absolute self path becomes the script's argument zero, so it can read
     its own payload after a directory change, and the caller's arguments
     follow it.  */
  av = xmalloc ((argc + 4) * sizeof *av);
  i = 0;
  av[i++] = (char *) "bash";
  av[i++] = (char *) "-c";
  av[i++] = script;
  av[i++] = (char *) GetProgramExecutableName ();
  for (j = 1; j < argc; ++j)
    av[i++] = argv[j];
  av[i] = NULL;
  execvp ("bash", av);
  /* No bash on the host: fall through and serve as an ordinary make.  */
  free (av);
  free (script);
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

static int
amk_ape_list_cmp (const void *a, const void *b)
{
  return strcmp (*(const char *const *) a, *(const char *const *) b);
}

/* Every regular member under the directory, named relative to the payload root, appended to the list.  */
static void
amk_ape_list_walk (const char *dir, char ***names, size_t *n, size_t *cap)
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
          amk_ape_list_walk (path, names, n, cap);
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

/* The payload's members, one per line, sorted, as --ape-unpack names them.  */
int
amk_ape_list (void)
{
  char **names = NULL;
  size_t i, n = 0, cap = 0;
  struct stat st;

  if (stat ("/zip", &st) < 0)
    {
      fprintf (stderr, "amk: --ape-list: this build carries no payload\n");
      return MAKE_FAILURE;
    }
  amk_ape_list_walk ("/zip", &names, &n, &cap);
  qsort (names, n, sizeof *names, amk_ape_list_cmp);
  for (i = 0; i < n; ++i)
    {
      puts (names[i] + 5);
      free (names[i]);
    }
  free (names);
  return MAKE_SUCCESS;
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

void
amk_payload_path (void)
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
    return;

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
          closedir (d);
          free (dir);
          return;
        }
    }
  closedir (d);

  next = xmalloc (n + (path ? strlen (path) : 0) + 2);
  sprintf (next, "%s%s%s", dir, path && *path ? ":" : "", path ? path : "");
  setenv ("PATH", next, 1);
  free (next);
  free (dir);
}
#else
void
amk_payload_path (void)
{
}
#endif

/* Payload bundle: write a copy of this binary whose payload carries a makefile
   program, and run that program when the caller names no makefile.  */

#define AMK_MAIN_MK "/zip/__main__.mk"

#ifdef __COSMOPOLITAN__
#include "third_party/zlib/zlib.h"

struct amk_member
{
  const char *name;
  unsigned char *data;
  size_t len;
  unsigned long crc, off;
  unsigned int mode, dostime, dosdate;
};

static int
amk_bundle_fail (const char *what, const char *path)
{
  fprintf (stderr, "amk: --bundle: %s: %s: %s\n", what, path,
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

static unsigned char *
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

int
amk_bundle (int n, char **files, const char *out)
{
  struct amk_members set = { NULL, 0, 0 };
  struct amk_member *m;
  unsigned char *self, *eocd = NULL, *q, hdr[46];
  size_t selflen, cdoff, cdsize, entries, pos, cdstart, kept = 0;
  const char *base;
  char *tmp;
  int fd, r, i, e, reported = 0;

  if (n < 1)
    {
      fprintf (stderr, "amk: --bundle: names no makefile\n");
      return MAKE_FAILURE;
    }
  if (!out || !*out)
    {
      fprintf (stderr, "amk: --bundle: names no --out\n");
      return MAKE_FAILURE;
    }

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
    if (amk_bundle_add (&set, files[i], i == 0 ? "__main__.mk" : files[i])
        != MAKE_SUCCESS)
      return MAKE_FAILURE;
  m = set.m;
  n = set.n;

  self = amk_slurp (GetProgramExecutableName (), &selflen);
  if (!self)
    return amk_bundle_fail ("read", GetProgramExecutableName ());
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
  entries = amk_get16 (eocd + 10);
  cdsize = amk_get32 (eocd + 12);
  cdoff = amk_get32 (eocd + 16);
  /* Only a plain end record is rewritten; zip64 and split archives stop here.  */
  if (entries == 0xffff || cdoff == 0xffffffff
      || cdoff + cdsize > (size_t) (eocd - self))
    {
      errno = ENOTSUP;
      return amk_bundle_fail ("unsupported zip layout",
                              GetProgramExecutableName ());
    }

  tmp = xmalloc (strlen (out) + 32);
  base = strrchr (out, '/');
  base = base ? base + 1 : out;
  sprintf (tmp, "%.*s.tmp.%ld.%s", (int) (base - out), out, (long) getpid (),
           base);
  EINTRLOOP (fd, open (tmp, O_WRONLY | O_CREAT | O_TRUNC, 0755));
  if (fd < 0)
    return amk_bundle_fail ("open", tmp);

  /* Everything ahead of the central directory is kept byte for byte.  */
  if (amk_write_all (fd, self, cdoff) < 0)
    goto fail;
  pos = cdoff;
  for (i = 0; i < n; ++i)
    {
      size_t nl = strlen (m[i].name);
      memset (hdr, 0, 30);
      amk_put32 (hdr, 0x04034b50);
      amk_put16 (hdr + 4, 20);
      amk_put16 (hdr + 10, m[i].dostime);
      amk_put16 (hdr + 12, m[i].dosdate);
      amk_put32 (hdr + 14, m[i].crc);
      amk_put32 (hdr + 18, m[i].len);
      amk_put32 (hdr + 22, m[i].len);
      amk_put16 (hdr + 26, nl);
      m[i].off = pos;
      if (amk_write_all (fd, hdr, 30) < 0
          || amk_write_all (fd, m[i].name, nl) < 0
          || amk_write_all (fd, m[i].data, m[i].len) < 0)
        goto fail;
      pos += 30 + nl + m[i].len;
    }

  /* The old directory minus any member a new one replaces, then the new ones.  */
  cdstart = pos;
  for (q = self + cdoff, e = 0; (size_t) e < entries; ++e)
    {
      size_t nl, rec;
      int replaced = 0;
      if (q + 46 > self + cdoff + cdsize || amk_get32 (q) != 0x02014b50)
        {
          errno = EINVAL;
          reported = amk_bundle_fail ("damaged central directory",
                                      GetProgramExecutableName ());
          goto fail;
        }
      nl = amk_get16 (q + 28);
      rec = 46 + nl + amk_get16 (q + 30) + amk_get16 (q + 32);
      for (i = 0; i < n; ++i)
        if (strlen (m[i].name) == nl && memcmp (m[i].name, q + 46, nl) == 0)
          replaced = 1;
      if (!replaced)
        {
          if (amk_write_all (fd, q, rec) < 0)
            goto fail;
          pos += rec;
          ++kept;
        }
      q += rec;
    }
  for (i = 0; i < n; ++i)
    {
      size_t nl = strlen (m[i].name);
      memset (hdr, 0, 46);
      amk_put32 (hdr, 0x02014b50);
      amk_put16 (hdr + 4, (3 << 8) | 30);
      amk_put16 (hdr + 6, 20);
      amk_put16 (hdr + 12, m[i].dostime);
      amk_put16 (hdr + 14, m[i].dosdate);
      amk_put32 (hdr + 16, m[i].crc);
      amk_put32 (hdr + 20, m[i].len);
      amk_put32 (hdr + 24, m[i].len);
      amk_put16 (hdr + 28, nl);
      amk_put32 (hdr + 38, (unsigned long) (S_IFREG | m[i].mode) << 16);
      amk_put32 (hdr + 42, m[i].off);
      if (amk_write_all (fd, hdr, 46) < 0
          || amk_write_all (fd, m[i].name, nl) < 0)
        goto fail;
      pos += 46 + nl;
    }
  if (pos > 0xffffffffUL || kept + n > 0xfffe)
    {
      errno = EFBIG;
      reported = amk_bundle_fail ("too large for a plain zip", out);
      goto fail;
    }
  memset (hdr, 0, 22);
  amk_put32 (hdr, 0x06054b50);
  amk_put16 (hdr + 8, kept + n);
  amk_put16 (hdr + 10, kept + n);
  amk_put32 (hdr + 12, pos - cdstart);
  amk_put32 (hdr + 16, cdstart);
  if (amk_write_all (fd, hdr, 22) < 0)
    goto fail;
  fchmod (fd, 0755);
  close (fd);

  EINTRLOOP (r, rename (tmp, out));
  if (r < 0)
    {
      amk_bundle_fail ("rename", out);
      unlink (tmp);
      return MAKE_FAILURE;
    }
  return MAKE_SUCCESS;

 fail:
  if (!reported)
    amk_bundle_fail ("write", tmp);
  close (fd);
  unlink (tmp);
  return MAKE_FAILURE;
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
amk_bundle (int n UNUSED, char **files UNUSED, const char *out UNUSED)
{
  fprintf (stderr, "amk: --bundle: this build carries no payload\n");
  return MAKE_FAILURE;
}

void
amk_payload_main (int *argcp UNUSED, char ***argvp UNUSED)
{
}
#endif

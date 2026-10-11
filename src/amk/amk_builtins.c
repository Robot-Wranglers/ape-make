/* amk's small builtins: amk.require, amk.sys, amk.dedent and its value form, cksum, and amk.match.  */

#include "makeint.h"
#include "filedef.h"
#include "variable.h"
#include "amk.h"

/* $(amk.require names...): empty when every name is a feature, fatal naming the missing ones otherwise, in red on a terminal unless NO_COLOR, or the same name without its underscore, is set; commas and spaces both separate names.  */
char *
amk_func_require (char *o, char **argv, const char *funcname)
{
  size_t len = 64;
  char **a, *names, *text, *want, *missing, *msg;
  const char *red = "", *off = "";

  for (a = argv; *a != NULL; a++)
    len += strlen (*a) + 1;
  names = xmalloc (len);
  names[0] = '\0';
  for (a = argv; *a != NULL; a++)
    {
      strcat (names, *a);
      strcat (names, " ");
    }
  text = xmalloc (2 * len);
  sprintf (text, "$(strip $(filter-out $(.FEATURES),%s))", names);
  missing = allocated_variable_expand (text);
  sprintf (text, "$(strip %s)", names);
  want = allocated_variable_expand (text);
  free (text);
  free (names);
  if (*missing != '\0')
    {
      if (getenv ("NO_COLOR") == NULL && getenv ("NOCOLOR") == NULL && isatty (fileno (stderr)))
        red = "\033[1;31m", off = "\033[0m";
      msg = xmalloc (strlen (want) + strlen (missing) + strlen (funcname) + 128);
      sprintf (msg, "%s%s: this makefile needs amk with %s, and this amk has no %s%s", red, funcname, want, missing, off);
      OS (fatal, reading_file, "%s", msg);
    }
  free (want);
  free (missing);
  return o;
}

#include <sys/utsname.h>

/* $(amk.sys name): one process or host identity answered from the kernel, no shell: pid, ppid, uid, uname, arch, hostname, epoch, or uuid; an unknown name is fatal.  */
char *
amk_func_sys (char *o, char **argv, const char *funcname)
{
  const char *name = argv[0];
  char buf[256];

  while (*name == ' ' || *name == '\t')
    ++name;
  if (strcmp (name, "pid") == 0)
    sprintf (buf, "%ld", (long) getpid ());
  else if (strcmp (name, "ppid") == 0)
    sprintf (buf, "%ld", (long) getppid ());
  else if (strcmp (name, "uid") == 0)
    sprintf (buf, "%ld", (long) getuid ());
  else if (strcmp (name, "epoch") == 0)
    sprintf (buf, "%ld", (long) time (NULL));
  else if (strcmp (name, "uname") == 0 || strcmp (name, "arch") == 0)
    {
      struct utsname u;
      if (uname (&u) != 0)
        OSS (fatal, reading_file, _("%s: uname: %s"), funcname, strerror (errno));
      snprintf (buf, sizeof buf, "%s", name[0] == 'a' ? u.machine : u.sysname);
    }
  else if (strcmp (name, "hostname") == 0)
    {
      if (gethostname (buf, sizeof buf) != 0)
        OSS (fatal, reading_file, _("%s: hostname: %s"), funcname, strerror (errno));
      buf[sizeof buf - 1] = '\0';
    }
  else if (strcmp (name, "uuid") == 0)
    {
      unsigned char b[16];
      FILE *fp = fopen ("/dev/urandom", "rb");
      size_t i;
      if (fp == NULL || fread (b, 1, sizeof b, fp) != sizeof b)
        OSS (fatal, reading_file, _("%s: uuid: %s"), funcname, strerror (errno));
      fclose (fp);
      b[6] = (b[6] & 0x0F) | 0x40;
      b[8] = (b[8] & 0x3F) | 0x80;
      for (i = 0; i < sizeof b; ++i)
        sprintf (buf + 2 * i + (i > 3) + (i > 5) + (i > 7) + (i > 9), "%02x%s", b[i], (i == 3 || i == 5 || i == 7 || i == 9) ? "-" : "");
    }
  else
    OSS (fatal, reading_file, _("%s: unknown name `%s'"), funcname, name);
  return variable_buffer_output (o, buf, strlen (buf));
}

/* The text with its block indent removed, allocated; the base's width and the count of inconsistent lines come back through the pointers.  */
char *
amk_dedent (const char *text, size_t *basep, int *badp)
{
  const char *base = NULL, *line = text;
  size_t blen = 0;
  char *out = xmalloc (strlen (text) + 1);
  char *o = out;

  *badp = 0;
  for (;;)
    {
      size_t len = strcspn (line, "\n");
      size_t lead = strspn (line, " \t");
      size_t skip = 0;

      if (lead == len)
        skip = len;
      else if (base == NULL)
        {
          base = line;
          blen = skip = lead;
        }
      else if (line[0] == '\t' && memchr (base, '\t', blen) == NULL)
        skip = 0;
      else if (len < blen || memcmp (line, base, blen) != 0)
        ++*badp;
      else
        skip = blen;
      memcpy (o, line + skip, len - skip);
      o += len - skip;
      if (line[len] == '\0')
        break;
      *o++ = '\n';
      line += len + 1;
    }
  *o = '\0';
  *basep = blen;
  return out;
}

/* $(amk.dedent text): the text dedented, with one warning when a line breaks the base.  */
char *
amk_func_dedent (char *o, char **argv, const char *funcname)
{
  size_t base;
  int bad;
  char *text = amk_dedent (argv[0], &base, &bad);

  if (bad)
    error (reading_file, strlen (funcname) + INTSTR_LENGTH, _("%s: inconsistent indentation (a line is less-indented than the %d-column body base); passed through verbatim"), funcname, (int) base);
  o = variable_buffer_output (o, text, strlen (text));
  free (text);
  return o;
}

/* $(amk.val.dedent name): the variable's unexpanded value, as the value function reads it, dedented.  */
char *
amk_func_val_dedent (char *o, char **argv, const char *funcname)
{
  struct variable *v = lookup_variable (argv[0], strlen (argv[0]));
  char *args[2] = { v != NULL ? v->value : (char *) "", NULL };

  return amk_func_dedent (o, args, funcname);
}

/* The cksum of a byte run, the checksum the cksum utility prints: the cyclic redundancy check of the data and then of its length a byte at a time, low byte first, complemented.  */
unsigned long
amk_cksum (const unsigned char *data, size_t len)
{
  static unsigned long table[256];
  unsigned long crc = 0;
  size_t i, rest = len;

  if (table[1] == 0)
    for (i = 0; i < 256; ++i)
      {
        unsigned long c = i << 24;
        int j;
        for (j = 0; j < 8; ++j)
          c = (c & 0x80000000UL) ? ((c << 1) ^ 0x04C11DB7UL) : (c << 1);
        table[i] = c & 0xFFFFFFFFUL;
      }
  for (i = 0; i < len; ++i)
    crc = ((crc << 8) ^ table[((crc >> 24) ^ data[i]) & 0xFF]) & 0xFFFFFFFFUL;
  for (; rest != 0; rest >>= 8)
    crc = ((crc << 8) ^ table[((crc >> 24) ^ (rest & 0xFF)) & 0xFF]) & 0xFFFFFFFFUL;
  return ~crc & 0xFFFFFFFFUL;
}

/* $(cksum text), $(cksum.hex text), $(cksum.file path) and $(cksum.file.hex path): the checksum and length as the cksum utility would print them joined by a dash, or seven hex digits of the checksum modulo 2^28; a file is read whole, and one that cannot be read answers empty with a warning.  */
char *
amk_func_cksum (char *o, char **argv, const char *funcname)
{
  const char *name = funcname + 5;
  int file = strncmp (name, ".file", 5) == 0;
  int hex = strcmp (name + (file ? 5 : 0), ".hex") == 0;
  unsigned char *data = (unsigned char *) argv[0];
  size_t len;
  unsigned long crc;
  char buf[64];

  if (file)
    {
      FILE *fp = fopen (argv[0], "rb");
      size_t cap = 65536;
      if (fp == NULL)
        {
          error (reading_file, strlen (funcname) + strlen (argv[0]) + 64, _("%s: %s: %s"), funcname, argv[0], strerror (errno));
          return o;
        }
      data = xmalloc (cap);
      len = 0;
      for (;;)
        {
          size_t got = fread (data + len, 1, cap - len, fp);
          len += got;
          if (len < cap)
            break;
          cap *= 2;
          data = xrealloc (data, cap);
        }
      if (ferror (fp))
        {
          error (reading_file, strlen (funcname) + strlen (argv[0]) + 64, _("%s: %s: %s"), funcname, argv[0], strerror (errno));
          fclose (fp);
          free (data);
          return o;
        }
      fclose (fp);
    }
  else
    len = strlen (argv[0]);
  crc = amk_cksum (data, len);
  if (hex)
    sprintf (buf, "%07lx", crc % 268435456UL);
  else
    sprintf (buf, "%lu-%lu", crc, (unsigned long) len);
  if (file)
    free (data);
  return variable_buffer_output (o, buf, strlen (buf));
}

#include <regex.h>

/* $(amk.match re,text) and $(amk.match.file re,path): the lines of the text or of the file that an extended regular expression matches, in order and joined by newlines; a pattern that does not compile is fatal, and a file that cannot be read answers empty with a warning.  */
char *
amk_func_match (char *o, char **argv, const char *funcname)
{
  int file = strcmp (funcname + 9, ".file") == 0;
  regex_t re;
  char *text, *line;
  int rc = regcomp (&re, argv[0], REG_EXTENDED | REG_NOSUB);
  int first = 1;

  if (rc != 0)
    {
      char why[128];
      regerror (rc, &re, why, sizeof why);
      OSSS (fatal, reading_file, _("%s: %s: %s"), funcname, argv[0], why);
    }
  if (file)
    {
      FILE *fp = fopen (argv[1], "rb");
      size_t cap = 65536, len = 0;
      if (fp == NULL)
        {
          error (reading_file, strlen (funcname) + strlen (argv[1]) + 64, _("%s: %s: %s"), funcname, argv[1], strerror (errno));
          regfree (&re);
          return o;
        }
      text = xmalloc (cap);
      for (;;)
        {
          len += fread (text + len, 1, cap - len - 1, fp);
          if (len < cap - 1)
            break;
          cap *= 2;
          text = xrealloc (text, cap);
        }
      fclose (fp);
      text[len] = '\0';
    }
  else
    text = xstrdup (argv[1]);
  for (line = text; *line != '\0'; )
    {
      char *nl = strchr (line, '\n');
      size_t len = nl != NULL ? (size_t) (nl - line) : strlen (line);
      line[len] = '\0';
      if (regexec (&re, line, 0, NULL, 0) == 0)
        {
          if (!first)
            o = variable_buffer_output (o, "\n", 1);
          o = variable_buffer_output (o, line, len);
          first = 0;
        }
      if (nl == NULL)
        break;
      line = nl + 1;
    }
  regfree (&re);
  free (text);
  return o;
}

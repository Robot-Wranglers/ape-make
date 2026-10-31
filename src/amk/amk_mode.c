/* Modes: the table of named behaviour sets, with default in effect when none is set; the amk.mode builtin and its setter, the check that a mode precedes every file target, and the setting lookup the modes share.  */

#include "makeint.h"
#include "filedef.h"
#include "variable.h"
#include "hash.h"
#include "amk.h"

static const struct amk_mode amk_default_mode = { "default", NULL, NULL };

/* One row per mode; the first is in effect when none is set.  */
const struct amk_mode *const amk_modes[] = { &amk_default_mode, &amk_dataflow_mode, NULL };

static const struct amk_mode *amk_mode_now = &amk_default_mode;

const struct amk_mode *
amk_mode_active (void)
{
  return amk_mode_now;
}

/* The row a name picks, or null.  */
static const struct amk_mode *
amk_mode_by_name (const char *name)
{
  const struct amk_mode *const *m;
  for (m = amk_modes; *m != NULL; ++m)
    if (streq ((*m)->name, name))
      return *m;
  return NULL;
}

/* The known names, space-joined and allocated, for an error.  */
static char *
amk_mode_names (void)
{
  const struct amk_mode *const *m;
  size_t len = 1;
  char *names;
  for (m = amk_modes; *m != NULL; ++m)
    len += strlen ((*m)->name) + 1;
  names = xmalloc (len);
  names[0] = '\0';
  for (m = amk_modes; *m != NULL; ++m)
    {
      if (names[0] != '\0')
        strcat (names, " ");
      strcat (names, (*m)->name);
    }
  return names;
}

/* The active row follows the amk.mode variable, which the environment, a makefile and the command line set in make's own precedence; a name that is no mode is fatal and lists the modes.  */
static void
amk_mode_follow (const floc *flocp)
{
  const struct variable *v = lookup_variable ("amk.mode", 8);
  char *name = v != NULL && v->value[0] != '\0' ? (v->recursive ? allocated_variable_expand (v->value) : xstrdup (v->value)) : xstrdup (amk_default_mode.name);
  const struct amk_mode *m = amk_mode_by_name (amk_trim (name));

  if (m == NULL)
    {
      char *known = amk_mode_names ();
      fatal (flocp, strlen (name) + strlen (known), _("amk.mode: '%s' is no mode; the modes are %s"), name, known);
    }
  amk_mode_now = m;
  free (name);
}

/* A file target a makefile has defined so far, or null: a target that is neither special, phony, nor imported.  */
static const char *
amk_mode_file_target (void)
{
  struct file **slot = (struct file **) files.ht_vec;
  struct file **end = slot + files.ht_size;
  for (; slot < end; ++slot)
    if (! HASH_VACANT (*slot) && (*slot)->is_target && !(*slot)->phony && (*slot)->amk_engine == NULL && (*slot)->name[0] != '.')
      return (*slot)->name;
  return NULL;
}

/* $(amk.mode name) sets the mode for the whole process and answers nothing, and is fatal after a file target is defined, naming one; $(amk.mode) answers the active mode's name.  */
static char *
amk_func_mode (void *state, const char *name, unsigned int argc, char **argv)
{
  char *want = argc > 0 ? amk_trim (argv[0]) : (char *) "";
  const char *target;

  if (*want == '\0')
    return xstrdup (amk_mode_now->name);
  target = amk_mode_file_target ();
  if (target != NULL)
    OSS (fatal, reading_file, _("%s: a mode is set before any file target, and '%s' is already one"), name, target);
  define_variable_cname ("amk.mode", want, o_file, 0);
  amk_mode_follow (reading_file);
  return xstrdup ("");
}

/* At startup, before any makefile is read: AMK_MODE from the environment, under whatever the command line defined; then the active row follows, and the builtin registers.  */
void
amk_mode_init (void)
{
  const char *env = getenv ("AMK_MODE");
  if (env != NULL && *env != '\0')
    define_variable_cname ("amk.mode", env, o_env, 0);
  amk_mode_follow (NILF);
  amk_func_add ("amk.mode", NULL, amk_func_mode);
}

/* A setting under the amk namespace, allocated: the variable's expanded value when a makefile or the command line set it, else the environment name's value, else the default.  */
char *
amk_setting (const char *name, const char *env, const char *dflt)
{
  const struct variable *v = lookup_variable (name, strlen (name));
  const char *e;

  if (v != NULL && v->value[0] != '\0')
    return v->recursive ? allocated_variable_expand (v->value) : xstrdup (v->value);
  e = env != NULL ? getenv (env) : NULL;
  return xstrdup (e != NULL && *e != '\0' ? e : dflt);
}

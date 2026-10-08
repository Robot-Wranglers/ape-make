/* The micropython guest's entry point: amk links the interpreter, not the micropython cli, so it supplies this and the hal. */

#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#include "py/compile.h"
#include "py/cstack.h"
#include "py/gc.h"
#include "py/mphal.h"
#include "py/objmodule.h"
#include "py/runtime.h"
#include "py/stream.h"
#include "extmod/vfs.h"
#include "extmod/vfs_posix.h"
#include "shared/runtime/gchelper.h"
#include "amk_guest.h"

/* Under the engine flag make has parsed nothing, so the handle refuses rather than reads. */
static void
amk_need_make (void)
{
  if (!amk_has_db ())
    mp_raise_msg (&mp_type_RuntimeError, MP_ERROR_TEXT ("amk: no make database, running outside a makefile"));
}

/* The gc heap, and the C stack the interpreter may use before it raises rather than overflows; an ape's main thread has four times that. */
#define MICROPY_GUEST_HEAP  (64 * 1024 * 1024)
#define MICROPY_GUEST_STACK (1024 * 1024)

static void
write_all (int fd, const char *str, size_t len)
{
  while (len > 0)
    {
      ssize_t w = write (fd, str, len);
      if (w < 0 && errno == EINTR)
        continue;
      if (w <= 0)
        return;
      str += w;
      len -= w;
    }
}

static void
stderr_print_strn (void *env, const char *str, size_t len)
{
  (void) env;
  write_all (2, str, len);
}

const mp_print_t mp_stderr_print = { NULL, stderr_print_strn };

mp_uint_t
mp_hal_stdout_tx_strn (const char *str, size_t len)
{
  write_all (1, str, len);
  return len;
}

void
mp_hal_stdout_tx_strn_cooked (const char *str, size_t len)
{
  write_all (1, str, len);
}

void
mp_hal_stdout_tx_str (const char *str)
{
  write_all (1, str, strlen (str));
}

static uint64_t
clock_ns (clockid_t clock)
{
  struct timespec ts;
  clock_gettime (clock, &ts);
  return (uint64_t) ts.tv_sec * 1000000000ull + (uint64_t) ts.tv_nsec;
}

uint64_t
mp_hal_time_ns (void)
{
  return clock_ns (CLOCK_REALTIME);
}

mp_uint_t
mp_hal_ticks_ms (void)
{
  return (mp_uint_t) (clock_ns (CLOCK_MONOTONIC) / 1000000);
}

mp_uint_t
mp_hal_ticks_us (void)
{
  return (mp_uint_t) (clock_ns (CLOCK_MONOTONIC) / 1000);
}

void
mp_hal_delay_ms (mp_uint_t ms)
{
  struct timespec ts = { (time_t) (ms / 1000), (long) (ms % 1000) * 1000000 };
  nanosleep (&ts, NULL);
}

/* The system's entropy, or the clock when there is none, for os.urandom and the random seed. */
void
mp_hal_get_random (size_t n, uint8_t *buf)
{
  int fd = open ("/dev/urandom", O_RDONLY);
  size_t got = 0;
  uint64_t now;

  if (fd >= 0)
    {
      while (got < n)
        {
          ssize_t r = read (fd, buf + got, n - got);
          if (r <= 0)
            break;
          got += r;
        }
      close (fd);
    }
  now = clock_ns (CLOCK_REALTIME);
  for (; got < n; got++)
    buf[got] = (uint8_t) (now >> (8 * (got % 8)));
}

void
gc_collect (void)
{
  gc_collect_start ();
  gc_helper_collect_regs_and_stack ();
  gc_collect_end ();
}

/* An exception raised with no handler on the C stack, which run_chunk makes unreachable; leave through amk's exit rather than hang. */
void
nlr_jump_fail (void *val)
{
  (void) val;
  fprintf (stderr, "micropy: exception raised outside the chunk\n");
  exit (1);
}

/* A string make allocated, as a Python str, freed here; null becomes None. */
static mp_obj_t
amk_take_str (char *s)
{
  mp_obj_t o;
  if (s == NULL)
    return mp_const_none;
  o = mp_obj_new_str (s, strlen (s));
  gmk_free (s);
  return o;
}

/* amk.expand(text): the text expanded by make. */
static mp_obj_t
amk_expand (mp_obj_t text)
{
  amk_need_make ();
  return amk_take_str (gmk_expand (mp_obj_str_get_str (text)));
}
static MP_DEFINE_CONST_FUN_OBJ_1 (amk_expand_obj, amk_expand);

/* amk.eval(text): the text read by make as makefile syntax. */
static mp_obj_t
amk_eval_fn (mp_obj_t text)
{
  amk_need_make ();
  amk_eval (mp_obj_str_get_str (text));
  return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1 (amk_eval_obj, amk_eval_fn);

static mp_obj_t
amk_var_load (const char *name)
{
  amk_need_make ();
  return amk_take_str (amk_var_get (name));
}

/* A value as the text make gets: a str as is, None as nothing, and anything else as str would show it. The vstr is the caller's to clear. */
static const char *
amk_obj_text (mp_obj_t value, vstr_t *vstr)
{
  mp_print_t print;
  if (value == mp_const_none)
    return "";
  if (mp_obj_is_str (value))
    return mp_obj_str_get_str (value);
  vstr_init_print (vstr, 16, &print);
  mp_obj_print_helper (&print, value, PRINT_STR);
  return vstr_null_terminated_str (vstr);
}

/* amk.call(name, *values): the cascade, a make function, the name under amk., a macro, each value one whole argument, never expanded; amk.fxn and amk.macro take one layer by its full name. */
static mp_obj_t
amk_call_kind_fn (int kind, const char *who, size_t n_args, const mp_obj_t *args)
{
  const char *err = NULL, *name, **vals;
  size_t n = n_args - 1, i;
  vstr_t *vstrs;
  char *s;
  amk_need_make ();
  name = mp_obj_str_get_str (args[0]);
  vals = m_new (const char *, n + 1);
  vstrs = m_new0 (vstr_t, n + 1);
  for (i = 0; i < n; i++)
    vals[i] = amk_obj_text (args[i + 1], &vstrs[i]);
  s = amk_call_kind (kind, name, (unsigned int) n, vals, &err);
  for (i = 0; i < n; i++)
    vstr_clear (&vstrs[i]);
  m_del (vstr_t, vstrs, n + 1);
  m_del (const char *, vals, n + 1);
  if (s == NULL)
    mp_raise_msg_varg (&mp_type_ValueError, MP_ERROR_TEXT ("%s: %s"), who, err);
  return amk_take_str (s);
}
static mp_obj_t amk_call_fn (size_t n_args, const mp_obj_t *args) { return amk_call_kind_fn (AMK_AS_ANY, "amk.call", n_args, args); }
static mp_obj_t amk_fxn_fn (size_t n_args, const mp_obj_t *args) { return amk_call_kind_fn (AMK_AS_FXN, "amk.fxn", n_args, args); }
static mp_obj_t amk_macro_fn (size_t n_args, const mp_obj_t *args) { return amk_call_kind_fn (AMK_AS_MACRO, "amk.macro", n_args, args); }
static MP_DEFINE_CONST_FUN_OBJ_VAR (amk_call_obj, 1, amk_call_fn);
static MP_DEFINE_CONST_FUN_OBJ_VAR (amk_fxn_obj, 1, amk_fxn_fn);
static MP_DEFINE_CONST_FUN_OBJ_VAR (amk_macro_obj, 1, amk_macro_fn);

/* A deferred call's handle: a stream whose poll answers once the result is in, so asyncio can wait on it, with the pid, the fd, and result() that collects the text or raises. */
typedef struct
{
  mp_obj_base_t base;
  pid_t pid;
  int fd;
} amk_acall_obj_t;

static mp_uint_t
amk_acall_ioctl (mp_obj_t self_in, mp_uint_t request, uintptr_t arg, int *errcode)
{
  amk_acall_obj_t *o = MP_OBJ_TO_PTR (self_in);
  if (request == MP_STREAM_GET_FILENO)
    return (mp_uint_t) o->fd;
  if (request == MP_STREAM_POLL)
    {
      struct pollfd pfd = { .fd = o->fd, .events = (arg & MP_STREAM_POLL_RD) ? POLLIN : 0 };
      mp_uint_t ret = 0;
      if (poll (&pfd, 1, 0) > 0)
        {
          if (pfd.revents & POLLIN)
            ret |= MP_STREAM_POLL_RD;
          if (pfd.revents & POLLHUP)
            ret |= MP_STREAM_POLL_HUP;
          if (pfd.revents & POLLERR)
            ret |= MP_STREAM_POLL_ERR;
        }
      return ret;
    }
  *errcode = MP_EINVAL;
  return MP_STREAM_ERROR;
}
static const mp_stream_p_t amk_acall_stream_p = { .ioctl = amk_acall_ioctl };

static mp_obj_t
amk_acall_result (mp_obj_t self_in)
{
  amk_acall_obj_t *o = MP_OBJ_TO_PTR (self_in);
  const char *err = NULL;
  char *s;
  if (amk_call_end (o->pid, &s, &err) < 0)
    mp_raise_msg_varg (&mp_type_ValueError, MP_ERROR_TEXT ("amk.acall: %s"), err);
  return amk_take_str (s);
}
static MP_DEFINE_CONST_FUN_OBJ_1 (amk_acall_result_obj, amk_acall_result);

static const mp_rom_map_elem_t amk_acall_locals_table[] = {
  { MP_ROM_QSTR (MP_QSTR_result), MP_ROM_PTR (&amk_acall_result_obj) },
};
static MP_DEFINE_CONST_DICT (amk_acall_locals, amk_acall_locals_table);

static void
amk_acall_attr (mp_obj_t self_in, qstr attr, mp_obj_t *dest)
{
  amk_acall_obj_t *o = MP_OBJ_TO_PTR (self_in);
  if (dest[0] != MP_OBJ_NULL)
    return;
  if (attr == MP_QSTR_pid)
    dest[0] = mp_obj_new_int (o->pid);
  else if (attr == MP_QSTR_fd)
    dest[0] = mp_obj_new_int (o->fd);
  else
    dest[1] = MP_OBJ_SENTINEL;
}

static MP_DEFINE_CONST_OBJ_TYPE (amk_acall_type, MP_QSTR_acall_handle, MP_TYPE_FLAG_NONE,
                                 attr, amk_acall_attr, protocol, &amk_acall_stream_p, locals_dict, &amk_acall_locals);

/* amk.call_begin(name, *values): the call begun in a fork, as its handle; amk.acall is the awaitable over it, and fxn_begin and macro_begin take one layer for amk.afxn and amk.amacro. */
static mp_obj_t
amk_call_begin_kind (int kind, size_t n_args, const mp_obj_t *args)
{
  const char *name, **vals;
  size_t n = n_args - 1, i;
  vstr_t *vstrs;
  int fd = -1;
  pid_t pid;
  amk_acall_obj_t *o;
  amk_need_make ();
  name = mp_obj_str_get_str (args[0]);
  vals = m_new (const char *, n + 1);
  vstrs = m_new0 (vstr_t, n + 1);
  for (i = 0; i < n; i++)
    vals[i] = amk_obj_text (args[i + 1], &vstrs[i]);
  pid = amk_call_begin (kind, name, (unsigned int) n, vals, &fd);
  for (i = 0; i < n; i++)
    vstr_clear (&vstrs[i]);
  m_del (vstr_t, vstrs, n + 1);
  m_del (const char *, vals, n + 1);
  if (pid < 0)
    mp_raise_msg (&mp_type_OSError, MP_ERROR_TEXT ("amk.acall: fork failed"));
  o = mp_obj_malloc (amk_acall_obj_t, &amk_acall_type);
  o->pid = pid;
  o->fd = fd;
  return MP_OBJ_FROM_PTR (o);
}
static mp_obj_t amk_call_begin_fn (size_t n_args, const mp_obj_t *args) { return amk_call_begin_kind (AMK_AS_ANY, n_args, args); }
static mp_obj_t amk_fxn_begin_fn (size_t n_args, const mp_obj_t *args) { return amk_call_begin_kind (AMK_AS_FXN, n_args, args); }
static mp_obj_t amk_macro_begin_fn (size_t n_args, const mp_obj_t *args) { return amk_call_begin_kind (AMK_AS_MACRO, n_args, args); }
static MP_DEFINE_CONST_FUN_OBJ_VAR (amk_call_begin_obj, 1, amk_call_begin_fn);
static MP_DEFINE_CONST_FUN_OBJ_VAR (amk_fxn_begin_obj, 1, amk_fxn_begin_fn);
static MP_DEFINE_CONST_FUN_OBJ_VAR (amk_macro_begin_obj, 1, amk_macro_begin_fn);

/* An ask's handle: the id, and result() that waits for the reply and answers its text or raises. */
typedef struct
{
  mp_obj_base_t base;
  unsigned long id;
} amk_ask_obj_t;

static mp_obj_t
amk_ask_result_fn (mp_obj_t self_in)
{
  amk_ask_obj_t *o = MP_OBJ_TO_PTR (self_in);
  const char *err = NULL;
  char *s;
  if (amk_ask_result (amk_ask_collect (o->id), &s, &err) < 0)
    mp_raise_msg_varg (&mp_type_ValueError, MP_ERROR_TEXT ("amk.ask: %s"), err);
  return amk_take_str (s);
}
static MP_DEFINE_CONST_FUN_OBJ_1 (amk_ask_result_obj, amk_ask_result_fn);

static const mp_rom_map_elem_t amk_ask_locals_table[] = {
  { MP_ROM_QSTR (MP_QSTR_result), MP_ROM_PTR (&amk_ask_result_obj) },
};
static MP_DEFINE_CONST_DICT (amk_ask_locals, amk_ask_locals_table);

static void
amk_ask_attr (mp_obj_t self_in, qstr attr, mp_obj_t *dest)
{
  amk_ask_obj_t *o = MP_OBJ_TO_PTR (self_in);
  if (dest[0] != MP_OBJ_NULL)
    return;
  if (attr == MP_QSTR_id)
    dest[0] = mp_obj_new_int_from_uint (o->id);
  else
    dest[1] = MP_OBJ_SENTINEL;
}

static MP_DEFINE_CONST_OBJ_TYPE (amk_ask_type, MP_QSTR_ask_handle, MP_TYPE_FLAG_NONE,
                                 attr, amk_ask_attr, locals_dict, &amk_ask_locals);

/* amk.ask(op, namespace, *values): one request sent to the owner, as its handle; the process goes on until result() is called, and in the owner a request that would park raises. */
static mp_obj_t
amk_ask_fn (size_t n_args, const mp_obj_t *args)
{
  const char *op, *ns, **vals;
  size_t n = n_args - 2, i;
  vstr_t *vstrs;
  char *line;
  long id;
  amk_ask_obj_t *o;
  amk_need_make ();
  op = mp_obj_str_get_str (args[0]);
  ns = mp_obj_str_get_str (args[1]);
  vals = m_new (const char *, n + 1);
  vstrs = m_new0 (vstr_t, n + 1);
  for (i = 0; i < n; i++)
    vals[i] = amk_obj_text (args[i + 2], &vstrs[i]);
  line = amk_ask_line (op, ns, (unsigned int) n, vals);
  for (i = 0; i < n; i++)
    vstr_clear (&vstrs[i]);
  m_del (vstr_t, vstrs, n + 1);
  m_del (const char *, vals, n + 1);
  id = amk_ask_begin (line);
  free (line);
  if (id < 0)
    mp_raise_msg (&mp_type_RuntimeError, MP_ERROR_TEXT ("amk.ask: " AMK_ASK_PARKED));
  o = mp_obj_malloc (amk_ask_obj_t, &amk_ask_type);
  o->id = (unsigned long) id;
  return MP_OBJ_FROM_PTR (o);
}
static MP_DEFINE_CONST_FUN_OBJ_VAR (amk_ask_obj, 2, amk_ask_fn);

/* A store defines a recursive variable with the text as written, as a define does. */
static void
amk_var_raw_store (const char *name, mp_obj_t value)
{
  vstr_t vstr = { 0 };
  amk_need_make ();
  amk_var_raw_set (name, amk_obj_text (value, &vstr));
  vstr_clear (&vstr);
}

static mp_obj_t
amk_var_raw_load (const char *name)
{
  amk_need_make ();
  return amk_take_str (amk_var_raw_get (name));
}

/* amk.var.raw.name reads a variable's text as stored, never expanded, or assigns it; deleting one is refused. */
static void
amk_var_raw_attr (mp_obj_t self_in, qstr attr, mp_obj_t *dest)
{
  (void) self_in;
  if (dest[0] == MP_OBJ_NULL)
    dest[0] = amk_var_raw_load (qstr_str (attr));
  else if (dest[1] != MP_OBJ_NULL)
    {
      amk_var_raw_store (qstr_str (attr), dest[1]);
      dest[0] = MP_OBJ_NULL;
    }
}

/* amk.var.raw[name] reads or assigns a variable whose name attribute syntax cannot spell. */
static mp_obj_t
amk_var_raw_subscr (mp_obj_t self_in, mp_obj_t index, mp_obj_t value)
{
  (void) self_in;
  if (value == MP_OBJ_SENTINEL)
    return amk_var_raw_load (mp_obj_str_get_str (index));
  if (value == MP_OBJ_NULL)
    return MP_OBJ_NULL;
  amk_var_raw_store (mp_obj_str_get_str (index), value);
  return mp_const_none;
}

static MP_DEFINE_CONST_OBJ_TYPE (amk_var_raw_type, MP_QSTR_raw, MP_TYPE_FLAG_NONE,
                                 attr, amk_var_raw_attr, subscr, amk_var_raw_subscr);
static const mp_obj_base_t amk_var_raw_obj = { &amk_var_raw_type };

/* A read of raw is the raw proxy in every engine; a write of raw defines the variable. */
static mp_obj_t
amk_var_read (const char *name)
{
  return strcmp (name, "raw") == 0 ? MP_OBJ_FROM_PTR (&amk_var_raw_obj) : amk_var_load (name);
}

/* A store defines a simple variable with the literal text of the value. */
static void
amk_var_store (const char *name, mp_obj_t value)
{
  vstr_t vstr = { 0 };
  amk_need_make ();
  amk_var_set (name, amk_obj_text (value, &vstr));
  vstr_clear (&vstr);
}

/* amk.var.name reads or assigns the variable; deleting one is refused. */
static void
amk_var_attr (mp_obj_t self_in, qstr attr, mp_obj_t *dest)
{
  (void) self_in;
  if (dest[0] == MP_OBJ_NULL)
    dest[0] = amk_var_read (qstr_str (attr));
  else if (dest[1] != MP_OBJ_NULL)
    {
      amk_var_store (qstr_str (attr), dest[1]);
      dest[0] = MP_OBJ_NULL;
    }
}

/* amk.var[name] reads or assigns a variable whose name attribute syntax cannot spell. */
static mp_obj_t
amk_var_subscr (mp_obj_t self_in, mp_obj_t index, mp_obj_t value)
{
  (void) self_in;
  if (value == MP_OBJ_SENTINEL)
    return amk_var_read (mp_obj_str_get_str (index));
  if (value == MP_OBJ_NULL)
    return MP_OBJ_NULL;
  amk_var_store (mp_obj_str_get_str (index), value);
  return mp_const_none;
}

static MP_DEFINE_CONST_OBJ_TYPE (amk_var_type, MP_QSTR_var, MP_TYPE_FLAG_NONE,
                                 attr, amk_var_attr, subscr, amk_var_subscr);
static const mp_obj_base_t amk_var_obj = { &amk_var_type };

/* What lives in the state rather than the module's constant table: the dict of hook callables by event and the awaitable slots, all attributes of amk the prelude assigns, and the dict of make functions the kept state has defined. */
enum { AMK_MUTABLE_ON, AMK_MUTABLE_ACALL, AMK_MUTABLE_AGOAL, AMK_MUTABLE_AFXN, AMK_MUTABLE_AMACRO, AMK_MUTABLE_FUNCS };
MP_REGISTER_ROOT_POINTER(mp_obj_t amk_mutable[6]);

/* A make function reached as an attribute of amk: amk.name(...) calls it, and amk.name.field reaches amk.name.field the same way. */
typedef struct
{
  mp_obj_base_t base;
  mp_obj_t name;
} amk_fxn_obj_t;

static mp_obj_t amk_fxn_new (const char *name);

static void
amk_fxn_attr (mp_obj_t self_in, qstr attr, mp_obj_t *dest)
{
  amk_fxn_obj_t *self = MP_OBJ_TO_PTR (self_in);
  char full[256];
  if (dest[0] != MP_OBJ_NULL || dest[1] != MP_OBJ_NULL)
    return;
  snprintf (full, sizeof full, "%s.%s", mp_obj_str_get_str (self->name), qstr_str (attr));
  dest[0] = amk_fxn_new (full);
}

static mp_obj_t
amk_fxn_call (mp_obj_t self_in, size_t n_args, size_t n_kw, const mp_obj_t *args)
{
  amk_fxn_obj_t *self = MP_OBJ_TO_PTR (self_in);
  mp_obj_t *full, r;
  size_t i;
  if (n_kw != 0)
    mp_raise_TypeError (MP_ERROR_TEXT ("a make function takes no keywords"));
  full = m_new (mp_obj_t, n_args + 1);
  full[0] = self->name;
  for (i = 0; i < n_args; i++)
    full[i + 1] = args[i];
  r = amk_call_fn (n_args + 1, full);
  m_del (mp_obj_t, full, n_args + 1);
  return r;
}

static MP_DEFINE_CONST_OBJ_TYPE (amk_fxn_type, MP_QSTR_fxn, MP_TYPE_FLAG_NONE,
                                 attr, amk_fxn_attr, call, amk_fxn_call);

static mp_obj_t
amk_fxn_new (const char *name)
{
  amk_fxn_obj_t *o = mp_obj_malloc (amk_fxn_obj_t, &amk_fxn_type);
  o->name = mp_obj_new_str (name, strlen (name));
  return MP_OBJ_FROM_PTR (o);
}

void
amk_module_attr (mp_obj_t self_in, qstr attr, mp_obj_t *dest)
{
  static const uint16_t keys[] = { MP_QSTR_on, MP_QSTR_acall, MP_QSTR_agoal, MP_QSTR_afxn, MP_QSTR_amacro, MP_QSTRnull };
  (void) self_in;
  mp_module_generic_attr (attr, dest, keys, MP_STATE_VM (amk_mutable));
  /* A missing attribute names an amk module, the file lib/name/__init__.py, loaded once by path as the module amk.name; with no such file, what the cascade resolves the name to, else the name stays missing. */
  if (dest[0] == MP_OBJ_NULL && dest[1] == MP_OBJ_NULL)
    {
      mp_map_t *loaded = &MP_STATE_VM (mp_loaded_modules_dict).map;
      mp_map_elem_t *el;
      nlr_buf_t nlr;
      char path[512];
      qstr name;
      FILE *f;
      snprintf (path, sizeof path, "amk.%s", qstr_str (attr));
      name = qstr_from_str (path);
      if ((el = mp_map_lookup (loaded, MP_OBJ_NEW_QSTR (name), MP_MAP_LOOKUP)) != NULL)
        {
          dest[0] = el->value;
          return;
        }
      snprintf (path, sizeof path, "/zip/lib/%s/__init__.py", qstr_str (attr));
      if ((f = fopen (path, "r")) == NULL)
        {
          const char *err;
          if (amk_resolve (qstr_str (attr), path, sizeof path, &err) >= 0)
            dest[0] = amk_fxn_new (qstr_str (attr));
          return;
        }
      fclose (f);
      dest[0] = mp_obj_new_module (name);
      if (nlr_push (&nlr) == 0)
        {
          mp_obj_dict_t *globals = mp_obj_module_get_globals (dest[0]);
          mp_parse_compile_execute (mp_lexer_new_from_file (qstr_from_str (path)), MP_PARSE_FILE_INPUT, globals, globals);
          nlr_pop ();
          /* A module that put another object under its name in sys.modules is answered as that object, python's own idiom for a module with item access. */
          if ((el = mp_map_lookup (loaded, MP_OBJ_NEW_QSTR (name), MP_MAP_LOOKUP)) != NULL)
            dest[0] = el->value;
        }
      else
        {
          mp_map_lookup (loaded, MP_OBJ_NEW_QSTR (name), MP_MAP_LOOKUP_REMOVE_IF_FOUND);
          dest[0] = MP_OBJ_NULL;
          nlr_jump (nlr.ret_val);
        }
    }
}

/* Whether the one kept state, the only one micropython's heap allows, is up; make holds it as main for the life of the process, and its address is the state make sees. */
static int micropy_kept;

static mp_map_elem_t *
amk_dict_lookup (int slot, const char *key)
{
  mp_obj_t dict = MP_STATE_VM (amk_mutable)[slot];
  if (!mp_obj_is_type (dict, &mp_type_dict))
    return NULL;
  return mp_map_lookup (&((mp_obj_dict_t *) MP_OBJ_TO_PTR (dict))->map, mp_obj_new_str_from_cstr (key), MP_MAP_LOOKUP);
}

static void amk_deadline_settle (void);

/* make's call into a defined function: the arguments as strings, the result as text, and an error raised to whoever made the call. */
static char *
amk_func_call (void *state, const char *nm, unsigned int argc, char **argv)
{
  nlr_buf_t nlr;
  mp_map_elem_t *el;
  char *out = NULL;

  (void) state;
  if (!micropy_kept)
    return NULL;
  mp_cstack_init_with_sp_here (MICROPY_GUEST_STACK);
  el = amk_dict_lookup (AMK_MUTABLE_FUNCS, nm);
  if (el == NULL)
    return NULL;
  if (nlr_push (&nlr) == 0)
    {
      mp_obj_t *args = alloca (argc * sizeof *args);
      mp_obj_t result;
      vstr_t vstr = { 0 };
      const char *text;
      unsigned int i;
      for (i = 0; i < argc; i++)
        args[i] = mp_obj_new_str_from_cstr (argv[i]);
      result = mp_call_function_n_kw (el->value, argc, 0, args);
      text = amk_obj_text (result, &vstr);
      out = gmk_alloc ((unsigned int) strlen (text) + 1);
      strcpy (out, text);
      vstr_clear (&vstr);
      nlr_pop ();
    }
  else if (amk_deadline_expired ())
    amk_deadline_settle ();
  else
    {
      vstr_t why;
      mp_print_t print;
      vstr_init_print (&why, 64, &print);
      mp_obj_print_helper (&print, MP_OBJ_FROM_PTR (nlr.ret_val), PRINT_EXC);
      amk_func_raise ("micropy", nm, vstr_null_terminated_str (&why));
      vstr_clear (&why);
    }
  return out;
}

/* The callable becomes make's function of that name, or replaces the one this state defined before; a name make has from elsewhere is an error. */
static void
amk_define_func (mp_obj_t name, mp_obj_t fn)
{
  const char *nm = mp_obj_str_get_str (name);
  if (amk_func_add (nm, &micropy_kept, amk_func_call) < 0)
    mp_raise_msg_varg (&mp_type_RuntimeError, MP_ERROR_TEXT ("amk.func: %s is a make function already"), nm);
  mp_obj_dict_store (MP_STATE_VM (amk_mutable)[AMK_MUTABLE_FUNCS], name, fn);
}

/* amk.func(name, fn): make gains a function of that name whose arguments, expanded, reach fn as strings and whose result is what fn returns; only the kept state outlives the call to answer. */
static mp_obj_t
amk_func (mp_obj_t name, mp_obj_t fn)
{
  if (!micropy_kept)
    mp_raise_msg (&mp_type_RuntimeError, MP_ERROR_TEXT ("amk.func: only from micropy.exec, since a one-shot call's state ends with the call"));
  amk_need_make ();
  if (!mp_obj_is_callable (fn))
    mp_raise_TypeError (MP_ERROR_TEXT ("amk.func: fn must be callable"));
  amk_define_func (name, fn);
  return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_2 (amk_func_obj, amk_func);

static int
amk_elem_cmp (const void *a, const void *b)
{
  return strcmp (mp_obj_str_get_str ((*(const mp_map_elem_t *const *) a)->key),
                 mp_obj_str_get_str ((*(const mp_map_elem_t *const *) b)->key));
}

/* The filled entries of a map whose keys are all str, in key order; a key that is not a str is an error naming the owner. */
static size_t
amk_sorted_entries (mp_map_t *map, mp_map_elem_t **out, const char *owner)
{
  size_t n = 0, i;
  for (i = 0; i < map->alloc; i++)
    {
      if (!mp_map_slot_is_filled (map, i))
        continue;
      if (!mp_obj_is_str (map->table[i].key))
        mp_raise_msg_varg (&mp_type_ValueError, MP_ERROR_TEXT ("amk import: %s has a key that is not a str"), owner);
      out[n++] = &map->table[i];
    }
  qsort (out, n, sizeof *out, amk_elem_cmp);
  return n;
}

/* One global into make: a callable as a make function, a list or tuple as words, a dict as fields named name.key, a bool as true or nothing, and a str or number as its text; None, modules, and types are skipped. The names exported are appended to the vstr. */
static void
amk_export_value (const char *name, mp_obj_t value, vstr_t *names)
{
  vstr_t text = { 0 };
  if (value == mp_const_none || mp_obj_is_type (value, &mp_type_module) || mp_obj_is_type (value, &mp_type_type))
    return;
  if (mp_obj_is_type (value, &mp_type_dict))
    {
      mp_map_t *map = &((mp_obj_dict_t *) MP_OBJ_TO_PTR (value))->map;
      mp_map_elem_t **fields = alloca (map->alloc * sizeof *fields);
      size_t n = amk_sorted_entries (map, fields, name), i;
      for (i = 0; i < n; i++)
        {
          const char *key = mp_obj_str_get_str (fields[i]->key);
          vstr_t child = { 0 };
          if (!amk_name_ok (key))
            mp_raise_msg_varg (&mp_type_ValueError, MP_ERROR_TEXT ("amk import: %s has a key make cannot spell: %s"), name, key);
          vstr_init (&child, strlen (name) + strlen (key) + 2);
          vstr_printf (&child, "%s.%s", name, key);
          amk_export_value (vstr_null_terminated_str (&child), fields[i]->value, names);
          vstr_clear (&child);
        }
      return;
    }
  if (mp_obj_is_callable (value))
    amk_define_func (mp_obj_new_str_from_cstr (name), value);
  else if (value == mp_const_true || value == mp_const_false)
    amk_var_set (name, value == mp_const_true ? "true" : "");
  else if (mp_obj_is_type (value, &mp_type_list) || mp_obj_is_type (value, &mp_type_tuple))
    {
      size_t n, i;
      mp_obj_t *items;
      mp_obj_get_array (value, &n, &items);
      vstr_init (&text, 16);
      for (i = 0; i < n; i++)
        {
          vstr_t item = { 0 };
          if (i > 0)
            vstr_add_char (&text, ' ');
          vstr_add_str (&text, amk_obj_text (items[i], &item));
          vstr_clear (&item);
        }
      amk_var_set (name, vstr_null_terminated_str (&text));
      vstr_clear (&text);
    }
  else
    {
      amk_var_set (name, amk_obj_text (value, &text));
      vstr_clear (&text);
    }
  if (names->len > 0)
    vstr_add_char (names, ' ');
  vstr_add_str (names, name);
}

/* Every global that is new or rebound since the snapshot, exported in name order since the globals dict keeps none, and the names as the result. */
static void
amk_export_globals (mp_obj_t before, struct amk_sink *out)
{
  mp_map_t *now = &mp_globals_get ()->map;
  mp_map_t *was = &((mp_obj_dict_t *) MP_OBJ_TO_PTR (before))->map;
  mp_map_elem_t **all = alloca (now->alloc * sizeof *all);
  size_t n = amk_sorted_entries (now, all, "globals"), i;
  vstr_t names;

  vstr_init (&names, 64);
  for (i = 0; i < n; i++)
    {
      const char *key = mp_obj_str_get_str (all[i]->key);
      mp_map_elem_t *old = mp_map_lookup (was, all[i]->key, MP_MAP_LOOKUP);
      if (!amk_name_ok (key) || (old != NULL && old->value == all[i]->value))
        continue;
      amk_export_value (key, all[i]->value, &names);
    }
  if (names.len > 0)
    out->write (out, names.buf, names.len);
  out->write (out, "\n", 1);
  vstr_clear (&names);
}

int amk_deadline_tick = 64;

/* Every 64 branches, then on every branch once the process's deadline has passed, so each frame that catches the error raises it again and the run unwinds to the call that set it. */
void
amk_deadline_poll (void)
{
  amk_deadline_tick = 64;
  if (amk_deadline_expired ())
    {
      amk_deadline_tick = 1;
      mp_sched_exception (mp_obj_new_exception_msg_varg (&mp_type_RuntimeError, MP_ERROR_TEXT ("deadline: %d ms"), (int) amk_deadline_budget ()));
    }
}

/* The check back to its normal pace and any error it scheduled dropped, once a bounded run has unwound. */
static void
amk_deadline_settle (void)
{
  amk_deadline_tick = 64;
  MP_STATE_THREAD (mp_pending_exception) = MP_OBJ_NULL;
}

/* amk.deadline(ms, fn, *args): fn's result, or RuntimeError("deadline: ms ms") once ms milliseconds pass, in this guest or in any other it calls; a nested deadline keeps the tighter one. */
static mp_obj_t
amk_deadline (size_t n_args, const mp_obj_t *args)
{
  mp_int_t ms = mp_obj_get_int (args[0]);
  struct amk_deadline saved;
  long hit;
  nlr_buf_t nlr;
  mp_obj_t r = mp_const_none, exc = MP_OBJ_NULL;

  if (ms < 0)
    mp_raise_ValueError (MP_ERROR_TEXT ("amk.deadline: ms must not be negative"));
  if (!mp_obj_is_callable (args[1]))
    mp_raise_TypeError (MP_ERROR_TEXT ("amk.deadline: fn must be callable"));
  amk_deadline_push ((long) ms, &saved);
  if (nlr_push (&nlr) == 0)
    {
      r = mp_call_function_n_kw (args[1], n_args - 2, 0, args + 2);
      nlr_pop ();
    }
  else
    exc = MP_OBJ_FROM_PTR (nlr.ret_val);
  hit = amk_deadline_pop (&saved);
  amk_deadline_settle ();
  if (exc != MP_OBJ_NULL && hit >= 0)
    mp_raise_msg_varg (&mp_type_RuntimeError, MP_ERROR_TEXT ("deadline: %d ms"), (int) hit);
  if (exc != MP_OBJ_NULL)
    nlr_raise (exc);
  return r;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR (amk_deadline_obj, 2, amk_deadline);

static const mp_rom_map_elem_t amk_module_globals_table[] = {
  { MP_ROM_QSTR (MP_QSTR___name__), MP_ROM_QSTR (MP_QSTR_amk) },
  { MP_ROM_QSTR (MP_QSTR_expand), MP_ROM_PTR (&amk_expand_obj) },
  { MP_ROM_QSTR (MP_QSTR_eval), MP_ROM_PTR (&amk_eval_obj) },
  { MP_ROM_QSTR (MP_QSTR_call), MP_ROM_PTR (&amk_call_obj) },
  { MP_ROM_QSTR (MP_QSTR_fxn), MP_ROM_PTR (&amk_fxn_obj) },
  { MP_ROM_QSTR (MP_QSTR_macro), MP_ROM_PTR (&amk_macro_obj) },
  { MP_ROM_QSTR (MP_QSTR_call_begin), MP_ROM_PTR (&amk_call_begin_obj) },
  { MP_ROM_QSTR (MP_QSTR_fxn_begin), MP_ROM_PTR (&amk_fxn_begin_obj) },
  { MP_ROM_QSTR (MP_QSTR_macro_begin), MP_ROM_PTR (&amk_macro_begin_obj) },
  { MP_ROM_QSTR (MP_QSTR_ask), MP_ROM_PTR (&amk_ask_obj) },
  { MP_ROM_QSTR (MP_QSTR_var), MP_ROM_PTR (&amk_var_obj) },
  { MP_ROM_QSTR (MP_QSTR_func), MP_ROM_PTR (&amk_func_obj) },
  { MP_ROM_QSTR (MP_QSTR_deadline), MP_ROM_PTR (&amk_deadline_obj) },
};
static MP_DEFINE_CONST_DICT (amk_module_globals, amk_module_globals_table);

const mp_obj_module_t amk_module = {
  .base = { &mp_type_module },
  .globals = (mp_obj_dict_t *) &amk_module_globals,
};
MP_REGISTER_MODULE(MP_QSTR_amk, amk_module);
MP_REGISTER_MODULE_DELEGATION(amk_module, amk_module_attr);

static int run_chunk (const char *src);

/* amk.acall as asyncio awaits it: the handle begun, the task parked on its descriptor through the loop's own io queue, the result collected on wake; afxn and amacro the same over one layer, agoal over the goal function. */
static const char *micropy_amk_prelude =
  "def awaited(begin):\n"
  "  def go(name, *args):\n"
  "    from asyncio import core\n"
  "    h = begin(name, *args)\n"
  "    yield core._io_queue.queue_read(h)\n"
  "    return h.result()\n"
  "  return go\n"
  "amk.acall = awaited(amk.call_begin)\n"
  "amk.afxn = awaited(amk.fxn_begin)\n"
  "amk.amacro = awaited(amk.macro_begin)\n"
  "amk.agoal = lambda name: amk.acall('amk.goal', name)\n"
  "del awaited\n";

/* The path variable micropython reads from its environment, here as make holds it, words or colon-separated, onto sys.path once each; a state reads it when it opens, and the persistent state again at the goals event, so a makefile that grows it after the state opened is honored by every recipe. */
static void
micropy_sync_path (void)
{
  char *path, *p, *word;
  size_t n, i;
  mp_obj_t *items;

  if (!amk_has_db ())
    return;
  path = amk_var_get ("MICROPYPATH");
  if (path == NULL)
    return;
  for (p = path; (word = strtok_r (p, " \t\n:", &p)) != NULL;)
    {
      mp_obj_list_get (mp_sys_path, &n, &items);
      for (i = 0; i < n; i++)
        if (strcmp (mp_obj_str_get_str (items[i]), word) == 0)
          break;
      if (i == n)
        mp_obj_list_append (mp_sys_path, mp_obj_new_str_from_cstr (word));
    }
  gmk_free (path);
}

/* A state: the heap, the interpreter, the host filesystem at the root, and the module's mutable slots; 0 when it is up. */
static int
micropy_state_open (void)
{
  char *heap = malloc (MICROPY_GUEST_HEAP);
  if (heap == NULL)
    return -1;
  gc_init (heap, heap + MICROPY_GUEST_HEAP);
  mp_init ();
  {
    mp_obj_t args[2] = {
      MP_OBJ_TYPE_GET_SLOT (&mp_type_vfs_posix, make_new) (&mp_type_vfs_posix, 0, 0, NULL),
      MP_OBJ_NEW_QSTR (MP_QSTR__slash_),
    };
    mp_vfs_mount (2, args, (mp_map_t *) &mp_const_empty_map);
    MP_STATE_VM (vfs_cur) = MP_STATE_VM (vfs_mount_table);
    while (MP_STATE_VM (vfs_cur)->next != NULL)
      MP_STATE_VM (vfs_cur) = MP_STATE_VM (vfs_cur)->next;
  }
  mp_obj_list_append (mp_sys_path, mp_obj_new_str_from_cstr ("/zip/lib/micropy"));
  micropy_sync_path ();
  MP_STATE_VM (amk_mutable)[AMK_MUTABLE_ON] = mp_obj_new_dict (0);
  MP_STATE_VM (amk_mutable)[AMK_MUTABLE_FUNCS] = mp_obj_new_dict (0);
  MP_STATE_VM (amk_mutable)[AMK_MUTABLE_ACALL] = mp_const_none;
  MP_STATE_VM (amk_mutable)[AMK_MUTABLE_AGOAL] = mp_const_none;
  MP_STATE_VM (amk_mutable)[AMK_MUTABLE_AFXN] = mp_const_none;
  MP_STATE_VM (amk_mutable)[AMK_MUTABLE_AMACRO] = mp_const_none;
  mp_store_global (MP_QSTR_amk, MP_OBJ_FROM_PTR (&amk_module));
  return run_chunk (micropy_amk_prelude);
}

/* Run the chunk: 0 on success, the SystemExit value when the chunk exits, 1 with the traceback on stderr otherwise. */
static int
run_chunk (const char *src)
{
  nlr_buf_t nlr;
  mp_obj_t exc;

  if (nlr_push (&nlr) == 0)
    {
      mp_lexer_t *lex = mp_lexer_new_from_str_len (MP_QSTR__lt_stdin_gt_, src, strlen (src), 0);
      qstr source_name = lex->source_name;
      mp_parse_tree_t parse_tree = mp_parse (lex, MP_PARSE_FILE_INPUT);
      mp_obj_t module_fun = mp_compile (&parse_tree, source_name, false);
      mp_call_function_0 (module_fun);
      nlr_pop ();
      return 0;
    }

  exc = MP_OBJ_FROM_PTR (nlr.ret_val);
  if (mp_obj_is_subclass_fast (MP_OBJ_FROM_PTR (mp_obj_get_type (exc)), MP_OBJ_FROM_PTR (&mp_type_SystemExit)))
    {
      mp_obj_t value = mp_obj_exception_get_value (exc);
      mp_int_t status = 0;
      if (value != mp_const_none && !mp_obj_get_int_maybe (value, &status))
        status = 1;
      return (int) (status & 255);
    }
  mp_obj_print_exception (&mp_stderr_print, exc);
  return 1;
}

/* argv[1] is Python source text rather than a command line; whatever it prints is the result. */
__attribute__ ((visibility ("default"))) int
micropy_run_main (int argc, char **argv)
{
  int rc;

  if (argc < 2 || argv[1] == NULL)
    {
      fprintf (stderr, "micropy: no chunk\n");
      return 2;
    }

  mp_cstack_init_with_sp_here (MICROPY_GUEST_STACK);
  micropy_kept = 0;
  if (micropy_state_open () != 0)
    {
      fprintf (stderr, "micropy: cannot allocate heap\n");
      return 1;
    }

  rc = run_chunk (argv[1]);

  mp_deinit ();
  fflush (stdout);
  return rc;
}

/* The create member: the one kept state, which make holds as main; a second create answers null, since micropython has one heap and one set of globals. */
__attribute__ ((visibility ("default"))) void *
micropy_create (void)
{
  if (micropy_kept)
    return NULL;
  mp_cstack_init_with_sp_here (MICROPY_GUEST_STACK);
  if (micropy_state_open () != 0)
    {
      fprintf (stderr, "micropy: cannot create state\n");
      return NULL;
    }
  micropy_kept = 1;
  return &micropy_kept;
}

/* exec runs the chunk with what it writes to stdout going to the sink; import runs it with output on stderr, then hands make the globals it defined or rebound and the sink their names. */
static int
micropy_run_op (void *state, struct amk_sink *out, const char *op, const char *prog)
{
  struct amk_capture capture;
  int export = strcmp (op, "import") == 0;
  mp_obj_t before;
  nlr_buf_t nlr;
  int rc;

  (void) state;
  if (prog == NULL)
    {
      fprintf (stderr, "micropy.%s: no chunk\n", op);
      return 2;
    }
  mp_cstack_init_with_sp_here (MICROPY_GUEST_STACK);

  if (!export)
    {
      amk_capture_begin_to (&capture, out);
      rc = run_chunk (prog);
      amk_capture_end (&capture, out);
      return rc;
    }

  before = mp_obj_dict_copy (MP_OBJ_FROM_PTR (mp_globals_get ()));
  amk_capture_begin (&capture);
  rc = run_chunk (prog);
  amk_capture_end (&capture, &amk_sink_stderr);
  if (rc != 0)
    return rc;
  if (nlr_push (&nlr) == 0)
    {
      amk_export_globals (before, out);
      nlr_pop ();
      return 0;
    }
  fprintf (stderr, "micropy.import: ");
  mp_obj_print_exception (&mp_stderr_print, MP_OBJ_FROM_PTR (nlr.ret_val));
  return 1;
}

__attribute__ ((visibility ("default"))) int
micropy_exec (void *state, struct amk_sink *out, const char *prog)
{
  return micropy_run_op (state, out, "exec", prog);
}

__attribute__ ((visibility ("default"))) int
micropy_import (void *state, struct amk_sink *out, const char *prog)
{
  return micropy_run_op (state, out, "import", prog);
}

/* The hook primitive: amk.on[event], when the state holds a callable there, is called with the event as a dict. Its print goes to stderr, and an error reports there and is otherwise ignored. */
__attribute__ ((visibility ("default"))) void
micropy_hook (void *state, const char *event, const char *target, const char *status, int exit_code, int exit_sig, long pid)
{
  struct amk_capture capture;
  nlr_buf_t nlr;
  mp_obj_t fn;
  mp_map_elem_t *el;

  (void) state;
  mp_cstack_init_with_sp_here (MICROPY_GUEST_STACK);
  if (strcmp (event, "goals") == 0)
    micropy_sync_path ();
  el = amk_dict_lookup (AMK_MUTABLE_ON, event);
  if (el == NULL || !mp_obj_is_callable (el->value))
    return;
  fn = el->value;

  amk_capture_begin (&capture);
  if (nlr_push (&nlr) == 0)
    {
      mp_obj_t e = mp_obj_new_dict (6);
      mp_obj_dict_store (e, MP_OBJ_NEW_QSTR (MP_QSTR_event), mp_obj_new_str_from_cstr (event));
      mp_obj_dict_store (e, MP_OBJ_NEW_QSTR (MP_QSTR_target), mp_obj_new_str_from_cstr (target));
      mp_obj_dict_store (e, MP_OBJ_NEW_QSTR (MP_QSTR_status), mp_obj_new_str_from_cstr (status));
      mp_obj_dict_store (e, MP_OBJ_NEW_QSTR (MP_QSTR_code), mp_obj_new_int (exit_code));
      mp_obj_dict_store (e, MP_OBJ_NEW_QSTR (MP_QSTR_signal), mp_obj_new_int (exit_sig));
      mp_obj_dict_store (e, MP_OBJ_NEW_QSTR (MP_QSTR_pid), mp_obj_new_int (pid));
      mp_call_function_1 (fn, e);
      nlr_pop ();
    }
  else
    {
      fprintf (stderr, "micropy hook %s: ", event);
      mp_obj_print_exception (&mp_stderr_print, MP_OBJ_FROM_PTR (nlr.ret_val));
    }
  amk_capture_end (&capture, &amk_sink_stderr);
}

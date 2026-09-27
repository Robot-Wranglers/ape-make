/* The micropython guest's entry point: amk links the interpreter, not the micropython cli, so it supplies this and the hal. */

#include <errno.h>
#include <fcntl.h>
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
    dest[0] = amk_var_load (qstr_str (attr));
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
    return amk_var_load (mp_obj_str_get_str (index));
  if (value == MP_OBJ_NULL)
    return MP_OBJ_NULL;
  amk_var_store (mp_obj_str_get_str (index), value);
  return mp_const_none;
}

static MP_DEFINE_CONST_OBJ_TYPE (amk_var_type, MP_QSTR_var, MP_TYPE_FLAG_NONE,
                                 attr, amk_var_attr, subscr, amk_var_subscr);
static const mp_obj_base_t amk_var_obj = { &amk_var_type };

/* What lives in the state rather than the module's constant table: the call's input, the dict of hook callables by event, both attributes of amk, and the dict of make functions the persistent state has defined. */
enum { AMK_MUTABLE_INPUT, AMK_MUTABLE_ON, AMK_MUTABLE_FUNCS };
MP_REGISTER_ROOT_POINTER(mp_obj_t amk_mutable[3]);

void
amk_module_attr (mp_obj_t self_in, qstr attr, mp_obj_t *dest)
{
  static const uint16_t keys[] = { MP_QSTR_input, MP_QSTR_on, MP_QSTRnull };
  (void) self_in;
  mp_module_generic_attr (attr, dest, keys, MP_STATE_VM (amk_mutable));
}

/* Whether the one state the persistent entry and the hook share is up; it is kept for the life of the process. */
static int persistent_ready;

static mp_map_elem_t *
amk_dict_lookup (int slot, const char *key)
{
  mp_obj_t dict = MP_STATE_VM (amk_mutable)[slot];
  if (!mp_obj_is_type (dict, &mp_type_dict))
    return NULL;
  return mp_map_lookup (&((mp_obj_dict_t *) MP_OBJ_TO_PTR (dict))->map, mp_obj_new_str_from_cstr (key), MP_MAP_LOOKUP);
}

/* make's call into a defined function: the arguments as strings, the result as text, and an error reported on stderr and answered empty. */
static char *
amk_func_call (const char *nm, unsigned int argc, char **argv)
{
  nlr_buf_t nlr;
  mp_map_elem_t *el;
  char *out = NULL;

  if (!persistent_ready)
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
  else
    {
      fprintf (stderr, "micropy $(%s ...): ", nm);
      mp_obj_print_exception (&mp_stderr_print, MP_OBJ_FROM_PTR (nlr.ret_val));
    }
  return out;
}

/* The callable becomes make's function of that name, or replaces the one this state defined before; a name make has from elsewhere is an error. */
static void
amk_define_func (mp_obj_t name, mp_obj_t fn)
{
  const char *nm = mp_obj_str_get_str (name);
  if (amk_dict_lookup (AMK_MUTABLE_FUNCS, nm) == NULL)
    {
      if (amk_function_exists (nm))
        mp_raise_msg_varg (&mp_type_RuntimeError, MP_ERROR_TEXT ("amk.func: %s is a make function already"), nm);
      gmk_add_function (nm, amk_func_call, 0, 0, 0);
    }
  mp_obj_dict_store (MP_STATE_VM (amk_mutable)[AMK_MUTABLE_FUNCS], name, fn);
}

/* amk.func(name, fn): make gains a function of that name whose arguments, expanded, reach fn as strings and whose result is what fn returns; only the persistent state outlives the call to answer. */
static mp_obj_t
amk_func (mp_obj_t name, mp_obj_t fn)
{
  if (!persistent_ready)
    mp_raise_msg (&mp_type_RuntimeError, MP_ERROR_TEXT ("amk.func: only from micropy.persistent, since a one-shot call's state ends with the call"));
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
        mp_raise_msg_varg (&mp_type_ValueError, MP_ERROR_TEXT ("amk export: %s has a key that is not a str"), owner);
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
            mp_raise_msg_varg (&mp_type_ValueError, MP_ERROR_TEXT ("amk export: %s has a key make cannot spell: %s"), name, key);
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

static const mp_rom_map_elem_t amk_module_globals_table[] = {
  { MP_ROM_QSTR (MP_QSTR___name__), MP_ROM_QSTR (MP_QSTR_amk) },
  { MP_ROM_QSTR (MP_QSTR_expand), MP_ROM_PTR (&amk_expand_obj) },
  { MP_ROM_QSTR (MP_QSTR_eval), MP_ROM_PTR (&amk_eval_obj) },
  { MP_ROM_QSTR (MP_QSTR_var), MP_ROM_PTR (&amk_var_obj) },
  { MP_ROM_QSTR (MP_QSTR_func), MP_ROM_PTR (&amk_func_obj) },
};
static MP_DEFINE_CONST_DICT (amk_module_globals, amk_module_globals_table);

const mp_obj_module_t amk_module = {
  .base = { &mp_type_module },
  .globals = (mp_obj_dict_t *) &amk_module_globals,
};
MP_REGISTER_MODULE(MP_QSTR_amk, amk_module);
MP_REGISTER_MODULE_DELEGATION(amk_module, amk_module_attr);

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
  MP_STATE_VM (amk_mutable)[AMK_MUTABLE_INPUT] = MP_OBJ_NEW_QSTR (MP_QSTR_);
  MP_STATE_VM (amk_mutable)[AMK_MUTABLE_ON] = mp_obj_new_dict (0);
  MP_STATE_VM (amk_mutable)[AMK_MUTABLE_FUNCS] = mp_obj_new_dict (0);
  mp_store_global (MP_QSTR_amk, MP_OBJ_FROM_PTR (&amk_module));
  return 0;
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
  persistent_ready = 0;
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

/* The persistent entry: one state for the life of the process, so a global one chunk sets is there for the next. What the chunk writes to stdout goes to the sink, and argv[2], if any, is amk.input. */
__attribute__ ((visibility ("default"))) int
micropy_persist_main (struct amk_sink *out, int argc, char **argv)
{
  struct amk_capture capture;
  const char *input = argc > 2 && argv[2] != NULL ? argv[2] : "";
  int export = amk_entry_is (argv[0], "export");
  mp_obj_t before;
  nlr_buf_t nlr;
  int rc;

  if (argc < 2 || argv[1] == NULL)
    {
      fprintf (stderr, "micropy.persistent: no chunk\n");
      return 2;
    }
  mp_cstack_init_with_sp_here (MICROPY_GUEST_STACK);
  if (!persistent_ready)
    {
      if (micropy_state_open () != 0)
        {
          fprintf (stderr, "micropy.persistent: cannot create state\n");
          return 1;
        }
      persistent_ready = 1;
    }
  MP_STATE_VM (amk_mutable)[AMK_MUTABLE_INPUT] = mp_obj_new_str (input, strlen (input));

  if (!export)
    {
      amk_capture_begin (&capture);
      rc = run_chunk (argv[1]);
      amk_capture_end (&capture, out);
      return rc;
    }

  before = mp_obj_dict_copy (MP_OBJ_FROM_PTR (mp_globals_get ()));
  amk_capture_begin (&capture);
  rc = run_chunk (argv[1]);
  amk_capture_end (&capture, &amk_sink_stderr);
  if (rc != 0)
    return rc;
  if (nlr_push (&nlr) == 0)
    {
      amk_export_globals (before, out);
      nlr_pop ();
      return 0;
    }
  fprintf (stderr, "micropy.export: ");
  mp_obj_print_exception (&mp_stderr_print, MP_OBJ_FROM_PTR (nlr.ret_val));
  return 1;
}

/* The hook entry: amk.on[event], when the persistent state holds a callable there, is called with the event as a dict. Its print goes to stderr, and an error reports there and is otherwise ignored. */
__attribute__ ((visibility ("default"))) void
micropy_hook_main (const char *event, const char *target, const char *status, int exit_code, int exit_sig, long pid)
{
  struct amk_capture capture;
  nlr_buf_t nlr;
  mp_obj_t fn;
  mp_map_elem_t *el;

  if (!persistent_ready)
    return;
  mp_cstack_init_with_sp_here (MICROPY_GUEST_STACK);
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

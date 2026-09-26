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
#include "py/runtime.h"
#include "extmod/vfs.h"
#include "extmod/vfs_posix.h"
#include "shared/runtime/gchelper.h"

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
  char *heap;
  int rc;

  if (argc < 2 || argv[1] == NULL)
    {
      fprintf (stderr, "micropy: no chunk\n");
      return 2;
    }

  mp_cstack_init_with_sp_here (MICROPY_GUEST_STACK);
  heap = malloc (MICROPY_GUEST_HEAP);
  if (heap == NULL)
    {
      fprintf (stderr, "micropy: cannot allocate heap\n");
      return 1;
    }
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

  rc = run_chunk (argv[1]);

  mp_deinit ();
  free (heap);
  fflush (stdout);
  return rc;
}

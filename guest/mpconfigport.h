/* MicroPython's configuration for the amk guest: the everything level, numbers as CPython has them, and stdio and files through the host filesystem. */

#include <alloca.h>
#include <stdint.h>
#include <time.h>
#include <unistd.h>

#define MICROPY_CONFIG_ROM_LEVEL                (MICROPY_CONFIG_ROM_LEVEL_EVERYTHING)

/* marshal saves bytecode, which needs the qstr table that persistent code brings, so mpy loading comes on as in the unix port. */
#define MICROPY_PERSISTENT_CODE_LOAD            (1)

typedef long mp_off_t;

#define MICROPY_FLOAT_IMPL                      (MICROPY_FLOAT_IMPL_DOUBLE)
#define MICROPY_LONGINT_IMPL                    (MICROPY_LONGINT_IMPL_MPZ)

/* One source for both architectures in the ape: no assembly for the gc's register scan or for non-local return. */
#define MICROPY_ENABLE_GC                       (1)
#define MICROPY_ENABLE_FINALISER                (1)
#define MICROPY_GCREGS_SETJMP                   (1)
#define MICROPY_NLR_SETJMP                      (1)
#define MICROPY_STACK_CHECK                     (1)
#define MICROPY_MALLOC_USES_ALLOCATED_SIZE      (1)
#define MICROPY_USE_INTERNAL_PRINTF             (0)

/* The host filesystem mounted at the root, which is where sys.stdin and open come from. */
#define MICROPY_VFS                             (1)
#define MICROPY_VFS_POSIX                       (1)
#define MICROPY_READER_VFS                      (1)
#define MICROPY_READER_POSIX                    (1)
#define MICROPY_HELPER_LEXER_UNIX               (1)
#define MICROPY_PY_SYS_STDFILES                 (1)
#define MICROPY_STREAMS_POSIX_API               (1)
#define MICROPY_EPOCH_IS_1970                   (1)
#define MICROPY_TIMESTAMP_IMPL                  (MICROPY_TIMESTAMP_IMPL_TIME_T)
#define MICROPY_PY_SYS_PLATFORM                 "amk"

/* Errors report in full on stderr, so the chunk's output stays the result. */
#define MICROPY_ERROR_REPORTING                 (MICROPY_ERROR_REPORTING_DETAILED)
#define MICROPY_WARNINGS                        (1)
extern const struct _mp_print_t mp_stderr_print;
#define MICROPY_ERROR_PRINTER                   (&mp_stderr_print)
#define MICROPY_DEBUG_PRINTER                   (&mp_stderr_print)

/* os and time as the unix port has them, over the hal in micropy_main.c. */
#define MICROPY_PY_OS_INCLUDEFILE               "ports/unix/modos.c"
#define MICROPY_PY_OS_ERRNO                     (1)
#define MICROPY_PY_OS_GETENV_PUTENV_UNSETENV    (1)
#define MICROPY_PY_OS_SYSTEM                    (1)
#define MICROPY_PY_OS_URANDOM                   (1)
#define MICROPY_PY_TIME                         (1)
#define MICROPY_PY_TIME_TIME_TIME_NS            (1)
#define MICROPY_PY_TIME_CUSTOM_SLEEP            (1)
#define MICROPY_PY_TIME_INCLUDEFILE             "ports/unix/modtime.c"
#define MICROPY_PY_SELECT_POSIX_OPTIMISATIONS   (0)
#define MICROPY_PY_SELECT_SELECT                (0)
#define MICROPY_PY_RANDOM_SEED_INIT_FUNC        (mp_random_seed_init ())
void mp_hal_get_random (size_t n, uint8_t *buf);
static inline unsigned long
mp_random_seed_init (void)
{
  unsigned long r;
  mp_hal_get_random (sizeof r, (uint8_t *) &r);
  return r;
}

/* Sockets as the unix port has them, polled through select. */
#define MICROPY_PY_SOCKET                       (1)

/* The unix port's command line: its default path with the payload's modules added. */
#define MICROPY_PY_SYS_PATH_DEFAULT             ".frozen:~/.micropython/lib:/usr/lib/micropython:/zip/lib/micropy"
/* Compile-only runs as the unix port has them. */
extern _Bool mp_compile_only;
#define MICROPY_PYEXEC_COMPILE_ONLY             (1)
/* A script's exit status as the unix port has it. */
#define MICROPY_PYEXEC_ENABLE_EXIT_CODE_HANDLING (1)
/* The verbose flag and its printers, as in the unix port. */
#define MICROPY_DEBUG_PRINTERS                  (1)
/* A module run by the command line's module option is the main module, as in the unix port. */
#define MICROPY_MODULE_OVERRIDE_MAIN_IMPORT     (1)
/* The port's state is the vm's, as in the unix port. */
#define MP_STATE_PORT                           MP_STATE_VM

/* A prompt that reads lines and no threads; asyncio's Python half is read from the payload. */
#define MICROPY_HELPER_REPL                     (1)
#define MICROPY_USE_READLINE                    (0)
#define MICROPY_PY_BUILTINS_INPUT               (0)
#define MICROPY_PY_BUILTINS_HELP                (0)
#define MICROPY_KBD_EXCEPTION                   (0)
#define MICROPY_PY_THREAD                       (0)
#define MICROPY_PY_MACHINE                      (0)
#define MICROPY_PY_ASYNCIO                      (1)

/* amk.deadline's check, on a countdown of branches so a run without a deadline pays one decrement per branch. */
extern int amk_deadline_tick;
void amk_deadline_poll (void);
#define MICROPY_VM_HOOK_LOOP                    if (--amk_deadline_tick <= 0) amk_deadline_poll ();

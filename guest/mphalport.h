/* The hal the amk guest gives MicroPython: a process on a host libc with no terminal; the functions live in micropy_main.c. */

#include <errno.h>
#include <unistd.h>

#define mp_hal_ticks_cpu() 0

static inline void
mp_hal_delay_us (mp_uint_t us)
{
  usleep (us);
}

#define RAISE_ERRNO(err_flag, error_val) \
  { if (err_flag == -1) { mp_raise_OSError (error_val); } }

/* A syscall interrupted by a signal is retried, as the unix port and pep 475 have it. */
#define MP_HAL_RETRY_SYSCALL(ret, syscall, raise) { \
    for (;;) { \
      ret = syscall; \
      if (ret == -1) { \
        int err = errno; \
        if (err == EINTR) { \
          mp_handle_pending (MP_HANDLE_PENDING_CALLBACKS_AND_EXCEPTIONS); \
          continue; \
        } \
        raise; \
      } \
      break; \
    } \
  }

void mp_hal_get_random (size_t n, uint8_t *buf);

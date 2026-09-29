# The micropython guest: amk's own port of MicroPython, laid out like ports/unix and built as objects for the partial link, from guest/ where its two config headers live.
include $(MICROPYTHON_TOP)/py/mkenv.mk
MICROPY_PY_SSL := 1
MICROPY_SSL_MBEDTLS := 1
include $(TOP)/py/py.mk
include $(TOP)/extmod/extmod.mk

CFLAGS += -I. -I$(TOP) -I$(TOP)/ports/unix -I$(BUILD) -std=gnu99 -Wall -DNDEBUG $(CFLAGS_EXTRA)

# The entry point and hal, the gc's stack scan, and the time helpers; py.mk and extmod.mk bring the rest, the in-tree libraries included by the modules that use them.
SRC_C += micropy_main.c \
	shared/runtime/gchelper_generic.c \
	shared/timeutils/timeutils.c \
	ports/unix/modsocket.c
SRC_QSTR += micropy_main.c ports/unix/modsocket.c

OBJ = $(PY_O) $(addprefix $(BUILD)/,$(SRC_C:.c=.o))

include $(TOP)/py/mkrules.mk

objects: $(OBJ)

/* tinycc's configuration for the guest: one code generator per slice of the fat ape, chosen by the arch being compiled, and the predefined macros compiled in.  */

#define TCC_VERSION "0.9.28rc"
#define CC_NAME CC_gcc
#define GCC_MAJOR 0
#define GCC_MINOR 0

#if defined(__x86_64__)
#define TCC_TARGET_X86_64 1
#define CONFIG_TRIPLET "x86_64-linux-gnu"
#else
#define TCC_TARGET_ARM64 1
#define CONFIG_TRIPLET "arm64-linux-gnu"
#endif

#define CONFIG_TCCDIR "/zip/lib/tcc"
#define CONFIG_TCC_PREDEFS 1
#define CONFIG_TCC_BACKTRACE 0
#define CONFIG_TCC_BCHECK 0

/* Course simulation port. Upstream benchmark sources are unchanged. */
#ifndef CORE_PORTME_H
#define CORE_PORTME_H

#define HAS_FLOAT 0
#define HAS_TIME_H 0
#define USE_CLOCK 0
#define HAS_STDIO 0
#define HAS_PRINTF 0
#define COMPILER_VERSION "GCC " __VERSION__
#define COMPILER_FLAGS "See the framework build log for exact compiler flags"
#define MEM_LOCATION "STACK"

typedef signed short ee_s16;
typedef unsigned short ee_u16;
typedef signed int ee_s32;
typedef unsigned int ee_u32;
typedef unsigned char ee_u8;
typedef __UINTPTR_TYPE__ ee_ptr_int;
typedef __SIZE_TYPE__ ee_size_t;
#ifndef NULL
#define NULL ((void *)0)
#endif
#define align_mem(x) (void *)(4 + (((ee_ptr_int)(x) - 1) & ~(ee_ptr_int)3))

/* Timing belongs to the testbench, not the target program in this port. */
#define CORETIMETYPE ee_u32
typedef ee_u32 CORE_TICKS;
#define SEED_METHOD SEED_VOLATILE
#define MEM_METHOD MEM_STACK
#define MULTITHREAD 1
#define USE_PTHREAD 0
#define USE_FORK 0
#define USE_SOCKET 0
#define MAIN_HAS_NOARGC 1
#define MAIN_HAS_NORETURN 0

#ifndef ITERATIONS
#define ITERATIONS 1
#endif
#if ITERATIONS < 1 || ITERATIONS > 2147483647
#error "ITERATIONS must be positive; target-side automatic timing is unavailable"
#endif
#ifndef COREMARK_VALIDATION
#define COREMARK_VALIDATION 0
#endif
#if COREMARK_VALIDATION != 0 && COREMARK_VALIDATION != 1
#error "COREMARK_VALIDATION must be 0 (performance seeds) or 1 (validation seeds)"
#endif
#if TOTAL_DATA_SIZE != 2000
#error "This CRC-checking port requires TOTAL_DATA_SIZE=2000"
#endif

extern ee_u32 default_num_contexts;
typedef struct CORE_PORTABLE_S { ee_u8 portable_id; } core_portable;
void portable_init(core_portable *, int *, char *[]);
void portable_fini(core_portable *);
int ee_printf(const char *, ...);
int coremark_check(void);

#endif

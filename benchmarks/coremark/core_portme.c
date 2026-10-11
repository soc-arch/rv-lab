/* RV32IM course port: SRAM result signatures and testbench ROI timing only. */
#include "coremark.h"
#include "lab.h"
#include <stdarg.h>

#if COREMARK_VALIDATION
volatile ee_s32 seed1_volatile = 0x3415;
volatile ee_s32 seed2_volatile = 0x3415;
#else
volatile ee_s32 seed1_volatile = 0;
volatile ee_s32 seed2_volatile = 0;
#endif
volatile ee_s32 seed3_volatile = 0x66;
volatile ee_s32 seed4_volatile = ITERATIONS;
volatile ee_s32 seed5_volatile = 0;
ee_u32 default_num_contexts = 1;

static ee_u32 crc_values[5];
static ee_u32 crc_seen, errors, time_warnings, starts, stops;

static int contains(const char *text, const char *needle)
{
    for (; *text; ++text) {
        const char *a = text, *b = needle;
        while (*a && *a == *b) { ++a; ++b; }
        if (!*b) return 1;
    }
    return 0;
}

void start_time(void)
{
    ++starts;
    lab_roi_begin();
}

void stop_time(void)
{
    lab_roi_end();
    ++stops;
}

/* Zero means that this target has no software-visible timing source. Do not
 * fabricate elapsed seconds. The unmodified benchmark emits its short-run
 * warning; the RTL runner measures the marker-to-marker cycle interval. */
CORE_TICKS get_time(void) { return 0; }
secs_ret time_in_secs(CORE_TICKS ticks) { (void)ticks; return 0; }

void portable_init(core_portable *p, int *argc, char *argv[])
{
    (void)argc;
    (void)argv;
    p->portable_id = 1;
}
void portable_fini(core_portable *p) { p->portable_id = 0; }

/* Capture the fixed upstream diagnostics, not a general printf service.
 * uint16_t CRC arguments undergo integer promotion to int on RV32 ILP32. */
int ee_printf(const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    if (contains(fmt, "Must execute for at least 10 secs")) {
        ++time_warnings;
    } else if (contains(fmt, "ERROR!") || contains(fmt, "ERROR: ")
               || contains(fmt, "Cannot validate")
               || contains(fmt, "too big for comparable")) {
        ++errors;
    }

    int index = -1;
    if (contains(fmt, "seedcrc ")) index = 0;
    if (contains(fmt, "crclist ")) index = 1;
    if (contains(fmt, "crcmatrix ")) index = 2;
    if (contains(fmt, "crcstate ")) index = 3;
    if (contains(fmt, "crcfinal ")) index = 4;
    if (index >= 0) {
        if (index != 0) (void)va_arg(ap, int); /* Context number. */
        if (crc_seen & (1u << index)) ++errors;
        crc_values[index] = (ee_u32)va_arg(ap, int);
        crc_seen |= 1u << index;
    }
    va_end(ap);
    return 0;
}

int coremark_check(void)
{
#if COREMARK_VALIDATION
    static const ee_u32 expected[4] = {0x18f2, 0xe3c1, 0x0747, 0x8d84};
#else
    static const ee_u32 expected[4] = {0xe9f5, 0xe714, 0x1fd7, 0x8e3a};
#endif
    int failed = 0;
    for (ee_u32 i = 0; i < 4; ++i) {
        lab_check(100 + i, crc_values[i], expected[i]);
        if (crc_values[i] != expected[i]) failed = 1;
    }
    lab_check(104, crc_seen, 31);
    lab_check(105, errors, 0);
    lab_check(106, (starts << 16) | stops, 0x00010001);
    lab_check(107, time_warnings, 1);
    lab_result(0, ITERATIONS);
    for (ee_u32 i = 0; i < 5; ++i) lab_result(1 + i, crc_values[i]);
    lab_result(6, COREMARK_VALIDATION);
    if (crc_seen != 31 || errors != 0 || starts != 1 || stops != 1
        || time_warnings != 1) failed = 1;
    return failed;
}
